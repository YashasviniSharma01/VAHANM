# VAHANM Development Guide

This document describes the **current implementation state**: what code exists, what
it does, how to run it, and what comes next.

Architecture and reasoning design live in separate documents. When a section says
"see `02_REASONING_AND_ORCHESTRATION.md Section N`" that is the authoritative design
reference. This document records the implementation decisions made against those
interfaces.

---

## Repository Layout

```
VAHANM/
├── backend/
│   ├── .venv/                          ↝ Python 3.13 virtual environment
│   ├── config/
│   │   └── detection.yaml              ↝ YOLODetector configuration
│   ├── intelligence/
│   │   ├── perception/
│   │   │   └── detection/
│   │   │       ├── edge_tracker.py     ↝ Phase 1 entry point
│   │   │       ├── yolo_detector.py    ↝ YOLODetector wrapper (detection-only)
│   │   │       └── __init__.py
│   │   ├── perception/
│   │   │   ├── observation_manager.py  ↝ Phase 2
│   │   │   ├── evidence_capture.py     ↝ Phase 4
│   │   │   └── lpr/                    ↝ Phase 5
│   │   ├── coordinator/                ↝ Phase 6, 8
│   │   ├── graph/                      ↝ Phase 9
│   │   ├── rules/                      ↝ Phase 3
│   │   │   └── state_machine_rules.py
│   │   └── tracking/                   ↝ Phase 2+
│   ├── api/                            ↝ Phase 7
│   ├── storage/                        ↝ Phase 7
│   ├── output/                         ↝ observations.json written here at runtime
│   ├── main.py                         ↝ Phase 7 app entry point
│   ├── requirements.txt
│   └── yolo26n.pt                      ↝ downloaded on first run, now cached
└── docs/
```

See `docs/PROJECT_STATUS.md` for the current build/code status of each directory.

---

## Environment Setup

The virtual environment uses **Python 3.13** and lives inside `backend/`.

```powershell
# Windows PowerShell — run once
cd d:\SIH\VAHANM\backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version          # must print Python 3.13.x

pip install ultralytics opencv-python pyyaml
```

```bash
# Linux / macOS — run once
cd /path/to/VAHANM/backend
python3.13 -m venv .venv
source .venv/bin/activate
pip install ultralytics opencv-python pyyaml
```

**Verify the install:**

```powershell
python -c "from ultralytics import YOLO; print('OK')"
python -c "import cv2; print(cv2.__version__)"
```

---

## `requirements.txt`

```
# ── Phase 1–2 (active) ───────────────────────────────────────────────────────
ultralytics>=8.2.0        # YOLO26 detection + built-in ByteTrack
opencv-python>=4.8.0      # video capture and frame I/O
pyyaml>=6.0               # config file loading

# ── Phase 3 (violation geometry) — uncomment when starting Phase 3 ───────────
# shapely>=2.0.0

# ── Phase 7 (API + transport) — uncomment when starting Phase 7 ──────────────
# fastapi>=0.100.0
# uvicorn>=0.23.0

# ── Phase 7 (database) — uncomment when starting Phase 7 ─────────────────────
# psycopg2-binary>=2.9.0

# asyncio is part of the Python standard library — do NOT add it here.
```

Uncomment each block only when the corresponding phase becomes active. This keeps
`pip install -r requirements.txt` fast and the environment clean.

---

## Phase Status

| # | Phase | Primary file(s) |
| --- | ------- | ----------------- |
| 1 | First Working Tracker | `intelligence/perception/detection/edge_tracker.py` |
| 2 | Observation Manager | `intelligence/perception/observation_manager.py` |
| 3 | Violation Detection | `intelligence/rules/` |
| 4 | Evidence Capture | `intelligence/perception/evidence_capture.py` |
| 5 | LPR Capability | `intelligence/perception/lpr/` |
| 6 | Hypothesis Management | `intelligence/coordinator/` |
| 7 | FastAPI Transport | `api/`, `main.py` |
| 8 | Orchestrator | `intelligence/coordinator/orchestrator.py` |
| 9 | Multi-Cluster Association | `intelligence/graph/` |
| 10 | Web Platform | `web/` |

