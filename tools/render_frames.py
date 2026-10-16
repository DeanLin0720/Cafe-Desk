"""固定亂數種子與時間，做一杯濃縮、一杯拿鐵，每隔幾步存一張完整畫面（比對繪圖修改前後）

    python tools/render_frames.py tools/out/before      （改之前）
    python tools/render_frames.py tools/out/after       （改之後）
    python tools/compare_frames.py tools/out/before tools/out/after
同一份程式跑兩次結果完全相同，所以有差異就是繪圖改動造成的。
"""
import sys, os, json, random
os.environ.update(QT_QPA_PLATFORM="offscreen", CAFE_DESK_NO_AUDIO="1", CAFE_DESK_DATE="2026-08-01")
if os.path.isdir("C:/Windows/Fonts"):
    os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"      # 無頭模式也用系統字型，截圖才看得到中文
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); out = sys.argv[1]; os.makedirs(out, exist_ok=True)
from PySide6.QtWidgets import QApplication
app = QApplication([])
from cafe_desk import paths, desk
import time as _t
_t0 = 1000.0; _clock = [0.0]
_t.perf_counter = lambda: _t0 + _clock[0]           # 固定時間：蒸氣、氣泡、沉降都可重現
for mk in ("lever", "compact"):
    paths.CONFIG_PATH = os.path.abspath(f"{out}/f_{mk}.json")
    for f in (paths.CONFIG_PATH, paths.CONFIG_PATH[:-5] + "_records.db"):
        if os.path.exists(f): os.remove(f)
    json.dump({"x": 0, "y": 0, "light_mode": "day", "machine": mk}, open(paths.CONFIG_PATH, "w"))
    random.seed(11)
    w = desk.CafeDesk(); w.show_window(); w.timer.stop(); w.warming = False; w.boiler.temp = w.params.temp
    k = 0
    for drink in ("espresso", "latte"):
        w.start_session(drink, False); n = 0
        while w.busy() or n < 400:
            _clock[0] += 1 / 30; w.step(1 / 30, 1 / 30 * 2); n += 1
            if n % 25 == 0:
                w.grab().save(f"{out}/{mk}_{k:03d}.png"); k += 1
            if n > 6000: break
    w.stats.db.close(); w.host.close()
    print(mk, k, "frames")
