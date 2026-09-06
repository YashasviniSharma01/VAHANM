# VAHANM — Project Overview

## What VAHANM Is

**VAHANM** is a distributed, edge-first vehicle monitoring system built for the BEL
challenge:

> City-Wide AI Engine for Multi-Camera ANPR, Trajectory Tracking, and Urban Traffic
> Analytics.

The system processes geographically distributed camera streams, detects and tracks
vehicles at the edge, identifies traffic violations, performs license-plate
recognition, associates vehicles across cameras, and reconstructs their movement
through a city-wide road network.

The central design question VAHANM answers is not:

> "Where is the vehicle?"

It is:

> "Given an event, how do we spend the minimum amount of computational and sensing
> resources necessary to establish what happened, and collect evidence that can stand
> up to scrutiny?"

---

## Core Principles

**1. Edge-first computation.**
Heavy video processing stays at the source. The network carries compact metadata, not
raw video.

**2. Capability activation, not continuous processing.**
The system does not run OCR, Re-ID, and high-resolution capture continuously. These
are activated when an event justifies the cost.

**3. Nodes are clusters of heterogeneous devices, not cameras.**
A monitoring location contains cameras, radars, microphones, and signal controllers.
Each device has an independent identity and capability set. The cluster coordinates
them.

**4. Iterative investigation, not a forward pipeline.**
Once a violation is detected, the system enters an investigation loop: collect
evidence, update beliefs, select the next most useful action, repeat. It may
backtrack, query multiple clusters, and invoke multiple capabilities before committing
to an identity.

**5. Implementation is separate from architecture.**
The reasoning model is defined by interfaces, not by specific libraries. Which OCR
engine, which fusion method, and which estimator are currently in use is recorded in
`03_DEVELOPMENT_GUIDE.md`, not here.

---

## The Five Subsystems

```
                        VAHANM
                           │
          ┌────────────────┼─────────────────┝
          │                                  │
    EDGE LAYER                        CENTRAL SYSTEM
          │                                  │
   ┌──────┼──────┝                    ┌──────┼──────┝
   ▼      ▼      ▼                    ▼             ▼
 YOLO  ByteTrack Sensors        Investigation   Persistence
   │      │      │              & Orchestration      │
   └──────┼──────┘                    │         PostgreSQL
          ▼                           │
   Observation Manager                │
          │                           │
          └──────────────┬────────────┘
                         ▼
                  STATE / EVIDENCE
                         │
             ┌───────────┼────────────┝
             ▼           ▼            ▼
          Rules       Belief       Hypotheses
          engine      estimation    management
             │           │            │
             └───────────┼────────────┘
                         ▼
                    ORCHESTRATOR
                         │
               ┌─────────┼──────────┝
               ▼         ▼          ▼
              LPR       Re-ID    Sensors
               │         │          │
               └─────────┼──────────┘
                         ▼
                   new evidence
                         │
                         ↺
```

The **↺** is the defining feature of VAHANM's intelligence. The system does not make
a single pass and commit. It iterates: new evidence updates beliefs, beliefs drive new
capability activations, new capabilities produce new evidence.

---

## Subsystem Responsibilities

### Edge Layer

Runs at or near the camera. Responsible for producing observations.

- **YOLO detection** — finds vehicles in each frame
- **ByteTrack tracking** — assigns locally-consistent track IDs across frames
- **Sensors** — radar speed, microphone event detection, signal state
- **Observation Manager** — evaluates each observation: discard, retain, or escalate

The Observation Manager is the gatekeeper between raw detections and the reasoning
layer. In a dense traffic scene it prevents the system from storing hundreds of
redundant observations per second. See `02_REASONING_AND_ORCHESTRATION.md Section 2`.

### State / Evidence Layer

Holds the current beliefs about vehicles and investigations.

- **Rules engine** — evaluates what constitutes a violation against world state
- **Belief estimation** — models vehicle position and motion over time
- **Hypothesis management** — maintains competing identity candidates,
  scores them, and backtracks when evidence contradicts the leading hypothesis

See `02_REASONING_AND_ORCHESTRATION.md Section 4–9`.

### Orchestrator

The decision-making core. Reads world state, investigation state, and resource state
to decide what to do next: which capability to invoke, which cluster to query, when to
commit, when to escalate to a human operator.

See `02_REASONING_AND_ORCHESTRATION.md Section 10–12`.

### Capabilities (on-demand)

Expensive computation invoked only when an investigation justifies it:

- **LPR** — license plate recognition on selected high-quality crops
- **Re-ID** — appearance-based vehicle matching
- **Evidence capture** — high-resolution annotated frames for violation records
- **Radar query** — speed measurement
- **OCR consensus** — temporal fusion of multiple plate reads

### Persistence

- **PostgreSQL** — vehicles, observations, tracklets, violations, investigations,
  evidence, decision history
- **Object storage** — evidence frames, video clips (optional)

---

## What VAHANM Is Not

**Not a batch processor.** It operates on live streams and must produce timely
decisions.

**Not a self-learning system at runtime.** Model weights are static during operation.
Fusion parameters can be tuned offline. See
`02_REASONING_AND_ORCHESTRATION.md Section 15`.

