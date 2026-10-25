"""倒液體的容器：內腔形狀、液面高度與傾倒角度（簡化的物理）

- 每種容器的內腔是一條 QPainterPath，原點＝倒出口（壺嘴、瓶口），容器本體在原點的右下方；
  畫面（render/milk.py、render/station.py）與時間軸（drinks.PourStage）用同一份形狀。
- 液面永遠水平：傾斜的時候，找出一條水平線，讓線以下的內腔面積＝剩下的液量（level_y）。
- 倒的角度：液體要碰到倒出口才流得出來，所以傾斜到「通過倒出口的水平線以下剛好是剩下的液量」（pour_tilt）；
  越倒越空就要傾斜得越多，跟真的倒東西一樣。
面積用多邊形近似（曲線先轉成折線），座標以 painter 的 rotate(-tilt) 為準：tilt 越大，容器往逆時針倒。
"""
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath, QTransform

MAX_TILT = 135.0              # 倒到最後最多傾斜幾度（再多就是整個倒過來了）


# ───────────── 內腔形狀（原點＝倒出口） ─────────────
def pitcher():
    """蒸氣管用的拉花鋼杯"""
    body = QPainterPath()
    body.moveTo(0, 0)
    body.lineTo(8, 4)
    body.lineTo(34, 4)
    body.cubicTo(QPointF(35, 18), QPointF(39, 30), QPointF(38, 41))
    body.lineTo(5, 41)
    body.cubicTo(QPointF(4, 30), QPointF(6, 14), QPointF(7, 6))
    body.closeSubpath()
    return body


def kettle():
    """熱水壺：壺身加上細長壺嘴（水從壺底沿壺嘴流到壺嘴口＝原點）"""
    body = QPainterPath()
    body.moveTo(30, 16)
    body.lineTo(70, 16)
    body.cubicTo(QPointF(74, 30), QPointF(76, 44), QPointF(72, 52))
    body.lineTo(28, 52)
    body.cubicTo(QPointF(24, 44), QPointF(26, 30), QPointF(30, 16))
    spout = QPainterPath(QPointF(-1.5, 1))
    spout.cubicTo(QPointF(7, 3.5), QPointF(12.5, 19), QPointF(20.5, 35))
    spout.lineTo(29, 44)
    spout.lineTo(31, 40)
    spout.lineTo(23.5, 33)
    spout.cubicTo(QPointF(15.5, 17), QPointF(9, 0.5), QPointF(1.5, -1))
    spout.closeSubpath()
    return body.united(spout)


def bottle():
    """牛奶瓶／水瓶"""
    glass = QPainterPath()
    glass.moveTo(-5, 0)
    glass.lineTo(5, 0)
    glass.lineTo(5, 9)
    glass.cubicTo(QPointF(13, 12), QPointF(13, 16), QPointF(13, 20))
    glass.lineTo(13, 52)
    glass.quadTo(QPointF(13, 55), QPointF(10, 55))
    glass.lineTo(-10, 55)
    glass.quadTo(QPointF(-13, 55), QPointF(-13, 52))
    glass.lineTo(-13, 20)
    glass.cubicTo(QPointF(-13, 16), QPointF(-13, 12), QPointF(-5, 9))
    glass.closeSubpath()
    return glass


def tonic():
    """通寧水小玻璃瓶"""
    glass = QPainterPath()
    glass.moveTo(-4, 0)
    glass.lineTo(4, 0)
    glass.lineTo(4, 12)
    glass.cubicTo(QPointF(11, 16), QPointF(11, 20), QPointF(11, 24))
    glass.lineTo(11, 56)
    glass.quadTo(QPointF(11, 59), QPointF(8, 59))
    glass.lineTo(-8, 59)
    glass.quadTo(QPointF(-11, 59), QPointF(-11, 56))
    glass.lineTo(-11, 24)
    glass.cubicTo(QPointF(-11, 20), QPointF(-11, 16), QPointF(-4, 12))
    glass.closeSubpath()
    return glass


def jug():
    """獨立奶泡機的玻璃壺"""
    glass = QPainterPath()
    glass.moveTo(0, 2)
    glass.lineTo(6, 6)
    glass.lineTo(42, 6)
    glass.lineTo(43, 52)
    glass.quadTo(QPointF(43, 56), QPointF(39, 56))
    glass.lineTo(7, 56)
    glass.quadTo(QPointF(3, 56), QPointF(3, 52))
    glass.lineTo(4, 9)
    glass.closeSubpath()
    return glass


