"""
Line Crossing Violation Rule
Architecture reference:
  - 02_REASONING_AND_ORCHESTRATION.md §6.1
  - 03_DEVELOPMENT_GUIDE.md §Phase 3
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple, Union

from shapely.geometry import LineString

try:
    from .result import RuleResult
    from .state_machine_rules import TrafficRule, Tracklet, WorldState, ZoneGeometry
except (ImportError, ValueError):
    from result import RuleResult
    from state_machine_rules import TrafficRule, Tracklet, WorldState, ZoneGeometry


class CrossingDirection(str, Enum):
    """Allowed or forbidden crossing directions across a reference boundary line."""
    ANY = "any"
    LEFT_TO_RIGHT = "left_to_right"
    RIGHT_TO_LEFT = "right_to_left"


@dataclass
class LineCrossingConfig:
    """Configuration parameters for the line crossing rule.
    
    Eliminates magic numbers and allows external configuration per camera/zone.
    """
    forbidden_line: List[Tuple[float, float]]
    direction: CrossingDirection = CrossingDirection.ANY
    min_confidence: float = 0.35
    min_track_history: int = 2
    smoothing_window: int = 2

    def __post_init__(self) -> None:
        if len(self.forbidden_line) < 2:
            raise ValueError("forbidden_line must contain at least 2 points to define a line.")
        if not (0.0 <= self.min_confidence <= 1.0):
            raise ValueError(f"min_confidence must be in [0.0, 1.0], got {self.min_confidence}")
        if self.min_track_history < 2:
            raise ValueError("min_track_history must be >= 2 to compute trajectory motion.")
        if self.smoothing_window < 1:
            raise ValueError("smoothing_window must be >= 1.")
        if isinstance(self.direction, str):
            self.direction = CrossingDirection(self.direction)


class LineCrossingRule(TrafficRule):
    """Detects when a vehicle's centroid trajectory crosses a forbidden boundary line."""
    
    rule_id = "line_crossing_v1"
    rule_name = "Line Crossing Rule"
    description = "Triggers a violation when vehicle track crosses a forbidden polyline."

    def __init__(
        self,
        forbidden_line: Optional[List[Tuple[float, float]]] = None,
        direction: Union[CrossingDirection, str] = CrossingDirection.ANY,
        min_confidence: float = 0.35,
        config: Optional[LineCrossingConfig] = None,
    ):
        """
        Initialize the line crossing rule.
        
        Accepts either a validated LineCrossingConfig or individual parameters for backwards compatibility.
        """
        if config is not None:
            self.config = config
        else:
            if forbidden_line is None:
                raise ValueError("Either 'config' or 'forbidden_line' must be provided.")
            self.config = LineCrossingConfig(
                forbidden_line=forbidden_line,
                direction=CrossingDirection(direction) if isinstance(direction, str) else direction,
                min_confidence=min_confidence,
            )
        
        self.line_coords = self.config.forbidden_line
        self.line = LineString(self.config.forbidden_line)
        self.direction = self.config.direction
        self.min_confidence = self.config.min_confidence

    def _check_direction(
        self,
        prev_pt: Tuple[float, float],
        curr_pt: Tuple[float, float],
    ) -> bool:
        """Verify crossing direction using 2D cross product against the reference line segment."""
        if self.direction == CrossingDirection.ANY:
            return True
        
        # Reference vector from the first segment of the forbidden line
        lx = self.line_coords[1][0] - self.line_coords[0][0]
        ly = self.line_coords[1][1] - self.line_coords[0][1]
        
        # Motion vector of the vehicle
        vx = curr_pt[0] - prev_pt[0]
        vy = curr_pt[1] - prev_pt[1]
        
        # 2D cross product: lx * vy - ly * vx
        cross = lx * vy - ly * vx
        
        if self.direction == CrossingDirection.LEFT_TO_RIGHT:
            return cross < 0
        elif self.direction == CrossingDirection.RIGHT_TO_LEFT:
            return cross > 0
        return True

    def evaluate_points(
        self,
        prev_centroid: Tuple[float, float],
        curr_centroid: Tuple[float, float],
        track_conf: float = 1.0,
        track_id: Optional[int] = None,
    ) -> RuleResult:
        """Direct point-to-point evaluation helper as specified in 03_DEVELOPMENT_GUIDE.md §Phase 3."""
        if track_conf < self.config.min_confidence:
            return RuleResult(
                triggered=False,
                confidence=track_conf,
                explanation=f"Track confidence ({track_conf:.2f}) below threshold ({self.config.min_confidence:.2f}).",
            )

        segment = LineString([prev_centroid, curr_centroid])
        crossed = segment.crosses(self.line) or segment.touches(self.line)

        if not crossed:
            return RuleResult(triggered=False, confidence=track_conf)

        if not self._check_direction(prev_centroid, curr_centroid):
            return RuleResult(
                triggered=False,
                confidence=track_conf,
                explanation=f"Line crossed, but direction does not match constraint '{self.direction.value}'.",
            )

        tid_str = f"Track {track_id}" if track_id is not None else "Vehicle"
        explanation = (
            f"{tid_str} crossed forbidden line from "
            f"({prev_centroid[0]:.1f}, {prev_centroid[1]:.1f}) to "
            f"({curr_centroid[0]:.1f}, {curr_centroid[1]:.1f})."
        )

        return RuleResult(
            triggered=True,
            violation_type="LINE_CROSSING",
            confidence=track_conf,
            evidence_hint="VIOLATION_FRAME",
            explanation=explanation,
        )

    def evaluate(
        self,
        tracklet: Tracklet,
        world_state: Optional[WorldState] = None,
        geometry: Optional[ZoneGeometry] = None,
    ) -> RuleResult:
        """
        Evaluate full tracklet history against the forbidden line.
        Satisfies the TrafficRule interface contract.
        """
        # If geometry is supplied dynamically, update reference line
        if geometry and len(geometry.coordinates) >= 2:
            self.line_coords = geometry.coordinates
            self.line = LineString(geometry.coordinates)

        if len(tracklet.centroids) < self.config.min_track_history:
            return RuleResult(
                triggered=False,
                explanation=f"Insufficient track history (< {self.config.min_track_history} centroids).",
            )

        prev = tracklet.centroids[-2]
        curr = tracklet.centroids[-1]
        
        # Use average or minimum of latest confidences based on smoothing window
        window = self.config.smoothing_window
        conf_slice = tracklet.confidences[-window:] if len(tracklet.confidences) >= window else tracklet.confidences
        conf = min(conf_slice) if conf_slice else 1.0

        return self.evaluate_points(
            prev_centroid=prev,
            curr_centroid=curr,
            track_conf=conf,
            track_id=tracklet.local_track_id,
        )


