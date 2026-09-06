# VAHANM — Reasoning and Orchestration

This document describes **why the system makes decisions and how it makes them**.

It is the canonical reference for:

- How observations are evaluated and selected
- How evidence is represented and accumulated
- How vehicle hypotheses are formed, maintained, and resolved
- How traffic rules are evaluated
- How uncertainty is modelled
- How evidence is fused
- How hypotheses are managed and backtracked
- How capabilities are modelled and selected
- How the orchestrator decides what to do next
- What components can be replaced experimentally

`01_ARCHITECTURE.md` describes **what** VAHANM is.  
`03_DEVELOPMENT_GUIDE.md` describes **how** we currently implement it.  
This document describes **why** it behaves as it does.

---

## 1. Observation Model

An observation is the **atomic unit of sensory fact** in VAHANM. It is produced by a
device, stored once, and never modified. Processing an observation produces Evidence
(Section 3) — never a modified observation.

```
Observation
├── observation_id        UUID
├── source
│   ├── cluster_id        UUID
│   ├── device_id         UUID
│   └── modality          CAMERA | RADAR | MICROPHONE | SIGNAL | OTHER
├── temporal
│   ├── timestamp         datetime (device local)
│   └── sequence_id       int (monotonic within device)
├── spatial
│   └── estimated_world   (lat, lon)  optional, if device is calibrated
├── quality
│   ├── signal_quality    float 0..1  (general signal quality for this modality)
│   └── modality_quality  dict  (modality-specific quality fields — see Section 1.1)
├── payload               dict  (modality-specific data — see Section 1.1)
└── provenance
    ├── firmware_version  str
    └── processing_notes  str
```

**An observation is immutable after creation.** There are no augmented fields, no
post-hoc additions, no capability outputs written back into the observation. The
relationship is:

```
Observation  ──(processed by capability)──▶  Evidence
```

Not:

```
Observation  ──(modified by capability)──▶  Observation+
```

This gives a clean audit trail: an observation always reflects exactly what the
device reported, nothing more.

### 1.1 Modality-Specific Payloads

Camera observations and radar observations are structurally different. Modality-
specific fields live inside `payload` and `modality_quality`, not at the top level.
This preserves the heterogeneous-device abstraction all the way down to the data model.

**Camera payload:**
```
payload:
  frame_index:      int
  bbox:             [x1, y1, x2, y2]   pixel coordinates
  centroid:         (cx, cy)
  class_id:         int   (COCO or custom)
  class_name:       str
  detection_conf:   float 0..1
  local_track_id:   int   (device-local ByteTrack ID, not globally unique)
  track_conf:       float 0..1
  direction:        [dx, dy]   pixel velocity (optional)

modality_quality:
  blur_score:       float 0..1   (1 = sharp; Laplacian variance)
  occlusion_score:  float 0..1   (0 = fully occluded)
  plate_visibility: float 0..1   (0 = plate not visible)
  illumination:     float 0..1   (0 = too dark or blown out)
```

**Radar payload:**
```
payload:
  speed_kmh:      float
  range_m:        float
  bearing_deg:    float
  radar_conf:     float 0..1

modality_quality:
  signal_snr:     float   (signal-to-noise ratio)
```

**Microphone payload:**
```
payload:
  event_type:     str    (e.g. "collision", "horn", "brake_squeal")
  duration_ms:    int
  audio_conf:     float 0..1

modality_quality:
  ambient_db:     float  (background noise level)
```

**Signal controller payload:**
```
payload:
  phase:          str    (e.g. "RED", "GREEN", "AMBER")
  duration_sec:   int
```

The Observation Manager (Section 2) and all downstream components accept an `Observation`
regardless of modality; they read `payload` only for fields relevant to their task.

---

## 2. Observation Manager

The Observation Manager sits between raw device output and the reasoning layer. Its
single responsibility is to decide what to do with each observation.

```
frame
  ↓
is this observation useful?
  ↓
discard / retain / escalate
```

Without it, a traffic jam with 30 vehicles at 30 fps produces 900 observations/second.
Most of those carry no new information.

