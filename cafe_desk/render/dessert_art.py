"""甜點的寫實圖（商店、圖鑑、近期紀錄的甜點圖）：跟飲品照片一樣墊深色底塊，放在白瓷盤上

畫在 100×100 的方框裡，盤面在 y≈76、中心 x＝50；櫃檯櫥窗裡的小甜點還是 shop.paint_dessert（場景裡很小，不用這麼細）。
"""
import math
import random

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QLinearGradient, QRadialGradient, QPainterPath, QPen, QPolygonF

from ..gfx import C


def _lgrad(x0, y0, x1, y1, stops):
    g = QLinearGradient(x0, y0, x1, y1)
    for t, c in stops:
        g.setColorAt(t, C(c) if isinstance(c, str) else c)
    return g


def _rgrad(cx, cy, r, stops):
    g = QRadialGradient(cx, cy, r)
    for t, c in stops:
        g.setColorAt(t, C(c) if isinstance(c, str) else c)
    return g


def paint_tile(p, size):
    """深色底塊（跟飲品照片的底一樣：上面是牆、下面一條檯面）"""
    p.setPen(Qt.NoPen)
    p.setBrush(_lgrad(0, 0, 0, size, [(0, "#3a2c24"), (0.78, "#2a1f1a"), (0.78, "#4a3628"), (1, "#3a2a20")]))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.1, size * 0.1)


def paint_plate(p):
    """白瓷盤"""
    p.setPen(Qt.NoPen)
    p.setBrush(C("#000000", 80))
    p.drawEllipse(QPointF(50, 79), 44, 9)
    p.setBrush(_lgrad(0, 66, 0, 88, [(0, "#ffffff"), (1, "#cfc8bc")]))
    p.drawEllipse(QPointF(50, 76), 44, 10)
    p.setBrush(_lgrad(0, 68, 0, 84, [(0, "#e9e4da"), (1, "#f8f6f1")]))
    p.drawEllipse(QPointF(50, 76), 34, 7)


def _contact(p, x, y, rx):
    """貼著盤面的影子：在甜點底下、只露出一點點（影子比底大一圈、離底太遠的話看起來像浮在盤子上）"""
    p.save()
    p.translate(x, y)
    p.scale(1, 0.12)
    g = QRadialGradient(0, 0, rx)
    g.setColorAt(0, C("#3a2a1c", 150))
    g.setColorAt(0.75, C("#3a2a1c", 70))
    g.setColorAt(1, C("#3a2a1c", 0))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(0, 0), rx, rx)
    p.restore()


def _croissant(p):
    cx, cy = 50, 64

    def spine(t):                       # t：-1（左尖）～ 1（右尖），兩端往下彎
        return QPointF(cx + 35 * math.sin(t * 1.2) / math.sin(1.2), cy - 4 + 12 * t * t)

    def half(t):                        # 半厚度：中間胖、兩端尖
        return 2.6 + 12.5 * (1 - abs(t) ** 1.7)

    p.setPen(Qt.NoPen)
    _contact(p, cx, 70.5, 32)
    bands = [-1, -0.78, -0.55, -0.3, 0.3, 0.55, 0.78, 1]
    for i in (0, 6, 1, 5, 2, 4, 3):     # 外面的先畫，中間那節最後畫（在最前面）
        a, b = bands[i], bands[i + 1]
        ts = [a + (b - a) * k / 10 for k in range(11)]
        top = [QPointF(spine(t).x(), spine(t).y() - half(t)) for t in ts]
        bot = [QPointF(spine(t * 0.82).x(), spine(t * 0.82).y() + half(t) * 0.7) for t in reversed(ts)]   # 下緣往中間收：斜斜的一節一節
        m, hw = spine((a + b) / 2), half((a + b) / 2)
        path = QPainterPath(top[0])
        for q in top[1:]:
            path.lineTo(q)
        path.quadTo(QPointF(spine(b).x() + (2 if b > 0 else -2), spine(b).y()), bot[0])
        for q in bot[1:]:
            path.lineTo(q)
        path.quadTo(QPointF(spine(a).x() + (-2 if a < 0 else 2), spine(a).y()), top[0])
        span = abs(spine(b).x() - spine(a).x())
        p.setBrush(_rgrad(m.x() - span * 0.15, m.y() - hw * 0.55, max(span, hw * 2) * 0.85,
                          [(0, "#f9d286"), (0.35, "#e09a44"), (0.75, "#b0661f"), (1, "#7a3e10")]))
        p.setPen(QPen(C("#5e2e0c", 170), 0.8))
        p.drawPath(path)
        p.setPen(QPen(C("#fff0c8", 70), 0.6))           # 酥皮的層次
        for k in (0.3, 0.55, 0.8):
            y0 = m.y() - hw * k
            p.drawLine(QPointF(m.x() - span * 0.32, y0 + 1), QPointF(m.x() + span * 0.32, y0))
        p.setPen(Qt.NoPen)
        p.setBrush(C("#fff6dc", 80))                    # 蛋液的光澤
        p.drawEllipse(QPointF(m.x() - span * 0.08, m.y() - hw * 0.62), span * 0.28, hw * 0.16)


