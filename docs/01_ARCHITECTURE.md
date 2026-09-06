# VAHANM Architecture

This document describes the **structural components, data models, and information
flow** of VAHANM.

It does not describe how the system reasons or makes decisions — that is in
`02_REASONING_AND_ORCHESTRATION.md`.

It does not describe how the system is currently implemented — that is in
`03_DEVELOPMENT_GUIDE.md`.

---

## 1. Structural Overview

VAHANM is divided into two physical tiers and one logical cross-cutting layer.

```
┌─────────────────────────────────────────────────────────────┝
│  EDGE TIER                                                  │
│  Runs at or near the camera.                                │
│                                                             │
│  ┌──────────┝  ┌──────────┝  ┌──────────┝  ┌───────────┝  │
│  │ Detection│  │ Tracking │  │ Sensors  │  │ Obs.Mgr.  │  │
│  │ (YOLO)   │  │(ByteTrack│  │(Radar,   │  │ filter /  │  │
│  │          │  │          │  │ Mic, etc)│  │ escalate  │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └─────┬─────┘  │
│       └─────────────┴─────────────┴───────────────┘        │
│                             │                               │
│                      Observations                           │
│                             │                               │
│                      Event Transport                        │
│                     (compact metadata)                      │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┝
│  CENTRAL TIER                                               │
│  Runs on a server or cluster.                               │
│                                                             │
│  ┌──────────────────────────────────────────────────────┝  │
│  │  Reasoning Layer                                     │  │
│  │  Rules │ State Estimation │ Evidence Fusion          │  │
│  │  Hypothesis Management │ Orchestrator                │  │
│  │  (see 02_REASONING_AND_ORCHESTRATION.md)             │  │
│  └─────────────────────┬────────────────────────────────┘  │
│                        │                                    │
│  ┌─────────────────────┼────────────────────────────────┝  │
│  │  Capability Layer   │                                │  │
│  │  Capabilities execute at edge OR central tier.      │  │
│  │  The Orchestrator selects both what and where.      │  │
│  │  See Section 4 (Capability Execution Location).            │  │
│  └─────────────────────┼────────────────────────────────┘  │
│                        │                                    │
│  ┌─────────────────────┼────────────────────────────────┝  │
│  │  Persistence Layer  │                                │  │
│  │  PostgreSQL │ Object Store (evidence frames)         │  │
│  └─────────────────────┼────────────────────────────────┘  │
│                        │                                    │
│  ┌─────────────────────┼────────────────────────────────┝  │
│  │  API Layer          │                                │  │
│  │  FastAPI REST │ WebSocket (live feed to web platform)│  │
│  └─────────────────────┴────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┝
│  WEB PLATFORM                                               │
│  Browser-based visualisation and operator interface.        │
│                                                             │
│  Dashboard │ Map │ Violation Log │ Investigation View       │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Core Data Models

### 2.1 Cluster

A cluster is a **logical monitoring location**, not a physical camera.

```
Cluster
├── cluster_id          UUID  (persistent; survives device replacement)
├── label               str   (human-readable name)
├── location            (latitude, longitude)  approximate
├── topology_ref        str   (road segment ID or intersection ID)
├── state               Enum[IDLE, ACTIVE, INVESTIGATING, OFFLINE]
├── devices[]           List[Device]
├── created_at          datetime
└── updated_at          datetime
```

A cluster retains its identity when a camera is replaced, upgraded, or joined by
additional sensors. The cluster UUID is what other components reference.

### 2.2 Device

A device is a **physical or virtual sensing unit** attached to a cluster.

```
Device
├── device_id           UUID  (persistent)
├── cluster_id          UUID  (foreign key → Cluster)
├── device_type         Enum[CAMERA, RADAR, MICROPHONE, SIGNAL_CONTROLLER, OTHER]
├── capabilities[]      List[str]  e.g. ["detection", "tracking", "lpr", "reid"]
├── state               Enum[IDLE, ACTIVE, PROCESSING, OFFLINE]
├── calibration         dict  (intrinsics, extrinsics, world transform — optional)
├── metadata            dict  (hardware model, firmware, resolution, etc.)
├── created_at          datetime
└── updated_at          datetime
```

### 2.3 Observation

An observation is the **atomic unit of sensory output** produced by a device for a
single detected object in a single frame. See `02_REASONING_AND_ORCHESTRATION.md Section 1`
for the full field specification.

Key fields:

```
Observation
├── observation_id      UUID
├── cluster_id          UUID
├── device_id           UUID
├── modality            CAMERA | RADAR | MICROPHONE | SIGNAL | OTHER
├── timestamp           datetime
├── quality             {blur, occlusion, plate_visibility, illumination}
└── payload             modality-specific data (see Section 2 of 02_REASONING_AND_ORCHESTRATION.md)
```

Observations are **immutable after creation**. They are sensory facts. Processing
an observation produces Evidence (Section 2.7), never a modified observation.

See `02_REASONING_AND_ORCHESTRATION.md Section 1` for the full field specification.

### 2.4 Tracklet

A tracklet is a **sequence of observations sharing the same local track ID** on the
same device, representing one vehicle tracked continuously within a single camera's
view.

```
Tracklet
├── tracklet_id                 UUID
├── cluster_id                  UUID
├── device_id                   UUID
├── local_track_id              int
├── first_observation_id        UUID
├── last_observation_id         UUID
├── first_observation_time      datetime
├── last_observation_time       datetime
├── observation_count           int
├── plate_visibility_max        float
├── estimated_speed             float  (optional)
├── direction                   [dx, dy]  (optional)
└── created_at                  datetime
```

A tracklet is **local to a device**. Cross-device identity resolution happens in the
reasoning layer via VehicleHypothesis (see `02_REASONING_AND_ORCHESTRATION.md Section 4`).

### 2.5 VehicleHypothesis

A vehicle hypothesis is the reasoning layer's working model of a vehicle whose global
identity has not yet been committed.

It maintains competing IdentityHypotheses, accumulated evidence, and uncertainty
estimates. The **in-memory hypothesis** is transient; the **investigation record** —
including all hypotheses (committed, weakened, and abandoned), all evidence, and the
full decision history — is persisted when the investigation closes.

This ensures the backtracking story is auditable: you can reconstruct why H1 was
weakened, why H2 was selected, and what evidence drove the final commitment.

See `02_REASONING_AND_ORCHESTRATION.md Section 4` for the full model.

### 2.6 Vehicle

A vehicle record is created only when the reasoning layer commits to a global identity.

```
Vehicle
├── vehicle_id              UUID  (global, unique across all clusters)
├── plate_text              str   (optional, from LPR)
├── plate_confidence        float (optional)
├── appearance_embedding    List[float]  (optional, from Re-ID)
├── physical_attributes     dict  (type, color, make, model, features)
├── first_seen              datetime
├── last_seen               datetime
├── last_cluster_id         UUID
└── created_at              datetime
```

The `Vehicle` record is the **committed output** of a resolved investigation. It is
not used as a working identity during an active investigation — that is the role of
`VehicleHypothesis`.

### 2.7 Evidence

Evidence is a curated subset of observations produced by a capability invocation for a
specific reasoning goal.

See `02_REASONING_AND_ORCHESTRATION.md Section 3` for the full model.

Key fields:

```
Evidence
├── evidence_id             UUID
├── investigation_id        UUID
├── goal                    LPR | REID | VIOLATION_CONFIRM | TRAJECTORY | ...
├── observations[]          List[observation_id]
├── produced_by             capability_id
├── timestamp_produced      datetime
└── result                  dict  (plate hypothesis, embedding, frame path, etc.)
```

Evidence is **immutable after creation**. A new capability invocation produces new
evidence; it does not modify existing evidence.

### 2.8 Violation

```
Violation
├── violation_id        UUID
├── vehicle_id          UUID  (null until investigation resolves)
├── hypothesis_id       UUID  (the working hypothesis at time of detection)
├── cluster_id          UUID
├── device_id           UUID
├── violation_type      Enum[LINE_CROSSING, SPEEDING, WRONG_WAY,
│                            RED_LIGHT, PEDESTRIAN_CONFLICT, OTHER]
├── timestamp           datetime
├── location            (latitude, longitude)
├── severity            Enum[LOW, MEDIUM, HIGH, CRITICAL]
├── rule_id             str   (which rule triggered)
├── evidence[]          List[evidence_id]
├── state               Enum[DETECTED, UNDER_INVESTIGATION, VERIFIED,
│                            INSUFFICIENT_EVIDENCE, RESOLVED]
└── created_at          datetime
```

### 2.9 Investigation

An investigation is an active reasoning session opened when a violation or significant
event triggers the Orchestrator.

```
Investigation
├── investigation_id        UUID
├── opened_at               datetime
├── closed_at               datetime  (null while active)
├── trigger                 violation_id or event description
├── hypothesis_set[]        List[VehicleHypothesis]
├── evidence_collected[]    List[evidence_id]
├── capabilities_invoked[]  List[capability_id]
├── decision_history[]      List[Decision]
├── outcome                 Enum[COMMITTED, UNRESOLVED, INSUFFICIENT_EVIDENCE,
│                                OPERATOR_RESOLVED]
└── committed_vehicle_id    UUID  (null until committed)
```

---

## 3. Information Flow

### 3.1 Normal Operation

```
Camera frame
     ↓
