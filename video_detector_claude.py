import cv2
import numpy as np
from collections import defaultdict, deque
from pathlib import Path
from ultralytics import YOLO
import base64
from anthropic import Anthropic

# Configuration
VIDEO_PATH = "/Users/ananyaj/atlas/atlas-app/video1.MOV"
CONFIDENCE_THRESHOLD = 0.5
DETECTION_HISTORY_FRAMES = 15

# Initialize clients
print("Loading YOLOv8 model...")
model = YOLO('yolov8n.pt')
print("✓ YOLOv8 loaded")

claude = Anthropic()
print("✓ Claude API initialized\n")

class ObjectTracker:
    def __init__(self, history_frames=15):
        self.objects = {}
        self.disappeared = {}
        self.next_id = 0
        self.history_frames = history_frames
        self.disappeared_objects = []
        self.frames_captured = {}  # Store frames for later analysis
        
    def register(self, center, yolo_class, confidence, box):
        """Register a new object."""
        self.objects[self.next_id] = {
            'center': center,
            'yolo_class': yolo_class,
            'confidence': confidence,
            'box': box,
            'history': deque(maxlen=self.history_frames),
            'first_frame': 0,
            'first_frame_data': None,
            'last_frame_data': None,
            'frames_seen': 0
        }
        self.disappeared[self.next_id] = 0
        self.next_id += 1
        
    def deregister(self, object_id, current_frame):
        """Deregister and log disappeared object."""
        if object_id in self.objects:
            obj = self.objects[object_id]
            if obj['frames_seen'] > 2:
                self.disappeared_objects.append({
                    'id': object_id,
                    'yolo_class': obj['yolo_class'],
                    'claude_class': None,  # Will be filled by Claude
                    'first_frame': obj['first_frame'],
                    'last_frame': current_frame,
                    'frames_seen': obj['frames_seen'],
                    'confidence': obj['confidence'],
                    'first_frame_data': obj['first_frame_data'],
                    'last_frame_data': obj['last_frame_data']
                })
            del self.objects[object_id]
            del self.disappeared[object_id]
            
    def update(self, detections, current_frame, frame_data=None):
        """Update tracking with new detections."""
        if len(detections) == 0:
            for obj_id in list(self.disappeared.keys()):
                self.disappeared[obj_id] += 1
                if self.disappeared[obj_id] > 15:
                    self.deregister(obj_id, current_frame)
            return
        
        for obj_id in list(self.objects.keys()):
            self.disappeared[obj_id] += 1
            if self.disappeared[obj_id] > 15:
                self.deregister(obj_id, current_frame)
        
        for center, yolo_class, confidence, box in detections:
            matched = False
            best_distance = float('inf')
            best_id = None
            
            for obj_id in self.objects:
                obj_center = self.objects[obj_id]['center']
                distance = np.sqrt((center[0] - obj_center[0])**2 + (center[1] - obj_center[1])**2)
                
                if distance < 100 and distance < best_distance:
                    best_distance = distance
                    best_id = obj_id
                    matched = True
            
            if matched:
                self.objects[best_id]['center'] = center
                self.objects[best_id]['box'] = box
                self.objects[best_id]['history'].append(center)
                self.objects[best_id]['frames_seen'] += 1
                self.objects[best_id]['last_frame_data'] = frame_data
                self.disappeared[best_id] = 0
            else:
                self.register(center, yolo_class, confidence, box)
                self.objects[self.next_id - 1]['first_frame'] = current_frame
                self.objects[self.next_id - 1]['first_frame_data'] = frame_data
    
    def draw(self, frame):
        """Draw tracked objects on frame."""
        for obj_id, obj in self.objects.items():
            center = obj['center']
            yolo_class = obj['yolo_class']
            confidence = obj['confidence']
            box = obj['box']
            
            # Color based on confidence
            if confidence > 0.8:
                color = (0, 255, 0)  # Green
            elif confidence > 0.6:
                color = (0, 255, 255)  # Yellow
            else:
                color = (0, 0, 255)  # Red
            
            # Draw circle marker
            cv2.circle(frame, center, 20, color, 3)
            cv2.circle(frame, center, 10, color, -1)
            
            # Draw bounding box
            x1, y1, x2, y2 = box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Label
            label = f"{yolo_class[:12]} {confidence:.2f}"
            cv2.putText(frame, label, (center[0] - 50, center[1] - 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        return frame

def detect_objects_yolov8(frame):
    """Detect objects using YOLOv8."""
    results = model(frame, conf=CONFIDENCE_THRESHOLD, verbose=False)
    
    detections = []
    if len(results) > 0:
        boxes = results[0].boxes
        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            conf = float(box.conf[0].cpu().numpy())
            cls_id = int(box.cls[0].cpu().numpy())
            class_name = model.names[cls_id]
            
            center = (int((x1 + x2) / 2), int((y1 + y2) / 2))
            box_coords = (int(x1), int(y1), int(x2), int(y2))
            
            detections.append((center, class_name, conf, box_coords))
    
    return detections

def frame_to_base64(frame):
    """Convert frame to base64 for Claude."""
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buffer).decode('utf-8')

def identify_object_with_claude(frame_base64, yolo_class):
    """Use Claude Layer 2 to identify what the object actually is."""
    try:
        message = claude.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": frame_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": f"""Look at this image. There's an object that YOLO detected as '{yolo_class}'.

What is this object ACTUALLY? Be specific and concise.
- If it's a drink: specify the brand/type (e.g., "Celsius Peach Vibe energy drink")
- If it's tech: specify what device (e.g., "iPhone with white case")
- If it's common item: be specific (e.g., "blue water bottle")

Respond with ONLY the object name, nothing else. Max 20 words."""
                        }
                    ],
                }
            ],
        )
        
        return message.content[0].text.strip()
    except Exception as e:
        print(f"❌ Claude API error: {e}")
        return yolo_class

