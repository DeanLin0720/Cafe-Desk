"""咖啡機定義的基底：機器特性（影響模擬）、定位點、共用繪圖

座標
    場景座標：整個場景（scene_w × WIN_H），磨豆機、把手、填壓器、奶泡機、狀態列用這個座標。
    機身座標：咖啡機本體，原點在場景的 (mx, my)；機身、杯子、液體、蒸氣、蒸氣管用這個座標。
"""
import math
from dataclasses import dataclass

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QRadialGradient, QPen, QPainterPath, QFont

from ..gfx import C, vgrad, hgrad, rrect
from ..layout import PF_TIPS, PF_TIP_Y, PF_BASKET_W, dial_angle
from ..util import clamp


@dataclass
class Traits:
    """機器特性：會影響萃取模擬、鍋爐、奶泡"""
    summary: str = ""
    profile: str = "pump"          # pump＝幫浦恆壓；lever＝彈簧拉桿，壓力隨萃取遞減
    temp_offset: float = 0.0       # 沖煮頭實際水溫與設定的差
    temp_noise: float = 0.0        # 每杯水溫隨機偏差（溫控越差越大）
    boiler_heat: float = 0.45      # 加熱器每秒升溫
    boiler_draw: float = 0.25      # 每 1 g/s 流量每秒降溫
    channel_add: float = 0.0       # 研磨均勻度等造成的通道效應增減
    sweet_add: float = 0.0         # 甜感加成
    pressure_cap: float = 12.0     # 幫浦壓力上限（洩壓閥）
    milk: str = "frother"          # frother＝獨立奶泡機；wand＝蒸氣管
    steam_power: float = 1.0       # 蒸氣強度：越強打得越快、奶泡越細
    steam_heatup: bool = False     # 單鍋爐：打奶前要先把鍋爐加熱到蒸氣溫度
    steam_temp: float = 125.0
    grinder: str = "external"      # external＝獨立磨豆機；integrated＝內建磨豆機