Current build status for each phase: see `docs/PROJECT_STATUS.md`.

---

## Phase 1 — First Working Tracker ✅

**File:** `backend/intelligence/perception/detection/edge_tracker.py`

**What it proves:** `video → YOLO26 detection → ByteTrack tracking → observation JSON`

**Model on disk:** `backend/yolo26n.pt` (downloaded automatically on first run,
now cached)

### Running

```powershell
cd d:\SIH\VAHANM\backend
.\.venv\Scripts\Activate.ps1

# Webcam (index 0)
python intelligence/perception/detection/edge_tracker.py --source 0

# Video file
python intelligence/perception/detection/edge_tracker.py --source traffic.mp4

# Vehicle classes only (car=2, motorcycle=3, bus=5, truck=7), tighter confidence
python intelligence/perception/detection/edge_tracker.py `
    --source traffic.mp4 `
    --classes 2 3 5 7 `
    --conf 0.4

# Headless — no display window (servers, scripts)
python intelligence/perception/detection/edge_tracker.py `
    --source traffic.mp4 `
    --no-show

# Cap frames (useful for quick tests)
python intelligence/perception/detection/edge_tracker.py `
    --source 0 `
    --max-frames 300
```

**CLI flags:**

| Flag | Default | Description |
| ------ | --------- | ------------- |
| `--source` | required | File path, URL, or camera index (`0`) |
| `--output-dir` | `output` | Directory for `observations.json` |
| `--classes` | None (all) | Space-separated COCO class IDs |
| `--conf` | `0.35` | Detection confidence threshold |
| `--max-frames` | None | Stop after N frames |
| `--no-save` | off | Skip writing `observations.json` |
| `--no-show` | off | Skip the OpenCV display window |

### Output — `output/observations.json`

The exact schema produced by the current code:

```json
{
  "metadata": {
    "source": "edge_tracker",
    "version": "1.0.0",
    "generated_at": "2026-09-03T14:22:01.123456",
    "total_observations": 847
  },
  "observations": [
    {
      "frame": 1,
      "timestamp": "2026-09-03T14:22:01.130000",
      "track_id": 3,
      "class_id": 2,
      "class_name": "car",
      "confidence": 0.8712,
      "bbox": {
        "x1": 142.3,
        "y1": 210.1,
        "x2": 389.7,
        "y2": 401.5
      },
      "centroid": {
        "x": 266.0,
        "y": 305.8
      },
      "dimensions": {
        "width": 247.4,
        "height": 191.4
      }
    }
  ]
}
```

**Important:** `timestamp` is wall-clock time at the moment the frame is processed,
not a video timestamp. For live cameras this is close enough. For recorded video being
replayed faster or slower than real-time, the timestamp will not match the original
capture time. This is a known limitation to address in Phase 2 when the observation
schema is formalised.

**Important:** `track_id` is a device-local ByteTrack integer. It is not a global
vehicle identity. Two cameras running simultaneously will both produce a `track_id=3`
that refer to different vehicles.

### EdgeTracker class API

```python
from intelligence.perception.detection.edge_tracker import EdgeTracker

tracker = EdgeTracker(
    model_path="yolo26n.pt",   # default
    tracker_config="bytetrack.yaml",
    classes=[2, 3, 5, 7],
    conf=0.35,
    iou=0.7,
    imgsz=640,
)

observations = tracker.track(
    source="traffic.mp4",
    output_dir="output",
    max_frames=None,
    save_output=True,
    show=True,
)