### 2.1 Usefulness Criteria

The Observation Manager evaluates each observation against a set of criteria:

| Criterion | Description |
|-----------|-------------|
| Detection quality | Confidence above threshold |
| Track quality | Track stable for at least N frames |
| Plate visibility | Plate crop large enough and sharp enough for OCR |
| Motion novelty | Object has moved enough since last retained observation |
| Scene relevance | Object is inside a monitored zone |
| Occlusion | Object not heavily occluded |
| Illumination | Frame not too dark or blown out |
| Investigation relevance | Object matches an active investigation target |

### 2.2 Disposition Decisions

```
DISCARD       — observation carries no new information; do not store
RETAIN        — useful, store as normal tracklet observation
ESCALATE      — high value (plate visible, high-quality frame, zone entry/exit);
                flag for immediate evidence consideration
```

Escalation feeds directly into the Orchestrator's candidate action queue
(see Section 10).

### 2.3 Observation Selection vs. Evidence Selection

These are two distinct filtering steps:

```
raw frame
    ↓
Observation Manager    ↝ decides which frames produce observations
    ↓
retained observations
    ↓
Evidence Selector      ↝ decides which observations become evidence
    ↓
evidence set
    ↓
Reasoning Layer
```

The Evidence Selector is invoked by the Orchestrator when a capability is activated.
It re-evaluates the retained observation pool for the specific goal (e.g., best plate
crops for OCR, sharpest frontal frames for Re-ID).

### 2.4 State Tracked per Track

The Observation Manager maintains lightweight per-track state:

```
TrackWindow
├── local_track_id
├── last_retained_timestamp
├── last_retained_centroid
├── retained_count
├── escalated_count
├── plate_visibility_max
├── investigation_relevant    bool
└── age_frames
```

This state is transient and lives only in the edge process. It is not persisted.

---

## 3. Evidence Model

Evidence is a **curated subset of observations** selected because they are useful for
a specific reasoning goal.

```
Evidence
├── evidence_id           UUID
├── investigation_id      UUID (the investigation this serves)
├── goal                  LPR | REID | TRAJECTORY | VIOLATION_CONFIRM | ...
├── observations[]        List[observation_id]
├── quality_scores        {observation_id: float}
├── produced_by           capability_id
├── timestamp_produced    datetime
└── result                dict  (output from the capability: plate text, embedding, etc.)
```

Evidence is **immutable after creation**. A new capability invocation produces new
evidence; it does not overwrite old evidence. This preserves the audit trail.

### 3.1 Evidence Types

| Type | Produced by | Content |
|------|-------------|---------|
| PLATE_OCR | LPR capability | plate hypothesis, character confidences |
| APPEARANCE | Re-ID capability | embedding vector, reference images |
| VIOLATION_FRAME | Evidence capture | high-res annotated frame |
| SPEED | Radar / optical flow | speed estimate, confidence interval |
| TRAJECTORY_POINT | Trajectory engine | world-coordinate position estimate |
| AUDIO_EVENT | Microphone | event type, timestamp, confidence |

### 3.2 Evidence vs. Observation

| Observation | Evidence |
|-------------|----------|
| Raw detection event | Processed, goal-directed output |
| Created automatically | Created on demand by the Orchestrator |
| One per detection | One per capability invocation |
| Never interpreted in isolation | Combined by Evidence Fusion (Section 7) |

---

## 4. Vehicle Hypothesis

Before the system knows that something is a vehicle with a confirmed identity, it has
only a **hypothesis**: a belief that some set of observations belong to the same
physical vehicle.

