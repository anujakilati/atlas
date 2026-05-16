import os
import cv2
import json
import base64
from pathlib import Path
from collections import defaultdict
from datetime import timedelta
import time
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()
load_dotenv("/Users/ananyaj/.env")
load_dotenv("/Users/ananyaj/atlas/.env")

# Initialize NVIDIA Nemotron client
client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.getenv("NVIDIA_API_KEY")
)

# Configuration
VIDEO_PATH = "/Users/ananyaj/atlas/atlas-app/video1.MOV"
OUTPUT_DIR = "/Users/ananyaj/atlas/analysis_results"
FRAME_INTERVAL = 10  # Analyze every Nth frame to reduce API calls
MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"

# Create output directory
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_video_properties(video_path):
    """Get video properties like FPS and total frames."""
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return fps, total_frames, width, height

def extract_frame(video_path, frame_num):
    """Extract a specific frame from video and return as base64."""
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        return None
    
    # Encode to JPEG
    _, buffer = cv2.imencode('.jpg', frame)
    frame_base64 = base64.b64encode(buffer).decode('utf-8')
    return frame_base64

def extract_json_from_response(text):
    """Extract JSON object from response that may contain extra text."""
    if not text:
        return None
    
    # Find first {
    start_idx = text.find('{')
    if start_idx == -1:
        return None
    
    # Count braces to find matching }
    brace_count = 0
    in_string = False
    escape_next = False
    
    for i in range(start_idx, len(text)):
        char = text[i]
        
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        
        if in_string:
            continue
        
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                return text[start_idx:i+1]
    
    return None

def analyze_frame_with_nemotron(frame_base64, frame_num, timestamp, max_retries=3):
    """Use NVIDIA Nemotron Nano Omni to detect and describe objects in a frame."""
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{frame_base64}"
                                }
                            },
                            {
                                "type": "text",
                                "text": """Analyze this video frame and identify ALL visible objects/items in the scene.

For each object, provide:
1. Object name/description
2. Location in frame (top-left, center, bottom-right, etc.)
3. Approximate size (small, medium, large)
4. Any distinctive features

Format your response as ONLY a JSON object with an "objects" array:
{
  "objects": [
    {
      "name": "object name",
      "location": "position in frame",
      "size": "small/medium/large",
      "features": "distinctive features"
    }
  ],
  "summary": "brief summary of scene"
}

Return ONLY the JSON, no markdown formatting or extra text."""
                            }
                        ]
                    }
                ],
                temperature=0.6,
                max_tokens=1024,
            )
            
            # Parse response
            content = response.choices[0].message.content
            
            if not content:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                raise Exception("Model returned empty content after retries")
            
            # Extract JSON from response (may contain extra text)
            json_str = extract_json_from_response(content)
            if not json_str:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                raise Exception("Could not extract JSON from response after retries")
            
            data = json.loads(json_str)
            return {
                "frame_num": frame_num,
                "timestamp": timestamp,
                "objects": data.get("objects", []),
                "summary": data.get("summary", "")
            }
        except json.JSONDecodeError as e:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            print(f"  ⚠️  Failed to parse JSON response for frame {frame_num}: {e}")
            return {
                "frame_num": frame_num,
                "timestamp": timestamp,
                "objects": [],
                "summary": "Failed to analyze frame"
            }
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            print(f"  ❌ Error analyzing frame {frame_num}: {e}")
            return {
                "frame_num": frame_num,
                "timestamp": timestamp,
                "objects": [],
                "summary": f"Error: {str(e)}"
            }

def frame_num_to_timestamp(frame_num, fps):
    """Convert frame number to timestamp."""
    seconds = frame_num / fps
    return str(timedelta(seconds=int(seconds)))

def analyze_video(video_path):
    """Main function to analyze video for object tracking."""
    print(f"🎬 Analyzing video: {video_path}")
    
    # Get video properties
    fps, total_frames, width, height = get_video_properties(video_path)
    print(f"📊 Video properties: {total_frames} frames @ {fps} FPS ({width}x{height})")
    print(f"⏱️  Duration: {frame_num_to_timestamp(total_frames, fps)}")
    print(f"🔍 Analyzing every {FRAME_INTERVAL} frames...\n")
    
    # Extract and analyze frames
    frame_analyses = []
    frames_to_analyze = range(0, total_frames, FRAME_INTERVAL)
    
    for i, frame_num in enumerate(frames_to_analyze):
        print(f"Processing frame {i+1}/{len(list(frames_to_analyze))} (frame #{frame_num})...", end=" ", flush=True)
        
        timestamp = frame_num_to_timestamp(frame_num, fps)
        frame_base64 = extract_frame(video_path, frame_num)
        
        if frame_base64:
            analysis = analyze_frame_with_nemotron(frame_base64, frame_num, timestamp)
            frame_analyses.append(analysis)
            print(f"✓ Found {len(analysis['objects'])} objects")
            # Add delay between API calls
            time.sleep(0.5)
        else:
            print("❌ Failed to extract frame")
    
    return frame_analyses, fps, total_frames

