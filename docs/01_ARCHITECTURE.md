# VAHANM Architecture

## Core Insight

**A node is a collection of heterogeneous devices, not a camera. Devices have independent identities and capabilities, while the node/cluster coordinates their operation.**

The architecture is driven by **capability activation** rather than a fixed pipeline. Not every layer executes for every observation. Resources are activated only when needed.

---

## 1. The Data Model

### 1.1 Cluster (Logical Edge Domain)

Each cluster represents a logical edge domain that usually corresponds to a physical monitoring location but can be reassigned or moved without corrupting identity.

```python
Cluster:
  cluster_id: UUID (unique, persistent)
  location: (latitude, longitude) - may be approximate
  topology_reference: str (road segment ID, intersection ID, etc.)
  state: Enum[IDLE, ACTIVE, EVENT_TRIGGERED, INVESTIGATION, RESOLVED]
  created_at: datetime
  updated_at: datetime
```

### 1.2 Device (Heterogeneous Sensing Unit)

A device is a physical or virtual sensing unit attached to a cluster.

```python
Device:
  device_id: UUID (unique, persistent)
  cluster_id: UUID (foreign key)
  device_type: Enum[CAMERA, RADAR, MICROPHONE, SIGNAL_CONTROLLER, OTHER]
  capabilities: List[str] (e.g., ["detection", "tracking", "lpr", "reid"])
  state: Enum[IDLE, ACTIVE, PROCESSING, OFFLINE]
  metadata: dict (hardware specs, calibration data)
  created_at: datetime
  updated_at: datetime
```

### 1.3 Observation

An observation is a single detection event from a device.

```python
Observation:
  observation_id: UUID
  cluster_id: UUID
  device_id: UUID
  local_track_id: int (device-local track identifier)
  timestamp: datetime (source time from device)
  bbox: [x1, y1, x2, y2] (bounding box coordinates)
  centroid: (cx, cy)
  class: str (vehicle type: car, truck, bus, motorcycle, etc.)
  confidence: float (0.0 - 1.0) - detection confidence
  direction: [dx, dy] (movement direction vector)
  speed: float (optional, from radar or estimation)
  created_at: datetime
```

### 1.4 Vehicle (Global Identity)

A vehicle represents a unique vehicle identified across clusters.

```python
Vehicle:
  vehicle_id: UUID (global, unique across all clusters)
  plate_text: str (optional, from OCR)
  plate_confidence: float (optional)
  appearance_embedding: List[float] (optional, from Re-ID)
  first_seen: datetime
  last_seen: datetime
  created_at: datetime
```

### 1.5 Tracklet

A tracklet is a collection of observations belonging to the same local track.

```python
Tracklet:
  tracklet_id: UUID
  cluster_id: UUID
  device_id: UUID
  local_track_id: int
  first_observation_time: datetime
  last_observation_time: datetime
  observation_count: int
  estimated_speed: float (optional)
  direction: [dx, dy] (optional)
  metadata: dict
  created_at: datetime
```

### 1.6 Violation

A violation is a detected traffic infraction.

```python
Violation:
  violation_id: UUID
  vehicle_id: UUID (global)
  cluster_id: UUID
  device_id: UUID
  violation_type: Enum[REDC_LIGHT, SPEEDING, WRONG_WAY, PEDESTRIAN_CROSSING, OTHER]
  timestamp: datetime
  location: (latitude, longitude)
  severity: Enum[LOW, MEDIUM, HIGH, CRITICAL]
  evidence: dict ( URLs to captured frames, plate text, etc.)
  state: Enum[DETECTED, VERIFIED, ISSUED, RESOLVED]
  created_at: datetime
```

### 1.7 Vehicle Attributes (Structured Features)

Vehicles have multiple measurable attributes, some stable and some potentially changing:

```python
VehicleFeatures:
  # Relatively stable (good for identity)
  vehicle_type: str (car, truck, bus, SUV, etc.)
  make: str (Toyota, Hyundai, Maruti, etc.)
  model: str
  color: str (white, black, silver, etc.)
  physical_characteristics: dict (dents, scratches, roof racks, etc.)
  appearance_embedding: List[float]
  
  # Potentially unstable (search-space reduction only)
  driver_attributes: dict (apparent gender, age range, beard, glasses)
  clothing_attributes: dict (shirt color, hat, etc.)
  accessories: dict (phone visible, items on dash)
```