```
VehicleHypothesis
├── hypothesis_id             UUID
├── created_at                datetime
├── updated_at                datetime
│
├── identity_hypotheses[]     List[IdentityHypothesis]  (Section 8)
│
├── physical_attributes
│   ├── vehicle_type          str (car / truck / bus / motorcycle / unknown)
│   ├── make                  str (optional)
│   ├── model                 str (optional)
│   ├── color                 str (optional)
│   └── physical_features     dict (dents, racks, stickers, etc.)
│
├── motion_state
│   ├── last_known_centroid   (cx, cy)
│   ├── last_known_velocity   [dx, dy]
│   ├── last_known_speed      float (optional)
│   └── heading               float (degrees, optional)
│
├── spatial_state
│   ├── current_cluster_id    UUID (last cluster with confirmed observation)
│   ├── current_zone          str (optional)
│   └── estimated_world_pos   (lat, lon) (optional)
│
├── temporal_state
│   ├── first_seen            datetime
│   ├── last_seen             datetime
│   ├── observation_span_sec  float
│   └── gap_since_last_obs    float (seconds, live)
│
├── evidence[]                List[evidence_id]
│
├── uncertainty
│   ├── identity_entropy      float  (over identity_hypotheses)
│   ├── position_uncertainty  float  (covariance trace or similar)
│   └── evidence_sufficiency  Enum[NONE, LOW, MEDIUM, HIGH, CONFIRMED]
│
├── candidate_observations[]  List[observation_id]  (unassigned, under evaluation)
│
├── active_investigation      investigation_id (optional)
│
└── decision_history[]        List[Decision]
```

The hypothesis is **not a vehicle record**. A vehicle record (`Vehicle` in the
persistent store) is only created when the system has sufficient evidence to commit to
a global identity. Until then, the hypothesis exists only in the reasoning layer.

### 4.1 Hypothesis Lifecycle

```
New observations cluster around a local_track_id
          ↓
VehicleHypothesis created
          ↓
Evidence accumulates (quality, zone events, etc.)
          ↓
One of three paths:
  A. Evidence sufficient → commit → Vehicle record created
  B. Evidence insufficient, track lost → hypothesis expires
  C. Violation detected → investigation opened, Orchestrator activated
```

---

## 5. State Representation

VAHANM maintains three distinct levels of state. Conflating them is the primary source
of architectural confusion in simpler systems.

```
┌──────────────────────────────────────────────────────┝
│  WORLD STATE                                         │
│  What is currently happening in the physical world.  │
│  Source: observations, device telemetry              │
│  Examples: track positions, speeds, zone occupancy   │
└──────────────────────────────────────────────────────┘
             ↓ feeds
┌──────────────────────────────────────────────────────┝
│  INVESTIGATION STATE                                 │
│  What the system is actively trying to determine.    │
│  Source: violation triggers, manual requests         │
│  Examples: active hypotheses, pending capabilities,  │
│            evidence collected so far                 │
└──────────────────────────────────────────────────────┘
             ↓ drives
┌──────────────────────────────────────────────────────┝
│  RESOURCE STATE                                      │
│  What capabilities are available right now.          │
│  Source: device registry, capability health checks   │
│  Examples: LPR available, GPU load, camera offline   │
└──────────────────────────────────────────────────────┘
```

The Orchestrator (Section 10) reads all three levels to choose the next action.

---

## 6. Traffic Rule Evaluation

Traffic rules answer: **what constitutes a violation?**

Rules are evaluated against world state. They do not interact with the hypothesis layer
directly.

### 6.1 Rule Interface

Every rule implements the same interface:

```python
class TrafficRule:
    rule_id: str
    description: str

    def evaluate(
        self,
        tracklet: Tracklet,
        world_state: WorldState,
        geometry: ZoneGeometry,
    ) -> RuleResult:
        ...

class RuleResult:
    triggered: bool
    violation_type: str          # if triggered
    confidence: float            # how certain is the trigger
    evidence_hint: EvidenceHint  # what evidence would be useful
    explanation: str             # human-readable reason
```

### 6.2 Rule Separation from State Estimation

```
Traffic Rule              "What is forbidden here?"
       ↓
State Estimator           "What probably happened?"
       ↓
Evidence Fusion           "How strongly do we believe it?"
       ↓
Orchestrator              "What should we do next?"
```

A rule evaluating a line-crossing does not need to know whether the system is using a
Kalman filter or an HMM to estimate the vehicle position. That is the state estimator's
concern. The rule only consumes the state estimator's output.

