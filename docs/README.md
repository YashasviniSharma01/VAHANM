# VAHANM Documentation

## Document Map

| File | Purpose |
|------|---------|
| `00_PROJECT_OVERVIEW.md` | What VAHANM is, core principles, 10-phase build order |
| `01_ARCHITECTURE.md` | Structural components, data models, information flow |
| `02_REASONING_AND_ORCHESTRATION.md` | How the system reasons, manages hypotheses, orchestrates |
| `03_DEVELOPMENT_GUIDE.md` | How each phase is implemented: interfaces, commands, examples |
| `PROJECT_STATUS.md` | **Current code state** — what exists, what's in progress, what's not started |
| `04_CONTRIBUTING.md` | Contribution guidelines |

### Separation rule

- `01_`, `02_`, `03_` describe the **full intended design**. They do not track build state.
- `PROJECT_STATUS.md` tracks **what code exists right now** and known issues.
- When implementation catches up to the design, only `PROJECT_STATUS.md` changes.
- When the design changes, update `01_`/`02_`/`03_` and note the decision in `PROJECT_STATUS.md`.

---

## Quick Start

```powershell
cd d:\SIH\VAHANM\backend
.\.venv\Scripts\Activate.ps1

# Webcam
python intelligence/perception/detection/edge_tracker.py --source 0

# Video file, vehicles only
python intelligence/perception/detection/edge_tracker.py `
    --source traffic.mp4 --classes 2 3 5 7
```

Output: `backend/output/observations.json`

For full setup instructions, see `03_DEVELOPMENT_GUIDE.md`.  
For current build state, see `PROJECT_STATUS.md`.

