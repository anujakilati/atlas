"""
COMPLETELY FREE CCTV Detection System
- YOLOv8: Free, local object detection
- No API calls, no charges
- Real-time video analysis with object tracking
"""

import cv2
import numpy as np
from collections import defaultdict, deque
from pathlib import Path
from ultralytics import YOLO
import json

# Configuration
VIDEO_PATH = "/Users/ananyaj/atlas/atlas-app/video1.MOV"
CONFIDENCE_THRESHOLD = 0.5
DETECTION_HISTORY_FRAMES = 15

print("🟢 Loading YOLOv8 (FREE - runs locally)...")
model = YOLO('yolov8n.pt')
print("✓ YOLOv8 ready\n")

class ObjectTracker:
    def __init__(self, history_frames=15):
        self.objects = {}
        self.disappeared = {}
        self.next_id = 0
        self.history_frames = history_frames
        self.disappeared_objects = []
        
    def register(self, center, class_name, confidence, box):
        self.objects[self.next_id] = {
            'center': center,
            'class': class_name,
            'confidence': confidence,
            'box': box,
            'history': deque(maxlen=self.history_frames),
            'first_frame': 0,
            'frames_seen': 0
        }
        self.disappeared[self.next_id] = 0
        self.next_id += 1
        
    def deregister(self, object_id, current_frame):
        if object_id in self.objects:
            obj = self.objects[object_id]
            if obj['frames_seen'] > 2:
                self.disappeared_objects.append({
                    'id': object_id,
                    'class': obj['class'],
                    'first_frame': obj['first_frame'],
                    'last_frame': current_frame,
                    'frames_seen': obj['frames_seen'],
                    'confidence': obj['confidence']
                })
            del self.objects[object_id]
            del self.disappeared[object_id]
            
    def update(self, detections, current_frame):
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
        
        for center, class_name, confidence, box in detections:
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
                self.disappeared[best_id] = 0
            else:
                self.register(center, class_name, confidence, box)
                self.objects[self.next_id - 1]['first_frame'] = current_frame
    
    def draw(self, frame):
        for obj_id, obj in self.objects.items():
            center = obj['center']
            class_name = obj['class']
            confidence = obj['confidence']
            box = obj['box']
            
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
            
            # Label with confidence
            label = f"{class_name[:15]} {confidence:.2f}"
            cv2.putText(frame, label, (center[0] - 50, center[1] - 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
            cv2.putText(frame, f"ID:{obj_id}", (center[0] - 50, center[1] + 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        
        return frame

def detect_objects_yolov8(frame):
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

def process_video(video_path):
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print(f"❌ Could not open video: {video_path}")
        return
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    print(f"🎬 Video: {width}x{height} @ {fps} FPS ({total_frames} frames)")
    print(f"⏱️  Duration: {total_frames / fps:.2f}s\n")
    print("💰 COST: $0.00 (100% FREE - YOLOv8 runs locally)\n")
    print("Controls: SPACE=pause, Q=quit, S=screenshot\n")
    
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
            
            detections = detect_objects_yolov8(frame)
            tracker.update(detections, frame_num)
        
        frame_display = tracker.draw(frame.copy())
        
        # Info overlay
        info_text = f"Frame: {frame_num}/{total_frames} | Tracked: {len(tracker.objects)} | Missing: {len(tracker.disappeared_objects)}"
        cv2.putText(frame_display, info_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame_display, "FREE - No API Charges", (10, 70),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        cv2.imshow("🎥 FREE CCTV Detection - YOLOv8 Only", frame_display)
        
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('q'):
            print("\n✓ Exiting...")
            break
        elif key == ord(' '):
            paused = not paused
            status = "▶️ Resumed" if not paused else "⏸️ Paused"
            print(status)
        elif key == ord('s'):
            screenshot_path = output_dir / f"screenshot_frame_{frame_num}.png"
            cv2.imwrite(str(screenshot_path), frame_display)
            print(f"📸 Saved: {screenshot_path}")
        
        if not paused:
            frame_num += 1
    
    cap.release()
    cv2.destroyAllWindows()
    
    # Summary
    print("\n" + "="*70)
    print("✅ FREE DETECTION COMPLETE (No charges incurred)")
    print("="*70)
    print(f"Frames processed: {frame_num}")
    print(f"Objects disappeared: {len(tracker.disappeared_objects)}\n")
    
    if tracker.disappeared_objects:
        print("📦 ITEMS THAT DISAPPEARED:")
        print("-" * 70)
        for obj in sorted(tracker.disappeared_objects, key=lambda x: x['last_frame']):
            duration = (obj['last_frame'] - obj['first_frame']) / fps
            print(f"  [{obj['id']:2d}] {obj['class']:20s} | "
                  f"Frames {obj['first_frame']:3d}-{obj['last_frame']:3d} ({duration:.2f}s) | "
                  f"Conf: {obj['confidence']:.2f}")
    
    # Save JSON report
    report = {
        'video': str(video_path),
        'cost': '$0.00 - 100% FREE',
        'tool': 'YOLOv8 (local)',
        'total_frames': total_frames,
        'fps': fps,
        'duration': total_frames / fps,
        'disappeared_objects': [
            {
                'id': obj['id'],
                'object': obj['class'],
                'first_frame': obj['first_frame'],
                'last_frame': obj['last_frame'],
                'duration_seconds': (obj['last_frame'] - obj['first_frame']) / fps,
                'frames_seen': obj['frames_seen'],
                'confidence': obj['confidence']
            }
            for obj in tracker.disappeared_objects
        ]
    }
    
    report_path = output_dir / "FREE_detection_report.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n💾 Report saved: {report_path}")
    print(f"📁 Results: {output_dir}")

if __name__ == "__main__":
    process_video(VIDEO_PATH)
