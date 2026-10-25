"""杯子：幾何、容量、玻璃繪製（機身座標）

每種飲品用不同的玻璃杯；杯底中心放在咖啡機定義的位置（cup_cx, cup_base）。
"""
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QRadialGradient, QPen, QPainterPath, QFont

from .gfx import C, vgrad, hgrad
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

# 大中小杯（營業模式，加奶／加水的飲品）：牛奶、水的倍率與杯子的縮放（容量跟液量一起變）
SIZE_K = {"S": 0.75, "M": 1.0, "L": 1.3}
# 杯子的 (寬, 高) 縮放：高度差比較多，一眼看得出大中小（寬²×高 ≈ SIZE_K，容量跟著液量）
SIZE_SCALE = {"S": (0.94, 0.82), "M": (1.0, 1.0), "L": (1.06, 1.2)}
# 每種飲品（大中小各一個）的杯子容量倍率：做好時約九成滿。數字＝預設參數做出來的量 ÷ 0.9 ÷ 杯子容量
# （2026-10-24 量的：每種飲品營業模式做一杯，take_cup 時 cup_volume() / cup.cap）；高度縮得比寬度多（寬^0.25、高^0.5）。
# 阿芙佳朵不調（冰淇淋球不算在液量裡，照算會小到裝不下球）；沒列的是 1。改了預設參數或杯子要重量
CUP_FIT = {
    "espresso": {"M": 0.54}, "ristretto": {"M": 0.35}, "lungo": {"M": 0.8}, "doppio": {"M": 0.63},
    "americano": {"S": 0.82, "M": 0.76, "L": 0.74}, "iced_americano": {"S": 0.9, "M": 0.84, "L": 0.81},
    "latte": {"S": 1.02, "M": 0.92, "L": 0.94}, "cappuccino": {"S": 1.03, "M": 0.99, "L": 1.0},
    "flat_white": {"M": 1.01}, "cortado": {"M": 0.87}, "macchiato": {"M": 1.02},
    "iced_latte": {"S": 0.94, "M": 0.88, "L": 0.85}, "mocha": {"S": 1.04, "M": 0.96, "L": 1.0},
    "caramel_macchiato": {"S": 1.08, "M": 1.03, "L": 1.02}, "espresso_tonic": {"S": 0.94, "M": 0.88, "L": 0.85},
    "pour_over": {"M": 1.01}, "moka_pot": {"M": 0.73}, "siphon": {"M": 0.94}, "cold_drip": {"M": 0.59},
    "pumpkin_latte": {"S": 1.11, "M": 1.04, "L": 0.99}, "gingerbread_latte": {"S": 1.1, "M": 0.99, "L": 0.99},
    "rose_latte": {"S": 1.08, "M": 1.0, "L": 1.01},
}


def cup_fit(drink, size="M"):
    """這杯飲品（大中小）的杯子容量倍率（CUP_FIT），做好時約九成滿"""
    return CUP_FIT.get(drink, {}).get(size, 1.0)

# 營業模式外帶的紙杯（不透明）：size → (高, 杯口寬, 杯底寬)。每種熱飲玻璃杯對應一種 "paper_<玻璃杯>"，
# 容量沿用玻璃杯的（液面高度只看比例），大小依容量分 s／m／l
PAPER_SIZE = {"s": (52, 46, 34), "m": (68, 56, 40), "l": (86, 64, 44)}


def paper_size(kind):
    cap = CUP_KINDS[kind]["cap"]
    return "s" if cap <= 110 else ("m" if cap <= 175 else "l")


for _k in [k for k in CUP_KINDS if k != "iced"]:
    _h, _top, _bot = PAPER_SIZE[paper_size(_k)]
    CUP_KINDS["paper_" + _k] = {"name": "外帶紙杯", "top": _top, "bottom": _bot, "h": _h,
                                "cap": CUP_KINDS[_k]["cap"], "handle": False, "paper": paper_size(_k)}


