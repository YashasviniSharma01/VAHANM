# VAHANM — Project Status

This is the only document that tracks **current code state vs. design plan**.

All other documents (`01_ARCHITECTURE.md`, `02_REASONING_AND_ORCHESTRATION.md`,
`03_DEVELOPMENT_GUIDE.md`) describe the full intended design, not what exists
right now. Update this file as code is written, not those.

---

## Last Updated

2026-09-03

---

## Codebase Snapshot

### What exists and runs

| File | State | Notes |
| ------ | ------- | ------- |
| `backend/intelligence/perception/detection/edge_tracker.py` | ✅ working | Phase 1 complete. Tested live at ~22–24 FPS on CPU. |
| `backend/intelligence/perception/detection/yolo_detector.py` | ✅ written | Detection-only wrapper. `half_precision` defaults to `True` internally — override to `False` on CPU. |
| `backend/intelligence/perception/detection/__init__.py` | ✅ | Exports `YOLODetector`, `create_detector`. |
| `backend/config/detection.yaml` | ✅ corrected | `yolo26n.pt`, `half_precision: false`, `device: cpu`. |
| `backend/yolo26n.pt` | ✅ cached | Downloaded on first run, now on disk. |
| `backend/requirements.txt` | ✅ | Phase 1–3 deps active (shapely enabled). |
| `backend/intelligence/rules/result.py` | ✅ working | Unified RuleResult model matching 02_REASONING_AND_ORCHESTRATION.md §6.1. |
| `backend/intelligence/rules/state_machine_rules.py` | ✅ working | Foundational models (Tracklet, WorldState, ZoneGeometry, TrafficRule ABC). |
| `backend/intelligence/rules/line_crossing.py` | ✅ working | Line crossing geometry & direction checks via Shapely. |
| `backend/intelligence/rules/__init__.py` | ✅ | Exports public rule interfaces. |

### What is started but not yet functional

| File | State | Notes |
|------|-------|-------|
| `backend/main.py` | 🔧 in progress | Being written by developer. See Section Phase 7 below. |

### What exists only as directory stubs (no code yet)

| Path | For phase |
| ------ | ----------- |
| `backend/intelligence/coordinator/` | Phase 6, 8 |
| `backend/intelligence/graph/` | Phase 9 |
| `backend/intelligence/tracking/` | Phase 2+ |
| `backend/api/` | Phase 7 |
| `backend/storage/` | Phase 7 |

### What does not exist yet

| Path | For phase |
| ------ | ----------- |
| `backend/intelligence/perception/observation_manager.py` | Phase 2 |
| `backend/intelligence/perception/evidence_capture.py` | Phase 4 |
| `backend/intelligence/perception/lpr/` | Phase 5 |
| `backend/intelligence/coordinator/orchestrator.py` | Phase 8 |
| `web/` | Phase 10 |

---

## Phase Progress

### Phase 1 — First Working Tracker ✅

**Proves:** `video → detection → tracking → observation JSON`

- `edge_tracker.py` complete.
- `yolo26n.pt` cached in `backend/`.
- `output/observations.json` produced on each run.
- Observation schema fields: `frame`, `timestamp` (wall-clock), `track_id`
  (device-local), `class_id`, `class_name`, `confidence`, `bbox` (x1/y1/x2/y2),
  `centroid` (x/y), `dimensions` (width/height).
- Known limitation: `timestamp` is wall-clock at processing time, not video capture
  time. Addressed in Phase 2 when the observation schema is formalised.

---

### Phase 2 — Observation Manager ❳ not started

**Proves:** observations are filtered before storage.

**Design reference:** `02_REASONING_AND_ORCHESTRATION.md Section 2`

**What to implement:** `backend/intelligence/perception/observation_manager.py`

Nothing written yet.

---

### Phase 3 — Violation Detection ✅ functional baseline

**Proves:** a rule fires correctly against world state.

**Design reference:** `02_REASONING_AND_ORCHESTRATION.md Section 6`

**Implemented:**
- `backend/intelligence/rules/result.py`: Canonical `RuleResult` dataclass.
- `backend/intelligence/rules/state_machine_rules.py`: `TrafficRule` ABC, `Tracklet`, `WorldState`, `ZoneGeometry`.
- `backend/intelligence/rules/line_crossing.py`: `LineCrossingRule` with 2D cross-product direction check and Shapely intersection.
- `backend/intelligence/rules/__init__.py`: Public package exports.
- `learning_guide.md`: Internal guide for developers (gitignored).