---

## 2. Confidence, Evidence, and Matching

### 2.1 Multi-Dimensional Confidence

Confidence should not be a single magical number. Instead, we track multiple evidence values:

| Evidence Type | Description | Use |
|---------------|-------------|-----|
| Detection confidence | YOLO detection certainty | Filter bad detections |
| Tracking confidence | ByteTrack track stability | Filter tracklets |
| OCR confidence | Plate recognition confidence | Support but not determine identity |
| Appearance similarity | Cosine similarity of embeddings | Primary identification signal |
| Temporal feasibility | Time distance between observations | Filter impossible matches |
| Route feasibility | Graph shortest path distance | Filter impossible routes |
| Direction consistency | Angle difference between tracks | Filter conflicting evidence |
| Sensor confidence | Radar speed, microphone confidence | Supporting evidence |

### 2.2 OCR/LPR - Primary ML Development Target

The PS requires a **High-Precision OCR Module** achieving >90% accuracy across diverse real-world conditions:

- Varying lighting (day/night, glare, shadows)
- Poor weather (rain, fog, smoke)
- Angled shots (non-perpendicular camera angles)
- Motion blur (fast-moving vehicles)
- Dirty or damaged plates (stains, cracks, missing characters)
- Partial visibility (plate partially occluded)

**The Challenge:** A single frame's OCR may be unreliable or fail entirely. We cannot assume every vehicle gets a perfect OCR result.

**The Solution - Evidence-Aware Temporal OCR:**

Instead of one frame → OCR → string, we use evidence aggregation:

```text
Multiple Frames (8 seconds)
    ↓
Collect all candidate plate crops
    ↓
Quality scoring (blur, exposure, occlusion, resolution)
    ↓
Select top N high-quality crops
    ↓
Preprocessing (enhancement, deblur, rectification)
    ↓
OCR on each crop
    ↓
Temporal consensus algorithm
    ↓
Final plate hypothesis with evidence summary
```

**Evidence-Aware OCR Output:**

```text
Plate Hypothesis: DL8CAX1234
Evidence:
  - 11 good crops with clear plate visibility
  - 7 OCR results agreeing on plate text
  - 2 partial matches (confidence 50-70%)
  - 1 contradictory result (likely noise)
Status: HIGH CONFIDENCE
```

Or when evidence is insufficient:

```text
Plate Hypothesis: INDETERMINATE
Evidence:
  - 3 low-quality crops
  - 1 partial match (60% confidence)
  - 0 agreeing results
Status: INSUFFICIENT EVIDENCE
     ↓
Request more evidence from:
  - Another camera/node
  - Higher-resolution capture
  - Additional temporal samples
```

**Security Boundary:**

The OCR output is **untrusted data**, never instructions:

```text
Camera
 ↓
OCR
 ↓
UNTRUSTED DATA
 ↓
validation / normalization
 ↓
application logic
```

This prevents SQL injection, prompt injection, and similar attacks. Plate text is data to be stored and queried, never executable code or LLM instructions.

### 2.3 Association Scoring

The association layer combines evidence into a matching score:

```python
association_score = (
    w1 * appearance_similarity +
    w2 * plate_similarity +
    w3 * temporal_feasibility +
    w4 * route_feasibility +
    w5 * direction_consistency
)

# Not a probability, but a matching score
# Can be normalized for interpretability
```

The weights are configurable based on operational requirements.

### 2.3 The "One Vehicle, Three Observations" Problem

When different cameras see the same vehicle differently:

- Camera A: misses plate
- Camera B: OCR incorrectly (e.g., "DL8CAX1234" vs "DL8CAX1284")
- Camera C: correct OCR (e.g., "DL8CAX1234")

These are **three observations** that may belong to **one global vehicle**.

The association layer determines this by combining evidence:

```text
Observations from multiple cameras
    ↓
Filter by temporal feasibility
    ↓
Filter by route feasibility (graph)
    ↓
Compare appearance embeddings
    ↓
Compare plate text (with fuzzy matching)
    ↓
Association score above threshold?
    ├─ Yes → same vehicle (global ID assigned)
    └─ No → separate vehicles OR retain as hypothesis
```

OCR provides supporting evidence, but it doesn't determine identity by itself.

---

## 3. Stable vs Unstable Attributes

### 3.1 Relatively Stable Attributes

These change rarely and are good for vehicle identification:

| Attribute | Typical Change Frequency | Use |
|-----------|--------------------------|-----|
| Vehicle type | Never | Broad filtering |
| Make/Model | Never (unless modified) | Good filtering |
| Color | Never (unless repainted) | Good filtering |
| Physical characteristics | Years (dents, modifications) | Fine-grained matching |
| Appearance embedding | Years | Primary matching signal |

### 3.2 Potentially Unstable Attributes

These change frequently and should only reduce search space:

| Attribute | Typical Change Frequency | Use |
|-----------|--------------------------|-----|
| Driver | Each trip | Temporary filtering |
| Driver clothing | Each trip | Temporary filtering |
| Accessories | Each trip | Temporary filtering |
| Items in vehicle | Each trip | Temporary filtering |
| Driver appearance | Each trip | Temporary filtering |

### 3.3 The Answer to "What if characteristics change?"

**Some features are identity features. Some are search-space reduction features.**

When the driver changes clothes:

- The driver attribute changes
- But the vehicle type, make, model, color, appearance embedding remain stable
- The system still recognizes it as the same vehicle

When a vehicle is repainted:

- The color attribute changes
- But the make, model, physical characteristics, and appearance embedding likely remain similar enough for matching

The system doesn't require perfect evidence from all sensors. It combines imperfect evidence probabilistically.

---

## 4. The Execution Model: Capability Activation

### 2.1 State Machine

```text
IDLE → ACTIVE → EVENT_TRIGGERED → INVESTIGATION → RESOLVED
```

### 2.2 State Transitions

#### IDLE
- Lightweight monitoring only
- Device is online but not actively processing
- Minimal resource usage

#### ACTIVE
- Normal operation mode
- YOLO detection running
- ByteTrack tracking running
- Local tracklets being formed
- Basic OCR (low-res, single frame) if plate visible
- No expensive operations (high-res OCR, Re-ID)

#### EVENT_TRIGGERED
- A violation or significant event has occurred
- Required capabilities are activated:
  - High-res plate capture
  - Evidence-aware OCR (multiple frames, consensus)
  - Re-ID (if cross-cluster matching needed)
  - Evidence capture (high-resolution frames)
- State entered via rule evaluation

#### INVESTIGATION
- Central coordinator performs cross-cluster search
- Graph traversal to find reachable clusters
- Appearance/plate matching against candidates
- Trajectory reconstruction

#### RESOLVED
- Investigation complete
- Results stored in database
- Expensive capabilities released
- Devices return to ACTIVE or IDLE state

### 2.3 Capability Activation Protocol

```python
# Event that triggers capability activation
{
    "event_type": "violation_detected",
    "cluster_id": "abc-123",
    "device_id": "cam-456",
    "local_track_id": 17,
    "violation_type": "red_light_violation",
    "timestamp": "2026-09-03T12:00:00Z"
}

# Response from central coordinator
{
    "activation_request": {
        "cluster_id": "abc-123",
        "required_capabilities": ["lpr", "reid", "evidence_capture"],
        "duration_seconds": 30
    }
}
```

---

## 3. The Layered Architecture

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

### 3.1 Perception Layer

| Component | Technology | Purpose | Output |
|-----------|------------|---------|--------|
| Detection | Ultralytics YOLOv8 | Vehicle/object detection | Bounding boxes, classes, confidence |
| Tracking | ByteTrack | Local object tracking | Track IDs per device |
| OCR | Custom Deep-Learning ANPR | License plate recognition (primary ML deliverable) |
| Re-ID | Vehicle Re-ID model | Appearance-based matching |

#### YOLO Detection Configuration

The YOLO detector is configured via `backend/config/detection.yaml`:

```yaml
model_path: "yolov8n.pt"           # Model file (n, s, m, l, x)
conf_threshold: 0.25               # Minimum confidence (0.0 - 1.0)
iou_threshold: 0.45                # NMS threshold (0.0 - 1.0)
device: "cuda"                     # "cuda" for GPU, "cpu" for CPU
imgsz: 640                         # Image size before inference
half_precision: true               # FP16 inference for speed
preprocess:                        # Preprocessing options
  resize: true
  target_size: 640
  normalize: true
```

**Usage:**
```python
from backend.intelligence.perception.detection import create_detector

detector = create_detector()  # Uses config/detection.yaml
results = detector.detect(frame, return_type='boxes')
```

