# VAHANM Rules Engine — C/C++ Developer's Guide to the Python Implementation

Welcome to the internal engineering guide for `backend/intelligence/rules/`.

If your background is primarily **C / C++** (memory layouts, compilation units, RAII, pointers, abstract classes, and deterministic linking), Python's runtime behavior, dynamic typing, and top-level module execution can feel unfamiliar or counter-intuitive.

This document breaks down:
1. **The C/C++ vs. Python Mental Model** (why code broke previously).
2. **Every bug that was present in the codebase and how it was fixed.**
3. **Detailed code walkthrough of all models and rule evaluations.**
4. **C++ to Python "Rosetta Stone" mapping.**
5. **How this aligns strictly with `@docs` (`01_ARCHITECTURE.md`, `02_REASONING_AND_ORCHESTRATION.md`, `03_DEVELOPMENT_GUIDE.md`).**

---

## 1. C/C++ vs. Python: The Mental Model

In C++, compilation and execution are cleanly separated into distinct stages:
1. **Preprocessing (`#include`, `#define`)**
2. **Compilation (AST generation, type checking, code generation into `.o` objects)**
3. **Linking (resolving symbols into a binary)**
4. **Runtime (`main()` is called; no code runs before `main()` except static initializers)**

### In Python, `import` IS Execution!
Python has **no ahead-of-time compiler or linker**. When you write:
```python
import intelligence.rules.state_machine_rules
```
Python reads the file from top to bottom and **executes every single statement in real time**:
- `class TrafficRules:` executes at file-import time to construct a `type` object in heap memory.
- `def evaluate(...):` executes at file-import time to bind a function object to that name.
- Any top-level statement (like `raise NotImplementedError()`) executes **immediately when imported**, not when a function is called!

---

## 2. Autopsy: What Was Broken and Why It Crashed

Here is the exact code that was previously in `state_machine_rules.py` and why it failed:

### Bug 1: Forward Declaration / Top-to-Bottom Name Resolution
```python
# PREVIOUS BROKEN CODE:
class TrafficRules:
    rule_id: str
    rule_state: RuleState   # <-- CRASH! NameError: name 'RuleState' is not defined

...
class RuleState(Enum):      # Defined 20 lines later!
    IDLE = "idle"
```

* **Why it crashed:** In C++, you can forward-declare an enum or class:
  ```cpp
  enum class RuleState; // C++ forward declaration
  class TrafficRules { RuleState state; };
  ```
  In Python, line 7 was executed before Python had ever encountered line 25. Because Python evaluates types at runtime during class construction, it encountered the symbol `RuleState`, found nothing in the namespace, and threw `NameError`.
* **The Fix:**
  1. Define `RuleState` *before* `TrafficRules`.
  2. Add `from __future__ import annotations` at the very top. In Python 3.7+, this tells Python to treat type annotations as inert strings at definition time (postponed evaluation), eliminating circular type-hinting crashes.

---

### Bug 2: Top-Level Code Execution
```python
# PREVIOUS BROKEN CODE:
@dataclass
def evaluate(self, tracklet: Tracklet, ...): ...

raise NotImplementedError()   # <-- CRASH! Executed on import!
```

* **Why it crashed:** In C++, writing `throw std::runtime_error("not implemented");` inside an uncalled member function has zero effect at program startup.
  In Python, this `raise` was outside any function or class block. The moment any other file typed `import state_machine_rules`, Python reached that line and aborted the entire program.
* **The Fix:** Move `raise NotImplementedError` inside the body of the virtual method `evaluate(self, ...)` in the base class.

---

### Bug 3: Decorator Misapplication
```python
# PREVIOUS BROKEN CODE:
@dataclass
def evaluate(self, ...):
```

* **Why it crashed:** In C++, you might think of `@dataclass` like a macro or attribute (`[[nodiscard]]`). In Python, `@dataclass` is a metaprogramming decorator that inspects a **class** and automatically synthesizes a constructor (`__init__`), equality operators (`__eq__`), and representation printers (`__repr__`). Applying it to a standalone function (`def evaluate`) is an error.
* **The Fix:** Use `@dataclass` only on classes (`@dataclass class Tracklet:`), and use `@abstractmethod` from the `abc` library on interface functions.

---

### Bug 4: Duplicate Structs with Mismatched Fields (ODR Violation Equivalent)
* In `result.py`:
  ```python
  @dataclass
  class RuleResult:
      triggered: bool = False
      violation_type: str = ""
      confidence: float = 0.0
      evidence_hint: str = ""
      explanation: str = ""
  ```
