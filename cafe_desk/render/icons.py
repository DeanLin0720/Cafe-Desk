"""圖鑑用的飲品圖：側面看的一杯（杯型、分層、配料），沒做過的是灰色剪影

不用圖檔：杯型取 cups.CUP_KINDS 的比例，液體分層與配料依飲品寫在 RECIPES。
"""
import random

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QPen, QColor, QFont, QLinearGradient

from ..cups import CUP_KINDS
from ..drinks import DRINKS

COFFEE, CREMA, MILK, FOAM = "#3b2416", "#b07a45", "#efe6d8", "#f7f2ea"
MIX, CHOC, VANILLA = "#c39a74", "#4a2a18", "#eadab2"

# 由下往上的液體層 (佔杯高的比例, 顏色)，以及配料
RECIPES = {
    "espresso": ([(0.40, COFFEE), (0.08, CREMA)], {}),
    "ristretto": ([(0.26, COFFEE), (0.07, CREMA)], {}),
    "lungo": ([(0.60, COFFEE), (0.07, CREMA)], {}),
    "doppio": ([(0.54, COFFEE), (0.08, CREMA)], {}),
    "americano": ([(0.76, "#4a2c18"), (0.04, CREMA)], {}),
    "iced_americano": ([(0.80, "#5b3a22")], {"ice": True}),
    "latte": ([(0.50, MIX), (0.18, "#dcc4a6"), (0.12, FOAM)], {}),
    "cappuccino": ([(0.42, MIX), (0.40, FOAM)], {"dust": "#6b4226"}),
    "flat_white": ([(0.74, "#b88a5e"), (0.07, FOAM)], {}),
    "cortado": ([(0.36, "#7a4e2c"), (0.34, MIX), (0.08, FOAM)], {}),
    "macchiato": ([(0.40, COFFEE), (0.10, CREMA)], {"dot": True}),
    "iced_latte": ([(0.46, MILK), (0.30, "#a87a52")], {"ice": True}),
    "mocha": ([(0.12, CHOC), (0.52, "#9a6a46"), (0.08, FOAM)], {"whip": True, "dust": "#5a3420"}),
    "caramel_macchiato": ([(0.10, VANILLA), (0.48, MILK), (0.14, "#8a5a32"), (0.07, FOAM)], {"drizzle": "#c98a3a"}),
    "espresso_tonic": ([(0.52, "#e9efe6"), (0.26, "#7a4a28")], {"ice": True, "bubbles": True}),
    "affogato": ([(0.34, COFFEE)], {"scoop": True}),
    "pour_over": ([(0.74, "#6b3e1e")], {}),
    "cold_drip": ([(0.74, "#3a2214")], {"ice": True}),
    "moka_pot": ([(0.58, "#3e2516"), (0.05, "#8a5a32")], {}),
    "siphon": ([(0.74, "#5e3519")], {}),
    "pumpkin_latte": ([(0.58, "#d4925a"), (0.10, FOAM)], {"whip": True, "dust": "#a0582a"}),
    "gingerbread_latte": ([(0.58, "#b88360"), (0.10, FOAM)], {"whip": True, "dust": "#a0582a"}),
    "rose_latte": ([(0.60, "#e3aeb3"), (0.14, FOAM)], {}),
}
MAX_H = max(d["h"] for d in CUP_KINDS.values())
MAX_W = max(d["top"] for d in CUP_KINDS.values())


def _cup_geom(kind, size):
    """杯子在 size×size 畫布裡的梯形（上寬下窄）：(上緣 y, 底 y, 上左, 上右, 下左, 下右)"""
    d = CUP_KINDS[kind]
    k = size * 0.84 / max(MAX_H, MAX_W * 1.15)
    h, top, bottom = d["h"] * k, d["top"] * k, d["bottom"] * k
    cx = size * (0.46 if d["handle"] else 0.5)
    base = size * 0.94
    return base - h, base, cx - top / 2, cx + top / 2, cx - bottom / 2, cx + bottom / 2


def _body(g):
    t, b, tl, tr, bl, br = g
    path = QPainterPath()
    path.moveTo(tl, t)
    path.lineTo(tr, t)
    path.lineTo(br, b - 4)
    path.quadTo(br, b, br - 4, b)
    path.lineTo(bl + 4, b)
    path.quadTo(bl, b, bl, b - 4)
    path.closeSubpath()
    return path


def _handle(p, g, kind):
    if not CUP_KINDS[kind]["handle"]:
        return
    t, b, tl, tr, bl, br = g
    h = b - t
    x0 = tr - (tr - br) * 0.25
    path = QPainterPath()
    path.moveTo(x0, t + h * 0.2)
    path.cubicTo(QPointF(x0 + h * 0.42, t + h * 0.15), QPointF(x0 + h * 0.42, t + h * 0.72),
                 QPointF(x0 - (tr - br) * 0.35, t + h * 0.72))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)