See `docs/03_DEVELOPMENT_GUIDE.md` for detailed YOLO setup and usage instructions.

#### ByteTrack Tracking Configuration

```yaml
tracker_type: "bytetrack"          # "bytetrack" or "botsort"
track_buffer: 30                  # Number of frames to track
match_threshold: 0.8              # Matching threshold
```

See `backend/intelligence/tracking/tracker.py` for implementation.

#### OCR/LPR Configuration

```yaml
ocr_engine: "easyocr"              # "easyocr" or "tesseract"
ocr_model: "latin"                 # Language model
confidence_threshold: 0.7         # Minimum OCR confidence
evidence_consensus: true          # Use multiple frames for consensus
min_evidence_frames: 3            # Minimum frames for temporal consensus
```

See `backend/intelligence/perception/ocr/ocr_engine.py` for implementation.

### 3.2 Frontend Layer

| Component | Technology | Purpose |
|-----------|------------|---------|
| Web Platform | React/Vue/Angular | Visualization and user interface |
| Maps | Google Maps API / Leaflet | Geographic visualization |
| Charts | Chart.js / D3.js | Traffic analytics and trends |
| Real-time | WebSocket | Live data streaming from backend |

### 3.3 Edge Control Layer

| Component | Purpose |
|-----------|---------|
| Device Manager | Manages camera, radar, microphone devices |
| Local Coordinator | Runs YOLO, ByteTrack, tracks local state |
| Capability Activation | Activates/deactivates expensive capabilities based on events |
| Event Transport | Sends compact events to central backend via TCP/WebSocket |

### 3.3 Central Reasoning Layer

| Component | Purpose |
|-----------|---------|
| Coordinator | Receives events, maintains global vehicle state |
| Graph Engine | Camera/road topology, reachability, shortest paths |
| Association | Cross-cluster vehicle matching (plate + appearance + temporal) |
| Trajectory | Reconstructs vehicle movement across clusters |
| State Machine | Manages investigation state (IDLE → ACTIVE → EVENT → RESOLVED) |

---

## 4. The Data Flow

### 4.1 Normal Operation Flow

```text
Edge Device (Camera)
    ↓
OpenCV / FFmpeg (video decoding)
    ↓
YOLO Detection
    ↓
ByteTrack Tracking (local track ID)
    ↓
Observation → Tracklet
    ↓
Compact event (no video)
    ↓
TCP / WebSocket
    ↓
Central Backend
    ↓
PostgreSQL (observations, tracklets)
```

### 4.2 Violation Detection Flow

```text
Tracklet
    ↓
Geometry / State Machine
    ↓
Violation Detected
    ↓
Central Coordinator
    ↓
Activate Capabilities:
  • LPR on vehicle crop
  • Re-ID embedding extraction
  • High-res evidence capture
    ↓
Vehicle Identification
    ↓
Global Vehicle ID Assigned
    ↓
Violation Event Stored
```

### 4.3 Cross-Cluster Association Flow

```text
Violation at Cluster A
    ↓
Vehicle ID: V1
    ↓
Central Coordinator
    ↓
Graph Search:
  • Which clusters are reachable from A?
  • What's the temporal feasibility?
    ↓
Candidate Clusters: [B, C, D]
    ↓
Matching (parallel):
  • Plate similarity
  • Appearance embedding cosine similarity
    ↓
Confirmed Match at Cluster B
    ↓
Global Trajectory: A → B
    ↓
Investigation Resolved
```

---

## 7. The Architecture Differentiators

### 7.1 What's Actually New About VAHANM?

The question "What's new?" is important because vehicle tracking systems already exist. VAHANM's novelty lies in **how** it organizes computation, not **what** it does.

### 7.2 The Differentiators

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

### 7.3 The Real Value Proposition

VAHANM isn't just about:
> "Where is the vehicle?"

It's about:
> "Given an event, how do we spend the minimum amount of computational and sensing resources necessary to establish where the vehicle went?"

### 7.4 The "Who Is This For?" Answer

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

## 9. Implementation Strategy: HMM vs Heuristics

### 8.1 Current Design Philosophy

We're currently designing the association layer as **graph-constrained heuristic reasoning**.

This means:
- Use cheap geometric/temporal constraints first
- Then expensive appearance/attribute matching
- Use graph reachability to prune candidates

### 8.2 Where HMM Fits In