# Inspect results
unique_ids = tracker.get_unique_tracks()          # List[int]
car_obs    = tracker.get_observations_by_track(3) # List[dict]
tracker.reset()                                   # clear state for reuse
```

### Underlying Ultralytics API

`EdgeTracker` is a thin wrapper. The core call is:

```python
for result in model.track(
    source=source,
    tracker="bytetrack.yaml",   # built-in — do NOT install a separate byte_track package
    classes=self.classes,
    conf=self.conf,
    iou=self.iou,
    imgsz=self.imgsz,
    stream=True,
    verbose=False,
    show=show,
):
    if result.boxes.id is None:   # no tracks yet — always guard this
        continue

    for box, track_id in zip(result.boxes, result.boxes.id):
        tid   = int(track_id.item())
        cls   = int(box.cls.item())
        conf  = float(box.conf.item())
        x1,y1,x2,y2 = box.xyxy[0].tolist()
```

`result.boxes.id` returns a `torch.Tensor` or `None`. Call `.item()` to extract a
Python scalar. Do not compare the tensor directly with `== None` — use `is None`.

### COCO vehicle class IDs

| ID | Class | Notes |
| ---- | ------- | ------- |
| 2 | car | sedans, hatchbacks, SUVs |
| 3 | motorcycle | includes scooters |
| 5 | bus | includes minibuses |
| 7 | truck | includes lorries, trailers |

Pass `--classes 2 3 5 7` to ignore pedestrians, bicycles, and all other COCO classes.

### Performance observed (tested)

| Source | Hardware | FPS |
|--------|----------|-----|
| 640×480 webcam, yolo26n | CPU (Intel i5, no GPU) | ~22–24 FPS after warmup |

GPU will be significantly faster. First ~50 frames are slower while ByteTrack
initialises track state — this is normal.

---

## `yolo_detector.py` — Secondary Component

`backend/intelligence/perception/detection/yolo_detector.py` is a feature-rich
wrapper around Ultralytics that predates `edge_tracker.py`.

**Current state:** it references `yolo26n.pt` internally (the `model_path`
default in the class). `config/detection.yaml` correctly points to `yolo26n.pt`.
`YOLODetector` via `create_detector()` will use `yolo26n.pt` by default, or you can
pass a config that specifies a different variant.

**When to use which:**

| Component | Use for |
|-----------|---------|
| `EdgeTracker` (`edge_tracker.py`) | All new tracking work — Phase 1 onwards |
| `YOLODetector` (`yolo_detector.py`) | Detection-only (no tracking), or if you need per-frame `detect()` calls |

`YOLODetector` exposes `detect(frame)`, `detect_video()`, `_extract_crops()` — useful
if Phase 4 (evidence capture) needs to crop individual vehicle regions without
running ByteTrack.

**Known issue in `yolo_detector.py`:** `half_precision: true` is the hardcoded
default in the class (`__init__`), which will error on CPU. Override it with
`config={"half_precision": False}` when not on a CUDA GPU, or use `detection.yaml`
which now defaults to `false`.

---

## Phase 2 — Observation Manager ❳

**What it proves:** observations are filtered before storage; a dense scene does not
produce hundreds of redundant records per second.

**Design reference:** `02_REASONING_AND_ORCHESTRATION.md Section 2`

**File to create:** `backend/intelligence/perception/observation_manager.py`

The Observation Manager wraps the per-frame output of `EdgeTracker` and applies
per-track quality scoring before an observation is retained or escalated.

**Interface:**

```python
from dataclasses import dataclass
from enum import Enum

class Disposition(Enum):
    DISCARD  = "discard"
    RETAIN   = "retain"
    ESCALATE = "escalate"

@dataclass
class ObservationManager:
    min_detection_conf:  float = 0.35
    min_track_age:       int   = 3      # frames before track is considered stable
    min_motion_px:       float = 5.0    # centroid must move this far since last retain
    min_plate_vis:       float = 0.3    # plate_visibility threshold to trigger ESCALATE

    def evaluate(self, observation: dict, track_window: dict) -> Disposition:
        ...