# 營業模式外帶冰飲的透明塑膠杯（PET）：比玻璃冰飲杯薄、杯口有捲邊、杯底有一圈圈的紋路；容量一樣
CUP_KINDS["plastic_iced"] = {"name": "外帶塑膠杯", "top": 96, "bottom": 68, "h": 124, "cap": 330.0, "handle": False,
                             "plastic": True}
ICED_CUPS = ("iced", "plastic_iced")         # 冰飲杯（會凝結水珠、外帶時加圓頂蓋）


def paper_kind(kind):
    """外帶用哪一種杯子：熱飲換成同容量的紙杯，冰飲換成透明塑膠杯（內用一律是玻璃杯）"""
    if kind == "iced":
        return "plastic_iced"
    return kind if kind in ICED_CUPS or kind.startswith("paper_") else "paper_" + kind


def paint_paper_body(p, x, base, size, z=(1.0, 1.0), mark=""):
    """紙杯杯身（不透明，蓋住杯中的液體）與杯口捲邊；櫃檯的外帶杯（render/shop.py）也用這個。
    z：大中小杯的 (寬, 高) 縮放；mark：杯身印的杯量字（S／M／L）"""
    h0, tw0, bw0 = PAPER_SIZE[size]
    h, top_w, bot_w = h0 * z[1], tw0 * z[0], bw0 * z[0]
    top = base - h
    body = QPainterPath()
    body.moveTo(x - top_w / 2, top + 2)
    body.lineTo(x + top_w / 2, top + 2)
    body.lineTo(x + bot_w / 2, base)
    body.lineTo(x - bot_w / 2, base)
    body.closeSubpath()
    p.setPen(Qt.NoPen)
    p.fillPath(body, hgrad(x - top_w / 2, x + top_w / 2, [(0, C("#d9d4cc")), (0.3, C("#fbfaf7")),
                                                         (0.7, C("#eeebe5")), (1, C("#c4beb4"))]))
    rx = top_w / 2 + 1
    p.setBrush(C("#f6f4f0"))
    p.setPen(QPen(C("#bdb6aa"), 0.6))
    p.drawChord(QRectF(x - rx, top + 2 - rx * 0.11, rx * 2, rx * 0.22), 180 * 16, 180 * 16)
    p.setPen(Qt.NoPen)
    if mark:                                     # 杯量：印在杯身下方（隔熱套底下露出來的地方）
        f = QFont()
        f.setPointSizeF(max(5.0, 7.5 * z[0]))
        f.setBold(True)
        p.setFont(f)
        p.setPen(C("#8a7a66"))
        p.drawText(QRectF(x - 12, base - h * 0.27 - 6, 24, 12), Qt.AlignCenter, mark)
        p.setPen(Qt.NoPen)


