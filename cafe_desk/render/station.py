"""手沖與冰滴的獨立畫面：手沖用磨豆機、濾杯／分享壺／細口壺、冰滴塔，以及倒進杯子的分享壺／冰滴壺

沖煮方式（app.method）是 pourover／colddrip 時，畫面不顯示咖啡機，改畫這裡的器具；杯子放在右邊桌上。
狀態：手沖在 session.station（brew.PourOverStage 更新，沒在沖時用 brew.idle_pourover）；冰滴架設中也在
session.station，滴的過程依 app.cold（背景批次，真實時間；切到別的沖煮方式也會繼續滴）。座標都是場景座標。
"""
import math
import random
import time

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QPainterPath

from .. import brew
from ..gfx import C, mix, vgrad, hgrad, rrect
from ..layout import ROAST_LOOK, BEAN_COLORS, FLOOR
from ..util import clamp, lerp
from ..workflow import ease

GLASS = "#dfe8ec"
WOOD = ("#8a5a34", "#b07a4a", "#5e3a1e")
PAPER = "#f3ece0"


def brew_color(roast, tds, scale=1.0):
    """濾泡咖啡的顏色：比濃縮淡、透亮的琥珀色；scale 讓冰滴（濃一點）共用"""
    look = ROAST_LOOK.get(roast, ROAST_LOOK["中焙"])
    k = clamp((tds * scale - 0.9) / 1.2, 0, 1)
    return mix(look["amber"], look["deep"], 0.35 + 0.5 * k), int(190 + 50 * k)


