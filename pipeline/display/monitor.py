import textwrap
import time
import cv2
import numpy as np
from pipeline.state_machine.incident_sm import State
from pipeline.roi_logic.zones import ProtectedZone
from pipeline.tracking.person_tracker import Track

# ── palette ───────────────────────────────────────────────────────────────────
C = {
    "bg":      (14, 14, 14),
    "border":  (42, 42, 42),
    "green":   (0, 210, 100),
    "amber":   (0, 165, 255),
    "red":     (40, 40, 220),
    "grey":    (130, 130, 130),
    "white":   (215, 215, 215),
    "cyan":    (200, 200, 0),
    "divider": (32, 32, 32),
    "bar_bg":  (38, 38, 38),
}

STATE_COLOR = {
    State.IDLE:                C["grey"],
    State.APPROACH:            C["cyan"],
    State.INTERACTION:         C["amber"],
    State.SUSPICIOUS_ACTIVITY: C["red"],
    State.ESCALATED:           C["red"],
    State.INCIDENT_CONFIRMED:  C["red"],
    State.RESOLVED:            C["green"],
}

FONT   = cv2.FONT_HERSHEY_SIMPLEX
VIDEO_W, VIDEO_H = 960, 540
PANEL_W          = 680
DISPLAY_W        = VIDEO_W + PANEL_W


def _put(img, text, x, y, color=None, scale=0.42, bold=False):
    cv2.putText(img, str(text), (x, y), FONT, scale,
                color or C["white"], 2 if bold else 1, cv2.LINE_AA)


def _wrap(text: str, width: int = 56) -> list[str]:
    lines = []
    for para in str(text).split("\n"):
        lines.extend(textwrap.wrap(para.strip(), width) or [""])
    return lines


def _bar(img, x, y, w, h, value: float):
    cv2.rectangle(img, (x, y), (x+w, y+h), C["bar_bg"], -1)
    fill  = int(w * min(value, 1.0))
    color = C["green"] if value < 0.4 else C["amber"] if value < 0.7 else C["red"]
    if fill > 0:
        cv2.rectangle(img, (x, y), (x+fill, y+h), color, -1)
    cv2.rectangle(img, (x, y), (x+w, y+h), C["border"], 1)
    _put(img, f"{value:.0%}", x+w+8, y+h-1, color, 0.38)