An HMM or another learned temporal model is an **option we'll evaluate** if:
- The simpler heuristic approach isn't sufficient
- We have enough training data for temporal modeling
- The computational cost is justified

### 8.3 The Recommendation for SIH

For SIH 2026, I recommend:

1. **Demonstrate the architecture** with heuristics
2. **Show capability activation** working end-to-end
3. **Demonstrate progressive search** reducing candidates
4. **Build a robust OCR model** that exceeds 90% accuracy on real-world conditions
5. **Show evidence aggregation** handling imperfect observations

### 8.4 YOLO Setup and Usage

**Installation:**
```bash
cd backend
pip install ultralytics
```

**Quick Test:**
```bash
python -c "from ultralytics import YOLO; model = YOLO('yolov8n.pt'); results = model('bus.jpg'); results.show()"
```

**Using the YOLO Detector:**
```python
from backend.intelligence.perception.detection import create_detector
import cv2

# Create detector (uses config/detection.yaml)
detector = create_detector()

# Detect in an image
frame = cv2.imread("test_image.jpg")
results = detector.detect(frame, return_type='boxes')
print(f"Found {len(results)} objects")

# Detect in video
results_per_frame = detector.detect_video("input.mp4", output_path="output.mp4")
```

**Model Size Selection:**

| Model | Size | Speed | Accuracy | Use Case |
|-------|------|-------|----------|----------|
| yolov8n.pt | 6 MB | Fastest | Lower | Real-time edge |
| yolov8s.pt | 22 MB | Fast | Good | General purpose |
| yolov8m.pt | 52 MB | Medium | Better | Accuracy critical |
| yolov8l.pt | 98 MB | Slow | Better still | Offline processing |
| yolov8x.pt | 171 MB | Slowest | Best | Maximum accuracy |

For VAHANM, start with `yolov8n.pt` for speed, upgrade if accuracy is insufficient.

**Configuring Detection:**
```yaml
# backend/config/detection.yaml
model_path: "yolov8n.pt"
conf_threshold: 0.25
iou_threshold: 0.45
device: "cuda"  # or "cpu" for CPU-only
imgsz: 640
classes: [2, 3, 5, 7]  # Only detect cars, motorcycles, buses, trucks
```

See `docs/03_DEVELOPMENT_GUIDE.md` for complete YOLO documentation.

---

## 10. Implementation Priorities for SIH 2026

### Phase 1: Foundation (Week 1-2)

| Task | Priority |
|------|----------|
| PostgreSQL schema for clusters/devices/vehicles | High |
| FastAPI skeleton with basic endpoints | High |
| OpenCV video capture | High |
| YOLO detection integration | High |
| ByteTrack tracking integration | High |

### Phase 2: Event-Driven (Week 2-3)

| Task | Priority |
|------|----------|
| Violation detection (line crossing) | High |
| Capability activation logic | High |
| LPR integration on violation | Medium |
| Plate temporal consensus | Medium |

### Phase 3: Multi-Cluster (Week 3-4)

| Task | Priority |
|------|----------|
| TCP server for multiple clusters | High |
| Central coordinator | High |
| Web platform UI for visualization | High |
| Demo scripting | High |

### Phase 4: Polish (Week 4+)

| Task | Priority |
|------|----------|
| Documentation | Medium |
| Performance optimization | Low |
| Docker containerization | Low |
| Advanced features (Re-ID, radar fusion) | Stretch |

---

## 7. Technology Stack

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
- **Framework**: Flutter
- **Maps**: Google Maps API
- **State Management**: Provider / Riverpod
- **Video**: camera package + custom TCP client

### Deployment
- **Containerization**: Docker (after MVP stability)
- **Edge**: Docker or direct Python deployment
- **Central**: Docker Compose or Kubernetes

---

## 7. Current Architecture Statement

> **VAHANM is an edge-first, event-driven, cluster-based vehicle monitoring system where devices have independent identities, and capabilities are activated dynamically based on violations rather than running continuously.**

The key distinction from traditional architectures:

| Traditional | VAHANM |
|-------------|--------|
| Cameras = Nodes | Clusters = Nodes (containers of devices) |
| All layers always active | Capabilities activated on demand |
| Centralized processing | Edge-first with central coordination |
| Camera ID = Identity | Device/Cluster UUID = Identity |
| Fixed topology | Logical topology (reassignable) |
