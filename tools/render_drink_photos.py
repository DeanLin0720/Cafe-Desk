"""圖鑑的飲品圖：每種飲品在遊戲裡實際做一杯（DESK·01、預設參數），做好後用 cup_photo() 拍成透明底的 PNG

    python tools/render_drink_photos.py            輸出到 cafe_desk/assets/drinks/<飲品>.png
    python tools/render_drink_photos.py latte,mocha   只重拍這幾種

新增飲品、改了杯子或杯中畫法時要重拍（tests/test_drink_notes.py 會檢查每種飲品都有圖）。
固定亂數與時間，同一份程式重拍結果相同。
"""
import json
import os
import random
import sys
import tempfile
import time

os.environ.update(QT_QPA_PLATFORM="offscreen", CAFE_DESK_NO_AUDIO="1", CAFE_DESK_DATE="2026-08-01", CAFE_DESK_NO_UPDATE="1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_clock = [0.0]
time.perf_counter = lambda: 1000.0 + _clock[0]           # 固定時間：蒸氣、氣泡、混合都可重現

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

app = QApplication([])
from cafe_desk import paths, desk, growth
from cafe_desk.drinks import DRINK_KEYS, FESTIVAL_DRINKS
from cafe_desk.render.icons import PHOTO_DIR, PHOTO_RATIO

SETTLE = 4.0          # 做好後再等幾秒才拍（濃縮在牛奶裡暈開一點、冰塊浮起來）


def crop(img):
    """裁掉四周透明的部分（cup_photo 上面留了擠鮮奶油的空間）"""
    img = img.convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    bits = bytes(img.constBits())
    stride = img.bytesPerLine()
    xs, ys = [], []
    for y in range(h):
        row = bits[y * stride:y * stride + w * 4]
        alpha = row[3::4]
        hit = [i for i, a in enumerate(alpha) if a > 8]
        if hit:
            ys.append(y)
            xs += (hit[0], hit[-1])
    pad = 2
    x0, x1 = max(0, min(xs) - pad), min(w - 1, max(xs) + pad)
    y0, y1 = max(0, min(ys) - pad), min(h - 1, max(ys) + pad)
    out = img.copy(x0, y0, x1 - x0 + 1, y1 - y0 + 1)
    out.setDevicePixelRatio(1.0)
    return out


growth.MACHINE_LEVEL = {k: 1 for k in growth.MACHINE_LEVEL}
growth.METHOD_LEVEL = {k: 1 for k in growth.METHOD_LEVEL}
growth.DRINK_RANK = {}
keys = sys.argv[1].split(",") if len(sys.argv) > 1 else list(DRINK_KEYS) + list(FESTIVAL_DRINKS)
os.makedirs(PHOTO_DIR, exist_ok=True)
tmp = tempfile.mkdtemp(prefix="drink_photos_")
paths.CONFIG_PATH = os.path.join(tmp, "cfg.json")
with open(paths.CONFIG_PATH, "w", encoding="utf-8") as f:
    json.dump({"x": 0, "y": 0, "light_mode": "day", "machine": "desk01", "intro_seen": True, "welcomed": True}, f)
w = desk.CafeDesk()
w.timer.stop()
w.warming = False
for k in keys:
    random.seed(sum(map(ord, k)))
    w.boiler.temp = w.params.temp
    w.bag["left"] = w.bag["size"] = 9999.0
    if w.cold is not None or k == "cold_drip":       # 冰滴：直接給一壺滴好的
        from cafe_desk import brew
        p = w.params
        w.cold = dict(brew.new_cold_batch(w.dp, p.roast, p.bean_age, w.bag["origin"]), done=True, servings=brew.COLD_SERVINGS)
    if not w.start_session(k, False):
        sys.exit(f"{k}：開始不了")
    n = 0
    while w.busy():
        _clock[0] += 0.05
        w.step(0.05, 0.5)
        n += 1
        if n > 20000:
            sys.exit(f"{k}：卡住了")
    for _ in range(int(SETTLE / 0.05)):
        _clock[0] += 0.05
        w.step(0.05, 0.05)
    img, _ = w.cup_photo(PHOTO_RATIO)
    crop(img).save(os.path.join(PHOTO_DIR, f"{k}.png"))
    print(k)
w.stats.db.close()
w.host.close()
