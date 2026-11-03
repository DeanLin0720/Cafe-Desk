"""圖鑑用的圖：飲品（側面看的一杯）、牛奶盒、咖啡豆袋；沒收集過的是灰色剪影

飲品圖是遊戲裡實際做出來的杯子（tools/render_drink_photos.py 拍的 cafe_desk/assets/drinks/*.png）；
沒有照片的飲品退回用 RECIPES 畫的示意圖（杯型取 cups.CUP_KINDS 的比例，液體分層與配料依飲品寫在 RECIPES）。
"""
import os
import random

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QPen, QColor, QFont, QLinearGradient, QImage

from ..cups import CUP_KINDS
from ..drinks import DRINKS, MILK_KINDS

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
    "maple_latte": ([(0.58, "#c89a6a"), (0.10, FOAM)], {"whip": True}),
    "white_mocha": ([(0.58, "#e8d6b8"), (0.10, FOAM)], {"whip": True}),
    "strawberry_milk": ([(0.12, "#c0304a"), (0.62, "#f4c4cc")], {"ice": True}),
    "salted_caramel_latte": ([(0.58, "#c8925a"), (0.10, FOAM)], {"whip": True, "drizzle": "#c98a3a"}),
    "honey_cinnamon_latte": ([(0.58, "#d8b07a"), (0.14, FOAM)], {"dust": "#a0582a"}),
    "longan_latte": ([(0.60, "#b08068"), (0.14, FOAM)], {}),
    "carrot_cake_latte": ([(0.58, "#d4986a"), (0.10, FOAM)], {"whip": True, "dust": "#a0582a"}),
    "lavender_latte": ([(0.60, "#c8b0c8"), (0.14, FOAM)], {}),
    "apple_cinnamon_latte": ([(0.58, "#d09a6a"), (0.10, FOAM)], {"whip": True, "dust": "#a0582a"}),
    "con_panna": ([(0.40, COFFEE), (0.06, CREMA)], {"whip": True}),
    "vienna": ([(0.66, "#4a2c18")], {"whip": True, "dust": "#5a3420"}),
    "lemon_americano": ([(0.80, "#5b3a22")], {"ice": True, "lemon": True}),
    "orange_coffee": ([(0.52, "#f0a030"), (0.26, "#6a3a1e")], {"ice": True}),
    "vanilla_latte": ([(0.08, VANILLA), (0.48, MIX), (0.14, "#dcc4a6"), (0.10, FOAM)], {}),
    "hazelnut_latte": ([(0.08, "#a8743e"), (0.48, "#c09068"), (0.14, "#dcc4a6"), (0.10, FOAM)], {}),
    "coconut_latte": ([(0.50, "#cfae8a"), (0.18, "#e8dcc6"), (0.12, FOAM)], {}),
    "iced_vanilla_latte": ([(0.08, VANILLA), (0.40, MILK), (0.28, "#a87a52")], {"ice": True}),
    "iced_mocha": ([(0.10, CHOC), (0.44, "#b08860"), (0.20, "#7a4e2c")], {"ice": True, "whip": True, "dust": "#5a3420"}),
    "iced_caramel_latte": ([(0.10, "#b8691f"), (0.40, MILK), (0.26, "#a87a52")], {"ice": True}),
    "dirty_latte": ([(0.10, "#4a2208"), (0.44, MILK), (0.22, "#6a3e22")], {"ice": True, "streaks": "#4a2208"}),
    "coffee_float": ([(0.74, "#5b3a22")], {"ice": True, "scoop": True}),
    "hot_cocoa": ([(0.62, "#8a5a3c"), (0.06, FOAM)], {"whip": True, "dust": "#5a3420"}),
    "honey_milk": ([(0.08, "#e0a428"), (0.58, "#f4e8cc"), (0.10, FOAM)], {}),
    "ginger_milk": ([(0.08, "#d9b45a"), (0.58, "#f2e6c8"), (0.10, FOAM)], {}),
    "matcha_latte": ([(0.56, "#9cb86a"), (0.10, "#c8d8a0"), (0.10, FOAM)], {}),
    "tea_latte": ([(0.56, "#c09078"), (0.10, "#dcc4b0"), (0.10, FOAM)], {}),
    "iced_matcha_latte": ([(0.30, "#7a9a3e"), (0.46, "#cfdcae")], {"ice": True}),
    "milk_tea": ([(0.76, "#c8a088")], {"ice": True}),
    "brown_sugar_milk": ([(0.10, "#4a2208"), (0.64, MILK)], {"ice": True, "streaks": "#4a2208"}),
    "italian_soda": ([(0.12, "#c0304a"), (0.64, "#f0b8c0")], {"ice": True, "bubbles": True}),
    "cocoa_float": ([(0.70, "#9a7258")], {"ice": True, "scoop": True}),
    "iced_pour_over": ([(0.70, "#7a4824")], {"ice": True}),
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


PHOTO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "drinks")
PHOTO_RATIO = 3.0          # 照片的解析度（機身座標的幾倍）
PHOTO_SPAN = 150.0         # 圖鑑裡所有飲品照片共用的比例：機身座標這麼高剛好塞滿（最高的冰摩卡約 144）；杯子大小彼此相稱
_photos = {}


