"""繪圖小工具：顏色、漸層、圓角矩形、字型"""
from contextlib import contextmanager
from functools import lru_cache

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPainterPath, QFontDatabase


@lru_cache(maxsize=1024)
def hex2rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    a, b = hex2rgb(c1), hex2rgb(c2)
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


@lru_cache(maxsize=8192)
def _color(h, a):
    c = QColor(h)
    c.setAlpha(a)
    return c


_remap = None                  # 畫咖啡機的時候暫時換上的顏色對應（recolor）


@contextmanager
def recolor(fn):
    """在這個區塊裡 C() 的顏色先經過 fn(#rrggbb) → #rrggbb（咖啡機換烤漆顏色，decor.make_remap）；fn 是 None 就不換"""
    global _remap
    old, _remap = _remap, fn
    try:
        yield
    finally:
        _remap = old


def C(h, a=255):
    """顏色（#rrggbb＋透明度 0–255）。每幀要建上百萬次，所以快取起來；
    回傳的 QColor 是共用的，呼叫端不能修改它（要改請 QColor(C(...)) 複製一份）"""
    if _remap is not None:
        h = _remap(h)
    return _color(h, 0 if a <= 0 else 255 if a >= 255 else int(a))


def vgrad(y1, y2, stops):
    g = QLinearGradient(0, y1, 0, y2)
    for pos, col in stops:
        g.setColorAt(pos, col)
    return g


def hgrad(x1, x2, stops):
    g = QLinearGradient(x1, 0, x2, 0)
    for pos, col in stops:
        g.setColorAt(pos, col)
    return g


def rrect(x1, y1, x2, y2, r):
    p = QPainterPath()
    p.addRoundedRect(QRectF(x1, y1, x2 - x1, y2 - y1), r, r)
    return p


def pick_family(cands, fallback):
    fams = set(QFontDatabase.families())
    for f in cands:
        if f in fams:
            return f
    return fallback