YOLO detection          produces raw bounding boxes
     ↓
ByteTrack tracking      assigns local_track_id
     ↓
Observation created     stored locally on edge
     ↓
Observation Manager     discard / retain / escalate
     ↓
Retained observations   form Tracklets
     ↓
Compact event           sent to central tier (no video)
     ↓
Central: world state updated
```

Only compact metadata leaves the edge. No video is streamed to the central tier
during normal operation.

### 3.2 Violation Trigger

```
Tracklet + world state
     ↓
Rule evaluation         "does this tracklet violate rule R?"
     ↓
RuleResult.triggered = True
     ↓
Violation record created (state: DETECTED)
     ↓
Investigation opened
     ↓
Orchestrator activated  (see Section 3.3)
```

### 3.3 Investigation Loop

```
Orchestrator reads: world state + investigation state + resource state
     ↓
Candidate actions generated
     ↓
Best action selected (usefulness / cost / constraints)
     ↓
Capability invoked
     ↓
Evidence produced
     ↓
Hypothesis set re-evaluated (Evidence Fusion)
     ↓
Termination check
     ├── not met → loop back ↺
     └── met → commit identity / resolve / escalate
```

For the full decision loop, backtracking protocol, and termination conditions, see
`02_REASONING_AND_ORCHESTRATION.md Section 9–11`.

### 3.4 Cross-Cluster Association

```
Vehicle hypothesis at Cluster A, time T
     ↓
