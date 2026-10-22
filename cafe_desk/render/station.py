"""手沖、冰滴、摩卡壺、虹吸壺的獨立畫面：手沖用磨豆機、濾杯／分享壺／細口壺、冰滴塔、瓦斯爐與摩卡壺、
虹吸壺與酒精燈，以及倒進杯子的分享壺／冰滴壺／摩卡壺／下壺

沖煮方式（app.method）不是 espresso 時，畫面不顯示咖啡機，改畫這裡的器具；杯子放在右邊桌上。
狀態：手沖在 session.station（brew.PourOverStage 更新，沒在沖時用 brew.idle_pourover）；冰滴架設中也在
session.station，滴的過程依 app.cold（背景批次，真實時間；切到別的沖煮方式也會繼續滴）。座標都是場景座標。
"""
import math
import random
import time

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QPainterPath

from .. import brew, vessels
from ..gfx import C, mix, vgrad, hgrad, rrect
from ..layout import ROAST_LOOK, BEAN_COLORS, FLOOR
from ..util import clamp, lerp
from ..workflow import ease

GLASS = "#dfe8ec"
WOOD = ("#8a5a34", "#b07a4a", "#5e3a1e")
PAPER = "#f3ece0"
WATER_C = "#cfe2ea"
# 摩卡壺：放在爐架上（器具座標）；壺本身的座標以壺底中心為原點
MOKA_BASE = FLOOR - 34
MOKA_SPOUT = (-30, -71)          # 壺嘴（倒咖啡的原點）相對壺底中心
MOKA_HELD = 0.78
ALU = [(0, "#737a81"), (0.16, "#c3c8cd"), (0.3, "#eef1f3"), (0.46, "#a4abb1"), (0.62, "#e1e5e8"),
       (0.8, "#959ca2"), (1, "#686f76")]                   # 八角鋁壺的刻面