def process_video(video_path):
    """Analyze video with YOLOv8 + Claude identification."""
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print(f"❌ Could not open video: {video_path}")
        return
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    print(f"🎬 Video loaded: {width}x{height} @ {fps} FPS ({total_frames} frames)")
    print(f"⏱️  Duration: {total_frames / fps:.2f}s\n")
    
    print("🟢 LAYER 1: YOLOv8 Detection (every frame)")
    print("🟡 LAYER 2: Claude Validation (confirms what was picked up)\n")
    print("Controls: SPACE=pause, Q=quit\n")
    
    tracker = ObjectTracker(history_frames=DETECTION_HISTORY_FRAMES)
    frame_num = 0
    paused = False
    
    output_dir = Path("/Users/ananyaj/atlas/detection_results")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Layer 1: YOLOv8 Detection
            detections = detect_objects_yolov8(frame)
            frame_base64 = frame_to_base64(frame)
            
            # Update tracker
            tracker.update(detections, frame_num, frame_base64)
        
        # Draw on frame
        frame_display = tracker.draw(frame.copy())
        
        # Add info overlay
        info_text = f"Frame: {frame_num}/{total_frames} | Tracked: {len(tracker.objects)} | Disappeared: {len(tracker.disappeared_objects)}"
        cv2.putText(frame_display, info_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Display
        cv2.imshow("🎥 YOLOv8 + Claude Detection", frame_display)
        
        # Keyboard controls
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('q'):
            print("\n✓ Exiting...")
            break
        elif key == ord(' '):
            paused = not paused
            print(f"{'▶️ Resumed' if not paused else '⏸️ Paused'}")
        
        if not paused:
            frame_num += 1
    
    cap.release()
    cv2.destroyAllWindows()
    
    # Layer 2: Claude identifies disappeared objects
    print("\n" + "="*70)
    print("🟡 LAYER 2: CLAUDE IDENTIFICATION")
    print("="*70)
    print(f"Analyzing {len(tracker.disappeared_objects)} disappeared objects...\n")
    
    for i, obj in enumerate(tracker.disappeared_objects):
        if obj['first_frame_data']:
            print(f"[{i+1}/{len(tracker.disappeared_objects)}] Object #{obj['id']}: ", end="", flush=True)
            print(f"YOLO says '{obj['yolo_class']}' → ", end="", flush=True)
            
            # Get Claude's identification
            claude_id = identify_object_with_claude(obj['first_frame_data'], obj['yolo_class'])
            obj['claude_class'] = claude_id
            
            print(f"Claude says '{claude_id}' ✓")
    
    # Summary
    print("\n" + "="*70)
    print("🎯 FINAL REPORT: PICKED UP/DISAPPEARED ITEMS")
    print("="*70)
    print(f"✓ Frames processed: {frame_num}")
    print(f"✓ Objects disappeared: {len(tracker.disappeared_objects)}\n")
    
    if tracker.disappeared_objects:
        print("📦 SUSPICIOUS ITEMS (with Claude identification):")
        print("-" * 70)
        for obj in sorted(tracker.disappeared_objects, key=lambda x: x['last_frame']):
            duration = (obj['last_frame'] - obj['first_frame']) / fps
            print(f"  ID {obj['id']:2d}: {obj['claude_class']:40s} | "
                  f"Frames {obj['first_frame']:3d}-{obj['last_frame']:3d} ({duration:.2f}s)")
    
    # Save report
    import json
    report = {
        'video': str(video_path),
        'total_frames': total_frames,
        'fps': fps,
        'duration': total_frames / fps,
        'disappeared_objects': [
            {
                'id': obj['id'],
                'yolo_detection': obj['yolo_class'],
                'claude_identification': obj['claude_class'],
                'first_frame': obj['first_frame'],
                'last_frame': obj['last_frame'],
                'duration_seconds': (obj['last_frame'] - obj['first_frame']) / fps,
                'frames_seen': obj['frames_seen']
            }
            for obj in tracker.disappeared_objects
        ]
    }
    
    report_path = output_dir / "detection_report_with_claude.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n✅ Report saved to: {report_path}")

if __name__ == "__main__":
    process_video(VIDEO_PATH)
