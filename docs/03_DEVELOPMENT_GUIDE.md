# VAHANM Development Guide

## Getting Started

This guide will help you set up the VAHANM development environment and understand the codebase structure.

### Prerequisites

- Python 3.10 or higher
- pip package manager
- Git
- Camera for testing (laptop webcam or external camera)
- PostgreSQL (for backend storage)

### System Requirements

#### Minimum (for MVP development)
- CPU: Intel i5 / AMD Ryzen 5 or better
- RAM: 8GB minimum, 16GB recommended
- Storage: 50GB free space
- GPU: Not required but recommended (NVIDIA GPU with CUDA support for faster inference)

#### Recommended (for production development)
- CPU: Intel i7 / AMD Ryzen 7 or better
- RAM: 16GB minimum
- Storage: 100GB free space
- GPU: NVIDIA GPU with at least 4GB VRAM and CUDA support

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd vahanm
```

### 2. Backend Setup

#### Install Python Dependencies

```bash
cd backend

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

#### Requirements (`backend/requirements.txt`)

```
# Core dependencies
opencv-python>=4.8.0
numpy>=1.24.0
ultralytics>=8.0.0  # YOLO v8
pyyaml>=6.0
fastapi>=0.100.0
uvicorn>=0.23.0
aiofiles>=23.0.0
python-multipart>=0.0.6
psycopg2-binary>=2.9.0
shapely>=2.0.0
Pillow>=10.0.0
asyncio>=3.4.3
```

#### PostgreSQL Setup

```bash
# Install PostgreSQL (if not already installed)
# Windows: Download from https://www.postgresql.org/download/windows/

# Create database
psql -U postgres -c "CREATE DATABASE vahanm;"

# Create tables
psql -U postgres -d vahanm -f schema.sql
```

#### Configuration

Copy the example config and modify as needed:

```bash
cp config/example_config.yaml config/config.yaml
```

Edit `config/config.yaml` with your settings.

### 3. Frontend Setup (Flutter)

```bash
# Install Flutter (if not already installed)
# Follow instructions at https://docs.flutter.dev/get-started/install

# Install dependencies
flutter pub get

# Run the app
flutter run
```

## Project Structure

### Backend

```
backend/
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── config/
│   ├── detection.yaml      # YOLO detection configuration
│   └── config.yaml         # Main configuration
├── intelligence/
│   ├── perception/         # Perception layer (YOLO, OCR, etc.)
│   │   ├── detection/
│   │   │   ├── __init__.py
│   │   │   └── yolo_detector.py
│   │   ├── ocr/
│   │   └── attributes/
│   ├── tracking/           # Multi-object tracking
│   │   ├── tracklet.py
│   │   ├── tracker.py
│   │   └── association.py
│   ├── matching/           # Vehicle matching
│   │   ├── appearance.py
│   │   ├── plate.py
│   │   └── matcher.py
│   ├── graph/              # Camera/road graph
│   │   ├── camera_graph.py
│   │   ├── road_graph.py
│   │   └── routing.py
│   ├── rules/              # Violation detection rules
│   │   ├── speeding.py
│   │   ├── wrong_way.py
│   │   └── signal.py
│   └── coordinator/        # Central coordinator
│       ├── state.py
│       └── coordinator.py
├── media/                  # Media processing
│   ├── ingestion/
│   └── transport/
├── sensors/                # Sensor integration
│   ├── radar/
│   └── microphone/
├── storage/                # Database access
│   ├── database.py
│   └── embedding_store.py
└── api/                    # REST API
    ├── routes/
    └── websocket.py
```

### Frontend (Flutter)

```
lib/
├── main.dart              # App entry point
├── app.dart               # Main application widget
├── config/
│   ├── models/            # Data models
│   ├── themes/            # UI themes
│   └── constants.dart     # App constants
└── src/
    ├── features/
    │   └── presentation/
    │       ├── screens/   # Screen widgets
    │       └── widgets/   # Reusable widgets
    └── utils/             # Utility functions
```

## Core Components

### 1. YOLO Detector

The YOLO (You Only Look Once) detector is the primary vehicle detection component.

#### What is YOLO?

YOLO is a real-time object detection algorithm that:
- Processes the entire image in a single forward pass
- Predicts multiple bounding boxes and class probabilities
- Very fast compared to R-CNN variants
- Good tradeoff between speed and accuracy

#### How YOLO Works

1. **Image Division**: The input image is divided into a grid (e.g., 416x416 pixels)
2. **Grid Prediction**: Each grid cell predicts bounding boxes and class probabilities
3. **Non-Maximum Suppression (NMS)**: Overlapping boxes are filtered to keep the best predictions

#### YOLO Model Sizes

Ultralytics YOLOv8 provides multiple model sizes:

| Model | Size | Parameters | mAP (val) | Speed (CPU) | Speed (GPU) |
|-------|------|------------|-----------|-------------|-------------|
| YOLOv8n | 6.3 MB | 3.2 M | 37.3 | 454.6 ms | 1.5 ms |
| YOLOv8s | 22.0 MB | 11.2 M | 44.9 | 489.8 ms | 1.7 ms |
| YOLOv8m | 52.4 MB | 25.9 M | 50.2 | 521.4 ms | 2.3 ms |
| YOLOv8l | 98.1 MB | 43.7 M | 52.9 | 570.0 ms | 3.1 ms |
| YOLOv8x | 170.8 MB | 68.2 M | 53.9 | 605.9 ms | 4.5 ms |

**Recommendation for VAHANM**: Start with `yolov8n.pt` (nano) for speed, upgrade to `yolov8s.pt` (small) or larger if accuracy is insufficient.

#### Using the YOLO Detector

```python
from backend.intelligence.perception.detection import create_detector

# Create detector with default configuration
detector = create_detector()

# Detect objects in a frame
import cv2
frame = cv2.imread("test_image.jpg")
results = detector.detect(frame)

# Extract results
for box in results.boxes:
    x1, y1, x2, y2 = box.xyxy[0].tolist()
    confidence = box.conf[0].item()
    class_id = int(box.cls[0])
    class_name = detector.classes[class_id]
    print(f"Found {class_name} with confidence {confidence:.2f}")
```

#### Configuration Options

Edit `backend/config/detection.yaml` to customize:

```yaml
model_path: "yolov8n.pt"           # Model file
conf_threshold: 0.25               # Minimum confidence
iou_threshold: 0.45                # NMS threshold
device: "cuda"                     # "cuda" or "cpu"
imgsz: 640                         # Image size
```

#### Supported Classes

By default, YOLO detects all COCO dataset classes:

| Class ID | Class Name |
|----------|------------|
| 0 | person |
| 1 | bicycle |
| 2 | car |
| 3 | motorcycle |
| 4 | airplane |
| 5 | bus |
| 6 | train |
| 7 | truck |
| 8 | boat |
| ... | ... |

For VAHANM, commonly used classes are:
- `2` - car
- `3` - motorcycle
- `5` - bus
- `7` - truck

Configure classes in `detection.yaml`:

```yaml
classes: [2, 3, 5, 7]  # Only detect vehicles
```

### 2. ByteTrack Tracker

ByteTrack is a multi-object tracker that maintains consistent IDs across frames.

#### How ByteTrack Works

1. **Detection association**: Matches detections across frames
2. **Tracklet creation**: Creates short track segments
3. **Tracklet linking**: Links tracklets into full tracks
4. **Identity maintenance**: Maintains consistent track IDs

#### Usage

```python
from byte_track import ByteTrack

# Create tracker
tracker = ByteTrack()

# Update with detections
tracks = tracker.update(detections)
```

### 3. OCR/LPR Engine

The OCR (Optical Character Recognition) engine extracts license plate text from images.

#### Requirements

- Deep learning OCR model (>90% accuracy target per PS)
- Support for Indian license plate formats
- Robustness to poor lighting, motion blur, dirty plates

#### Implementation Status

The OCR component is a primary ML development target for VAHANM.

## Development Workflow

### 1. Setting Up YOLO for Development

```bash
# Install ultralytics
pip install ultralytics

# Test YOLO
python -c "from ultralytics import YOLO; model = YOLO('yolov8n.pt'); results = model('bus.jpg'); results.show()"

# Or use our wrapper
python -c "from backend.intelligence.perception.detection import create_detector; detector = create_detector(); print(detector.get_classes())"
```

### 2. Testing Detection

```bash
# Test with image
python -c "
import cv2
from backend.intelligence.perception.detection import create_detector

detector = create_detector()
frame = cv2.imread('test_image.jpg')
results = detector.detect(frame, return_type='boxes')
print(f'Found {len(results)} objects:')
for box in results:
    print(f'  {box[\"class_name\"]} ({box[\"confidence\"]:.2f})')
"

# Test with video
python -c "
import cv2
from backend.intelligence.perception.detection import create_detector

detector = create_detector()
cap = cv2.VideoCapture(0)  # Laptop camera

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    results = detector.detect(frame, return_type='boxes')
    
    # Draw boxes
    for box in results:
        x1, y1 = int(box['x1']), int(box['y1'])
        x2, y2 = int(box['x2']), int(box['y2'])
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, f'{box[\"class_name\"]} {box[\"confidence\"]:.2f}', 
                   (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    
    cv2.imshow('YOLO Detection', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
"
```

### 3. Integration with Tracking

```python
from backend.intelligence.perception.detection import create_detector
from backend.intelligence.tracking import ByteTrack

detector = create_detector()
tracker = ByteTrack()

cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    # Detect
    detections = detector.detect(frame, return_type='boxes')
    
    # Track
    tracklets = tracker.update(detections)
    
    # Display
    for track in tracklets:
        x1, y1, x2, y2 = track['bbox']
        track_id = track['track_id']
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, f'ID {track_id}', (x1, y1 - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    
    cv2.imshow('Tracking', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
```

