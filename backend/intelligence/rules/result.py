"""
RuleResult — what every rule returns.

Architecture reference: 02_REASONING_AND_ORCHESTRATION.md §6.1

A rule NEVER mutates observations or the world state.
It only reads Tracklet + WorldState + Geometry → RuleResult.
The Orchestrator acts on the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RuleResult:
    """Minimal result from evaluating a traffic rule.

    Corresponds to the architecture's RuleResult:
      triggered, violation_type, confidence, evidence_hint, explanation
    """

    triggered: bool = False
    violation_type: str = ""
    confidence: float = 0.0
    evidence_hint: str = ""  # what evidence would help confirm/refute
    explanation: str = ""    # human-readable reason