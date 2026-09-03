"""
YOLO v8 Detector for Vehicle Detection

This module provides a wrapper around Ultralytics YOLOv8 for vehicle detection
in traffic camera feeds.

Usage:
    detector = YOLODetector(config_path="config/detection.yaml")
    results = detector.detect(frame)
    for box in results.boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        confidence = box.conf[0].item()
        class_id = int(box.cls[0])
        class_name = detector.classes[class_id]
"""

import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
import logging

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None
    logging.warning("ultralytics not installed. Install with: pip install ultralytics")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class YOLODetector:
    """
    YOLO v8 detector wrapper for vehicle detection.
    
    Features:
    - Multiple model sizes (n, s, m, l, x) for speed/accuracy tradeoff
    - Pretrained COCO weights with optional fine-tuning
    - Configurable confidence and IoU thresholds
    - GPU acceleration via CUDA
    - Frame preprocessing options
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, config_path: Optional[str] = None):
        """
        Initialize YOLO detector.
        
        Args:
            config: Dictionary with configuration parameters
            config_path: Path to YAML config file (overrides config dict)
        """
        if YOLO is None:
            raise ImportError(
                "ultralytics package not installed. "
                "Install with: pip install ultralytics"
            )
        
        # Default configuration
        self.default_config = {
            "model_path": "yolov8n.pt",  # Default: smallest model for speed
            "model_size": "n",  # n, s, m, l, x
            "classes": None,  # None = all classes, or list of class indices
            "conf_threshold": 0.25,
            "iou_threshold": 0.45,
            "device": "cuda" if cv2.cuda.getCudaEnabledDeviceCount() > 0 else "cpu",
            "imgsz": 640,
            "half_precision": True,  # FP16 inference for speed
            "preprocess": {
                "resize": True,
                "target_size": 640,
                "normalize": True,
                "color_conversion": True
            }
        }
        
        # Load config from file if provided
        if config_path:
            config = self._load_config(config_path)
        
        # Merge with defaults
        if config:
            self.config = {**self.default_config, **config}
        else:
            self.config = self.default_config
        
        # Initialize model
        self.model = None
        self.classes = None
        self._initialize_model()
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        import yaml
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Could not load config from {config_path}: {e}")
            return {}
    
    def _initialize_model(self):
        """Initialize YOLO model with configuration."""
        model_path = self.config["model_path"]
        model_size = self.config["model_size"]
        
        # Build model path if only size specified
        if not model_path.endswith('.pt') and not model_path.endswith('.yaml'):
            model_path = f"yolov8{model_size}.pt"
        
        logger.info(f"Loading YOLO model: {model_path}")
        logger.info(f"Using device: {self.config['device']}")
        
        try:
            self.model = YOLO(model_path)
            
            # Get class names from COCO dataset
            self.classes = self.model.names
            
            # Set detection parameters
            self.model.conf = self.config["conf_threshold"]
            self.model.iou = self.config["iou_threshold"]
            self.model.classes = self.config["classes"]
            self.model.imgsz = self.config["imgsz"]
            
            logger.info(f"Model loaded successfully with {len(self.classes)} classes")
            logger.info(f"Detection classes: {self.classes}")
            
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            raise
    
    def detect(self, frame: np.ndarray, return_type: str = "detection") -> Any:
        """
        Perform object detection on a frame.
        
        Args:
            frame: Input image (BGR format from OpenCV)
            return_type: Type of results to return
                - "detection": Ultralytics DetectionResults object
                - "boxes": List of bounding boxes with confidence and class
                - "cropped": List of cropped vehicle regions
        
        Returns:
            Detection results in requested format
        """
        if self.model is None:
            raise RuntimeError("Model not initialized. Call _initialize_model() first.")
        
        # Preprocess frame if configured
        if self.config["preprocess"]["resize"]:
            frame = self._preprocess_frame(frame)
        
        # Run inference
        results = self.model.predict(
            source=frame,
            conf=self.config["conf_threshold"],
            iou=self.config["iou_threshold"],
            classes=self.config["classes"],
            imgsz=self.config["imgsz"],
            device=self.config["device"],
            half=self.config["half_precision"],
            verbose=False
        )
        
        if return_type == "detection":
            return results[0]  # Returns DetectionResults
        elif return_type == "boxes":
            return self._extract_boxes(results[0])
        elif return_type == "cropped":
            return self._extract_crops(frame, results[0])
        else:
            return results[0]
    
    def _preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        """Preprocess frame according to configuration."""
        if not self.config["preprocess"]["resize"]:
            return frame
        
        target_size = self.config["preprocess"]["target_size"]
        h, w = frame.shape[:2]
        
        # Resize maintaining aspect ratio
        if h != target_size or w != target_size:
            frame = cv2.resize(frame, (target_size, target_size))
        
        return frame
    
    def _extract_boxes(self, results) -> List[Dict[str, Any]]:
        """Extract bounding boxes from DetectionResults."""
        boxes_list = []
        
        if results.boxes is None:
            return boxes_list
        
        for box in results.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            confidence = box.conf[0].item()
            class_id = int(box.cls[0])
            class_name = self.classes[class_id]
            
            boxes_list.append({
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "confidence": confidence,
                "class_id": class_id,
                "class_name": class_name,
                "centroid": ((x1 + x2) / 2, (y1 + y2) / 2),
                "area": (x2 - x1) * (y2 - y1)
            })
        
        return boxes_list
    
    def _extract_crops(self, frame: np.ndarray, results) -> List[np.ndarray]:
        """Extract cropped vehicle regions from frame."""
        crops = []
        
        if results.boxes is None:
            return crops
        
        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            
            # Add padding for context
            padding = int((x2 - x1) * 0.1)
            x1 = max(0, x1 - padding)
            y1 = max(0, y1 - padding)
            x2 = min(frame.shape[1], x2 + padding)
            y2 = min(frame.shape[0], y2 + padding)
            
            crop = frame[y1:y2, x1:x2]
            crops.append(crop)
        
        return crops
    
    def detect_video(
        self,
        video_path: str,
        output_path: Optional[str] = None,
        max_frames: Optional[int] = None
    ) -> List[List[Dict[str, Any]]]:
        """
        Detect objects in a video file.
        
        Args:
            video_path: Path to input video
            output_path: Optional path to save annotated output video
            max_frames: Maximum number of frames to process
        
        Returns:
            List of detection results per frame
        """
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")
        
        results_per_frame = []
        
        # Setup output video if specified
        if output_path:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        else:
            out = None
        
        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            if max_frames and frame_count >= max_frames:
                break
            
            # Detect objects
            boxes = self.detect(frame, return_type="boxes")
            results_per_frame.append(boxes)
            
            # Annotate frame
            annotated_frame = self._annotate_frame(frame.copy(), boxes)
            
            # Write annotated frame
            if out:
                out.write(annotated_frame)
            
            frame_count += 1
            if frame_count % 100 == 0:
                logger.info(f"Processed {frame_count} frames")
        
        cap.release()
        if out:
            out.release()
        
        logger.info(f"Total frames processed: {frame_count}")
        return results_per_frame
    
    def _annotate_frame(self, frame: np.ndarray, boxes: List[Dict]) -> np.ndarray:
        """Annotate frame with detection bounding boxes."""
        for box in boxes:
            x1, y1 = int(box["x1"]), int(box["y1"])
            x2, y2 = int(box["x2"]), int(box["y2"])
            confidence = box["confidence"]
            class_name = box["class_name"]
            
            # Draw bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
            # Draw label
            label = f"{class_name} {confidence:.2f}"
            cv2.putText(
                frame,
                label,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2
            )
        
        return frame
    
    def get_classes(self) -> List[str]:
        """Return list of class names the model can detect."""
        return list(self.classes.values())
    
    def get_class_id(self, class_name: str) -> Optional[int]:
        """Get class ID by class name."""
        return self.classes.get(class_name, None)
    
    def __del__(self):
        """Cleanup on deletion."""
        if hasattr(self, 'model'):
            # YOLO model cleanup if needed
            pass


def create_detector(config: Optional[Dict] = None) -> YOLODetector:
    """
    Factory function to create YOLO detector.
    
    Args:
        config: Optional configuration dictionary
    
    Returns:
        Initialized YOLODetector instance
    """
    return YOLODetector(config=config)