class SurveillanceMonitor:
    def __init__(self):
        self._last_incident = None
        self._analyzing = False
        self._last_analyzed = 0.0

    def set_analyzing(self, v: bool):
        self._analyzing = v

    def set_incident(self, report):
        self._last_incident = report
        self._analyzing     = False
        self._last_analyzed = time.time()

    # ── video panel ───────────────────────────────────────────────────────────

    def _draw_video(self, frame: np.ndarray, tracks: list[Track],
                    zone: ProtectedZone, state: State,
                    suspicion: float, frame_num: int, fps: float) -> np.ndarray:
        vis = frame.copy()

        # ROI
        roi_c = STATE_COLOR.get(state, C["cyan"])
        cv2.rectangle(vis, (zone.x1, zone.y1), (zone.x2, zone.y2), roi_c, 2)
        cv2.putText(vis, "PROTECTED ZONE", (zone.x1+6, zone.y1-8),
                    FONT, 0.48, roi_c, 1, cv2.LINE_AA)

        # Person tracks
        for t in tracks:
            x1,y1,x2,y2 = t.box
            cv2.rectangle(vis, (x1,y1), (x2,y2), C["cyan"], 2)
            cv2.putText(vis, f"P{t.id}", (x1, max(y1-6,0)),
                        FONT, 0.5, C["cyan"], 1, cv2.LINE_AA)
            path = list(t.path)
            for i in range(1, len(path)):
                cv2.line(vis, path[i-1], path[i], (0, int(180*i/len(path)), 200), 1)

        # HUD
        ts = frame_num / fps
        cv2.putText(vis, f"t={ts:.2f}s  f={frame_num:04d}", (12, 32),
                    FONT, 0.55, C["green"], 2, cv2.LINE_AA)
        cv2.putText(vis, state.name, (12, 60),
                    FONT, 0.48, STATE_COLOR.get(state, C["white"]), 1, cv2.LINE_AA)

        # Suspicion bar (right edge vertical)
        bh = int(VIDEO_H * suspicion)
        bc = C["green"] if suspicion < 0.4 else C["amber"] if suspicion < 0.7 else C["red"]
        cv2.rectangle(vis, (VIDEO_W-10, VIDEO_H-bh), (VIDEO_W-4, VIDEO_H), bc, -1)

        return cv2.resize(vis, (VIDEO_W, VIDEO_H))

    # ── telemetry panel ───────────────────────────────────────────────────────

    def _draw_panel(self, state: State, suspicion: float,
                    tracks: list[Track], dwell: float,
                    roi_change: float, frame_num: int, fps: float) -> np.ndarray:
        p  = np.full((VIDEO_H, PANEL_W, 3), C["bg"], dtype=np.uint8)
        x0 = 14
        y  = 22

        def line(text="", color=None, scale=0.42, bold=False):
            nonlocal y
            _put(p, text, x0, y, color, scale, bold)
            y += int(scale * 38 + 2)

        def div():
            nonlocal y
            cv2.line(p, (x0, y), (PANEL_W-x0, y), C["divider"], 1)
            y += 10

        line("ATLAS  SURVEILLANCE", C["green"], 0.58, bold=True)
        line(f"t={frame_num/fps:.2f}s   frame {frame_num:04d}", C["grey"], 0.40)
        div()

        # Live state
        line("LIVE  STATUS", C["grey"], 0.40, bold=True)
        y += 2
        sc = STATE_COLOR.get(state, C["white"])
        line(f"state      : {state.name}", sc, 0.44, bold=True)
        line(f"persons    : {len(tracks)}", C["white"], 0.42)
        if dwell > 0:
            line(f"dwell      : {dwell:.1f}s", C["amber"], 0.42)
        if roi_change > 0.02:
            line(f"ROI change : {roi_change:.1%}  ← object moved?",
                 C["red"] if roi_change > 0.06 else C["amber"], 0.42)
        y += 4
        line("suspicion", C["grey"], 0.38)
        _bar(p, x0, y, PANEL_W - x0*2 - 55, 14, suspicion)
        y += 26
        div()

        # Nemotron
        line("NEMOTRON  ANALYSIS", C["grey"], 0.40, bold=True)
        y += 3
        if self._analyzing:
            line("[ analyzing evidence... ]", C["amber"], 0.44)
        elif self._last_analyzed > 0:
            ago = time.time() - self._last_analyzed
            line(f"last analyzed: {ago:.0f}s ago", C["grey"], 0.38)
        else:
            line("waiting for trigger (suspicion ≥ 0.65)", C["grey"], 0.38)

        inc = self._last_incident
        if inc:
            y += 4
            rc = (C["red"] if inc.risk_level in ("high","critical")
                  else C["amber"] if inc.risk_level == "medium" else C["green"])
            ac = {"monitor": C["green"], "alert_operator": C["amber"],
                  "call_security": C["red"], "lock_down": C["red"]}.get(
                  inc.recommended_action, C["white"])

            line(f"{'INCIDENT CONFIRMED' if inc.incident_confirmed else 'not confirmed'}",
                 C["red"] if inc.incident_confirmed else C["green"], 0.50, bold=True)
            line(f"type       : {inc.incident_type}", C["white"], 0.42)
            line(f"confidence : {inc.confidence:.0%}   risk: {inc.risk_level.upper()}", rc, 0.42)
            y += 4
            line(f"ACTION: {inc.recommended_action.upper().replace('_',' ')}",
                 ac, 0.52, bold=True)
            y += 6
            div()
            line("SUMMARY", C["grey"], 0.38, bold=True)
            y += 2
            for ln in _wrap(inc.summary, 54):
                if y > VIDEO_H - 50:
                    break
                line(ln, C["white"], 0.40)
            y += 6
            notifs = inc.notifications or {}
            short = notifs.get("short", "")
            if short:
                div()
                line("NOTIFICATION", C["grey"], 0.38, bold=True)
                y += 2
                for ln in _wrap(short, 54):
                    if y > VIDEO_H - 20:
                        break
                    line(ln, C["amber"], 0.40)

        cv2.line(p, (0, 0), (0, VIDEO_H), C["border"], 2)
        return p

    # ── compose ───────────────────────────────────────────────────────────────

    def render(self, frame: np.ndarray, tracks: list[Track],
               zone: ProtectedZone, state: State,
               suspicion: float, dwell: float, roi_change: float,
               frame_num: int, fps: float) -> np.ndarray:
        vp = self._draw_video(frame, tracks, zone, state, suspicion, frame_num, fps)
        tp = self._draw_panel(state, suspicion, tracks, dwell, roi_change, frame_num, fps)
        return np.concatenate([vp, tp], axis=1)