Key constraint maintained: **rules evaluate conditions and return a result. They do not invoke
capabilities, write to the database, or call the Orchestrator.** That separation holds.

---

### Phase 4 — Evidence Capture ❳ not started

**Proves:** a violation produces an immutable, storable evidence record.

**Design reference:** `02_REASONING_AND_ORCHESTRATION.md Section 3`

**What to implement:** `backend/intelligence/perception/evidence_capture.py`

Nothing written yet. `YOLODetector._extract_crops()` already implements crop-with-
padding logic and can be reused here.

---

### Phase 5 — LPR Capability ❳ not started

**Proves:** OCR runs on demand, not on every frame.

**Design reference:** `02_REASONING_AND_ORCHESTRATION.md Section 5, 8.3`

**What to implement:** `backend/intelligence/perception/lpr/`

OCR engine not yet selected. Candidates: EasyOCR, PaddleOCR, Tesseract, custom
fine-tuned. Do not select until Phase 5 begins and crops can be benchmarked.

---

### Phase 6 — Hypothesis Management ❳ not started

**Proves:** the system maintains competing identity candidates and backtracks.

**Design reference:** `02_REASONING_AND_ORCHESTRATION.md Section 4, 9`

**What to implement:** `backend/intelligence/coordinator/`

Nothing written yet. Fusion baseline: likelihood scoring (see
`03_DEVELOPMENT_GUIDE.md Section Phase 6`).

---

### Phase 7 — FastAPI Transport 🔧 in progress (main.py)

**Proves:** edge observations reach the central system.

**Design reference:** `03_DEVELOPMENT_GUIDE.md Section Phase 7`

**What is being written:** `backend/main.py`

Developer is implementing this. API directories (`backend/api/`, `backend/storage/`)
are empty stubs.

Protocol decision: **FastAPI native WebSocket, not Socket.IO.**

Dependencies to uncomment in `requirements.txt` when ready:

- `fastapi>=0.100.0`
- `uvicorn>=0.23.0`
- `psycopg2-binary>=2.9.0`

---

### Phase 8 — Orchestrator ❳ not started

**Proves:** the investigation loop runs end-to-end.

**Design reference:** `02_REASONING_AND_ORCHESTRATION.md Section 11`

**What to implement:** `backend/intelligence/coordinator/orchestrator.py`

Nothing written yet. Depends on Phase 6 (hypothesis management) being functional.

---

### Phase 9 — Multi-Cluster Association ❳ not started

**Proves:** the same vehicle is identified across two clusters.

**Design reference:** `02_REASONING_AND_ORCHESTRATION.md Section 13–14`

**What to implement:** `backend/intelligence/graph/`

Dependency to add: `networkx>=3.0`

Nothing written yet.

---

### Phase 10 — Web Platform ❳ not started

**Framework decision:** deferred until Phase 7 (WebSocket feed) is stable.

**What to implement:** `web/`

Nothing written yet. Framework (React/Vue/Angular) and map library (Leaflet/Mapbox)
decided at Phase 10 start.

---

## Open Design Decisions

These are decisions that have been deliberately deferred. Do not commit to an answer
before the relevant phase begins.

| Decision | Deferred to | Notes |
| ---------- | ------------- | ------- |
| OCR engine | Phase 5 | Benchmark on real crops first |
| Web framework (React/Vue/Angular) | Phase 10 | Depends on team familiarity |
| Map library (Leaflet/Mapbox) | Phase 10 | Depends on API key availability |
| Evidence fusion method | Phase 6 | Start with likelihood scoring, evaluate Bayesian |
| Temporal state estimator | Phase 6+ | Start with heuristic baseline, then Kalman |
| HMM vs. learned motion model | Phase 9+ | Experimental; see `02_REASONING_AND_ORCHESTRATION.md Section 17` |

---

## Known Issues in Existing Code

| File | Issue | Fix |
| ------ | ------- | ----- |
| `yolo_detector.py` | `half_precision: True` hardcoded as default — errors on CPU | Pass `config={"half_precision": False}` or use `detection.yaml` |
| `yolo_detector.py` | `model_path` default is `"yolo26n.pt"` (class-level default) | Correct; matches `detection.yaml` |
| `edge_tracker.py` | `timestamp` is wall-clock, not video capture time | Accepted for Phase 1; fix in Phase 2 observation schema |
| `edge_tracker.py` | No quality scoring on observations (all retained) | Phase 2 adds `ObservationManager` |