def drink_photo(key):
    """遊戲裡實際做出來的那杯（QImage，透明底）；沒有照片時 None"""
    if key not in _photos:
        img = QImage(os.path.join(PHOTO_DIR, f"{key}.png"))
        _photos[key] = None if img.isNull() else img
    return _photos[key]


def _photo_icon(img, size, made, dpr, tile):
    """照片縮到 size×size（底部對齊、左右置中，所有飲品同一個比例）；made=False 是同一個輪廓的灰色剪影加問號。
    tile＝墊一塊遊戲畫面的深色底（玻璃反光與白色牛奶是照深色背景畫的，放在紙上會看不見）"""
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    k = size / PHOTO_SPAN
    w, h = img.width() / PHOTO_RATIO * k, img.height() / PHOTO_RATIO * k
    if h > size or w > size:                          # 保險：比預期大的照片整張縮進來
        f = size / max(w, h)
        w, h = w * f, h * f
    rect = QRectF((size - w) / 2, size - h, w, h)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.setPen(Qt.NoPen)
    if tile:                                          # 沒做過的剪影也墊同一塊底，圖鑑排起來整齊
        back = QLinearGradient(0, 0, 0, size)
        back.setColorAt(0, QColor("#3a2c24"))
        back.setColorAt(0.78, QColor("#2a1f1a"))
        back.setColorAt(0.78, QColor("#4a3628"))           # 檯面
        back.setColorAt(1, QColor("#3a2a20"))
        p.setBrush(back)
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.1, size * 0.1)
        k = 0.86                                          # 照片縮一點，四周留邊
        w, h = w * k, h * k
        rect = QRectF((size - w) / 2, size * 0.94 - h, w, h)
    p.setBrush(QColor(0, 0, 0, 60 if tile else 28))   # 桌面上的影子
    p.drawEllipse(QPointF(size / 2, rect.bottom() - h * 0.04), w * 0.3, 2.5)
    if made:
        p.drawImage(rect, img)
    else:
        sil = QImage(img.size(), QImage.Format_ARGB32_Premultiplied)
        sil.fill(Qt.transparent)
        q = QPainter(sil)
        q.drawImage(0, 0, img)
        q.setCompositionMode(QPainter.CompositionMode_SourceIn)
        q.fillRect(sil.rect(), QColor("#5e4c40" if tile else "#d4ccc2"))
        q.end()
        p.drawImage(rect, sil)
        f = QFont()
        f.setPointSizeF(size * 0.2)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#8c7868" if tile else "#f4efe8"))
        p.drawText(QRectF(rect.left(), rect.top() + h * 0.3, w, h * 0.65), Qt.AlignCenter, "?")
    p.end()
    return pm


def drink_icon(key, size=96, made=True, dpr=1.0, tile=True):
    """一杯飲品的側面圖（有照片就用照片；tile＝照片墊深色底）；made=False 是灰色剪影加問號"""
    img = drink_photo(key)
    if img is not None:
        return _photo_icon(img, size, made, dpr, tile)
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
    if extra.get("streaks"):                                        # 黑糖掛杯壁的紋路
        p.setPen(QPen(QColor(extra["streaks"]), max(1.2, size * 0.03), Qt.SolidLine, Qt.RoundCap))
        for i in range(5):
            x = tl + (tr - tl) * (0.15 + 0.17 * i)
            p.drawLine(QPointF(x, t + h * 0.12), QPointF(x + (bl - tl) * 0.3, b - h * 0.2 * rnd.random()))
    if extra.get("lemon"):                                          # 檸檬片
        r = (tr - tl) * 0.18
        c = QPointF(tr - r * 1.6, surface + r * 0.6)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#e8c832"))
        p.drawEllipse(c, r * 0.6, r)
        p.setBrush(QColor("#fbf1b8"))
        p.drawEllipse(c, r * 0.48, r * 0.82)
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


# ───────────── 圖鑑的牛奶與豆子產地 ─────────────
# 牛奶盒的色帶與標籤字（不放品牌，只寫種類）
MILK_LOOK = {"dairy": ("#4f86c6", "MILK"), "oat": ("#c79a4e", "OAT"), "soy": ("#6f9e52", "SOY"),
             "almond": ("#a8704a", "ALMOND"), "coconut": ("#6a4a2a", "COCONUT")}
# 豆袋標籤的顏色（依產地）；精品豆的標籤加金邊
ORIGIN_LOOK = {"yirgacheffe": "#d9a441", "kenya": "#b8433a", "colombia": "#d0703a", "guatemala": "#3f7a5a",
               "house": "#8a6a4a", "brazil": "#3f8a4a", "sumatra": "#5a4a7a", "geisha": "#c9567a",
               "bluemountain": "#3f6fa8", "kona": "#2f9a8a"}
ROAST_BEAN = {"淺焙": "#9a6236", "中焙": "#6a3f20", "深焙": "#2e1a10"}
GREY, GREY_TXT = QColor("#d4ccc2"), QColor("#f4efe8")
MILK_KINDS_COLOR = {k: v["color"] for k, v in MILK_KINDS.items()}


