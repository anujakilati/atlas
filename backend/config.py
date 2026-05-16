import os
from pathlib import Path
import yaml

BASE = Path(__file__).resolve().parent.parent
ENV = os.environ

def load_config():
    cfg_file = BASE / "config" / "config.yaml"
    cfg = {}
    if cfg_file.exists():
        cfg = yaml.safe_load(cfg_file.read_text())
    # override with env
    cfg.setdefault("storage", {})
    cfg["storage"]["frames_dir"] = os.getenv("STORAGE_DIR", cfg["storage"].get("frames_dir", "./storage/frames"))
    cfg["storage"]["clips_dir"] = cfg["storage"].get("clips_dir", "./storage/clips")
    cfg["storage"]["db_path"] = os.getenv("DB_PATH", cfg["storage"].get("db_path", "./data/events.db"))
    cfg["vlm"] = cfg.get("vlm", {})
    cfg["vlm"]["endpoint"] = os.getenv("NEMOTRON_URL", cfg["vlm"].get("endpoint"))
    cfg["action_agent"] = {
        "security_webhook_url": os.getenv("SECURITY_WEBHOOK_URL", ""),
        "nemoclaw_enabled": os.getenv("NEMOCLAW_ENABLED", "1") != "0",
    }
    return cfg

CONFIG = load_config()