if __name__ == "__main__":
    print("Testing line_crossing module...")
    # Setup forbidden boundary line
    boundary = [(0.0, 100.0), (200.0, 100.0)]
    config = LineCrossingConfig(
        forbidden_line=boundary,
        direction=CrossingDirection.ANY,
        min_confidence=0.4,
    )
    rule = LineCrossingRule(config=config)

    # Test 1: Crossing trajectory (50, 50) -> (50, 150)
    t_crossing = Tracklet(local_track_id=42, class_id=2, class_name="car")
    t_crossing.add_point((50.0, 50.0), confidence=0.9)
    t_crossing.add_point((50.0, 150.0), confidence=0.88)
    res1 = rule.evaluate(t_crossing)
    print(f"Test 1 (Crossing): Triggered={res1.triggered}, Explanation={res1.explanation}")
    assert res1.triggered, "Test 1 failed: Line crossing should trigger violation"

    # Test 2: Non-crossing trajectory (50, 50) -> (50, 80)
    t_safe = Tracklet(local_track_id=43, class_id=2, class_name="car")
    t_safe.add_point((50.0, 50.0), confidence=0.9)
    t_safe.add_point((50.0, 80.0), confidence=0.85)
    res2 = rule.evaluate(t_safe)
    print(f"Test 2 (Safe): Triggered={res2.triggered}")
    assert not res2.triggered, "Test 2 failed: Safe movement should not trigger violation"

    print("line_crossing: ALL CHECKS PASSED.")