## Troubleshooting

### Common Issues

#### 1. YOLO Import Error

```
ModuleNotFoundError: No module named 'ultralytics'
```

**Solution**: Install ultralytics

```bash
pip install ultralytics
```

#### 2. CUDA Out of Memory

```
RuntimeError: CUDA out of memory
```

**Solutions**:
- Use smaller model: `yolov8n.pt` instead of `yolov8x.pt`
- Reduce `imgsz` in config
- Close other GPU applications
- Use CPU instead: `device: "cpu"`

#### 3. Slow Inference

**Solutions**:
- Use smaller model (nano or small)
- Enable half precision: `half_precision: true`
- Use GPU if available
- Reduce image size: `imgsz: 320` or `416`

#### 4. Poor Detection Accuracy

**Solutions**:
- Use larger model: `yolov8s.pt` or larger
- Lower confidence threshold: `conf_threshold: 0.15`
- Ensure proper lighting conditions
- Consider fine-tuning on vehicle-specific dataset

### Performance Optimization

#### GPU Acceleration

```bash
# Check if CUDA is available
python -c "import torch; print(torch.cuda.is_available())"

# Use GPU in config
device: "cuda"
```

#### Model Quantization

```bash
# Export to ONNX for faster inference
python -c "
from ultralytics import YOLO
model = YOLO('yolov8n.pt')
model.export(format='onnx', dynamic=True)
"
```

## Next Steps

1. **Setup ByteTrack** for multi-object tracking
2. **Implement OCR** for license plate recognition
3. **Create cluster architecture** for multi-camera support
4. **Build violation detection** rules
5. **Implement cross-cluster association** for vehicle tracking

## Web Platform Setup

### 1. Project Setup

```bash
# Create web platform directory
mkdir web-platform
cd web-platform

# Choose a framework and set up project
# React
npx create-react-app vahanm-web
cd vahanm-web

# Vue
npm create vue@latest vahanm-web
cd vahanm-web

# Angular
ng new vahanm-web
cd vahanm-web
```

### 2. Install Dependencies

```bash
# Map visualization
npm install leaflet react-leaflet
# or
npm install vue2-leaflet

# Charts and analytics
npm install chart.js react-chartjs-2
# or
npm install vue-chartjs

# WebSocket for real-time data
npm install socket.io-client
```

### 3. Basic Structure

```
web-platform/
├── public/
├── src/
│   ├── components/
│   │   ├── CameraFeed.vue
│   │   ├── VehicleList.vue
│   │   ├── ViolationAlert.vue
│   │   └── TrafficAnalytics.vue
│   ├── pages/
│   │   ├── Dashboard.vue
│   │   ├── VehicleSearch.vue
│   │   ├── TrafficMap.vue
│   │   └── Analytics.vue
│   ├── services/
│   │   ├── api.js
│   │   ├── websocket.js
│   │   └── mapService.js
│   ├── App.vue
│   └── main.js
├── package.json
└── README.md
```

### 4. Connecting to Backend

```javascript
// src/services/api.js
import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json'
  }
});

// Example: Get vehicles
export const getVehicles = async () => {
  const response = await api.get('/vehicles');
  return response.data;
};

// Example: Get violations
export const getViolations = async () => {
  const response = await api.get('/violations');
  return response.data;
};
```

### 5. WebSocket for Real-time Updates

```javascript
// src/services/websocket.js
import io from 'socket.io-client';

const SOCKET_URL = 'http://localhost:8000';

export const socket = io(SOCKET_URL, {
  transports: ['websocket']
});

// Listen for new vehicles
socket.on('vehicle_detected', (data) => {
  console.log('New vehicle detected:', data);
  // Update UI
});

// Listen for violations
socket.on('violation', (data) => {
  console.log('Violation detected:', data);
  // Show alert
});
```

### 6. Map Integration

```javascript
// src/components/TrafficMap.vue
import { MapContainer, TileLayer, Marker, Polyline } from 'react-leaflet';

const TrafficMap = ({ vehicles, routes }) => {
  return (
    <MapContainer center={[12.9716, 77.5946]} zoom={12} style={{ height: '100vh' }}>
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; OpenStreetMap contributors'
      />
      {vehicles.map(vehicle => (
        <Marker
          key={vehicle.id}
          position={[vehicle.latitude, vehicle.longitude]}
          popupContent={vehicle.plate}
        />
      ))}
      {routes.map((route, index) => (
        <Polyline
          key={index}
          positions={route.coordinates}
          color="blue"
          weight={2}
        />
      ))}
    </MapContainer>
  );
};
```

### 7. Running the Web Platform

```bash
# Start backend
cd ../backend
python -m uvicorn main:app --reload

# Start web platform
cd ../web-platform
npm start
```

Visit `http://localhost:3000` to see your web platform.

## Contributing

See `docs/04_CONTRIBUTING.md` for contribution guidelines.