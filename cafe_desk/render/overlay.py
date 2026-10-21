"""覆蓋層：磅秤顯示（機身座標）、狀態列與萃取曲線卡片（視窗座標）、環境光"""
import time
from datetime import datetime

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QBrush, QFont, QFontMetricsF, QPainterPath, QColor, QPolygonF, QPixmap, QPainter

from ..gfx import C, mix, rrect
from ..layout import WIN_H, TOP_PAD
from ..drinks import DRINKS, ART_NAMES, MILK_NAMES, milk_plan, is_milk, base_of
from ..model import STYLES
from ..i18n import T
from .. import maintenance, festivals, brew
from ..util import clamp, lerp

STATUS_H = 52               # 狀態列快取圖的高度（視窗底部往上；膠囊在 WIN_H-50 到 WIN_H-6）

# 環境光關鍵時刻：(小時, 色調, 覆蓋強度, 夜晚程度)
LIGHT_KEYS = [
    (0.0, "#16203c", 0.34, 1.0),
    (5.0, "#16203c", 0.30, 0.9),
    (6.5, "#ffcfa0", 0.10, 0.3),
    (8.0, "#ffffff", 0.00, 0.0),
    (16.0, "#ffffff", 0.00, 0.0),
    (17.5, "#ffb068", 0.14, 0.15),
    (19.0, "#ff9c50", 0.13, 0.5),
    (21.0, "#1e2a4a", 0.24, 0.85),
    (24.0, "#16203c", 0.34, 1.0),
]
LIGHT_PRESETS = {"day": 12.0, "dusk": 18.3, "night": 23.0}


def light_at(hour):
    for (h0, c0, a0, n0), (h1, c1, a1, n1) in zip(LIGHT_KEYS, LIGHT_KEYS[1:]):
        if h0 <= hour <= h1:
            k = (hour - h0) / (h1 - h0) if h1 > h0 else 0.0
            # 由無色調轉入時，色調直接用目標色，只讓強度漸變
            col = c1 if a0 == 0 else c0 if a1 == 0 else mix(c0, c1, k)
            return {"tint": col, "alpha": lerp(a0, a1, k), "night": lerp(n0, n1, k)}
    return {"tint": "#ffffff", "alpha": 0.0, "night": 0.0}