def _canvas(size, dpr):
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    return pm, p


def _shadow(p, cx, b, rx):
    p.setBrush(QColor(0, 0, 0, 28))
    p.drawEllipse(QPointF(cx, b + 1), rx, 3)


def _unknown(p, path, rect, size):
    """沒收集過：灰色剪影加問號"""
    p.fillPath(path, GREY)
    f = QFont()
    f.setPointSizeF(size * 0.22)
    f.setBold(True)
    p.setFont(f)
    p.setPen(GREY_TXT)
    p.drawText(rect, Qt.AlignCenter, "?")


def _label(p, rect, text, size, color="#ffffff"):
    f = QFont()
    f.setPointSizeF(max(4.0, size * 0.085))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(color))
    p.drawText(rect, Qt.AlignCenter, text)
    p.setPen(Qt.NoPen)


def milk_icon(key, size=84, have=True, dpr=1.0):
    """一盒牛奶（屋頂型紙盒）：白色盒身、種類顏色的色帶與標籤；have=False 是灰色剪影加問號"""
    pm, p = _canvas(size, dpr)
    s = size / 84
    x0, x1, b = 26 * s, 58 * s, 80 * s
    shoulder, peak = 24 * s, 8 * s
    _shadow(p, (x0 + x1) / 2, b, 20 * s)
    body = QPainterPath()
    body.moveTo(x0, b)
    body.lineTo(x0, shoulder)
    body.lineTo((x0 + x1) / 2 - 4 * s, peak + 4 * s)
    body.lineTo((x0 + x1) / 2 - 4 * s, peak)                  # 盒頂的封口
    body.lineTo((x0 + x1) / 2 + 4 * s, peak)
    body.lineTo((x0 + x1) / 2 + 4 * s, peak + 4 * s)
    body.lineTo(x1, shoulder)
    body.lineTo(x1, b)
    body.closeSubpath()
    if not have:
        _unknown(p, body, QRectF(x0, shoulder, x1 - x0, b - shoulder), size)
        p.end()
        return pm
    band, text = MILK_LOOK.get(key, ("#888888", key.upper()))
    g = QLinearGradient(x0, 0, x1, 0)
    g.setColorAt(0, QColor("#e9e4dc"))
    g.setColorAt(0.45, QColor("#fbf9f5"))
    g.setColorAt(1, QColor("#d8d2c8"))
    p.fillPath(body, g)
    p.save()
    p.setClipPath(body)
    p.fillRect(QRectF(x0, shoulder - 1 * s, x1 - x0, 5 * s), QColor(band))          # 肩上的色帶
    p.fillRect(QRectF(x0, 44 * s, x1 - x0, 20 * s), QColor(band))                   # 標籤
    p.fillRect(QRectF(x0, b - 5 * s, x1 - x0, 5 * s), QColor(band).darker(115))
    p.restore()
    p.setBrush(QColor(MILK_KINDS_COLOR.get(key, "#f4eee4")))                         # 倒出來的一滴，顏色是這種奶
    p.setPen(QPen(QColor(band), 1.0 * s))
    drop = QPainterPath(QPointF(x1 - 8 * s, 30 * s))
    drop.cubicTo(QPointF(x1 - 3 * s, 36 * s), QPointF(x1 - 3 * s, 41 * s), QPointF(x1 - 8 * s, 41 * s))
    drop.cubicTo(QPointF(x1 - 13 * s, 41 * s), QPointF(x1 - 13 * s, 36 * s), QPointF(x1 - 8 * s, 30 * s))
    p.drawPath(drop)
    p.setPen(Qt.NoPen)
    _label(p, QRectF(x0, 44 * s, x1 - x0, 20 * s), text, size * (0.8 if len(text) > 4 else 1.0))
    p.end()
    return pm