def _cake(p):
    """草莓鮮奶油蛋糕切片：正面是切面的層次（海綿、鮮奶油、草莓果醬），上面擠花加一顆草莓"""
    FL, FR, B = QPointF(22, 50), QPointF(70, 50), QPointF(60, 34)
    BOT = 74
    p.setPen(Qt.NoPen)
    _contact(p, 48, BOT, 28)
    H = BOT - FL.y()
    for a, b, col in ((0, 4, "#fbf6ee"), (4, 11, "#f0d49c"), (11, 13.5, "#fffaf2"), (13.5, 15.5, "#c93a4a"),
                      (15.5, 22, "#efd09a"), (22, 24, "#d9b47a")):
        p.fillRect(QRectF(FL.x(), FL.y() + a, FR.x() - FL.x(), b - a), C(col))
    p.fillRect(QRectF(FL.x(), FL.y(), FR.x() - FL.x(), H),
               _lgrad(FL.x(), 0, FR.x(), 0, [(0, C("#000000", 30)), (0.3, C("#000000", 0)), (1, C("#000000", 20))]))
    rnd = random.Random(3)
    p.setBrush(C("#c99a58", 120))                         # 海綿蛋糕的氣孔
    for _ in range(26):
        y = rnd.choice((rnd.uniform(4.6, 10.5), rnd.uniform(16, 21.5)))
        p.drawEllipse(QPointF(rnd.uniform(FL.x() + 2, FR.x() - 2), FL.y() + y), 0.7, 0.5)
    p.setBrush(C("#e85868"))                              # 果醬裡的草莓丁
    for _ in range(6):
        p.drawEllipse(QPointF(rnd.uniform(FL.x() + 3, FR.x() - 3), FL.y() + 14.5), 1.6, 0.9)
    p.setBrush(_lgrad(FR.x(), 0, B.x(), 0, [(0, "#efe6d8"), (1, "#d8cbb8")]))   # 側面的外層鮮奶油
    p.drawPolygon(QPolygonF([FR, B, QPointF(B.x(), B.y() + (BOT - FR.y())), QPointF(FR.x(), BOT)]))
    p.setBrush(_lgrad(0, B.y(), 0, FL.y(), [(0, "#fffdf8"), (1, "#f2e8da")]))   # 上面
    p.drawPolygon(QPolygonF([FL, FR, B]))
    p.setPen(QPen(C("#ffffff", 200), 0.8))
    p.drawLine(FL, FR)
    p.setPen(Qt.NoPen)
    for x, y in ((40, 46), (54, 41)):                     # 擠花鮮奶油
        p.setBrush(_rgrad(x - 1, y - 2, 5, [(0, "#ffffff"), (1, "#e6dccb")]))
        p.drawEllipse(QPointF(x, y), 4.5, 3)
        p.drawEllipse(QPointF(x, y - 2.5), 3, 2.2)
    sx, sy = 47, 40                                       # 草莓
    sb = QPainterPath(QPointF(sx, sy + 6))
    sb.cubicTo(sx - 8, sy + 1, sx - 6, sy - 7, sx, sy - 6)
    sb.cubicTo(sx + 6, sy - 7, sx + 8, sy + 1, sx, sy + 6)
    p.setBrush(_rgrad(sx - 2, sy - 3, 9, [(0, "#ff6f73"), (0.6, "#d8243a"), (1, "#8e1022")]))
    p.drawPath(sb)
    p.setBrush(C("#ffe08a"))
    for dx, dy in ((-3, -2), (0, -3.5), (3, -2), (-2, 1), (2, 1), (0, 3)):
        p.drawEllipse(QPointF(sx + dx, sy + dy), 0.5, 0.7)
    p.setBrush(C("#ffffff", 120))
    p.drawEllipse(QPointF(sx - 2.5, sy - 3), 1.6, 1)
    p.setBrush(C("#4c8a3a"))
    for a in (-40, 0, 40):
        p.save()
        p.translate(sx, sy - 6)
        p.rotate(a)
        p.drawEllipse(QPointF(0, -2), 1.3, 2.6)
        p.restore()


