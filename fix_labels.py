"""
Simple tool to correct object labels in the JSON report
Change what YOLOv8 incorrectly identified
"""

import json
from pathlib import Path

report_path = Path("/Users/ananyaj/atlas/detection_results/SUSPICIOUS_ACTIVITY_REPORT.json")

if not report_path.exists():
    print("❌ No report found. Run video_detector_suspicious_activity.py first.")
    exit()

# Load report
with open(report_path, 'r') as f:
    report = json.load(f)

print("\n" + "="*70)
print("🏷️  OBJECT LABEL CORRECTOR")
print("="*70)
print(f"Activities found: {len(report['activities'])}\n")

# Show current labels
for i, activity in enumerate(report['activities'], 1):
    print(f"Activity {i}:")
    print(f"  Current label: '{activity['detected_as']}'")
    print(f"  Duration: {activity['duration_seconds']:.2f}s")
    print(f"  Frames tracked: {activity['frames_tracked']}")
    
    # Ask user for correction
    correct_label = input(f"  Enter correct label (or press Enter to keep '{activity['detected_as']}'): ").strip()
    
    if correct_label:
        activity['detected_as'] = correct_label
        print(f"  ✓ Updated to: '{correct_label}'")
    print()

# Save corrected report
with open(report_path, 'w') as f:
    json.dump(report, f, indent=2)

print("="*70)
print("✅ Labels updated!")
print(f"📄 Report saved: {report_path}")
print("="*70)

# Show updated content
print("\n📋 Updated activities:")
for i, activity in enumerate(report['activities'], 1):
    print(f"  {i}. {activity['detected_as']} (picked up at frame {activity['first_seen_frame']})")
