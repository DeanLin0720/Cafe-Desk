"""依序做幾杯飲品並在各階段截圖

    python tools/run_drinks.py <輸出資料夾> <機器 key> <飲品,飲品,...> [full]
    例：python tools/run_drinks.py out lever latte,mocha,affogato
"""
import sys, os, json, time, traceback
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

out, machine, drinks = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
full = len(sys.argv) > 4 and sys.argv[4] == "full"
os.environ.update(QT_QPA_PLATFORM="offscreen", CAFE_DESK_NO_AUDIO="1")
sys.path.insert(0, _ROOT)
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPainter, QImage, QLinearGradient, QColor
from PySide6.QtCore import QTimer
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
from cafe_desk import paths, desk
paths.CONFIG_PATH = f"{out}/cfg_{machine}.json"
json.dump({"x": 0, "y": 0, "speed": 4.0, "light_mode": "day", "machine": machine, "pf_used": True}, open(paths.CONFIG_PATH, "w"))
w = desk.CafeDesk(); w.show_window(); w.boiler.temp = w.params.temp; w.warming = False
def snap(tag):
    pm = w.host.grab(); img = QImage(pm.size(), QImage.Format_ARGB32)
    p = QPainter(img); g = QLinearGradient(0, 0, img.width(), img.height())
    g.setColorAt(0, QColor("#3d6b8f")); g.setColorAt(1, QColor("#9fb7a0")); p.fillRect(img.rect(), g); p.drawPixmap(0, 0, pm); p.end()
    img.save(f"{out}/{machine}_{tag}.png")
state = {"i": -1, "last": None, "mid": set(), "t0": time.time()}
def next_drink():
    state["i"] += 1
    if state["i"] >= len(drinks):
        app.quit(); return
    d = drinks[state["i"]]
    w.start_session(d, full)
    state["last"] = None; state["mid"] = set(); state["t0"] = time.time()
def poll():
    try:
        d = drinks[state["i"]]
        ss = w.session
        if ss is None:
            if not state.get("done_snapped"):
                state["done_snapped"] = True
                w.hover, w.hover_since = True, time.perf_counter() - 2
                QTimer.singleShot(900, lambda: (snap(f"{d}_9done"), setattr(w, "hover", False), state.pop("done_snapped"), next_drink()))
            QTimer.singleShot(30, poll); return
        name = ss.stage_name
        st = ss.stage
        key = f"{d}_{ss.i}_{name}"
        frac = None
        if name == "pour":
            frac = st.poured / max(1, st.grams) if getattr(st, "phase", "") == "pour" else None
        elif name == "steam":
            frac = (st.t / st.total) if getattr(st, "phase", "") == "run" else None
        elif name == "brew" and w.shot:
            frac = w.shot.progress
        elif name in ("whip", "cocoa", "caramel"):
            frac = ss.tool["k"] if ss.tool else None
        elif name == "scoop":
            frac = 0.7 if st.phase == "exit" else None
        elif name == "ice":
            frac = 0.5 if len(w.ice) >= 3 else None
        elif name == "prep" and w.workflow:
            frac = 0.5 if w.workflow.name == "grind" else None
        if frac is not None and frac >= 0.6 and key not in state["mid"]:
            state["mid"].add(key)
            snap(f"{d}_{ss.i}{name}")
            print("snap", key, round(frac, 2), ss.status(), flush=True)
        if time.time() - state["t0"] > 150:
            print("TIMEOUT", key); app.quit(); return
    except Exception:
        traceback.print_exc(); app.quit(); return
    QTimer.singleShot(30, poll)
QTimer.singleShot(200, next_drink)
QTimer.singleShot(260, poll)
app.exec()
r = w.result
print("final result:", r.drink if r else None, round(r.score) if r else None, r.comment if r else None)
