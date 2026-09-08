from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class Disposition(str, Enum):
    """The decision based on a single observation."""
    PENDING = "pending"    # Waiting for evaluation
    RETAIN = "retain"      # Keep in tracklet; useful for future matches / trajectory
    DISCARD = "discard"    # Carried no new info; dropped
    ESCALATE = "escalate"  # High-value / critical observation; sent for evidence / OCR


@dataclass
class ObservationQuality:
    """Quality assessment of an observation (per-frame feature)."""
    blur_score: float = 0.0          # Laplacian variance / sharpness score
    crop_ratio: float = 0.0          # How much of the frame or bbox is filled
    occlusion_level: float = 0.0     # 0.0 (clean) to 1.0 (heavily occluded)
    plate_visibility: float = 0.0    # Heuristic based on bbox area & aspect ratio
    illumination: float = 1.0        # Mean pixel intensity (normalized)
    
    # Soft / Fuzzy boolean flags
    is_sharp: bool = False
    is_well_lit: bool = False
    is_good_aspect_ratio: bool = False


@dataclass
class TrackWindow:
    """A sliding window over recent observations for an active track."""
    local_track_id: int
    age_frames: int = 0
    retained_count: int = 0
    is_active: bool = True
    estimated_speed: Optional[float] = None
    estimated_direction: Optional[Tuple[float, float]] = None
    
    # Tracklet history & memory
    last_retained_centroid: Optional[Tuple[float, float]] = None
    last_retained_timestamp: Optional[float] = None
    plate_visibility_max: float = 0.0
    best_blur_score: float = 0.0
    best_crop_ratio: float = 0.0
    
    observations: List[Dict[str, Any]] = field(default_factory=list)
    qualities: List[ObservationQuality] = field(default_factory=list)
