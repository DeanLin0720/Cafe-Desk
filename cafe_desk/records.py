"""紀錄與收集冊視窗：今天、近兩週、成就、拉花收集、飲品圖鑑"""
import datetime
import html

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPixmap, QPen, QFont, QColor, QPainterPath
from PySide6.QtWidgets import (QDialog, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QGridLayout,
                               QScrollArea, QPushButton, QFrame, QProgressBar, QComboBox)

from .drinks import DRINKS, DRINK_KEYS, FESTIVAL_DRINKS, ART_NAMES, MILK_KINDS
from .beans import ORIGINS
from .festivals import today, FESTIVALS
from . import growth, theme, store, beans, brew, orders
from .i18n import T, money, money_text, retext
from .machines import MACHINES
from .stats import ACHIEVEMENTS, ART_BOOK, TIER_GROUPS, TIER_OF, ACH_SECTIONS
from .render.milk import make_art
from .render.icons import drink_icon, milk_icon, bean_icon, upgrade_icon
from .render import gear_icons
from .drinks import method_of
from .drink_notes import DRINK_NOTES

ACCENT = "#8a5426"


def _title(text):
    lab = QLabel(text)
    lab.setStyleSheet("font-weight:bold; font-size:13px; padding-top:6px;")
    return lab


def _muted(text):
    lab = QLabel(text)
    lab.setStyleSheet("color:#7a6a5a;")
    lab.setWordWrap(True)
    return lab


MEDAL_COLORS = ("#c07a3e", "#aab2ba", "#e0b030")       # 銅、銀、金