def server(x=0.0, y=0.0):
    """手沖分享壺（原點＝左上壺嘴）"""
    body = QPainterPath()
    body.moveTo(x, y)
    body.lineTo(x + 44, y)
    body.cubicTo(QPointF(x + 46, y + 20), QPointF(x + 48, y + 46), QPointF(x + 42, y + 56))
    body.lineTo(x + 4, y + 56)
    body.cubicTo(QPointF(x - 3, y + 46), QPointF(x - 1, y + 20), QPointF(x + 1, y + 4))
    body.closeSubpath()
    return body


def carafe(x=0.0, y=0.0):
    """冰滴壺（原點＝左上壺口）：細頸燒瓶"""
    body = QPainterPath()
    body.moveTo(x + 1, y)
    body.lineTo(x + 23, y)
    body.lineTo(x + 23, y + 14)
    body.cubicTo(QPointF(x + 36, y + 20), QPointF(x + 38, y + 34), QPointF(x + 36, y + 58))
    body.quadTo(QPointF(x + 36, y + 64), QPointF(x + 30, y + 64))
    body.lineTo(x - 6, y + 64)
    body.quadTo(QPointF(x - 12, y + 64), QPointF(x - 12, y + 58))
    body.cubicTo(QPointF(x - 14, y + 34), QPointF(x - 12, y + 20), QPointF(x + 1, y + 14))
    body.closeSubpath()
    return body


GLOBE_R = 25
GLOBE_LIP = (-7, -32)         # 虹吸壺下壺：壺口（倒出口）相對球心


def globe(cx=-GLOBE_LIP[0], cy=-GLOBE_LIP[1]):
    """虹吸壺下壺（cx, cy＝球心；預設讓壺口在原點）：球形加短頸"""
    body = QPainterPath()
    body.addEllipse(QPointF(cx, cy), GLOBE_R, GLOBE_R)
    neck = QPainterPath()
    neck.addRect(QRectF(cx - 7, cy - 32, 14, 10))
    return body.united(neck)


def moka():
    """摩卡壺上壺（原點＝壺嘴）：咖啡在上壺裡"""
    body = QPainterPath(QPointF(0, 0))
    for x, y in ((8, 5), (53, 5), (47, 36), (13, 36), (8, 14)):
        body.lineTo(x, y)
    body.closeSubpath()
    return body


def moka_hull():
    """摩卡壺整支的外形（原點＝壺嘴）：上壺、中間的接環、下壺、把手。咖啡只在上壺（moka()），
    但拿去倒的時候下壺也跟著，判斷會不會撞進杯子要用整支（render/station.py 的 paint_moka_pot，壺底中心在 (30, 71)）"""
    body = QPainterPath(QPointF(0, 0))
    for x, y in ((7, 5), (53, 5), (63, 10), (67, 11), (66, 16), (61, 30), (57, 33), (48, 31), (47, 36), (48.5, 36),
                 (48.5, 41.5), (47, 41), (52, 71), (8, 71), (13, 41), (11.5, 41.5), (11.5, 36), (13, 36), (10, 14)):
        body.lineTo(x, y)
    body.closeSubpath()
    return body


JIGGER_K = 2.0                # 量杯的放大倍數（形狀以 1 倍寫，畫刻度、把手時也乘這個）


def jigger():
    """營業模式的濃縮量杯：像小拉花杯的玻璃量杯，左上角有倒口（原點）；放在沖煮頭下的滴水盤上接濃縮"""
    glass = QPainterPath()
    glass.moveTo(0, 0)
    glass.lineTo(6, 3)
    glass.lineTo(44, 3)
    glass.lineTo(42, 47)
    glass.quadTo(QPointF(41.5, 51), QPointF(38, 51))
    glass.lineTo(10, 51)
    glass.quadTo(QPointF(6.5, 51), QPointF(6, 47))
    glass.lineTo(4, 6)
    glass.closeSubpath()
    return QTransform().scale(JIGGER_K, JIGGER_K).map(glass)


SHAPES = {"pitcher": pitcher, "kettle": kettle, "bottle": bottle, "tonic": tonic, "jug": jug,
          "server": server, "carafe": carafe, "globe": globe, "moka": moka, "jigger": jigger}
JIGGER_CAP = 160.0            # 量杯畫面上的「滿」是幾 g（量杯放大後，一份濃縮也看得到液面）
# 外形比內腔大很多的容器：碰撞與超出視窗用外形（沒列的，內腔外框就是外形）
HULLS = {"moka": moka_hull}
# 拿去倒時「內腔裡液體佔多少」：裝滿到能倒的最高水位是 1（冰滴壺只裝到瓶頸下面）
CARAFE_FULL = 0.78


# ───────────── 多邊形計算 ─────────────
@lru_cache(maxsize=None)
def outline(kind):
    """容器內腔的折線（原點＝倒出口）"""
    poly = SHAPES[kind]().toFillPolygon()
    return tuple((pt.x(), pt.y()) for pt in poly)