class StationRenderer:
    # ───────────── 版面 ─────────────
    def scene_width(self):
        """視窗寬度：手沖／冰滴也跟目前的咖啡機一樣寬"""
        return self.machine.scene_w

    def cup_anchor(self):
        """杯子位置（機身座標，Cup 用）：義式在沖煮頭下，手沖／冰滴放在右邊桌上"""
        m = self.machine
        if self.method == "espresso":
            return m.cup_cx, m.cup_base
        return m.scene_w - brew.CUP_RIGHT[self.method] - m.mx, FLOOR - 2 - m.my

    # ───────────── 拉近／拉遠 ─────────────
    def brew_focus(self):
        """現在要不要拉近看沖煮器具：手沖注水到滴濾；冰滴加冰水、開閥，以及背景滴的時候"""
        if self.method == "espresso":
            return False
        ss = self.session
        if ss is not None:
            return getattr(ss.stage, "phase", "") in brew.FOCUS_PHASES[self.method]
        b = self.cold
        return self.method == "colddrip" and b is not None and not b.get("done")

    def update_zoom(self, dt):
        target = 1.0 if self.brew_focus() else 0.0
        step = brew.ZOOM_SPEED * dt
        z = self.brew_zoom
        self.brew_zoom = min(target, z + step) if target > z else max(target, z - step)

    def zoom_amount(self):
        return ease(self.brew_zoom)

    def gear_view(self):
        """器具圖層的放大倍數與位置：(倍數 k, 中心在場景的 x, 器具座標的中心 x)"""
        e = self.zoom_amount()
        k0, k1 = brew.GEAR_K.get(self.method, 1.0), brew.GEAR_ZOOM.get(self.method, 1.0)
        gc = brew.FOCUS_X.get(self.method, 0.0)
        k = lerp(k0, k1, e)
        return k, lerp(gc * k0, self.machine.scene_w / 2, e), gc

    def gear_k(self):
        return self.gear_view()[0]

    def gear_to_scene(self, x, y):
        """器具座標 → 場景座標"""
        k, ox, gc = self.gear_view()
        return ox + (x - gc) * k, FLOOR - (FLOOR - y) * k

    def station_pos(self, name):
        """器具的位置：手沖壺是器具座標（在放大的器具圖層裡移動）；分享壺、冰滴壺會拿去倒，回傳場景座標"""
        scx = brew.PO_STAND_X
        if name == "kettle_rest":
            return scx + 28, FLOOR - 33
        if name == "kettle_pour":
            return scx + 3, FLOOR - 62 - 44 - 16      # 濾杯正上方
        if name == "server":                         # 分享壺的倒出口（左上壺嘴）
            return self.gear_to_scene(scx - 22, FLOOR - 62)
        return self.gear_to_scene(brew.CD_TOWER_X + 43 - 12, FLOOR - 6 - 64)    # carafe：冰滴壺的倒出口

    # ───────────── 繪圖 ─────────────
    def paint_station(self, p):
        ss = self.session
        st = ss.station if (ss is not None and ss.station is not None) else None
        vessel = ss.vessel if ss else None
        k, ox, gc = self.gear_view()
        p.save()
        p.translate(ox, FLOOR)                         # 器具圖層：放大、拉近時移到中央
        p.scale(k, k)
        p.translate(-gc, -FLOOR)
        self._paint_gear(p, st, vessel)
        p.restore()

    def _paint_gear(self, p, st, vessel):
        fade = 1 - self.zoom_amount()                  # 拉近時磨豆機淡出
        if fade > 0.01:
            p.save()
            p.setOpacity(fade)
            self.paint_drip_grinder(p, st)
            p.restore()
        if self.method == "pourover":
            if st is None:
                st = self._idle_po = getattr(self, "_idle_po", None) or brew.idle_pourover(self)
            self.paint_pourover(p, st, vessel)
        else:
            self.paint_cold_tower(p, st, vessel)

    def paint_drip_grinder(self, p, st):
        """手沖用磨豆機：豆倉、刻度盤、出粉口、接粉杯；磨豆時機身微震、粉落進接粉杯"""
        gx = brew.GRINDER_X
        grinding = bool(st and st.get("grinding"))
        catch = st.get("catch", 0.0) if st else 0.0
        jit = math.sin(self.anim_t * 90) * 0.35 if grinding else 0.0
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(C("#000000", 40))
        p.drawEllipse(QPointF(gx + 30, FLOOR), 32, 3)
        p.fillPath(rrect(gx, FLOOR - 9, gx + 60, FLOOR, 3), vgrad(FLOOR - 9, FLOOR, [(0, C("#3a3633")), (1, C("#1c1a18"))]))
        p.translate(jit, 0)
        # 機身
        body = rrect(gx + 6, FLOOR - 122, gx + 54, FLOOR - 9, 7)
        p.fillPath(body, hgrad(gx + 6, gx + 54, [(0, C("#b9b2a8")), (0.3, C("#efeae2")), (0.7, C("#ddd6cc")),
                                                 (1, C("#a59e94"))]))
        p.fillPath(rrect(gx + 6, FLOOR - 126, gx + 54, FLOOR - 118, 3), C("#3a3633"))
        # 豆倉（玻璃）＋豆子
        hop = QRectF(gx + 13, FLOOR - 168, 34, 42)
        p.fillPath(rrect(hop.left(), hop.top(), hop.right(), hop.bottom(), 4), C(GLASS, 55))
        level = clamp(self.hopper, 0, 1)
        if level > 0.01:
            beans = BEAN_COLORS.get(self.params.roast, BEAN_COLORS["中焙"])
            top = hop.bottom() - 3 - (hop.height() - 8) * level
            p.save()
            p.setClipRect(QRectF(hop.left() + 2, top, hop.width() - 4, hop.bottom() - top - 2))
            rnd = random.Random(7)
            y = hop.bottom() - 4
            while y > top - 4:
                for i in range(5):
                    x = hop.left() + 5 + i * 6.2 + rnd.uniform(-1.5, 1.5)
                    p.setBrush(C(beans[rnd.randrange(3)]))
                    p.drawEllipse(QPointF(x, y + rnd.uniform(-1, 1)), 3.0, 2.2)
                y -= 3.6
            p.restore()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#ffffff", 140), 1.0))
        p.drawRoundedRect(hop, 4, 4)
        p.setPen(Qt.NoPen)
        p.fillPath(rrect(gx + 11, FLOOR - 174, gx + 49, FLOOR - 167, 3), C("#3a3633"))
        # 刻度盤
        dc = QPointF(gx + 30, FLOOR - 98)
        p.setBrush(C("#3a3633"))
        p.drawEllipse(dc, 11, 11)
        p.setBrush(C("#d8d2c8"))
        p.drawEllipse(dc, 8, 8)
        p.setPen(QPen(C("#3a3633"), 0.8))
        for i in range(12):
            a = math.radians(i * 30)
            p.drawLine(QPointF(dc.x() + 6 * math.cos(a), dc.y() + 6 * math.sin(a)),
                       QPointF(dc.x() + 7.6 * math.cos(a), dc.y() + 7.6 * math.sin(a)))
        um = self.dp.po_grind if self.method == "pourover" else self.dp.cd_grind
        a = math.radians(-120 + 240 * clamp((um - 350) / 650, 0, 1))
        p.setPen(QPen(C("#c0392b"), 1.4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(dc, QPointF(dc.x() + 6 * math.sin(a), dc.y() - 6 * math.cos(a)))
        p.setPen(Qt.NoPen)
        p.setBrush(C("#7ad06a" if grinding else "#4a4a46"))       # 電源燈
        p.drawEllipse(QPointF(gx + 30, FLOOR - 78), 1.6, 1.6)
        # 出粉口與接粉杯
        p.fillPath(rrect(gx + 23, FLOOR - 66, gx + 37, FLOOR - 56, 2), C("#2a2725"))
        cup_top, cup_bot = FLOOR - 40, FLOOR - 9
        if grinding:
            p.setPen(QPen(C("#5a3a22", 200), 2.2, Qt.DotLine))
            p.drawLine(QPointF(gx + 30, FLOOR - 56), QPointF(gx + 30, cup_bot - 3 - 20 * catch))
            p.setPen(Qt.NoPen)
        p.translate(-jit, 0)
        cup = QPainterPath()
        cup.moveTo(gx + 17, cup_top)
        cup.lineTo(gx + 43, cup_top)
        cup.lineTo(gx + 41, cup_bot)
        cup.lineTo(gx + 19, cup_bot)
        cup.closeSubpath()
        p.fillPath(cup, hgrad(gx + 17, gx + 43, [(0, C("#7b8288")), (0.4, C("#e6eaed")), (1, C("#6a7177"))]))
        if catch > 0.02:
            look = ROAST_LOOK.get(self.params.roast, ROAST_LOOK["中焙"])
            p.setBrush(C(mix(look["amber"], "#8a5a34", 0.4)))
            p.drawEllipse(QPointF(gx + 30, cup_top + 2), 12 * clamp(catch * 1.4, 0.3, 1), 2.6)
        p.setBrush(C("#4a5056"))
        p.drawEllipse(QPointF(gx + 30, cup_top), 13, 2)
        p.restore()

    def paint_pourover(self, p, st, vessel):
        scx = brew.PO_STAND_X
        roast = self.params.roast
        res = self.session.brew_res if (self.session and self.session.brew_res) else None
        tds = res.tds if res else 1.3
        p.save()
        # 磅秤
        p.setPen(Qt.NoPen)
        p.fillPath(rrect(scx - 30, FLOOR - 7, scx + 30, FLOOR, 2), vgrad(FLOOR - 7, FLOOR, [(0, C("#3a3d40")), (1, C("#1e2022"))]))
        p.fillRect(QRectF(scx - 8, FLOOR - 4.5, 16, 3), C("#0a0c0d"))
        held = vessel is not None and vessel.get("kind") == "server"
        if not held:
            self.paint_server(p, scx - 22, FLOOR - 62, st["server"], roast, tds)
        if st["dripper"] > 0.01:
            p.save()
            p.setOpacity(st["dripper"])
            p.translate(0, -12 * (1 - st["dripper"]))
            self.paint_dripper(p, scx, FLOOR - 62, st, roast, tds)
            p.restore()
        k = st["kettle"]
        p.save()
        p.translate(k["x"], k["y"])
        if k["pour"] > 0:
            # 細口壺的水柱：從壺嘴落進濾杯口裡的液面（繞圈注水，落點跟著壺左右移）
            surf_y, _ = self.dripper_surface(st, FLOOR - 62 - 44)
            hx = k["x"] - 3 - k["x"]
            path = QPainterPath(QPointF(0, 0))
            path.cubicTo(QPointF(-1, 6), QPointF(hx, surf_y - k["y"] - 10), QPointF(hx, surf_y - k["y"]))
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(C("#9fb8c4", 200), 1.8, Qt.SolidLine, Qt.RoundCap))
            p.drawPath(path)
            p.setPen(QPen(C("#ffffff", 150), 0.6))
            p.drawPath(path)
        p.rotate(-k["tilt"])
        p.scale(0.62, 0.62)
        self.paint_kettle(p)
        p.restore()
        p.restore()

    def paint_server(self, p, x, y, grams, roast, tds):
        """分享壺（原點＝左上壺嘴）：玻璃壺身、刻度、把手，裡面的咖啡"""
        p.save()
        p.translate(x, y)
        body = QPainterPath()
        body.moveTo(0, 0)
        body.lineTo(44, 0)
        body.cubicTo(QPointF(46, 20), QPointF(48, 46), QPointF(42, 56))
        body.lineTo(4, 56)
        body.cubicTo(QPointF(-3, 46), QPointF(-1, 20), QPointF(1, 4))
        body.closeSubpath()
        p.setPen(Qt.NoPen)
        p.fillPath(body, C(GLASS, 50))
        frac = clamp(grams / 300.0, 0, 1)
        if frac > 0.004:
            top = 56 - 50 * frac
            col, alpha = brew_color(roast, tds)
            liquid = QPainterPath()
            liquid.addRect(QRectF(-4, top, 54, 60))
            p.fillPath(body.intersected(liquid), vgrad(top, 56, [(0, C(mix(col, "#e8b878", 0.2), alpha)),
                                                                 (1, C(col, alpha))]))
            p.fillRect(QRectF(3, top, 40, 1), C("#ffffff", 50))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#ffffff", 150), 1.0))
        p.drawPath(body)
        p.setPen(QPen(C("#ffffff", 90), 0.6))
        for i in range(1, 4):                       # 刻度
            yy = 56 - i * 12
            p.drawLine(QPointF(32, yy), QPointF(38, yy))
        p.setPen(QPen(C("#ffffff", 120), 1.6))
        p.drawLine(QPointF(8, 6), QPointF(7, 46))     # 反光
        hd = QPainterPath(QPointF(44, 8))
        hd.cubicTo(QPointF(58, 8), QPointF(58, 36), QPointF(44, 38))
        p.setPen(QPen(C("#2a2c2f"), 3.2, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(hd)
        p.restore()

    @staticmethod
    def dripper_surface(st, top_y):
        """濾杯裡粉床／水面的 (y, 半寬)：只有粉時在杯口下方，注水後往上升到接近杯口；悶蒸時粉床微微鼓起"""
        fill = 0.3 * st["bed"] + 0.7 * clamp(st["water"] / 110, 0, 1) + 0.06 * st["swell"]
        depth = 6.0 * (1 - clamp(fill, 0, 1)) + 0.5
        return top_y + depth, 24.5 - depth * 1.2

    def paint_dripper(self, p, cx, base_y, st, roast, tds):
        """V 形濾杯（底部尖端插在分享壺口）：濾紙、粉床、水位、底下滴落"""
        top_y = base_y - 44
        cone = QPainterPath()
        cone.moveTo(cx - 26, top_y)
        cone.lineTo(cx + 26, top_y)
        cone.lineTo(cx + 8, base_y - 6)
        cone.lineTo(cx - 8, base_y - 6)
        cone.closeSubpath()
        p.setPen(Qt.NoPen)
        p.fillPath(cone, hgrad(cx - 26, cx + 26, [(0, C("#d9d4cc")), (0.35, C("#fbf9f5")), (1, C("#c9c2b8"))]))
        p.fillPath(rrect(cx - 30, base_y - 8, cx + 30, base_y - 3, 2), C("#e6e1d9"))     # 底座
        p.fillRect(QRectF(cx - 5, base_y - 3, 10, 4), C("#d8d2c8"))
        # 杯口往裡看：濾紙內壁，粉床／水面在杯口裡面，水越多液面越高（被杯口裁切）
        mouth = QRectF(cx - 25, top_y - 6.5, 50, 13)
        rim = QPainterPath()
        rim.addEllipse(mouth)
        p.save()
        p.setClipPath(rim)
        p.fillRect(mouth, vgrad(mouth.top(), mouth.bottom(), [(0, C(mix(PAPER, "#b8a88e", 0.35))), (1, C(PAPER))]))
        bed = st["bed"]
        if bed > 0.01:
            look = ROAST_LOOK.get(roast, ROAST_LOOK["中焙"])
            wet = clamp(st["swell"], 0, 1)
            grounds = mix(mix(look["amber"], "#8a5a34", 0.4), look["deep"], 0.4 + 0.5 * wet)
            sy, r = self.dripper_surface(st, top_y)
            ry = 6.0 * r / 24
            col = grounds
            if st["water"] > 1:                      # 粉被水淹過：表面是帶泡沫的咖啡液
                col = mix(grounds, "#b07a46", 0.3 + 0.2 * clamp(st["water"] / 110, 0, 1))
            p.setBrush(C(col))
            p.drawEllipse(QPointF(cx, sy), r, ry)
            p.setBrush(C("#ffffff", 26))
            p.drawEllipse(QPointF(cx - r * 0.25, sy - ry * 0.3), r * 0.45, ry * 0.4)
            k = st["kettle"]
            if k["pour"] > 0:                        # 水柱落點的漣漪
                hx = k["x"] - 3
                p.setBrush(Qt.NoBrush)
                for i in range(2):
                    ph = (self.anim_t * 2.2 + i * 0.5) % 1
                    p.setPen(QPen(C("#f2e2c8", int(150 * (1 - ph))), 0.6))
                    p.drawEllipse(QPointF(hx, sy), 2 + 7 * ph, (2 + 7 * ph) * 0.2)
                p.setPen(Qt.NoPen)
            if st["swell"] > 0.3:                    # 悶蒸冒泡
                t = self.anim_t
                p.setBrush(C("#e8c89a", 140))
                for i in range(6):
                    ph = (t * 0.7 + i * 0.37) % 1
                    p.drawEllipse(QPointF(cx - 13 + i * 5.2, sy + math.sin(i * 2.1) * ry * 0.5), 1.3 * ph, 0.8 * ph)
        p.restore()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#b9b2a8"), 0.8))
        p.drawEllipse(mouth)
        for i in (-1, 0, 1):                        # 杯身的肋條
            p.drawLine(QPointF(cx + i * 10, top_y + 6), QPointF(cx + i * 4, base_y - 9))
        p.setPen(QPen(C("#ffffff", 140), 1.4))
        p.drawLine(QPointF(cx - 20, top_y + 4), QPointF(cx - 7, base_y - 10))
        # 滴落：出水多時是細流，少時是一滴一滴
        d = st["drip"]
        if d > 0.02:
            tip = base_y + 1
            surf = FLOOR - 6 - 50 * clamp(st["server"] / 300.0, 0, 1)
            col, alpha = brew_color(roast, tds)
            if d > 0.35:
                p.setPen(QPen(C(col, alpha), 1.2 + 0.8 * d, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(cx, tip), QPointF(cx, surf))
            else:
                ph = (self.anim_t * (1.5 + 4 * d)) % 1
                p.setPen(Qt.NoPen)
                p.setBrush(C(col, alpha))
                p.drawEllipse(QPointF(cx, lerp(tip, surf, ph)), 1.3, 1.8)

    def paint_cold_tower(self, p, st, vessel):
        """冰滴塔：木架、上層冰水、閥、中層咖啡粉、下層冰滴壺；st＝架設中的狀態（None＝背景滴或空塔）"""
        b = self.cold
        now = time.time()
        if st is not None:
            grounds, top, valve, prog = st["grounds"], st["top"], st["valve"], 0.0
        elif b is not None:
            grounds, top, valve, prog = 1.0, 1.0, 1.0, brew.cold_progress(b, now)
        else:
            grounds = top = valve = prog = 0.0                  # 還沒架：空的冰滴塔
        rate = b["rate"] if b else self.dp.cd_rate
        roast = b["roast"] if b else self.params.roast
        tds = b["res"][2] if b else 1.5
        sx = brew.CD_TOWER_X
        tcx = sx + 43
        p.save()
        p.setPen(Qt.NoPen)
        # 木架
        p.fillPath(rrect(sx + 4, FLOOR - 8, sx + 82, FLOOR, 2), vgrad(FLOOR - 8, FLOOR, [(0, C(WOOD[1])), (1, C(WOOD[2]))]))
        for x in (sx + 8, sx + 74):
            p.fillRect(QRectF(x, FLOOR - 266, 5, 258), hgrad(x, x + 5, [(0, C(WOOD[2])), (0.5, C(WOOD[1])), (1, C(WOOD[0]))]))
        p.fillPath(rrect(sx + 4, FLOOR - 270, sx + 82, FLOOR - 263, 2), C(WOOD[0]))
        for y in (FLOOR - 178, FLOOR - 100):            # 托架
            p.fillRect(QRectF(sx + 10, y, 66, 4), C(WOOD[0]))
        # 上層：冰水瓶
        water = top * (1 - prog)
        tb = QRectF(tcx - 20, FLOOR - 252, 40, 72)
        p.fillPath(rrect(tb.left(), tb.top(), tb.right(), tb.bottom(), 5), C(GLASS, 45))
        if water > 0.01:
            wt = tb.bottom() - 4 - (tb.height() - 10) * water
            p.fillPath(rrect(tb.left() + 2, wt, tb.right() - 2, tb.bottom() - 2, 4), C("#cfe2ea", 130))
            p.setBrush(C("#ffffff", 150))
            for i in range(3):                           # 浮在上面的冰塊
                p.drawRoundedRect(QRectF(tcx - 15 + i * 10, wt - 3 + (i % 2) * 2, 9, 7), 2, 2)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#ffffff", 140), 1.0))
        p.drawRoundedRect(tb, 5, 5)
        p.setPen(Qt.NoPen)
        # 閥
        p.fillPath(rrect(tcx - 3, FLOOR - 180, tcx + 3, FLOOR - 166, 1.5), C("#b8bec4"))
        p.save()
        p.translate(tcx + 4, FLOOR - 174)
        p.rotate(-60 * (1 - valve))
        p.fillPath(rrect(0, -1.5, 9, 1.5, 1), C("#7a8086"))
        p.restore()
        # 中層：咖啡粉
        mb = QRectF(tcx - 16, FLOOR - 150, 32, 44)
        p.fillPath(rrect(mb.left(), mb.top(), mb.right(), mb.bottom(), 3), C(GLASS, 45))
        look = ROAST_LOOK.get(roast, ROAST_LOOK["中焙"])
        if grounds > 0.01:
            gh = 30 * grounds
            g_top = mb.bottom() - 4 - gh
            dry = mix(look["amber"], "#8a5a34", 0.4)
            wet_to = g_top + gh * clamp(prog * 6, 0, 1)        # 一開始水慢慢滲下去
            p.fillRect(QRectF(mb.left() + 2, g_top, mb.width() - 4, gh), C(dry))
            if prog > 0:
                p.fillRect(QRectF(mb.left() + 2, g_top, mb.width() - 4, wet_to - g_top), C(look["deep"]))
        p.fillRect(QRectF(mb.left() + 2, mb.bottom() - 4, mb.width() - 4, 2), C(PAPER))    # 濾紙
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#ffffff", 140), 1.0))
        p.drawRoundedRect(mb, 3, 3)
        p.setPen(Qt.NoPen)
        p.fillPath(rrect(tcx - 2, mb.bottom(), tcx + 2, mb.bottom() + 6, 1), C("#b8bec4"))
        # 下層：冰滴壺
        held = vessel is not None and vessel.get("kind") == "carafe"
        filled = (b["servings"] / brew.COLD_SERVINGS if b.get("done") else prog) if b else 0.0
        if not held:                                     # 器具座標（station_pos 回傳的是場景座標）
            self.paint_carafe(p, tcx - 12, FLOOR - 6 - 64, filled, roast, tds)
        # 水滴：上面滴進粉層、下面滴進壺
        if b is not None and not b.get("done") and st is None:
            col, alpha = brew_color(roast, tds, 0.8)
            for off, y0, y1, c, al in ((0.0, FLOOR - 166, mb.top() + 14, "#d8e8ee", 200),
                                       (0.5, mb.bottom() + 6, FLOOR - 6 - 52 * filled - 4, col, alpha)):
                ph = brew.drop_phase(rate, now, off)
                p.setBrush(C(c, al))
                if ph <= 1:
                    p.drawEllipse(QPointF(tcx, lerp(y0, y1, ph * ph)), 1.4, 2.0)
                else:
                    p.drawEllipse(QPointF(tcx, y0 + 1), 1.0, 1.2)     # 掛在出口、慢慢長大
        p.restore()

    def paint_carafe(self, p, x, y, frac, roast, tds):
        """冰滴壺（原點＝左上壺口）：細頸燒瓶"""
        p.save()
        p.translate(x, y)
        body = QPainterPath()
        body.moveTo(1, 0)
        body.lineTo(23, 0)
        body.lineTo(23, 14)
        body.cubicTo(QPointF(36, 20), QPointF(38, 34), QPointF(36, 58))
        body.quadTo(QPointF(36, 64), QPointF(30, 64))
        body.lineTo(-6, 64)
        body.quadTo(QPointF(-12, 64), QPointF(-12, 58))
        body.cubicTo(QPointF(-14, 34), QPointF(-12, 20), QPointF(1, 14))
        body.closeSubpath()
        p.setPen(Qt.NoPen)
        p.fillPath(body, C(GLASS, 45))
        if frac > 0.004:
            top = 62 - 44 * frac
            col, alpha = brew_color(roast, tds, 0.8)
            liquid = QPainterPath()
            liquid.addRect(QRectF(-16, top, 56, 70))
            p.fillPath(body.intersected(liquid), vgrad(top, 64, [(0, C(mix(col, "#e8b878", 0.15), alpha)),
                                                                 (1, C(col, alpha))]))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#ffffff", 150), 1.0))
        p.drawPath(body)
        p.setPen(QPen(C("#ffffff", 110), 1.4))
        p.drawLine(QPointF(-6, 26), QPointF(-7, 54))
        p.restore()

    def paint_station_vessel(self, p, v):
        """倒進杯子時的分享壺／冰滴壺（paint_vessel 已經平移、旋轉到壺口）；跟器具一樣放大"""
        p.scale(self.gear_k(), self.gear_k())
        if v["kind"] == "server":
            self.paint_server(p, 0, 0, self.session.station["server"] * v.get("fill", 1.0),
                              self.params.roast, self.session.brew_res.tds)
        else:
            b = self.cold
            roast, tds = (b["roast"], b["res"][2]) if b else (self.params.roast, 1.5)
            left = (b["servings"] - 1 + v.get("fill", 1.0)) / brew.COLD_SERVINGS if b else 0.0
            self.paint_carafe(p, 0, 0, left, roast, tds)

    def paint_brew_liquid(self, p):
        """杯裡的手沖／冰滴咖啡（機身座標）"""
        c = self.contents
        if c["water"] <= 0.05:
            return
        ss = self.session
        res = ss.brew_res if (ss and ss.brew_res) else self.last_brew_res
        if res is None:
            return
        cold = self.drink_kind() == "cold_drip"
        roast = self.cold["roast"] if (cold and self.cold) else self.params.roast
        col, alpha = brew_color(roast, res.tds, 0.8 if cold else 1.0)
        ly, cx, rx, ry = self.surface_geom()
        yb = self.cup.liquid_bottom
        body = self.body_polygon(ly, rx, ry, cx)
        p.setPen(Qt.NoPen)
        p.setBrush(vgrad(ly, yb, [(0, C(mix(col, "#d9a060", 0.18), alpha)), (1, C(col, alpha))]))
        p.drawPolygon(body)
        p.setBrush(C(mix(col, "#e0b070", 0.3), alpha))
        p.drawEllipse(QPointF(cx, ly), rx, ry)
        p.setBrush(C("#ffffff", 40))
        p.drawEllipse(QPointF(cx - rx * 0.3, ly - ry * 0.2), rx * 0.35, ry * 0.4)

    def cup_alpha(self):
        """拉近時杯子淡出"""
        return 1 - self.zoom_amount()

    def paint_brew_background(self, p):
        """獨立畫面的背景圖層：只有杯子後半（器具每幀畫）"""
        m = self.machine
        p.save()
        p.translate(m.mx, m.my)
        self.cup.paint_back(p)
        p.restore()

    def paint_brew_front(self, p):
        m = self.machine
        p.save()
        p.translate(m.mx, m.my)
        self.cup.paint_front(p)
        p.restore()