### 6.3 Rule Examples

| Rule | Trigger condition |
|------|-------------------|
| LineCrossing | Track centroid crosses a defined polyline in a forbidden direction |
| ZoneDwell | Track remains inside a no-stop zone for longer than T seconds |
| SpeedExceedance | Estimated speed exceeds posted limit by more than a margin |
| WrongWay | Track direction contradicts one-way designation on road segment |
| RedLightViolation | Track crosses stop line while signal state is RED |
| PedestrianConflict | Track enters pedestrian zone while pedestrian present |

Rules are **data-driven**: each rule reads its parameters (line geometry, speed limit,
dwell threshold) from a configuration file or database, not from hardcoded constants.

---

## 7. Uncertainty Representation

VAHANM deals with incomplete, imperfect, and sometimes contradictory evidence. The
uncertainty model must be explicit.

### 7.1 Per-observation uncertainty

Already encoded in the observation quality fields (Section 1):
`detection_conf`, `track_conf`, `blur_score`, `occlusion_score`, `plate_visibility`.

### 7.2 Per-hypothesis uncertainty

```
identity_entropy      Shannon entropy over the probability distribution of
                      identity hypotheses (Section 8). Zero when identity is confirmed;
                      maximum when all candidates are equally likely.

position_uncertainty  Covariance trace of the position estimate from the
                      temporal state estimator (Section 13). Grows with time since
                      last observation.

evidence_sufficiency  Discrete label summarising overall evidence quality:
                      NONE → LOW → MEDIUM → HIGH → CONFIRMED
```

### 7.3 What uncertainty is NOT

Uncertainty in VAHANM is **not** a catch-all excuse to ignore bad evidence.

Every piece of evidence that contradicts the current hypothesis must be explicitly
modelled as a contradiction, not silently dropped. If evidence is dropped, the reason
must be logged in the decision history.

---

## 8. Evidence Fusion

Evidence Fusion answers: **how strongly do we believe something given all available evidence?**

This is distinct from rule evaluation (which defines what constitutes a violation) and
from the state estimator (which models what probably happened).

### 8.1 Fusion Interface

```python
class EvidenceFusion:
    def fuse(
        self,
        evidence_set: List[Evidence],
        hypothesis: VehicleHypothesis,
    ) -> BeliefUpdate:
        ...

class BeliefUpdate:
    identity_scores: Dict[hypothesis_id, float]
    updated_evidence_sufficiency: EvidenceSufficiency
    contradictions: List[EvidenceContradiction]
    explanation: str
```

### 8.2 Fusion Methods (Replaceable)

The fusion method is a **pluggable component**. The interface above remains stable
regardless of which method is active:

```
Evidence Fusion
├── likelihood_scoring        weighted sum of evidence confidences (baseline)
├── bayesian_update           prior × likelihood → posterior
├── dempster_shafer           belief/plausibility intervals under ignorance
├── learned_fusion            neural / gradient-boosted scorer
└── deterministic_aggregation rule-based thresholding (simplest, lowest risk)
```

For the SIH MVP, **likelihood scoring** is the recommended starting point.
It is interpretable, debuggable, and easy to tune.

Bayesian methods and Dempster-Shafer are better candidates once the observation
distribution is better understood from real data.

### 8.3 OCR Consensus as a Fusion Problem

Temporal OCR consensus is a special case of evidence fusion:

```
OCR results across N frames
     ↓
Evidence Fusion (plate_text)
     ↓
Plate hypothesis with confidence

Input evidence:
  frame_1: "DL8CAX1234"  conf 0.91
  frame_2: "DL8CAX1284"  conf 0.67   ↝ one character differs
  frame_3: "DL8CAX1234"  conf 0.88
  frame_4: INDETERMINATE  conf 0.00   ↝ blur

Fusion output:
  best_hypothesis:   "DL8CAX1234"
  character_confs:   [0.99, 0.97, 0.98, 0.99, 0.96, 0.99, 0.91, 0.97, 0.96, 0.89]
  contradictions:    frame_2 position 7 disagrees (0.67 conf)
  sufficiency:       HIGH
```