```

**TrackWindow state** (maintained in memory per track_id, not persisted):

```python
track_window = {
    "local_track_id":          int,
    "age_frames":              int,
    "last_retained_centroid":  (float, float) | None,
    "last_retained_timestamp": str | None,
    "retained_count":          int,
    "escalated_count":         int,
}
```

**Start simple:** implement threshold rules on `detection_conf`, `age_frames`, and
centroid displacement. Add `blur_score` (Laplacian variance of the cropped bbox
region) once the basic filter is working.

**Integration point:** call `ObservationManager.evaluate()` inside the
`EdgeTracker.track()` loop, replacing the unconditional `self.observations.append()`.

---

## Phase 3 — Violation Detection ❳

**What it proves:** a rule fires correctly against world state.

**Design reference:** `02_REASONING_AND_ORCHESTRATION.md Section 6`

**Dependency to add:** `shapely>=2.0.0` (uncomment in `requirements.txt`)

**Directory:** `backend/intelligence/rules/`

**Start with `LineCrossingRule`** — the simplest geometrically verifiable rule, and
the most common traffic violation trigger:

```python
# backend/intelligence/rules/line_crossing.py
from shapely.geometry import LineString, Point
from dataclasses import dataclass

@dataclass
class RuleResult:
    triggered:      bool
    violation_type: str
    confidence:     float
    explanation:    str

class LineCrossingRule:
    rule_id = "line_crossing_v1"

    def __init__(self, forbidden_line: list[tuple[float, float]], direction: str = "any"):
        self.line = LineString(forbidden_line)
        self.direction = direction   # "any" | "left_to_right" | "right_to_left"

    def evaluate(self, prev_centroid, curr_centroid, track_conf: float) -> RuleResult:
        segment = LineString([prev_centroid, curr_centroid])
        triggered = segment.crosses(self.line)
        return RuleResult(
            triggered=triggered,
            violation_type="LINE_CROSSING",
            confidence=track_conf if triggered else 0.0,
            explanation="centroid path crossed forbidden line" if triggered else "",
        )
```

**Integration:** `edge_tracker.py` already stores `centroid` per frame and `track_id`
per observation — the consecutive centroids needed by `LineCrossingRule` are already
in `observations`. Phase 3 reads consecutive observations for the same `track_id` and
runs `evaluate()` on each consecutive pair.

**Do not** put OCR, database writes, or capability activation inside a rule. A rule
returns a `RuleResult`. The Orchestrator (Phase 8) acts on it.

---

## Phase 4 — Evidence Capture ❳

**What it proves:** a violation produces an immutable, storable evidence record.

**Design reference:** `02_REASONING_AND_ORCHESTRATION.md Section 3`

Evidence records are frozen after creation. A second capability invocation creates a
new record; it does not overwrite the first.

```python
# backend/intelligence/perception/evidence_capture.py
from dataclasses import dataclass, field
from typing import Tuple
import uuid

@dataclass(frozen=True)
class Evidence:
    evidence_id:          str
    investigation_id:     str
    goal:                 str          # "VIOLATION_FRAME" | "PLATE_OCR" | ...
    observation_ids:      tuple        # immutable; subset selected for this evidence
    produced_by:          str          # capability id, e.g. "evidence_capture_v1"
    timestamp_produced:   str          # ISO8601
    result:               dict = field(default_factory=dict)
    # result keys for VIOLATION_FRAME:
    #   frame_path: str   (relative path to saved .jpg)
    #   bbox: dict        (x1,y1,x2,y2 of the vehicle in the frame)
    #   track_id: int
    #   violation_type: str
```

**Frame selection:** from the N frames surrounding the violation timestamp, pick the
one with the highest `bbox.width * bbox.height` (largest = closest/clearest) where
`detection_conf >= 0.5`. Save it as a JPEG to `output/evidence/`.

`YOLODetector._extract_crops()` already implements the crop-with-padding logic and
can be reused here.

---

## Phase 5 — LPR Capability ❳

**What it proves:** OCR runs on demand, not on every frame.

**Design reference:** `02_REASONING_AND_ORCHESTRATION.md Section 5, 8.3`

**OCR engine:** not yet selected. The interface below must be satisfied regardless of
engine. Do not import a specific OCR library at the module level before it is chosen.

```python
# backend/intelligence/perception/lpr/base.py