class Cup:
    def __init__(self, kind, cx, base, size="M", fit=1.0):
        d = CUP_KINDS[kind]
        zw, zh = SIZE_SCALE[size]                  # 大中小杯：杯子 (寬, 高) 縮放，容量依液量的倍率
        zw, zh = zw * fit ** 0.25, zh * fit ** 0.5  # 依這杯的量縮放，約九成滿（CUP_FIT）
        self.kind = kind
        self.size = size
        self.z = (zw, zh)
        self.cap = d["cap"] * SIZE_K[size] * fit
        self.handle = d["handle"]
        self.CX = cx
        self.B = base
        self.T = base - d["h"] * zh
        self.TL, self.TR = cx - d["top"] * zw / 2, cx + d["top"] * zw / 2
        self.BL, self.BR = cx - d["bottom"] * zw / 2, cx + d["bottom"] * zw / 2
        self.k = d["h"] * zh / 74.0                # 相對濃縮杯的高度比例（把手、反光用）
        self.paper = d.get("paper")                # 外帶紙杯的大小（s／m／l；玻璃杯是 None）
        self.plastic = d.get("plastic", False)     # 外帶冰飲的透明塑膠杯
        self.sized = False                         # 分大中小的飲品（紙杯上印杯量字；reset_cup 設定）

    def mark(self):
        """紙杯上印的杯量字：只有分大中小的飲品才印（reset_cup 設 sized）"""
        return self.size if self.sized else ""

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
        """液面高度：杯子是上寬下窄的圓錐台，越往上每一層裝得越多，所以液面上升越來越慢
        （截面積 ∝ 半徑²；解 ∫r² dh 的三次方程，見下）"""
        frac = min(1.0, max(0.0, volume) / self.cap)
        yb, yt = self.liquid_bottom, self.liquid_top
        l, r = self.cup_x(yb)
        a = (r - l) / 2
        l, r = self.cup_x(yt)
        b = (r - l) / 2
        if abs(b - a) < 1e-6:
            h = frac
        else:
            h = ((a ** 3 + frac * (b ** 3 - a ** 3)) ** (1 / 3) - a) / (b - a)
        return yb - h * (yb - yt)

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
        if self.paper:                             # 紙杯：杯口裡面看得到的內壁
            p.setPen(Qt.NoPen)
            p.setBrush(C("#e8e2d8"))
            p.drawEllipse(QRectF(self.TL, self.T + 2 - rx_t * 0.11, rx_t * 2, rx_t * 0.22))
            return
        p.setPen(QPen(C("#ffffff", 60), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(self.TL, self.T - rx_t * 0.11, rx_t * 2, rx_t * 0.22), 0, 180 * 16)
        p.fillPath(self.path(), C("#ffffff", 6 if self.plastic else 10))

    def paint_plastic_front(self, p):
        """外帶塑膠杯：杯壁薄（細線）、杯口捲邊、杯底沒有厚玻璃，靠下有兩圈紋路，一道直的反光"""
        T, B, TL, TR, BL, BR = self.T, self.B, self.TL, self.TR, self.BL, self.BR
        rx_t = (TR - TL) / 2
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#ffffff", 85), 0.9))
        p.drawLine(QPointF(TL, T), QPointF(BL, B - 3))
        p.drawLine(QPointF(TR, T), QPointF(BR, B - 3))
        p.drawArc(QRectF(BL, B - 7, BR - BL, 7), 180 * 16, 180 * 16)               # 杯底
        for dy in (16, 22):                                                         # 杯身下方的紋路
            l, r = self.cup_x(B - dy, inner=False)
            p.setPen(QPen(C("#ffffff", 45), 0.8))
            p.drawArc(QRectF(l, B - dy - 2.5, r - l, 5), 180 * 16, 180 * 16)
        p.setPen(QPen(C("#ffffff", 190), 2.4))                                      # 杯口捲邊
        p.drawArc(QRectF(TL - 1, T - rx_t * 0.11, rx_t * 2 + 2, rx_t * 0.22), 180 * 16, 180 * 16)
        refl = QPainterPath()
        refl.moveTo(TL + 7, T + 10)
        refl.lineTo(TL + 10, T + 10)
        refl.lineTo(BL + 8, B - 14)
        refl.lineTo(BL + 6, B - 14)
        refl.closeSubpath()
        p.fillPath(refl, vgrad(T, B, [(0, C("#ffffff", 110)), (1, C("#ffffff", 15))]))

    def paint_front(self, p):
        """前景圖層：杯緣、杯身線條、厚杯底、反光、把手"""
        T, B, TL, TR, BL, BR, CX, k = self.T, self.B, self.TL, self.TR, self.BL, self.BR, self.CX, self.k
        if self.paper:                             # 紙杯不透明：杯身蓋住杯中的液體
            paint_paper_body(p, CX, B, self.paper, self.z, self.mark())
            return
        if self.plastic:
            return self.paint_plastic_front(p)
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