The character-level confidence array is important: it tells the system
**which characters are uncertain**, not just the overall plate confidence.

---

## 9. Hypothesis Management and Backtracking

An investigation should not commit to a single identity prematurely. Instead, it
maintains a ranked set of competing hypotheses.

### 9.1 Hypothesis Set Structure

```
Investigation
└── hypothesis_set
    ├── H1  →  observations [A, C, F]   score: 0.81
    ├── H2  →  observations [A, B, F]   score: 0.63
    └── H3  →  observations [A, D]      score: 0.41
```

Each `IdentityHypothesis` is a candidate explanation for the same physical vehicle:
which global vehicle identity it corresponds to, and which observations support that
claim.

```
IdentityHypothesis
├── identity_hypothesis_id    UUID
├── candidate_vehicle_id      UUID (or null if new identity)
├── supporting_observations[] List[observation_id]
├── score                     float 0..1
├── contradictions[]          List[EvidenceContradiction]
└── status                    ACTIVE | WEAKENED | ABANDONED | COMMITTED
```

### 9.2 Backtracking Protocol

When new evidence contradicts the leading hypothesis:

```
new evidence E arrives
        ↓
Evidence Fusion re-evaluates all active hypotheses
        ↓
H1 score drops below H2 score?
        ↓
    YES:
        mark H1 as WEAKENED
        promote H2 to leading hypothesis
        log contradiction in decision_history
        request capability that could disambiguate H1 vs H2
        ↓
    NO:
        absorb E into H1 (or flag as noise if contradicts all)
```

Backtracking is **not retraining**. The system does not update its models at runtime.
It re-evaluates which hypothesis best explains the available evidence, which is a
purely inferential operation.

### 9.3 Termination Conditions

An investigation terminates when one of the following is met:

| Condition | Action |
|-----------|--------|
| Leading hypothesis score ≥ commitment threshold | Commit identity, create Vehicle record |
| All hypotheses below abandonment threshold | Mark as UNRESOLVED, preserve evidence |
| Resource limit reached (time, capability calls) | Commit best available, flag uncertainty |
| Manual resolution by operator | Record operator decision |
| No further disambiguating capability available | Commit best available, flag uncertainty |

### 9.4 Why Not Just Pick the Best Match?

Committing to the highest-scoring hypothesis without checking the margin is
dangerous in forensic contexts:

```
H1: score 0.52
H2: score 0.48
```

These are nearly indistinguishable. Committing to H1 and issuing a violation notice
would be incorrect. The system should instead escalate for human review or request
more evidence.

The commitment threshold and the minimum margin between H1 and H2 are
**configurable operational parameters**, not constants.

---

## 10. Capability Model

A capability is a unit of computation that can be activated on demand.

```
Capability
├── capability_id         str  (e.g., "lpr_v2", "reid_resnet50")
├── capability_type       LPR | REID | EVIDENCE_CAPTURE | RADAR_QUERY |
│                         OCR_CONSENSUS | TRAJECTORY_FIT | AUDIO_DETECT
├── resource_cost         ResourceCost
│   ├── gpu_memory_mb     int
│   ├── cpu_load_percent  float
│   ├── latency_ms        float  (expected)
│   └── network_cost      float  (for remote capabilities)
├── expected_information  float  (expected entropy reduction)
├── prerequisites         List[str]  (other capabilities or data requirements)
├── constraints           List[Constraint]  (e.g., "requires plate_visibility > 0.4")
└── available             bool  (live resource check)
```

### 10.1 Capability vs. Component

A **component** is a deployed service (a Python process, a GPU worker, a microphone
listener). A **capability** is what the system *can do* using that component.

The same component can expose multiple capabilities with different parameters or
quality levels (e.g., fast LPR at low resolution vs. precise LPR at full resolution).

### 10.2 Capability Registry

The Orchestrator queries the capability registry before selecting an action:

