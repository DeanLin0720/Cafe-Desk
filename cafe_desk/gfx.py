"""繪圖小工具：顏色、漸層、圓角矩形、字型"""
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPainterPath, QFontDatabase

from .util import clamp


def hex2rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    a, b = hex2rgb(c1), hex2rgb(c2)
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def C(h, a=255):
    c = QColor(h)
    c.setAlpha(int(clamp(a, 0, 255)))
    return c


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

