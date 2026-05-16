"""
IMPROVED FREE CCTV Detection - Focus on DISAPPEARANCES
Shows what items were there, then disappeared (picked up)
With screenshot evidence and clear activity log
"""

import cv2
import numpy as np
from collections import defaultdict, deque
from pathlib import Path
from ultralytics import YOLO
import json

VIDEO_PATH = "/Users/ananyaj/atlas/atlas-app/video1.MOV"
CONFIDENCE_THRESHOLD = 0.5

print("🟢 Loading YOLOv8...")
model = YOLO('yolov8n.pt')
print("✓ Ready\n")

class SuspiciousActivityTracker:
    def __init__(self):
        self.objects = {}  # {obj_id: object_data}
        self.disappeared = {}
        self.next_id = 0
        self.activities = []  # List of suspicious activities
        self.frame_snapshots = {}  # {obj_id: {'first': frame, 'last': frame}}
        
    def register(self, center, class_name, confidence, box, frame):
        self.objects[self.next_id] = {
            'center': center,
            'class': class_name,
            'confidence': confidence,
            'box': box,
            'first_frame': None,
            'last_frame': None,
            'frames_seen': 0,
            'first_frame_image': frame.copy()
        }
        self.disappeared[self.next_id] = 0
        self.next_id += 1
        
    def deregister(self, obj_id, current_frame, frame):
        if obj_id in self.objects:
            obj = self.objects[obj_id]
            if obj['frames_seen'] > 3:  # Only care if tracked for multiple frames
                # This item DISAPPEARED
                activity = {
                    'type': 'ITEM_PICKED_UP',
                    'object_id': obj_id,
                    'yolo_class': obj['class'],
                    'confidence': obj['confidence'],
                    'box': obj['box'],
                    'first_seen_frame': obj['first_frame'],
                    'last_seen_frame': current_frame,
                    'frames_tracked': obj['frames_seen'],
                    'first_image': obj['first_frame_image'],
                    'last_image': frame.copy()
                }
                self.activities.append(activity)
            
            del self.objects[obj_id]
            del self.disappeared[obj_id]
            
    def update(self, detections, current_frame, frame):
        if len(detections) == 0:
            for obj_id in list(self.disappeared.keys()):
                self.disappeared[obj_id] += 1
                if self.disappeared[obj_id] > 15:
                    self.deregister(obj_id, current_frame, frame)
            return
        
        for obj_id in list(self.objects.keys()):
            self.disappeared[obj_id] += 1
            if self.disappeared[obj_id] > 15:
                self.deregister(obj_id, current_frame, frame)
        
        for center, class_name, confidence, box in detections:
            matched = False
            best_distance = float('inf')
            best_id = None
            
            # Match to nearest existing object
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
                self.objects[best_id]['frames_seen'] += 1
                self.objects[best_id]['last_frame'] = current_frame
                self.disappeared[best_id] = 0
            else:
                self.register(center, class_name, confidence, box, frame)
                self.objects[self.next_id - 1]['first_frame'] = current_frame
    
    def draw(self, frame):
        for obj_id, obj in self.objects.items():
            center = obj['center']
            box = obj['box']
            confidence = obj['confidence']
            
            if confidence > 0.8:
                color = (0, 255, 0)
            elif confidence > 0.6:
                color = (0, 255, 255)
            else:
                color = (0, 0, 255)
            
            # Circle marker
            cv2.circle(frame, center, 20, color, 3)
            cv2.circle(frame, center, 10, color, -1)
            
            # Bounding box
            x1, y1, x2, y2 = box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
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