def drink_icon(key, size=96, made=True, dpr=1.0):
    """一杯飲品的側面圖；made=False 是灰色剪影加問號"""
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    kind = DRINKS[key]["cup"]
    g = _cup_geom(kind, size)
    t, b, tl, tr, bl, br = g
    body = _body(g)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 28))
    p.drawEllipse(QPointF((bl + br) / 2, b + 1), (br - bl) * 0.62, 3)
    if not made:
        grey = QColor("#d4ccc2")
        p.setPen(QPen(grey, max(2.0, size * 0.05), Qt.SolidLine, Qt.RoundCap))
        _handle(p, g, kind)
        p.setPen(Qt.NoPen)
        p.fillPath(body, grey)
        f = QFont()
        f.setPointSizeF(size * 0.22)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#f4efe8"))
        p.drawText(QRectF(tl, t, tr - tl, b - t), Qt.AlignCenter, "?")
        p.end()
        return pm
    layers, extra = RECIPES.get(key, ([(0.6, MIX)], {}))
    h = b - t
    p.fillPath(body, QColor(220, 235, 240, 40))                       # 玻璃
    p.save()
    p.setClipPath(body)
    y = b
    for frac, col in layers:
        top = y - frac * h
        p.fillRect(QRectF(tl - 2, top, tr - tl + 4, y - top + 0.5), QColor(col))
        y = top
    surface = y
    rnd = random.Random(sum(map(ord, key)))
    if extra.get("ice"):
        for i in range(4):
            cx = bl + (br - bl) * (0.25 + 0.5 * rnd.random())
            cy = surface + h * (0.08 + 0.18 * i)
            s = h * 0.13
            p.save()
            p.translate(cx, cy)
            p.rotate(rnd.uniform(-25, 25))
            p.setBrush(QColor(235, 246, 250, 150))
            p.setPen(QPen(QColor(255, 255, 255, 170), 0.8))
            p.drawRoundedRect(QRectF(-s / 2, -s / 2, s, s), s * 0.2, s * 0.2)
            p.restore()
    if extra.get("bubbles"):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 170))
        for _ in range(12):
            p.drawEllipse(QPointF(bl + (br - bl) * rnd.random(), b - h * 0.5 * rnd.random()), 0.9, 0.9)
    if extra.get("drizzle"):
        p.setPen(QPen(QColor(extra["drizzle"]), max(1.0, size * 0.018)))
        for i in range(3):
            yy = surface + 2 + i * 3
            p.drawLine(QPointF(tl + 4, yy), QPointF(tr - 4, yy + 1.5))
    p.restore()
    if extra.get("scoop"):                                          # 阿芙佳朵：冰淇淋球
        r = (tr - tl) * 0.26
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#f3e8cf"))
        p.drawEllipse(QPointF((tl + tr) / 2, surface - r * 0.35), r, r * 0.9)
        p.setBrush(QColor(COFFEE))
        p.drawEllipse(QPointF((tl + tr) / 2 + r * 0.3, surface - r * 0.75), r * 0.25, r * 0.16)
    if extra.get("whip"):                                           # 鮮奶油
        w = tr - tl
        p.setPen(QPen(QColor("#d8c8ae"), 0.9))                 # 淡淡的輪廓：紙底上才看得出白色的鮮奶油
        for dx, dy, rr in ((-0.2, -0.02, 0.2), (0.2, -0.02, 0.2), (0, -0.07, 0.27), (0, -0.19, 0.17)):
            c = QPointF((tl + tr) / 2 + dx * w, t + dy * w)
            grad = QLinearGradient(0, c.y() - rr * w * 0.6, 0, c.y() + rr * w * 0.6)
            grad.setColorAt(0, QColor("#ffffff"))
            grad.setColorAt(1, QColor("#eadfcd"))
            p.setBrush(grad)
            p.drawEllipse(c, rr * w, rr * w * 0.62)
    if extra.get("dust"):                                           # 可可粉／肉桂粉
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(extra["dust"]))
        top_y = t - (0.12 * (tr - tl) if extra.get("whip") else 0)
        for _ in range(26):
            p.drawEllipse(QPointF(tl + 6 + (tr - tl - 12) * rnd.random(), top_y + rnd.uniform(-1.5, 2)), 0.8, 0.8)
    if extra.get("dot"):                                            # 瑪奇朵：一匙奶泡
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(FOAM))
        p.drawEllipse(QPointF((tl + tr) / 2, surface), (tr - tl) * 0.18, 3)
    # 玻璃外框、反光、把手
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor("#8c979c"), 1.1))                     # 紙底上看得到的玻璃邊
    p.drawPath(body)
    grad = QLinearGradient(tl, 0, tl + (tr - tl) * 0.25, 0)
    grad.setColorAt(0, QColor(255, 255, 255, 110))
    grad.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillRect(QRectF(tl + 3, t + 3, (tr - tl) * 0.18, h - 8), grad)
    p.setPen(QPen(QColor("#a7b0b4"), max(1.6, size * 0.035), Qt.SolidLine, Qt.RoundCap))
    _handle(p, g, kind)
    p.end()
    return pm