```
CapabilityRegistry
├── list_available(device_id)       → List[Capability]
├── estimate_cost(capability_id)    → ResourceCost
├── check_constraints(capability_id, observation) → bool
└── invoke(capability_id, observation_ids) → Evidence
```

---

## 11. Orchestrator

The Orchestrator is the central decision-making component of VAHANM. It answers:
**given what we know and what we can do, what should we do next?**

### 11.1 Orchestrator State

```
Orchestrator
├── world_state           WorldState       (Section 5)
├── investigation_state   InvestigationState
├── resource_state        ResourceState
├── capability_registry   CapabilityRegistry (Section 10)
├── active_investigations List[Investigation]
├── candidate_actions     PriorityQueue[Action]
├── action_history        List[ActionRecord]
└── constraints
    ├── max_concurrent_investigations   int
    ├── max_capability_calls_per_inv    int
    ├── investigation_timeout_sec       float
    └── commitment_threshold            float
```

### 11.2 Decision Loop

```
new event / evidence arrives
          ↓
update world state
          ↓
for each active investigation:
    re-evaluate hypotheses (Evidence Fusion)
    check termination conditions
    if terminated: commit or abandon
          ↓
for each active investigation that continues:
    generate candidate actions
    estimate usefulness (expected entropy reduction)
    estimate cost (ResourceCost)
    check constraints
    rank candidates
    select and execute highest-ranked feasible action
          ↓
receive action result (new Evidence)
          ↓
update investigation state
          ↓
log to decision_history
          ↓
repeat
```

### 11.3 Action Generation

The Orchestrator generates candidate actions by asking:
*"What observation or capability would most reduce our uncertainty right now?"*

Candidate actions include:

| Action | Trigger |
|--------|---------|
| Invoke LPR on best plate crop | plate visible, identity uncertain |
| Invoke Re-ID on appearance crop | identity uncertain, no plate |
| Request high-res evidence frame | violation confirmed, need evidence |
| Query adjacent cluster | vehicle may have moved to cluster B |
| Trigger radar query | speed estimate needed |
| Escalate to human operator | evidence insufficient at termination |
| Commit identity | evidence sufficiency ≥ HIGH |
| Abandon investigation | all hypotheses below threshold, timeout |

### 11.4 Usefulness Estimation

Expected usefulness of an action is approximated by:

```
usefulness(action) ≈ expected_entropy_reduction(action)
                   × probability_action_succeeds
                   - cost(action)
```

In practice this is estimated heuristically rather than computed exactly, especially
early in development. The estimation method is a **replaceable component**:

```
Usefulness Estimator
├── heuristic (rule-based, baseline)
├── lookup table (trained on past investigations)
├── learned model (future)
└── utility function (explicit cost/benefit)
```

### 11.5 The ↺ Loop

The iterative loop is the core of VAHANM's intelligence:

```
evidence
    ↓
belief update
    ↓
new action selected
    ↓
new evidence collected
    ↓
belief update
    ↓
    ↺
```

This loop terminates when a termination condition is met (Section 9.3), not after a fixed
number of steps. The system may collect evidence from multiple clusters, invoke
multiple capabilities, and backtrack multiple times before committing.

---

## 12. Resource and Utility Scoring

The Orchestrator needs a consistent way to compare the value of different actions.

### 12.1 Resource Cost

```
ResourceCost
├── gpu_memory_mb         int
├── cpu_load_percent      float
├── latency_ms            float
├── network_bytes         int
└── financial_cost        float  (for cloud APIs, if applicable)
```

### 12.2 Information Value

The **expected information value** of an action is the expected reduction in hypothesis
uncertainty if the action succeeds:

```
IV(action) = H(hypotheses_before) - E[H(hypotheses_after | action)]
```

Where H is Shannon entropy over hypothesis scores.

An action with high IV is worth invoking even at moderate cost.
An action with low IV should not be invoked even if it is cheap.

### 12.3 Urgency

Some investigations are time-critical:

```
urgency(investigation) = violation_severity × time_since_event × decay_factor
```