* In `state_machine_rules.py`:
  ```python
  class RuleResult:
      is_triggered: bool      # <-- Inconsistent field name!
      confidence: float
      violation_type: str
      timestamp: float
      evidance_hint: str      # <-- Typo in field name!
      explanation: str
  ```
* In `line_crossing.py`:
  `line_crossing.py` imported `RuleResult` from `state_machine_rules`, but tried to instantiate it with `RuleResult(triggered=triggered...)`, which failed because `state_machine_rules.RuleResult` called that field `is_triggered`!
* **The Fix:** Standardize on `result.py` as the **Single Source of Truth** for `RuleResult`, matching `02_REASONING_AND_ORCHESTRATION.md §6.1`.

---

### Bug 5: Missing Dependencies (`shapely`)
* `line_crossing.py` did:
  ```python
  from shapely.geometry import LineString
  ```
  `shapely` is a C-extension library wrapping GEOS (Geometry Engine, Open Source). It was commented out in `requirements.txt` and not installed in `.venv`.
* **The Fix:** Uncommented `shapely>=2.0.0` in `requirements.txt` and installed it via `pip install shapely`.

---

## 3. The Architecture: Rules Are Pure Functions, Not State Machines

One key architectural distinction from `docs/01_ARCHITECTURE.md §6` and `docs/02_REASONING_AND_ORCHESTRATION.md §6`:

```
                 WORLD STATE (Sensory facts, positions)
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  TrafficRule::evaluate()                                    │
│  A PURE FUNCTION:                                           │
│  (Tracklet, WorldState, ZoneGeometry) ──▶ RuleResult        │
│                                                             │
│  - No database writes                                       │
│  - No capability invocations                                │
│  - No internal persistent mutation                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                         RuleResult
                              │
                              ▼
           CENTRAL ORCHESTRATOR / INVESTIGATION
           (Maintains state machine: IDLE -> INVESTIGATING -> RESOLVED)
```

In the original draft, the developer placed `RuleState (IDLE, MONITORING, TRIGGERED, EXPIRED)` directly on the rule. But traffic rules should be **stateless condition checkers**. The state machine belongs to the **Cluster** and the **Investigation**, not the rule logic!

We preserved `RuleState` as an optional tracking state for multi-stage monitoring, but ensured that `TrafficRule` evaluates purely as a function.

---

## 4. Code Deep Dive: The New Rule Components

### A. `result.py` — The Universal Output Contract
Equivalent to a POD (Plain Old Data) `struct` in C++:

```python
@dataclass
class RuleResult:
    triggered: bool = False
    violation_type: str = ""
    confidence: float = 0.0
    evidence_hint: str = ""
    explanation: str = ""
```

In C++, this is identical to:
```cpp
struct RuleResult {
    bool triggered = false;
    std::string violation_type = "";
    double confidence = 0.0;
    std::string evidence_hint = "";
    std::string explanation = "";
};
```

---

### B. `state_machine_rules.py` — Foundational Types & Abstract Base Class

#### 1. `Tracklet` (from `01_ARCHITECTURE.md §2.4`)
In C++, you would define a class containing vectors of coordinates and timestamps:
```cpp
struct Tracklet {
    std::string tracklet_id;
    int local_track_id;
    std::vector<std::pair<double, double>> centroids;
    std::vector<double> confidences;
    // ...
};
```
In our Python code, we use `@dataclass`:
```python
@dataclass
class Tracklet:
    tracklet_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    cluster_id: Optional[str] = None
    device_id: Optional[str] = None
    local_track_id: int = 0
    class_id: int = 2
    class_name: str = "car"
    centroids: List[Tuple[float, float]] = field(default_factory=list)
    confidences: List[float] = field(default_factory=list)
    # ...
```

> **C++ Insight:** `field(default_factory=list)` is required in Python because default arguments in Python are evaluated *once when the function/class is created*. If you wrote `centroids: List = []`, **every single instance of `Tracklet` would share the exact same list in memory!** `default_factory=list` creates a fresh heap allocation for each instance (like `new std::vector`).

