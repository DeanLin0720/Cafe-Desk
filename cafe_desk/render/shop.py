"""營業模式：咖啡機旁的出杯台與出餐架、櫃檯畫面（現代 POS、交付）（場景座標）、打烊日報收據（視窗座標）"""
import math
import random
import time

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QPen, QFont, QFontMetricsF, QPainterPath, QImage, QPainter, QLinearGradient, QPolygonF,
                           QRadialGradient, QColor)

from ..cups import PAPER_SIZE, ICED_CUPS, paint_paper_body
from .. import orders
from ..drinks import DRINKS
from .icons import drink_icon, ORIGIN_LOOK
from ..machines import MACHINES
from ..gfx import C, rrect, vgrad, hgrad
from .. import growth, decor, festivals, beans, ingredients
from ..growth import MAX_LEVEL, level_name
from ..i18n import T, money, retext
from ..layout import TOP_PAD, WIN_H, FLOOR
from ..util import clamp, lerp

SIDE_W, SIDE_W2 = 170, 136  # 營業模式咖啡機右邊的出杯台寬度（雙頭機多一個杯位）
SHELF_Y = FLOOR - 178       # 出杯台上方出餐架的高度（場景座標）
MAT_H = 6                   # 出杯台吧台墊的厚度：杯底在墊子上緣
MENU_X0, MENU_X1 = 170, 840  # 櫃檯畫面：吊掛菜單看板與後方層架的左右範圍（右上角留給翻頁鐘）
BACK_GEAR = ("pourover", "colddrip", "moka", "siphon")   # 後檯可以擺出來的沖煮設備（右鍵「後檯顯示新設備」逐項開關）
BEAN_SLOTS = 10             # 右下展示窗最多擺幾種庫存咖啡豆（兩層、每層一半）
CASE_IN = 300               # 前櫃檯右段甜點玻璃櫃的左端距視窗右邊
CUPS_X = 150                # 做好的杯子從這裡開始排（POS 在甜點櫃左邊）
# 店面配色（使用者選的暖木）：牆、看板、後檯、前櫃檯、地板
STORE = {"wall": ("#2b2522", "#1b1715"), "blind": "#c8b89a", "board": "#1e1c1a", "accent": "#ffd27a", "shelf": "#8a6440",
         "front": ("#7a5434", "#4a3220"), "top": ("#e8dcc8", "#b8a88e"), "logo": "#f0dcb8",
         "floor": ("#5a4030", "#3a2a20")}
SIGN_DX, SIGN_W = 122, 62  # 座位小黑板：中心在 POS 左邊多遠、寬度
COUNTER_CUP_K = 0.4         # 櫃檯上的杯子縮小成跟 POS 相稱的真實比例（紙杯跟刷卡機差不多高）
PASS_K = 0.55               # 出餐架上等著的杯子縮小的比例
COUNTER_TOP = 300           # 櫃檯畫面的檯面高度（場景座標）
FLOAT_SEC = 1.6
RESULT_SHOW = 15.0          # 營業模式：客人的評價在狀態列顯示幾秒（之後回到「等待客人點單…」）             # 收錢時金額往上飄的秒數
DELIVERY_T = {"in": 0.7, "place": 0.9, "pickup": 0.9, "out": 0.65}   # 櫃檯交付各段的秒數（模擬時間；咖啡師在等，改了要重跑平衡模擬）
CHECKOUT_T = {"in": 0.5, "pay": 2.0}        # 接單時在櫃檯結帳：切到櫃檯、每一組客人刷卡（同上，改了要重跑平衡模擬）
REPORT_SEC = 15.0           # 日報停留秒數（點一下就收起）
REPORT_W = 214


def star_path(cx, cy, r):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.42
        pts.append(QPointF(cx + rr * math.cos(a), cy + rr * math.sin(a)))
    path = QPainterPath()
    path.addPolygon(QPolygonF(pts + [pts[0]]))
    return path


def paint_stars(p, x, y, r, rating, gap=3.0, empty="#5a4a3a"):
    """五顆星（x 是左端、y 是中心），rating 1.0–5.0：滿的金色、最後一顆依小數填一部分、其餘暗色"""
    p.save()
    p.setPen(Qt.NoPen)
    for i in range(5):
        cx = x + r + i * (2 * r + gap)
        path = star_path(cx, y, r)
        p.fillPath(path, C(empty))
        frac = max(0.0, min(1.0, rating - i))
        if frac > 0:
            p.setClipRect(QRectF(cx - r, y - r, 2 * r * frac, 2 * r))
            p.fillPath(path, C("#f2c14e"))
            p.setClipping(False)
    p.restore()


def _swag(p, x0, x1, y, sag, pen):
    """兩端掛在 (x0, x1, y)、中間下垂 sag 的一條彩帶；回傳畫出來的路徑（要沿著它掛東西用 _swag_pt）"""
    path = QPainterPath(QPointF(x0, y))
    path.quadTo(QPointF((x0 + x1) / 2, y + 2 * sag), QPointF(x1, y))
    p.setBrush(Qt.NoBrush)
    p.setPen(pen)
    p.drawPath(path)
    return path


def _swag_pt(x0, x1, y, sag, t):
    """_swag 這條彎曲上 t（0–1）的點"""
    cx = (x0 + x1) / 2
    return ((1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x1, (1 - t) ** 2 * y + 2 * (1 - t) * t * (y + 2 * sag) + t * t * y)


def paint_heart(p, x, y, s, col, alpha=255):
    path = QPainterPath(QPointF(x, y + s * 0.9))
    path.cubicTo(QPointF(x - s * 1.5, y - s * 0.2), QPointF(x - s * 0.55, y - s * 1.1), QPointF(x, y - s * 0.3))
    path.cubicTo(QPointF(x + s * 0.55, y - s * 1.1), QPointF(x + s * 1.5, y - s * 0.2), QPointF(x, y + s * 0.9))
    p.setPen(Qt.NoPen)
    p.fillPath(path, C(col, alpha))


def paint_pumpkin(p, x, base, s=1.0, glow=True):
    """南瓜燈（x、base＝底中心）：橘色身體、三角眼、鋸齒嘴，裡面有一點暖光"""
    p.save()
    p.translate(x, base)
    p.scale(s, s)
    p.setPen(Qt.NoPen)
    p.fillPath(rrect(-3, -30, 3, -22, 2), C("#4a6a2a"))                           # 蒂
    for dx, w in ((-11, 11), (11, 11), (0, 14)):                                   # 一瓣一瓣的南瓜
        p.setBrush(vgrad(-24, 0, [(0, C("#f0902a")), (1, C("#c25a14"))]))
        p.drawEllipse(QPointF(dx, -12), w, 13)
    if glow:
        g = QRadialGradient(0, -12, 14)
        g.setColorAt(0, C("#ffe27a", 255))
        g.setColorAt(1, C("#ffb030", 0))
        p.setBrush(g)
        p.drawEllipse(QPointF(0, -12), 13, 11)
    eye = QPainterPath()
    eye.addPolygon(QPolygonF([QPointF(-8, -17), QPointF(-3, -17), QPointF(-5.5, -22)]))
    p.fillPath(eye, C("#3a1a08"))
    eye2 = QPainterPath()
    eye2.addPolygon(QPolygonF([QPointF(3, -17), QPointF(8, -17), QPointF(5.5, -22)]))
    p.fillPath(eye2, C("#3a1a08"))
    mouth = QPainterPath()
    mouth.addPolygon(QPolygonF([QPointF(-9, -10), QPointF(-6, -7), QPointF(-3, -10), QPointF(0, -6), QPointF(3, -10),
                                QPointF(6, -7), QPointF(9, -10), QPointF(6, -4), QPointF(0, -2), QPointF(-6, -4)]))
    p.fillPath(mouth, C("#3a1a08"))
    p.restore()


def paint_bat(p, x, y, s=1.0):
    p.save()
    p.translate(x, y)
    p.scale(s, s)
    p.setPen(Qt.NoPen)
    p.setBrush(C("#14101a"))
    body = QPainterPath(QPointF(0, -5))
    body.cubicTo(QPointF(-6, -4), QPointF(-10, -9), QPointF(-18, -3))
    body.cubicTo(QPointF(-14, -1), QPointF(-12, 2), QPointF(-9, 5))
    body.cubicTo(QPointF(-6, 2), QPointF(-3, 3), QPointF(0, 6))
    body.cubicTo(QPointF(3, 3), QPointF(6, 2), QPointF(9, 5))
    body.cubicTo(QPointF(12, 2), QPointF(14, -1), QPointF(18, -3))
    body.cubicTo(QPointF(10, -9), QPointF(6, -4), QPointF(0, -5))
    p.drawPath(body)
    p.drawEllipse(QPointF(0, -1), 3.4, 4.4)
    p.setBrush(C("#ff6a3a"))
    p.drawEllipse(QPointF(-1.2, -1.8), 0.7, 0.7)
    p.drawEllipse(QPointF(1.2, -1.8), 0.7, 0.7)
    p.restore()


def paint_cobweb(p, x, y, r=46):
    """左上角的蜘蛛網（x、y 是角落）：幾條放射線加幾圈弧線"""
    p.save()
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(C("#e8e4f0", 120), 0.8))
    for k in range(5):
        a = math.radians(k * 22.5)
        p.drawLine(QPointF(x, y), QPointF(x + r * math.cos(a), y + r * math.sin(a)))
    for ring in (0.3, 0.55, 0.8, 1.0):
        path = QPainterPath(QPointF(x + r * ring, y))
        for k in range(1, 5):
            a = math.radians(k * 22.5)
            rr = r * ring * (0.88 if k % 2 else 1.0)
            path.lineTo(QPointF(x + rr * math.cos(a), y + rr * math.sin(a)))
        p.drawPath(path)
    p.restore()


def paint_xmas_tree(p, x, base, h=118):
    """聖誕樹（x、base＝樹底中心）：三層綠色、彩球、頂上的星星；燈會閃（用時間）"""
    p.save()
    p.setPen(Qt.NoPen)
    p.fillRect(QRectF(x - 4, base - 12, 8, 12), C("#6a4a2e"))
    for i, (w, y0, y1) in enumerate(((50, base - 14, base - h * 0.5), (40, base - h * 0.42, base - h * 0.76), (28, base - h * 0.68, base - h + 14))):
        tri = QPainterPath()
        tri.addPolygon(QPolygonF([QPointF(x - w / 2, y0), QPointF(x + w / 2, y0), QPointF(x, y1)]))
        p.fillPath(tri, vgrad(y1, y0, [(0, C("#2f8a4a")), (1, C("#1a5a30"))]))
    t = time.perf_counter()
    for k, (dx, dy, col) in enumerate(((-12, 20, "#e84a4a"), (10, 28, "#ffd24a"), (-4, 44, "#4aa8e8"), (14, 50, "#e84a4a"),
                                      (-16, 56, "#ffd24a"), (2, 70, "#e84a4a"), (-9, 84, "#4aa8e8"), (8, 90, "#ffd24a"))):
        on = 0.55 + 0.45 * math.sin(t * 3 + k * 1.3)
        p.setBrush(C(col, int(70 + 185 * on)))
        p.drawEllipse(QPointF(x + dx * 0.85, base - dy * h / 118), 3.2, 3.2)
    star = QPainterPath()
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        r = 8 if i % 2 == 0 else 3.4
        pt = QPointF(x + r * math.cos(a), base - h + 8 + r * math.sin(a))
        star.moveTo(pt) if i == 0 else star.lineTo(pt)
    star.closeSubpath()
    p.fillPath(star, C("#ffe27a"))
    p.restore()


def paint_wreath(p, x, y, r=15):
    p.save()
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(C("#1f6a38"), 6.5))
    p.drawEllipse(QPointF(x, y), r, r)
    p.setPen(QPen(C("#3a9a56"), 2.2, Qt.DotLine))
    p.drawEllipse(QPointF(x, y), r, r)
    p.setPen(Qt.NoPen)
    p.setBrush(C("#d83a3a"))
    for k in range(6):
        a = k * 1.1 + 0.4
        p.drawEllipse(QPointF(x + r * math.cos(a), y + r * math.sin(a)), 2, 2)
    p.fillRect(QRectF(x - 6, y + r - 4, 12, 5), C("#d83a3a"))                       # 蝴蝶結
    p.restore()