Road graph: reachable clusters from A within feasible time window
     ↓
Candidate clusters ranked by probability, observation quality, capability availability
     ↓
Query top-ranked cluster for matching observations
     ↓
Temporal feasibility check (min/max travel time A → B)
     ↓
Evidence fusion: appearance + plate similarity
     ↓
Hypothesis score updated
     ↓
Loop ↺ until committed or abandoned
```

---

## 4. Capability Execution Location

A capability's execution location is part of its registration, not fixed by the
architecture. The Orchestrator selects **both which capability to invoke and where
to execute it**.

```
                  Capability Registry
                         │
          ┌──────────────┴──────────────┝
          ▼                             ▼
       EDGE                         CENTRAL
  ─────────────────────       ─────────────────────────
  LPR (fast, low-res)         LPR (precise, heavy model)
  Re-ID (lightweight)         Re-ID (large embedding model)
  Evidence Capture            Evidence Storage
  Radar Query                 Graph Reasoning
  Observation Manager         Hypothesis Management
```

**Evidence Capture is intentionally split:**

```
Evidence Capture Capability   →  executes at EDGE
    central sends: "I need evidence from device X around time T"
    edge: retrieve frame, crop vehicle region, encode, attach provenance
    edge sends: Evidence record (bytes + metadata)

Evidence Storage              →  executes at CENTRAL
    receives Evidence record from edge
    persists to object store + PostgreSQL