def bean_icon(key, roast="中焙", premium=False, size=84, have=True, dpr=1.0):
    """一袋咖啡豆（牛皮紙袋、單向排氣閥）：標籤顏色依產地，窗口裡的豆子依烘焙度；精品豆標籤加金邊"""
    pm, p = _canvas(size, dpr)
    s = size / 84
    x0, x1, t, b = 22 * s, 62 * s, 10 * s, 80 * s
    _shadow(p, (x0 + x1) / 2, b, 24 * s)
    bag = QPainterPath()
    bag.moveTo(x0 + 2 * s, t)
    bag.lineTo(x1 - 2 * s, t)
    bag.lineTo(x1, t + 8 * s)
    bag.quadTo(QPointF(x1 + 2 * s, (t + b) / 2), QPointF(x1, b))
    bag.lineTo(x0, b)
    bag.quadTo(QPointF(x0 - 2 * s, (t + b) / 2), QPointF(x0, t + 8 * s))
    bag.closeSubpath()
    if not have:
        _unknown(p, bag, QRectF(x0, t, x1 - x0, b - t), size)
        p.end()
        return pm
    g = QLinearGradient(x0, 0, x1, 0)
    g.setColorAt(0, QColor("#b08a5e"))
    g.setColorAt(0.45, QColor("#d6b88e"))
    g.setColorAt(1, QColor("#a07a50"))
    p.fillPath(bag, g)
    p.save()
    p.setClipPath(bag)
    p.fillRect(QRectF(x0, t + 8 * s, x1 - x0, 1.2 * s), QColor(0, 0, 0, 40))       # 封口的摺線
    p.restore()
    p.setBrush(QColor("#3a2c22"))                                                    # 排氣閥
    p.drawEllipse(QPointF((x0 + x1) / 2, t + 15 * s), 3 * s, 3 * s)
    p.setBrush(QColor("#6a5a4a"))
    p.drawEllipse(QPointF((x0 + x1) / 2, t + 15 * s), 1.4 * s, 1.4 * s)
    lab = QRectF(x0 + 5 * s, t + 22 * s, x1 - x0 - 10 * s, 24 * s)                   # 產地標籤
    p.setBrush(QColor(ORIGIN_LOOK.get(key, "#8a6a4a")))
    if premium:
        p.setPen(QPen(QColor("#e8c25a"), 1.6 * s))
    p.drawRoundedRect(lab, 2 * s, 2 * s)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 200))                                           # 標籤上的小豆子
    p.save()
    p.translate(lab.center())
    p.rotate(-25)
    p.drawEllipse(QPointF(0, 0), 5 * s, 7 * s)
    p.setPen(QPen(QColor(ORIGIN_LOOK.get(key, "#8a6a4a")), 1.1 * s))
    p.drawLine(QPointF(0, -6 * s), QPointF(0, 6 * s))
    p.restore()
    p.setPen(Qt.NoPen)
    win = QRectF(x0 + 9 * s, t + 51 * s, x1 - x0 - 18 * s, 15 * s)                   # 透明窗口看得到豆子（烘焙度）
    p.setBrush(QColor(255, 255, 255, 60))
    p.drawRoundedRect(win, 3 * s, 3 * s)
    rnd = random.Random(sum(map(ord, key)))
    col = QColor(ROAST_BEAN.get(roast, "#6a3f20"))
    p.save()
    p.setClipRect(win.adjusted(1 * s, 1 * s, -1 * s, -1 * s))
    for i in range(14):
        bx = win.left() + 3 * s + (i % 7) * 3.6 * s + rnd.uniform(-0.6, 0.6) * s
        by = win.top() + 4 * s + (i // 7) * 6 * s + rnd.uniform(-0.6, 0.6) * s
        p.save()
        p.translate(bx, by)
        p.rotate(rnd.uniform(0, 180))
        p.setBrush(col.darker(int(100 + rnd.uniform(0, 25))))
        p.drawEllipse(QPointF(0, 0), 2.6 * s, 1.9 * s)
        p.restore()
    p.restore()
    p.end()
    return pm


# ───────────── 商店的升級圖示 ─────────────
CHROME = [(0, "#6b7177"), (0.35, "#f2f4f5"), (0.6, "#b4bbc1"), (1, "#4e545a")]


def _grad(x0, x1, stops):
    g = QLinearGradient(x0, 0, x1, 0)
    for t, c in stops:
        g.setColorAt(t, QColor(c))
    return g


def _burr(p, cx, cy, r, teeth, curve=0.0, color="#9aa2a8"):
    """刀盤（俯視）：圓盤、中心孔、一圈齒；curve＞0 的齒是彎的（鬼齒）"""
    import math
    p.setPen(QPen(QColor("#4e545a"), 1.2))
    g = QLinearGradient(cx - r, cy - r, cx + r, cy + r)
    g.setColorAt(0, QColor("#eef1f3"))
    g.setColorAt(1, QColor(color))
    p.setBrush(g)
    p.drawEllipse(QPointF(cx, cy), r, r)
    p.setPen(QPen(QColor("#5a6066"), 1.3, Qt.SolidLine, Qt.RoundCap))
    for i in range(teeth):
        a = 2 * math.pi * i / teeth
        a2 = a + curve
        p.drawLine(QPointF(cx + math.cos(a) * r * 0.42, cy + math.sin(a) * r * 0.42),
                   QPointF(cx + math.cos(a2) * r * 0.9, cy + math.sin(a2) * r * 0.9))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#3a3f44"))
    p.drawEllipse(QPointF(cx, cy), r * 0.22, r * 0.22)


def upgrade_icon(kind, size=64, opened=True, dpr=1.0):
    """商店升級的小圖：frother 奶泡機、collar 恆溫套環、pid 溫控、flat 平刀盤、conical 錐刀、ghost 鬼齒、
    steam 蒸氣管、preinfuse 預浸壓力曲線、boiler 鍋爐；還沒解鎖的畫淡一點"""
    import math
    pm, p = _canvas(size, dpr)
    s = size / 64
    p.scale(s, s)
    if not opened:
        p.setOpacity(0.35)
    if kind == "frother":                                   # 奶泡機：底座＋不鏽鋼壺＋把手
        p.fillPath(_rr(18, 52, 46, 58, 3), QColor("#2a2b2e"))
        p.fillPath(_rr(20, 18, 44, 52, 4), _grad(20, 44, CHROME))
        p.setPen(QPen(QColor("#9aa2a8"), 3, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(38, 24, 14, 20), -90 * 16, 180 * 16)
        p.setPen(Qt.NoPen)
        p.fillPath(_rr(19, 14, 45, 19, 2), QColor("#3a3b3e"))
        p.setBrush(QColor("#5adf8a"))
        p.drawEllipse(QPointF(32, 55), 1.6, 1.6)
        p.setBrush(QColor(255, 255, 255, 170))                # 細奶泡
        for i, (x, y) in enumerate(((26, 11), (31, 8), (36, 10), (33, 4))):
            p.drawEllipse(QPointF(x, y), 1.8 - 0.2 * i, 1.8 - 0.2 * i)
    elif kind == "collar":                                  # 沖煮頭恆溫套環：環＋上下的沖煮頭
        p.fillPath(_rr(22, 8, 42, 22, 3), _grad(22, 42, CHROME))
        p.setPen(QPen(QColor("#c8763a"), 6))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(14, 22, 36, 14))
        p.setPen(QPen(QColor(240, 176, 112, 120), 1.4))
        p.drawArc(QRectF(15, 22, 34, 12), 30 * 16, 120 * 16)
        p.setPen(Qt.NoPen)
        p.fillPath(_rr(20, 36, 44, 46, 3), _grad(20, 44, CHROME))
        p.setPen(QPen(QColor("#4e545a"), 2.4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(28, 46), QPointF(25, 54))
        p.drawLine(QPointF(36, 46), QPointF(39, 54))
    elif kind == "pid":                                     # PID 溫控：小黑盒、橘色數字、兩個按鈕
        p.fillPath(_rr(8, 16, 56, 48, 5), QColor("#1e1f22"))
        p.fillPath(_rr(12, 20, 52, 36, 3), QColor("#0d1a12"))
        f = QFont()
        f.setPointSizeF(11)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#ffb04a"))
        p.drawText(QRectF(12, 20, 40, 16), Qt.AlignCenter, "93.0")
        p.setPen(Qt.NoPen)
        for x in (20, 32, 44):
            p.setBrush(QColor("#4a4c50"))
            p.drawEllipse(QPointF(x, 42), 2.6, 2.6)
    elif kind in ("flat", "conical", "ghost"):
        if kind == "flat":                                  # 平刀盤：兩片疊著
            _burr(p, 26, 34, 18, 14)
            _burr(p, 38, 28, 18, 14)
        elif kind == "ghost":                               # 鬼齒：彎的齒
            _burr(p, 32, 32, 24, 12, curve=0.55, color="#b8a07a")
        else:                                               # 錐刀：側面的錐形刀頭＋外圈
            p.setPen(QPen(QColor("#4e545a"), 1.2))
            p.setBrush(_grad(16, 48, CHROME))
            p.drawEllipse(QRectF(10, 40, 44, 14))
            cone = QPainterPath(QPointF(20, 46))
            cone.lineTo(32, 12)
            cone.lineTo(44, 46)
            cone.closeSubpath()
            p.drawPath(cone)
            p.setPen(QPen(QColor("#5a6066"), 1.2))
            for i in range(5):
                x = 23 + i * 4.5
                p.drawLine(QPointF(x, 45), QPointF(32 - (32 - x) * 0.2, 17))
    elif kind == "steam":                                   # 蒸氣管：彎管、噴嘴、蒸氣
        path = QPainterPath(QPointF(14, 8))
        path.lineTo(14, 30)
        path.cubicTo(QPointF(14, 44), QPointF(28, 46), QPointF(36, 50))
        p.setPen(QPen(QColor("#9aa2a8"), 5, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setPen(QPen(QColor("#e8eaec"), 1.6, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 150))
        for i, (x, y, r) in enumerate(((42, 50, 4), (48, 46, 5), (54, 40, 6), (50, 32, 5))):
            p.drawEllipse(QPointF(x, y), r, r)
        p.fillPath(_rr(8, 4, 20, 10, 2), QColor("#3a3b3e"))
    elif kind == "preinfuse":                               # 預浸：壓力錶＋先低後高的曲線
        p.setPen(QPen(QColor("#4e545a"), 2))
        p.setBrush(QColor("#f4eee2"))
        p.drawEllipse(QPointF(32, 32), 24, 24)
        p.setPen(QPen(QColor("#2a6a9a"), 2.4, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        curve = QPainterPath(QPointF(14, 42))
        curve.lineTo(24, 40)
        curve.cubicTo(QPointF(30, 39), QPointF(30, 24), QPointF(38, 22))
        curve.lineTo(50, 22)
        p.drawPath(curve)
        p.setPen(QPen(QColor("#c0392b"), 1.8, Qt.SolidLine, Qt.RoundCap))
        a = math.radians(-35)
        p.drawLine(QPointF(32, 32), QPointF(32 + 15 * math.cos(a), 32 + 15 * math.sin(a)))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#3a3f44"))
        p.drawEllipse(QPointF(32, 32), 2.4, 2.4)
    elif kind == "boiler":                                  # 鍋爐：不鏽鋼筒＋底下的加熱紅光
        p.setPen(Qt.NoPen)
        p.fillPath(_rr(14, 12, 50, 50, 8), _grad(14, 50, CHROME))
        p.fillPath(_rr(14, 20, 50, 23, 1), QColor(0, 0, 0, 40))
        p.fillPath(_rr(14, 40, 50, 43, 1), QColor(0, 0, 0, 40))
        p.setBrush(QColor("#ff6a2a"))
        for x in (20, 28, 36, 44):
            wave = QPainterPath(QPointF(x - 3, 58))
            wave.quadTo(QPointF(x, 50), QPointF(x + 3, 58))
            p.drawPath(wave)
    p.end()
    return pm


def _rr(x0, y0, x1, y1, r):
    path = QPainterPath()
    path.addRoundedRect(QRectF(x0, y0, x1 - x0, y1 - y0), r, r)
    return path


def decor_icon(key, size=64, dpr=1.0):
    """商店的店面裝潢小圖（decor.ITEMS 的每一款）：配色款畫示意的色塊，掛畫、植物、燈光直接用櫃檯畫面的繪圖函式"""
    from .. import decor
    from . import shop
    pm, p = _canvas(size, dpr)
    p.scale(size / 64, size / 64)
    slot = decor.ITEMS[key][0]
    look = decor.LOOK.get(key, {})

    def val(k):
        return look.get(k, shop.STORE.get(k))

    def vgrad(y0, y1, c0, c1):
        g = QLinearGradient(0, y0, 0, y1)
        g.setColorAt(0, QColor(c0))
        g.setColorAt(1, QColor(c1))
        return g
    if slot == "counter":
        front, top = val("front"), val("top")
        p.fillPath(_rr(6, 26, 58, 56, 3), vgrad(26, 56, *front))
        p.fillPath(_rr(4, 18, 60, 28, 2), vgrad(18, 28, *top))
        p.fillRect(QRectF(14, 36, 24, 4), QColor(val("logo")))
        p.fillRect(QRectF(14, 44, 14, 2.5), QColor(val("logo")).darker(120))
    elif slot == "cabinet":
        c0, c1 = look.get("cab", ("#6e4c30", "#4e3420"))
        for i in range(2):
            x = 6 + i * 28
            p.fillPath(_rr(x, 16, x + 26, 56, 2), vgrad(16, 56, c0, c1))
            p.fillRect(QRectF(x + 3, 21, 20, 1.2), QColor(look.get("cab_line", "#8a6440")))
            p.fillPath(_rr(x + 7, 32, x + 19, 36, 2), QColor(look.get("handle", "#c9a35a")))
    elif slot == "floor":
        c0, c1 = val("floor")
        if look.get("floor_pat") == "check":
            for r in range(3):
                for c in range(5):
                    p.fillRect(QRectF(4 + c * 12, 22 + r * 12, 12, 12), QColor((c0, c1)[(r + c) % 2]))
        elif look.get("floor_pat") == "herring":
            p.fillPath(_rr(4, 22, 60, 58, 3), vgrad(22, 58, c0, c1))
            p.save()
            p.setClipRect(QRectF(4, 22, 56, 36))
            p.setPen(QPen(QColor(0, 0, 0, 90), 1))
            for r in range(3):
                for i, x in enumerate(range(4, 64, 8)):
                    d = 8 if i % 2 else -8
                    p.drawLine(QPointF(x, 22 + r * 12), QPointF(x + d, 34 + r * 12))
            p.restore()
        elif look.get("floor_pat") == "marble":
            p.fillPath(_rr(4, 22, 60, 58, 3), vgrad(22, 58, c0, c1))
            p.setPen(QPen(QColor(255, 255, 255, 120), 1))
            p.drawLine(QPointF(32, 22), QPointF(32, 58))
            p.drawLine(QPointF(4, 40), QPointF(60, 40))
            p.setPen(QPen(QColor(90, 86, 80, 90), 0.8))
            p.drawLine(QPointF(10, 26), QPointF(24, 36))
            p.drawLine(QPointF(38, 44), QPointF(54, 54))
        else:
            p.fillPath(_rr(4, 22, 60, 58, 3), vgrad(22, 58, c0, c1))
            p.setPen(QPen(QColor(0, 0, 0, 60), 1))
            for x in range(10, 60, 14):
                p.drawLine(QPointF(x, 22), QPointF(x - 5, 58))
    elif slot == "wall":
        c0, c1 = val("wall")
        p.fillPath(_rr(4, 8, 60, 58, 3), vgrad(8, 58, c0, c1))
        if look.get("wall_pat") == "brick":
            p.setPen(QPen(QColor(0, 0, 0, 90), 1))
            for i, y in enumerate(range(8, 58, 8)):
                p.drawLine(QPointF(4, y), QPointF(60, y))
                for x in range(4 + 10 * (i % 2), 60, 20):
                    p.drawLine(QPointF(x, y), QPointF(x, y + 8))
        elif look.get("wall_pat") == "subway":
            p.save()
            p.setClipPath(_rr(4, 8, 60, 58, 3))
            p.setPen(QPen(QColor(120, 114, 104, 140), 1))
            for i, y in enumerate(range(8, 58, 7)):
                p.drawLine(QPointF(4, y), QPointF(60, y))
                for x in range(4 + 8 * (i % 2), 60, 16):
                    p.drawLine(QPointF(x, y), QPointF(x, y + 7))
            p.restore()
        elif look.get("wall_pat") == "panel":
            p.setPen(QPen(QColor(0, 0, 0, 110), 1))
            for x in range(13, 60, 9):
                p.drawLine(QPointF(x, 8), QPointF(x, 58))
    elif slot == "board":
        frame = look.get("frame")
        if look.get("neon"):
            p.setPen(QPen(QColor(look["neon"]).lighter(100), 3))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(6, 12, 52, 40), 3, 3)
            p.setPen(Qt.NoPen)
        p.fillPath(_rr(4 if frame else 6, 10 if frame else 12, 60 if frame else 58, 54 if frame else 52, 3), QColor(frame or "#0e0d0c"))
        light = look.get("board_light")
        p.fillPath(_rr(8, 14, 56, 50, 2), QColor("#f4f0e6" if light else val("board")))
        acc = QColor(look.get("accent", shop.STORE["accent"]))
        p.fillRect(QRectF(14, 19, 22, 3), acc)
        for i in range(3):
            p.fillRect(QRectF(14, 27 + i * 7, 28, 2.4), QColor("#3a2a1e" if light else "#efe6d4"))
            p.fillRect(QRectF(46, 27 + i * 7, 6, 2.4), QColor("#7a6a56" if light else "#c8b8a0"))
    elif slot == "machine":
        c = QColor("#c9ced3")
        spec = decor.MACHINE_TINT.get(key)
        if spec:
            hue, s_k, s_add, v_k = spec[:4]
            c = QColor.fromHsv(c.hue() if hue is None else hue, min(255, int(c.saturation() * s_k + 255 * s_add)),
                               min(255, int(c.value() * v_k)))
        p.fillPath(_rr(8, 16, 56, 52, 4), vgrad(16, 52, c.lighter(115).name(), c.darker(125).name()))
        p.fillPath(_rr(8, 16, 56, 26, 4), QColor("#2a2b2e"))
        p.setBrush(QColor("#f0e8d8"))
        p.drawEllipse(QPointF(20, 21), 3.4, 3.4)
        p.drawEllipse(QPointF(30, 21), 3.4, 3.4)
        p.fillRect(QRectF(16, 40, 32, 3), QColor("#1a1b1d"))
        p.fillRect(QRectF(24, 52, 16, 4), QColor("#3a3b3e"))
    elif slot == "lighting":
        p.fillRect(QRectF(4, 10, 56, 48), QColor("#2b2522"))
        if key == "neon_sign":
            p.save()
            p.translate(-2, 2)
            p.scale(0.72, 0.72)
            shop.paint_neon_sign(p, 2, 6)
            p.restore()
        elif key == "none":
            p.setBrush(QColor("#6a5a4a"))
            p.drawEllipse(QPointF(32, 34), 6, 6)
        elif key == "fairy":
            p.save()
            p.setClipRect(QRectF(4, 10, 56, 48))
            shop.paint_fairy_lights(p, 2, 62, 22, sag=9, swag=60)
            shop.paint_fairy_lights(p, 2, 62, 40, sag=9, swag=60)
            p.restore()
        else:
            p.save()
            p.setClipRect(QRectF(4, 10, 56, 48))
            p.translate(32 - shop.LAMP_X[0], -34)               # 第一盞燈放在圖的中間
            shop.paint_lamps(p, key, 640)
            p.restore()
    elif slot == "cup":
        pat, col = decor.CUP_STYLES.get(key, (None, None))
        p.fillPath(_poly([(20, 22), (44, 22), (40, 56), (24, 56)]), vgrad(22, 56, "#f4f0e6", "#d8d2c4"))
        p.fillPath(_poly([(21.4, 31), (42.6, 31), (41.2, 45), (22.8, 45)]), QColor("#c49a6a"))
        p.fillPath(_rr(18, 17, 46, 23, 2), QColor("#f4f2ee"))
        p.save()
        p.setClipPath(_poly([(21.4, 31), (42.6, 31), (41.2, 45), (22.8, 45)]))
        if pat == "stripe":
            p.setPen(QPen(QColor(col), 1.8))
            for k in range(-4, 5):
                p.drawLine(QPointF(32 + k * 4.4, 30), QPointF(32 + k * 4.4, 46))
        elif pat == "dots":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(col))
            for r, y in enumerate((34, 38.5, 43)):
                for k in range(-4, 5):
                    p.drawEllipse(QPointF(32 + k * 4.6 + (r % 2) * 2.3, y), 1.3, 1.3)
        elif pat == "brand":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(col))
            p.drawEllipse(QPointF(32, 38), 4.4, 4.4)
            p.setBrush(QColor("#6a4a30"))
            p.drawEllipse(QPointF(32, 38), 2.6, 2.6)
        elif pat == "hearts":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(col))
            for r, y in enumerate((35, 42)):
                for k in range(-3, 4):
                    p.drawPath(shop.heart_path(32 + k * 5.6 + (r % 2) * 2.8, y, 2.2))
        elif pat == "stars":
            p.setPen(Qt.NoPen)
            for r, y in enumerate((35, 42)):
                for k in range(-3, 4):
                    p.fillPath(shop.star_path(32 + k * 5.6 + (r % 2) * 2.8, y, 2.3), QColor(col))
        elif pat == "leaf":
            p.setPen(QPen(QColor(col), 1))
            p.drawLine(QPointF(20, 38), QPointF(44, 38))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(col))
            for k in range(-5, 6):
                p.save()
                p.translate(32 + k * 4, 38)
                p.rotate(-35 if k % 2 else 215)
                p.drawEllipse(QPointF(0, -2.8), 1.4, 2.8)
                p.restore()
        elif pat == "waves":
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(col), 1.3))
            for yy in (34, 38.5, 43):
                wave = QPainterPath()
                wave.moveTo(20, yy)
                for k in range(-5, 5):
                    wave.quadTo(32 + k * 4.4 + 1.1, yy - 1.8, 32 + k * 4.4 + 2.2, yy)
                    wave.quadTo(32 + k * 4.4 + 3.3, yy + 1.8, 32 + k * 4.4 + 4.4, yy)
                p.drawPath(wave)
        p.restore()
    elif slot == "pos":
        pl = decor.POS_BASE | decor.POS_LOOK.get(key, {})
        p.fillPath(_rr(22, 44, 42, 58, 2), vgrad(44, 58, *pl["stand"]))
        p.fillRect(QRectF(30, 38, 4, 8), QColor(pl["stand"][1]))
        p.fillPath(_rr(7, 10, 57, 42, 4), QColor(pl["bezel"]))
        p.fillPath(_rr(10, 13, 54, 39, 2), vgrad(13, 39, *pl["screen"]))
        p.fillRect(QRectF(14, 17, 18, 2.6), QColor(pl["ink"]))
        for i in range(3):
            p.fillRect(QRectF(14, 22 + i * 4.5, 26, 1.8), QColor(pl["ink2"]))
            p.fillRect(QRectF(44, 22 + i * 4.5, 6, 1.8), QColor(pl["muted"]))
        p.fillRect(QRectF(14, 35, 36, 1), QColor(pl["line"]))
    elif slot == "paintings":
        shop.paint_painting(p, key, 4, 10, 56, 44)
    else:                                                    # plants
        shop.paint_plant(p, key, 32, {"plant_hang": 20, "plant_ivy": 10}.get(key, 56))
    p.end()
    return pm