def save_activity_screenshots(activity, output_dir, idx):
    """Save before/after screenshots of suspicious activity."""
    first_img = activity['first_image']
    last_img = activity['last_image']
    
    # Add text overlays
    cv2.putText(first_img, "ITEM PRESENT", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 2)
    cv2.putText(last_img, "ITEM DISAPPEARED (PICKED UP)", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 2)
    
    # Draw boxes
    x1, y1, x2, y2 = activity['box']
    cv2.rectangle(first_img, (x1, y1), (x2, y2), (0, 255, 0), 3)
    cv2.rectangle(last_img, (x1, y1), (x2, y2), (0, 0, 255), 3)
    
    first_path = output_dir / f"activity_{idx}_01_PRESENT.png"
    last_path = output_dir / f"activity_{idx}_02_DISAPPEARED.png"
    
    cv2.imwrite(str(first_path), first_img)
    cv2.imwrite(str(last_path), last_img)
    
    return str(first_path), str(last_path)

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
    print(f"⏱️  Duration: {total_frames / fps:.2f}s")
    print(f"💰 Cost: $0.00 FREE\n")
    print("Tracking objects and detecting disappearances...\n")
    
    tracker = SuspiciousActivityTracker()
    frame_num = 0
    
    output_dir = Path("/Users/ananyaj/atlas/detection_results")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        detections = detect_objects_yolov8(frame)
        tracker.update(detections, frame_num, frame)
        
        frame_display = tracker.draw(frame.copy())
        info = f"Frame {frame_num}/{total_frames} | Tracking: {len(tracker.objects)} | Suspicious: {len(tracker.activities)}"
        cv2.putText(frame_display, info, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        cv2.imshow("Analyzing... (Press Q to stop)", frame_display)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        
        frame_num += 1
    
    cap.release()
    cv2.destroyAllWindows()
    
    # Generate report
    print("\n" + "="*70)
    print("🚨 SUSPICIOUS ACTIVITY REPORT")
    print("="*70)
    print(f"Total activities detected: {len(tracker.activities)}\n")
    
    if tracker.activities:
        for idx, activity in enumerate(tracker.activities, 1):
            duration = (activity['last_seen_frame'] - activity['first_seen_frame']) / fps
            print(f"[ACTIVITY {idx}] ITEM PICKED UP")
            print(f"  Object detected as: {activity['yolo_class']}")
            print(f"  Confidence: {activity['confidence']:.2f}")
            print(f"  Present in frames: {activity['first_seen_frame']} to {activity['last_seen_frame']}")
            print(f"  Duration visible: {duration:.2f} seconds")
            print(f"  Frames tracked: {activity['frames_tracked']}")
            
            # Save before/after screenshot
            first_path, last_path = save_activity_screenshots(activity, output_dir, idx)
            print(f"  Screenshots saved:")
            print(f"    - Before: {first_path}")
            print(f"    - After: {last_path}")
            print()
    
    # Save JSON report
    report = {
        'video': str(video_path),
        'cost': '$0.00 - 100% FREE',
        'total_frames': total_frames,
        'fps': fps,
        'duration_seconds': total_frames / fps,
        'suspicious_activities': len(tracker.activities),
        'activities': [
            {
                'activity_type': 'ITEM_PICKED_UP',
                'detected_as': act['yolo_class'],
                'confidence': act['confidence'],
                'first_seen_frame': act['first_seen_frame'],
                'last_seen_frame': act['last_seen_frame'],
                'duration_seconds': (act['last_seen_frame'] - act['first_seen_frame']) / fps,
                'frames_tracked': act['frames_tracked'],
                'box_coordinates': act['box']
            }
            for act in tracker.activities
        ]
    }
    
    report_path = output_dir / "SUSPICIOUS_ACTIVITY_REPORT.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    # Generate HTML report
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>CCTV Suspicious Activity Report</title>
    <style>
        body {{ font-family: Arial; margin: 20px; background: #f0f0f0; }}
        .header {{ background: #d32f2f; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
        .summary {{ background: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
        .activity {{ background: white; padding: 20px; margin-bottom: 20px; border-left: 4px solid #d32f2f; border-radius: 5px; }}
        .activity h3 {{ color: #d32f2f; margin-top: 0; }}
        .images {{ display: flex; gap: 20px; margin: 20px 0; }}
        .images img {{ max-width: 45%; height: auto; border: 2px solid #ddd; border-radius: 5px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }}
        .stat-box {{ background: #f5f5f5; padding: 15px; border-radius: 5px; text-align: center; }}
        .stat-box h4 {{ margin: 0; color: #d32f2f; }}
        .stat-box p {{ margin: 10px 0 0 0; font-size: 24px; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚨 CCTV Suspicious Activity Report</h1>
        <p>Items Detected as Picked Up</p>
    </div>
    
    <div class="summary">
        <h2>Summary</h2>
        <div class="stats">
            <div class="stat-box">
                <h4>Total Suspicious Activities</h4>
                <p>{len(tracker.activities)}</p>
            </div>
            <div class="stat-box">
                <h4>Video Duration</h4>
                <p>{total_frames / fps:.2f}s</p>
            </div>
            <div class="stat-box">
                <h4>Cost</h4>
                <p>$0.00</p>
            </div>
        </div>
    </div>
    
    {''.join([f'''
    <div class="activity">
        <h3>⚠️ Activity #{i}: Item Picked Up</h3>
        <p><strong>Detected as:</strong> {act['yolo_class']}</p>
        <p><strong>Confidence:</strong> {act['confidence']:.2%}</p>
        <p><strong>Time Frame:</strong> Frame {act['first_seen_frame']} → {act['last_seen_frame']} ({(act['last_seen_frame'] - act['first_seen_frame']) / fps:.2f}s)</p>
        <p><strong>Tracked for:</strong> {act['frames_tracked']} frames</p>
        <p><strong>Activity:</strong> Item was present, then disappeared (likely picked up)</p>
        <div class="images">
            <div>
                <h4>Before (Item Present)</h4>
                <img src="activity_{i}_01_PRESENT.png" alt="Item present">
            </div>
            <div>
                <h4>After (Item Disappeared)</h4>
                <img src="activity_{i}_02_DISAPPEARED.png" alt="Item disappeared">
            </div>
        </div>
    </div>
    ''' for i, act in enumerate(tracker.activities, 1)])}
    
    <div class="summary" style="margin-top: 30px;">
        <p style="color: #666; font-size: 12px;">Report generated at {Path(video_path).name} | 100% FREE Analysis</p>
    </div>
</body>
</html>
"""
    
    html_path = output_dir / "SUSPICIOUS_ACTIVITY_REPORT.html"
    with open(html_path, 'w') as f:
        f.write(html_content)
    
    print("="*70)
    print(f"✅ Report saved to:")
    print(f"  📊 JSON: {report_path}")
    print(f"  🌐 HTML: {html_path}")
    print(f"  📸 Screenshots in: {output_dir}")
    print("="*70)

if __name__ == "__main__":
    process_video(VIDEO_PATH)