High-urgency investigations preempt lower-urgency ones in the capability queue.

### 12.4 Constraint Checking

Before any action is selected:

1. Device/capability available?
2. Prerequisites satisfied?
3. Observation quality meets capability constraints?
4. Resource budget not exceeded?
5. Investigation not timed out?

If any check fails, the action is skipped and the next candidate is evaluated.

---

## 13. Temporal State Estimation

Temporal state estimation answers: **where is the vehicle, and how is it moving?**

This feeds the Orchestrator's camera/cluster selection decisions, the rule evaluator's
position queries, and the hypothesis scoring.

### 13.1 Estimation Interface

```python
class TemporalStateEstimator:
    def update(self, observation: Observation) -> VehicleState:
        ...

    def predict(self, delta_t: float) -> VehicleState:
        ...

    def uncertainty(self) -> float:
        ...
```

### 13.2 Estimation Methods (Replaceable)

```
Temporal State Estimator
├── heuristic_baseline     last known position + linear extrapolation
├── kalman_filter          standard Kalman, constant velocity model
├── extended_kalman        for nonlinear motion models
├── particle_filter        for multimodal position distributions
├── hmm                    for discrete state transitions (lane changes, turns)
└── learned_model          future: learned motion prior
```

The **heuristic baseline** is the correct starting point. It is interpretable and
requires no training data.

The **Kalman filter** is the natural second step when a continuous position estimate
with uncertainty bounds is needed.

An **HMM** is appropriate when the vehicle's state is better described as a sequence
of discrete events (e.g., stopped → moving → turning) rather than a continuous
trajectory. This is an experiment to run once the simpler estimators are working.

All estimators expose the same interface. Switching between them does not change any
other component.

### 13.3 Temporal Feasibility

Temporal feasibility is the check used during cross-cluster association:

```
observation_A  at cluster_A  at time T1
observation_B  at cluster_B  at time T2

feasible if:
    min_travel_time(A → B) ≤ (T2 - T1) ≤ max_travel_time(A → B)
```

`min_travel_time` and `max_travel_time` are derived from the road graph and known
speed limits. This filter is cheap and eliminates most impossible matches before any
expensive similarity computation is run.

---

## 14. Camera and Node Selection

When the Orchestrator needs more observations, it must decide **which cluster to query
next**.

### 14.1 Candidate Cluster Generation

Given a VehicleHypothesis at cluster A at time T, candidate next clusters are:

```
road_graph.reachable(cluster_A, min_time=T+δ_min, max_time=T+δ_max)
```

This produces a set of clusters the vehicle could plausibly have reached given its
last known position, velocity, and the elapsed time.

### 14.2 Cluster Ranking

Candidate clusters are ranked by:

```
cluster_score = p_vehicle_reached × observation_quality_estimate × capability_availability
```

Where:
- `p_vehicle_reached` — probability the vehicle reached this cluster (from temporal model)
- `observation_quality_estimate` — expected quality of observations from this cluster
- `capability_availability` — whether the needed capabilities are available at this cluster

The top-ranked cluster is queried first.

### 14.3 Parallel Queries

When time permits and resources allow, the Orchestrator may query multiple candidate
clusters in parallel. Results are fed back into the hypothesis evaluation loop as they
arrive.

---

## 15. Learning and Adaptation Boundary

VAHANM is **not a self-training system at runtime**.

The boundary between static and adaptive components is:

```
┌────────────────────────────────────────────────────────────┝
│  STATIC (not updated at runtime)                           │
│                                                            │
│  YOLO weights                                              │
│  Re-ID model weights                                       │
│  OCR model weights                                         │
│  Fusion method implementation                              │
│  Rule definitions                                          │
│  Road graph topology                                       │
└────────────────────────────────────────────────────────────┘
                         ↕  offline training / configuration
┌────────────────────────────────────────────────────────────┝
│  ADAPTIVE (updated via configuration or offline training)  │
│                                                            │
│  Fusion weights (can be retrained offline)                 │
│  Rule parameters (zone geometry, speed limits, thresholds) │
│  Capability costs (updated from observed latency)          │
│  Commitment threshold (operational tuning)                 │
└────────────────────────────────────────────────────────────┘
                         ↕  future research
┌────────────────────────────────────────────────────────────┝
│  FUTURE (not in current scope)                             │
│                                                            │
│  Online model fine-tuning                                  │
│  Reinforcement-learned orchestration policy                │
│  Continual learning from investigation outcomes            │
└────────────────────────────────────────────────────────────┘
```