def paint_festival_wall(p, key, W, bt, top):
    """節日裝飾（牆上與後檯）：情人節＝愛心彩帶、玫瑰；萬聖節＝南瓜燈、蝙蝠、蜘蛛網；聖誕節＝聖誕樹、燈串、花圈"""
    p.save()
    p.setPen(Qt.NoPen)
    t = time.perf_counter()
    x0, x1 = 150, W - 20
    if key == "valentine":
        for off in (0, 7):
            path = _swag(p, x0, x1, -TOP_PAD + 8 + off, 22, QPen(C("#e8a0b0", 200 - off * 8), 1.6))
        for k in range(1, 13):
            hx, hy = _swag_pt(x0, x1, -TOP_PAD + 8, 22, k / 13)
            paint_heart(p, hx, hy + 6, 5.4, "#e83a5a" if k % 2 else "#ff8aa8")
        p.setPen(QPen(C("#3a7a3a"), 2))
        for dx in (-5, 0, 5):
            p.drawLine(QPointF(80 + dx * 0.5, bt), QPointF(80 + dx * 2, bt - 34))
        p.setPen(Qt.NoPen)
        for dx, dy, col in ((-10, 38, "#d83a4a"), (0, 46, "#e8566a"), (10, 36, "#c82a3a")):
            p.setBrush(C(col))
            p.drawEllipse(QPointF(80 + dx, bt - dy), 5.4, 5.4)
            p.setBrush(C("#ffffff", 60))
            p.drawEllipse(QPointF(80 + dx - 1.5, bt - dy - 1.5), 1.8, 1.8)
        p.fillPath(rrect(72, bt - 12, 88, bt, 3), vgrad(bt - 12, bt, [(0, C("#f2ece0")), (1, C("#c8c0b0"))]))
    elif key == "halloween":
        paint_cobweb(p, 0, -TOP_PAD, 54)
        for k, (bx, by, s) in enumerate(((330, -112, 1.0), (470, -122, 0.8), (700, -108, 1.1), (860, -120, 0.9))):
            paint_bat(p, bx, by + 3 * math.sin(t * 2 + k), s)
        paint_pumpkin(p, 76, bt, 1.15)
        paint_pumpkin(p, MENU_X1 - 4, bt, 0.9)
        _swag(p, x0, x1, -TOP_PAD + 6, 16, QPen(C("#3a2a4a"), 1.4))
        for k in range(1, 12):                                                                     # 橘色燈串
            lx, ly = _swag_pt(x0, x1, -TOP_PAD + 6, 16, k / 12)
            on = 0.6 + 0.4 * math.sin(t * 2.4 + k)
            g = QRadialGradient(lx, ly + 5, 11)
            g.setColorAt(0, C("#ffb030", int(130 * on)))
            g.setColorAt(1, C("#ffb030", 0))
            p.setBrush(g)
            p.drawEllipse(QPointF(lx, ly + 5), 11, 11)
            p.setBrush(C("#ffc860", int(150 + 105 * on)))
            p.drawEllipse(QPointF(lx, ly + 4), 2.6, 3.4)
    elif key == "christmas":
        paint_xmas_tree(p, 84, bt, 122)
        paint_wreath(p, 150, 168, 15)
        _swag(p, x0, x1, -TOP_PAD + 6, 20, QPen(C("#1f6a38"), 4))
        for k in range(1, 15):                                                                      # 燈串
            lx, ly = _swag_pt(x0, x1, -TOP_PAD + 6, 20, k / 15)
            col = ("#ff5a5a", "#ffd24a", "#5ac8ff", "#7aff8a")[k % 4]
            on = 0.5 + 0.5 * math.sin(t * 3 + k * 0.9)
            g = QRadialGradient(lx, ly + 5, 9)
            g.setColorAt(0, C(col, int(120 * on)))
            g.setColorAt(1, C(col, 0))
            p.setBrush(g)
            p.drawEllipse(QPointF(lx, ly + 5), 9, 9)
            p.setBrush(C(col, int(160 + 95 * on)))
            p.drawEllipse(QPointF(lx, ly + 4), 2.4, 3.2)
        for k in range(22):                                                                         # 窗外的雪
            sx = 22 + (k * 37) % 96
            sy = -88 + ((t * (14 + k % 5 * 4) + k * 53) % 290)
            p.setBrush(C("#ffffff", 200))
            p.drawEllipse(QPointF(sx + 3 * math.sin(t + k), sy), 1.6, 1.6)
    p.restore()


def paint_festival_front(p, key, W, top):
    """節日裝飾（前櫃檯檯面）：情人節＝愛心小卡、萬聖節＝南瓜糖果碗、聖誕節＝薑餅人與小聖誕樹"""
    p.save()
    p.setPen(Qt.NoPen)
    if key == "valentine":
        for hx, hy, s, col in ((26, top - 6, 5, "#e83a5a"), (40, top - 14, 4, "#ff8aa8"), (52, top - 5, 4.4, "#d83a4a")):
            paint_heart(p, hx, hy, s, col)
    elif key == "halloween":
        paint_pumpkin(p, 36, top, 0.7)
        p.setBrush(C("#4a2a6a"))
        p.drawEllipse(QPointF(100, top - 6), 14, 6)
        for k, col in enumerate(("#ffb030", "#7ad05a", "#e85aa8", "#ffb030")):
            p.setBrush(C(col))
            p.drawEllipse(QPointF(94 + k * 4, top - 12 - (k % 2) * 2), 2.4, 2.4)
    elif key == "christmas":
        paint_xmas_tree(p, 40, top, 52)
        p.setBrush(C("#b8743a"))                                                                    # 薑餅人
        p.drawEllipse(QPointF(96, top - 21), 4.2, 4.2)
        p.fillRect(QRectF(92, top - 17, 8, 11), C("#b8743a"))
        p.fillRect(QRectF(86, top - 16, 20, 3.4), C("#b8743a"))
        p.fillRect(QRectF(92, top - 7, 3, 7), C("#b8743a"))
        p.fillRect(QRectF(97, top - 7, 3, 7), C("#b8743a"))
        p.setBrush(C("#ffffff"))
        for dx, dy in ((-1.4, -22), (1.4, -22)):
            p.drawEllipse(QPointF(96 + dx, top + dy), 0.7, 0.7)
        p.drawEllipse(QPointF(96, top - 13), 0.9, 0.9)
        p.drawEllipse(QPointF(96, top - 10), 0.9, 0.9)
    p.restore()


RACK_KINDS = ("choc", "vanilla", "caramel", "pumpkin", "cream", "tonic", "cocoa", "oat", "soy", "almond")


def rack_positions(x0, x1):
    """配料架上每一件的中心 x：[(kind, cx)]，由左到右平均排開"""
    step = (x1 - x0 - 16) / len(RACK_KINDS)
    return [(kind, x0 + 8 + step * (i + 0.5)) for i, kind in enumerate(RACK_KINDS)]


def paint_ingredient_rack(p, x0, x1, y, items=True):
    """配料架：一塊木板（y 是板子上緣），上面站著配料——巧克力醬、香草糖漿、焦糖醬、南瓜醬、鮮奶油、通寧水、可可粉、燕麥奶、豆奶、杏仁奶；
    由左到右平均排開（營業模式咖啡機旁的出杯台上方、櫃檯畫面的後檯上方都用這個）"""
    p.save()
    p.setPen(Qt.NoPen)
    p.fillPath(rrect(x0, y, x1, y + 6, 2), vgrad(y, y + 6, [(0, C("#b98a5a")), (1, C("#6a4a2e"))]))
    for bx in (x0 + 10, x1 - 14):
        p.fillPath(rrect(bx, y + 6, bx + 4, y + 20, 1), C("#3a3632"))
    if items:                                   # items＝False：只畫板子，配料由 paint_rack_items 每幀畫（被拿去用的那件不在架上）
        for kind, cx in rack_positions(x0, x1):
            _rack_item(p, kind, cx, y)
    p.restore()


def _rack_item(p, kind, cx, base):
    """配料架上的一件（cx＝中心、base＝站的那條線）"""
    p.setPen(Qt.NoPen)
    sh = QColor(0, 0, 0, 60)
    p.setBrush(sh)
    p.drawEllipse(QPointF(cx + 1, base), 7, 1.6)
    if kind in ("choc", "vanilla", "caramel", "pumpkin", "ginger", "rose"):    # 擠瓶：瓶身加尖尖的瓶口
        body, cap = {"choc": ("#4a2a18", "#d83a3a"), "vanilla": ("#eadab2", "#e8c84a"),
                     "caramel": ("#c8883a", "#8a4a18"), "pumpkin": ("#e8872a", "#4a6a2a"),
                     "ginger": ("#a8683a", "#c83a3a"), "rose": ("#d0607a", "#f4efe2")}[kind]
        p.fillPath(rrect(cx - 6, base - 20, cx + 6, base, 3), vgrad(base - 20, base, [(0, C(body)), (1, C(body).darker(135))]))
        p.fillRect(QRectF(cx - 4.5, base - 14, 9, 7), C("#f4efe2", 235))                  # 標籤
        p.fillRect(QRectF(cx - 3, base - 12, 6, 1.2), C(body).darker(150))
        tip = QPainterPath()
        tip.addPolygon(QPolygonF([QPointF(cx - 3.5, base - 20), QPointF(cx + 3.5, base - 20), QPointF(cx + 1, base - 28), QPointF(cx - 1, base - 28)]))
        p.fillPath(tip, C(cap))
        p.fillRect(QRectF(cx - 4, base - 21, 8, 2), C(cap).darker(120))
        p.fillRect(QRectF(cx - 4.2, base - 18, 1.4, 14), C("#ffffff", 70))
    elif kind == "cream":                                                       # 鮮奶油槍：銀色鋼瓶＋藍色噴頭
        p.fillPath(rrect(cx - 5.5, base - 22, cx + 5.5, base, 3), hgrad(cx - 5.5, cx + 5.5, [(0, C("#7a8086")), (0.4, C("#f2f4f5")), (1, C("#6a7076"))]))
        p.fillRect(QRectF(cx - 5.5, base - 16, 11, 5), C("#f4efe2"))
        p.fillPath(rrect(cx - 3.5, base - 26, cx + 3.5, base - 21, 1.5), C("#5aa8d8"))
        p.fillRect(QRectF(cx - 1, base - 30, 2, 5), C("#5aa8d8"))
        p.fillRect(QRectF(cx + 1, base - 30, 5, 1.8), C("#5aa8d8"))
    elif kind == "tonic":                                                       # 通寧水：綠色玻璃瓶
        neck = QPainterPath()
        neck.addRect(QRectF(cx - 2, base - 28, 4, 10))
        p.fillPath(neck, C("#2f7a52", 235))
        p.fillPath(rrect(cx - 5.5, base - 20, cx + 5.5, base, 3.5), vgrad(base - 20, base, [(0, C("#3a9a6a", 235)), (1, C("#1f6a42", 235))]))
        p.fillRect(QRectF(cx - 5, base - 13, 10, 6), C("#f4efe2", 235))
        p.fillRect(QRectF(cx - 2.5, base - 11, 5, 1.4), C("#2f7a52"))
        p.fillRect(QRectF(cx - 2.5, base - 30, 5, 2.4), C("#c9ced3"))
        p.fillRect(QRectF(cx - 4.4, base - 18, 1.2, 14), C("#ffffff", 80))
    elif kind == "icecream":                                                    # 冰淇淋：圓桶加粉紅的蓋子
        p.fillPath(rrect(cx - 7, base - 15, cx + 7, base, 2.5), hgrad(cx - 7, cx + 7, [(0, C("#e8d8b8")), (0.5, C("#faf2de")), (1, C("#d0c0a0"))]))
        p.fillRect(QRectF(cx - 7, base - 10, 14, 4), C("#e8708a"))
        p.fillPath(rrect(cx - 7.5, base - 18, cx + 7.5, base - 14, 2), C("#c8506a"))
    elif kind in ("cocoa", "cinnamon"):                                         # 可可粉、肉桂粉：有孔的鐵罐
        cin = kind == "cinnamon"
        p.fillPath(rrect(cx - 5.5, base - 16, cx + 5.5, base, 2), hgrad(cx - 5.5, cx + 5.5, [(0, C("#8a4a22" if cin else "#5a3a22")), (0.4, C("#b8703a" if cin else "#8a5a38")), (1, C("#6a3818" if cin else "#4a2c18"))]))
        p.fillPath(rrect(cx - 6, base - 20, cx + 6, base - 15, 2), C("#c9ced3"))
        p.setBrush(C("#3a3f44"))
        for dx in (-2.5, 0, 2.5):
            p.drawEllipse(QPointF(cx + dx, base - 17.5), 0.7, 0.7)
        p.fillRect(QRectF(cx - 4, base - 11, 8, 5), C("#f4efe2", 225))
    else:                                                                       # 植物奶：燕麥／豆奶／杏仁，三角屋頂的紙盒
        body, band = {"oat": ("#efe3cc", "#c8a560"), "soy": ("#f3ead2", "#7aa05a"), "almond": ("#ebe2d5", "#a8744a"),
                      "milk": ("#f6f6f2", "#4a8ac8")}[kind]
        p.fillPath(rrect(cx - 6.5, base - 22, cx + 6.5, base, 1.5), hgrad(cx - 6.5, cx + 6.5, [(0, C(body)), (0.6, C(body).lighter(105)), (1, C(body).darker(110))]))
        roof = QPainterPath()
        roof.addPolygon(QPolygonF([QPointF(cx - 6.5, base - 22), QPointF(cx + 6.5, base - 22), QPointF(cx + 4, base - 28), QPointF(cx - 4, base - 28)]))
        p.fillPath(roof, C(body).darker(118))
        p.fillRect(QRectF(cx - 6.5, base - 15, 13, 5), C(band))
        p.setBrush(C("#ffffff", 200))
        p.drawEllipse(QPointF(cx, base - 12.5), 1.6, 1.6)


PAINT_X = (206, 396, 586, 776)   # 牆上掛畫的位置（左上角 x；y 是 PAINT_Y）：兩塊看板之間的牆
PAINT_Y = 6
PAINT_W, PAINT_H = 56, 44
LAMP_X = (305, 495, 685)         # 吊燈的位置（在掛畫之間）
CUP_STYLE = (None, None)         # 杯子圖案（decor.cup_style）：紙杯隔熱套與杯盤用，desk 每次畫櫃檯時設定


def set_cup_style(style):
    global CUP_STYLE
    CUP_STYLE = style