def track_object_disappearances(frame_analyses):
    """Track which objects appear and disappear across frames."""
    print("\n" + "="*60)
    print("📍 OBJECT TRACKING ANALYSIS")
    print("="*60 + "\n")
    
    # Build object presence timeline
    object_timeline = defaultdict(list)
    
    for frame_data in frame_analyses:
        frame_num = frame_data["frame_num"]
        timestamp = frame_data["timestamp"]
        objects = frame_data["objects"]
        
        # Create a normalized object set for this frame
        for obj in objects:
            obj_name = obj["name"].lower().strip()
            object_timeline[obj_name].append({
                "frame": frame_num,
                "timestamp": timestamp,
                "location": obj.get("location", "unknown"),
                "size": obj.get("size", "unknown")
            })
    
    # Analyze disappearances (picked up items)
    disappeared_objects = []
    
    for obj_name, appearances in object_timeline.items():
        # Sort by frame number
        appearances.sort(key=lambda x: x["frame"])
        
        # Check if object disappeared (last frame is not the last analyzed frame)
        if len(appearances) > 1:
            # Object was present in multiple frames
            last_frame_appearance = appearances[-1]["frame"]
            first_frame_appearance = appearances[0]["frame"]
            
            # Check if there's a gap (disappeared)
            if len(frame_analyses) > 0:
                latest_frame = frame_analyses[-1]["frame_num"]
                if last_frame_appearance < latest_frame:
                    # Object disappeared
                    time_present_frames = last_frame_appearance - first_frame_appearance
                    disappeared_objects.append({
                        "object": obj_name,
                        "first_seen_frame": first_frame_appearance,
                        "first_seen_time": appearances[0]["timestamp"],
                        "last_seen_frame": last_frame_appearance,
                        "last_seen_time": appearances[-1]["timestamp"],
                        "frames_present": len(appearances),
                        "status": "✓ PICKED UP AND REMOVED",
                        "locations": [a["location"] for a in appearances]
                    })
    
    return disappeared_objects, object_timeline

def generate_report(frame_analyses, disappeared_objects, object_timeline, fps, total_frames):
    """Generate a comprehensive analysis report."""
    report = {
        "video_analysis": {
            "total_frames": total_frames,
            "fps": fps,
            "duration": frame_num_to_timestamp(total_frames, fps),
            "frames_analyzed": len(frame_analyses)
        },
        "objects_detected": len(object_timeline),
        "objects_that_disappeared": disappeared_objects,
        "frame_by_frame_analysis": frame_analyses,
        "object_timeline": {obj: appearances for obj, appearances in object_timeline.items()}
    }
    
    return report

def main():
    """Main execution."""
    if not os.path.exists(VIDEO_PATH):
        print(f"❌ Video not found: {VIDEO_PATH}")
        return
    
    # Analyze video
    frame_analyses, fps, total_frames = analyze_video(VIDEO_PATH)
    
    # Track disappearances
    disappeared_objects, object_timeline = track_object_disappearances(frame_analyses)
    
    # Generate report
    report = generate_report(frame_analyses, disappeared_objects, object_timeline, fps, total_frames)
    
    # Print summary
    print("\n" + "="*60)
    print("🎯 SUMMARY")
    print("="*60)
    print(f"Total objects detected: {len(object_timeline)}")
    print(f"Objects that were picked up: {len(disappeared_objects)}\n")
    
    if disappeared_objects:
        print("📦 PICKED UP ITEMS (Missing from later frames):")
        print("-" * 60)
        for item in disappeared_objects:
            print(f"\n✓ {item['object'].upper()}")
            print(f"  First seen: Frame {item['first_seen_frame']} ({item['first_seen_time']})")
            print(f"  Last seen:  Frame {item['last_seen_frame']} ({item['last_seen_time']})")
            print(f"  Appeared in {item['frames_present']} frames")
            print(f"  Locations tracked: {', '.join(set(item['locations']))}")
    else:
        print("✓ No objects were picked up (all objects remained in scene)")
    
    # Save detailed report
    report_path = os.path.join(OUTPUT_DIR, "video_analysis_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n💾 Detailed report saved to: {report_path}")
    
    # Save summary to text file
    summary_path = os.path.join(OUTPUT_DIR, "analysis_summary.txt")
    with open(summary_path, "w") as f:
        f.write("VIDEO OBJECT TRACKING ANALYSIS\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Video: {VIDEO_PATH}\n")
        f.write(f"Duration: {frame_num_to_timestamp(total_frames, fps)}\n")
        f.write(f"Total frames: {total_frames}\n")
        f.write(f"Frames analyzed: {len(frame_analyses)}\n\n")
        f.write(f"Total objects detected: {len(object_timeline)}\n")
        f.write(f"Objects picked up: {len(disappeared_objects)}\n\n")
        
        if disappeared_objects:
            f.write("PICKED UP ITEMS:\n")
            f.write("-" * 60 + "\n")
            for item in disappeared_objects:
                f.write(f"\n{item['object'].upper()}\n")
                f.write(f"  First seen: Frame {item['first_seen_frame']} ({item['first_seen_time']})\n")
                f.write(f"  Last seen:  Frame {item['last_seen_frame']} ({item['last_seen_time']})\n")
                f.write(f"  Appeared in {item['frames_present']} frames\n")
    
    print(f"📄 Summary saved to: {summary_path}")

if __name__ == "__main__":
    main()
