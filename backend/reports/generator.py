import json
from typing import List, Dict, Any
from backend.storage import db
from backend.config import CONFIG

def generate_report(limit: int = 100) -> Dict[str, Any]:
    rows = db.list_events(CONFIG['storage']['db_path'], limit=limit)
    events = []
    for r in rows:
        events.append({"id": r[0], "ts": r[1], "label": r[2], "score": r[3], "bbox": r[4], "frame": r[5], "clip": r[6], "meta": r[7]})
    timeline = sorted(events, key=lambda x: x['ts'])
    summary = {"total_events": len(events), "by_label": {}}
    for e in events:
        summary['by_label'].setdefault(e['label'], 0)
        summary['by_label'][e['label']] += 1
    report = {"timeline": timeline, "summary": summary}
    return report

def report_markdown(report: Dict[str, Any]) -> str:
    md = "# Incident Report\n\n"
    md += f"**Total events**: {report['summary']['total_events']}\n\n"
    md += "## Timeline\n"
    for e in report['timeline']:
        md += f"- {e['ts']}: {e['label']} (score={e['score']})\n"
    return md