This boundary prevents the runtime system from being described as "learning" when it
is actually inferring, and it gives a clear target for future research extensions.

---

## 16. Simulation Environment

Before deploying reasoning components against live cameras, they should be exercised
in a simulation environment.

### 16.1 What the Simulation Provides

```
SimulatedWorld
├── synthetic_video_source      (pre-recorded or generated traffic)
├── ground_truth_tracks         (known vehicle positions)
├── ground_truth_violations     (known violation events)
├── injected_noise              (configurable detection errors, OCR errors)
├── simulated_cluster_topology  (defined graph of fake clusters)
└── oracle_capability           (returns ground truth evidence on demand)
```

### 16.2 What Can Be Tested

| Component | Simulation test |
|-----------|----------------|
| Observation Manager | Does it correctly discard/retain/escalate? |
| Rule Evaluator | Does it trigger on correct events, not false ones? |
| Evidence Fusion | Does it correctly promote/demote hypotheses? |
| Hypothesis Manager | Does it backtrack correctly when evidence conflicts? |
| Orchestrator | Does it select the right capabilities? Does it terminate correctly? |
| Temporal Estimator | Does it maintain accurate position predictions? |
| Cross-cluster association | Does it correctly link vehicles across clusters? |

### 16.3 Simulation vs. Live Testing

The simulation is not a replacement for live testing. It is used to:
- Establish baseline behaviour before live deployment
- Reproduce edge cases that are hard to observe in the wild
- Run regression tests after changes to reasoning components

---

## 17. Experimental Roadmap

The following components are marked for experimental investigation, in order of
expected priority:

| # | Component | Experiment | Metric |
|---|-----------|------------|--------|
| 1 | Evidence Fusion | likelihood scoring vs. Bayesian update | precision/recall of identity commitment |
| 2 | Temporal Estimator | heuristic baseline vs. Kalman filter | position error at T+30s |
| 3 | OCR Consensus | simple majority vote vs. character-level fusion | plate accuracy on noisy crops |
| 4 | Hypothesis scoring | fixed weights vs. learned weights | investigation termination accuracy |
| 5 | Orchestration | greedy action selection vs. look-ahead | average capabilities per investigation |
| 6 | Temporal Estimator | Kalman vs. HMM | position error + state transition accuracy |
| 7 | Evidence Fusion | Dempster-Shafer for contradictory evidence | resolution rate on contradictory observations |
| 8 | Orchestration | heuristic utility vs. learned policy | resource consumption vs. accuracy trade-off |

Each experiment:
1. Has a baseline (the simpler method) and a challenger
2. Uses the same interface (Section 7, 13, 11.4) so that swapping is a configuration change
3. Is evaluated on the simulation environment before live data
4. Is documented in the decision history when the component is swapped in production

---

## Document Relationships

```
00_PROJECT_OVERVIEW.md
    What VAHANM is and why it exists.

01_ARCHITECTURE.md
    The structural components, data models, and information flow.
    References this document for reasoning behaviour.

02_REASONING_AND_ORCHESTRATION.md  ↝ this document
    How the system reasons, manages evidence, and makes decisions.
    Defines the interfaces that implementation must satisfy.

03_DEVELOPMENT_GUIDE.md
    The current implementation: which libraries, which commands, which phases.
    References this document for component boundaries.
```

Implementation choices in `03_DEVELOPMENT_GUIDE.md` (e.g., which OCR library, which
fusion method) are **decisions about current implementations of the interfaces defined
here**. Changing the implementation does not require changing this document, only
`03_DEVELOPMENT_GUIDE.md`.