@lru_cache(maxsize=None)
def hull(kind):
    """容器整個外形的折線（原點＝倒出口）：碰撞、超出視窗用這個"""
    poly = HULLS[kind]().toFillPolygon() if kind in HULLS else SHAPES[kind]().toFillPolygon()
    return tuple((pt.x(), pt.y()) for pt in poly)


def _area(pts):
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i - 1]
        x2, y2 = pts[i]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def _below(pts, level):
    """多邊形在水平線 y＝level 以下（y 較大）的部分（Sutherland–Hodgman）"""
    out = []
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i - 1]
        x2, y2 = pts[i]
        in1, in2 = y1 >= level, y2 >= level
        if in1 != in2:
            t = (level - y1) / (y2 - y1)
            out.append((x1 + (x2 - x1) * t, level))
        if in2:
            out.append((x2, y2))
    return out


def _rotate(pts, tilt):
    m = QTransform().rotate(-tilt)
    return [(m.map(QPointF(x, y)).x(), m.map(QPointF(x, y)).y()) for x, y in pts]


def level_y(pts, content):
    """水平液面的 y：線以下的面積＝content × 總面積（pts 是已經轉成畫面方向的多邊形）"""
    if content <= 0:
        return max(y for _, y in pts) + 1
    if content >= 1:
        return min(y for _, y in pts)
    total = _area(pts)
    lo, hi = min(y for _, y in pts), max(y for _, y in pts)
    for _ in range(28):
        mid = (lo + hi) / 2
        if _area(_below(pts, mid)) > content * total:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def below_lip(kind, tilt):
    """傾斜 tilt 度時，通過倒出口（原點）的水平線以下佔內腔多少：這麼多液體時剛好碰到倒出口"""
    pts = _rotate(outline(kind), tilt)
    return _area(_below(pts, 0.0)) / _area(pts)


def pour_tilt(kind, content, cap=MAX_TILT):
    """剩下 content（0–1）時，要傾斜幾度液面才碰到倒出口"""
    if below_lip(kind, 0.0) <= content:
        return 0.0
    lo, hi = 0.0, cap
    if below_lip(kind, hi) > content:
        return hi
    for _ in range(24):
        mid = (lo + hi) / 2
        if below_lip(kind, mid) > content:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


@lru_cache(maxsize=None)
def _dense(kind, step=3.0):
    """外形加密成每段不超過 step 的點（判斷碰撞時，長直線邊的中段也要算到）"""
    pts = hull(kind)
    out = []
    for i in range(len(pts)):
        (x1, y1), (x2, y2) = pts[i - 1], pts[i]
        n = max(1, int(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 / step))
        out += [(x1 + (x2 - x1) * j / n, y1 + (y2 - y1) * j / n) for j in range(n)]
    return tuple(out)


def lowest_over(kind, tilt, scale, x, left, right):
    """倒出口在 x、傾斜 tilt、放大 scale 時，容器在 left–right（杯子上方）這段最低點離倒出口多遠（往下為正）；
    這段沒有容器時回傳 None"""
    m = QTransform().rotate(-tilt)
    low = None
    for px, py in _dense(kind):
        q = m.map(QPointF(px, py))
        wx = x + q.x() * scale
        if left <= wx <= right:
            dy = q.y() * scale
            low = dy if low is None else max(low, dy)
    return low


def liquid_region(painter, body, content):
    """painter 目前座標（可能已經旋轉、縮放）下，body 裡面的液體：液面在畫面上保持水平"""
    world = painter.worldTransform()
    inv, ok = world.inverted()
    if not ok or content <= 0.003:
        return QPainterPath()
    poly = world.map(body.toFillPolygon())
    pts = [(pt.x(), pt.y()) for pt in poly]
    level = level_y(pts, min(1.0, content))
    r = poly.boundingRect()
    cut = QPainterPath()
    cut.addRect(QRectF(r.left() - 5, level, r.width() + 10, max(0.0, r.bottom() - level) + 5))
    region = QPainterPath()
    region.addPolygon(poly)
    return inv.map(region.intersected(cut))


def surface_line(painter, region):
    """液面那條線（畫面座標下的最上緣），用來畫反光：回傳 painter 座標的 (左點, 右點) 或 None"""
    world = painter.worldTransform()
    inv, ok = world.inverted()
    if not ok or region.isEmpty():
        return None
    poly = world.map(region).toFillPolygon()
    top = poly.boundingRect().top()
    xs = [pt.x() for pt in poly if pt.y() <= top + 0.5]     # 只取液面那一排的點：液面寬度＝容器在那個高度的寬度
    if len(xs) < 2 or max(xs) - min(xs) < 3:
        return None
    return inv.map(QPointF(min(xs) + 1.5, top)), inv.map(QPointF(max(xs) - 1.5, top))