**Not a deterministic pipeline.** The same violation can trigger a different sequence
of capability activations depending on resource availability, evidence quality, and
which hypotheses are active.

**Not a single-camera system.** The cross-cluster investigation loop is a first-class
design concern, not an afterthought.

---

## Incremental Build Order

The system is built in phases to prove each loop before adding the next.

### Phase 1 — First Working Tracker ✅
Prove: `video → detection → tracking → observation JSON`

**Complete.** `backend/intelligence/perception/detection/edge_tracker.py`

- YOLO26n (`yolo26n.pt`, cached in `backend/`)
- Ultralytics built-in ByteTrack via `model.track(tracker="bytetrack.yaml")`
- JSON observation output: `output/observations.json`
- Tested live at ~22–24 FPS on CPU (640×480 webcam)
- No database, no OCR, no multi-camera

### Phase 2 — Observation Manager ❳
Prove: `observations are filtered, not blindly stored`

- Track quality scoring (age, confidence, motion novelty)
- Plate visibility scoring (bbox size + Laplacian blur)
- Disposition: DISCARD / RETAIN / ESCALATE
- Integrates into `EdgeTracker.track()` loop

### Phase 3 — Violation Detection ❳
Prove: `a rule fires correctly against world state`

- Line-crossing geometry (Shapely)
- Rule interface: `evaluate(prev_centroid, curr_centroid, track_conf) → RuleResult`
- Violation JSON output; rule does not invoke capabilities

### Phase 4 — Evidence Capture ❳
Prove: `a violation produces an immutable storable evidence record`

- Best-frame selection from N frames around violation timestamp
- Evidence dataclass: frozen, goal-tagged, references observation IDs
- Evidence frames saved to `output/evidence/`
- Reuses `YOLODetector._extract_crops()` for bbox cropping

### Phase 5 — LPR Capability ❳
Prove: `OCR runs on demand, not on every frame`

- `LPRCapability` interface defined; engine not yet selected
- Temporal OCR consensus across multiple crops
- `PlateHypothesis` with character-level confidence array
- Engine candidates: EasyOCR, PaddleOCR, Tesseract, custom fine-tuned

### Phase 6 — Hypothesis Management ❳
Prove: `the system maintains competing identity candidates`

- `VehicleHypothesis` and `IdentityHypothesis` structures
- Likelihood scoring (baseline fusion method)
- Backtracking on contradictory evidence

### Phase 7 — FastAPI Transport ❳
Prove: `edge observations reach the central system`

- FastAPI native WebSocket (not Socket.IO)
- Compact event protocol — no video bytes over the wire
- PostgreSQL persistence
- `main.py` becomes the app entry point

### Phase 8 — Orchestrator ❳
Prove: `the investigation loop runs end-to-end`

- Orchestrator async decision loop
- Capability registry with cost and constraint checking
- Action selection, execution, belief update, termination
- ↺ loop: evidence → belief → action → evidence
- Termination conditions

### Phase 9 — Multi-Cluster Association

### Phase 9 — Multi-Cluster Association ❳
Prove: `the same vehicle is identified across two clusters`

- Road graph (NetworkX) with `min_travel_time_sec` / `max_travel_time_sec` per edge
- Temporal feasibility filter runs before any appearance comparison
- Cross-cluster hypothesis linking

### Phase 10 — Web Platform ❳
Visualise: live tracking, violations, trajectories, investigation state

- One framework: React, Vue, or Angular (decided at Phase 10 start)
- FastAPI native WebSocket feed (not Socket.IO)
- Map visualisation: Leaflet or Mapbox GL JS (decided at Phase 10 start)

---

## What Is Novel About This Architecture

Comparable systems treat a camera network as a set of independent cameras and perform
identity resolution as a post-processing step. VAHANM differs in three ways:

**Nodes are not cameras.** The cluster abstraction decouples logical monitoring
locations from physical devices. A cluster can have its camera replaced, upgraded, or
supplemented with a radar without changing any identity records.

**Investigation is iterative, not single-pass.** The system backtracks when evidence
contradicts the leading hypothesis, rather than committing to the first plausible
match. This matters in forensic contexts where a wrong match is worse than no match.

**Reasoning components are interfaces, not implementations.** The temporal estimator,
evidence fusion method, and orchestration policy are all replaceable. The system can
be operated with simple heuristics for a demo and upgraded to learned models without
changing the architecture.

---

## Document Map

| Document | Contents |
| ---------- | ---------- |
| `00_PROJECT_OVERVIEW.md` | What VAHANM is, why it exists, build order |
| `01_ARCHITECTURE.md` | Structural components, data models, information flow |
| `02_REASONING_AND_ORCHESTRATION.md` | How the system reasons, manages hypotheses, orchestrates |
| `03_DEVELOPMENT_GUIDE.md` | Current implementation: libraries, commands, active phases |
| `04_CONTRIBUTING.md` | Contribution guidelines |

---

## Licensing Note

VAHANM uses Ultralytics models (YOLO26) which are licensed under AGPL-3.0 for open
source use. Commercial, embedded, or proprietary deployment requires an Enterprise
License.

Review before deployment: <https://www.ultralytics.com/license>