```

This prevents the central server from needing the video stream.
Capture happens where the data is; storage happens where the database is.

The capability registration for any capability looks like:

```
Capability
├── capability_id         str
├── capability_type       LPR | REID | EVIDENCE_CAPTURE | RADAR_QUERY | ...
├── execution_location    EDGE | CENTRAL | EDGE_OR_CENTRAL
├── available_at[]        List[device_id or "central"]
├── resource_cost         ResourceCost
├── expected_information  float
├── prerequisites         List[str]
└── constraints           List[Constraint]
```

`execution_location = EDGE_OR_CENTRAL` means the same capability type exists at both
tiers with different quality/cost profiles. The Orchestrator selects based on urgency,
resource state, and expected information value.

---

## 5. Component Responsibilities

| Component | Tier | Responsibility |
|-----------|------|----------------|
| YOLO Detector | Edge | Vehicle detection per frame |
| ByteTrack | Edge | Local track ID assignment |
| Sensor Adapters | Edge | Radar, microphone, signal state |
| Observation Manager | Edge | Filter / retain / escalate observations |
| Evidence Capture | Edge | Crop and encode frames on request from Orchestrator |
| LPR (fast) | Edge | Low-latency plate read on capable edge devices |
| Re-ID (lightweight) | Edge | Lightweight appearance embedding on capable edge devices |
| Event Transport | Edge→Central | Send compact observation events (no video) |
| Rules Engine | Central | Evaluate violation conditions against world state |
| State Estimator | Central | Model vehicle position and motion over time |
| Evidence Fusion | Central | Combine evidence into belief updates |
| Hypothesis Manager | Central | Maintain, score, and backtrack hypotheses |
| Orchestrator | Central | Select and execute investigation actions |
| Capability Registry | Central | Track all available capabilities, costs, and locations |
| LPR (precise) | Central | High-accuracy plate recognition on central GPU |
| Re-ID (full) | Central | Large-model appearance embedding |
| Evidence Storage | Central | Persist evidence frames and records |
| Road Graph | Central | Cluster topology, reachability, travel time |
| PostgreSQL | Central | Persistent storage for all records |
| FastAPI | Central | REST API and WebSocket for web platform |
| Web Platform | Client | Operator interface, map visualisation |

---

## 6. State Machine

The cluster state machine governs resource allocation at the edge.

```
IDLE
  │  (device comes online, normal traffic)
  ▼
ACTIVE
  │  (violation detected / significant event)
  ▼
INVESTIGATING
  │  (investigation resolves)
  ├──→ ACTIVE  (return to normal monitoring)
  └──→ IDLE    (no traffic, quiet period)

OFFLINE (any state → device unreachable → OFFLINE → reconnects → ACTIVE)
```

Capability activation is tied to state:

| State | Active capabilities |
|-------|---------------------|
| IDLE | None (device standby) |
| ACTIVE | Detection + Tracking + Observation Manager |
| INVESTIGATING | + LPR + Re-ID + Evidence Capture + Radar Query (as needed) |

---

## 7. Stable vs. Unstable Vehicle Attributes

Vehicle attributes are used in hypothesis scoring. They are divided by how frequently
they change:

### Stable (useful for identity)

| Attribute | Change frequency |
|-----------|-----------------|
| Vehicle type (car/truck/bus) | Never |
| Make and model | Never unless modified |
| Color | Years (unless repainted) |
| Physical features (dents, racks) | Years |
| Appearance embedding | Years |

### Unstable (useful only for search-space reduction)

| Attribute | Change frequency |
|-----------|-----------------|
| Driver identity | Each trip |
| Driver clothing | Each trip |
| Visible accessories | Each trip |
| Items visible inside vehicle | Each trip |

Unstable attributes are used to narrow candidate lists but are never used as the
primary basis for committing an identity. Scoring them as stable leads to false
matches.

---

## 8. Architecture Differentiators

These are the properties that distinguish VAHANM from a conventional camera network:

**Clusters, not cameras.**
Logical monitoring locations decouple identity from hardware. Device replacement,
upgrade, or augmentation does not corrupt any vehicle history.

**Capability activation.**
Expensive computation (LPR, Re-ID, high-res capture) is invoked by the Orchestrator
when an investigation justifies it, not continuously. This is the primary resource
efficiency mechanism.

**Iterative investigation with backtracking.**
The system does not commit to the first plausible identity. It maintains competing
hypotheses, collects disambiguating evidence, and backtracks when evidence contradicts
the leading candidate. This matters in forensic contexts.

**Progressive graph-constrained search.**
Cross-cluster matching starts with cheap temporal feasibility filtering on the road
graph, eliminating most impossible candidates before any expensive similarity
computation runs.

**Replaceable reasoning components.**
The state estimator, evidence fusion method, and orchestration policy are all defined
as interfaces. Heuristics, Kalman filters, and learned models can be swapped without
changing any other component. See `02_REASONING_AND_ORCHESTRATION.md Section 7, 13, 11.4`.

---

## 9. What This Document Does Not Cover

- **How the Orchestrator makes decisions** → `02_REASONING_AND_ORCHESTRATION.md Section 11`
- **How hypotheses are managed and backtracked** → `02_REASONING_AND_ORCHESTRATION.md Section 9`
- **How evidence is fused** → `02_REASONING_AND_ORCHESTRATION.md Section 8`
- **Which fusion method or estimator is currently active** → `03_DEVELOPMENT_GUIDE.md`
- **Which OCR library is in use** → `03_DEVELOPMENT_GUIDE.md`
- **How to run the system** → `03_DEVELOPMENT_GUIDE.md`