class LPRCapability:
    capability_id = "lpr_v1"

    def run(self, crop_paths: list[str]) -> "PlateHypothesis":
        """
        Run OCR on a list of pre-selected plate crops.
        Returns a PlateHypothesis. Does not select crops — that is the
        EvidenceSelector's job.
        """
        raise NotImplementedError

@dataclass
class PlateHypothesis:
    best_text:             str            # e.g. "DL8CAX1234" or "" if indeterminate
    character_confidences: list[float]    # one per character in best_text
    supporting_reads:      int            # OCR results agreeing on best_text
    contradictions:        int            # conflicting reads
    sufficiency:           str            # NONE | LOW | MEDIUM | HIGH | CONFIRMED
```

**Engine candidates for evaluation (not yet decided):**

| Engine | Strengths | Weaknesses |
| -------- | ----------- | ------------ |
| EasyOCR | simple API, good multilingual | slow on CPU |
| PaddleOCR | fast, accurate | large dependency footprint |
| Tesseract | mature, well-documented | poor on angled/partial plates |
| Custom fine-tuned | best accuracy on Indian plates | requires labelled training data |

Benchmark on real plate crops before committing. The interface above insulates
everything else from the choice.

---

## Phase 6 — Hypothesis Management ❳

**What it proves:** the system maintains competing identity candidates and backtracks
when evidence contradicts the leading hypothesis.

**Design reference:** `02_REASONING_AND_ORCHESTRATION.md Section 4, 9`

`VehicleHypothesis` and `IdentityHypothesis` live in memory in the central tier until
an investigation commits. Start with **likelihood scoring** as the fusion method:

```python
# backend/intelligence/coordinator/evidence_fusion.py

WEIGHTS = {
    "plate_similarity":      0.40,
    "appearance_similarity": 0.35,
    "temporal_feasibility":  0.15,
    "direction_consistency": 0.10,
}

def likelihood_score(evidence_set: list, hypothesis_id: str) -> float:
    return sum(
        WEIGHTS.get(e["goal"], 0.0) * e["result"].get("confidence", 0.0)
        for e in evidence_set
        if e["goal"] in WEIGHTS
    )
```

The weights are configurable. The fusion interface is fixed — a Bayesian or learned
method can replace this without changing any caller.

---

## Phase 7 — FastAPI Transport ❳

**What it proves:** edge observations reach the central system reliably.

**Dependencies to add:** `fastapi>=0.100.0`, `uvicorn>=0.23.0`, `psycopg2-binary>=2.9.0`

**Important:** use FastAPI's **native WebSocket**, not Socket.IO. They are different
protocols. Do not mix them.

```python
# backend/api/websocket.py
from fastapi import FastAPI, WebSocket

app = FastAPI()

@app.websocket("/ws/edge/{cluster_id}")
async def edge_feed(websocket: WebSocket, cluster_id: str):
    await websocket.accept()
    while True:
        data = await websocket.receive_json()
        # compact observation event — no video bytes
        await ingest_observation(cluster_id, data)