# 虹吸壺：下壺球心（器具座標）；下壺壺口相對球心
SY_GLOBE_Y = FLOOR - 72
GLOBE_R = vessels.GLOBE_R
GLOBE_LIP = vessels.GLOBE_LIP


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
            return scx + 36, FLOOR - 33              # 壺嘴不要疊到分享壺的把手
        if name == "kettle_pour":
            return scx + 3, FLOOR - 62 - 44 - 28      # 濾杯正上方；夠高，傾斜時壺身與壺嘴根部才不會壓進杯口
        if name == "server":                         # 分享壺的倒出口（左上壺嘴）
            return self.gear_to_scene(scx - 22, FLOOR - 62)
        if name == "moka":                           # 摩卡壺的壺嘴
            return self.gear_to_scene(brew.MK_STOVE_X + MOKA_SPOUT[0], MOKA_BASE + MOKA_SPOUT[1])
        if name == "globe":                          # 虹吸壺下壺的壺口
            return self.gear_to_scene(brew.SY_X + GLOBE_LIP[0], SY_GLOBE_Y + GLOBE_LIP[1])
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
        elif self.method == "moka":
            self.paint_moka_station(p, st or brew.idle_moka(), vessel)
        elif self.method == "siphon":
            self.paint_siphon_station(p, st or brew.idle_siphon(), vessel)
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
        um = getattr(self.dp, brew.GRIND_ATTR[self.method])
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
        body = vessels.server()
        p.setPen(Qt.NoPen)
        p.fillPath(body, C(GLASS, 50))
        col, alpha = brew_color(roast, tds)
        self.paint_level(p, body, clamp(grams / 300.0, 0, 1), col, alpha, "#e8b878", 0.2)
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
        cone = QPainterPath()                       # 上緣跟著杯口橢圓的前半圈（直線的話左右兩角會凸出杯口）
        cone.moveTo(cx - 25, top_y)
        cone.arcTo(QRectF(cx - 25, top_y - 6.5, 50, 13), 180, 180)
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
        self.paint_drip(p, cx, base_y + 1, st, roast, tds)

    def paint_drip(self, p, cx, tip, st, roast, tds):
        """濾杯底下滴進分享壺：
        - 出水少：濾杯尖端先長出一顆水珠，長大到撐不住才掉下來，落下時越來越快、拉長
        - 出水多：一條細細的水柱，越往下越細（越流越快），到下面斷成一串水滴
        - 落到分享壺的液面泛起一圈漣漪
        水滴用真實時間（anim_t）推進，跟著重力加速；滴的頻率依出水量（st["drip"]）。"""
        if getattr(self, "_drip_of", None) is not st:          # 換了一壺：清掉上一壺還在空中的水滴
            self._drip_of, self._drips, self._drip_rings, self._drip_acc = st, [], [], 0.0
            self._drip_t = self.anim_t
        dt = clamp(self.anim_t - self._drip_t, 0.0, 0.1)
        self._drip_t = self.anim_t
        d = st["drip"]
        content = clamp(st["server"] / 300.0, 0, 1)
        pts = list(vessels.outline("server"))
        surf = FLOOR - 62 + (vessels.level_y(pts, content) if content > 0.004 else max(y for _, y in pts))
        surf = min(surf, FLOOR - 7)
        stream = d > 0.55                                        # 出水夠多：連成水柱
        brk = tip + (surf - tip) * (0.35 + 0.45 * clamp((d - 0.55) / 0.45, 0, 1))   # 水柱斷開的位置
        start = brk if stream else tip
        rate = (6 + 18 * d) if stream else (0.8 + 9 * d / 0.55)  # 每秒幾滴
        if d > 0.02:
            self._drip_acc += dt * rate
        while self._drip_acc >= 1.0:                            # 水珠撐不住了：掉下去
            self._drip_acc -= 1.0
            v0 = 120.0 if stream else 0.0
            self._drips.append([start, v0])
        g = 4200.0                                              # 重力（器具座標／秒²，約 2 mm 一單位）
        alive = []
        for drop in self._drips:
            drop[1] += g * dt
            drop[0] += drop[1] * dt
            if drop[0] >= surf:
                self._drip_rings.append([cx + random.uniform(-0.6, 0.6), 0.0])
            else:
                alive.append(drop)
        self._drips = alive
        self._drip_rings = [[x, a + dt] for x, a in self._drip_rings if a + dt < 0.45]
        col, alpha = brew_color(roast, tds)
        p.save()
        p.setPen(Qt.NoPen)
        if stream:                                              # 細水柱：上粗下細，輕微晃動
            w0 = 0.7 + 0.9 * clamp((d - 0.55) / 0.45, 0, 1)
            wob = math.sin(self.anim_t * 23) * 0.25
            col_path = QPainterPath(QPointF(cx - w0 / 2, tip))
            col_path.lineTo(cx + w0 / 2, tip)
            col_path.quadTo(QPointF(cx + w0 * 0.35 + wob, (tip + brk) / 2), QPointF(cx + w0 * 0.25 + wob, brk))
            col_path.lineTo(cx - w0 * 0.25 + wob, brk)
            col_path.quadTo(QPointF(cx - w0 * 0.35 + wob, (tip + brk) / 2), QPointF(cx - w0 / 2, tip))
            p.fillPath(col_path, C(col, alpha))
        elif d > 0.02 or self._drip_acc > 0.05:                 # 尖端正在長大的水珠
            r = 0.5 + 0.9 * clamp(self._drip_acc, 0, 1)
            p.setBrush(C(col, alpha))
            p.drawEllipse(QPointF(cx, tip + r * 0.9), r * 0.85, r)
        for y, v in self._drips:                                # 落下的水滴：越快拉得越長
            stretch = min(3.5, v / 260.0)
            p.setBrush(C(col, alpha))
            p.drawEllipse(QPointF(cx, y - stretch * 0.5), 0.8, 0.9 + stretch)
            p.setBrush(C("#ffffff", 70))
            p.drawEllipse(QPointF(cx - 0.3, y - stretch * 0.5 - 0.3), 0.25, 0.4 + stretch * 0.3)
        p.setBrush(Qt.NoBrush)
        for x, a in self._drip_rings:                           # 液面的漣漪
            k = a / 0.45
            p.setPen(QPen(C(mix(col, "#e8c8a0", 0.5), int(150 * (1 - k))), 0.5))
            p.drawEllipse(QPointF(x, surf), 1.5 + 9 * k, (1.5 + 9 * k) * 0.22)
        p.restore()

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
        body = vessels.carafe()
        p.setPen(Qt.NoPen)
        p.fillPath(body, C(GLASS, 45))
        col, alpha = brew_color(roast, tds, 0.8)
        self.paint_level(p, body, vessels.CARAFE_FULL * clamp(frac, 0, 1), col, alpha, "#e8b878", 0.15)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#ffffff", 150), 1.0))
        p.drawPath(body)
        p.setPen(QPen(C("#ffffff", 110), 1.4))
        p.drawLine(QPointF(-6, 26), QPointF(-7, 54))
        p.restore()

    # ───────────── 摩卡壺 ─────────────
    def paint_moka_station(self, p, st, vessel):
        """小瓦斯爐（爐架、旋鈕、火焰）上的摩卡壺；倒咖啡時壺拿走了只畫爐子"""
        cx = brew.MK_STOVE_X
        held = vessel is not None and vessel.get("kind") == "moka"
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(C("#000000", 45))
        p.drawEllipse(QPointF(cx, FLOOR), 42, 3)
        # 爐身與面板
        p.fillPath(rrect(cx - 38, FLOOR - 21, cx + 38, FLOOR, 4),
                   vgrad(FLOOR - 21, FLOOR, [(0, C("#45494e")), (1, C("#1b1d20"))]))
        p.fillPath(rrect(cx - 40, FLOOR - 24, cx + 40, FLOOR - 19, 2),
                   hgrad(cx - 40, cx + 40, [(0, C("#7c838a")), (0.5, C("#d9dde0")), (1, C("#7c838a"))]))
        kc = QPointF(cx + 26, FLOOR - 10)               # 旋鈕：點火時轉過去
        p.setBrush(C("#121314"))
        p.drawEllipse(kc, 5.5, 5.5)
        p.setBrush(C("#2c2f33"))
        p.drawEllipse(kc, 4.2, 4.2)
        a = math.radians(-90 + 90 * st["knob"])
        p.setPen(QPen(C("#e8e2d6"), 1.2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(kc, QPointF(kc.x() + 3.6 * math.cos(a), kc.y() + 3.6 * math.sin(a)))
        p.setPen(Qt.NoPen)
        p.setBrush(C("#ff7a3a" if st["flame"] > 0.05 else "#4a4440"))
        p.drawEllipse(QPointF(cx + 14, FLOOR - 10), 1.3, 1.3)
        # 爐頭、後半圈火焰、爐架
        p.setBrush(C("#2a2c2f"))
        p.drawEllipse(QPointF(cx, FLOOR - 25), 13, 2.6)
        self.paint_burner_flame(p, cx, FLOOR - 26, st["flame"], back=True)
        p.setBrush(C("#1a1b1d"))
        for dx in (-31, 27):
            p.drawRect(QRectF(cx + dx, MOKA_BASE - 1, 4, FLOOR - 23 - MOKA_BASE + 1))
        p.drawRect(QRectF(cx - 33, MOKA_BASE - 1, 66, 2.4))
        if not held:
            self.paint_moka_pot(p, cx, MOKA_BASE, st)
        self.paint_burner_flame(p, cx, FLOOR - 26, st["flame"], back=False)
        p.restore()

    def paint_burner_flame(self, p, cx, y, f, back):
        """爐火：一圈藍色火舌（back＝後半圈，畫在壺後面），火越大火圈越大、火舌越高"""
        if f <= 0.01:
            return
        t = self.anim_t
        n = 12
        spread = 9 + 12 * f
        for i in range(n):
            a = (i + 0.5) / n * math.pi * 2
            if (math.sin(a) > 0) == back:
                continue
            x = cx + math.cos(a) * spread
            yb = y + math.sin(a) * 2.2
            h = (4 + 10 * f) * (0.78 + 0.22 * math.sin(t * 23 + i * 1.7))
            lean = math.cos(a) * 3.0 * f              # 外圈的火往外翻
            path = QPainterPath(QPointF(x - 2.2, yb))
            path.quadTo(QPointF(x - 1.6 + lean * 0.4, yb - h * 0.6), QPointF(x + lean, yb - h))
            path.quadTo(QPointF(x + 1.6 + lean * 0.4, yb - h * 0.6), QPointF(x + 2.2, yb))
            path.closeSubpath()
            a0 = int(200 * min(1.0, f * 1.6))
            p.fillPath(path, vgrad(yb - h, yb, [(0, C("#7fb6ff", 0)), (0.45, C("#4f8dff", a0)),
                                                (1, C("#c9e6ff", a0))]))

    @staticmethod
    def _alu(x0, x1):
        return hgrad(x0, x1, [(k, C(c)) for k, c in ALU])

    @staticmethod
    def _facets(p, cx, yb, yt, wb, wt):
        """八角壺的稜線"""
        for f in (-0.62, 0.0, 0.62):
            p.setPen(QPen(C("#ffffff", 70), 0.6))
            p.drawLine(QPointF(cx + f * wb + 0.6, yb), QPointF(cx + f * wt + 0.6, yt))
            p.setPen(QPen(C("#000000", 40), 0.6))
            p.drawLine(QPointF(cx + f * wb - 0.6, yb), QPointF(cx + f * wt - 0.6, yt))
        p.setPen(Qt.NoPen)

    def moka_color(self):
        res = self.session.brew_res if (self.session and self.session.brew_res) else None
        return brew_color(self.params.roast, res.tds if res else 3.2)

    def paint_moka_pot(self, p, cx, y0, st):
        """八角鋁製摩卡壺（cx, y0＝壺底中心）：下壺、粉槽、上壺（轉開時往上提）、把手、蓋子；
        蓋子打開時看得到上壺裡的咖啡，以及從中柱冒出來的咖啡、收尾的噴濺與蒸氣"""
        p.save()
        p.setPen(Qt.NoPen)
        lift = st["lift"]
        low = QPainterPath()
        low.moveTo(cx - 22, y0)
        low.lineTo(cx + 22, y0)
        low.lineTo(cx + 17, y0 - 30)
        low.lineTo(cx - 17, y0 - 30)
        low.closeSubpath()
        p.fillPath(low, self._alu(cx - 22, cx + 22))
        self._facets(p, cx, y0, y0 - 30, 22, 17)
        p.setBrush(C("#c9a24a"))                        # 洩壓閥
        p.drawEllipse(QPointF(cx + 11, y0 - 15), 2.2, 2.2)
        p.setBrush(C("#8a6a2a"))
        p.drawEllipse(QPointF(cx + 11, y0 - 15), 0.9, 0.9)
        if lift > 0.02:                                 # 上壺拿起來：看得到粉槽
            p.setBrush(C("#9aa1a7"))
            p.drawEllipse(QPointF(cx, y0 - 30), 16, 3.2)
            p.setBrush(C("#5a6066"))
            p.drawEllipse(QPointF(cx, y0 - 30), 13.5, 2.4)
            if st["basket"] > 0.01:
                look = ROAST_LOOK.get(self.params.roast, ROAST_LOOK["中焙"])
                p.setBrush(C(mix(look["amber"], "#8a5a34", 0.4)))
                p.drawEllipse(QPointF(cx, y0 - 30.6), 13 * clamp(st["basket"] * 1.2, 0.3, 1), 2.3)
        p.save()
        p.translate(st.get("twist", 0.0) * 1.2, -26 * lift)
        p.fillPath(rrect(cx - 18.5, y0 - 35, cx + 18.5, y0 - 29.5, 1.5),
                   hgrad(cx - 18.5, cx + 18.5, [(0, C("#5c6369")), (0.4, C("#b9bfc4")), (1, C("#50575d"))]))
        up = QPainterPath()
        up.moveTo(cx - 17, y0 - 35)
        up.lineTo(cx + 17, y0 - 35)
        up.lineTo(cx + 23, y0 - 66)
        up.lineTo(cx - 23, y0 - 66)
        up.closeSubpath()
        p.fillPath(up, self._alu(cx - 23, cx + 23))
        self._facets(p, cx, y0 - 35, y0 - 66, 17, 23)
        spout = QPainterPath(QPointF(cx - 22, y0 - 66))  # 壺嘴：往左上翹
        spout.lineTo(cx + MOKA_SPOUT[0], y0 + MOKA_SPOUT[1])
        spout.lineTo(cx - 20, y0 - 57)
        spout.closeSubpath()
        p.fillPath(spout, hgrad(cx - 30, cx - 20, [(0, C("#8d949a")), (1, C("#d6dade"))]))
        hd = QPainterPath(QPointF(cx + 20, y0 - 63))     # 黑色電木把手
        hd.lineTo(cx + 33, y0 - 61)
        hd.quadTo(QPointF(cx + 37, y0 - 60), QPointF(cx + 36, y0 - 55))
        hd.lineTo(cx + 31, y0 - 41)
        hd.quadTo(QPointF(cx + 29, y0 - 37), QPointF(cx + 26, y0 - 40))
        hd.lineTo(cx + 29, y0 - 52)
        hd.lineTo(cx + 19, y0 - 54)
        hd.closeSubpath()
        p.fillPath(hd, C("#1c1c1e"))
        p.setPen(QPen(C("#ffffff", 50), 0.8))
        p.drawLine(QPointF(cx + 23, y0 - 62), QPointF(cx + 33, y0 - 60))
        p.setPen(Qt.NoPen)
        lid = st["lid"]
        top = y0 - 66
        if lid > 0.02:                                   # 打開蓋子往裡看：上壺內壁、咖啡液面、中柱、噴濺
            col, alpha = self.moka_color()
            crema = mix(col, "#c8894a", 0.35)
            k = st["coffee"]
            g = st["gush"]
            t = self.anim_t
            mouth = QPainterPath()
            mouth.addEllipse(QPointF(cx, top), 22, 4.5)
            surf = top + 0.4 + 5.0 * (1 - k) ** 1.3       # 液面：咖啡越多越接近壺口（深的時候被近側壺口擋住大半）
            col_top = top + 1.2                          # 中柱的管口，就在壺口下面一點
            p.save()
            p.setClipPath(mouth)
            p.fillPath(mouth, vgrad(top - 4.5, top + 4.5, [(0, C("#4a5056")), (0.5, C("#24272a")),
                                                           (1, C("#121315"))]))
            if k > 0.01:
                p.setBrush(C(col, alpha))
                p.drawEllipse(QPointF(cx, surf), 21.5, 4.3)
                p.setBrush(C(crema, int(110 + 60 * g)))  # 液面上的一層淡淡的 crema
                p.drawEllipse(QPointF(cx - 2, surf - 0.6), 13, 2.2)
                if g > 0.05:                             # 從中柱流下來的漣漪
                    p.setBrush(Qt.NoBrush)
                    for i in range(2):
                        ph = (t * 1.8 + i * 0.5) % 1
                        p.setPen(QPen(C(crema, int(160 * (1 - ph))), 0.5))
                        p.drawEllipse(QPointF(cx, surf), 3 + 9 * ph, (3 + 9 * ph) * 0.2)
                    p.setPen(Qt.NoPen)
            if surf > col_top + 0.3:                     # 中柱露在液面上的那段
                p.fillRect(QRectF(cx - 2.2, col_top, 4.4, surf - col_top),
                           hgrad(cx - 2.2, cx + 2.2, [(0, C("#6a7177")), (0.4, C("#d5d9dc")), (1, C("#5a6066"))]))
                if g > 0.01:                             # 咖啡沿著中柱外面流下去
                    p.fillRect(QRectF(cx - 2.4, col_top, 4.8, surf - col_top), C(col, int(200 * min(1.0, g * 1.5))))
            p.restore()
            p.setBrush(C("#2a2d30"))
            p.drawEllipse(QPointF(cx, col_top), 2.2, 0.8)
            if g > 0.01:                                 # 管口冒出來的咖啡：一小團，表面是 crema
                h = 1.2 + 2.2 * g + 0.5 * math.sin(t * 19)
                dome = QPainterPath(QPointF(cx - 2.4 - 0.8 * g, col_top))
                dome.quadTo(QPointF(cx, col_top - h * 1.6), QPointF(cx + 2.4 + 0.8 * g, col_top))
                dome.closeSubpath()
                p.fillPath(dome, vgrad(col_top - h, col_top, [(0, C(crema, 240)), (1, C(col, 240))]))
            sp = st["sputter"]
            if sp > 0.01:                                # 收尾：從管口噴出的小滴
                p.setBrush(C(crema, 220))
                for i in range(int(3 + 7 * sp)):
                    ph = (t * 2.6 + i * 0.37) % 1
                    x = cx + math.sin(i * 2.3) * (1 + 8 * ph)
                    y = col_top - 1 - math.sin(ph * math.pi) * (3 + 7 * sp)
                    p.drawEllipse(QPointF(x, y), 0.8, 0.8)
            steam = max(sp, 0.35 * g * k)
            if steam > 0.02:                             # 熱氣
                for i in range(6):
                    ph = (t * 0.55 + i / 6) % 1
                    x = cx - 5 + i * 2 + math.sin(t * 1.3 + i) * 4 * ph
                    p.setBrush(C("#ffffff", int(70 * steam * (1 - ph))))
                    p.drawEllipse(QPointF(x, top - 4 - 34 * ph), 2.5 + 5 * ph, 2.5 + 5 * ph)
        p.save()                                         # 蓋子：鉸鏈在右邊，打開時往上翻
        p.translate(cx + 21, top)
        p.rotate(84 * lid)
        cap = QPainterPath(QPointF(-44, 0))
        cap.lineTo(0, 0)
        cap.lineTo(-3, -4)
        cap.lineTo(-41, -4)
        cap.closeSubpath()
        p.fillPath(cap, self._alu(-44, 0))
        p.fillPath(rrect(-25, -7.5, -17, -4, 1.5), C("#1c1c1e"))     # 蓋鈕
        p.restore()
        p.restore()
        p.restore()

    # ───────────── 虹吸壺 ─────────────
    def paint_siphon_station(self, p, st, vessel):
        """虹吸壺：底座、支架、酒精燈、下壺（球形）、上壺（濾布、玻璃管）、攪拌棒"""
        cx, gy = brew.SY_X, SY_GLOBE_Y
        held = vessel is not None and vessel.get("kind") == "globe"
        res = self.session.brew_res if (self.session and self.session.brew_res) else None
        col, alpha = brew_color(self.params.roast, res.tds if res else 1.35)
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(C("#000000", 45))
        p.drawEllipse(QPointF(cx + 6, FLOOR), 44, 3)
        p.fillPath(rrect(cx - 34, FLOOR - 6, cx + 46, FLOOR, 3),
                   vgrad(FLOOR - 6, FLOOR, [(0, C("#4a3a2c")), (1, C("#2a2019"))]))
        p.fillRect(QRectF(cx + 38, gy - 44, 4, FLOOR - 6 - (gy - 44)),
                   hgrad(cx + 38, cx + 42, [(0, C("#6c737a")), (0.5, C("#e2e6e9")), (1, C("#6c737a"))]))
        p.setBrush(C("#2a2c2f"))
        p.drawEllipse(QPointF(cx + 40, gy - 45), 3, 3)
        self.paint_lamp(p, cx, FLOOR - 6, st["flame"])
        if not held:
            self.paint_globe(p, cx, gy, st["lower"], st["lower_coffee"], col, alpha, st["boil"])
        p.fillRect(QRectF(cx + 8, gy - 35, 31, 3.5),
                   vgrad(gy - 35, gy - 31.5, [(0, C("#d5d9dc")), (1, C("#7c838a"))]))   # 夾具
        self.paint_upper_bowl(p, cx, gy, st, col, alpha)
        p.restore()

    def paint_lamp(self, p, cx, y, flame):
        """酒精燈（cx, y＝燈底中心）：玻璃燈身、酒精、燈芯；火焰外黃內藍、輕輕搖晃"""
        p.save()
        p.setPen(Qt.NoPen)
        body = QPainterPath(QPointF(cx - 15, y))
        body.lineTo(cx + 15, y)
        body.quadTo(QPointF(cx + 18, y - 14), QPointF(cx + 8, y - 20))
        body.lineTo(cx - 8, y - 20)
        body.quadTo(QPointF(cx - 18, y - 14), QPointF(cx - 15, y))
        body.closeSubpath()
        p.fillPath(body, C(GLASS, 60))
        alc = QPainterPath()
        alc.addRect(QRectF(cx - 20, y - 10, 40, 10))
        p.fillPath(body.intersected(alc), C("#b9c7f0", 110))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#ffffff", 140), 0.9))
        p.drawPath(body)
        p.setPen(Qt.NoPen)
        p.fillPath(rrect(cx - 6, y - 24, cx + 6, y - 19, 1.5), C("#b8bec4"))
        p.fillRect(QRectF(cx - 1.5, y - 28, 3, 4), C("#efe4c8"))
        if flame > 0.01:
            t = self.anim_t
            h = 16 * flame * (0.9 + 0.1 * math.sin(t * 17))
            sway = math.sin(t * 5) * 1.2 * flame
            fl = QPainterPath(QPointF(cx - 4, y - 27))
            fl.quadTo(QPointF(cx - 5 + sway * 0.3, y - 27 - h * 0.5), QPointF(cx + sway, y - 27 - h))
            fl.quadTo(QPointF(cx + 5 + sway * 0.3, y - 27 - h * 0.5), QPointF(cx + 4, y - 27))
            fl.closeSubpath()
            p.fillPath(fl, vgrad(y - 27 - h, y - 27, [(0, C("#ffb347", 0)), (0.35, C("#ffd36a", 210)),
                                                      (0.8, C("#ff9a3a", 200)), (1, C("#6fa8ff", 210))]))
            p.setBrush(C("#8fbaff", 170))
            p.drawEllipse(QPointF(cx, y - 29), 1.6, 2.6)
        p.restore()

    def paint_globe(self, p, cx, cy, frac, coffee, col, alpha, boil, handle=False):
        """下壺（cx, cy＝球心）：球形玻璃加短頸；frac＝液量，coffee＝液體是咖啡的程度；boil＝冒泡"""
        r = GLOBE_R
        p.save()
        p.setPen(Qt.NoPen)
        body = vessels.globe(cx, cy)
        p.fillPath(body, C(GLASS, 45))
        lcol, lal = mix(WATER_C, col, coffee), int(lerp(110, alpha, coffee))
        region = self.paint_level(p, body, frac, lcol, lal, "#ffffff", 0.12)
        top = region.boundingRect().top() if not region.isEmpty() else cy + r
        if boil > 0.01 and frac > 0.02:                  # 氣泡：從底部與玻璃管口往上冒
            t = self.anim_t
            for i in range(int(4 + 16 * boil)):
                ph = (t * (0.9 + 0.3 * (i % 3)) + i * 0.173) % 1
                x = cx + (math.sin(i * 2.7) * r * 0.55 if i % 2 else math.sin(i * 1.3) * 2.5)
                y = lerp(cy + r - 3, top + 1, ph)
                rr = 0.6 + 1.5 * boil * ph
                p.setBrush(C("#ffffff", int(160 * (1 - ph * 0.5))))
                p.drawEllipse(QPointF(x + math.sin(t * 7 + i) * 0.6, y), rr, rr)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#ffffff", 150), 1.0))
        p.drawPath(body)
        p.setPen(QPen(C("#ffffff", 120), 1.6))
        p.drawArc(QRectF(cx - r + 4, cy - r + 4, 2 * r - 8, 2 * r - 8), 110 * 16, 55 * 16)
        p.setPen(Qt.NoPen)
        if handle:                                       # 拿起來倒的時候：夾具當把手
            p.fillRect(QRectF(cx + 7, cy - 31, 26, 3.5), vgrad(cy - 31, cy - 27.5, [(0, C("#d5d9dc")),
                                                                                   (1, C("#7c838a"))]))
        p.restore()

    def paint_upper_bowl(self, p, cx, gy, st, col, alpha):
        """上壺：玻璃管插進下壺、濾布、液體（水→咖啡）、浮在上面的粉層、抽完後的粉山、攪拌棒"""
        a = st["upper_alpha"]
        if a <= 0.01:
            return
        p.save()
        p.setOpacity(a)
        p.translate(0, -30 * st["upper_lift"])
        p.setPen(Qt.NoPen)
        p.fillRect(QRectF(cx - 1.6, gy - 34, 3.2, 50), C(GLASS, 90))          # 玻璃管
        bowl = QPainterPath(QPointF(cx - 5, gy - 34))
        for x, y in ((cx - 5, gy - 48), (cx - 20, gy - 60), (cx - 20, gy - 114), (cx + 20, gy - 114),
                     (cx + 20, gy - 60), (cx + 5, gy - 48), (cx + 5, gy - 34)):
            bowl.lineTo(x, y)
        bowl.closeSubpath()
        p.fillPath(bowl, C(GLASS, 45))
        look = ROAST_LOOK.get(self.params.roast, ROAST_LOOK["中焙"])
        up = st["upper"]
        top = gy - 58 - 52 * up
        if up > 0.01:
            m = st["mixed"]
            lcol, lal = mix(WATER_C, col, m), int(lerp(110, alpha, m))
            liquid = QPainterPath()
            liquid.addRect(QRectF(cx - 22, top, 44, gy - 34 - top))
            p.fillPath(bowl.intersected(liquid), vgrad(top, gy - 48, [(0, C(mix(lcol, "#ffffff", 0.1), lal)),
                                                                      (1, C(lcol, lal))]))
            g = st["grounds"]
            if g > 0.01:                                 # 粉層浮在上面；攪拌時表面起伏
                thick = 4 + 4 * g * (1 - 0.4 * st["paddle"])
                wob = math.sin(st["stir"]) * 2.0 * st["paddle"]
                layer = QPainterPath(QPointF(cx - 21, top + thick))
                layer.lineTo(cx - 21, top - wob)
                layer.quadTo(QPointF(cx, top + wob * 1.5), QPointF(cx + 21, top + wob))
                layer.lineTo(cx + 21, top + thick)
                layer.closeSubpath()
                p.fillPath(bowl.intersected(layer), C(mix(look["deep"], "#6a4426", 0.35), int(235 * g)))
                p.setBrush(C("#d8b07a", int(120 * g)))
                p.drawEllipse(QPointF(cx, top + 0.5), 18, 1.4)
        p.setBrush(C(PAPER, 190))                        # 濾布與鏈子
        p.drawEllipse(QPointF(cx, gy - 58), 13, 2)
        p.setPen(QPen(C("#b8bec4"), 0.6))
        p.drawLine(QPointF(cx, gy - 58), QPointF(cx, gy - 36))
        p.setPen(Qt.NoPen)
        d = st["dome"]
        if d > 0.01 and up < 0.6:                        # 抽完：粉在濾布上鼓成小山
            mound = QPainterPath(QPointF(cx - 16, gy - 56))
            mound.quadTo(QPointF(cx, gy - 56 - 24 * d), QPointF(cx + 16, gy - 56))
            mound.closeSubpath()
            p.fillPath(mound, C(mix(look["deep"], "#6a4426", 0.25)))
        if st["paddle"] > 0.01:                          # 竹攪拌棒
            sx = cx + math.sin(st["stir"]) * 8
            p.save()
            p.setOpacity(a * st["paddle"])
            p.setPen(QPen(C("#c9a46a"), 2.2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(sx, gy - 72), QPointF(cx + 12 + math.sin(st["stir"]) * 2, gy - 140))
            p.setPen(Qt.NoPen)
            p.fillPath(rrect(sx - 3, gy - 80, sx + 3, gy - 68, 1.5), C("#c9a46a"))
            p.restore()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#ffffff", 140), 1.0))
        p.drawPath(bowl)
        p.setPen(QPen(C("#ffffff", 110), 1.4))
        p.drawLine(QPointF(cx - 16, gy - 108), QPointF(cx - 16, gy - 66))
        p.setPen(Qt.NoPen)
        p.fillPath(rrect(cx - 10, gy - 37, cx + 10, gy - 31, 2), C("#3a2e28"))     # 橡膠圈
        p.restore()

    def paint_level(self, p, body, content, col, alpha, sheen, k):
        """容器裡的液體（液面在畫面上保持水平，液量佔內腔 content）：上淡下濃，液面一條反光；回傳液體的範圍"""
        region = vessels.liquid_region(p, body, content)
        if region.isEmpty():
            return region
        r = region.boundingRect()
        p.fillPath(region, vgrad(r.top(), r.bottom(), [(0, C(mix(col, sheen, k), alpha)), (1, C(col, alpha))]))
        line = vessels.surface_line(p, region)
        if line:
            p.setPen(QPen(C("#ffffff", 60), 0.9))
            p.drawLine(*line)
            p.setPen(Qt.NoPen)
        return region

    def paint_station_vessel(self, p, v):
        """倒進杯子時的分享壺／冰滴壺（paint_vessel 已經平移、旋轉到壺口）；跟器具一樣放大"""
        p.scale(self.gear_k(), self.gear_k())
        if v["kind"] == "server":
            self.paint_server(p, 0, 0, self.session.station["server"] * v.get("fill", 1.0),
                              self.params.roast, self.session.brew_res.tds)
        elif v["kind"] == "moka":
            # 拿起來倒的時候慢慢變小一點，才不會超出畫面右邊（在爐子上時跟原本一樣大）
            k = lerp(1.0, MOKA_HELD, clamp(abs(v["x"] - self.station_pos("moka")[0]) / 60, 0, 1))
            p.scale(k, k)
            self.paint_moka_pot(p, -MOKA_SPOUT[0], -MOKA_SPOUT[1], brew.idle_moka())
        elif v["kind"] == "globe":
            st = self.session.station
            col, alpha = brew_color(self.params.roast, self.session.brew_res.tds)
            self.paint_globe(p, -GLOBE_LIP[0], -GLOBE_LIP[1], st["lower"] * v.get("fill", 1.0), 1.0, col, alpha, 0.0,
                             handle=True)
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
