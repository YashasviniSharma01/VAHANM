# VAHANM — Project Overview

## Vehicle Analytics & Heuristics Node Monitoring

### 1. Project Purpose

**VAHANM (Vehicle Analytics & Heuristics Node Monitoring)** is a distributed, edge-first vehicle monitoring and traffic analytics system designed for Bharat Electronics Limited's challenge:

> City-Wide AI Engine for Multi-Camera ANPR Trajectory Tracking and Urban Traffic Analytics.

The system processes geographically distributed traffic-camera streams, detects and tracks vehicles locally, identifies traffic violations, performs license-plate recognition, associates vehicles across different sensors, and reconstructs their movement through a city-wide road graph.

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
> "Where is the vehicle?"

It's about:
> "Given an event, how do we spend the minimum amount of computational and sensing resources necessary to establish where the vehicle went?"

### The "Who Is This For?" Answer

The primary users are:
1. **Traffic Police** - for violation detection and enforcement
2. **Law Enforcement** - for finding vehicles involved in crimes

The plate recognition case is easy - once the plate is identified, existing enforcement workflows apply.

The interesting case is partial observation:

```
Camera A: no plate
Camera B: wrong OCR
Camera C: imperfect OCR
         ↓
System: "These observations are likely the same vehicle"
         ↓
System: "Vehicle is at Cluster X, went to Cluster Y"
         ↓
Provide evidence/trajectory to authorities
```

This is where the architecture really matters.

---

# 8. Implementation Strategy: HMM vs Heuristics

### Current Design Philosophy

We're currently designing the association layer as **graph-constrained heuristic reasoning**.

This means:
- Use cheap geometric/temporal constraints first
- Then expensive appearance/attribute matching
- Use graph reachability to prune candidates

### Where HMM Fits In

An HMM or another learned temporal model is an **option we'll evaluate** if:
- The simpler heuristic approach isn't sufficient
- We have enough training data for temporal modeling
- The computational cost is justified

### The Recommendation for SIH

For SIH 2026, I recommend:

1. **Demonstrate the architecture** with heuristics
2. **Show capability activation** working end-to-end
3. **Demonstrate progressive search** reducing candidates

If you have time and want to experiment with HMM:

- Keep it modular (not baked into core architecture)
- Train on synthetic data first
- Compare against heuristic baseline

But don't commit to HMM in your documentation until you've tested both approaches.

---

# 9. Current Architecture Statement

> **VAHANM is an edge-first, event-driven, cluster-based vehicle monitoring system where devices have independent identities, and capabilities are activated dynamically based on violations rather than running continuously.**

The key distinction from traditional architectures:

| Traditional | VAHANM |
|-------------|--------|
| Cameras = Nodes | Clusters = Nodes (containers of devices) |
| All layers always active | Capabilities activated on demand |
| Centralized processing | Edge-first with central coordination |
| Camera ID = Identity | Device/Cluster UUID = Identity |
| Fixed topology | Logical topology (reassignable) |