```

`main.py` is currently empty — it becomes the FastAPI app entry point in Phase 7.

---

## Phase 8 — Orchestrator ❳

**Design reference:** `02_REASONING_AND_ORCHESTRATION.md Section 11`

The Orchestrator runs as an async coroutine in the central tier. It is the only
component that invokes capabilities. Rules fire; the Orchestrator decides what to do
with a fired rule.

**Directory:** `backend/intelligence/coordinator/`

---

## Phase 9 — Multi-Cluster Association ❳

**Design reference:** `02_REASONING_AND_ORCHESTRATION.md Section 13–14`

**Dependencies to add:** `networkx>=3.0`

The road graph stores clusters as nodes, road segments as directed edges with
`min_travel_time_sec` and `max_travel_time_sec` attributes. Temporal feasibility
filtering runs cheaply on the graph before any appearance comparison.

**Directory:** `backend/intelligence/graph/`

---

## Phase 10 — Web Platform ❳

**Framework decision:** choose one of React, Vue, or Angular when Phase 10 begins.
Do not create scaffolding before Phase 7 (the WebSocket feed) is stable.

**Maps:** Leaflet (no API key) or Mapbox GL JS (key required). Decide at Phase 10
start; do not import both.

**Minimum viable dashboard:**

1. Live map with vehicle markers (WebSocket feed)
2. Violation log table
3. Investigation detail view (hypothesis scores, evidence, decision history)

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'ultralytics'`

The venv is not activated, or packages were installed to the wrong Python.

```powershell
cd d:\SIH\VAHANM\backend
.\.venv\Scripts\Activate.ps1
pip show ultralytics    # should show path inside .venv
```

### Packages install to global Python, not venv

```powershell
pip --version
# must show a path inside d:\SIH\VAHANM\backend\.venv\
# if it shows D:\softwares\python\ the venv is not active
```

### `Activate.ps1 cannot be loaded — execution policy`

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### `result.boxes.id is None` on every frame

Normal for the first few frames while ByteTrack initialises. If it persists:

- Confirm detections are actually happening: check `len(result.boxes) > 0`
- Lower `--conf` to get more detections for ByteTrack to latch onto
- ByteTrack needs at least 2–3 consistent detections to assign an ID

### `results.show()` crashes or errors

`model.predict()` returns a **list**. Call `results[0].show()`, not `results.show()`.
On headless servers, use `save=True` instead:

```python
results = model.predict(source="image.jpg", save=True)
# output in runs/detect/predict/image.jpg
```

Or explicitly: `result.save(filename="output.jpg")`.

### `half_precision` error on CPU

```
RuntimeError: "slow_conv2d_cpu" not implemented for 'Half'
```

`yolo_detector.py` defaults `half_precision=True` internally. Override:

```python
detector = YOLODetector(config={"half_precision": False})
```

Or use `config/detection.yaml` which now correctly sets `half_precision: false`.

### `lap` package auto-installed by Ultralytics on first run

On first tracking run, Ultralytics detects that `lap` (Linear Assignment Problem
solver, needed by ByteTrack) is missing and auto-installs it. This is expected. You
will see:

```
requirements: Ultralytics requirement ['lap>=0.5.12'] not found, attempting AutoUpdate...
```

It installs `lap` into the active venv. Subsequent runs skip this step.

---

## GPU Acceleration

```powershell
python -c "import torch; print('CUDA:', torch.cuda.is_available())"
```

YOLO will automatically use a CUDA GPU if available. Force CPU with:

```python
model = YOLO("yolo26n.pt")
model.to("cpu")
```

`half_precision` (FP16) provides a ~2× speed boost on NVIDIA GPUs. It requires CUDA.
Do not enable it in config unless `torch.cuda.is_available()` returns `True`.

---

## Model Export (production only)

Only export when model weights are finalised. Do not export during active development.

```python
from ultralytics import YOLO
model = YOLO("yolo26n.pt")
model.export(format="onnx")              # portable CPU/GPU
model.export(format="engine", device=0)  # TensorRT, NVIDIA only
```

---

## Reference Links

| Resource | URL |
| ---------- | ----- |
| Ultralytics tracking | <https://docs.ultralytics.com/modes/track> |
| Ultralytics prediction | <https://docs.ultralytics.com/modes/predict> |
| Results API | <https://docs.ultralytics.com/modes/predict/#working-with-results> |
| FastAPI | <https://fastapi.tiangolo.com> |
| Shapely | <https://shapely.readthedocs.io> |
| NetworkX | <https://networkx.org> |
| Ultralytics license | <https://www.ultralytics.com/license> |

---

## Contributing

See `04_CONTRIBUTING.md`.