class OverlayRenderer:
    # ───────────── 環境光 ─────────────
    def update_light(self, force=False):
        now = time.perf_counter()
        if not force and now - getattr(self, "_light_clock", -1e9) < 30:
            return
        self._light_clock = now
        if self.light_mode in LIGHT_PRESETS:
            hour = LIGHT_PRESETS[self.light_mode]
        else:
            t = datetime.now()
            hour = t.hour + t.minute / 60
        self.light = light_at(hour)

    def paint_ambient(self, p):
        """只染在已畫出的像素上（SourceAtop），透明的地方保持透明"""
        a = self.light["alpha"]
        if a <= 0.005:
            return
        p.save()
        p.resetTransform()
        p.setCompositionMode(p.CompositionMode.CompositionMode_SourceAtop)
        col = QColor(self.light["tint"])
        col.setAlphaF(a)
        p.fillRect(QRectF(0, 0, self.width(), self.height()), col)
        p.restore()

    # ───────────── 磅秤（機身座標） ─────────────
    def paint_lcd(self, p):
        s = self.shot
        w = self.scale_weight()
        t = s.timer if s else 0.0
        f = QFont(self.mono, 9)
        f.setBold(True)
        p.setFont(f)
        glow = int(60 * (1 + 0.8 * self.light["night"]))
        rw, rt = self.machine.lcd_rects()
        for text, rect in ((f"{w:5.1f} g", rw), (f"{t:5.1f} s", rt)):
            p.setPen(C("#ffb040", glow))
            for dx, dy in ((-0.8, 0), (0.8, 0), (0, -0.8), (0, 0.8)):
                p.drawText(rect.translated(dx, dy), Qt.AlignRight | Qt.AlignVCenter, text)
            p.setPen(C("#ffc566"))
            p.drawText(rect, Qt.AlignRight | Qt.AlignVCenter, text)

    # ───────────── 狀態列（視窗座標） ─────────────
    def status_parts(self):
        ss = self.session
        if ss:
            text = ss.status()
            if text:
                return [(text, "#efe6da")]
        if self.job:
            return [(self.job_status(), "#9fd3e6")]
        if self.notice and time.perf_counter() < self.notice[1]:
            return [(self.notice[0], "#ffd27a")]
        if self.warming and self.method == "espresso":   # 咖啡機鍋爐預熱：手沖／冰滴畫面不顯示
            return [(T("預熱中…  {t:.1f}°C", t=self.boiler.temp), "#efe6da")]
        r = self.result
        o = self.order
        if self.order_mode and (r is None or (o is not None and o.state == "waiting")):
            if o is not None and o.state == "waiting":
                if self.business():
                    return [(T("{name} 點了{title}，咖啡師準備中…", name=T(o.name), title=o.title), "#efe6da")]
                return [(T("{name} 點了{title} · 點擊咖啡機開始製作", name=T(o.name), title=o.title), "#efe6da")]
            return [(T("等待客人點單…"), "#efe6da")]
        if r is None:
            return [(T("點擊咖啡機開始沖煮{name}", name=T(DRINKS[self.drink]["name"])), "#efe6da")]
        n = int(round(r.score / 20))
        return [("★" * n, "#ffc24a"), ("☆" * (5 - n), "#6a5e50"),
                (T("  {name} {score:.0f} 分 · {comment}", name=r.title or T(DRINKS[r.drink]["name"]), score=r.score,
                   comment=r.comment), "#efe6da")]

    def paint_status(self, p):
        """狀態列：內容沒變就直接貼上次畫好的圖（文字排版每幀重畫很花時間）"""
        fade = 1 - self.toast_now()[1]          # 成就通知出現時，狀態列淡出讓位
        if fade <= 0:
            return
        content = self.status_content()
        ratio = self.devicePixelRatioF() * self.scale_f
        key = (content, self._scene_w, self.ui, ratio)
        cache = getattr(self, "_status_cache", None)
        if cache is None or cache[0] != key:
            pm = QPixmap(int(self._scene_w * ratio), int(STATUS_H * ratio))
            pm.setDevicePixelRatio(ratio)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.Antialiasing)
            q.translate(0, -(WIN_H - STATUS_H))
            self.draw_status(q, *content)
            q.end()
            cache = self._status_cache = (key, pm)
        p.setOpacity(fade)
        p.drawPixmap(QPointF(0, WIN_H - STATUS_H), cache[1])

    def status_content(self):
        """狀態列要顯示的內容：(主要文字段落, 參數列, 參數列顏色, 節日圖示)；可以當快取的 key"""
        parts = self.status_parts()
        s = self.shot
        p_ = s.p if (s and not self.workflow) else self.params
        o = self.order
        if self.session:
            drink = self.session.drink
        elif self.order_mode and o is not None and o.state == "waiting":
            drink = o.drink
        else:
            drink = self.drink
        info = (f"{T(DRINKS[drink]['name'])} · {T(p_.roast)} {p_.dose:g}g→{p_.yield_g:g}g · {p_.grind_um:.0f}µm · "
                f"{p_.temp:g}°C")
        if self.session:
            dp = self.session.dp
        elif self.result is not None and self.last_dp is not None and not (o and o.state == "waiting"):
            dp = self.last_dp
        else:
            dp = self.dp
        milk_name = T(MILK_NAMES.get(dp.milk_kind, "牛奶"))
        family = base_of(drink)
        if family == "pourover":
            info = T("{name} · {roast} {dose:g}g：{water:.0f}g · {um:.0f}µm · {t:g}°C · 悶蒸 {b:.0f}s · {n:.0f} 段注水",
                     name=T(DRINKS[drink]["name"]), roast=T(p_.roast), dose=dp.po_dose, water=dp.po_dose * dp.po_ratio,
                     um=dp.po_grind, t=dp.po_temp, b=dp.po_bloom, n=dp.po_pulses)
        elif family == "moka":
            info = T("{name} · {roast} {dose:g}g · {um:.0f}µm · 火力 {h:g}",
                     name=T(DRINKS[drink]["name"]), roast=T(p_.roast), dose=dp.mk_dose, um=dp.mk_grind, h=dp.mk_heat)
        elif family == "siphon":
            info = T("{name} · {roast} {dose:g}g：{water:.0f}g · {um:.0f}µm · {t:g}°C · 浸泡 {s:.0f}s",
                     name=T(DRINKS[drink]["name"]), roast=T(p_.roast), dose=dp.sy_dose, water=dp.sy_dose * brew.SIPHON_RATIO,
                     um=dp.sy_grind, t=dp.sy_temp, s=dp.sy_steep)
        elif family == "colddrip":
            b = self.cold
            dose, ratio, um, rate = (b["dose"], b["ratio"], b["grind"], b["rate"]) if b else \
                (dp.cd_dose, dp.cd_ratio, dp.cd_grind, dp.cd_rate)
            info = T("{name} · {roast} {dose:g}g：{water:.0f}g · {um:.0f}µm · 每 10 秒 {r:.0f} 滴",
                     name=T(DRINKS[drink]["name"]), roast=T(b["roast"] if b else p_.roast), dose=dose,
                     water=dose * ratio, um=um, r=rate)
            if b is not None:
                info += (T(" · 還有 {n} 杯", n=b["servings"]) if b.get("done") else
                         T(" · 約 {m} 分鐘後滴完", m=brew.cold_remaining_min(b)))
        elif is_milk(drink):
            grams = milk_plan(drink, dp)[0]
            info += T(" · {milk} {g:.0f}g {t:.0f}°C", milk=milk_name, g=grams, t=dp.milk_temp)
            if drink == "mocha":
                info += T(" · 巧克力醬 {g:.0f}g", g=dp.choc_g)
            elif drink == "caramel_macchiato":
                info += T(" · 香草糖漿 {g:.0f}g", g=dp.vanilla_g)
            if dp.art in ART_NAMES and drink in ("latte", "cappuccino", "flat_white", "cortado") \
                    or (drink == "mocha" and not dp.whip and dp.art in ART_NAMES):
                info += T(" · 拉{name}", name=T(ART_NAMES[dp.art]))
        elif drink == "americano":
            info += T(" · 熱水 {g:.0f}g", g=dp.water_g)
        elif drink == "iced_americano":
            info += T(" · 冰塊 {n:.0f} · 冷水 {g:.0f}g", n=dp.ice, g=dp.iced_water_g)
        elif drink == "iced_latte":
            info += T(" · 冰塊 {n:.0f} · {milk} {g:.0f}g", n=dp.ice, milk=milk_name, g=dp.iced_milk_g)
        elif drink == "espresso_tonic":
            info += T(" · 冰塊 {n:.0f} · 通寧水 {g:.0f}g", n=dp.ice, g=dp.tonic_g)
        elif drink == "affogato":
            info += T(" · 香草冰淇淋 {g:.0f}g", g=dp.scoop_g)
        if s and s.style in STYLES:
            info += T(" · 以 {name} 標準評分", name=STYLES[s.style]["name"])
        if self.business():
            info = T("營業中 · 排隊 {n} · 今日 ${rev:,} · ", n=len(self.queue),
                     rev=self.stats.day()["revenue"]) + info
        elif self.order_mode and not self.busy():
            if o is None:
                remain = max(0, int(self.next_order_at - time.perf_counter()))
                info = T("顧客點單模式 · 下一位客人約 {sec}s 後到 · ", sec=remain) + info
            else:
                info = T("訂單 #{no} · ", no=o.no) + info
        elif self.auto and not self.busy():
            remain = max(0, int(self.interval - (time.perf_counter() - self.idle_since)))
            info = T("自動模式 · 下一杯 {sec}s · ", sec=remain) + info
        elif self.result is None and not self.session and self.method == "espresso":
            info = T("{machine} · 右鍵開啟選單 · 滑鼠停在機身上可看萃取曲線", machine=T(self.machine.name))
        due = maintenance.due(self.maint) if self.method == "espresso" else []   # 手沖／冰滴不提醒咖啡機清潔
        if due and not self.busy():                  # 清潔保養提醒
            names = T("、").join(T(maintenance.task_name(k, self.machine.traits)) for k in due)
            info = T("⚠ 該{task}了 · ", task=names) + info
        info_col = "#e0b060" if due and not self.busy() else "#a89a8a"
        return tuple(parts), info, info_col, self.status_festival()

    def draw_status(self, p, parts, info, info_col, fest):
        top = WIN_H - 50
        WIN_W = self._scene_w
        pill = rrect(20, top, WIN_W - 20, WIN_H - 6, 14)
        p.setBrush(QBrush(C("#120f0d", 180)))
        p.setPen(QPen(C("#ffffff", 28), 1))
        p.drawPath(pill)
        p.setBrush(Qt.NoBrush)

        f = QFont(self.ui, 9.5)
        f.setBold(True)
        p.setFont(f)
        parts = list(parts)
        fm = QFontMetricsF(f)
        total = sum(fm.horizontalAdvance(t) for t, _ in parts)
        room = WIN_W - 56
        if total > room:                         # 太長：最後一段加刪節號
            head = total - fm.horizontalAdvance(parts[-1][0])
            parts = parts[:-1] + [(fm.elidedText(parts[-1][0], Qt.ElideRight, room - head), parts[-1][1])]
            total = sum(fm.horizontalAdvance(t) for t, _ in parts)
        x = WIN_W / 2 - total / 2
        for text, col in parts:
            p.setPen(C(col))
            p.drawText(QPointF(x, top + 20), text)
            x += fm.horizontalAdvance(text)

        small = QFont(self.ui, 7)
        p.setFont(small)
        p.setPen(C(info_col))
        pad = 26 if fest else 0
        info = QFontMetricsF(small).elidedText(info, Qt.ElideRight, WIN_W - 56 - pad * 2)
        p.drawText(QRectF(20, top + 25, WIN_W - 40, 14), Qt.AlignCenter, info)
        if fest:
            self.paint_festival_icon(p, festivals.FESTIVALS[fest][2], 38, top + 22)

    def status_festival(self):
        """狀態列要顯示哪個節日的小圖示：只有正在製作節日限定飲品時才顯示（節日 key 或 None）"""
        return DRINKS[self.session.drink].get("festival") if self.session else None

    def paint_festival_icon(self, p, icon, x, y):
        """狀態列左側的節日小圖示"""
        p.save()
        p.translate(x, y)
        p.setPen(Qt.NoPen)
        if icon == "pumpkin":
            p.setBrush(C("#e07a20"))
            for dx in (-4, 0, 4):
                p.drawEllipse(QPointF(dx, 0), 5, 6)
            p.setBrush(C("#3a2a10"))
            p.drawPolygon(QPolygonF([QPointF(-4, -2), QPointF(-2, -2), QPointF(-3, -4)]))
            p.drawPolygon(QPolygonF([QPointF(2, -2), QPointF(4, -2), QPointF(3, -4)]))
            p.drawRect(QRectF(-3, 2, 6, 1.4))
            p.setBrush(C("#4a7a2a"))
            p.drawRect(QRectF(-1, -9, 2, 3.5))
        elif icon == "tree":
            p.setBrush(C("#2f8a4a"))
            for i, w in enumerate((9, 7, 5)):
                yy = 6 - i * 5
                p.drawPolygon(QPolygonF([QPointF(-w, yy), QPointF(w, yy), QPointF(0, yy - 7)]))
            p.setBrush(C("#ffd24a"))
            p.drawEllipse(QPointF(0, -10), 1.8, 1.8)
            p.setBrush(C("#e04040"))
            p.drawEllipse(QPointF(-3, 2), 1.2, 1.2)
            p.drawEllipse(QPointF(3, -3), 1.2, 1.2)
        elif icon == "heart":
            path = QPainterPath()
            path.moveTo(0, 6)
            path.cubicTo(QPointF(-9, 0), QPointF(-5, -8), QPointF(0, -3))
            path.cubicTo(QPointF(5, -8), QPointF(9, 0), QPointF(0, 6))
            p.fillPath(path, C("#e0506a"))
        p.restore()

    def toast_now(self):
        """目前顯示中的成就通知：(文字, 不透明度)；沒有時是 (None, 0)"""
        now = time.perf_counter()
        self.toasts = [t for t in self.toasts if t[2] > now]
        if not self.toasts or now < self.toasts[0][1]:
            return None, 0.0
        text, start, end = self.toasts[0]
        return text, clamp(min((now - start) / 0.3, (end - now) / 0.5), 0, 1)

    def paint_toasts(self, p):
        """成就解鎖通知：暫時取代狀態列（同一個位置，交叉淡入淡出），不會蓋到咖啡機"""
        text, a = self.toast_now()
        if text is not None and a > 0:
            f = QFont(self.ui, 9.5)
            f.setBold(True)
            fm = QFontMetricsF(f)
            W = self._scene_w
            r = QRectF(20, TOP_PAD + WIN_H - 50, W - 40, 44)
            text = fm.elidedText(text, Qt.ElideRight, r.width() - 60)
            tw = fm.horizontalAdvance(text)
            p.save()
            p.setOpacity(a)
            p.setPen(QPen(C("#ffd27a", 160), 1))
            p.setBrush(C("#2a1f12", 240))
            p.drawRoundedRect(r, 14, 14)
            # 小獎盃（和文字一起置中）
            cx, cy = W / 2 - (tw + 22) / 2 + 6, r.center().y()
            p.setPen(Qt.NoPen)
            p.setBrush(C("#ffc24a"))
            cup = QPainterPath()
            cup.moveTo(cx - 6, cy - 6)
            cup.lineTo(cx + 6, cy - 6)
            cup.quadTo(QPointF(cx + 6, cy + 2), QPointF(cx, cy + 3))
            cup.quadTo(QPointF(cx - 6, cy + 2), QPointF(cx - 6, cy - 6))
            p.drawPath(cup)
            p.drawRect(QRectF(cx - 1, cy + 3, 2, 3))
            p.drawRect(QRectF(cx - 4, cy + 6, 8, 1.6))
            p.setFont(f)
            p.setPen(C("#ffe2a0"))
            p.drawText(QRectF(cx + 16, r.top(), tw + 4, r.height()), Qt.AlignLeft | Qt.AlignVCenter, text)
            p.restore()

    # ───────────── 萃取曲線卡片（視窗座標） ─────────────
    def chart_rect(self):
        """咖啡機正上方的透明區（視窗座標）；拉花卡片也出現時兩張並排"""
        cx = self.machine.card_cx
        lo = self.cards_left()
        if self.art_alpha > 0.05 and self.art_state() is not None:
            left = clamp(cx - 169, lo, self._scene_w - 4 - 344)
            return QRectF(left, TOP_PAD - 132, 208, 120)
        return QRectF(clamp(cx - 104, lo, self._scene_w - 4 - 208), TOP_PAD - 132, 208, 120)

    def fit_text(self, p, rect, text, font, flags=Qt.AlignLeft | Qt.AlignVCenter, min_pt=5.5):
        """文字太長時先縮小字級，還是放不下就加刪節號（英文介面的長品名用）"""
        f = QFont(font)
        size = f.pointSizeF()
        while QFontMetricsF(f).horizontalAdvance(text) > rect.width() and size > min_pt:
            size -= 0.5
            f.setPointSizeF(size)
        p.setFont(f)
        p.drawText(rect, flags, QFontMetricsF(f).elidedText(text, Qt.ElideRight, rect.width()))

    # ───────────── 訂單卡（視窗座標，上方透明區左側） ─────────────
    ORDER_W = 98

    def cards_left(self):
        """訂單卡出現時，曲線卡片與拉花卡片往右讓位"""
        return 4 + self.ORDER_W + 4 if (self.order_mode and self.order_alpha > 0.05) else 4

    def paint_order_card(self, p):
        o = self.order
        a = self.order_alpha
        if o is None or a <= 0.01:
            return
        w, h = self.ORDER_W, 120
        slide = (1 - a) * -24                    # 從上方滑進來
        p.save()
        p.setOpacity(a)
        p.translate(4 + w / 2, TOP_PAD - 132 + h / 2 + slide)
        p.rotate(-2.2)
        r = QRectF(-w / 2, -h / 2, w, h)
        p.setPen(Qt.NoPen)
        queued = min(3, len(self.queue)) if self.business() else 0
        for i in range(queued, 0, -1):           # 營業模式：排隊的訂單疊在後面，下緣露出一點
            p.save()
            p.translate(0, 3.5 * i)
            p.rotate((1.6 if i % 2 else -1.2) * i)
            p.setBrush(C("#000000", 50))
            p.drawRoundedRect(r.translated(1.5, 2), 4, 4)
            p.setBrush(C("#e9e0cc"))
            p.drawRoundedRect(r, 4, 4)
            p.restore()
        p.setBrush(C("#000000", 70))
        p.drawRoundedRect(r.translated(2, 3), 4, 4)
        paper = QPainterPath()
        paper.addRoundedRect(r, 4, 4)
        p.fillPath(paper, C("#f7f1e3"))
        # 撕線（點單紙下緣鋸齒）
        p.setPen(QPen(C("#c9bfa9"), 0.8, Qt.DashLine))
        p.drawLine(QPointF(r.left() + 6, r.top() + 20), QPointF(r.right() - 6, r.top() + 20))
        # 夾子
        p.fillPath(rrect(-14, r.top() - 5, 14, r.top() + 5, 2), C("#8a6a48"))
        p.fillRect(QRectF(-12, r.top() - 4, 24, 1.5), C("#ffffff", 70))
        x0, iw = r.left() + 8, w - 16
        small = QFont(self.ui, 6.5)
        p.setFont(small)
        p.setPen(C("#8a7a66"))
        p.drawText(QRectF(x0, r.top() + 6, iw, 12), Qt.AlignLeft | Qt.AlignVCenter, f"#{o.no:03d}")
        self.fit_text(p, QRectF(x0 + 26, r.top() + 6, iw - 26, 12), T(o.name), small, Qt.AlignRight | Qt.AlignVCenter)
        big = QFont(self.ui, 9)
        big.setBold(True)
        p.setFont(big)
        p.setPen(C("#2a1d12"))
        self.fit_text(p, QRectF(x0, r.top() + 23, iw, 16), o.title, big)
        p.setFont(QFont(self.ui, 7))
        p.setPen(C("#5a4632"))
        y = r.top() + 41
        for line in o.mod_lines[:2]:
            self.fit_text(p, QRectF(x0, y, iw, 12), f"· {line}", QFont(self.ui, 7))
            y += 12
        if not o.mod_lines:
            p.setPen(C("#9a8a76"))
            p.drawText(QRectF(x0, y, iw, 12), Qt.AlignLeft | Qt.AlignVCenter, T("· 照一般做法"))
        foot = QRectF(x0, r.bottom() - 40, iw, 34)
        p.setFont(QFont(self.ui, 7))
        if self.business() and o.state in ("waiting", "making"):
            p.setPen(C("#5a4632"))
            p.drawText(foot.adjusted(0, 0, -5 if queued else 0, 0), Qt.AlignRight | Qt.AlignBottom, f"${o.price}")
        if o.state == "waiting" and o.patience > 0:
            # 耐心條：剩下的耐心，越少越紅
            left = clamp(1 - o.wait / o.patience, 0, 1)
            p.fillRect(QRectF(x0, r.bottom() - 4, iw, 1.6), C("#e0d6c2"))
            col = C("#6a9a4a") if left > 0.5 else (C("#c08a2a") if left > 0.25 else C("#c0392b"))
            p.fillRect(QRectF(x0, r.bottom() - 4, iw * left, 1.6), col)
        if queued:
            # 排隊人數徽章：貼在疊起來的訂單右下角
            c = QPointF(r.right() - 1, r.bottom() + 1)
            p.setBrush(C("#b06a2a"))
            p.setPen(QPen(C("#f7f1e3"), 1))
            p.drawEllipse(c, 7, 7)
            bf = QFont(self.ui, 6)
            bf.setBold(True)
            p.setFont(bf)
            p.setPen(C("#ffffff"))
            p.drawText(QRectF(c.x() - 7, c.y() - 7, 14, 14), Qt.AlignCenter, f"+{len(self.queue)}")
            p.setFont(QFont(self.ui, 7))
        if o.state == "waiting":
            dots = "." * (1 + int(self.anim_t * 2) % 3)
            p.setPen(C("#9a8a76"))
            p.drawText(foot, Qt.AlignLeft | Qt.AlignBottom, T("等待製作{dots}", dots=dots))
        elif o.state == "making":
            p.setPen(C("#b06a2a"))
            p.drawText(foot, Qt.AlignLeft | Qt.AlignBottom, T("製作中…"))
        else:
            # 分數印章與顧客的話
            k = clamp(o.t / 0.35, 0, 1) if o.state == "done" else 1.0
            stamp_c = "#c0392b" if o.score >= 84 else ("#c07a2b" if o.score >= 66 else "#7a6a5a")
            p.save()
            p.translate(r.right() - 21, r.top() + 76)
            p.rotate(12)
            p.scale(1.6 - 0.6 * k, 1.6 - 0.6 * k)
            p.setOpacity(a * k)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(C(stamp_c, 220), 1.6))
            p.drawEllipse(QPointF(0, 0), 15, 15)
            p.setPen(QPen(C(stamp_c, 160), 0.7))
            p.drawEllipse(QPointF(0, 0), 12.5, 12.5)
            sf = QFont(self.ui, 9)
            sf.setBold(True)
            p.setFont(sf)
            p.setPen(C(stamp_c, 230))
            p.drawText(QRectF(-15, -9, 30, 14), Qt.AlignCenter, f"{o.score:.0f}")
            p.setFont(QFont(self.ui, 4.5))
            p.drawText(QRectF(-15, 4, 30, 7), Qt.AlignCenter, T("分"))
            p.restore()
            p.setFont(QFont(self.ui, 6.5))
            p.setPen(C("#3a2a1a"))
            p.drawText(foot, Qt.AlignLeft | Qt.AlignBottom | Qt.TextWordWrap, f"「{o.reaction}」")
        p.restore()

    def paint_chart(self, p):
        a = self.card_alpha
        if a <= 0.01:
            return
        p.save()
        p.setOpacity(a)
        r = self.chart_rect()
        p.setBrush(QBrush(C("#14110f", 225)))
        p.setPen(QPen(C("#ffffff", 40), 1))
        p.drawRoundedRect(r, 10, 10)
        tip = QPainterPath()                       # 指向下方咖啡機的小箭頭
        cx = r.center().x()
        tip.moveTo(cx - 8, r.bottom() - 0.5)
        tip.lineTo(cx, r.bottom() + 8)
        tip.lineTo(cx + 8, r.bottom() - 0.5)
        tip.closeSubpath()
        p.fillPath(tip, C("#14110f", 225))
        s = self.shot
        title = QFont(self.ui, 8)
        title.setBold(True)
        small = QFont(self.ui, 6.5)
        p.setFont(title)
        p.setPen(C("#efe6da"))
        if not s or not s.log:
            p.drawText(r, Qt.AlignCenter, T("還沒有萃取紀錄"))
            p.restore()
            return
        p.drawText(QRectF(r.x() + 10, r.y() + 6, r.width() - 20, 14), Qt.AlignLeft | Qt.AlignVCenter, T("萃取曲線"))
        right = T("萃取中…") if s.phase != "done" else T("{score:.0f} 分", score=s.res.score)
        p.drawText(QRectF(r.x() + 10, r.y() + 6, r.width() - 20, 14), Qt.AlignRight | Qt.AlignVCenter, right)

        plot = QRectF(r.x() + 12, r.y() + 26, r.width() - 24, 62)
        p.setPen(QPen(C("#ffffff", 22), 0.6))
        for i in range(5):
            y = plot.top() + plot.height() * i / 4
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        t_max = max(30.0, s.log[-1][0] + 1)
        y_max = s.p.yield_g * 1.1

        def path_of(idx, vmax, fill=False):
            path = QPainterPath()
            for j, row in enumerate(s.log):
                x = plot.left() + plot.width() * row[0] / t_max
                y = plot.bottom() - plot.height() * clamp(row[idx] / vmax, 0, 1.05)
                (path.lineTo if j else path.moveTo)(QPointF(x, y))
            if fill:
                path.lineTo(QPointF(plot.left() + plot.width() * s.log[-1][0] / t_max, plot.bottom()))
                path.lineTo(QPointF(plot.left(), plot.bottom()))
                path.closeSubpath()
            return path

        p.setPen(Qt.NoPen)
        p.setBrush(C("#d6a96c", 40))
        p.drawPath(path_of(3, y_max, fill=True))
        p.setBrush(Qt.NoBrush)
        for idx, vmax, col in ((3, y_max, "#d6a96c"), (2, 4.0, "#5fc4d6"), (1, 12.0, "#e8664f")):
            p.setPen(QPen(C(col), 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(path_of(idx, vmax))

        p.setFont(small)
        lx = plot.left()
        for label, col in ((T("壓力 bar"), "#e8664f"), (T("流速 g/s"), "#5fc4d6"), (T("重量 g"), "#d6a96c")):
            p.setPen(Qt.NoPen)
            p.setBrush(C(col))
            p.drawRoundedRect(QRectF(lx, plot.bottom() + 7, 8, 3), 1.5, 1.5)
            p.setPen(C("#bfb3a5"))
            w = QFontMetricsF(small).horizontalAdvance(label)
            p.drawText(QPointF(lx + 11, plot.bottom() + 11), label)
            lx += w + 22
        last = s.log[-1]
        p.setPen(C("#efe6da"))
        p.drawText(QRectF(r.x() + 10, r.bottom() - 18, r.width() - 20, 14), Qt.AlignCenter,
                   f"EY {s.res.ey:.1f}%  ·  TDS {s.res.tds:.1f}%  ·  {last[0]:.1f} s  ·  {last[3]:.1f} g")
        p.restore()