class Machine:
    key = ""
    name = ""
    traits = Traits()

    scene_w = 430                  # 場景寬度
    drip_area = None               # 滴水盤（x1, x2, 上緣；機身座標）
    mx, my = 120, 18               # 機身原點（場景座標）
    group_pf = (114, 128)          # 把手扣上時濾杯左上角（機身座標）
    cup_cx, cup_base = 150, 314    # 杯底中心（機身座標）
    vent = (262, 18)               # 洩壓口（機身座標）
    card_cx = 270                  # 曲線卡片中心 x（場景座標）
    temp_range = (80.0, 100.0)

    # 獨立磨豆區（場景座標），內建磨豆機的機型會覆寫
    fork = (27, 254)
    knock = (93, 290)
    chute = (63, 236)
    tamper_rest = (62, 326)
    knock_box = (106, 312, 152, 366)
    puck_floor = 336

    # 點擊／滑鼠停留範圍（場景座標）
    machine_hit = (148, 18, 392, 188)
    grinder_hit = (16, 10, 108, 240)
    hover_area = (148, 18, 392, 382)

    # 蒸氣管（機身座標）：轉軸、待機時管口、打奶時管口；奶泡機（場景座標）
    wand_pivot = None
    wand_rest = None
    wand_steam = None
    frother_pos = None

    # ───────────── 定位點 ─────────────
    @property
    def spouts(self):
        gx = self.group_pf[0]
        return tuple(gx + t for t in PF_TIPS)

    @property
    def spout_y(self):
        return self.group_pf[1] + PF_TIP_Y

    @property
    def pf_group_scene(self):
        return (self.mx + self.group_pf[0], self.my + self.group_pf[1])

    def gauges(self, a):
        """[(中心, 半徑, 數值, 範圍)]：讓 paint_needles 畫指針"""
        return []

    # ───────────── 需要子類別實作 ─────────────
    def silhouette(self):
        raise NotImplementedError

    def paint_static(self, a, p):
        """機身座標，背景圖層（快取）"""
        raise NotImplementedError

    def paint_front(self, a, p):
        """機身座標，前景圖層（快取）：錶面反光等"""

    def paint_dynamic(self, a, p):
        """機身座標，每幀：按鈕燈、拉桿等（指針由 paint_needles 統一畫）"""

    def paint_collar(self, a, p, pf):
        """機身座標，畫在把手之後：沖煮頭環座"""

    def paint_overlay(self, a, p):
        """機身座標，畫在把手之後：拉桿等在把手前面的零件"""

    def paint_static_scene(self, a, p):
        """場景座標，背景圖層：機身以外的配件（敲渣盒等）"""

    def paint_dynamic_scene(self, a, p):
        """場景座標，每幀：內建磨豆機的豆倉等"""

    # ───────────── 共用繪圖 ─────────────
    def paint_shadow(self, a, p, cx, floor, radius, width=300):
        g = QRadialGradient(cx, floor, radius)
        g.setColorAt(0, C("#000000", 110))
        g.setColorAt(1, C("#000000", 0))
        p.save()
        p.translate(cx, floor)
        p.scale(1, 0.09)
        p.translate(-cx, -floor)
        p.fillRect(QRectF(cx - width / 2, floor - 168, width, 340), g)
        p.restore()

    def paint_scale(self, p):
        """杯子下方的電子秤（機身座標，以杯底中心定位）"""
        cx, b = self.cup_cx, self.cup_base
        p.fillPath(rrect(cx - 74, b + 2, cx + 74, b + 29, 6), vgrad(b + 2, b + 29, [(0, C("#2a2c2f")),
                                                                                    (1, C("#111214"))]))
        p.fillRect(QRectF(cx - 70, b + 2.5, 140, 1), C("#ffffff", 40))
        p.fillPath(rrect(cx - 60, b + 7, cx + 60, b + 24, 3), vgrad(b + 7, b + 24, [(0, C("#0a140e")),
                                                                                   (1, C("#13241a"))]))

    def lcd_rects(self):
        cx, b = self.cup_cx, self.cup_base
        return QRectF(cx - 58, b + 7, 62, 17), QRectF(cx - 4, b + 7, 62, 17)

    def paint_dial_face(self, a, p, center, r, vrange, ticks, majors, labels, zones, unit,
                        face=("#fbf8f1", "#ddd5c4"), ink="#2e2e2e"):
        """錶盤：金屬外圈、錶面、刻度、色區、單位"""
        cx, cy = center
        vmin, vmax = vrange
        rg = QRadialGradient(cx - r * 0.28, cy - r * 0.35, r * 1.4)
        rg.setColorAt(0, C("#f2f4f5"))
        rg.setColorAt(0.6, C("#9aa1a8"))
        rg.setColorAt(1, C("#4c5258"))
        p.setPen(Qt.NoPen)
        p.setBrush(rg)
        p.drawEllipse(QPointF(cx, cy), r + 4.5, r + 4.5)
        p.setBrush(C("#2f3337"))
        p.drawEllipse(QPointF(cx, cy), r + 1, r + 1)
        fg = QRadialGradient(cx, cy - r * 0.2, r * 1.1)
        fg.setColorAt(0, C(face[0]))
        fg.setColorAt(1, C(face[1]))
        p.setBrush(fg)
        p.drawEllipse(QPointF(cx, cy), r - 0.5, r - 0.5)
        p.setBrush(Qt.NoBrush)
        zr = r * 0.78
        rect = QRectF(cx - zr, cy - zr, zr * 2, zr * 2)
        for (lo, hi), col in zones:
            p.setPen(QPen(C(col), max(2.5, r * 0.12), Qt.SolidLine, Qt.FlatCap))
            a0, a1 = dial_angle(hi, vmin, vmax), dial_angle(lo, vmin, vmax)
            p.drawArc(rect, int(a0 * 16), int((a1 - a0) * 16))
        p.setFont(QFont(a.mono, 5 if r > 24 else 4))
        for v in ticks:
            ang = math.radians(dial_angle(v, vmin, vmax))
            major = v in majors
            r1 = r * (0.66 if major else 0.76)
            p.setPen(QPen(C(ink), 1.3 if major else 0.7))
            p.drawLine(QPointF(cx + r1 * math.cos(ang), cy - r1 * math.sin(ang)),
                       QPointF(cx + r * 0.86 * math.cos(ang), cy - r * 0.86 * math.sin(ang)))
        p.setPen(C(ink))
        for v in labels:
            ang = math.radians(dial_angle(v, vmin, vmax))
            lr = r * 0.42
            p.drawText(QRectF(cx + lr * math.cos(ang) - 8, cy - lr * math.sin(ang) - 4, 16, 8),
                       Qt.AlignCenter, f"{v:g}")
        p.setPen(C("#8a8478"))
        p.drawText(QRectF(cx - 10, cy + r * 0.45, 20, 8), Qt.AlignCenter, unit)

    def paint_dial_glass(self, p, center, r):
        gx, gy = center
        gl = QPainterPath()
        gl.addEllipse(QPointF(gx - r * 0.2, gy - r * 0.32), r * 0.68, r * 0.46)
        p.fillPath(gl, vgrad(gy - r * 0.8, gy + r * 0.1, [(0, C("#ffffff", 120)), (1, C("#ffffff", 0))]))

    def paint_needles(self, a, p):
        night = a.light["night"]
        for (cx, cy), r, value, (vmin, vmax) in self.gauges(a):
            if night > 0.05:                         # 夜晚：錶盤背光
                glow = QRadialGradient(cx, cy, r)
                glow.setColorAt(0, C("#ffd9a0", int(70 * night)))
                glow.setColorAt(1, C("#ffd9a0", 0))
                p.setPen(Qt.NoPen)
                p.setBrush(glow)
                p.drawEllipse(QPointF(cx, cy), r - 1, r - 1)
            ang = math.radians(dial_angle(min(vmax + 0.5, value), vmin, vmax))
            tip = QPointF(cx + r * 0.8 * math.cos(ang), cy - r * 0.8 * math.sin(ang))
            tail = QPointF(cx - r * 0.22 * math.cos(ang), cy + r * 0.22 * math.sin(ang))
            p.setPen(QPen(C("#000000", 50), 2.2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(tail + QPointF(1, 1.5), tip + QPointF(1, 1.5))
            p.setPen(QPen(C("#c0392b"), 1.8 if r > 24 else 1.5, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(tail, tip)
            cg = QRadialGradient(cx - 1, cy - 1, 5)
            cg.setColorAt(0, C("#d5d9dd"))
            cg.setColorAt(1, C("#3b3f44"))
            p.setPen(Qt.NoPen)
            p.setBrush(cg)
            p.drawEllipse(QPointF(cx, cy), 3.6 if r > 24 else 3.0, 3.6 if r > 24 else 3.0)

    def paint_round_collar(self, a, p, pf, x1, x2, top, bottom, under_y):
        """通用的鍍鉻環座：蓋住濾杯上緣；把手不在時看得到分水網開口"""
        gx, gy = self.pf_group_scene
        locked = abs(pf["x"] - gx) < 0.5 and pf["y"] <= gy + 7.5
        band = rrect(x1, top, x2, bottom, 2.5)
        p.fillPath(band, hgrad(x1, x2, [(0, C("#4e545a")), (0.12, C("#b9bfc5")), (0.3, C("#f4f6f7")),
                                        (0.45, C("#aab1b8")), (0.75, C("#70777e")), (0.9, C("#bcc2c7")),
                                        (1, C("#4a5056"))]))
        p.fillRect(QRectF(x1 + 1, top, x2 - x1 - 2, 0.9), C("#2a2e32", 150))
        p.fillRect(QRectF(x1 + 1, bottom - 1.4, x2 - x1 - 2, 0.8), C("#ffffff", 110))
        p.setPen(Qt.NoPen)
        cx = (x1 + x2) / 2
        if locked:
            depth = clamp((gy + 7.5 - pf["y"]) / 7.5, 0, 1)
            sh = QRectF(self.group_pf[0] + 1, bottom, PF_BASKET_W - 2, 6)
            p.fillRect(sh, vgrad(bottom, bottom + 6, [(0, C("#000000", int(120 * depth))), (1, C("#000000", 0))]))
        else:
            p.setBrush(C("#141618"))
            p.drawEllipse(QPointF(cx, under_y + 0.2), (x2 - x1) / 2 - 10, 2.4)
            p.setBrush(C("#7d848b", 140))
            p.drawEllipse(QPointF(cx, under_y - 0.1), (x2 - x1) / 2 - 16, 1.2)

    def paint_brew_light(self, a, p, center, r=12.5, halo_r=44):
        """沖煮中脈動的暖色按鈕燈"""
        from ..gfx import mix
        bx, by = center
        on = a.brewing()
        night = a.light["night"]
        pulse = 0.5 + 0.5 * math.sin(a.anim_t * 4)
        if on:
            hr = halo_r + 16 * night
            halo = QRadialGradient(bx, by, hr)
            halo.setColorAt(0, C("#ffa040", int((70 + 50 * pulse) * (1 + 0.6 * night))))
            halo.setColorAt(1, C("#ffa040", 0))
            p.setPen(Qt.NoPen)
            p.setBrush(halo)
            p.drawEllipse(QPointF(bx, by), hr, hr)
        g = QRadialGradient(bx - 3, by - 4, r * 1.2)
        if on:
            g.setColorAt(0, C("#fff2c8"))
            g.setColorAt(0.35, C(mix("#ff9a30", "#ffc060", pulse)))
            g.setColorAt(1, C("#b84a10"))
        else:
            g.setColorAt(0, C("#6a5a4a"))
            g.setColorAt(1, C("#2a211a"))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(bx, by), r, r)
        p.setBrush(C("#ffffff", 90))
        p.drawEllipse(QPointF(bx - r * 0.32, by - r * 0.4), r * 0.32, r * 0.2)

    def paint_wand(self, a, p, knob_color="#1c1d20"):
        """蒸氣管（機身座標）：轉軸 → 彎管 → 管口；a.wand_angle 0＝待機，1＝打奶"""
        if not self.wand_pivot:
            return
        from ..util import lerp
        k = a.wand_angle
        px, py = self.wand_pivot
        tx = lerp(self.wand_rest[0], self.wand_steam[0], k)
        ty = lerp(self.wand_rest[1], self.wand_steam[1], k)
        ex, ey = px + 10, py + 5
        tube = QPainterPath(QPointF(px, py))
        tube.lineTo(ex, ey)
        tube.quadTo(QPointF(tx, ey + 8), QPointF(tx, ty))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#3e4348"), 5.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(tube)
        p.setPen(QPen(C("#eef1f3"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(tube)
        # 防燙套
        grip = QPainterPath(QPointF(ex, ey))
        grip.quadTo(QPointF(lerp(ex, tx, 0.5), ey + 6), QPointF(lerp(ex, tx, 0.75), lerp(ey, ty, 0.45)))
        p.setPen(QPen(C(knob_color), 6.2, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(grip)
        p.setPen(QPen(C("#ffffff", 50), 1.2, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(grip)
        # 管口
        p.setPen(Qt.NoPen)
        p.fillPath(rrect(tx - 3, ty - 4, tx + 3, ty + 1.5, 1.2), hgrad(tx - 3, tx + 3, [(0, C("#4e545a")),
                                                                                    (0.4, C("#e3e7ea")),
                                                                                    (1, C("#4e545a"))]))
        # 轉軸座
        rg = QRadialGradient(px - 2, py - 2, 7)
        rg.setColorAt(0, C("#f2f4f5"))
        rg.setColorAt(1, C("#5d646b"))
        p.setBrush(rg)
        p.drawEllipse(QPointF(px, py), 5, 5)

    def paint_steam_knob(self, a, p, center, r=8, color="#1c1d20"):
        """蒸氣旋鈕：打奶時轉開"""
        cx, cy = center
        rg = QRadialGradient(cx - r * 0.3, cy - r * 0.3, r * 1.4)
        rg.setColorAt(0, C("#5a5c60"))
        rg.setColorAt(1, C(color))
        p.setPen(Qt.NoPen)
        p.setBrush(rg)
        p.drawEllipse(QPointF(cx, cy), r, r)
        ang = math.radians(90 - 120 * a.wand_angle)
        p.setPen(QPen(C("#e3e7ea"), 1.6, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy), QPointF(cx + r * 0.75 * math.cos(ang), cy - r * 0.75 * math.sin(ang)))

    def paint_lamp(self, a, p, center, on, color="#ffb050", r=2.6):
        cx, cy = center
        p.setPen(Qt.NoPen)
        if on:
            halo = QRadialGradient(cx, cy, r * 5)
            halo.setColorAt(0, C(color, int(130 * (1 + 0.6 * a.light["night"]))))
            halo.setColorAt(1, C(color, 0))
            p.setBrush(halo)
            p.drawEllipse(QPointF(cx, cy), r * 5, r * 5)
        p.setBrush(C(color if on else "#3a2e24"))
        p.drawEllipse(QPointF(cx, cy), r, r)

    def paint_brushed(self, p, path, x1, y1, x2, y2, stops, seed=5, n=200):
        """拉絲金屬面板"""
        import random
        p.fillPath(path, vgrad(y1, y2, [(pos, C(col)) for pos, col in stops]))
        p.save()
        p.setClipPath(path)
        rnd = random.Random(seed)
        for _ in range(n):
            y = rnd.uniform(y1, y2)
            x = rnd.uniform(x1 - 20, x2 - 30)
            light = rnd.random() < 0.5
            p.setPen(QPen(C("#ffffff" if light else "#3a4046", rnd.randint(8, 26)), 0.6))
            p.drawLine(QPointF(x, y), QPointF(x + rnd.uniform(30, 120), y))
        p.restore()

    def paint_drip_tray(self, p, x1, x2, top=340, bottom=364):
        tray = rrect(x1, top, x2, bottom, 8)
        p.fillPath(tray, vgrad(top, bottom, [(0, C("#c9ced3")), (0.15, C("#8d949b")), (1, C("#4b5157"))]))
        p.setPen(QPen(C("#2c3135"), 2.2, Qt.SolidLine, Qt.RoundCap))
        for x in range(int(x1) + 12, int(x2) - 10, 7):
            p.drawLine(QPointF(x, top + 6), QPointF(x, top + 17))
        p.setPen(QPen(C("#ffffff", 50), 0.8))
        for x in range(int(x1) + 13, int(x2) - 9, 7):
            p.drawLine(QPointF(x + 1.2, top + 6), QPointF(x + 1.2, top + 17))

    def paint_soft_shadow(self, p, path, w, h, dx=5, dy=8, opacity=0.42):
        from PySide6.QtGui import QImage, QPainter
        small = QImage(int(w // 6), int(h // 6), QImage.Format_ARGB32_Premultiplied)
        small.fill(Qt.transparent)
        sp = QPainter(small)
        sp.setRenderHint(QPainter.Antialiasing)
        sp.scale(1 / 6, 1 / 6)
        sp.translate(dx, dy)
        sp.fillPath(path, C("#000000", 255))
        sp.end()
        blur = small.scaled(int(w // 12), int(h // 12), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        blur = blur.scaled(int(w), int(h), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        p.setOpacity(opacity)
        p.drawImage(0, 0, blur)
        p.setOpacity(1.0)