def _medals(have, dpr=1.0):
    """分級成就的獎牌（三級：銅銀金；兩級：銀金）：解鎖的上色，沒解鎖的是灰色空圈"""
    w, h, r = 46, 18, 6.5
    pm = QPixmap(int(w * dpr), int(h * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    off = 3 - len(have)
    for i, ok in enumerate(have):
        c = QPointF(8 + (i + off) * 15, h / 2)
        if ok:
            p.setPen(QPen(QColor(MEDAL_COLORS[i + off]).darker(140), 1))
            p.setBrush(QColor(MEDAL_COLORS[i + off]))
            p.drawEllipse(c, r, r)
            p.setPen(QPen(QColor(255, 255, 255, 150), 1))
            p.drawArc(QRectF(c.x() - r + 2.5, c.y() - r + 2.5, 2 * r - 5, 2 * r - 5), 40 * 16, 100 * 16)
        else:
            p.setPen(QPen(QColor("#c8beb2"), 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, r - 0.5, r - 0.5)
    p.end()
    return pm


def _dash(kind="dash"):
    """收據的虛線（dash）或行與行之間的點線（dot），樣式在 theme.DIALOG_QSS"""
    f = QFrame()
    f.setObjectName(kind)
    f.setFixedHeight(1)
    return f


def _bar(prog):
    bar = QProgressBar()
    bar.setRange(0, 1000)
    bar.setValue(int(prog * 1000))
    bar.setTextVisible(False)
    bar.setFixedHeight(8)
    bar.setStyleSheet(f"QProgressBar{{background:#e8dfd2;border:none;border-radius:4px;}}"
                      f"QProgressBar::chunk{{background:{theme.ACCENT};border-radius:4px;}}")
    return bar


class Receipt(QWidget):
    """一張收據：白一點的紙、右下影子、下緣鋸齒（成就頁用）"""

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -5, -5)
        path = QPainterPath()
        path.moveTo(r.left(), r.top())
        path.lineTo(r.right(), r.top())
        path.lineTo(r.right(), r.bottom())
        teeth = max(8, int(r.width() // 14))
        step = r.width() / teeth
        for i in range(teeth):
            x = r.right() - i * step
            path.lineTo(x - step / 2, r.bottom() - 5)
            path.lineTo(x - step, r.bottom())
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(90, 70, 40, 40))
        p.drawPath(path.translated(3, 3))
        p.setBrush(QColor("#fffdf7"))
        p.setPen(QPen(QColor("#e4dac6"), 1))
        p.drawPath(path)
        p.end()


class DaysChart(QWidget):
    """近 14 天：每天杯數（長條）與平均分數（點）"""

    def __init__(self, days):
        super().__init__()
        self.days = days
        self.setMinimumSize(460, 200)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        left, right, top, bottom = 34, 34, 14, 34
        pw, ph = w - left - right, h - top - bottom
        cups = [d.get("cups", 0) for _, d in self.days]
        cmax = max(5, max(cups) if cups else 0)
        p.setPen(QPen(QColor("#d8cfc4"), 1))
        for i in range(5):
            y = top + ph * i / 4
            p.drawLine(QPointF(left, y), QPointF(left + pw, y))
        p.setPen(QColor("#7a6a5a"))
        f = QFont(self.font())
        f.setPointSizeF(7.5)
        p.setFont(f)
        p.drawText(QRectF(0, top - 6, left - 4, 12), Qt.AlignRight | Qt.AlignVCenter, str(cmax))
        p.drawText(QRectF(0, top + ph - 6, left - 4, 12), Qt.AlignRight | Qt.AlignVCenter, "0")
        p.drawText(QRectF(left + pw + 4, top - 6, right, 12), Qt.AlignLeft | Qt.AlignVCenter, "100")
        p.drawText(QRectF(left + pw + 4, top + ph - 6, right, 12), Qt.AlignLeft | Qt.AlignVCenter, "50")
        n = len(self.days)
        slot = pw / max(1, n)
        prev = None
        for i, (date, d) in enumerate(self.days):
            x = left + slot * i + slot / 2
            c = d.get("cups", 0)
            bh = ph * c / cmax
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#c9a27a" if date != today().isoformat() else ACCENT))
            p.drawRoundedRect(QRectF(x - slot * 0.32, top + ph - bh, slot * 0.64, bh), 2, 2)
            p.setPen(QColor("#7a6a5a"))
            md = datetime.date.fromisoformat(date)
            p.drawText(QRectF(x - slot / 2, top + ph + 4, slot, 12), Qt.AlignCenter, f"{md.month}/{md.day}")
            if c:
                avg = d["score_sum"] / c
                y = top + ph - ph * max(0.0, avg - 50) / 50
                if prev:
                    p.setPen(QPen(QColor("#4a7ab0"), 1.4))
                    p.drawLine(prev, QPointF(x, y))
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#4a7ab0"))
                p.drawEllipse(QPointF(x, y), 2.6, 2.6)
                prev = QPointF(x, y)
        p.setPen(QColor("#7a6a5a"))
        p.drawText(QRectF(left, h - 14, pw, 12), Qt.AlignCenter, T("長條：杯數　藍點：平均分數"))
        p.end()


class RecordsDialog(QDialog):
    def __init__(self, app, tab=None):
        super().__init__(None)
        self.app = app
        self.setWindowTitle(T("紀錄與收集冊"))
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.resize(760, 560)                       # 英文分頁名稱較長（店鋪、商店、說明分頁）
        theme.apply_dialog(self)
        lay = QVBoxLayout(self)
        if app.stats.tampered:
            warn = QLabel(T("⚠ 偵測到 {n} 筆紀錄被修改或刪除，這些紀錄不列入統計", n=app.stats.tampered))
            warn.setStyleSheet("color:#b03020; font-weight:bold; padding:4px;")
            warn.setWordWrap(True)
            lay.addWidget(warn)
        tabs = self.tabs = QTabWidget()
        lay.addWidget(tabs)
        st = app.stats.data
        tabs.addTab(self.today_tab(), T("今天"))
        tabs.addTab(self.scroll(self.shop_tab()), T("店鋪"))
        tabs.addTab(self.scroll(self.store_tab()), T("商店"))
        tabs.addTab(self.history_tab(), T("近期紀錄"))
        n = len(st["achievements"])
        tabs.addTab(self.scroll(self.achievements_tab()), T("成就 {n}/{total}", n=n, total=len(ACHIEVEMENTS)))
        tabs.addTab(self.scroll(self.book_tab()), T("圖鑑"))
        tabs.addTab(self.scroll(self.guide_tab()), T("說明"))
        if tab == "shop":
            tabs.setCurrentIndex(2)
        row = QHBoxLayout()
        row.addStretch(1)
        b = QPushButton(T("關閉"))
        b.clicked.connect(self.close)
        row.addWidget(b)
        lay.addLayout(row)

    @staticmethod
    def scroll(w):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        w.setObjectName("page")                      # 紙張底色（theme.DIALOG_QSS）
        sa.setWidget(w)
        return sa

    def today_tab(self):
        w = QWidget()
        g = QGridLayout(w)
        d = self.app.stats.day()
        cups = d["cups"]
        g.addWidget(_title(T("今天 {date}", date=today().isoformat())), 0, 0, 1, 2)
        rows = [(T("杯數"), f"{cups}"),
                (T("平均分數"), f"{d['score_sum'] / cups:.1f}" if cups else "—"),
                (T("點單"), f"{d['orders']}"),
                (T("營業額"), money(d["revenue"])),
                (T("比上一個營業日"), self.revenue_change(d)),
                (T("等太久離開的客人"), f"{d['walkouts']}"),
                (T("平均等待"), T("{s:.0f} 秒", s=d["wait_sum"] / d["waited"]) if d["waited"] else "—"),
                (T("用掉的豆子"), f"{d['beans_g']:.0f} g")]
        for i, (k, v) in enumerate(rows, start=1):
            g.addWidget(QLabel(k), i, 0)
            lab = QLabel(v)
            lab.setStyleSheet(f"font-weight:bold; color:{ACCENT};")
            g.addWidget(lab, i, 1)
        r = len(rows) + 1
        best = d.get("best")
        g.addWidget(_title(T("今天最好的一杯")), r, 0, 1, 2)
        if best:
            name = retext(best.get("title")) if best.get("title") not in DRINKS else T(DRINKS[best["drink"]]["name"])
            g.addWidget(QLabel(T("{name} · {score:.0f} 分", name=name, score=best["score"])), r + 1, 0, 1, 2)
            g.addWidget(_muted(retext(best.get("comment", ""))), r + 2, 0, 1, 2)
        else:
            g.addWidget(_muted(T("今天還沒有做咖啡")), r + 1, 0, 1, 2)
        r += 3
        g.addWidget(_title(T("今天做了什麼")), r, 0, 1, 2)
        r += 1
        for k, n in sorted(d["drinks"].items(), key=lambda kv: -kv[1]):
            if k in DRINKS:
                g.addWidget(QLabel(T(DRINKS[k]["name"])), r, 0)
                g.addWidget(QLabel(T("{n} 杯", n=n)), r, 1)
                r += 1
        g.setRowStretch(r, 1)
        g.setColumnStretch(1, 1)
        return w

    def revenue_change(self, d):
        """今日營業額跟上一個有接單的日子比"""
        prev = growth.last_business_day(self.app.stats, today().isoformat())
        pv = self.app.stats.data["days"][prev]["revenue"] if prev else 0
        if not d["orders"] or not pv:
            return "—"
        k = (d["revenue"] - pv) / pv
        return T("{arrow} {pct:.0f}%（{day}：{rev}）", arrow="↑" if k >= 0 else "↓", pct=abs(k) * 100, day=prev, rev=money(pv))

    def shop_tab(self):
        """店鋪等級（累積營業額）與咖啡師熟練度（總杯數）"""
        w = QWidget()
        g = QGridLayout(w)
        st = self.app.stats.data
        rev, cups = st["revenue_total"], st["total"]
        lv, nxt, prog = growth.level_progress(rev)
        g.addWidget(_title(T("店鋪 Lv.{n} {name}", n=lv, name=T(growth.level_name(lv)))), 0, 0, 1, 2)
        g.addWidget(_bar(prog), 1, 0, 1, 2)
        rows = [(T("累積營業額"), money(rev)),
                (T("下一級"), T("Lv.{n}：還差 {m}", n=lv + 1, m=money(nxt - rev)) if nxt else T("已經是最高等級")),
                (T("來客"), T("比開店時多 {p:.0f}%", p=(1 / growth.arrival_k(lv) - 1) * 100)),
                (T("客人耐心"), T("多 {p:.0f}%", p=(growth.patience_k(lv) - 1) * 100)),
                (T("排隊上限"), T("{n} 位", n=growth.queue_max(lv))),
                (T("內用座位"), T("{n} 位（下一級 {m} 位）", n=growth.seats(lv), m=growth.seats(lv + 1))
                 if growth.seats(lv + 1) > growth.seats(lv) and lv < growth.MAX_LEVEL else T("{n} 位", n=growth.seats(lv)))]
        r = 2
        for k, v in rows:
            g.addWidget(QLabel(k), r, 0)
            lab = QLabel(v)
            lab.setStyleSheet(f"font-weight:bold; color:{ACCENT};")
            g.addWidget(lab, r, 1)
            r += 1
        g.addWidget(_muted(T("店鋪等級依營業模式的累積營業額（含小費）計算，等級越高客人越多、越有耐心。")), r, 0, 1, 2)
        r += 1
        g.addWidget(QLabel(T("營業用咖啡機")), r, 0)                       # 做飲品和櫃檯後檯都用這台（只列解鎖的）
        box = QComboBox()
        box.addItem(T("隨機使用"), "auto")
        for k, m in MACHINES.items():
            if self.app.machine_open(k):
                box.addItem(T(m.name), k)
        i = box.findData(self.app.showcase)
        box.setCurrentIndex(max(0, i))
        box.currentIndexChanged.connect(lambda _i, b=box: self.app.set_showcase(b.currentData()))
        g.addWidget(box, r, 1)
        r += 1
        rank = growth.rank_of(cups)
        g.addWidget(_title(T("咖啡師：{name}", name=T(growth.rank_name(rank)))), r, 0, 1, 2)
        left = growth.rank_next(cups)
        rows = [(T("做過的咖啡"), T("{n} 杯", n=cups)),
                (T("下一個稱號"), T("{name}：還差 {n} 杯", name=T(growth.rank_name(rank + 1)), n=left)
                 if left is not None else T("已經是最高稱號")),
                (T("手感誤差"), T("新手的 {p:.0f}%", p=growth.skill(cups) * 100)),
                (T("萃取同時打奶"), T("已解鎖（單鍋爐機除外）") if rank >= growth.TOGETHER_RANK
                 else T("「{name}」解鎖", name=T(growth.rank_name(growth.TOGETHER_RANK))))]
        r += 1
        for k, v in rows:
            g.addWidget(QLabel(k), r, 0)
            lab = QLabel(v)
            lab.setStyleSheet(f"font-weight:bold; color:{ACCENT};")
            g.addWidget(lab, r, 1)
            r += 1
        g.addWidget(_muted(T("每做一杯都算（手動、自動、營業）。越熟練，打奶溫度、奶泡量、研磨與拉花的誤差越小。")), r, 0, 1, 2)
        r += 1
        days = [(k, v) for k, v in sorted(st["days"].items(), reverse=True) if v.get("orders")][:7]
        if days:
            g.addWidget(_title(T("最近的營業日")), r, 0, 1, 2)
            r += 1
            for k, v in days:
                g.addWidget(QLabel(k), r, 0)
                g.addWidget(QLabel(T("服務 {n} 位 · {rev} · 小費 {tip}", n=v["orders"], rev=money(v["revenue"]),
                                     tip=money(v["tips"]))), r, 1)
                r += 1
        g.setRowStretch(r, 1)
        g.setColumnStretch(1, 1)
        return w

    # 設備圖鑑：(種類, key, 名稱, 說明)；種類 machine／grinder（義式獨立磨豆機）／station（沖煮台，key 是沖煮方式或 grinder）
    GEAR_TEXT = {"grinder": "DESK·01、復古拉桿、小型單鍋爐共用", "station_grinder": "手沖、冰滴、摩卡壺、虹吸壺共用",
                 "pourover": "濾杯加細口壺，悶蒸後分段注水", "colddrip": "冰水一滴一滴滴過咖啡粉，約一小時",
                 "moka": "爐火加熱下壺，蒸氣壓把咖啡推上來", "siphon": "酒精燈把水推上上壺，熄火後咖啡被吸回"}
    STATION_DRINK = {"pourover": "pour_over", "colddrip": "cold_drip", "moka": "moka_pot", "siphon": "siphon"}

    def gear_cards(self, g, r):
        """圖鑑的設備區：每台咖啡機、磨豆機、沖煮台一張卡片（縮圖、名稱、解鎖條件或使用紀錄、說明、已買的升級）"""
        app = self.app
        col = app.stats.data["collection"]
        owned = app.stats.data["owned"]
        dpr = self.devicePixelRatioF()
        items = []
        for k, m in MACHINES.items():
            ok = app.machine_open(k)
            best = col["machine_best"].get(k)
            sub = (T("最高 {s:.0f} 分", s=best) if best else T("還沒用過")) if ok else \
                T("店鋪 Lv.{n} 解鎖", n=growth.MACHINE_LEVEL[k])
            pic = gear_icons.machine_icon(app, m, 150, 104, not ok, dpr)
            items.append((pic, T(m.name), sub, T(m.traits.summary), store.upgrade_names(k, owned), ok))
        ok = app.machine_open("desk01")
        items.append((gear_icons.grinder_icon(app, 150, 104, not ok, dpr), T("獨立磨豆機"), T("Lv.1 就有"),
                      T(self.GEAR_TEXT["grinder"]), [n for k, (t, n, *_r) in store.UPGRADES.items()
                                                      if t == store.EXTERNAL and k in owned], ok))
        for kind in ("grinder", "pourover", "colddrip", "moka", "siphon"):
            method = "pourover" if kind == "grinder" else kind
            ok = app.method_open(method)
            if kind == "grinder":
                name, text = T("手沖用磨豆機"), T(self.GEAR_TEXT["station_grinder"])
                ups = [n for k, (t, n, *_r) in store.UPGRADES.items() if t == store.STATION and k in owned]
                sub = T("跟著手沖解鎖") if ok else T("店鋪 Lv.{n} 解鎖", n=growth.METHOD_LEVEL[method])
            else:
                name, text, ups = T(brew.METHODS[kind]), T(self.GEAR_TEXT[kind]), []
                info = col["drinks"].get(self.STATION_DRINK[kind])
                if not ok:
                    sub = T("店鋪 Lv.{n} 解鎖", n=growth.METHOD_LEVEL[method])
                elif info:
                    sub = T("{n} 杯 · 最高 {s:.0f} 分", n=info["count"], s=info["best"])
                else:
                    sub = T("還沒用過")
            items.append((gear_icons.station_icon(app, kind, 150, 104, not ok, dpr), name, sub, text, ups, ok))
        g.addWidget(_title(T("設備（{n}/{total}）", n=sum(1 for it in items if it[5]), total=len(items))), r, 0, 1, 4)
        r += 1
        cols = 3
        box = QGridLayout()
        box.setHorizontalSpacing(14)
        box.setVerticalSpacing(10)
        for i, (pm, name, sub, text, ups, ok) in enumerate(items):
            card = QVBoxLayout()
            card.setSpacing(1)
            pic = QLabel()
            pic.setPixmap(pm)
            pic.setAlignment(Qt.AlignCenter)
            card.addWidget(pic)
            lab = QLabel(name)
            lab.setAlignment(Qt.AlignCenter)
            lab.setWordWrap(True)
            lab.setStyleSheet("font-weight:bold;" if ok else f"color:{theme.FAINT};")
            card.addWidget(lab)
            note = QLabel(sub)
            note.setAlignment(Qt.AlignCenter)
            note.setStyleSheet(f"color:{ACCENT if ok else theme.FAINT}; font-size:11px;")
            card.addWidget(note)
            desc = QLabel(text + ("<br>★ " + T("、").join(T(u) for u in ups) if ups else ""))
            desc.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color:{theme.MUTED if ok else theme.FAINT}; font-size:11px;")
            card.addWidget(desc)
            card.addStretch(1)
            box.addLayout(card, i // cols, i % cols)
        for c in range(cols):
            box.setColumnStretch(c, 1)
        g.addLayout(box, r, 0, 1, 4)
        return r + 1

    def guide_tab(self):
        """遊戲說明：操作、三種模式的差別、營業怎麼玩、成長、商店、成就、小技巧（數字從遊戲資料算，改數值不用改這裡）"""
        outer = QWidget()
        ol = QVBoxLayout(outer)
        ol.setContentsMargins(14, 12, 14, 12)
        paper = Receipt()
        ol.addWidget(paper)
        ol.addStretch(1)
        lay = QVBoxLayout(paper)
        lay.setContentsMargins(28, 20, 28, 32)
        lay.setSpacing(5)
        head = QLabel(T("遊戲說明"))
        head.setAlignment(Qt.AlignCenter)
        head.setStyleSheet(f"font-size:17px; font-weight:bold; color:{theme.INK_DARK};")
        lay.addWidget(head)
        sub = QLabel("Café Desk")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"color:{theme.MUTED};")
        lay.addWidget(sub)

        def section(title):
            lay.addWidget(_dash())
            lab = QLabel(title)
            lab.setStyleSheet(f"font-weight:bold; color:{ACCENT}; font-size:13px; padding-top:2px;")
            lay.addWidget(lab)

        def bullet(text):
            lab = QLabel(f"<table><tr><td style='padding-right:6px; color:{theme.MUTED}'>·</td><td>{text}</td></tr></table>")
            lab.setWordWrap(True)
            lay.addWidget(lab)

        section(T("基本操作"))
        bullet(T("點一下咖啡機（或沖煮台）做一杯；左鍵拖曳移動視窗；右鍵打開選單；滑鼠停在機身上看萃取曲線。"))
        bullet(T("右鍵「參數設定…」調研磨、粉量、水溫等參數，下方會預估這組參數拿幾分。"))

        section(T("三種模式（右鍵選單上方三選一）"))
        bullet(T("<b>手動</b>：點一下做一杯。"))
        bullet(T("<b>自動</b>：照目前的飲品與參數一直做同一杯，間隔在「自動間隔」選；適合當擺件。"))
        bullet(T("<b>營業</b>：客人排隊點單，咖啡師自己接單、賺營業額；這是遊戲的主體。"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        cols = (T("手動"), T("自動"), T("營業"))
        for c, name in enumerate(cols):
            lab = QLabel(f"<b>{name}</b>")
            lab.setAlignment(Qt.AlignCenter)
            grid.addWidget(lab, 0, c + 1)
        rows = ((T("咖啡師稱號"), (1, 1, 1)), (T("營業額、錢包"), (0, 0, 1)), (T("店鋪等級、設備解鎖"), (0, 0, 1)),
                (T("成就（跟杯子有關的）"), (0, 0, 1)), (T("客人、耐心、小費"), (0, 0, 1)))
        for r, (name, marks) in enumerate(rows, start=1):
            grid.addWidget(QLabel(name), r, 0)
            for c, ok in enumerate(marks):
                lab = QLabel("✓" if ok else "—")
                lab.setAlignment(Qt.AlignCenter)
                lab.setStyleSheet(f"color:{ACCENT if ok else theme.FAINT}; font-weight:bold;")
                grid.addWidget(lab, r, c + 1)
        grid.setColumnStretch(0, 1)
        lay.addLayout(grid)

        section(T("營業怎麼玩"))
        bullet(T("客人陸續進門排隊，每位都有耐心（點單紙下緣的細條），等太久會離開。"))
        bullet(T("分數＝飲品 65%＋照訂單要求 35%，等太久會扣分；84 分以上給 10% 小費，92 分以上 20%。"))
        bullet(T("離開營業模式或跨過午夜時，會出一張打烊日報。"))

        section(T("店鋪等級：看累積營業額"))
        bullet(T("等級越高，客人越多、越有耐心、出杯越快，排隊上限也變多；最高 Lv.{n}。", n=growth.MAX_LEVEL))
        bullet(T("內用座位 Lv.1 {a} 位、Lv.{n} {b} 位：內用客人拿到飲品後會坐一陣子，坐滿了新客人只能外帶。",
                 a=growth.seats(1), n=growth.MAX_LEVEL, b=growth.seats(growth.MAX_LEVEL)))
        names = {**{k: T(m.name) for k, m in MACHINES.items()}, **{k: T(v) for k, v in brew.METHODS.items()}}
        by_level = {}
        for table in (growth.MACHINE_LEVEL, growth.METHOD_LEVEL):
            for k, lv in table.items():
                by_level.setdefault(lv, []).append(names[k])
        unlock = "<br>".join(T("Lv.{lv}：{names}", lv=lv, names=T("、").join(by_level[lv])) for lv in sorted(by_level))
        bullet(T("設備依店鋪等級解鎖：<br>{list}", list=unlock))

        section(T("咖啡師稱號：看做過的總杯數（三種模式都算）"))
        ranks = " → ".join(T("{name} {n} 杯", name=T(name), n=cups) if cups else T(name)
                           for cups, name, _k in growth.RANKS)
        bullet(ranks)
        lines = []
        for r, (_c, rname, _e) in enumerate(growth.RANKS):
            ks = [k for k in DRINK_KEYS if growth.drink_rank(k) == r and method_of(k) == "espresso"]
            extra = [T("節日限定")] if r == growth.FESTIVAL_RANK else []
            if ks or extra:
                lines.append(T("{rank}：{names}", rank=T(rname), names=T("、").join([T(DRINKS[k]["name"]) for k in ks] + extra)))
        bullet(T("飲品依咖啡師稱號解鎖（沖煮台的飲品看店鋪等級）：<br>{list}", list="<br>".join(lines)))
        bullet(T("升到「{name}」解鎖萃取的同時打奶：熱牛奶飲品快約三成（單鍋爐機要先加熱到蒸氣溫度，不適用；雙頭機本來就會）。",
                 name=T(growth.rank_name(growth.TOGETHER_RANK))))
        pct = "、".join(f"{T(name)} {k * 100:.0f}%" for (_c, name, _e), k in zip(growth.RANKS, growth.SCORE_K))
        bullet(T("越熟練手感越穩、奶泡越細；而且 {base:.0f} 分以上的部分依稱號打折：{pct}。",
                 base=growth.SCORE_FROM, pct=pct))

        section(T("錢包與商店（「商店」分頁）"))
        bullet(T("錢包＝累積營業額 － 已花的錢；花錢不會掉級。"))
        bullet(T("咖啡機與磨豆機升級讓設備更穩、更好喝；精品豆比較甜，營業中用它做的飲品售價 ×{k:g}。", k=beans.PREMIUM_PRICE_K))

        section(T("成就"))
        bullet(T("跟杯子有關的成就只算營業模式裡為客人做的杯子；清潔保養、開豆子、等冰滴照常算。"))
        bullet(T("分級成就有銅、銀、金三級，「成就」分頁會顯示下一級還差多少。"))

        section(T("小技巧"))
        bullet(T("豆子烘焙後 7–21 天最好喝；豆子用完要開新包（自動、營業時咖啡師會自己開）。"))
        bullet(T("狀態列出現 ⚠ 就是該清潔保養了，太久沒清會扣分。"))
        bullet(T("冰滴要先架冰滴塔，之後在背景滴約 1 小時（關掉程式也照算）。"))
        bullet(T("右鍵「聲音」可以開環境音，「音樂」可以播放自己的音檔。"))
        return outer

    def store_tab(self):
        """商店：錢包餘額、咖啡機升級（每台一組）、磨豆機升級（共用的）、精品咖啡豆（一包一包買）"""
        app = self.app
        st = app.stats.data
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(6)
        lay.addWidget(_title(T("商店")))
        bal = app.wallet()
        purse = QLabel(T("錢包 {m}", m=money(bal)))
        purse.setStyleSheet(f"font-size:20px; font-weight:bold; color:{ACCENT};")
        lay.addWidget(purse)
        lay.addWidget(_muted(T("累積營業額 {a} － 已花 {b}。店鋪等級照累積營業額計算，花錢不會掉級。",
                               a=money(st["revenue_total"]), b=money(st["spent"]))))

        dpr = self.devicePixelRatioF()
        COLS = 3

        def card(pix, name, sub, desc, label, enabled, tip, fn, have=False):
            """一張商品卡片：圖示、名稱、小字、說明、按鈕（並排顯示，一列 COLS 張）"""
            box = QFrame()
            box.setObjectName("shopcard")
            box.setStyleSheet(f"#shopcard {{ border:1px solid {theme.FAINT}; border-radius:6px; "
                              f"background:{'#f3ead8' if have else 'transparent'}; }}")
            v = QVBoxLayout(box)
            v.setContentsMargins(8, 8, 8, 8)
            v.setSpacing(3)
            pic = QLabel()
            pic.setPixmap(pix)
            pic.setAlignment(Qt.AlignCenter)
            v.addWidget(pic)
            lab = QLabel(f"<b>{name}</b>" + (f"<br><span style='color:{theme.MUTED}'>{sub}</span>" if sub else ""))
            lab.setAlignment(Qt.AlignCenter)
            lab.setWordWrap(True)
            v.addWidget(lab)
            d = QLabel(desc)
            d.setWordWrap(True)
            d.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            d.setStyleSheet(f"color:{theme.MUTED}; font-size:11px;")
            v.addWidget(d, 1)
            b = QPushButton(label)
            b.setEnabled(enabled)
            if tip:
                b.setToolTip(tip)
                box.setToolTip(tip)
            b.clicked.connect(fn)
            v.addWidget(b)
            return box

        def grid(cards):
            g = QGridLayout()
            g.setSpacing(8)
            for i, c in enumerate(cards):
                g.addWidget(c, i // COLS, i % COLS)
            for c in range(COLS):
                g.setColumnStretch(c, 1)
            lay.addLayout(g)

        def upgrade(key):
            targets, name, desc, price, _c = store.UPGRADES[key]
            have = key in st["owned"]
            short = max(0, price - bal)
            opened = app.upgrade_open(key)
            if not opened:
                tip = T("店鋪 Lv.{n} 解鎖後才能升級", n=need_level(key))
            else:
                tip = T("還差 {m}", m=money(short)) if (not have and short) else ""
            sub = T(store.target_name(key))                          # 卡片上寫是哪台的；還沒解鎖的加上等級
            if not opened:
                sub = T("{name} · 店鋪 Lv.{n} 解鎖", name=sub, n=need_level(key))
            return card(upgrade_icon(store.UPGRADE_ICONS.get(key, "flat"), 64, opened, dpr), T(name), sub, T(desc),
                        T("已購買") if have else money(price), not have and short == 0 and opened, tip,
                        lambda _=False, k=key: self.buy(app.buy_upgrade, k), have)

        def need_level(key):
            targets = store.UPGRADES[key][0]
            return growth.METHOD_LEVEL["pourover"] if targets == store.STATION else \
                min(growth.MACHINE_LEVEL[k] for k in targets)

        def section(title, keys):
            """一段升級：標題寫已買幾項，卡片全部並排（照咖啡機的順序，卡片上寫是哪台的）"""
            lay.addWidget(_dash())
            got = sum(1 for k in keys if k in st["owned"])
            lay.addWidget(_title(T("{title}（已買 {n}/{total}）", title=title, n=got, total=len(keys))))
            grid([upgrade(k) for k in keys])

        section(T("咖啡機升級"), [k for mk in MACHINES for k, v in store.UPGRADES.items() if v[0] == (mk,)])
        section(T("磨豆機升級"), [k for t in (store.EXTERNAL, store.STATION) for k, v in store.UPGRADES.items() if v[0] == t])
        lay.addWidget(_dash())
        lay.addWidget(_title(T("精品咖啡豆")))
        lay.addWidget(_muted(T("一包 {g:.0f} g，取代目前這包：咖啡師沒在忙就馬上開封，正在做飲品就這杯做完換上（營業中也能買）。"
                               "甜感比一般豆高，營業中用這包做的飲品售價 ×{k:g}。", g=beans.BAG_G, k=beans.PREMIUM_PRICE_K)))
        waiting = app.pending_bag if beans.is_premium(app.pending_bag or "") else None
        bean_cards = []
        for key, (name, roast, flavor, sweet, price) in beans.PREMIUM.items():
            short = max(0, price - bal)
            now = app.bag["origin"] == key
            if waiting:
                tip = T("已經有一包精品豆等著換上")
            else:
                tip = T("還差 {m}", m=money(short)) if short else (T("咖啡師正在做飲品：這杯做完換上") if app.busy() else "")
            note = T("（正在用這包，剩 {g:.0f} g）", g=app.bag["left"]) if now else ""
            if waiting == key:
                note = T("（已買，這杯做完換上）")
            bean_cards.append(card(bean_icon(key, roast, True, 64, True, dpr), T(name),
                                   T("{roast} · 甜感 +{s:g}", roast=T(roast), s=sweet), T(flavor) + note,
                                   T("待換上") if waiting == key else T("買一包 {m}", m=money(price)),
                                   short == 0 and not waiting, tip, lambda _=False, k=key: self.buy(app.buy_beans, k),
                                   now or waiting == key))
        grid(bean_cards)
        lay.addStretch(1)
        return w

    def buy(self, fn, key):
        """按下購買：成功後重畫商店分頁（餘額、按鈕狀態會變）"""
        if fn(key):
            i = self.tabs.currentIndex()
            self.tabs.removeTab(i)
            self.tabs.insertTab(i, self.scroll(self.store_tab()), T("商店"))
            self.tabs.setCurrentIndex(i)

    def days_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        days = self.app.stats.data["days"]
        t = today()
        series = []
        for i in range(13, -1, -1):
            key = (t - datetime.timedelta(days=i)).isoformat()
            series.append((key, days.get(key, {})))
        lay.addWidget(_title(T("近兩週")))
        lay.addWidget(DaysChart(series))
        total = sum(d.get("cups", 0) for _, d in series)
        ssum = sum(d.get("score_sum", 0) for _, d in series)
        lay.addWidget(_muted(T("兩週共 {n} 杯，平均 {avg} 分；累計 {all} 杯", n=total,
                               avg=f"{ssum / total:.1f}" if total else "—", all=self.app.stats.data["total"])))
        return w

    def history_tab(self):
        """近期紀錄：上面是近兩週的圖表（固定），下面是最近幾杯（自己捲動）"""
        w = QWidget()
        w.setObjectName("page")                      # 紙張底色（theme.DIALOG_QSS）
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.days_tab())
        lay.addWidget(_dash())
        lay.addWidget(_title(T("最近幾杯")))
        rec = QWidget()
        rl = QVBoxLayout(rec)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.recent_tab())
        rl.addStretch(1)
        lay.addWidget(self.scroll(rec), 1)
        return w

    def recent_tab(self):
        w = QWidget()
        g = QGridLayout(w)
        rows = self.app.stats.recent(30)
        if not rows:
            g.addWidget(_muted(T("還沒有紀錄")), 0, 0)
        for i, c in enumerate(rows):
            ts = (c["ts"] or "")[5:16].replace("T", " ")
            name = retext(c["title"]) if c["title"] and c["title"] not in DRINKS else T(DRINKS.get(c["drink"], {}).get("name", c["drink"]))
            g.addWidget(_muted(ts), i, 0)
            g.addWidget(QLabel(name + ("  " + T("（點單）") if c.get("is_order") else "")), i, 1)
            sc = QLabel(T("{score:.0f} 分", score=float(c["score"] or 0)))
            sc.setStyleSheet(f"font-weight:bold; color:{ACCENT};")
            g.addWidget(sc, i, 2)
            com = _muted(retext(c["comment"] or ""))
            g.addWidget(com, i, 3)
        g.setColumnStretch(3, 1)
        return w

    def achievements_tab(self):
        """成就頁：排成一張收據（依 ACH_SECTIONS 分類，分級成就一組一列，右邊是解鎖日期）"""
        st = self.app.stats
        got = st.data["achievements"]
        info = {k: (n, d) for k, n, d in ACHIEVEMENTS}
        values = st.tier_values()
        outer = QWidget()
        ol = QVBoxLayout(outer)
        ol.setContentsMargins(14, 12, 14, 12)
        paper = Receipt()
        ol.addWidget(paper)
        ol.addStretch(1)
        lay = QVBoxLayout(paper)
        lay.setContentsMargins(26, 20, 26, 30)
        lay.setSpacing(6)
        head = QLabel(T("成就紀錄"))
        head.setAlignment(Qt.AlignCenter)
        head.setStyleSheet(f"font-size:17px; font-weight:bold; color:{theme.INK_DARK};")
        lay.addWidget(head)
        n, total = len(got), len(ACHIEVEMENTS)
        sub = QLabel(T("已解鎖 {n} / {total}", n=n, total=total))
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"color:{theme.MUTED};")
        lay.addWidget(sub)
        lay.addWidget(_bar(n / total))
        sections = []
        for title, keys in ACH_SECTIONS:                 # 依類別分段（營業、手藝、收集、沖煮方式、日常）
            rows = []
            for key in keys:
                if key in TIER_OF:
                    # 分級成就：一組一列，兩或三個獎牌；名稱是目前最高級，說明是下一級
                    group = TIER_OF[key][0]
                    tiers = TIER_GROUPS[group]
                    level = sum(1 for k, _ in tiers if k in got)
                    ok = level > 0
                    top = tiers[level - 1][0] if ok else tiers[0][0]
                    name = info[top][0]
                    if level < len(tiers):
                        nxt = tiers[level][0]
                        now = money(values[group]) if group == "revenue" else f"{values[group]:,}"
                        desc = T("{desc}（目前 {n}）", desc=money_text(T(info[nxt][1])), n=now)
                        desc = T("下一級：{desc}", desc=desc) if ok else desc
                    else:
                        desc = T("已達最高級：{desc}", desc=money_text(T(info[top][1])))
                    icon = QLabel()
                    icon.setPixmap(_medals([k in got for k, _ in tiers], self.devicePixelRatioF()))
                    date = max(got[k] for k, _ in tiers if k in got) if ok else ""
                    rows.append((icon, T(name), desc, ok, date))
                else:
                    ok = key in got
                    icon = QLabel("🏆" if ok else "🔒")
                    icon.setStyleSheet("font-size:16px;" + ("" if ok else f"color:{theme.FAINT};"))
                    rows.append((icon, T(info[key][0]), money_text(T(info[key][1])), ok, got.get(key, "")))
            sections.append((T(title), rows))
        for title, rows in sections:
            lay.addWidget(_dash())
            sec = QLabel(title)
            sec.setStyleSheet(f"font-weight:bold; color:{theme.MUTED}; letter-spacing:2px; padding-top:2px;")
            lay.addWidget(sec)
            for i, (icon, name, desc, ok, date) in enumerate(rows):
                if i:
                    lay.addWidget(_dash("dot"))
                row = QHBoxLayout()
                row.setSpacing(10)
                icon.setFixedWidth(48)
                icon.setAlignment(Qt.AlignCenter)
                row.addWidget(icon)
                ink = theme.INK if ok else theme.FAINT
                lab = QLabel(f"<span style='font-weight:bold; color:{ink}'>{name}</span><br>"
                             f"<span style='color:{theme.MUTED if ok else theme.FAINT}'>{desc}</span>")
                lab.setWordWrap(True)
                row.addWidget(lab, 1)
                d = QLabel(date if ok else T("未解鎖"))
                d.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                d.setStyleSheet(f"color:{theme.MUTED if ok else theme.FAINT}; font-family:Consolas, monospace;")
                row.addWidget(d)
                lay.addLayout(row)
        lay.addWidget(_dash())
        foot = QLabel(T("全部解鎖了，謝謝光臨！") if n >= total else T("— 還有 {n} 個等你解鎖 —", n=total - n))
        foot.setAlignment(Qt.AlignCenter)
        foot.setStyleSheet(f"color:{theme.MUTED}; padding-top:2px;")
        lay.addWidget(foot)
        return outer

    def art_tab(self):
        w = QWidget()
        g = QGridLayout(w)
        col = self.app.stats.data["collection"]["art"]
        g.setContentsMargins(0, 0, 0, 0)
        g.addWidget(_muted(T("每種圖案保留拉得最好的一次")), 0, 0, 1, 4)
        for i, pat in enumerate(ART_BOOK):
            r, c = divmod(i, 4)
            box = QVBoxLayout()
            pic = QLabel()
            pic.setFixedSize(104, 104)
            pic.setAlignment(Qt.AlignCenter)
            info = col.get(pat)
            pm = QPixmap(104, 104)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#ece6de"))
            p.drawEllipse(QPointF(52, 52), 50, 50)
            if info:
                tops = {"whip": 1.0, "cocoa": 1.0} if pat == "whip" else ({"caramel": 1.0} if pat == "mark" else {})
                base = "#e9d6bb" if pat not in ("dot",) else "#b07a4a"
                img = make_art(pat, 1.0, info["q"], info["seed"], base, "#8a5a32", 160, tops=tops)
                p.drawImage(QRectF(6, 6, 92, 92), img)
            else:
                p.setBrush(QColor("#d4ccc2"))
                p.drawEllipse(QPointF(52, 52), 44, 44)
                f = QFont(self.font())
                f.setPointSize(26)
                f.setBold(True)
                p.setFont(f)
                p.setPen(QColor("#f4efe8"))
                p.drawText(QRectF(0, 0, 104, 104), Qt.AlignCenter, "?")
            p.end()
            pic.setPixmap(pm)
            box.addWidget(pic, 0, Qt.AlignHCenter)
            name = T(ART_NAMES[pat].split("（")[0]) if info else "？？？"
            text = f"<b>{name}</b>"
            if info:
                text += "<br><span style='color:#7a6a5a'>" + T("品質 {q:.0f} · {date}", q=info["q"] * 100,
                                                               date=info["date"]) + "</span>"
            lab = QLabel(text)
            lab.setAlignment(Qt.AlignCenter)
            box.addWidget(lab)
            g.addLayout(box, r + 1, c)
        return w

    @staticmethod
    def drink_tip(k, made):
        """圖鑑飲品卡片的提示：說明與做法（drink_notes）；還沒做過的不透露，只說做過後會記下來"""
        if not made:
            return T("還沒做過：做過一次，這裡就會記下說明與做法")
        desc, steps = DRINK_NOTES[k]
        rows = "".join(f"<tr><td style='color:{theme.MUTED}'>{i}.</td><td>{html.escape(T(s))}</td></tr>"
                       for i, s in enumerate(steps, 1))
        # Qt 的提示不認 div 的寬度：用固定寬度的表格讓說明自動換行
        return (f"<table width='280' cellspacing='0'><tr><td><b>{html.escape(T(DRINKS[k]['name']))}</b><br>"
                f"{html.escape(T(desc))}<br><br><b>{T('做法')}</b>"
                f"<table cellspacing='0' cellpadding='1'>{rows}</table></td></tr></table>")

    @staticmethod
    def drink_price(k):
        """圖鑑飲品卡片的價格：分大中小的寫「小 / 中 / 大」三個價格"""
        base = orders.PRICES.get(k, orders.FESTIVAL_PRICE)
        if k in orders.SIZE_DRINKS:
            s, m, l = (money(base + orders.SIZE_PRICE[z]) for z in ("S", "M", "L"))
            return T("小 {s} · 中 {m} · 大 {l}", s=s, m=m, l=l)
        return money(base)

    @staticmethod
    def pic_card(pix, name, sub, have, tip=""):
        """圖鑑的小卡片：圖、名稱、一行說明（牛奶、豆子產地）"""
        box = QWidget()
        if tip:
            box.setToolTip(tip)
        card = QVBoxLayout(box)
        card.setContentsMargins(0, 0, 0, 0)
        card.setSpacing(1)
        pic = QLabel()
        pic.setPixmap(pix)
        pic.setAlignment(Qt.AlignCenter)
        card.addWidget(pic)
        lab = QLabel(name)
        lab.setAlignment(Qt.AlignCenter)
        lab.setWordWrap(True)
        lab.setStyleSheet("font-weight:bold;" if have else f"color:{theme.FAINT};")
        card.addWidget(lab)
        note = QLabel(sub)
        note.setAlignment(Qt.AlignCenter)
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{theme.MUTED if have else theme.FAINT}; font-size:11px;")
        card.addWidget(note)
        return box

    def milk_cards(self, g, r, have, dpr):
        """圖鑑的牛奶：每種一盒；沒用過的是灰色剪影"""
        g.addWidget(_title(T("{title}（{n}/{total}）", title=T("牛奶"), n=sum(1 for k in MILK_KINDS if k in have),
                             total=len(MILK_KINDS))), r, 0, 1, 4)
        r += 1
        for i, (k, v) in enumerate(MILK_KINDS.items()):
            ok = k in have
            sub = T("奶泡細緻度 ×{t:.2f}", t=v["texture"]) if ok else T("還沒用過")
            g.addWidget(self.pic_card(milk_icon(k, 72, ok, dpr), T(v["name"]) if ok else "？？？", sub, ok), r, i % 4)
            if i % 4 == 3:
                r += 1
        return r + (len(MILK_KINDS) % 4 != 0)

    def origin_cards(self, g, r, have, dpr):
        """圖鑑的豆子產地：每個產地一袋（標籤依產地、豆色依烘焙度，精品豆金邊）；滑鼠停著顯示風味"""
        g.addWidget(_title(T("{title}（{n}/{total}）", title=T("豆子產地"), n=sum(1 for k in ORIGINS if k in have),
                             total=len(ORIGINS))), r, 0, 1, 4)
        r += 1
        for i, (k, v) in enumerate(ORIGINS.items()):
            ok = k in have
            name, roast, flavor = v[0], v[1], v[2]
            premium = k in beans.PREMIUM
            sub = (T(roast) + (T(" · 精品") if premium else "")) if ok else T("還沒用過")
            tip = T("風味：{flavor}", flavor=T(flavor)) if ok else ""
            g.addWidget(self.pic_card(bean_icon(k, roast, premium, 72, ok, dpr), T(name) if ok else "？？？", sub, ok, tip),
                        r + i // 4, i % 4)
        return r + (len(ORIGINS) + 3) // 4

    def book_tab(self):
        w = QWidget()
        g = QGridLayout(w)
        col = self.app.stats.data["collection"]
        keys = list(DRINK_KEYS) + list(FESTIVAL_DRINKS)
        g.addWidget(_title(T("飲品（{n}/{total}）", n=sum(1 for k in keys if k in col["drinks"]), total=len(keys))),
                    0, 0, 1, 4)
        dpr = self.devicePixelRatioF()
        for i, k in enumerate(keys):                 # 一張卡片：側面圖、名稱、杯數與最高分；沒做過是灰色剪影
            info = col["drinks"].get(k)
            box = QWidget()                          # 整張卡片滑鼠停著時顯示說明與做法
            box.setToolTip(self.drink_tip(k, bool(info)))
            card = QVBoxLayout(box)
            card.setContentsMargins(0, 0, 0, 0)
            card.setSpacing(1)
            pic = QLabel()
            pic.setPixmap(drink_icon(k, 84, bool(info), dpr))
            pic.setAlignment(Qt.AlignCenter)
            card.addWidget(pic)
            name = T(DRINKS[k]["name"]) if info else "？？？"
            if DRINKS[k].get("festival"):
                name += T("（{fest}限定）", fest=T(FESTIVALS[DRINKS[k]["festival"]][0]))
            lab = QLabel(name)
            lab.setAlignment(Qt.AlignCenter)
            lab.setWordWrap(True)
            lab.setStyleSheet("font-weight:bold;" if info else f"color:{theme.FAINT};")
            card.addWidget(lab)
            m = method_of(k)
            if info:
                sub = T("{n} 杯 · 最高 {s:.0f} 分", n=info["count"], s=info["best"])
            elif not self.app.method_open(m):
                sub = T("店鋪 Lv.{n} 解鎖", n=growth.METHOD_LEVEL[m])
            elif not self.app.drink_open(k):
                sub = T("咖啡師「{rank}」解鎖", rank=T(growth.rank_name(growth.drink_rank(k))))
            else:
                sub = T("還沒做過")
            note = QLabel(sub)
            note.setAlignment(Qt.AlignCenter)
            note.setStyleSheet(f"color:{theme.MUTED if info else theme.FAINT}; font-size:11px;")
            card.addWidget(note)
            price = QLabel(self.drink_price(k))                   # 營業模式的價格（分大中小的列三個）
            price.setAlignment(Qt.AlignCenter)
            price.setWordWrap(True)
            price.setStyleSheet(f"color:{theme.ACCENT if info else theme.FAINT}; font-size:11px;")
            card.addWidget(price)
            r, c = divmod(i, 4)
            g.addWidget(box, 1 + r, c)
        r = 2 + (len(keys) - 1) // 4
        art = self.app.stats.data["collection"]["art"]                       # 拉花收集（原本是獨立分頁）
        g.addWidget(_title(T("拉花收集（{n}/{total}）", n=sum(1 for a in ART_BOOK if a in art), total=len(ART_BOOK))),
                    r, 0, 1, 4)
        g.addWidget(self.art_tab(), r + 1, 0, 1, 4)
        r += 2
        r = self.gear_cards(g, r)
        r = self.milk_cards(g, r, col["milks"], dpr)
        r = self.origin_cards(g, r, col["origins"], dpr)
        for c in range(4):
            g.setColumnStretch(c, 1)
        g.setRowStretch(r, 1)
        return w
