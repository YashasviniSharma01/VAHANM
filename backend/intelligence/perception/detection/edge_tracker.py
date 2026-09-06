"""
Edge Tracker - First working tracker for VAHANM MVP

This module implements the incremental MVP approach:
video → YOLO26 detection → ByteTrack tracking → observation JSON → violation trigger

Usage:
    python edge_tracker.py --source traffic.mp4 --classes 2 3 5 7 --conf 0.35

Output:
    observations.json - List of observations with track_id, timestamp, class, confidence, bbox
    violations.json - List of detected violations (when implemented)

Architecture:
    EdgeTracker class manages:
    - YOLO26 model with track() API
    - Observation collection
    - Local tracking state
    - JSON output generation
"""

import argparse
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    from ultralytics import YOLO
except ImportError:
    raise ImportError(
        "ultralytics not installed. Install with: pip install ultralytics"
    )

try:
    import cv2
except ImportError:
    raise ImportError(
        "opencv-python not installed. Install with: pip install opencv-python"
    )


class EdgeTracker:
    """
    Edge Tracker - First working tracker for VAHANM MVP
    
    This is the simplified tracker that demonstrates the core loop:
    video → YOLO26 detection → ByteTrack tracking → observation JSON
    """
    
    def __init__(
        self,
        model_path: str = "yolo26n.pt",
        tracker_config: str = "bytetrack.yaml",
        classes: Optional[List[int]] = None,
        conf: float = 0.35,
        iou: float = 0.7,
        imgsz: int = 640
    ):
        """
        Initialize the edge tracker.
        
        Args:
            model_path: Path to YOLO26 model (yolo26n.pt, yolo26s.pt, etc.)
            tracker_config: Path to tracker config file
            classes: List of class IDs to detect (None = all classes)
            conf: Confidence threshold for detections
            iou: IOU threshold for NMS
            imgsz: Image size for inference
        """
        self.model = YOLO(model_path)
        self.tracker_config = tracker_config
        self.classes = classes
        self.conf = conf
        self.iou = iou
        self.imgsz = imgsz
        
        # Track state
        self.observations: List[Dict[str, Any]] = []
        self.current_frame: Optional[int] = None
        self.tracking_started: bool = False
        
        # Log message
        print(f"EdgeTracker initialized with YOLO26 model: {model_path}")
        print(f"Tracker config: {tracker_config}")
        print(f"Classes: {classes}")
        print(f"Confidence threshold: {conf}")
    
    def track(
        self,
        source: str,
        output_dir: str = "output",
        max_frames: Optional[int] = None,
        save_output: bool = True,
        show: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Track vehicles in a video source.
        
        Args:
            source: Video file path or camera index (0 for laptop camera)
            output_dir: Directory to save output files
            max_frames: Maximum frames to process (None = process all)
            save_output: Whether to save observations to JSON
            show: Whether to display tracking visualization window
            
        Returns:
            List of observation dictionaries
        """
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Start tracking
        print(f"\nStarting tracking on: {source}")
        print(f"Output directory: {output_dir}")
        
        results = self.model.track(
            source=source,
            tracker=self.tracker_config,
            classes=self.classes,
            conf=self.conf,
            iou=self.iou,
            imgsz=self.imgsz,
            stream=True,
            verbose=False,
            show=show  # Display tracking results in real-time
        )
        
        self.observations = []
        self.tracking_started = True
        frame_count = 0
        start_time = time.time()
        
        for result in results:
            # Get frame info
            frame_count += 1
            timestamp = datetime.now().isoformat()
            
            if max_frames and frame_count > max_frames:
                break
            
            # Extract tracking results
            if result.boxes and result.boxes.id is not None:
                for box in result.boxes:
                    # Get track data
                    track_id = int(box.id.item()) if box.id is not None else None
                    class_id = int(box.cls.item())
                    confidence = box.conf.item()
                    bbox = box.xyxy[0].tolist()
                    
                    # Calculate centroid
                    x1, y1, x2, y2 = bbox
                    centroid = ((x1 + x2) / 2, (y1 + y2) / 2)
                    
                    # Create observation
                    observation = {
                        "frame": frame_count,
                        "timestamp": timestamp,
                        "track_id": track_id,
                        "class_id": class_id,
                        "class_name": self.model.names[class_id],
                        "confidence": confidence,
                        "bbox": {
                            "x1": x1,
                            "y1": y1,
                            "x2": x2,
                            "y2": y2
                        },
                        "centroid": {
                            "x": centroid[0],
                            "y": centroid[1]
                        },
                        "dimensions": {
                            "width": x2 - x1,
                            "height": y2 - y1
                        }
                    }
                    
                    self.observations.append(observation)
            
            # Progress update
            if frame_count % 100 == 0:
                elapsed = time.time() - start_time
                fps = frame_count / elapsed if elapsed > 0 else 0
                print(f"Processed {frame_count} frames ({fps:.1f} FPS)")
        
        # Calculate summary
        elapsed = time.time() - start_time
        fps = frame_count / elapsed if elapsed > 0 else 0
        
        print(f"\nTracking completed:")
        print(f"  Frames processed: {frame_count}")
        print(f"  Objects tracked: {len(self.observations)}")
        print(f"  Unique tracks: {len(set(o['track_id'] for o in self.observations if o['track_id']))}")
        print(f"  Duration: {elapsed:.1f} seconds")
        print(f"  Average FPS: {fps:.1f}")
        
        # Save output
        if save_output:
            self._save_observations(output_path)
        
        return self.observations
    
    def _save_observations(self, output_path: Path) -> None:
        """Save observations to JSON file."""
        output_file = output_path / "observations.json"
        
        with open(output_file, 'w') as f:
            json.dump({
                "metadata": {
                    "source": "edge_tracker",
                    "version": "1.0.0",
                    "generated_at": datetime.now().isoformat(),
                    "total_observations": len(self.observations)
                },
                "observations": self.observations
            }, f, indent=2)
        
        print(f"\nObservations saved to: {output_file}")
    
    def get_unique_tracks(self) -> List[int]:
        """Get list of unique track IDs."""
        return list(set(o['track_id'] for o in self.observations if o['track_id']))
    
    def get_observations_by_track(self, track_id: int) -> List[Dict[str, Any]]:
        """Get all observations for a specific track."""
        return [o for o in self.observations if o['track_id'] == track_id]
    
    def reset(self) -> None:
        """Reset the tracker state."""
        self.observations = []
        self.current_frame = None
        print("Tracker state reset.")


def main():
    """Main entry point for the edge tracker."""
    parser = argparse.ArgumentParser(description="Edge Tracker - First working tracker for VAHANM MVP")
    parser.add_argument("--source", type=str, required=True,
                        help="Video file path or camera index (0 for laptop camera)")
    parser.add_argument("--output-dir", type=str, default="output",
                        help="Directory to save output files")
    parser.add_argument("--classes", type=int, nargs="+", default=None,
                        help="Classes to detect (2=car, 3=motorcycle, 5=bus, 7=truck)")
    parser.add_argument("--conf", type=float, default=0.35,
                        help="Confidence threshold (default: 0.35)")
    parser.add_argument("--max-frames", type=int, default=None,
                        help="Maximum frames to process (None = all)")
    parser.add_argument("--no-save", action="store_true",
                        help="Don't save observations to JSON")
    parser.add_argument("--no-show", action="store_true",
                        help="Don't display tracking visualization window")
    
    args = parser.parse_args()
    
    # Initialize tracker
    tracker = EdgeTracker(
        classes=args.classes,
        conf=args.conf
    )
    
    # Run tracking
    observations = tracker.track(
        source=args.source,
        output_dir=args.output_dir,
        max_frames=args.max_frames,
        save_output=not args.no_save,
        show=not args.no_show
    )
    
    # Summary
    print(f"\nTracking complete!")
    print(f"Total observations: {len(observations)}")
    print(f"Unique tracks: {len(tracker.get_unique_tracks())}")


if __name__ == "__main__":
    main()