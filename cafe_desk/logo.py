"""圖示（logo）：程式繪製、讀取、輸出檔案"""
import math
import os
import random

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QImage, QPixmap, QIcon, QPen, QRadialGradient, QPainterPath, QPolygonF

from .gfx import C, vgrad, hgrad, rrect
from .paths import app_dir, resource_dirs
from .util import lerp

LOGO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def draw_logo(size: int) -> QImage:
    """深焙咖啡色圓角方塊 + 濾杯雙流 + 白瓷杯與 crema；32px 以下改用只有杯子的簡化版"""
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 100, size / 100)
    simple = size <= 32

    # 底板
    bg = rrect(3, 3, 97, 97, 22)
    p.fillPath(bg, vgrad(3, 97, [(0, C("#4a2b1a")), (0.55, C("#2b170d")), (1, C("#160b06"))]))
    p.save()
    p.setClipPath(bg)
    glow = QRadialGradient(50, 66 if not simple else 58, 46)
    glow.setColorAt(0, C("#ff9a3c", 95))
    glow.setColorAt(1, C("#ff9a3c", 0))
    p.fillRect(QRectF(0, 0, 100, 100), glow)
    p.fillRect(QRectF(3, 3, 94, 2.5), C("#ffffff", 40))
    p.restore()
    p.setPen(QPen(C("#000000", 90), 1.2))
    p.setBrush(Qt.NoBrush)
    p.drawPath(bg)

    if simple:                       # 小尺寸：杯子放大置中
        p.translate(50, 50)
        p.scale(1.32, 1.32)
        p.translate(-50, -62)
    else:
        # 濾杯與把手
        p.fillPath(rrect(68, 15.5, 93, 21.5, 3), vgrad(15.5, 21.5, [(0, C("#8a5a35")), (1, C("#3b2312"))]))
        p.fillPath(rrect(25, 12, 74, 24, 5), vgrad(12, 24, [(0, C("#f2f4f5")), (0.5, C("#b4bbc1")),
                                                           (1, C("#5d646b"))]))
        for sx in (43, 57):
            p.fillPath(rrect(sx - 2.6, 23, sx + 2.6, 30, 1),
                       hgrad(sx - 2.6, sx + 2.6, [(0, C("#4a5055")), (0.45, C("#c9ced3")), (1, C("#4a5055"))]))
        # 雙流柱合流
        for sx in (43, 57):
            path = QPainterPath()
            n = 12
            left, right = [], []
            for i in range(n + 1):
                g = i / n
                y = lerp(30, 51, g)
                e = g * g * (3 - 2 * g)
                x = lerp(sx, 50 + (sx - 50) * 0.1, e)
                w = lerp(1.5, 0.9, g)
                left.append(QPointF(x - w, y))
                right.append(QPointF(x + w, y))
            poly = QPolygonF(left + right[::-1])
            path.addPolygon(poly)
            p.fillPath(path, vgrad(30, 51, [(0, C("#5a2c10")), (0.5, C("#c27a3a")), (1, C("#e0a868"))]))

    # 杯碟
    sh = QRadialGradient(50, 86, 40)
    sh.setColorAt(0, C("#000000", 120))
    sh.setColorAt(1, C("#000000", 0))
    p.save()
    p.translate(50, 86)
    p.scale(1, 0.2)
    p.translate(-50, -86)
    p.fillRect(QRectF(5, 40, 90, 90), sh)
    p.restore()
    saucer = QPainterPath()
    saucer.addEllipse(QPointF(50, 83), 36, 6.5)
    p.fillPath(saucer, vgrad(76, 90, [(0, C("#fbf7f0")), (1, C("#bfb2a1"))]))

    # 杯身（白瓷）
    body = QPainterPath()
    body.moveTo(24, 50)
    body.cubicTo(QPointF(24, 71), QPointF(34, 80), QPointF(50, 80))
    body.cubicTo(QPointF(66, 80), QPointF(76, 71), QPointF(76, 50))
    body.closeSubpath()
    p.fillPath(body, hgrad(24, 76, [(0, C("#d8ccbc")), (0.3, C("#fffdf8")), (0.7, C("#ece3d6")),
                                    (1, C("#a8998a"))]))
    # 把手
    handle = QPainterPath(QPointF(75, 55))
    handle.cubicTo(QPointF(91, 52), QPointF(92, 70), QPointF(71, 71))
    p.setPen(QPen(C("#efe7dc"), 5.5 if not simple else 7, Qt.SolidLine, Qt.RoundCap))
    p.drawPath(handle)
    # 杯口與 crema
    p.setPen(Qt.NoPen)
    p.setBrush(C("#f7f1e8"))
    p.drawEllipse(QPointF(50, 50), 26, 5.6)
    cg = QRadialGradient(46, 48.5, 24)
    cg.setColorAt(0, C("#f2c890"))
    cg.setColorAt(0.5, C("#c98544"))
    cg.setColorAt(1, C("#6e3a18"))
    p.setBrush(cg)
    p.drawEllipse(QPointF(50, 50.3), 23, 4.3)
    if not simple:
        rnd = random.Random(3)
        for _ in range(14):
            a, r = rnd.random() * 6.283, math.sqrt(rnd.random()) * 0.85
            p.setBrush(C("#5a2c10", 110) if rnd.random() < 0.6 else C("#ffe2b8", 110))
            p.drawEllipse(QPointF(50 + 23 * r * math.cos(a), 50.3 + 4.3 * r * math.sin(a)), 1.1, 0.4)
    p.end()
    return img


def load_icon() -> QIcon:
    for d in resource_dirs():
        for name in ("cafe_desk.ico", "cafe_desk.png", "espresso_desk.ico", "espresso_desk.png"):
            path = os.path.join(d, name)
            if os.path.exists(path):
                icon = QIcon(path)
                if not icon.isNull():
                    return icon
    icon = QIcon()
    for s in LOGO_SIZES:
        icon.addPixmap(QPixmap.fromImage(draw_logo(s)))
    return icon


def make_logo_files(out_dir=None):
    """輸出 cafe_desk.png（1024）與多尺寸 cafe_desk.ico；有 Pillow 用 Pillow 合併尺寸，否則用 Qt 存單一尺寸"""
    out_dir = out_dir or os.path.join(app_dir(), "logo")
    os.makedirs(out_dir, exist_ok=True)
    png = os.path.join(out_dir, "cafe_desk.png")
    ico = os.path.join(out_dir, "cafe_desk.ico")
    draw_logo(1024).save(png)
    try:
        from PIL import Image  # pyright: ignore[reportMissingImports]
        tmp = []
        for s in LOGO_SIZES:
            t = os.path.join(out_dir, f"_tmp_{s}.png")
            draw_logo(s).save(t)
            tmp.append(t)
        big = Image.open(tmp[-1])
        big.save(ico, format="ICO", sizes=[(s, s) for s in LOGO_SIZES],
                 append_images=[Image.open(t) for t in tmp[:-1]])
        for t in tmp:
            os.remove(t)
    except ImportError:
        draw_logo(256).save(ico)
    print("已輸出：", os.path.abspath(png), os.path.abspath(ico))