def paint_painting(p, kind, x, y, w=PAINT_W, h=PAINT_H):
    """一幅掛畫（木框＋米色襯紙＋畫），x、y 是外框左上角"""
    p.save()
    p.setPen(Qt.NoPen)
    p.fillRect(QRectF(x + 1.5, y + 2.5, w, h), C("#000000", 70))
    p.fillPath(rrect(x, y, x + w, y + h, 1.5), C("#6a4a2e"))
    p.fillRect(QRectF(x + 2.5, y + 2.5, w - 5, h - 5), C("#efe6d4"))
    ax, ay, aw, ah = x + 6, y + 6, w - 12, h - 12
    art = QRectF(ax, ay, aw, ah)
    p.setClipRect(art)
    if kind == "art_beans":
        p.fillRect(art, C("#2a1d14"))
        for i, (bx, by, ang) in enumerate(((0.25, 0.35, 30), (0.6, 0.3, -40), (0.45, 0.7, 70), (0.8, 0.72, 10))):
            p.save()
            p.translate(ax + aw * bx, ay + ah * by)
            p.rotate(ang)
            p.setBrush(C("#8a5530"))
            p.drawEllipse(QPointF(0, 0), 6.5, 4.4)
            p.setPen(QPen(C("#2a1d14"), 1))
            p.drawLine(QPointF(-5, 0), QPointF(5, 0))
            p.restore()
            p.setPen(Qt.NoPen)
    elif kind == "art_latte":
        p.fillRect(art, C("#d8c4a4"))
        cx, cy = ax + aw / 2, ay + ah / 2
        p.setBrush(C("#f6f0e4"))
        p.drawEllipse(QPointF(cx, cy), ah * 0.5, ah * 0.5)
        p.setBrush(C("#8a5a34"))
        p.drawEllipse(QPointF(cx, cy), ah * 0.38, ah * 0.38)
        p.setBrush(C("#f4e8d4"))
        for dy, s in ((-0.2, 0.17), (0.0, 0.2), (0.2, 0.15)):
            p.drawEllipse(QPointF(cx, cy + ah * dy), ah * s, ah * s * 0.55)
    elif kind == "art_hills":
        p.fillRect(art, vgrad(ay, ay + ah, [(0, C("#f2b88a")), (1, C("#f8e4c0"))]))
        p.setBrush(C("#fff0c8"))
        p.drawEllipse(QPointF(ax + aw * 0.7, ay + ah * 0.42), 6, 6)
        for col, base, amp in (("#8a9a7a", 0.62, 0.18), ("#5a7a5a", 0.78, 0.2)):
            path = QPainterPath()
            path.moveTo(ax, ay + ah)
            path.lineTo(ax, ay + ah * base)
            path.quadTo(ax + aw * 0.3, ay + ah * (base - amp), ax + aw * 0.55, ay + ah * base)
            path.quadTo(ax + aw * 0.8, ay + ah * (base + amp * 0.4), ax + aw, ay + ah * (base - amp * 0.3))
            path.lineTo(ax + aw, ay + ah)
            path.closeSubpath()
            p.fillPath(path, C(col))
    elif kind == "art_poster":                                                  # 復古咖啡海報：紅底、大杯子
        p.fillRect(art, C("#a8372a"))
        p.setBrush(C("#f2e4c4"))
        cup = QPainterPath()
        cup.addPolygon(QPolygonF([QPointF(ax + aw * 0.28, ay + ah * 0.4), QPointF(ax + aw * 0.72, ay + ah * 0.4),
                                  QPointF(ax + aw * 0.64, ay + ah * 0.85), QPointF(ax + aw * 0.36, ay + ah * 0.85)]))
        p.fillPath(cup, C("#f2e4c4"))
        p.setPen(QPen(C("#f2e4c4"), 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(ax + aw * 0.76, ay + ah * 0.55), aw * 0.08, ah * 0.1)
        for sx in (0.4, 0.5, 0.6):
            p.drawLine(QPointF(ax + aw * sx, ay + ah * 0.3), QPointF(ax + aw * (sx + 0.04), ay + ah * 0.14))
        p.setPen(Qt.NoPen)
        p.fillRect(QRectF(ax + aw * 0.2, ay + ah * 0.9, aw * 0.6, 2), C("#f2e4c4"))
    elif kind == "art_map":                                                     # 咖啡產地的世界地圖
        p.fillRect(art, C("#2e4a5a"))
        p.setBrush(C("#c8b890"))
        for bx, by, bw, bh in ((0.08, 0.2, 0.26, 0.4), (0.3, 0.55, 0.14, 0.34), (0.5, 0.2, 0.18, 0.3), (0.52, 0.45, 0.14, 0.4),
                               (0.72, 0.22, 0.22, 0.34), (0.8, 0.66, 0.1, 0.16)):
            p.drawRoundedRect(QRectF(ax + aw * bx, ay + ah * by, aw * bw, ah * bh), 4, 4)
        p.setBrush(C("#d8483a"))
        for dx, dy in ((0.36, 0.7), (0.58, 0.62), (0.6, 0.5), (0.2, 0.5), (0.82, 0.55)):
            p.drawEllipse(QPointF(ax + aw * dx, ay + ah * dy), 1.8, 1.8)
    elif kind == "art_clock":                                                   # 掛鐘：指針是現在的時間
        p.fillRect(art, C("#d8cdb4"))
        cx, cy, r = ax + aw / 2, ay + ah / 2, ah * 0.5
        p.setBrush(C("#f8f2e4"))
        p.setPen(QPen(C("#4a3220"), 2))
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(QPen(C("#4a3220"), 1))
        for i in range(12):
            a = math.radians(i * 30)
            p.drawLine(QPointF(cx + math.sin(a) * r * 0.78, cy - math.cos(a) * r * 0.78),
                       QPointF(cx + math.sin(a) * r * 0.92, cy - math.cos(a) * r * 0.92))
        lt = time.localtime()
        for ang, ln, wd in (((lt.tm_hour % 12 + lt.tm_min / 60) * 30, 0.5, 1.8), (lt.tm_min * 6, 0.75, 1.2)):
            a = math.radians(ang)
            p.setPen(QPen(C("#2a1a10"), wd, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx, cy), QPointF(cx + math.sin(a) * r * ln, cy - math.cos(a) * r * ln))
        p.setPen(Qt.NoPen)
    elif kind == "art_gold":                                                    # 金咖啡杯（挑戰限定）
        p.fillRect(art, vgrad(ay, ay + ah, [(0, C("#1c1610")), (1, C("#0e0a06"))]))
        glow = QRadialGradient(ax + aw / 2, ay + ah * 0.55, aw * 0.5)
        glow.setColorAt(0, C("#f0c860", 120))
        glow.setColorAt(1, C("#f0c860", 0))
        p.setBrush(glow)
        p.drawEllipse(QPointF(ax + aw / 2, ay + ah * 0.55), aw * 0.5, aw * 0.5)
        cup = QPainterPath()
        cup.addPolygon(QPolygonF([QPointF(ax + aw * 0.3, ay + ah * 0.42), QPointF(ax + aw * 0.7, ay + ah * 0.42),
                                  QPointF(ax + aw * 0.62, ay + ah * 0.82), QPointF(ax + aw * 0.38, ay + ah * 0.82)]))
        p.fillPath(cup, hgrad(ax, ax + aw, [(0, C("#a88030")), (0.5, C("#f6dc84")), (1, C("#a88030"))]))
        p.setPen(QPen(C("#e8c25a"), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(ax + aw * 0.74, ay + ah * 0.55), aw * 0.07, ah * 0.09)
        p.drawLine(QPointF(ax + aw * 0.5, ay + ah * 0.32), QPointF(ax + aw * 0.54, ay + ah * 0.16))
        p.setPen(Qt.NoPen)
    else:                                                                       # art_photo：泛黃的老照片
        p.fillRect(art, vgrad(ay, ay + ah, [(0, C("#c8aa80")), (1, C("#8a6c48"))]))
        p.setBrush(C("#5a4430"))
        p.drawRoundedRect(QRectF(ax + aw * 0.12, ay + ah * 0.22, aw * 0.26, ah * 0.5), 6, 6)
        for i, hh in enumerate((0.38, 0.5, 0.32)):
            fx = ax + aw * (0.5 + i * 0.16)
            p.drawEllipse(QPointF(fx, ay + ah * (0.78 - hh)), 3, 3)
            p.fillRect(QRectF(fx - 3, ay + ah * (0.78 - hh) + 3, 6, ah * hh), C("#5a4430"))
        p.fillRect(art, C("#000000", 28))
    p.restore()


def paint_plant(p, kind, x, y):
    """植物：plant_pot（小盆栽，x、y＝盆底中心）、plant_vase（乾燥花瓶，底中心）、plant_hang（吊蘭，x、y＝吊盆口中心）"""
    p.save()
    p.setPen(Qt.NoPen)
    if kind == "plant_pot":
        p.setBrush(C("#4a8a4a"))
        for ang, ln in ((-50, 17), (-25, 21), (0, 24), (25, 21), (50, 17)):
            p.save()
            p.translate(x, y - 14)
            p.rotate(ang)
            p.drawEllipse(QPointF(0, -ln / 2), 4.2, ln / 2)
            p.restore()
        pot = QPainterPath()
        pot.addPolygon(QPolygonF([QPointF(x - 12, y - 16), QPointF(x + 12, y - 16), QPointF(x + 9, y), QPointF(x - 9, y)]))
        p.fillPath(pot, vgrad(y - 16, y, [(0, C("#c4784a")), (1, C("#8a4a2a"))]))
        p.fillRect(QRectF(x - 13, y - 18, 26, 4), C("#d48a5a"))
    elif kind == "plant_vase":
        p.setPen(QPen(C("#8a7a5a"), 1.2))
        for dx, dy, col in ((-7, 38, "#d8b88a"), (-2, 46, "#e8d8b8"), (4, 40, "#c8a07a"), (9, 34, "#e8c8a0")):
            p.drawLine(QPointF(x + dx * 0.3, y - 22), QPointF(x + dx, y - dy))
        p.setPen(Qt.NoPen)
        for dx, dy, col in ((-7, 38, "#d8b88a"), (-2, 46, "#e8d8b8"), (4, 40, "#c8a07a"), (9, 34, "#e8c8a0")):
            p.setBrush(C(col))
            p.drawEllipse(QPointF(x + dx, y - dy), 4, 4)
        p.fillPath(rrect(x - 6, y - 26, x + 6, y, 4), vgrad(y - 26, y, [(0, C("#f2ece0")), (1, C("#c8c0b0"))]))
        p.fillRect(QRectF(x - 5, y - 26, 10, 2), C("#ffffff", 110))
    elif kind == "plant_cactus":                                                # 仙人掌：圓圓的主體加兩支手臂，盆底中心
        p.setBrush(C("#4f9a5a"))
        p.drawRoundedRect(QRectF(x - 5, y - 36, 10, 26), 5, 5)
        p.drawRoundedRect(QRectF(x - 13, y - 28, 6, 14), 3, 3)
        p.fillRect(QRectF(x - 13, y - 18, 10, 5), C("#4f9a5a"))
        p.drawRoundedRect(QRectF(x + 7, y - 32, 6, 16), 3, 3)
        p.fillRect(QRectF(x + 3, y - 20, 8, 5), C("#4f9a5a"))
        p.setPen(QPen(C("#2a5a32"), 0.8))
        for dy in (-30, -22, -14):
            p.drawLine(QPointF(x, y + dy), QPointF(x, y + dy + 5))
        p.setPen(Qt.NoPen)
        p.setBrush(C("#e86a8a"))
        p.drawEllipse(QPointF(x, y - 37), 2.6, 2.2)
        pot = QPainterPath()
        pot.addPolygon(QPolygonF([QPointF(x - 11, y - 12), QPointF(x + 11, y - 12), QPointF(x + 8, y), QPointF(x - 8, y)]))
        p.fillPath(pot, vgrad(y - 12, y, [(0, C("#d8d0c0")), (1, C("#a8a090"))]))
    elif kind == "plant_fern":                                                  # 蕨類：垂下來的長葉子，盆底中心
        p.setBrush(C("#3f8a4a"))
        for ang, ln in ((-62, 24), (-38, 30), (-14, 34), (12, 34), (38, 30), (62, 24)):
            p.save()
            p.translate(x, y - 12)
            p.rotate(ang)
            p.drawEllipse(QPointF(0, -ln / 2), 2.8, ln / 2)
            p.restore()
        pot = QPainterPath()
        pot.addPolygon(QPolygonF([QPointF(x - 11, y - 14), QPointF(x + 11, y - 14), QPointF(x + 8, y), QPointF(x - 8, y)]))
        p.fillPath(pot, vgrad(y - 14, y, [(0, C("#6a8aa8")), (1, C("#3a5a78"))]))
        p.fillRect(QRectF(x - 12, y - 16, 24, 3), C("#7a9ab8"))
    else:                                                                       # plant_hang
        p.setPen(QPen(C("#111111"), 1))
        p.drawLine(QPointF(x - 7, y - 40), QPointF(x - 9, y - 4))
        p.drawLine(QPointF(x + 7, y - 40), QPointF(x + 9, y - 4))
        p.setPen(Qt.NoPen)
        p.setBrush(C("#4a8a4a"))
        for dx, ln in ((-9, 34), (-4, 46), (3, 40), (8, 52), (0, 26)):
            for k in range(int(ln / 7)):
                p.drawEllipse(QPointF(x + dx + (k % 2) * 2 - 1, y + 4 + k * 7), 2.6, 4.4)
        bowl = QPainterPath()
        bowl.moveTo(x - 11, y - 4)
        bowl.lineTo(x + 11, y - 4)
        bowl.quadTo(x + 10, y + 10, x, y + 11)
        bowl.quadTo(x - 10, y + 10, x - 11, y - 4)
        p.fillPath(bowl, vgrad(y - 4, y + 11, [(0, C("#8a6440")), (1, C("#5a3e26"))]))
    p.restore()


def paint_lamps(p, kind, W):
    """吊燈：pendant（暖黃球燈）、industrial（黑色圓罩）；從天花板垂下來，亮光往下打"""
    p.save()
    p.setPen(Qt.NoPen)
    for x in LAMP_X:
        if kind == "pendant":
            glow = QRadialGradient(x, 74, 58)
            glow.setColorAt(0, C("#ffd9a0", 110))
            glow.setColorAt(1, C("#ffd9a0", 0))
            p.setBrush(glow)
            p.drawEllipse(QPointF(x, 74), 58, 58)
            p.setPen(QPen(C("#111111"), 1))
            p.drawLine(QPointF(x, -TOP_PAD), QPointF(x, 64))
            p.setPen(Qt.NoPen)
            p.setBrush(C("#ffe7b0"))
            p.drawEllipse(QPointF(x, 74), 10, 10)
            p.setBrush(C("#ffffff", 150))
            p.drawEllipse(QPointF(x - 3, 71), 3, 3)
        else:
            cone = QPainterPath()
            cone.addPolygon(QPolygonF([QPointF(x - 14, 60), QPointF(x + 14, 60), QPointF(x + 46, 150), QPointF(x - 46, 150)]))
            p.fillPath(cone, vgrad(60, 150, [(0, C("#ffd9a0", 80)), (1, C("#ffd9a0", 0))]))
            p.setPen(QPen(C("#111111"), 1))
            p.drawLine(QPointF(x, -TOP_PAD), QPointF(x, 34))
            p.setPen(Qt.NoPen)
            shade = QPainterPath()
            shade.addPolygon(QPolygonF([QPointF(x - 7, 34), QPointF(x + 7, 34), QPointF(x + 22, 60), QPointF(x - 22, 60)]))
            p.fillPath(shade, hgrad(x - 22, x + 22, [(0, C("#101010")), (0.4, C("#3a3a3c")), (1, C("#0a0a0a"))]))
            p.setBrush(C("#ffe7b0"))
            p.drawEllipse(QPointF(x, 60), 6, 3)
    p.restore()


def paint_fairy_lights(p, x0, x1, y, sag=14, swag=96):
    """星星燈串：一條條垂弧的細線，上面掛著暖黃色的小燈（x0～x1 之間，y 是掛點）"""
    p.save()
    n = max(1, int((x1 - x0) // swag))
    w = (x1 - x0) / n
    for i in range(n):
        a = x0 + i * w
        path = QPainterPath()
        path.moveTo(a, y)
        path.quadTo(a + w / 2, y + sag * 2, a + w, y)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#111111"), 0.9))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        for k in range(1, 6):
            pt = path.pointAtPercent(k / 6)
            glow = QRadialGradient(pt.x(), pt.y() + 2, 9)
            glow.setColorAt(0, C("#ffd9a0", 120))
            glow.setColorAt(1, C("#ffd9a0", 0))
            p.setBrush(glow)
            p.drawEllipse(QPointF(pt.x(), pt.y() + 2), 9, 9)
            p.setBrush(C("#fff0c0"))
            p.drawEllipse(QPointF(pt.x(), pt.y() + 2), 2.2, 2.2)
    p.restore()


def heart_path(cx, cy, r):
    """小愛心（杯子圖案用）：cx、cy 是中心，r 是半寬"""
    path = QPainterPath()
    path.moveTo(cx, cy + r * 0.9)
    path.cubicTo(QPointF(cx - r * 1.6, cy - r * 0.1), QPointF(cx - r * 0.6, cy - r * 1.3), QPointF(cx, cy - r * 0.4))
    path.cubicTo(QPointF(cx + r * 0.6, cy - r * 1.3), QPointF(cx + r * 1.6, cy - r * 0.1), QPointF(cx, cy + r * 0.9))
    return path


def paint_bean_bag(p, cx, base, key):
    """庫存咖啡豆的一小包（牛皮紙袋、折起來的上緣、產地顏色的標籤；精品豆標籤有金邊）；cx 是中心、base 是站的那條線"""
    w, h = 19, 27
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 80))
    p.drawEllipse(QPointF(cx + 1, base), w / 2, 1.8)
    p.fillPath(rrect(cx - w / 2, base - h + 4, cx + w / 2, base, 2.5),
               hgrad(cx - w / 2, cx + w / 2, [(0, C("#b88c56")), (0.45, C("#d4ac72")), (1, C("#a07a48"))]))
    p.fillRect(QRectF(cx - w / 2, base - h, w, 6), C("#8a6a40"))
    p.fillRect(QRectF(cx - w / 2, base - h, w, 1.4), C("#c8a870"))
    p.setPen(QPen(C("#6a4e2c"), 0.7))
    for k in range(5):
        p.drawLine(QPointF(cx - w / 2 + 1 + k * 4.2, base - h + 1.5), QPointF(cx - w / 2 + 3 + k * 4.2, base - h + 6))
    prem = key in beans.PREMIUM
    if prem:
        p.setPen(QPen(C("#e8c25a"), 1))
    else:
        p.setPen(Qt.NoPen)
    p.setBrush(C(ORIGIN_LOOK.get(key, "#8a6a4a")))
    p.drawRoundedRect(QRectF(cx - 6.5, base - 20, 13, 12), 1.5, 1.5)
    p.setPen(Qt.NoPen)
    p.setBrush(C("#ffffff", 200))
    p.save()
    p.translate(cx, base - 14)
    p.rotate(-25)
    p.drawEllipse(QPointF(0, 0), 2.1, 3)
    p.restore()
    p.restore()


def paint_neon_sign(p, x, y):
    """牆上的咖啡杯霓虹招牌（粉紅杯子、藍色蒸氣）；x、y 是左上角，大小約 96×66"""
    cup = QPainterPath()
    cup.moveTo(x + 20, y + 28)
    cup.lineTo(x + 20, y + 48)
    cup.quadTo(x + 22, y + 60, x + 38, y + 60)
    cup.quadTo(x + 54, y + 60, x + 56, y + 48)
    cup.lineTo(x + 56, y + 28)
    cup.closeSubpath()
    handle = QPainterPath()
    handle.moveTo(x + 56, y + 33)
    handle.cubicTo(QPointF(x + 72, y + 31), QPointF(x + 72, y + 50), QPointF(x + 55, y + 48))
    steam = QPainterPath()
    for i, sx in enumerate((x + 29, x + 38, x + 47)):
        steam.moveTo(sx, y + 22)
        steam.cubicTo(QPointF(sx - 5, y + 16), QPointF(sx + 5, y + 10), QPointF(sx, y + 3))
    p.save()
    p.setBrush(Qt.NoBrush)
    for col, path in (("#ff6ad5", cup), ("#ff6ad5", handle), ("#5ad4ff", steam)):
        for wdt, alpha in ((9, 28), (5, 60)):
            p.setPen(QPen(C(col, alpha), wdt, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(path)
        p.setPen(QPen(C("#ffffff", 235), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        p.setPen(QPen(C(col), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        p.setPen(QPen(C("#ffffff", 200), 1.1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
    p.restore()



DESSERT_SHOWN = 6        # 櫥窗裡一種甜點最多擺幾個（庫存再多也擺這麼多）


def dessert_layout(stock, slots):
    """櫥窗要擺的甜點（key 的 list，同一種排在一起）：每種最多 DESSERT_SHOWN 個，超過格數時從擺最多的那種開始減"""
    counts = {k: min(n, DESSERT_SHOWN) for k, n in stock.items() if n > 0}
    while sum(counts.values()) > slots:
        counts[max(counts, key=counts.get)] -= 1
    return [k for k in ingredients.DESSERTS for _ in range(counts.get(k, 0))]


def paint_dessert(p, kind, x, y):
    """一個甜點（櫥窗與商店圖示共用）：x 是中心、y 是放在架子上的底線"""
    p.setPen(Qt.NoPen)
    if kind == "croissant":                                             # 可頌
        p.setBrush(C("#c8883a"))
        p.drawEllipse(QPointF(x, y - 6), 11, 6)
        p.setPen(QPen(C("#8a5a22"), 0.8))
        for dx in (-5, 0, 5):
            p.drawLine(QPointF(x + dx - 1, y - 11), QPointF(x + dx + 1, y - 1))
        p.setPen(Qt.NoPen)
    elif kind == "cake":                                                # 蛋糕：草莓鮮奶油
        p.fillRect(QRectF(x - 9, y - 16, 18, 16), C("#f2e2c8"))
        p.fillRect(QRectF(x - 9, y - 16, 18, 4), C("#b0505a"))
        p.fillRect(QRectF(x - 9, y - 9, 18, 1.6), C("#e0a0a8"))
        p.setBrush(C("#d23a4a"))
        p.drawEllipse(QPointF(x, y - 18), 3, 3)
    elif kind == "muffin":                                              # 馬芬
        p.setBrush(C("#6a3a22"))
        p.drawEllipse(QPointF(x, y - 12), 9, 7)
        p.fillRect(QRectF(x - 7, y - 10, 14, 10), C("#d8a870"))
        p.setPen(QPen(C("#b88850"), 0.7))
        for dx in (-3.5, 0, 3.5):
            p.drawLine(QPointF(x + dx, y - 10), QPointF(x + dx, y))
        p.setPen(Qt.NoPen)
    else:                                                               # 餅乾：巧克力豆
        p.setBrush(C("#d9a65c"))
        p.drawEllipse(QPointF(x, y - 5), 10, 5)
        p.setBrush(C("#4a2a18"))
        for dx, dy in ((-4, -6), (2, -4), (5, -7), (-1, -3)):
            p.drawEllipse(QPointF(x + dx, y + dy), 1.4, 1.2)

class ShopRenderer:
    # ───────────── 出杯台（咖啡機畫面，場景座標） ─────────────
    def side_on(self):
        """營業模式的義式畫面：咖啡機右邊多一段出杯台，杯子放這裡（量杯在沖煮頭下接濃縮，拿過來倒）"""
        return self.business() and self.method == "espresso"

    def side_extra(self):
        """出杯台的寬度（雙頭機有兩個杯位）"""
        if not self.business():
            return 0
        return SIDE_W + (SIDE_W2 if self.machine.traits.groups > 1 else 0) + (self.machine.side_gap - 66) - self.machine.side_trim

    def side_spot(self, g=0):
        """出杯台上第 g 個杯位的杯底中心（場景座標）"""
        return self.machine.scene_w + self.machine.side_gap + g * SIDE_W2, FLOOR

    def paint_side_counter(self, p):
        """出杯台的吧台墊與上方的出餐架（背景圖層）"""
        if not self.side_on():
            return
        x0 = self.machine.scene_w + self.machine.rack_gap
        x1 = self.machine.scene_w + self.side_extra() - 6
        for g in range(1 + (self.machine.traits.groups > 1)):
            cx, base = self.side_spot(g)
            top = base - MAT_H                                          # 墊子上緣＝杯底（杯子站在墊子上）
            p.fillPath(rrect(cx - 60, top, cx + 60, base, 2), vgrad(top, base, [(0, C("#3a3c40")), (0.35, C("#25262a")),
                                                                                (1, C("#111213"))]))
            p.setPen(QPen(C("#46484c"), 0.8))
            for x in range(int(cx - 54), int(cx + 56), 6):
                p.drawLine(QPointF(x, top + 1.5), QPointF(x + 1.5, base - 1.5))
            p.setPen(Qt.NoPen)
        paint_ingredient_rack(p, x0, x1, SHELF_Y, items=False)          # 配料架的板子（配料每幀畫：做飲品要用到的會從架上拿走）

    def rack_in_use(self):
        """現在做的飲品正在用的配料（配料架上的 kind）：醬料擠瓶、可可粉篩網、鮮奶油槍、焦糖醬瓶、通寧水、植物奶——這幾件從架上拿去用"""
        used = set()
        tw = getattr(self, "twin", None)
        for ss in (self.session, tw.get("session") if tw else None):
            st = getattr(ss, "stage", None) if ss else None
            if st is None or getattr(ss, "waiting", False):
                continue
            name = st.name
            if name in ("cocoa", "whip", "caramel"):
                used.add({"whip": "cream"}.get(name, name))
            elif name == "pour":
                if st.vessel == "squeeze":
                    used.add(st.liquid)
                elif st.vessel == "tonic":
                    used.add("tonic")
            if name in ("heat", "steam", "pour") and getattr(st, "vessel", "pitcher") not in ("squeeze", "tonic", "jigger"):
                milk = getattr(getattr(ss, "dp", None), "milk_kind", None)
                if milk in ("oat", "soy", "almond"):
                    used.add(milk)
        return used & set(RACK_KINDS)

    def paint_rack_items(self, p):
        """營業模式咖啡機畫面的配料架上的配料（場景座標）：正在用的那件不在架上"""
        if not self.side_on():
            return
        x0 = self.machine.scene_w + self.machine.rack_gap
        x1 = self.machine.scene_w + self.side_extra() - 6
        gone = self.rack_in_use()
        p.save()
        for kind, cx in rack_positions(x0, x1):
            if kind not in gone:
                _rack_item(p, kind, cx, SHELF_Y)
        p.restore()

    def paint_pass_cups(self, p):
        """做好、還在等同一張單其他杯子的飲品：先放在櫃檯上（櫃檯畫面看得到，見 paint_ready_on_counter），咖啡機畫面不畫"""
        return

    def paint_ready_on_counter(self, p, top, limit_x):
        """櫃檯上等著一起送出去的杯子（縮小成跟 POS 相稱），從左邊排起；排不下（會蓋到交付中的杯子）就不畫"""
        if not self.ready:
            return
        total = sum(counter_gap(c) for c in self.ready)
        if CUPS_X + total > limit_x:
            return
        x = CUPS_X
        for c in self.ready:
            x += counter_gap(c) / 2
            p.save()
            p.translate(x, top + 1)
            p.scale(COUNTER_CUP_K, COUNTER_CUP_K)
            self.paint_ready_cup(p, c, 0.0, 0.0)
            p.restore()
            x += counter_gap(c) / 2

    # ───────────── 做好的杯子 ─────────────
    def take_cup(self, o):
        """營業模式一杯做完：把杯子連同杯中的咖啡拍成一張圖（cup.paint_back → 液體 → paint_front），杯子收起來。
        同一張單的杯子都好了，就排進櫃檯交付（pending_deliveries）；還沒好的放在出餐架上等"""
        cup = self.cup
        x1, y1, x2, y2 = cup.TL - 14, cup.T - 46, cup.TR + 34, cup.B + 8
        ratio = self.devicePixelRatioF() * self.scale_f
        img = QImage(int((x2 - x1) * ratio) + 1, int((y2 - y1) * ratio) + 1, QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(ratio)
        img.fill(Qt.transparent)
        q = QPainter(img)
        q.setRenderHint(QPainter.Antialiasing)
        q.translate(-x1, -y1)
        cup.paint_back(q)
        self.paint_liquid(q)
        self.paint_ice(q)
        self.paint_condensation(q)
        cup.paint_front(q)
        q.end()
        self.ready.append({"img": img, "off": (x1 - cup.CX, y1 - cup.B), "top": cup.TR - cup.TL, "h": cup.B - cup.T,
                           "handle": cup.handle, "paper": cup.paper, "z": cup.z, "mark": cup.mark(), "iced": cup.kind in ICED_CUPS, "to_go": o.to_go,
                           "whip": self.topping.get("whip", 0) > 0.05,
                           "order": o})
        if self._in_twin:
            self.cup = None                                   # 雙頭機的第二杯：右邊的杯位收走
        else:
            self.cup_away = True
        self.check_party(o.party or [o])

    def check_party(self, party):
        """同一張單的杯子都做好了：從出餐架拿下來，排進櫃檯交付"""
        if not all(x.state in ("done", "leaving") for x in party):
            return
        cups = [c for c in self.ready if any(c["order"] is x for x in party)]
        if not cups:
            return
        self.ready = [c for c in self.ready if all(c is not k for k in cups)]
        self.pending_deliveries.append({"cups": cups, "orders": list(party), "paid": True,
                                        "price": sum(x.price for x in party), "tip": sum(x.tip for x in party)})

    def paint_ready_cup(self, p, c, x, base, alpha=1.0):
        """一杯做好的飲品（拍好的圖）：外帶紙杯加杯蓋與隔熱套、外帶冰飲加圓頂蓋、內用有把手的放杯盤"""
        p.save()
        p.setOpacity(p.opacity() * alpha)
        if not c["to_go"] and c["handle"]:
            paint_saucer(p, x, base, c["top"] * 1.3)
        ox, oy = c["off"]
        p.drawImage(QPointF(x + ox, base + oy), c["img"])
        if c["paper"]:                                                      # 加鮮奶油的外帶熱飲：圓頂蓋罩住鮮奶油
            paint_paper_cup(p, x, base, c["paper"], c["z"], c.get("mark", ""), dome=c.get("whip", False))
        elif c["to_go"] and c["iced"]:
            paint_dome_lid(p, x, base - c["h"], c["top"])
        p.restore()

    # ───────────── 接單結帳（櫃檯畫面） ─────────────
    def start_checkout(self):
        """咖啡師接單：先在櫃檯讓排隊裡還沒付錢的客人一組一組刷卡（點單付錢），結完才開始做。咖啡師要等（busy）"""
        groups = []
        for x in [self.order] + self.queue:
            if x is None or x.state != "waiting" or x.paid:
                continue
            g = x.party or [x]
            if all(g is not y for y in groups):
                groups.append(g)
        parties = [{"orders": g, "cups": g, "price": sum(x.price for x in g)} for g in groups]
        if not parties:
            return
        self.checkout = {"parties": parties, "i": 0, "phase": "in", "t": 0.0, "k": 0.0}
        self.set_counter_view(True)
        self.set_frame_interval(16)

    def update_checkout(self, sdt):
        """接單結帳的時間軸（模擬時間）：in →（每一組）pay；刷卡時嗶一聲、收據印出來、飄出金額"""
        ck = self.checkout
        ck["t"] += sdt
        ck["k"] = k = clamp(ck["t"] / CHECKOUT_T[ck["phase"]], 0, 1)
        party = ck["parties"][ck["i"]]
        if ck["phase"] == "pay" and not party.get("paid") and k >= 0.45:
            party["paid"] = True
            for x in party["orders"]:
                x.paid = True
            self.sound.once("beep", 0.35)
            self.sound.once("coin", 0.45)
            self.reg_floats.append({"text": "+" + money(party["price"]), "tip": 0, "t": 0.0})
        if k < 1:
            return
        if ck["phase"] == "in":
            ck["phase"] = "pay"
        else:
            ck["i"] += 1
            if ck["i"] >= len(ck["parties"]):
                self.checkout = None                                        # 結完了：接著開始做（update_order）
                return
        ck["t"], ck["k"] = 0.0, 0.0

    # ───────────── 櫃檯交付（獨立畫面，不顯示咖啡機） ─────────────
    def start_delivery(self):
        """把排好的單一次帶到櫃檯：切到櫃檯畫面、放杯子、客人一位一位取走（取走後才評分），再切回咖啡機。咖啡師要等（busy）"""
        parties, self.pending_deliveries = self.pending_deliveries, []
        self.delivery = {"parties": parties, "i": 0, "phase": "in", "t": 0.0, "k": 0.0}
        self.set_counter_view(True)
        self.set_frame_interval(16)

    def reveal_party(self, party):
        """客人取餐後公布這張單的分數：寫進紀錄（成就、營業額）、POS 顯示星等、飄出小費、狀態列顯示客人的反應、
        點單紙蓋章；好幾杯的看平均"""
        shown = [x for x in party["orders"] if not x.revealed]
        for x in shown:
            x.revealed = True
            if x.rec is not None:
                self.save_cup(x.rec)
                x.rec = None
            if x is self.order and x.state == "done":
                x.t = 0.0                                                   # 點單紙現在才蓋章
        if not shown:
            return
        avg = sum(x.score for x in shown) / len(shown)
        party["score"] = avg
        tip = sum(x.tip for x in shown)
        if tip > 0:                                                         # 喝了才給小費
            self.reg_floats.append({"text": T("小費 +{m}", m=money(tip)), "tip": 0, "t": 0.0})
        if len(party["cups"]) >= 3:
            self.announce(self.stats.unlock("party_3"))
        last = shown[-1].result
        if last is not None:
            if len(shown) > 1:                                              # 好幾杯：「n 杯 平均分數」，反應看分數最低的那杯
                low = min(shown, key=lambda x: x.score)
                last = type(last)(last.drink, avg, T("{name}：{text}", name=T(low.name), text=low.reaction),
                                  last.milk, T("{n} 杯", n=len(shown)))
            self.result = last
            self.result_until = time.perf_counter() + RESULT_SHOW                # 評價顯示一陣子就收起來
        self.sound.once("ding_hi" if avg >= 80 else "ding_lo", 0.55)

    def flush_unpaid(self):
        """關掉程式時還沒結帳的杯子：直接寫進紀錄（不然做好的杯子會不見）"""
        groups = [c["order"] for c in self.ready]
        for d in self.pending_deliveries + (self.delivery["parties"] if self.delivery else []):
            groups += d["orders"]
        for x in groups:
            if not x.revealed and x.rec is not None:
                x.revealed = True
                self.save_cup(x.rec)
                x.rec = None

    def update_delivery(self, sdt):
        """櫃檯交付的時間軸（模擬時間：咖啡師在等，營業模擬要算進去）"""
        for f in self.reg_floats:
            f["t"] += sdt
        self.reg_floats = [f for f in self.reg_floats if f["t"] < FLOAT_SEC]
        d = self.delivery
        if d is None:
            return
        d["t"] += sdt
        d["k"] = k = clamp(d["t"] / DELIVERY_T[d["phase"]], 0, 1)
        party = d["parties"][d["i"]] if d["i"] < len(d["parties"]) else None
        if k < 1:
            return
        if d["phase"] == "in":
            d["phase"] = "place"
        elif d["phase"] == "place":
            d["phase"] = "pickup"
        elif d["phase"] == "pickup":
            self.reveal_party(party)                                        # 客人拿到飲品：公布分數
            self.seated += [random.uniform(*orders.SIT_TIME) for x in party["orders"] if not x.to_go]   # 內用的去坐
            if len(self.seated) >= self.seats():
                self.announce(self.stats.unlock("seats_full"))
            d["i"] += 1
            if d["i"] < len(d["parties"]):
                d["phase"] = "pickup"
            else:
                d["phase"] = "out"
                self.set_counter_view(self.idle_counter())                  # 沒客人等著做就留在櫃檯
        elif d["phase"] == "out":
            self.delivery = None
            return
        d["t"], d["k"] = 0.0, 0.0

    def festival_decor_key(self):
        """今天要掛的節日裝飾（情人節、萬聖節、聖誕節的期間內；佈置分頁的「節日裝飾」可以關掉），沒有就是 None"""
        return festivals.festival() if self.cfg.get("festival_decor", True) else None

    def decor_look(self):
        """(目前選用的裝潢, 套用後的配色)：設定檔 decor 改了或買了東西才重算"""
        key = (repr(self.cfg.get("decor")), len(self.stats.data["owned"]))
        cache = getattr(self, "_decor_cache", None)
        if cache is None or cache[0] != key:
            sel = decor.selection(self.cfg.get("decor"), self.stats.data["owned"])
            cache = self._decor_cache = (key, sel, decor.palette(STORE, sel))
        return cache[1], cache[2]

    def paint_room(self, p, W, top):
        """店面（照使用者的參考圖，配色跟遊戲一樣偏暗暖）：牆、左邊百葉窗、吊掛的菜單看板、
        後檯的咖啡機（遊戲裡的機型，店鋪頁可以選哪一台）；裝潢（decor.py）的牆面、看板、燈光、掛畫、植物也在這裡"""
        sel, pal = self.decor_look()
        p.fillRect(QRectF(0, -TOP_PAD, W, top + TOP_PAD), vgrad(-TOP_PAD, top - 64, [          # 牆：跟操作畫面的背景同一套，
            (0, C(pal["wall"][0])), (1, C(pal["wall"][1]))]))                               # 越往下越暗，跟檯面分得開
        if pal["wall_pat"] == "brick":                                                      # 紅磚牆：一排一排錯開的磚縫
            p.setPen(QPen(C("#000000", 80), 1))
            for i, by in enumerate(range(-TOP_PAD, top - 64, 14)):
                p.drawLine(QPointF(0, by), QPointF(W, by))
                for bx in range(17 * (i % 2), int(W), 34):
                    p.drawLine(QPointF(bx, by), QPointF(bx, by + 14))
            p.setPen(Qt.NoPen)
        # 左邊的窗與百葉
        p.fillPath(rrect(14, -96, 124, 214, 3), C("#1a1410"))
        p.fillRect(QRectF(20, -90, 98, 298), vgrad(-90, 208, [(0, C("#1c2a3e")), (1, C("#3a4a5e"))]))
        p.setPen(QPen(C(pal["blind"], 200), 3))
        for y in range(-86, 206, 9):
            p.drawLine(QPointF(20, y), QPointF(118, y))
        p.setPen(Qt.NoPen)
        # 吊掛的菜單看板（四塊；第二塊是熱賣前三，第一、三塊畫一杯飲品，第四塊是其他品項）
        title, top3 = self.stats.top_drinks(3)
        n, bw, bh = 4, 150, 70
        gap = (MENU_X1 - MENU_X0 - n * bw) / (n - 1)
        for i in range(n):
            bx = MENU_X0 + i * (bw + gap)
            by = -84
            p.setPen(QPen(C("#111111"), 1))
            for wx in (bx + 20, bx + bw - 20):
                p.drawLine(QPointF(wx, -TOP_PAD), QPointF(wx, by))
            p.setPen(Qt.NoPen)
            light = pal["board_light"]
            fw = 5 if pal["frame"] else 3                                   # 木框看板的框比較寬
            if pal["neon"]:                                                 # 霓虹看板：粉紅的發光邊框
                for wdt, alpha in ((10, 26), (6, 60)):
                    p.setPen(QPen(C(pal["neon"], alpha), wdt))
                    p.drawRoundedRect(QRectF(bx - 2, by - 2, bw + 4, bh + 4), 4, 4)
                p.setPen(Qt.NoPen)
            p.fillPath(rrect(bx - fw, by - fw, bx + bw + fw, by + bh + fw, 4), C(pal["frame"] or "#0e0d0c"))
            if pal["neon"]:
                p.setPen(QPen(C(pal["neon"]), 1.6))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(QRectF(bx - 1, by - 1, bw + 2, bh + 2), 3, 3)
                p.setPen(Qt.NoPen)
            p.fillPath(rrect(bx, by, bx + bw, by + bh, 2), C(pal["board2"] if light else pal["board"]))
            ink = C("#3a2a1e") if light else C("#efe6d4")
            sub = C("#7a6a56") if light else C("#c8b8a0")
            if i in (0, 2):                                                 # 品項清單
                keys = [k for k, _n in top3] if i == 0 and top3 else ["espresso", "americano", "latte", "cappuccino"]
                head = T(title) if i == 0 and top3 else "COFFEE"
                if i == 2:
                    keys, head = ["iced_americano", "iced_latte", "mocha", "flat_white"], "MILK & ICE"
                f = QFont(self.ui, 6.5)
                f.setBold(True)
                p.setPen(C(pal["accent"]))
                self.fit_text(p, QRectF(bx + 6, by + 3, bw - 12, 12), head, f, Qt.AlignCenter)
                rf = QFont(self.ui, 5.5)
                for j, k in enumerate(keys[:4]):
                    y = by + 17 + j * 12.5
                    p.setPen(ink)
                    self.fit_text(p, QRectF(bx + 8, y, bw - 56, 11), T(DRINKS[k]["name"]), rf)
                    p.setPen(sub)
                    self.fit_text(p, QRectF(bx + bw - 48, y, 40, 11), money(orders.PRICES.get(k, orders.FESTIVAL_PRICE)),
                                  rf, Qt.AlignRight | Qt.AlignVCenter)
            else:                                                           # 一杯飲品的圖＋品名
                k = (top3[0][0] if top3 else "latte") if i == 1 else "iced_latte"
                pm = drink_icon(k, 52, True, 2.0)
                p.drawPixmap(QRectF(bx + 8, by + 9, 52, 52), pm, QRectF(0, 0, pm.width(), pm.height()))
                f = QFont(self.ui, 7)
                f.setBold(True)
                p.setPen(ink)
                self.fit_text(p, QRectF(bx + 64, by + 18, bw - 70, 14), T(DRINKS[k]["name"]), f)
                p.setPen(sub)
                self.fit_text(p, QRectF(bx + 64, by + 34, bw - 70, 12), money(orders.PRICES.get(k, orders.FESTIVAL_PRICE)),
                              QFont(self.ui, 6.5))
        p.setPen(Qt.NoPen)
        # 後檯：店鋪頁選的咖啡機（遊戲裡的機型），獨立磨豆機的機型旁邊放一台磨豆機
        bt = top - 64
        p.fillRect(QRectF(0, bt, W, top - bt), vgrad(bt, bt + (WIN_H - FLOOR), [   # 跟操作畫面的檯面同一套（paint_window_backdrop）
            (0, C("#4a3a30")), (0.04, C("#3a2d25")), (1, C("#1e1814"))]))
        self.paint_back_drawers(p, 10, self.case_left(W) - 4, bt + 10, top, pal)
        m = self.showcase_machine()
        img, rect = self.showcase_place(m, sel, W, bt)
        p.save()
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(rect, img)
        p.restore()
        self.paint_back_gear(p, W, bt)
        self.paint_decor_wall(p, W, top, sel, bt)
        fest = self.festival_decor_key()
        if fest:
            paint_festival_wall(p, fest, W, bt, top)

    def paint_decor_wall(self, p, W, top, sel, bt):
        """牆上與後檯的裝潢：掛畫、吊燈、霓虹招牌、植物（後檯的小盆栽、天花板的吊蘭）"""
        for (x, kind) in zip(PAINT_X, sel["paintings"]):
            paint_painting(p, kind, x, PAINT_Y)
        if sel["lighting"] in ("pendant", "industrial"):
            paint_lamps(p, sel["lighting"], W)
        elif sel["lighting"] == "fairy":
            paint_fairy_lights(p, 150, W - 150, -96)
        elif sel["lighting"] == "neon_sign":
            paint_neon_sign(p, W - 150, 72)
        if "plant_pot" in sel["plants"]:
            paint_plant(p, "plant_pot", 48, bt)                              # 後檯左邊（窗下面）
        if "plant_cactus" in sel["plants"]:
            paint_plant(p, "plant_cactus", 100, bt)
        if "plant_hang" in sel["plants"]:
            paint_plant(p, "plant_hang", 146, -52)

    def paint_decor_counter(self, p, W, top, sel):
        """前櫃檯檯面上的裝潢：乾燥花瓶"""
        if "plant_vase" in sel["plants"]:
            paint_plant(p, "plant_vase", 66, top)
        if "plant_fern" in sel["plants"]:
            paint_plant(p, "plant_fern", 124, top)

    def paint_back_drawers(self, p, x0, x1, y0, y1, pal):
        """後檯檯面下的收納抽屜（立面，下緣被前櫃檯擋住）：預設是暖木抽屜＋黃銅把手（使用者選的 A 方案），配色看「後檯櫃子」裝潢（pal 的 cab、cab_line、handle）"""
        p.setPen(Qt.NoPen)
        p.fillRect(QRectF(x0, y0 - 2, x1 - x0, 2), C("#000000", 90))         # 檯面下緣的陰影
        n = max(1, round((x1 - x0) / 96))
        w = (x1 - x0) / n
        for i in range(n):
            a, b = x0 + i * w + 2, x0 + (i + 1) * w - 2
            p.fillPath(rrect(a, y0 + 2, b, y1 + 4, 2), vgrad(y0, y1, [(0, C(pal["cab"][0])), (1, C(pal["cab"][1]))]))
            p.fillRect(QRectF(a + 4, y0 + 6, b - a - 8, 1), C(pal["cab_line"], 160))   # 面板倒角的亮線
            cx = (a + b) / 2
            p.fillPath(rrect(cx - 14, y0 + 13, cx + 14, y0 + 17, 2), C(pal["handle"]))  # 黃銅把手
            p.fillRect(QRectF(cx - 14, y0 + 17, 28, 1), C("#000000", 70))

    def showcase_machine(self):
        """櫃檯畫面後檯擺的咖啡機：店鋪頁指定的營業用咖啡機（隨機或還沒解鎖就是上一杯用的那台）"""
        key = self.showcase
        if key in MACHINES and self.machine_open(key):
            return MACHINES[key]
        return self.machine

    def showcase_image(self, m, tint=None):
        """後檯的整組（獨立磨豆機、咖啡機、右邊的配料架）照咖啡機畫面的比例畫成的圖與機身範圍 (圖, QRect)；依機型、升級與烤漆顏色快取"""
        key = (m.key, tuple(sorted(self.stats.data.get("owned", []))), tint)
        cache = getattr(self, "_showcase_cache", None)
        if cache is None or cache[0] != key:
            from .gear_icons import scene_image
            res = scene_image(self, m)
            self._showcase_cache = cache = (key, res)
        return cache[1]

    def showcase_place(self, m, sel, W, bt):
        """後檯那組（磨豆機、咖啡機、配料架）的圖與擺放的範圍 (圖, QRectF)：整組左緣在窗的右邊、右限在 POS 螢幕左邊，
        大小以機身高 118 以內為準（磨豆機、配料架照同一個比例縮，整組塞得進窗與 POS 之間）；站在後檯的桌面上（桌面是 bt～bt+10）"""
        img, mach, ground = self.showcase_image(m, decor.machine_tint(sel))
        left, right = 150, self.pos_x(W) - 75 - 14                        # POS 螢幕寬 150，再留一點
        k = min(118 / max(1, mach.height()), 250 / max(1, mach.width()), (right - left) / max(1, img.width()))
        return img, QRectF(left, bt + 0.5 - ground * k, img.width() * k, img.height() * k)

    def layout_preview(self, width, dpr=1.0):
        """櫃檯畫面整張畫成一張圖（紀錄視窗「佈置」分頁的預覽）：寬度 width 邏輯像素，圖本身依 dpr 產生"""
        from PySide6.QtGui import QImage
        W, H = self._scene_w, WIN_H + TOP_PAD
        k = width / W
        img = QImage(int(W * k * dpr), int(H * k * dpr), QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(C("#1b1715"))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.scale(k, k)
        p.translate(0, TOP_PAD)
        self.paint_counter(p)
        p.end()
        return img

    def back_gear_shown(self):
        """POS 後方檯面要擺出來的新解鎖設備（店鋪等級解鎖了、右鍵「後檯顯示新設備」沒關掉的），依解鎖順序"""
        off = self.cfg.get("back_gear_off", [])
        return [k for k in BACK_GEAR if k not in off and self.method_open(k)]

    def back_gear_images(self, kinds):
        """後檯設備的圖 {key: 圖}（手沖旁邊一定有手沖磨豆機）：整組依 kinds 快取"""
        cache = getattr(self, "_back_gear_cache", None)
        if cache is None or cache[0] != tuple(kinds):
            from .gear_icons import station_image
            imgs = {}
            for k in kinds:
                imgs[k] = station_image(self, k)
                if k == "pourover":
                    imgs["grinder"] = station_image(self, "grinder")
            self._back_gear_cache = cache = (tuple(kinds), imgs)
        return cache[1]

    def paint_back_gear(self, p, W, bt):
        """POS 後方的後檯：新解鎖的沖煮設備（手沖＋磨豆機、冰滴塔、摩卡壺、虹吸壺）從右邊排起，站在後檯桌面上；
        POS 螢幕與右邊的甜點櫃在前面，會擋住一部分（像是放在它們後面）"""
        kinds = self.back_gear_shown()
        if not kinds:
            return
        imgs = self.back_gear_images(kinds)
        order = [k for k in ("pourover", "grinder", "colddrip", "moka", "siphon") if k in imgs]
        left, right = self.pos_x(W) - 40, W - 24
        gap = 12
        k = min(0.62, (right - left - gap * (len(order) - 1)) / max(1, sum(imgs[o].width() for o in order)))
        hmax = 112
        k = min(k, *(hmax / max(1, imgs[o].height()) for o in order))
        x = right
        p.save()
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        for o in reversed(order):
            im = imgs[o]
            w, h = im.width() * k, im.height() * k
            x -= w
            p.drawImage(QRectF(x, bt + 1 - h, w, h), im)
            x -= gap
        p.restore()

    def counter_left(self, W):
        """前櫃檯的左端（整排櫃檯）"""
        return 10

    def case_left(self, W):
        """前櫃檯右段甜點玻璃櫃的左端"""
        return W - CASE_IN

    def pos_x(self, W):
        """POS 大螢幕的中心 x（在甜點櫃左邊，刷卡機在它右邊）"""
        return self.case_left(W) - 128

    def paint_shop_stars(self, p, x, y):
        """招牌店名下的星級評鑑（Lv.10 之後）：五顆星依小數填色；近期訂單不夠時寫「評鑑中」"""
        if self.shop_level() < growth.MAX_LEVEL:
            return
        r = self.star_rating()
        if r is None:
            f = QFont(self.ui, 6.5)
            p.setFont(f)
            p.setPen(C(self.decor_look()[1]["logo"], 150))
            p.drawText(QRectF(x, y - 7, 200, 14), Qt.AlignLeft | Qt.AlignVCenter, T("評鑑中…"))
            p.setPen(Qt.NoPen)
            return
        paint_stars(p, x, y, 8.5, r)

    def paint_counter_body(self, p, W, top):
        """整排前櫃檯：木檯面、前板（印店名）、底部燈條、右段甜點玻璃櫃（檯面上是玻璃櫃，前板是展示窗）、木地板。
        回傳 (左端, 杯子開始的 x)"""
        sel, pal = self.decor_look()
        x0, x1 = self.counter_left(W), W - 10
        p.fillRect(QRectF(0, WIN_H - 22, W, 22), vgrad(WIN_H - 22, WIN_H, [(0, C(pal["floor"][0])), (1, C(pal["floor"][1]))]))
        if pal["floor_pat"] == "check":                                     # 黑白格磁磚
            for i, fx in enumerate(range(0, int(W) + 22, 22)):
                p.fillRect(QRectF(fx, WIN_H - 22, 22, 11), C(pal["floor"][i % 2]))
                p.fillRect(QRectF(fx, WIN_H - 11, 22, 11), C(pal["floor"][(i + 1) % 2]))
        else:
            p.setPen(QPen(C("#000000", 50), 1))
            for x in range(0, int(W), 60):
                p.drawLine(QPointF(x, WIN_H - 22), QPointF(x - 14, WIN_H))
        p.setPen(Qt.NoPen)
        front = [(0, C(pal["front"][0])), (1, C(pal["front"][1]))]
        p.fillRect(QRectF(x0, top + 10, x1 - x0, WIN_H - 30 - top - 10), vgrad(top + 10, WIN_H - 30, front))
        p.setPen(QPen(C("#000000", 36), 1))                                  # 直紋木板
        for x in range(int(x0) + 18, int(x1), 24):
            p.drawLine(QPointF(x, top + 12), QPointF(x, WIN_H - 32))
        p.setPen(Qt.NoPen)
        glow = QLinearGradient(0, WIN_H - 34, 0, WIN_H - 18)               # 底部燈條
        glow.setColorAt(0, C("#ffd9a0", 120))
        glow.setColorAt(1, C("#ffd9a0", 0))
        p.fillRect(QRectF(x0, WIN_H - 32, x1 - x0, 14), glow)
        p.fillRect(QRectF(x0, WIN_H - 32, x1 - x0, 2), C("#ffe2b0", 160))
        f = QFont(self.ui, 15)                                              # 店名
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 3)
        p.setFont(f)
        p.setPen(C(pal["logo"]))
        p.drawText(QRectF(x0 + 36, top + 30, 300, 30), Qt.AlignLeft | Qt.AlignVCenter, "CAFÉ DESK")
        self.paint_shop_stars(p, x0 + 38, top + 66)
        p.setPen(Qt.NoPen)
        p.fillPath(rrect(x0 - 4, top, x1 + 4, top + 12, 2), vgrad(top, top + 12, [(0, C(pal["top"][0])), (1, C(pal["top"][1]))]))
        # 甜點玻璃櫃：檯面上的玻璃櫃＋前板的展示窗
        cx0, cx1 = self.case_left(W), x1 - 14
        p.fillPath(rrect(cx0, top - 74, cx1, top, 4), C("#dfeef4", 34))
        p.setPen(QPen(C("#ffffff", 120), 1.1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(rrect(cx0, top - 74, cx1, top, 4))
        p.setPen(Qt.NoPen)
        p.fillRect(QRectF(cx0 - 2, top - 77, cx1 - cx0 + 4, 4), C(pal["shelf"]))
        p.fillRect(QRectF(cx0, top + 18, cx1 - cx0, 72), vgrad(top + 18, top + 90, [(0, C("#2a2622")), (1, C("#1a1714"))]))
        warm = QLinearGradient(0, top + 18, 0, top + 40)
        warm.setColorAt(0, C("#ffd9a0", 70))
        warm.setColorAt(1, C("#ffd9a0", 0))
        p.fillRect(QRectF(cx0, top + 18, cx1 - cx0, 22), warm)
        p.setPen(QPen(C("#ffffff", 70), 1))
        p.drawRect(QRectF(cx0, top + 18, cx1 - cx0, 72))
        p.setPen(Qt.NoPen)
        ys = (top - 42, top - 6)
        for y in ys:
            p.fillRect(QRectF(cx0 + 4, y, cx1 - cx0 - 8, 2.5), C("#c8c0b0", 200))
        per = int((cx1 - cx0 - 30) // 30) + 1                               # 一層擺幾個
        shown = dessert_layout(self.dessert_stock(), per * len(ys))
        if not shown:
            p.setFont(QFont(self.ui, 7))
            p.setPen(C("#5a5448", 200))
            p.drawText(QRectF(cx0, top - 74, cx1 - cx0, 70), Qt.AlignCenter, T("櫥窗是空的：到商店「甜點」進貨"))
            p.setPen(Qt.NoPen)
        for i, kind in enumerate(shown):                                    # 有庫存的甜點才擺（一種最多擺 DESSERT_SHOWN 個）
            paint_dessert(p, kind, cx0 + 16 + 30 * (i % per), ys[i // per])
        self.paint_bean_window(p, cx0, cx1, top)
        return x0, CUPS_X

    def bean_window_items(self):
        """右下櫥窗要擺的咖啡豆 [(產地, 庫存包數, 是不是正在開的那包)]：有庫存的、加上正在用的那包，最多 BEAN_SLOTS 種"""
        cur = self.bag["origin"]
        items = [(k, self.bean_stock(k), k == cur) for k in beans.ORIGINS if self.bean_stock(k) > 0 or k == cur or k in self.shelf]
        return items[:BEAN_SLOTS]

    def paint_bean_window(self, p, cx0, cx1, top):
        """前板的右下展示窗：目前庫存的咖啡豆（兩層架子，每種一包加上包數）；客人指定精品豆時只會從這裡有的挑"""
        p.setPen(Qt.NoPen)
        ys = (top + 50, top + 86)
        for y in ys:
            p.fillRect(QRectF(cx0 + 4, y, cx1 - cx0 - 8, 2.5), C("#c8c0b0", 200))
        items = self.bean_window_items()
        if not items:
            p.setFont(QFont(self.ui, 7))
            p.setPen(C("#d8ccb8", 170))
            p.drawText(QRectF(cx0, top + 18, cx1 - cx0, 72), Qt.AlignCenter, T("店裡還沒有庫存的豆子"))
            p.setPen(Qt.NoPen)
            return
        per = BEAN_SLOTS // 2
        slot = (cx1 - cx0 - 16) / per
        small, tiny = QFont(self.ui, 6.5), QFont(self.ui, 5.5)
        small.setBold(True)
        for i, (key, n, cur) in enumerate(items):
            x = cx0 + 8 + slot * (i % per)
            y = ys[i // per]
            paint_bean_bag(p, x + 14, y, key)
            p.setFont(small)
            p.setPen(C("#f0e6d2"))
            p.drawText(QRectF(x + 26, y - 20, slot - 28, 10), Qt.AlignLeft | Qt.AlignVCenter, f"×{n}")
            if cur:
                p.setFont(tiny)
                p.setPen(C("#ffd27a"))
                self.fit_text(p, QRectF(x + 26, y - 10, slot - 26, 9), T("開封中"), tiny)
            p.setPen(Qt.NoPen)

    def paint_counter(self, p):
        """櫃檯畫面（場景座標）：木質櫃檯、現代 POS（平板、刷卡機、收據機）、做好的杯子"""
        W = self._scene_w
        top = COUNTER_TOP
        p.save()
        p.setPen(Qt.NoPen)
        self.paint_room(p, W, top)                                          # 店面：牆、窗、菜單看板、層架、後檯
        x0, cups_x = self.paint_counter_body(p, W, top)                     # 整排前櫃檯（右段是甜點櫃）
        sel = self.decor_look()[0]
        self.paint_decor_counter(p, W, top, sel)
        fest = self.festival_decor_key()
        if fest:
            paint_festival_front(p, fest, W, top)
        set_cup_style(decor.cup_style(sel))                                 # 紙杯隔熱套與杯盤的圖案
        self.paint_pos(p, W, top)
        # 杯子
        d = self.delivery
        deliver_x = self.seat_sign_left(W) - 8
        if d is not None:
            deliver_x -= sum(counter_gap(cc) for pp in d["parties"] for cc in pp["cups"])
        self.paint_ready_on_counter(p, top, deliver_x - 6)                  # 做好還在等同一張單其他杯子的飲品先放在櫃檯上
        if d is not None:
            allc = [cc for pp in d["parties"] for cc in pp["cups"]]
            cups_x = max(cups_x, self.seat_sign_left(W) - 8 - sum(counter_gap(cc) for cc in allc))   # 座位小黑板左邊，靠右排
            for j, party in enumerate(d["parties"]):
                if j < d["i"]:
                    continue                                                # 已經拿走了
                for n, c in enumerate(party["cups"]):
                    before = [cc for pp in d["parties"][:j] for cc in pp["cups"]] + party["cups"][:n]
                    x = cups_x + sum(counter_gap(cc) for cc in before) + counter_gap(c) / 2   # 依杯子寬度排（杯盤不疊在一起）
                    a, dx, dy = 1.0, 0.0, 0.0
                    if d["phase"] == "in":
                        a = 0.0
                    elif d["phase"] == "place":                             # 從左邊滑上櫃檯
                        e = d["k"] * d["k"] * (3 - 2 * d["k"])
                        a, dx = e, -60 * (1 - e)
                    elif d["phase"] == "pickup" and j == d["i"]:            # 客人拿起來帶走
                        a, dx, dy = 1 - d["k"], 18 * d["k"], -30 * d["k"]
                    elif d["phase"] == "out":
                        a = 0.0
                    if a > 0.01:                                            # 縮小成跟 POS 相稱的真實大小
                        p.save()
                        p.translate(x + dx, top + 1 + dy)
                        p.scale(COUNTER_CUP_K, COUNTER_CUP_K)
                        self.paint_ready_cup(p, c, 0.0, 0.0, a)
                        p.restore()
        # 收錢時飄出來的金額
        px = self.pos_x(W)                                                  # 金額飄在店員的大螢幕上面
        for fl in self.reg_floats:
            k = fl["t"] / FLOAT_SEC
            a = clamp(min(k / 0.12, (1 - k) / 0.35), 0, 1)
            y = top - 152 - 26 * k
            ff = QFont(self.ui, 11)
            ff.setBold(True)
            p.setFont(ff)
            p.setPen(C("#ffd27a", int(255 * a)))
            p.drawText(QRectF(px - 80, y - 15, 160, 16), Qt.AlignCenter, fl["text"])
            if fl["tip"] > 0:
                p.setFont(QFont(self.ui, 9))
                p.setPen(C("#f6e6b0", int(255 * a)))
                p.drawText(QRectF(px - 80, y + 2, 160, 14), Qt.AlignCenter, T("小費 +{m}", m=money(fl["tip"])))
        p.restore()

    def pos_pending(self):
        """櫃檯畫面沒在結帳時：目前這位客人點的單（還在等、還沒開始做）給 POS 顯示；沒有就 None"""
        o = self.order
        if not self.business() or o is None or o.state != "waiting" or o.paid:
            return None
        group = o.party or [o]
        return {"orders": group, "cups": group, "price": sum(x.price for x in group), "pending": True}

    def paint_pos(self, p, W, top):
        """POS（場景座標）：立架上的大螢幕（品項、合計、付款狀態與小費、結帳後的評分；底下是收據機）、刷卡機；
        在甜點櫃左邊"""
        d, ck = self.delivery, self.checkout
        party = None
        if ck is not None:                                                  # 接單結帳：這一組點了什麼、刷卡
            party = ck["parties"][min(ck["i"], len(ck["parties"]) - 1)]
        elif d is not None and d["phase"] in ("pickup", "out"):            # 取餐：這一組（取走後顯示評分）
            party = d["parties"][min(d["i"], len(d["parties"]) - 1)]
            if d["phase"] == "pickup" and d["i"] > 0 and "score" not in party:
                party = d["parties"][d["i"] - 1]                            # 前一組的評分留著，直到這一組也取走
        if party is None:
            party = self.pos_pending()                                      # 客人剛點單（還沒結帳）：POS 顯示點了什麼
        paid = bool(party and party.get("paid"))
        cx, sw, sh = self.pos_x(W), 150, 104                                # 店員的大螢幕
        pl = decor.pos_look(self.decor_look()[0])                           # 選用的 POS 配色（decor.POS_LOOK）
        sy = top - 34 - sh
        rx = cx - 34                                                        # 收據機：在大螢幕下面
        p.fillPath(rrect(rx - 24, top - 26, rx + 24, top, 5), vgrad(top - 26, top, [(0, C(pl["printer"][0])), (1, C(pl["printer"][1]))]))
        p.fillRect(QRectF(rx - 14, top - 26, 28, 2), C("#0a0a0b"))
        if ck is not None and paid:                                         # 收據從出紙口捲出來，垂在收據機前面
            k = clamp((ck["k"] - 0.45) / 0.4, 0, 1) if ck["phase"] == "pay" else 1.0
            if k > 0.02:
                p.fillRect(QRectF(rx - 12, top - 27, 24, 4), C("#fbf8f0"))
                p.fillRect(QRectF(rx - 12, top - 24, 24, 22 * k), C("#fbf8f0"))
                p.setPen(QPen(C("#9a8a76"), 0.7))
                for i in range(int(22 * k // 5)):
                    yy = top - 20 + i * 5
                    p.drawLine(QPointF(rx - 8, yy), QPointF(rx + (8 if i % 2 else 2), yy))
                p.setPen(Qt.NoPen)
        p.fillPath(rrect(cx + 10, top - 6, cx + 50, top, 2), C(pl["stand"][0]))  # 立架（偏右，讓出收據機）
        p.fillRect(QRectF(cx + 26.5, top - 34, 7, 30), C(pl["stand"][1]))
        p.fillPath(rrect(cx - sw / 2 - 4, sy - 4, cx + sw / 2 + 4, sy + sh + 4, 7), C(pl["bezel"]))
        p.fillPath(rrect(cx - sw / 2, sy, cx + sw / 2, sy + sh, 3), vgrad(sy, sy + sh, [(0, C(pl["screen"][0])), (1, C(pl["screen"][1]))]))
        f = QFont(self.ui, 8)
        f.setBold(True)
        small = QFont(self.ui, 7)
        L, R = cx - sw / 2 + 8, cx + sw / 2 - 8
        if party:
            orders_ = party["orders"]
            p.setFont(f)
            p.setPen(C(pl["ink"]))
            p.drawText(QRectF(L, sy + 4, R - L, 14), Qt.AlignLeft | Qt.AlignVCenter,
                       T("{name} · {n} 杯", name=T(orders_[0].name), n=len(party["cups"])) if len(party["cups"]) > 1
                       else T("{name} · 1 杯", name=T(orders_[0].name)))
            p.setFont(small)
            rows = [(o.title, o.price - o.dessert_price) for o in orders_]   # 品項與單價（加購的甜點另列一行，一定看得到）
            rows = rows[:3 - sum(1 for o in orders_ if o.dessert)] + [
                (T("＋ {name}（加購價）", name=T(ingredients.DESSERTS[o.dessert][0])), o.dessert_price) for o in orders_ if o.dessert]
            for i, (title, price) in enumerate(rows[:3]):
                y = sy + 20 + i * 12
                p.setPen(C(pl["ink2"]))
                self.fit_text(p, QRectF(L, y, R - L - 46, 12), title, small)
                p.drawText(QRectF(R - 46, y, 46, 12), Qt.AlignRight | Qt.AlignVCenter, money(price))
            p.setPen(QPen(C(pl["line"]), 0.8))
            p.drawLine(QPointF(L, sy + 58), QPointF(R, sy + 58))
            big = QFont(self.ui, 13)
            big.setBold(True)
            p.setFont(big)
            p.setPen(C(pl["ink"]))
            p.drawText(QRectF(L, sy + 59, R - L, 22), Qt.AlignRight | Qt.AlignVCenter, money(party["price"]))
            p.setFont(small)
            p.drawText(QRectF(L, sy + 59, R - L, 22), Qt.AlignLeft | Qt.AlignVCenter, T("合計"))
            badge = QRectF(L, sy + 84, R - L, 15)
            p.setFont(f)
            if paid:
                p.setBrush(C("#3aa36a"))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(badge, 3, 3)
                p.setPen(C("#ffffff"))
                if "score" in party:                                        # 結帳完：這張單的評分
                    n = int(round(party["score"] / 20))
                    text = T("{stars} {s:.0f} 分", stars="★" * n + "☆" * (5 - n), s=party["score"])
                else:
                    text = T("已付款") if ck is not None else T("已付款 · 取餐中…")
                self.fit_text(p, badge, text, f, Qt.AlignCenter)
            else:
                p.setPen(C(pl["muted2"]))
                p.drawText(badge, Qt.AlignCenter, T("點單中…") if party.get("pending") else T("等待客人付款…"))
        else:
            dd = self.stats.day()
            big = QFont(self.ui, 12)
            big.setBold(True)
            p.setFont(big)
            p.setPen(C(pl["muted"]))
            p.drawText(QRectF(cx - sw / 2, sy + 22, sw, 24), Qt.AlignCenter, T("今日 {m}", m=money(dd["revenue"])))
            p.setFont(f)
            p.drawText(QRectF(cx - sw / 2, sy + 58, sw, 20), Qt.AlignCenter, T("小費 {m}", m=money(dd["tips"])))
        # 刷卡機
        kx = self.pos_x(W) + 104
        p.setPen(Qt.NoPen)
        p.fillPath(rrect(kx - 13, top - 40, kx + 13, top, 5), vgrad(top - 40, top, [(0, C(pl["reader"][0])), (1, C(pl["reader"][1]))]))
        p.fillPath(rrect(kx - 9, top - 36, kx + 9, top - 22, 2), C("#0d1a12"))
        on = bool(party) and ck is not None and ck["phase"] == "pay"
        p.setBrush(C("#5adf8a" if paid else ("#ffd27a" if on else "#2a3a2e")))
        p.drawEllipse(QPointF(kx, top - 14), 2.2, 2.2)
        self.paint_seat_sign(p, self.pos_x(W) - SIGN_DX, top)

    def seat_sign_left(self, W):
        """座位小黑板的左端（做好的杯子排在它左邊）"""
        return self.pos_x(W) - SIGN_DX - SIGN_W / 2

    def paint_seat_sign(self, p, x, top):
        """POS 左邊的小黑板立牌（跟吊掛看板同一套配色）：坐著的內用客人／總座位，坐滿寫「客滿」"""
        n, total = len(self.seated), self.seats()
        w, h = SIGN_W, 50
        y0 = top - 8 - h
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#4a3220"), 3))                                     # A 字架的後腳
        p.drawLine(QPointF(x - w / 2 + 8, y0 + h - 4), QPointF(x - w / 2 + 2, top))
        p.drawLine(QPointF(x + w / 2 - 8, y0 + h - 4), QPointF(x + w / 2 - 2, top))
        p.setPen(Qt.NoPen)
        p.fillPath(rrect(x - w / 2, y0, x + w / 2, y0 + h, 4), C(STORE["shelf"]))
        p.fillPath(rrect(x - w / 2 + 3, y0 + 3, x + w / 2 - 3, y0 + h - 3, 2), C(STORE["board"]))
        f = QFont(self.ui, 7)
        f.setBold(True)
        p.setFont(f)
        p.setPen(C("#d8ccb8"))
        p.drawText(QRectF(x - w / 2, y0 + 5, w, 12), Qt.AlignCenter, T("座位"))
        big = QFont(self.ui, 12)
        big.setBold(True)
        full = n >= total
        p.setPen(C("#ff8a6a" if full else STORE["accent"]))
        self.fit_text(p, QRectF(x - w / 2 + 4, y0 + 19, w - 8, 24), T("客滿") if full else f"{n} / {total}", big, Qt.AlignCenter)

    # ───────────── 打烊日報（視窗座標） ─────────────
    def show_report(self, data):
        """顯示打烊日報收據（data 來自 growth.report）"""
        if data is None:
            return
        self.report_card = {"data": data, "t0": time.perf_counter()}
        self.cfg["report_seen"] = max(self.cfg.get("report_seen", ""), data["day"])
        self.tray_message(T("打烊日報 {day}：服務 {n} 位，營業額 {rev}", day=data["day"], n=data["served"],
                            rev=money(data["revenue"])))
        self.sound.once("ding_hi", 0.3)
        self.save_config()
        self.update()                                  # wanted_interval 在收據顯示時維持 AMBIENT

    def report_alpha(self):
        rc = self.report_card
        if rc is None:
            return 0.0
        t = time.perf_counter() - rc["t0"]
        if t >= REPORT_SEC:
            self.report_card = None
            return 0.0
        return clamp(min(t / 0.4, (REPORT_SEC - t) / 0.6), 0, 1)

    def dismiss_report(self):
        rc = self.report_card
        if rc is not None:                             # 快速淡出
            rc["t0"] = min(rc["t0"], time.perf_counter() - REPORT_SEC + 0.6)

    def report_lines(self, d):
        """收據內容：(左, 右, 種類)；種類 head／sub／row／dash／text／bar"""
        lines = [(T("打烊日報"), "", "head"), (d["day"], "", "sub"),
                 (T("Lv.{n} {name}", n=d["level"], name=T(level_name(d["level"]))), "", "sub"), ("", "", "dash"),
                 (T("服務客人"), T("{n} 位", n=d["served"]), "row"),
                 (T("等太久離開"), T("{n} 位", n=d["walkouts"]), "row"),
                 (T("營業額"), money(d["revenue"]), "row"),
                 (T("　其中小費"), money(d["tips"]), "row"),
                 (T("平均分數"), f"{d['avg']:.1f}", "row"),
                 (T("平均等待"), T("{s:.0f} 秒", s=d["wait"]) if d["wait"] is not None else "—", "row"),
                 ("", "", "dash")]
        best = d.get("best")
        if best:
            name = retext(best.get("title")) if best.get("title") not in DRINKS else T(DRINKS[best["drink"]]["name"])
            lines += [(T("最佳一杯"), "", "row"), (T("{name} · {score:.0f} 分", name=name, score=best["score"]), "", "text")]
        if d["change"] is not None:
            arrow = "↑" if d["change"] >= 0 else "↓"
            lines.append((T("比上一個營業日"), f"{arrow} {abs(d['change']) * 100:.0f}%", "row"))
        lines.append(("", "", "dash"))
        lv, nxt, prog = d["progress"]
        if d["level"] > d["level_from"]:
            lines.append((T("升級！Lv.{a} → Lv.{b}", a=d["level_from"], b=d["level"]), "", "text"))
        if lv < MAX_LEVEL:
            lines.append((T("距離 Lv.{n}", n=lv + 1), T("還差 {m}", m=money(d["need"])), "row"))
            lines.append(("", prog, "bar"))
        else:
            lines.append((T("已經是最高等級"), "", "text"))
        if d["achievements"]:
            lines.append((T("今天解鎖 {n} 個成就", n=len(d["achievements"])), "", "text"))
        lines.append((T("點一下收起"), "", "hint"))
        return lines

    def paint_report(self, p):
        a = self.report_alpha()
        if a <= 0.01:
            return
        d = self.report_card["data"]
        lines = self.report_lines(d)
        lh = {"head": 19, "sub": 12.5, "row": 13.5, "text": 13.5, "dash": 8, "bar": 9, "hint": 14}
        h = 14 + sum(lh[k] for _, _, k in lines)
        w = REPORT_W
        x0 = self._scene_w / 2 - w / 2
        y0 = TOP_PAD + WIN_H / 2 - h / 2 - 20 + (1 - a) * 26        # 從下面往上滑出來
        p.save()
        p.setOpacity(a)
        p.translate(x0, y0)
        paper = QPainterPath()                                     # 收據：下緣鋸齒
        paper.moveTo(0, 0)
        paper.lineTo(w, 0)
        paper.lineTo(w, h)
        teeth = 14
        for i in range(teeth):
            xa = w - (i + 0.5) * w / teeth
            paper.lineTo(xa, h - 4)
            paper.lineTo(w - (i + 1) * w / teeth, h)
        paper.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(C("#000000", 80))
        p.drawPath(paper.translated(3, 4))
        p.fillPath(paper, vgrad(0, h, [(0, C("#fbf8f0")), (1, C("#efe8d8"))]))
        y = 8
        mono = QFont(self.ui, 8)
        bold = QFont(self.ui, 8)
        bold.setBold(True)
        for left, right, kind in lines:
            hh = lh[kind]
            rect = QRectF(14, y, w - 28, hh)
            if kind == "head":
                f = QFont(self.ui, 11)
                f.setBold(True)
                p.setFont(f)
                p.setPen(C("#2a1d12"))
                p.drawText(rect, Qt.AlignCenter, left)
            elif kind == "sub":
                p.setFont(QFont(self.ui, 7))
                p.setPen(C("#7a6a56"))
                p.drawText(rect, Qt.AlignCenter, left)
            elif kind == "dash":
                p.setPen(QPen(C("#b8ab92"), 0.8, Qt.DashLine))
                p.drawLine(QPointF(14, y + hh / 2), QPointF(w - 14, y + hh / 2))
            elif kind == "bar":
                p.setPen(Qt.NoPen)
                p.fillRect(QRectF(14, y + 2, w - 28, 3.5), C("#e2d8c2"))
                p.fillRect(QRectF(14, y + 2, (w - 28) * right, 3.5), C("#b06a2a"))
            elif kind == "hint":
                p.setFont(QFont(self.ui, 6))
                p.setPen(C("#a89a86"))
                p.drawText(rect.adjusted(0, 2, 0, 0), Qt.AlignCenter, left)
            else:
                p.setFont(bold if kind == "text" else mono)
                p.setPen(C("#3a2a1a" if kind == "row" else "#8a4a1a"))
                fm = QFontMetricsF(p.font())
                rw = fm.horizontalAdvance(right) + 6 if right else 0
                p.drawText(rect.adjusted(0, 0, -rw, 0), Qt.AlignLeft | Qt.AlignVCenter,
                           fm.elidedText(left, Qt.ElideRight, rect.width() - rw))
                if right:
                    p.drawText(rect, Qt.AlignRight | Qt.AlignVCenter, right)
            y += hh
        p.restore()


def counter_gap(c):
    """櫃檯上一杯佔的寬度（場景座標）：杯盤或杯身加把手，再留一點空"""
    w = c["top"] * (1.3 if (not c["to_go"] and c["handle"]) else 1.0) + (14 if c["handle"] else 0)
    return w * COUNTER_CUP_K + 10


def paint_paper_cup(p, x, base, size, z=(1.0, 1.0), mark="", dome=False):
    """外帶紙杯：杯身（cups.paint_paper_body）、牛皮紙隔熱套、杯蓋（場景座標，杯底中心）；z 是大中小杯的 (寬, 高) 縮放；
    dome：加鮮奶油的用透明圓頂蓋（不插吸管）"""
    h0, tw0, bw0 = PAPER_SIZE[size]
    h, top_w, bot_w = h0 * z[1], tw0 * z[0], bw0 * z[0]
    top = base - h
    paint_paper_body(p, x, base, size, z, mark)
    # 隔熱套：杯身中段
    s1, s2 = top + h * 0.34, top + h * 0.72

    def half(y):
        f = (y - (top + 2)) / (base - top - 2)
        return lerp(top_w / 2, bot_w / 2, f) + 0.8
    sleeve = QPainterPath()
    sleeve.moveTo(x - half(s1), s1)
    sleeve.lineTo(x + half(s1), s1)
    sleeve.lineTo(x + half(s2), s2)
    sleeve.lineTo(x - half(s2), s2)
    sleeve.closeSubpath()
    p.fillPath(sleeve, hgrad(x - half(s1), x + half(s1), [(0, C("#8a6440")), (0.35, C("#c49a6a")),
                                                           (0.7, C("#b08458")), (1, C("#7a5634"))]))
    p.setPen(QPen(C("#ffffff", 70), 0.7))
    p.drawLine(QPointF(x - half(s1) + 2, s1 + 1), QPointF(x + half(s1) - 2, s1 + 1))
    pat, col = CUP_STYLE                                                    # 裝潢的杯子圖案：畫在隔熱套上
    if pat:
        p.save()
        p.setClipPath(sleeve)
        mid = (s1 + s2) / 2
        if pat == "stripe":
            p.setPen(QPen(C(col), 1.6))
            for k in range(-3, 4):
                p.drawLine(QPointF(x + k * 4.2, s1), QPointF(x + k * 4.2, s2))
        elif pat == "dots":
            p.setPen(Qt.NoPen)
            p.setBrush(C(col))
            for r_, y in enumerate((s1 + (s2 - s1) * 0.25, s1 + (s2 - s1) * 0.55, s1 + (s2 - s1) * 0.85)):
                for k in range(-3, 4):
                    p.drawEllipse(QPointF(x + k * 4.6 + (r_ % 2) * 2.3, y), 1.2, 1.2)
        elif pat == "hearts":
            p.setPen(Qt.NoPen)
            p.setBrush(C(col))
            for r_, y in enumerate((s1 + (s2 - s1) * 0.3, s1 + (s2 - s1) * 0.72)):
                for k in range(-3, 4):
                    p.drawPath(heart_path(x + k * 5.4 + (r_ % 2) * 2.7, y, 1.7))
        elif pat == "waves":
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(C(col), 1.1))
            for frac in (0.3, 0.6, 0.88):
                yy = s1 + (s2 - s1) * frac
                wave = QPainterPath()
                wave.moveTo(x - half(s2), yy)
                for k in range(-4, 4):
                    wave.quadTo(x + k * 4.4 + 1.1, yy - 1.8, x + k * 4.4 + 2.2, yy)
                    wave.quadTo(x + k * 4.4 + 3.3, yy + 1.8, x + k * 4.4 + 4.4, yy)
                p.drawPath(wave)
        else:                                                               # brand：中間一個小店標（杯子加一圈金線）
            p.setPen(Qt.NoPen)
            p.setBrush(C(col))
            p.drawEllipse(QPointF(x, mid), 3.6, 3.6)
            p.setBrush(C("#6a4a30"))
            p.drawEllipse(QPointF(x, mid), 2.2, 2.2)
            p.setPen(QPen(C(col), 0.9))
            p.drawLine(QPointF(x - half(s1) + 1, s1 + 1.5), QPointF(x + half(s1) - 1, s1 + 1.5))
            p.drawLine(QPointF(x - half(s2) + 1, s2 - 1.5), QPointF(x + half(s2) - 1, s2 - 1.5))
        p.restore()
    if dome:
        paint_dome_lid(p, x, top + 1, top_w, straw=False)
        return
    # 杯蓋：外緣一圈＋上面凸起的平台與喝口
    p.setPen(Qt.NoPen)
    p.fillPath(rrect(x - top_w / 2 - 2, top + 1, x + top_w / 2 + 2, top + 6, 2.2),
               vgrad(top + 1, top + 6, [(0, C("#f4f2ee")), (1, C("#b8b2a8"))]))
    lid = QPainterPath()
    lid.moveTo(x - top_w / 2 + 3, top + 1.5)
    lid.lineTo(x - top_w / 2 + 7, top - 4)
    lid.lineTo(x + top_w / 2 - 7, top - 4)
    lid.lineTo(x + top_w / 2 - 3, top + 1.5)
    lid.closeSubpath()
    p.fillPath(lid, vgrad(top - 4, top + 2, [(0, C("#fbfaf8")), (1, C("#d4cec4"))]))
    p.setBrush(C("#4a3a2e"))
    p.drawRoundedRect(QRectF(x + top_w / 2 - 17, top - 4, 7, 1.6), 0.8, 0.8)


def paint_dome_lid(p, x, top, width, straw=True):
    """外帶冰飲：透明圓頂蓋與吸管（場景座標，杯口中心）；加鮮奶油的熱飲也用（不插吸管）"""
    r = width / 2 + 2
    p.save()
    p.setPen(QPen(C("#ffffff", 220), 1.6))                                  # 看得出是蓋子：輪廓與蓋緣比較明顯
    p.setBrush(C("#e8f4f8", 95))
    dome = QPainterPath()
    dome.moveTo(x - r, top + 1)
    dome.cubicTo(QPointF(x - r, top - r * 0.75), QPointF(x + r, top - r * 0.75), QPointF(x + r, top + 1))
    dome.closeSubpath()
    p.drawPath(dome)
    p.setPen(QPen(C("#ffffff", 120), 1.2))                                  # 圓頂上的反光
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(x - r * 0.7, top - r * 0.5, r * 0.8, r * 0.9), 100 * 16, 60 * 16)
    p.setPen(Qt.NoPen)
    p.fillPath(rrect(x - r - 2, top - 2, x + r + 2, top + 4, 2), C("#f4fafc", 210))   # 蓋緣（扣在杯口）
    p.fillRect(QRectF(x - r - 2, top + 3, 2 * r + 4, 1), C("#8aa0a8", 160))
    if not straw:
        p.restore()
        return
    p.setPen(QPen(C("#2a5a3a"), 3.2, Qt.SolidLine, Qt.RoundCap))           # 吸管
    p.drawLine(QPointF(x + 6, top + 30), QPointF(x + 14, top - r * 0.8 - 18))
    p.setPen(QPen(C("#5a9a6a"), 1.0, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(x + 5.4, top + 30), QPointF(x + 13.4, top - r * 0.8 - 18))
    p.restore()


def paint_saucer(p, x, base, width):
    """內用：陶瓷杯盤（場景座標，杯底中心）"""
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(C("#000000", 60))
    p.drawEllipse(QPointF(x + 1.5, base + 2), width / 2, 3)
    p.setBrush(C("#d8d2c8"))
    p.drawEllipse(QPointF(x, base + 0.5), width / 2, 3.6)
    p.setBrush(C("#f6f3ee"))
    p.drawEllipse(QPointF(x, base - 0.4), width / 2 - 2, 2.6)
    pat, col = CUP_STYLE                                                    # 裝潢的杯子圖案：杯盤邊緣
    if pat:
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C(col, 230), 0.9))
        p.drawEllipse(QPointF(x, base - 0.4), width / 2 - 1.2, 3.0)
        if pat == "dots":
            p.setPen(Qt.NoPen)
            p.setBrush(C(col))
            for k in range(-4, 5):
                if abs(k) >= 2:
                    p.drawEllipse(QPointF(x + k * width / 10.5, base + (0.3 if abs(k) < 4 else -0.2)), 0.8, 0.5)
    p.restore()
