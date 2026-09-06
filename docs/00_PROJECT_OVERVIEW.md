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

<<<<<<< HEAD
=======
**Core Insight:** A node is a collection of heterogeneous devices (cameras, radars, microphones), not only a camera. Devices have independent identities and capabilities, while the node/cluster coordinates their operations.

The primary design principle is:

**Do as much computation as possible at the edge, transmit compact metadata rather than raw video, and perform city-wide reasoning centrally.**

A web-based platform serves as the visualization/client layer. The backend remains independent of the frontend so that the visualization system can later be replaced without redesigning the intelligence pipeline.

---

# 2. The Core Data Model

### 2.1 Cluster (Logical Edge Domain)

```text
Cluster
├── cluster_id (unique UUID, persistent)
├── location (latitude/longitude, may be approximate)
├── topology_reference (road segment, intersection ID)
├── state (IDLE, ACTIVE, EVENT_TRIGGERED, INVESTIGATION, RESOLVED)
└── devices[]
```

### 2.2 Device (Heterogeneous Sensing Unit)

```text
Device
├── device_id (unique UUID, persistent)
├── cluster_id (foreign key)
├── device_type (camera, radar, microphone, signal_controller, etc.)
├── capabilities (list of supported capabilities)
├── state (IDLE, ACTIVE, PROCESSING, OFFLINE)
└── metadata (hardware specs, calibration data)
```

### 2.3 Observation

```text
Observation
├── timestamp
├── cluster_id
├── device_id
├── local_track_id
├── bounding_box
├── centroid
├── class
└── confidence
```

### 2.4 Vehicle (Global Identity)

```text
Vehicle
├── vehicle_id (global, unique across all clusters)
├── first_seen
├── last_seen
├── plate_text
├── plate_confidence
└── appearance_embedding
```

---

# 3. The Execution Model: Capability Activation

**The architecture is driven by capability activation rather than a fixed pipeline.** Not every layer executes for every observation. Resources are activated only when needed.

```text
IDLE → ACTIVE → EVENT_TRIGGERED → INVESTIGATION → RESOLVED
```

### Normal Operation (IDLE → ACTIVE)

```text
Camera
  ↓
YOLO + ByteTrack (lightweight)
  ↓
Tracklet / event metadata
```

### Event Triggered (ACTIVE → EVENT_TRIGGERED)

When something important happens (violation detected, radar speed exceeded, etc.):

```text
Violation / Event
   ↓
Activate required capabilities:
  • LPR (license plate recognition)
  • Re-ID (appearance matching)
  • Evidence capture (high-resolution)
```

### Investigation (INVESTIGATION)

```text
Event
   ↓
Cross-cluster vehicle association
   ↓
Graph-constrained search (temporal feasibility)
   ↓
Appearance / plate matching
   ↓
Global vehicle identity
   ↓
Trajectory reconstruction
```

### Resolved (RESOLVED)

```text
Results stored
   ↓
Expensive capabilities released
   ↓
Return to IDLE state
```

This model ensures:
- Computational efficiency (no continuous heavy processing)
- Scalability (resources only used when needed)
- Explainability (clear state machine for debugging)

---

# 4. The Layered Architecture

```text
                    VAHANM
                       │
       ┌───────────────┼────────────────┐
       │               │                │
    Perception      Edge Control     Central Reasoning
       │               │                │
   YOLO/Tracker    capabilities       Graph
   OCR             resources          Association
   Re-ID           device state       Trajectory
       │               │                │
       └───────────────┼────────────────┘
                       │
                 Event-driven flow
                       │
                       ▼
                API / Persistence
                       │
                       ▼
                    Flutter
```

### Perception Layer

| Component | Technology | Purpose |
|-----------|------------|---------|
| Detection | Ultralytics YOLO | Vehicle/object detection |
| Tracking | ByteTrack | Local object tracking |
| OCR | Custom Deep-Learning ANPR | License plate recognition (primary ML deliverable) |
| Re-ID | Vehicle Re-ID model | Appearance-based matching |

### OCR/LPR as Primary ML Deliverable

The PS requires a **High-Precision OCR Module** powered by a deep-learning model exceeding 90% recognition accuracy for license plates in multi-lane traffic streams, working under challenging conditions:

- Varying lighting (day/night, glare, shadows)
- Poor weather (rain, fog, smoke)
- Angled shots (non-perpendicular camera angles)
- Motion blur (fast-moving vehicles)
- Dirty or damaged plates (stains, cracks, missing characters)
- Partial visibility (plate partially occluded)

The OCR pipeline is **evidence-aware and temporal**:

```text
Vehicle detected
     ↓
Collect candidate plate crops across frames
     ↓
Quality scoring (blur, exposure, occlusion)
     ↓
Best N crops selected
     ↓
Preprocessing (enhancement, rectification)
     ↓
OCR → plate hypothesis
     ↓
Temporal consensus across frames
     ↓
Plate hypothesis with evidence summary
```

When OCR confidence is insufficient, the system doesn't fail - it explicitly tracks:

```text
Plate Hypothesis
├── current_best: DL8CAX1234
├── evidence:
│   ├── 11 good crops
│   ├── 7 agreeing OCR results
│   ├── 2 partial matches
│   └── 1 contradictory result
└── status: HIGH CONFIDENCE

Or:

Plate Hypothesis
├── current_best: INDETERMINATE
├── evidence:
│   ├── 3 low-quality crops
│   ├── 1 partial match (60% confidence)
│   └── 0 agreeing results
└── status: INSUFFICIENT EVIDENCE
      ↓
  Request more evidence from:
  ├── Another camera/node
  ├── Higher-resolution capture
  └── Additional temporal samples
```

### Edge Control Layer

| Component | Purpose |
|-----------|---------|
| Device Manager | Manages camera, radar, microphone devices |
| Local Coordinator | Runs YOLO, ByteTrack, tracks local state |
| Capability Activation | Activates/deactivates expensive capabilities |
| Event Transport | Sends compact events to central backend |

### Central Reasoning Layer

| Component | Purpose |
|-----------|---------|
| Coordinator | Receives events, maintains global state |
| Graph Engine | Camera/road topology, reachability |
| Association | Cross-cluster vehicle matching |
| Trajectory | Reconstructs vehicle movement |

---

# 5. Implementation Plan for SIH 2026

## Phase A: Foundation (Week 1-2)

| Task | Priority |
|------|----------|
| PostgreSQL schema for clusters/devices/vehicles | High |
| FastAPI skeleton with basic endpoints | High |
| OpenCV video capture | High |
| YOLO detection integration | High |
| ByteTrack tracking integration | High |

## Phase B: Event-Driven (Week 2-3)

| Task | Priority |
|------|----------|
| Violation detection (line crossing) | High |
| Capability activation logic | High |
| LPR integration on violation | Medium |
| Plate temporal consensus | Medium |

## Phase C: Multi-Cluster (Week 3-4)

| Task | Priority |
|------|----------|
| TCP server for multiple clusters | High |
| Central coordinator | High |
| Web platform UI for visualization | High |
| Demo scripting | High |

## Phase D: Polish (Week 4+)

| Task | Priority |
|------|----------|
| Documentation | Medium |
| Performance optimization | Low |
| Docker containerization | Low |
| Advanced features (Re-ID, radar fusion) | Stretch |

---

# 6. Technology Stack

### Backend
- **Framework**: FastAPI (async, Python)
- **Database**: PostgreSQL (with UUID support)
- **Video Processing**: OpenCV, FFmpeg
- **ML Models**: Ultralytics YOLOv8, ByteTrack, EasyOCR
- **Communication**: TCP/WebSocket for edge→backend
- **Geometry**: Shapely

### Edge Devices
- **Runtime**: Python 3.10+
- **ML Models**: ONNX exports (for edge deployment)
- **Transport**: TCP/WebSocket
- **Device Abstraction**: Camera, radar, microphone interfaces

### Frontend
- **Framework**: React / Vue / Angular (web platform)
- **Maps**: Google Maps API / Leaflet
- **State Management**: Context API / Vuex / NgRx
- **Visualization**: Chart.js / D3.js for analytics, websockets for real-time updates
- **Video Streaming**: HTML5 Canvas / MediaPipe for browser-based inference

### Deployment
- **Containerization**: Docker (after MVP stability)
- **Edge**: Docker or direct Python deployment
- **Central**: Docker Compose or Kubernetes

---

# 7. The Architecture Differentiators

### What's Actually New About VAHANM?

The question "What's new?" is important because vehicle tracking systems already exist. VAHANM's novelty lies in **how** it organizes computation, not **what** it does.

### The Differentiators

**A. Adaptive Capability Activation**

Instead of every camera continuously running:
```
YOLO + OCR + ReID + everything
```

VAHANM uses capability activation:
```
cheap observation (YOLO + tracking)
      ↓
event detection
      ↓
activate required capabilities (LPR, Re-ID, high-res)
      ↓
investigation
      ↓
release everything unnecessary
```

This is one of the strongest architectural differentiators for SIH.

**B. Heterogeneous Node Architecture**

You aren't treating the city as:
```
Camera 1
Camera 2
Camera 3
```

You're treating it as:
```
Cluster
├── Camera
├── Radar
├── Signal controller
├── Microphone
└── other sensors
```

Each device has its own identity and capabilities, enabling multi-modal sensing.

**C. Progressive Search Instead of Brute Force**

Instead of:
```
vehicle
 ↓
compare against every camera
```

You do:
```
vehicle
 ↓
current cluster
 ↓
road topology
 ↓
reachable clusters
 ↓
time feasibility
 ↓
candidate observations
 ↓
appearance/identity matching
```

This makes the graph an optimization mechanism, not just visualization.

**D. Event-Driven Resource Management**

The system decides which computation should run right now:

Normal state:
- YOLO + ByteTrack only

Event state:
- + high-resolution capture
- + LPR
- + Re-ID
- + additional sensor interrogation

Investigation state:
- + cross-node search
- + graph traversal
- + trajectory reconstruction

Resolution:
- release everything unnecessary

This is essentially adaptive computation at the infrastructure level.

### The Real Value Proposition

VAHANM isn't just about:
>>>>>>> 4169d767e92d05f55744376ec5fec3b9ef9a0e73
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

