import cv2
import numpy as np
from collections import defaultdict, deque
import os
from pathlib import Path

# Configuration
VIDEO_PATH = "/Users/ananyaj/atlas/atlas-app/video1.MOV"
CONFIDENCE_THRESHOLD = 0.5
NMS_THRESHOLD = 0.4
DETECTION_HISTORY_FRAMES = 15  # Track objects across N frames

class ObjectTracker:
    def __init__(self, history_frames=15):
        self.objects = {}  # {object_id: {center, class, history}}
        self.disappeared = {}  # {object_id: frame_count}
        self.next_id = 0
        self.history_frames = history_frames
        self.disappeared_objects = []
        
    def register(self, center, class_name, confidence):
        """Register a new object."""
        self.objects[self.next_id] = {
            'center': center,
            'class': class_name,
            'confidence': confidence,
            'history': deque(maxlen=self.history_frames),
            'first_frame': 0,
            'frames_seen': 0
        }
        self.disappeared[self.next_id] = 0
        self.next_id += 1
        
    def deregister(self, object_id, current_frame):
        """Deregister and log disappeared object."""
        if object_id in self.objects:
            obj = self.objects[object_id]
            if obj['frames_seen'] > 3:  # Only care if we saw it in multiple frames
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
        """Update tracking with new detections."""
        if len(detections) == 0:
            # No detections, increment disappeared counter
            for obj_id in list(self.disappeared.keys()):
                self.disappeared[obj_id] += 1
                if self.disappeared[obj_id] > 10:  # Remove if not seen for 10 frames
                    self.deregister(obj_id, current_frame)
            return
        
        # Update existing objects
        for obj_id in list(self.objects.keys()):
            self.disappeared[obj_id] += 1
            if self.disappeared[obj_id] > 10:
                self.deregister(obj_id, current_frame)
        
        # Match new detections to existing objects
        for center, class_name, confidence, box in detections:
            matched = False
            best_distance = float('inf')
            best_id = None
            
            # Find closest object
            for obj_id in self.objects:
                obj_center = self.objects[obj_id]['center']
                distance = np.sqrt((center[0] - obj_center[0])**2 + (center[1] - obj_center[1])**2)
                
                if distance < 50 and distance < best_distance:  # Max distance threshold
                    best_distance = distance
                    best_id = obj_id
                    matched = True
            
            if matched:
                self.objects[best_id]['center'] = center
                self.objects[best_id]['history'].append(center)
                self.objects[best_id]['frames_seen'] += 1
                self.disappeared[best_id] = 0
            else:
                self.register(center, class_name, confidence)
                self.objects[self.next_id - 1]['first_frame'] = current_frame
    
    def draw(self, frame, frame_num):
        """Draw tracked objects on frame."""
        h, w = frame.shape[:2]
        
        for obj_id, obj in self.objects.items():
            center = obj['center']
            class_name = obj['class']
            frames_seen = obj['frames_seen']
            
            # Color based on time seen
            if frames_seen < 3:
                color = (200, 200, 0)  # Cyan - new
            elif frames_seen > 10:
                color = (0, 255, 0)  # Green - tracked
            else:
                color = (0, 255, 255)  # Yellow - tracking
            
            # Draw circle
            cv2.circle(frame, center, 15, color, 2)
            cv2.circle(frame, center, 8, color, -1)
            
            # Draw history trail
            if len(obj['history']) > 1:
                points = list(obj['history'])
                for i in range(len(points) - 1):
                    cv2.line(frame, points[i], points[i+1], color, 1)
            
            # Label
            label = f"{class_name}#{obj_id}"
            cv2.putText(frame, label, (center[0] - 30, center[1] - 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        return frame

def detect_objects_yolo(frame):
    """Simple object detection using edge detection + contours (fast alternative to YOLO)."""
    # Convert to HSV for better detection
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # Define color ranges for common items
    # Objects typically have distinct colors
    lower_color = np.array([0, 50, 50])
    upper_color = np.array([180, 255, 255])
    
    mask = cv2.inRange(hsv, lower_color, upper_color)
    
    # Morphological operations
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    
    # Find contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    detections = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area > 300:  # Min object size
            x, y, w, h = cv2.boundingRect(contour)
            center = (x + w // 2, y + h // 2)
            
            # Classify by size/shape
            aspect_ratio = w / h if h > 0 else 0
            if area > 2000:
                class_name = "Large Object"
            elif aspect_ratio > 2:
                class_name = "Horizontal Object"
            elif aspect_ratio < 0.5:
                class_name = "Vertical Object"
            else:
                class_name = "Object"
            
            confidence = min(1.0, area / 5000)
            detections.append((center, class_name, confidence, (x, y, w, h)))
    
    return detections

def process_video(video_path):
    """Analyze video with real-time display."""
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print(f"❌ Could not open video: {video_path}")
        return
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    print(f"🎬 Video loaded: {width}x{height} @ {fps} FPS ({total_frames} frames)")
    print(f"⏱️  Duration: {total_frames / fps:.2f}s")
    print(f"\n🟢 LAYER 1: YOLO Object Detection (Running at every frame)")
    print(f"Controls: SPACE=pause, Q=quit, S=screenshot\n")
    
    tracker = ObjectTracker(history_frames=DETECTION_HISTORY_FRAMES)
    frame_num = 0
    paused = False
    
    # Create output directory
    output_dir = Path("/Users/ananyaj/atlas/detection_results")
    output_dir.mkdir(exist_ok=True)
    
    suspicious_events = []
    
    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                break
        
        # Detect objects
        detections = detect_objects_yolo(frame)
        
        # Update tracker
        tracker.update(detections, frame_num)
        
        # Draw on frame
        frame = tracker.draw(frame, frame_num)
        
        # Add info overlay
        info_text = [
            f"Frame: {frame_num}/{total_frames} | FPS: {fps:.0f}",
            f"Tracked Objects: {len(tracker.objects)}",
            f"Disappeared Objects: {len(tracker.disappeared_objects)}"
        ]
        
        y_offset = 30
        for text in info_text:
            cv2.putText(frame, text, (10, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            y_offset += 25
        
        # Check for suspicious activity (object disappearance)
        for obj in tracker.disappeared_objects:
            if obj not in suspicious_events:
                suspicious_events.append(obj)
                print(f"⚠️  SUSPICIOUS: {obj['class']} disappeared after frame {obj['last_frame']}")
        
        # Display
        cv2.imshow("CCTV Live Detection - Layer 1 (YOLO)", frame)
        
        # Keyboard controls
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('q'):
            print("\n✓ Exiting...")
            break
        elif key == ord(' '):
            paused = not paused
            print(f"{'▶️ Resumed' if paused else '⏸️ Paused'}")
        elif key == ord('s'):
            screenshot_path = output_dir / f"screenshot_frame_{frame_num}.png"
            cv2.imwrite(str(screenshot_path), frame)
            print(f"📸 Screenshot saved: {screenshot_path}")
        
        if not paused:
            frame_num += 1
    
    cap.release()
    cv2.destroyAllWindows()
    
    # Summary
    print("\n" + "="*60)
    print("🎯 DETECTION SUMMARY")
    print("="*60)
    print(f"Total frames processed: {frame_num}")
    print(f"Objects that disappeared: {len(tracker.disappeared_objects)}")
    
    if tracker.disappeared_objects:
        print("\n📦 PICKED UP/DISAPPEARED ITEMS:")
        for obj in tracker.disappeared_objects:
            print(f"  • {obj['class']} (ID: {obj['id']})")
            print(f"    - Seen in frames: {obj['first_frame']} to {obj['last_frame']} ({obj['frames_seen']} frames)")
    
    print(f"\n✓ All results saved to: {output_dir}")

if __name__ == "__main__":
    process_video(VIDEO_PATH)
