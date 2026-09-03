"""
Vehicle Detection Package

This package provides object detection capabilities for vehicle monitoring.
"""

from .yolo_detector import YOLODetector, create_detector

__all__ = ["YOLODetector", "create_detector"]