def _muffin(p):
    """巧克力馬芬：摺紋紙杯、烤裂的圓頂、巧克力豆與糖粒的反光"""
    p.setPen(Qt.NoPen)
    _contact(p, 50, 76, 19)
    p.setBrush(_lgrad(29, 0, 71, 0, [(0, "#8a5a32"), (0.35, "#d8a46a"), (0.6, "#c48a50"), (1, "#7a4c28")]))
    p.drawPolygon(QPolygonF([QPointF(29, 52), QPointF(71, 52), QPointF(66, 76), QPointF(34, 76)]))
    p.setPen(QPen(C("#6a3e1e", 140), 0.8))                # 紙杯的摺紋
    for i in range(1, 10):
        t = i / 10
        p.drawLine(QPointF(29 + 42 * t, 52), QPointF(34 + 32 * t, 76))
    p.setPen(Qt.NoPen)
    dome = QPainterPath(QPointF(25, 55))
    dome.cubicTo(20, 36, 36, 22, 50, 22)
    dome.cubicTo(64, 22, 80, 36, 75, 55)
    dome.cubicTo(66, 58, 34, 58, 25, 55)
    p.setBrush(_rgrad(43, 32, 32, [(0, "#9a5e34"), (0.5, "#6a3a1e"), (1, "#3e2010")]))
    p.drawPath(dome)
    p.setPen(QPen(C("#2a140a", 160), 0.9))                # 烤裂的紋路
    for a, b, c in (((38, 34), (44, 38), (42, 44)), ((56, 30), (60, 36), (64, 38)), ((48, 46), (54, 48), (58, 47))):
        path = QPainterPath(QPointF(*a))
        path.quadTo(QPointF(*b), QPointF(*c))
        p.drawPath(path)
    p.setPen(Qt.NoPen)
    rnd = random.Random(5)
    for _ in range(9):                                    # 巧克力豆
        x, y = rnd.uniform(32, 68), rnd.uniform(28, 52)
        p.setBrush(C("#22100a"))
        p.drawEllipse(QPointF(x, y), 2.2, 1.6)
        p.setBrush(C("#ffffff", 70))
        p.drawEllipse(QPointF(x - 0.6, y - 0.5), 0.8, 0.4)
    p.setBrush(C("#ffffff", 140))                         # 糖粒的反光
    for _ in range(14):
        p.drawEllipse(QPointF(rnd.uniform(32, 66), rnd.uniform(26, 50)), 0.45, 0.45)
    p.setBrush(C("#ffe2c0", 45))
    p.drawEllipse(QPointF(42, 30), 9, 4)


def _cookie(p):
    """巧克力豆餅乾：有厚度、表面裂紋、大塊的巧克力"""
    p.setPen(Qt.NoPen)
    _contact(p, 50, 78, 31)
    rnd = random.Random(11)
    pts = []
    for i in range(36):
        a = i / 36 * math.tau
        r = 1 + rnd.uniform(-0.04, 0.04)
        pts.append(QPointF(50 + 30 * r * math.cos(a), 60 + 14 * r * math.sin(a)))
    edge = QPainterPath()
    edge.addPolygon(QPolygonF(pts))
    edge.closeSubpath()
    p.setBrush(C("#9a6226"))                              # 餅乾的厚度
    p.drawPath(edge.translated(0, 5))
    p.fillRect(QRectF(20, 60, 60, 5), C("#9a6226"))
    p.setBrush(_rgrad(44, 55, 34, [(0, "#efc07a"), (0.55, "#d79a4e"), (0.9, "#b2722e"), (1, "#8e5420")]))
    p.drawPath(edge)
    p.setPen(QPen(C("#8a5222", 150), 0.8))                # 表面的裂紋
    for x, y, w in ((36, 56, 6), (58, 52, 7), (52, 64, 5), (66, 60, 4)):
        path = QPainterPath(QPointF(x, y))
        path.quadTo(QPointF(x + w / 2, y - 1.6), QPointF(x + w, y + 0.5))
        p.drawPath(path)
    p.setPen(Qt.NoPen)
    for x, y, s in ((40, 52, 3.2), (55, 57, 3.6), (64, 51, 2.8), (46, 63, 3), (30, 59, 2.4), (70, 62, 2.2), (52, 49, 2.2)):
        p.setBrush(C("#2a140a"))
        p.drawPolygon(QPolygonF([QPointF(x + s * math.cos(a) * rnd.uniform(0.7, 1.1), y + s * 0.6 * math.sin(a) * rnd.uniform(0.7, 1.1))
                                 for a in (0, 1.3, 2.4, 3.5, 4.6, 5.6)]))
        p.setBrush(C("#7a4a30", 160))
        p.drawEllipse(QPointF(x - s * 0.3, y - s * 0.25), s * 0.35, s * 0.18)
    p.setBrush(C("#fff0d0", 50))
    p.drawEllipse(QPointF(42, 54), 12, 4)


DESSERT_ART = {"croissant": _croissant, "cake": _cake, "muffin": _muffin, "cookie": _cookie}
SIT_DY = {"croissant": 6.5, "cake": 3, "muffin": 1.5}      # 往下移多少，底部才落在盤面中間（y≈77），不像浮在盤子上


def paint_dessert_plated(p, kind):
    """白瓷盤＋甜點（100×100 的方框）"""
    paint_plate(p)
    p.save()
    p.translate(0, SIT_DY.get(kind, 0))
    DESSERT_ART.get(kind, _cookie)(p)
    p.restore()
