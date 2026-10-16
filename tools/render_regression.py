"""回歸測試：用固定狀態渲染畫面存成 PNG，比對新舊版本

    python tools/render_regression.py <專案根目錄> <標籤> <輸出資料夾>
    兩個版本各跑一次，再用 ImageMagick 比對：compare -metric AE old_idle.png new_idle.png null:（應為 0）
    建議設 CAFE_DESK_DATE=2026-08-01（沒有節日，避免狀態列節日圖示造成差異）
"""
import sys, os, json
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

root, tag, out = sys.argv[1], sys.argv[2], sys.argv[3]
os.environ.update(QT_QPA_PLATFORM="offscreen", CAFE_DESK_NO_AUDIO="1")
sys.path.insert(0, root)
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
try:
    from cafe_desk import paths, desk, model, workflow
except ImportError:
    from espresso_desk import paths, desk, model, workflow
paths.CONFIG_PATH = f"{out}/{tag}_cfg.json"
json.dump({"x": 0, "y": 0, "light_mode": "day"}, open(paths.CONFIG_PATH, "w"))
w = (getattr(desk, 'CafeDesk', None) or desk.EspressoDesk)(); w.show_window(); w.timer.stop()
w.boiler.temp = 93.0; w.warming = False; w.anim_t = 1.3; w.gauge = 8.4
def prep():
    w.steam.clear(); w.bubbles.clear(); w.drops.clear(); w.splash.clear(); w.ripples.clear()
def grab(name):
    prep(); w.repaint(); w.grab().toImage().save(f"{out}/{tag}_{name}.png")
grab("idle")
cases = [("light", dict(roast="淺焙")), ("dark", dict(roast="深焙")), ("lungo", dict(yield_g=54)), ("chan", dict(distribution=20))]
for name, kw in cases:
    p = model.Params(**kw); s = model.Shot(p); w.shot = s
    while s.progress < 0.55: s.update(0.05)
    w.last_flow = s.flow; w.stream = [{"head": 1.0, "tail": 0.0} for _ in range(2)]
    w.crema_h = w.crema_max(p); w.film_h = w.crema_h * 0.8; w.swirl = 0.7
    grab(name)
w.shot = None
if hasattr(w, "machine"):
    wf = workflow.Workflow(model.Params(), False, w.machine)
else:
    wf = workflow.Workflow(model.Params(), False)
w.workflow = wf
for t, name in ((0.4, "unlock"), (3.0, "grind"), (6.4, "tamp"), (7.6, "togroup")):
    while sum(d for _, d in wf.steps[:wf.i]) + wf.t < t: wf.update(0.02)
    wf.events.clear(); grab("wf_" + name)
print(tag, "done")