#### 2. `TrafficRule` (Abstract Interface)
In C++:
```cpp
class TrafficRule {
public:
    virtual ~TrafficRule() = default;
    virtual RuleResult evaluate(
        const Tracklet& tracklet,
        const std::optional<WorldState>& world_state,
        const std::optional<ZoneGeometry>& geometry
    ) = 0; // Pure virtual
};
```
In Python, we inherit from `abc.ABC` and use `@abstractmethod`:
```python
class TrafficRule(ABC):
    rule_id: str = "base_rule"
    rule_name: str = "Base Traffic Rule"

    @abstractmethod
    def evaluate(
        self,
        tracklet: Tracklet,
        world_state: Optional[WorldState] = None,
        geometry: Optional[ZoneGeometry] = None,
    ) -> RuleResult:
        raise NotImplementedError("Subclasses must implement evaluate()")
```
If a subclass forgets to implement `evaluate()`, Python will refuse to instantiate it, exactly like a C++ compiler rejecting instantiation of a class with pure virtual methods.

---

### C. `line_crossing.py` — Geometrical Line Crossing

`LineCrossingRule` checks if the line segment between the previous centroid ($P_{t-1}$) and current centroid ($P_t$) intersects the forbidden line.

#### Direction Check via 2D Cross Product:
To detect whether a vehicle crossed from **left-to-right** or **right-to-left**, we calculate the 2D cross product:
$$\vec{L} = B - A \quad (\text{forbidden line direction})$$
$$\vec{V} = P_t - P_{t-1} \quad (\text{vehicle trajectory})$$
$$\text{Cross} = L_x \cdot V_y - L_y \cdot V_x$$

- If $\text{Cross} < 0$: Trajectory crosses left-to-right.
- If $\text{Cross} > 0$: Trajectory crosses right-to-left.

This ensures that only forbidden traffic flows trigger a violation.

---

### D. `__init__.py` — The Public API Header

In C++, you provide a master header file (e.g. `rules.hpp`):
```cpp
#pragma once
#include "result.hpp"
#include "state_machine_rules.hpp"
#include "line_crossing.hpp"
```

In Python, `__init__.py` serves this exact role. By adding `__all__ = [...]`, any other file can cleanly do:
```python
from intelligence.rules import LineCrossingRule, Tracklet, RuleResult
```

---

## 5. C++ to Python Rosetta Stone

| C++ Concept | Python Equivalent | Notes |
| :--- | :--- | :--- |
| `#include <vector>` | `from typing import List` or `list` | Python 3.9+ supports built-in `list[float]` |
| `std::unique_ptr<T>` / heap alloc | Automatic reference counting + GC | Python objects live on heap; freed when refcount hits 0 |
| `nullptr` | `None` | Singleton object representing absence of value |
| `std::optional<T>` | `Optional[T]` or `T \| None` | Expresses nullable fields |
| `struct MyData { ... };` | `@dataclass class MyData: ...` | Synthesizes constructor, repr, and comparison |
| `virtual void func() = 0;` | `@abstractmethod def func(self): ...` | Requires class to inherit from `abc.ABC` |
| `enum class State { IDLE };` | `class State(str, Enum): IDLE = "idle"` | Strongly-typed enumeration |
| `this->member` | `self.member` | In Python, `self` must be explicitly named in method signatures |
| `namespace rules { ... }` | Directory with `__init__.py` | Directory structure defines the namespace |
| Public vs Private | Convention: `_private_method()` | Leading underscore indicates private/internal |
| `assert()` | `assert cond, "msg"` or `raise ValueError()` | Exceptions are standard for error handling |

---

## 6. How to Test Your Rules

You can run this quick verification snippet at any time from `backend/`:

```powershell
cd d:\SIH\VAHANM\backend
.\.venv\Scripts\Activate.ps1

python -c "
from intelligence.rules import LineCrossingRule, Tracklet

# Define forbidden line across Y = 10 from X=0 to X=10
rule = LineCrossingRule(forbidden_line=[(0, 10), (10, 10)])

# Create tracklet moving from (5, 5) to (5, 15) -> crosses Y=10!
tracklet = Tracklet(local_track_id=42)
tracklet.add_point(centroid=(5.0, 5.0), confidence=0.9)
tracklet.add_point(centroid=(5.0, 15.0), confidence=0.9)

result = rule.evaluate(tracklet)
print('Violation Triggered:', result.triggered)
print('Violation Type:', result.violation_type)
print('Explanation:', result.explanation)
"
```

Output:
```
Violation Triggered: True
Violation Type: LINE_CROSSING
Explanation: Track 42 crossed forbidden line from (5.0, 5.0) to (5.0, 15.0).
```