def _poly(pts):
    from PySide6.QtGui import QPolygonF
    path = QPainterPath()
    path.addPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
    path.closeSubpath()
    return path


def dessert_icon(key, size=64, dpr=1.0, ok=True):
    """商店、圖鑑、近期紀錄的甜點圖：跟飲品照片同一個風格（深色底塊、白瓷盤上的寫實甜點，render/dessert_art.py）；
    ok＝False 是圖鑑還沒賣過的：同一個輪廓的深色剪影加問號（跟飲品圖鑑一樣）"""
    from .dessert_art import paint_tile, paint_dessert_plated
    pm, p = _canvas(size, dpr)
    paint_tile(p, size)
    art = QImage(int(size * dpr), int(size * dpr), QImage.Format_ARGB32_Premultiplied)
    art.setDevicePixelRatio(dpr)
    art.fill(Qt.transparent)
    q = QPainter(art)
    q.setRenderHint(QPainter.Antialiasing)
    q.scale(size / 100, size / 100)
    q.translate(50, 50)
    q.scale(1.12, 1.12)                          # 甜點畫大一點，跟飲品照片一樣塞滿底塊
    q.translate(-50, -54)
    paint_dessert_plated(q, key)
    if not ok:
        q.resetTransform()
        q.setCompositionMode(QPainter.CompositionMode_SourceIn)
        q.fillRect(QRectF(0, 0, size, size), QColor("#5e4c40"))
    q.end()
    p.drawImage(QRectF(0, 0, size, size), art)
    if not ok:
        f = QFont()
        f.setPointSizeF(size * 0.2)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#8c7868"))
        p.drawText(QRectF(0, size * 0.25, size, size * 0.55), Qt.AlignCenter, "?")
    p.end()
    return pm


def ingredient_icon(key, size=64, dpr=1.0, ok=True):
    """商店與圖鑑的食材小圖：跟配料架上的是同一組畫法（shop._rack_item），放大畫在透明圖上；ok＝False 是灰色剪影（圖鑑還沒用過）"""
    from . import shop
    pm, p = _canvas(size, dpr)
    k = size / 40
    p.scale(k, k)
    p.setRenderHint(QPainter.Antialiasing)
    shop._rack_item(p, key, 20, 36)
    p.end()
    if not ok:
        img = pm.toImage()
        q = QPainter(img)
        q.setCompositionMode(QPainter.CompositionMode_SourceIn)
        q.fillRect(img.rect(), GREY)
        q.end()
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
    return pm
