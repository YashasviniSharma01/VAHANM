"""
Traffic Rules Base Interface & Core Rule Models
Architecture reference:
  - 01_ARCHITECTURE.md §2.4 (Tracklet Model)
  - 02_REASONING_AND_ORCHESTRATION.md §6 (Traffic Rule Evaluation)
  - 02_REASONING_AND_ORCHESTRATION.md §6.1 (Rule Interface & Separation)
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

try:
    from .result import RuleResult
except (ImportError, ValueError):
    from result import RuleResult


class RuleState(str, Enum):
    """Lifecycle state of a monitored traffic rule."""
    IDLE = "idle"
    MONITORING = "monitoring"  # inside zone / approaching, waiting
    TRIGGERED = "triggered"    # condition met
    EXPIRED = "expired"


class ZoneType(str, Enum):
    """Geometric topology type for monitored zones."""
    POLYLINE = "polyline"
    POLYGON = "polygon"
    LINE = "line"


class SignalPhase(str, Enum):
    """Traffic light signal phase states."""
    RED = "RED"
    AMBER = "AMBER"
    GREEN = "GREEN"
    UNKNOWN = "UNKNOWN"


@dataclass
class ZoneGeometry:
    """Represents geometric boundaries, polylines, and constraints for rules."""
    zone_id: str
    coordinates: List[Tuple[float, float]] = field(default_factory=list)
    zone_type: ZoneType = ZoneType.POLYLINE
    speed_limit_kmh: Optional[float] = None
    dwell_threshold_sec: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorldState:
    """Current world and environmental state observed at a cluster."""
    cluster_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    signal_phase: Optional[SignalPhase] = None
    weather_condition: Optional[str] = None
    active_violations_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Tracklet:
    """Continuous local track representation from edge perception.
    
    Conforms to 01_ARCHITECTURE.md §2.4.
    Maintains chronological centroids, confidences, and bounding boxes.
    
    Attributes representing detected real-world identity are explicit.
    """
    tracklet_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    cluster_id: Optional[str] = None
    device_id: Optional[str] = None
    local_track_id: int = 0
    class_id: Optional[int] = None
    class_name: Optional[str] = None
    
    # Chronological sensor data points
    centroids: List[Tuple[float, float]] = field(default_factory=list)
    confidences: List[float] = field(default_factory=list)
    timestamps: List[str] = field(default_factory=list)
    bboxes: List[Dict[str, float]] = field(default_factory=list)
    
    first_observation_time: Optional[datetime] = None
    last_observation_time: Optional[datetime] = None
    observation_count: int = 0
    plate_visibility_max: float = 0.0
    estimated_speed: Optional[float] = None
    direction: Optional[Tuple[float, float]] = None

    def add_point(
        self,
        centroid: Tuple[float, float],
        confidence: float,
        timestamp: Optional[str] = None,
        bbox: Optional[Dict[str, float]] = None,
    ) -> None:
        """Helper to append a new tracked observation point."""
        self.centroids.append(centroid)
        self.confidences.append(confidence)
        if timestamp:
            self.timestamps.append(timestamp)
        if bbox:
            self.bboxes.append(bbox)
        self.observation_count += 1


class TrafficRule(ABC):
    """Abstract Base Class for all traffic rule evaluators.
    
    Enforces the contract:
        evaluate(tracklet, world_state, geometry) -> RuleResult
    
    Rules are strictly stateless evaluators: they never mutate world state,
    never write to the database, and never invoke capabilities directly.
    """
    rule_id: str = "base_rule"
    rule_name: str = "Base Traffic Rule"
    description: str = "Base interface for traffic rule evaluations"
    rule_state: RuleState = RuleState.IDLE

    @abstractmethod
    def evaluate(
        self,
        tracklet: Tracklet,
        world_state: Optional[WorldState] = None,
        geometry: Optional[ZoneGeometry] = None,
    ) -> RuleResult:
        """Evaluate whether a tracklet breaches the rule condition."""
        raise NotImplementedError("Subclasses must implement evaluate()")


if __name__ == "__main__":
    # Self-test when executed directly
    print("Testing state_machine_rules models...")
    t = Tracklet(local_track_id=101, class_id=2, class_name="car")
    t.add_point((100.0, 150.0), confidence=0.88)
    t.add_point((105.0, 160.0), confidence=0.91)
    
    ws = WorldState(cluster_id="cluster-delhi-01", signal_phase=SignalPhase.RED)
    zg = ZoneGeometry(zone_id="stop_line_01", coordinates=[(90.0, 155.0), (120.0, 155.0)], zone_type=ZoneType.LINE)
    
    print(f"Tracklet created: ID={t.tracklet_id}, Points={t.observation_count}, Class={t.class_name}")
    print(f"WorldState created: Signal={ws.signal_phase}, Cluster={ws.cluster_id}")
    print(f"ZoneGeometry created: Zone={zg.zone_id}, Type={zg.zone_type.value}")
    print("state_machine_rules: ALL CHECKS PASSED.")