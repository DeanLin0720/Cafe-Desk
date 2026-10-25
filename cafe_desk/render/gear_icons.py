"""設備圖鑑用的縮圖：直接用畫面上的繪圖函式把咖啡機、磨豆機、沖煮台畫進一張透明圖，裁掉空白再縮小

去背、還沒解鎖的變成灰色剪影加問號（跟飲品圖鑑一樣）。app 是 CafeDesk（繪圖函式是它的 mixin）。
"""
from PySide6.QtCore import Qt, QRect, QRectF, QPointF
from PySide6.QtGui import QImage, QPainter, QPixmap, QColor, QFont

from .. import brew
from ..layout import WIN_H

CANVAS_W = 680                  # 最寬的雙頭機（場景寬 660）也放得下


def _render(fn):
    img = QImage(CANVAS_W, WIN_H, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    fn(p)
    p.end()
    return img


def _bbox(img):
    """不透明部分的範圍：先縮小 4 倍再掃描（快），再放大回來留一點邊"""
    k = 4
    small = img.scaled(img.width() // k, img.height() // k)
    xs, ys = [], []
    for y in range(small.height()):
        for x in range(small.width()):
            if (small.pixel(x, y) >> 24) > 16:
                xs.append(x)
                ys.append(y)
    if not xs:
        return img.rect()
    r = QRect(min(xs) * k - k, min(ys) * k - k, (max(xs) - min(xs) + 3) * k, (max(ys) - min(ys) + 3) * k)
    return r.intersected(img.rect())


def _mask(img, color):
    """同樣形狀、整片塗成一個顏色"""
    out = img.copy()
    q = QPainter(out)
    q.setCompositionMode(QPainter.CompositionMode_SourceIn)
    q.fillRect(out.rect(), QColor(color))
    q.end()
    return out


def _thumb(img, w, h, locked, dpr):
    """裁切縮小成去背圖（跟飲品圖鑑一樣）：底下一道淡影子；玻璃豆倉、虹吸壺這些半透明的部分在紙上看不出來，
    所以後面墊一圈淡褐色描邊。沒解鎖是灰色剪影加問號。座標一律用邏輯單位（w×h），圖片本身依 dpr 產生高解析度"""
    crop = img.copy(_bbox(img))
    pm = QPixmap(int(w * dpr), int(h * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    pad = 6
    scaled = crop.scaled(int((w - 2 * pad) * dpr), int((h - 2 * pad) * dpr), Qt.KeepAspectRatio,
                         Qt.SmoothTransformation)
    scaled.setDevicePixelRatio(dpr)
    sw, sh = scaled.width() / dpr, scaled.height() / dpr
    x, y = (w - sw) / 2, h - pad - sh
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 28))
    p.drawEllipse(QPointF(w / 2, h - pad), sw * 0.46, 3)
    if locked:
        p.drawImage(QRectF(x, y, sw, sh), _mask(scaled, "#d4ccc2"))
        f = QFont()
        f.setPointSizeF(h * 0.2)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#f4efe8"))
        p.drawText(QRectF(x, y, sw, sh), Qt.AlignCenter, "?")
    else:
        edge = _mask(scaled, "#8a7462")
        edge.setDevicePixelRatio(dpr)
        p.setOpacity(0.45)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            p.drawImage(QRectF(x + dx, y + dy, sw, sh), edge)
        p.setOpacity(1.0)
        p.drawImage(QRectF(x, y, sw, sh), scaled)
    p.end()
    return pm


def machine_icon(app, m, w=150, h=110, locked=False, dpr=1.0):
    """一台咖啡機（不含杯子）"""
    def draw(p):
        m.paint_static_scene(app, p)
        p.save()
        p.translate(m.mx, m.my)
        m.paint_static(app, p)
        m.paint_front(app, p)
        p.restore()
    return _thumb(_render(draw), w, h, locked, dpr)


def machine_image(app, m):
    """一台咖啡機的圖（不含杯子與機身外的配件，例如敲渣盒），裁掉空白、不縮小（櫃檯畫面後檯擺的那台）"""
    def draw(p):
        p.save()
        p.translate(m.mx, m.my)
        m.paint_static(app, p)
        m.paint_front(app, p)
        p.restore()
    img = _render(draw)
    return img.copy(_bbox(img))


def grinder_icon(app, w=150, h=110, locked=False, dpr=1.0):
    """義式用的獨立磨豆機"""
    def draw(p):
        app.paint_grinder_shadow(p)
        app.paint_grinder_static(p)
        app.paint_grinder_dynamic(p)                # 豆倉裡的豆子在動態圖層
    return _thumb(_render(draw), w, h, locked, dpr)


def station_icon(app, kind, w=150, h=110, locked=False, dpr=1.0):
    """沖煮台：pourover／colddrip／moka／siphon，或 grinder（手沖用磨豆機）。
    沖煮台的繪圖函式依 app.method 決定細節（研磨刻度等），畫的時候暫時換成那個方式，畫完換回來"""
    def draw(p):
        old = app.method
        app.method = "pourover" if kind == "grinder" else kind
        try:
            _draw(p)
        finally:
            app.method = old

    def _draw(p):
        if kind == "grinder":
            app.paint_drip_grinder(p, None)
        elif kind == "pourover":
            app.paint_pourover(p, brew.idle_pourover(app), None)
        elif kind == "moka":
            app.paint_moka_station(p, brew.idle_moka(), None)
        elif kind == "siphon":
            app.paint_siphon_station(p, brew.idle_siphon(), None)
        else:                                       # 冰滴塔：畫成架好的樣子（空塔只有木架）
            app.paint_cold_tower(p, {"grounds": 1.0, "top": 0.85, "valve": 1.0}, None)
    return _thumb(_render(draw), w, h, locked, dpr)
