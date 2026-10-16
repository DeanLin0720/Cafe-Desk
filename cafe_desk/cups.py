"""杯子：幾何、容量、玻璃繪製（機身座標）

每種飲品用不同的玻璃杯；杯底中心放在咖啡機定義的位置（cup_cx, cup_base）。
"""
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QRadialGradient, QPen, QPainterPath

from .gfx import C, vgrad
from .util import lerp

# top / bottom：杯口與杯底外寬；h：杯高；cap：裝滿的容量（g）；handle：有沒有把手
CUP_KINDS = {
    "espresso": {"name": "濃縮杯", "top": 88, "bottom": 68, "h": 74, "cap": 75.0, "handle": True},
    "americano": {"name": "美式杯", "top": 104, "bottom": 84, "h": 86, "cap": 230.0, "handle": True},
    "latte": {"name": "拿鐵杯", "top": 112, "bottom": 82, "h": 92, "cap": 270.0, "handle": True},
    "cappuccino": {"name": "卡布杯", "top": 106, "bottom": 74, "h": 80, "cap": 230.0, "handle": True},
    "flat_white": {"name": "馥列白杯", "top": 98, "bottom": 74, "h": 74, "cap": 170.0, "handle": True},
    "affogato": {"name": "阿芙佳朵杯", "top": 100, "bottom": 66, "h": 60, "cap": 130.0, "handle": False},
    "cortado": {"name": "Gibraltar 杯", "top": 80, "bottom": 70, "h": 72, "cap": 105.0, "handle": False},
    "iced": {"name": "冰飲杯", "top": 92, "bottom": 74, "h": 124, "cap": 330.0, "handle": False},
}


class Cup:
    def __init__(self, kind, cx, base):
        d = CUP_KINDS[kind]
        self.kind = kind
        self.cap = d["cap"]
        self.handle = d["handle"]
        self.CX = cx
        self.B = base
        self.T = base - d["h"]
        self.TL, self.TR = cx - d["top"] / 2, cx + d["top"] / 2
        self.BL, self.BR = cx - d["bottom"] / 2, cx + d["bottom"] / 2
        self.k = d["h"] / 74.0                     # 相對濃縮杯的高度比例（把手、反光用）

    # ───────────── 幾何 ─────────────
    def cup_x(self, y, inner=True):
        f = (self.B - y) / (self.B - self.T)
        l, r = lerp(self.BL, self.TL, f), lerp(self.BR, self.TR, f)
        return (l + 3, r - 3) if inner else (l, r)

    @property
    def liquid_bottom(self):
        return self.B - 6

    @property
    def liquid_top(self):
        return self.T + 8

    def level_y(self, volume):
        frac = min(1.0, max(0.0, volume) / self.cap)
        return self.liquid_bottom - frac * (self.liquid_bottom - self.liquid_top)

    def path(self):
        path = QPainterPath()
        path.moveTo(self.TL, self.T)
        path.lineTo(self.BL, self.B - 3)
        path.quadTo(QPointF(self.CX, self.B + 4), QPointF(self.BR, self.B - 3))
        path.lineTo(self.TR, self.T)
        path.closeSubpath()
        return path

    def inner_path(self):
        """杯內空間（裁切冰塊、凝結水珠用）"""
        l, r = self.cup_x(self.T)
        bl, br = self.cup_x(self.B - 4)
        path = QPainterPath()
        path.moveTo(l, self.T)
        path.lineTo(bl, self.B - 5)
        path.quadTo(QPointF(self.CX, self.B), QPointF(br, self.B - 5))
        path.lineTo(r, self.T)
        path.closeSubpath()
        return path

    # ───────────── 繪製 ─────────────
    def paint_back(self, p):
        """背景圖層：杯底陰影、後側杯緣、極淡的玻璃底色"""
        cx, B = self.CX, self.B
        sx = (self.BR - self.BL) / 68.0
        g = QRadialGradient(cx, B, 50 * sx)
        g.setColorAt(0, C("#000000", 140))
        g.setColorAt(1, C("#000000", 0))
        p.save()
        p.translate(cx, B + 1)
        p.scale(1, 0.12)
        p.translate(-cx, -(B + 1))
        p.fillRect(QRectF(cx - 70 * sx, B - 60, 140 * sx, 120), g)
        p.restore()
        rx_t = (self.TR - self.TL) / 2
        p.setPen(QPen(C("#ffffff", 60), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(self.TL, self.T - rx_t * 0.11, rx_t * 2, rx_t * 0.22), 0, 180 * 16)
        p.fillPath(self.path(), C("#ffffff", 10))

    def paint_front(self, p):
        """前景圖層：杯緣、杯身線條、厚杯底、反光、把手"""
        T, B, TL, TR, BL, BR, CX, k = self.T, self.B, self.TL, self.TR, self.BL, self.BR, self.CX, self.k
        rx_t = (TR - TL) / 2
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#ffffff", 120), 1.4))
        p.drawLine(QPointF(TL, T), QPointF(BL, B - 3))
        p.drawLine(QPointF(TR, T), QPointF(BR, B - 3))
        p.setPen(QPen(C("#ffffff", 160), 1.4))
        p.drawArc(QRectF(TL, T - rx_t * 0.11, rx_t * 2, rx_t * 0.22), 180 * 16, 180 * 16)
        base = QPainterPath()
        bl, br = BL + 1, BR - 1
        base.moveTo(bl, B - 7)
        base.quadTo(QPointF(CX, B - 3), QPointF(br, B - 7))
        base.lineTo(BR, B - 3)
        base.quadTo(QPointF(CX, B + 4), QPointF(BL, B - 3))
        base.closeSubpath()
        p.fillPath(base, vgrad(B - 8, B + 3, [(0, C("#ffffff", 70)), (1, C("#ffffff", 25))]))
        refl = QPainterPath()
        refl.moveTo(TL + 6, T + 8)
        refl.lineTo(TL + 13, T + 8)
        refl.lineTo(BL + 11, B - 12)
        refl.lineTo(BL + 6, B - 12)
        refl.closeSubpath()
        p.fillPath(refl, vgrad(T, B, [(0, C("#ffffff", 95)), (1, C("#ffffff", 10))]))
        p.setPen(QPen(C("#ffffff", 70), 1.2))
        p.drawLine(QPointF(TR - 9, T + 12 * k), QPointF(BR - 7, B - 22 * k))
        if self.handle:
            hp = QPainterPath(QPointF(TR - 1, T + 12 * k))
            hp.cubicTo(QPointF(TR + 24, T + 8 * k), QPointF(TR + 26, T + 46 * k),
                       QPointF(BR + 2, T + 54 * k))
            p.setPen(QPen(C("#ffffff", 70), 6, Qt.SolidLine, Qt.RoundCap))
            p.drawPath(hp)
            p.setPen(QPen(C("#ffffff", 150), 1.4, Qt.SolidLine, Qt.RoundCap))
            p.drawPath(hp)
