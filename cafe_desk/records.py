"""紀錄與收集冊視窗：今天、近兩週、成就、拉花收集、飲品圖鑑"""
import datetime
import html

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer
from PySide6.QtGui import QPainter, QPixmap, QPen, QFont, QColor, QPainterPath, QIcon
from PySide6.QtWidgets import (QCheckBox, QDialog, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QGridLayout,
                               QScrollArea, QPushButton, QFrame, QProgressBar, QToolButton)

from .drinks import DRINKS, DRINK_KEYS, FESTIVAL_DRINKS, ART_NAMES, MILK_KINDS
from .beans import ORIGINS
from .festivals import today, FESTIVALS
from . import growth, theme, store, beans, brew, orders, challenges, regulars, decor, ingredients
from .i18n import T, money, money_text, retext
from .machines import MACHINES
from .render.shop import BACK_GEAR
from . import stats as stats_mod
from .stats import ACHIEVEMENTS, ART_BOOK, TIER_GROUPS, TIER_OF, ACH_SECTIONS
from .render.milk import make_art
from .render.icons import drink_icon, milk_icon, bean_icon, upgrade_icon, decor_icon, ingredient_icon, dessert_icon
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
    KINDS = {"shop": "商店", "ingredients": "商店", "layout": "佈置"}      # tab → 獨立視窗；其他（None）是紀錄與收集冊

    def __init__(self, app, tab=None):
        super().__init__(None)
        self.app = app
        self.kind = self.KINDS.get(tab, "紀錄與收集冊")                     # 商店、佈置、紀錄與收集冊是三個獨立視窗
        self.setWindowTitle(T(self.kind))
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
        n = len(st["achievements"])
        if self.kind == "商店":
            tabs.addTab(self.store_tab(), T("商店"))
            if tab == "ingredients":
                self.store_sub.setCurrentIndex(3)
        elif self.kind == "佈置":
            self.layout_page = self.layout_tab()
            tabs.addTab(self.layout_page, T("佈置"))
        else:
            self.ops_sub = self.group([(self.today_tab(), T("今天")), (self.scroll(self.shop_tab()), T("店鋪")),
                                       (self.scroll(self.customers_tab()), T("客人")), (self.history_tab(), T("近期紀錄"))])
            tabs.addTab(self.ops_sub, T("營運紀錄"))                       # 今天／店鋪／客人／近期紀錄
            self.achv_sub = self.group([(self.scroll(self.achievements_tab()), T("成就 {n}/{total}", n=n, total=len(ACHIEVEMENTS))),
                                        (self.scroll(self.challenge_tab()), T("挑戰"))])
            tabs.addTab(self.achv_sub, T("成就與挑戰"))
            self.book_sub = self.book_tab()
            tabs.addTab(self.book_sub, T("圖鑑"))
        row = QHBoxLayout()
        row.addStretch(1)
        b = QPushButton(T("關閉"))
        b.clicked.connect(self.close)
        row.addWidget(b)
        lay.addLayout(row)

    @staticmethod
    def group(pages):
        """幾個頁面合成一個分頁（裡面再分小分頁）：pages＝[(頁面, 名稱)]"""
        sub = QTabWidget()
        for page, name in pages:
            sub.addTab(page, name)
        return sub

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

    def decor_cards(self, g, r, dpr):
        """圖鑑的店面裝潢收集：每一款（不含預設款）一張小圖，買過的是彩色、沒買的是淡淡的剪影；滑鼠停著看名稱與說明"""
        owned = self.app.stats.data["owned"]
        have, total = decor.collection(owned)
        g.addWidget(_title(T("店面裝潢收集（{n}/{total}）", n=have, total=total)), r, 0, 1, 4)
        box = QGridLayout()
        box.setSpacing(6)
        keys = [k for k in decor.ITEMS if not decor.is_default(k)]
        cols = 8
        for i, k in enumerate(keys):
            ok = f"decor_{k}" in owned
            pic = QLabel()
            pm = decor_icon(k, 56, dpr)
            if not ok:
                faded = QPixmap(pm.size())
                faded.setDevicePixelRatio(pm.devicePixelRatio())
                faded.fill(Qt.transparent)
                q = QPainter(faded)
                q.setOpacity(0.22)
                q.drawPixmap(0, 0, pm)
                q.end()
                pm = faded
            pic.setPixmap(pm)
            pic.setAlignment(Qt.AlignCenter)
            _slot, name, price, stamps, desc = decor.ITEMS[k]
            how = T("{n} 個章兌換", n=stamps) if stamps else money(price)
            pic.setToolTip(f"{T(decor.SLOT_NAME[decor.ITEMS[k][0]])} · {T(name)}\n{T(desc)}" if ok
                           else f"{T(decor.SLOT_NAME[decor.ITEMS[k][0]])} · ？？？\n{T('商店買得到')}：{how}")
            box.addWidget(pic, i // cols, i % cols)
        g.addLayout(box, r + 1, 0, 1, 4)
        return r + 2

    def customers_tab(self):
        """客人習慣紀錄：每位來過的客人（熟客等級高的在前）：杯數、平均分數、常點的飲品、杯型、內用或外帶、用的奶、最近一次"""
        lay = QVBoxLayout(w := QWidget())
        lay.setSpacing(2)
        custs = self.app.stats.data["customers"]
        lay.addWidget(_title(T("客人習慣紀錄（{n} 位）", n=len(custs))))
        if not custs:
            lay.addWidget(_muted(T("還沒有客人：營業模式的訂單會記下每位客人的習慣。")))
        elif not regulars.roster(custs):
            lay.addWidget(_muted(T("還沒有熟客：同一位客人來過 {n} 次、平均 {a:.0f} 分以上就會變熟面孔。",
                                   n=regulars.LEVELS[0][0], a=regulars.LEVELS[0][1])))
        lay.addWidget(_muted(T("熟客會常回來、點「老樣子」，每升一級小費多 {t:.0f}%、耐心多 {p:.0f}%（最高「{name}」）。",
                               t=regulars.TIP_STEP * 100, p=regulars.PATIENCE_STEP * 100, name=T(regulars.LEVELS[-1][2]))))
        usual = {name: fav for name, _lv, _n, _avg, fav in regulars.roster(custs)}        # 熟客的「老樣子」
        order = sorted(custs, key=lambda n: (-regulars.level_of(custs[n]), -custs[n]["cups"], n))
        for name in order:
            rec = custs[name]
            lv = regulars.level_of(rec)
            h = regulars.habits(rec)
            head = QLabel(f"{T(name)}" + (f" · {T(regulars.level_name(lv))}" if lv else "")
                          + "　" + T("{n} 杯 · 平均 {a:.0f} 分", n=rec["cups"], a=rec["score_sum"] / rec["cups"]))
            head.setStyleSheet(f"font-weight:bold; color:{ACCENT if lv else theme.INK}; padding-top:6px;")
            lay.addWidget(head)
            parts = [T("常點：{d}", d=T("、").join(T(DRINKS[k]["name"]) for k in h["drinks"] if k in DRINKS))]
            if usual.get(name) in DRINKS:
                parts.insert(0, T("老樣子：{d}", d=T(DRINKS[usual[name]]["name"])))
            if h["size"]:
                parts.append(T("杯型：{s}", s=T({"S": "小杯", "M": "中杯", "L": "大杯"}[h["size"]])))
            if h["place"]:
                parts.append(T("多半{p}", p=T("內用" if h["place"] == "dine" else "外帶")))
            if h["milk"] in MILK_KINDS:
                parts.append(T("奶：{m}", m=T(MILK_KINDS[h["milk"]]["name"])))
            lay.addWidget(_muted(" · ".join(parts)))
            lay.addWidget(_muted(T("最近一次：{day} · 最高 {s:.0f} 分", day=h["last"], s=h["best"])))
        lay.addStretch(1)
        return w

    def challenge_tab(self):
        """每日／每週挑戰的進度與集點卡（完成的蓋章、集滿章數換稱號）"""
        app = self.app
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(5)
        day = today().isoformat()
        cs = app.challenge_set()
        done_ids = app.stats.data["challenges"]

        def row(it):
            value, goal, failed = challenges.progress(it, app.stats, day)
            ok = it["id"] in done_ids
            text = challenges.text_of(it, lambda k: DRINKS[k]["name"])
            lab = QLabel(("✓ " if ok else "") + text)
            lab.setWordWrap(True)
            lab.setStyleSheet(f"font-weight:bold; color:{ACCENT if ok else theme.INK};")
            lay.addWidget(lab)
            if "revenue" in it["kind"]:
                note = f"{money(value)} / {money(goal)}"
            else:
                note = f"{value} / {goal}"
            if failed and not ok:
                note = T("已經有客人離開了，今天做不成")
            lay.addWidget(_bar(1.0 if ok else (0.0 if failed else value / goal)))
            lay.addWidget(_muted(T("已完成") if ok else note))

        lay.addWidget(_title(T("今日挑戰（完成各蓋 1 個章）")))
        for it in cs["daily"]:
            row(it)
        lay.addWidget(_title(T("本週挑戰（完成各蓋 {n} 個章）", n=challenges.WEEKLY_STAMPS)))
        for it in cs["weekly"]:
            row(it)
        stamps = challenges.stamps_of(done_ids)
        fill, cards = challenges.card_fill(stamps)
        lay.addWidget(_title(T("集點卡")))
        dots = "".join("●" if i < fill else "○" for i in range(challenges.STAMPS_PER_CARD))
        card = QLabel(f"<span style='font-size:20px; letter-spacing:4px; color:{ACCENT}'>{dots}</span>")
        lay.addWidget(card)
        lay.addWidget(_muted(T("共 {s} 個章，集滿 {c} 張卡", s=stamps, c=cards)))
        idx = challenges.title_index(stamps)
        lay.addWidget(QLabel(T("稱號：{name}", name=T(challenges.TITLES[idx][1])) if idx >= 0 else T("稱號：（還沒有）")))
        nxt = challenges.next_title(stamps)
        lay.addWidget(_muted(T("下一個稱號「{name}」：還差 {n} 個章", name=T(nxt[0]), n=nxt[1]) if nxt else T("已經是最高稱號")))
        lay.addWidget(_muted(T("只有營業模式的訂單會累計；每天（週）的挑戰不會因為升級而改變，隔天（下週）換新的。")))
        lay.addStretch(1)
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
        if lv >= growth.MAX_LEVEL:                                    # 星級評鑑：Lv.10 之後
            stars = self.app.star_rating()
            rows.append((T("店鋪評鑑"), T("近 {d} 天：{r:.1f} 星", d=growth.STAR_DAYS, r=stars) if stars is not None
                         else T("評鑑中（近 {d} 天要有 {n} 杯訂單）", d=growth.STAR_DAYS, n=growth.STAR_MIN_ORDERS)))
        r = 2
        for k, v in rows:
            g.addWidget(QLabel(k), r, 0)
            lab = QLabel(v)
            lab.setStyleSheet(f"font-weight:bold; color:{ACCENT};")
            g.addWidget(lab, r, 1)
            r += 1
        g.addWidget(_muted(T("店鋪等級依營業模式的累積營業額（含小費）計算，等級越高客人越多、越有耐心。")), r, 0, 1, 2)
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
    GEAR_TEXT = {"grinder": "DESK·01、復古拉桿、小型單鍋爐共用", "commercial_grinder": "營業用雙頭機的磨豆機：不鏽鋼機身、大豆倉，兩個沖煮頭共用", "station_grinder": "手沖、冰滴、摩卡壺、虹吸壺共用",
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
        ok = app.machine_open("duo")                                   # 營業用磨豆機：跟雙頭機一起解鎖
        items.append((gear_icons.grinder_icon(app, 150, 104, not ok, dpr, "commercial"), T("營業用磨豆機"),
                      T("{name} · 店鋪 Lv.{n} 解鎖", name=T("營業用雙頭機"), n=growth.MACHINE_LEVEL["duo"]) if not ok else T("跟著雙頭機解鎖"),
                      T(self.GEAR_TEXT["commercial_grinder"]), [n for k, (t, n, *_r) in store.UPGRADES.items()
                                                                if t == store.COMMERCIAL and k in owned], ok))
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

    @staticmethod
    def guide_tab():
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

        section(T("三種模式（右鍵選單上方：練習＝手動或自動，營業）"))
        bullet(T("<b>手動</b>：點一下做一杯。"))
        bullet(T("<b>自動</b>：照目前的飲品與參數一直做同一杯，間隔在「自動做咖啡」選；適合當擺件。"))
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
        bullet(T("店鋪到 Lv.{n} 之後有星級評鑑：看近 {d} 天的平均分數、客人離開的比例與平均等待，算出 1–5 星（成績變差會掉星），畫在櫃檯畫面的招牌上；偶爾會有評鑑員上門，那杯分數算兩倍。",
                 n=growth.MAX_LEVEL, d=growth.STAR_DAYS))
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
        bullet(T("到「{name}」之後，每種飲品各有 1–5 星的專精：這種飲品做過的杯數與最高分都要到（{steps}），每顆星手感誤差再少 {p:.0f}%，圖鑑的飲品卡片會掛星。",
                 name=T(growth.rank_name(growth.MASTERY_RANK)), p=growth.MASTERY_K * 100,
                 steps="、".join(f"{n} 杯 {b:.0f} 分" for n, b in growth.MASTERY_STEPS)))
        bullet(T("越熟練手感越穩、奶泡越細；而且 {base:.0f} 分以上的部分依稱號打折：{pct}。",
                 base=growth.SCORE_FROM, pct=pct))

        section(T("錢包與商店（「商店」分頁）"))
        bullet(T("錢包＝初始資金 {s} ＋ 累積營業額 － 已花的錢；花錢不會掉級，店鋪等級只看營業額（不含初始資金）。", s=money(stats_mod.START_FUNDS)))
        bullet(T("咖啡機與磨豆機升級讓設備更穩、更好喝；精品豆比較甜，營業中用它做的飲品售價 ×{k:g}。", k=beans.PREMIUM_PRICE_K))

        section(T("成就"))
        bullet(T("跟杯子有關的成就只算營業模式裡為客人做的杯子；清潔保養、開豆子、等冰滴照常算。"))
        bullet(T("分級成就有銅、銀、金三級，「成就」分頁會顯示下一級還差多少。"))

        section(T("小技巧"))
        bullet(T("豆子烘焙後 7–21 天最好喝；每一包都要先在商店買，用完從庫存開新包（自動、營業時咖啡師會從庫存自己開，庫存沒有就沒豆子可用）。"))
        bullet(T("狀態列出現 ⚠ 就是該清潔保養了，太久沒清會扣分。"))
        bullet(T("冰滴要先架冰滴塔，之後在背景滴約 1 小時（關掉程式也照算）。"))
        bullet(T("右鍵「聲音」可以開環境音，「音樂」可以播放自己的音檔。"))
        return outer

    def store_tab(self, sub=0):
        """商店：上面是錢包餘額，下面分三個分頁（各自捲動）：設備升級（咖啡機升級每台一組、磨豆機升級共用的）、店面裝潢、咖啡豆（一包一包買）；
        sub＝開哪一個分頁（重畫時留在原本那頁）"""
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
        lay.addWidget(_muted(T("初始資金 {s} ＋ 累積營業額 {a} － 已花 {b}。店鋪等級照累積營業額計算（不含初始資金），花錢不會掉級。",
                               s=money(stats_mod.START_FUNDS), a=money(st["revenue_total"]), b=money(st["spent"]))))

        dpr = self.devicePixelRatioF()
        COLS = 3

        def card(pix, name, sub, desc, label, enabled, tip, fn, have=False, auto=None):
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
            if auto is not None:                                 # (勾選?, 切換函式)：自動購買
                cb = QCheckBox(T(auto[3] if len(auto) > 3 else "自動購買（庫存隨時留一包）"))
                cb.setChecked(auto[0])
                cb.setToolTip(auto[2] if len(auto) > 2 else "")
                cb.toggled.connect(lambda on: (auto[1](on), QTimer.singleShot(0, self.refresh_store)))
                v.addWidget(cb)
            b = QPushButton(label)
            b.setEnabled(enabled)
            if tip:
                b.setToolTip(tip)
                box.setToolTip(tip)
            if fn is not None:
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
                min(growth.MACHINE_LEVEL[k] for k in targets if k in growth.MACHINE_LEVEL)

        def section(title, keys):
            """一段升級：標題寫已買幾項，卡片全部並排（照咖啡機的順序，卡片上寫是哪台的）"""
            lay.addWidget(_dash())
            got = sum(1 for k in keys if k in st["owned"])
            lay.addWidget(_title(T("{title}（已買 {n}/{total}）", title=title, n=got, total=len(keys))))
            grid([upgrade(k) for k in keys])

        header = lay
        subtabs = self.store_sub = QTabWidget()
        header.addWidget(subtabs, 1)

        def page(build, name):
            nonlocal lay
            pw = QWidget()
            lay = QVBoxLayout(pw)                                # grid／section 用的 lay 換成這一頁的
            lay.setSpacing(6)
            build()
            lay.addStretch(1)
            subtabs.addTab(self.scroll(pw), name)

        def upgrades_page():
            section(T("咖啡機升級"), [k for mk in MACHINES for k, v in store.UPGRADES.items() if v[0] == (mk,)])
            section(T("磨豆機升級"), [k for t in (store.EXTERNAL, store.COMMERCIAL, store.STATION) for k, v in store.UPGRADES.items() if v[0] == t])

        def beans_page():
            self.beans_section(lay, grid, card, bal)

        def decor_page():
            self.decor_section(lay, grid, card, bal)

        page(upgrades_page, T("設備升級"))
        page(decor_page, T("店面裝潢"))
        page(beans_page, T("咖啡豆"))
        page(lambda: self.ingredients_section(lay, grid, card, bal), T("食材"))
        page(lambda: self.desserts_section(lay, grid, card, bal), T("甜點"))
        subtabs.setCurrentIndex(sub)
        w.setObjectName("page")
        return w

    def beans_section(self, lay, grid, card, bal):
        """商店的「咖啡豆」分頁內容：庫存、每種豆子一張卡片（買一包）"""
        app, dpr = self.app, self.devicePixelRatioF()
        lay.addWidget(_title(T("咖啡豆（庫存 {n} 包）", n=app.bean_stock())))
        lay.addWidget(_muted(T("每一包都要買，一包 {g:.0f} g（約 14 杯），放進庫存；右鍵「豆子」開一包，自動模式與營業中的咖啡師用完會從庫存自己開。"
                               "庫存沒有就沒豆子可用（卡片上勾選「自動購買（庫存隨時留一包）」就會在庫存沒有時自動買）。精品豆甜感比一般豆高，營業中用它做的飲品售價 ×{k:g}，也有客人專門指定精品豆。",
                               g=beans.BAG_G, k=beans.PREMIUM_PRICE_K)))
        bean_cards = []
        for key, (name, roast, flavor, sweet) in ((k, v) for k, v in beans.ORIGINS.items()):
            price = beans.price_of(key)
            short = max(0, price - bal)
            now = app.bag["origin"] == key
            note = T("（正在用這包，剩 {g:.0f} g）", g=app.bag["left"]) if now else ""
            bean_cards.append(card(bean_icon(key, roast, True, 64, True, dpr), T(name),
                                   T("{roast} · 甜感 +{s:g} · 庫存 {n}", roast=T(roast), s=sweet, n=app.bean_stock(key))
                                   + (T(" · 自動購買") if key in app.auto_buy else ""),
                                   T(flavor) + note, T("買一包 {m}", m=money(price)), short == 0,
                                   T("還差 {m}", m=money(short)) if short else "",
                                   lambda _=False, k=key: self.buy(app.buy_beans, k), app.bean_stock(key) > 0 or now,
                                   auto=(key in app.auto_buy, lambda on, k=key: app.set_auto_buy(k, on),
                                         T("庫存沒有時自動買一包（勾多種就隨機買其中一種，錢包買得起的才買）"))))
        grid(bean_cards)

    def ingredients_section(self, lay, grid, card, bal):
        """商店的「食材」分頁內容：每種食材一張卡片（買一包），庫存不夠的飲品營業中客人不會點"""
        app, dpr = self.app, self.devicePixelRatioF()
        lay.addWidget(_title(T("食材")))
        lay.addWidget(_muted(T("營業中每杯飲品要用掉食材（一杯一份），一包有固定份數。庫存沒有時客人不會點需要它的飲品（例如沒有鮮奶就沒有拿鐵），"
                               "客人要求換植物奶時也要有那種奶。卡片上勾選「自動購買（庫存隨時留一份）」就會在沒庫存時自動買。手動與自動模式不消耗食材。")))
        cards = []
        for key, (name, per, price, desc) in ingredients.ITEMS.items():
            short = max(0, price - bal)
            n = app.ing_stock(key)
            cards.append(card(ingredient_icon(key, 64, dpr), T(name),
                              T("庫存 {n} 份 · 一包 {p} 份", n=n, p=per) + (T(" · 自動補貨") if key in app.auto_ing else ""),
                              T(desc) + (T("（用完了）") if n == 0 else ""), T("買一包 {m}", m=money(price)), short == 0,
                              T("還差 {m}", m=money(short)) if short else "",
                              lambda _=False, k=key: self.buy(app.buy_ingredient, k), n > 0,
                              auto=(key in app.auto_ing, lambda on, k=key: app.set_auto_ing(k, on),
                                    T("營業中這項食材沒有庫存時自動買一包（錢包買得起才買）"), "自動購買（庫存隨時留一份）")))
        grid(cards)

    def desserts_section(self, lay, grid, card, bal):
        """商店的「甜點」分頁內容：每種甜點一盤一盤進貨，擺在櫃檯右上的玻璃櫥窗；加購折價、有貨會多一些內用客人"""
        app, dpr = self.app, self.devicePixelRatioF()
        lay.addWidget(_title(T("甜點（庫存 {n} 個）", n=sum(app.ing_stock(k) for k in ingredients.DESSERTS))))
        lay.addWidget(_muted(T("甜點一盤一盤進貨，有庫存的擺在櫃檯右上的玻璃櫥窗。營業中客人點飲品時會有 {p:.0%} 的機會加購一個甜點，"
                               "加購折價 {off:g}%（POS 會另列一行）；櫥窗有貨的話外帶的客人變少、內用的客人變多（座位要有空位）。"
                               "賣完了客人就不會加購。手動與自動模式不消耗甜點。",
                               p=ingredients.DESSERT_P, off=round((1 - ingredients.DESSERT_COMBO_K) * 100))))
        cards = []
        for key, (name, per, price, desc) in ingredients.DESSERTS.items():
            short = max(0, price - bal)
            n = app.ing_stock(key)
            sell = ingredients.DESSERT_PRICE[key]
            cards.append(card(dessert_icon(key, 64, dpr), T(name),
                              T("庫存 {n} 個 · 一盤 {p} 個", n=n, p=per) + (T(" · 自動補貨") if key in app.auto_ing else ""),
                              T(desc) + T("；售價 {a}，加購 {b}", a=money(sell), b=money(ingredients.dessert_price(key)))
                              + (T("（賣完了）") if n == 0 else ""),
                              T("進一盤 {m}", m=money(price)), short == 0,
                              T("還差 {m}", m=money(short)) if short else "",
                              lambda _=False, k=key: self.buy(app.buy_ingredient, k), n > 0,
                              auto=(key in app.auto_ing, lambda on, k=key: app.set_auto_ing(k, on),
                                    T("營業中這種甜點賣完時自動進一盤（錢包買得起才買）"), "自動購買（庫存隨時留一盤）")))
        grid(cards)
        # 購買紀錄：累計進貨、賣出，以及最近幾筆進貨
        st = app.stats.data
        lay.addWidget(_dash())
        lay.addWidget(_title(T("購買紀錄")))
        trays, spent = sum(st["dessert_bought"].values()), st["dessert_spent"]
        sold = sum(st["dessert_sold"].values())
        lay.addWidget(_muted(T("累計進貨 {n} 盤，花了 {m}；營業中賣出 {s} 個。", n=trays, m=money(spent), s=sold)))
        for key, (name, per, price, desc) in ingredients.DESSERTS.items():
            b, s_ = st["dessert_bought"].get(key, 0), st["dessert_sold"].get(key, 0)
            if b or s_:
                lay.addWidget(QLabel(T("{name}：進貨 {b} 盤 · 賣出 {s} 個 · 庫存 {n} 個",
                                       name=T(name), b=b, s=s_, n=app.ing_stock(key))))
        log = app.stats.dessert_log()
        log = app.stats.dessert_log()
        if not log:
            lay.addWidget(_muted(T("還沒有進貨紀錄")))
        for day, key, price in log:
            lay.addWidget(QLabel(T("{day}　進貨一盤{name}　{m}", day=day, name=T(ingredients.DESSERTS[key][0]), m=money(price))))

    def decor_section(self, lay, grid, card, bal):
        """商店的「店面裝潢」分頁內容：每個欄位一排卡片，只能買（買過的標「已購買」）；要換上、拿下來到「佈置」分頁"""
        app, dpr = self.app, self.devicePixelRatioF()
        st = app.stats.data
        lay.addWidget(_title(T("店面裝潢（{n}/{total}）", n=decor.collection(st["owned"])[0], total=decor.collection(st["owned"])[1])))
        free = app.stamps_free()
        lay.addWidget(_muted(T("只改外觀、不影響平衡，改的是櫃檯畫面。一般款花錢包，標「章」的限定款用挑戰章數兌換（現有 {s} 個章）。這裡只能購買，要更換或拿下來到「佈置」分頁。", s=free)))
        for slot in decor.SLOTS:
            keys = [k for k, v in decor.ITEMS.items() if v[0] == slot]
            note = T("可以同時擺 {n} 個", n=decor.MAX_PAINTINGS if slot == "paintings" else decor.MAX_PLANTS) if slot in decor.MULTI else ""
            lay.addWidget(QLabel(f"<b>{T(decor.SLOT_NAME[slot])}</b>" + (f" <span style='color:{theme.MUTED}'>{note}</span>" if note else "")))
            cards = []
            for k in keys:
                _s, name, price, stamps, desc = decor.ITEMS[k]
                have = k in decor.owned_keys(st["owned"])
                if have:
                    label, ok, tip = T("已購買"), False, T("到「佈置」分頁更換")
                    fn = None
                elif stamps:
                    label, ok = T("{n} 個章兌換", n=stamps), free >= stamps
                    tip = "" if ok else T("還差 {n} 個章", n=stamps - free)
                    fn = (lambda _=False, key=k: self.buy(app.buy_decor, key))
                else:
                    short = max(0, price - bal)
                    label, ok = money(price), short == 0
                    tip = "" if ok else T("還差 {m}", m=money(short))
                    fn = (lambda _=False, key=k: self.buy(app.buy_decor, key))
                cards.append(card(decor_icon(k, 64, dpr), T(name), "", T(desc), label, ok, tip, fn, have))
            grid(cards)

    def layout_tab(self):
        """佈置：上面是櫃檯畫面的預覽，下面調整後檯的咖啡機與沖煮設備、每個裝潢欄位（只能換買過的款式；沒買的到「商店」）"""
        app = self.app
        st = app.stats.data
        top = QWidget()
        top.setObjectName("page")
        outer = QVBoxLayout(top)
        outer.setSpacing(6)
        outer.addWidget(_title(T("佈置")))
        outer.addWidget(_muted(T("調整櫃檯畫面的後檯與裝潢，上面的預覽會跟著變。只能換已經買到的款式，還沒買的到「商店」分頁買。")))
        dpr = self.devicePixelRatioF()
        pic = QLabel()                                          # 預覽固定在上面，下面的選項才捲動
        pic.setPixmap(QPixmap.fromImage(app.layout_preview(560, dpr)))
        pic.setAlignment(Qt.AlignCenter)
        outer.addWidget(pic)
        fest = QCheckBox(T("節日裝飾（情人節、萬聖節、聖誕節）"))
        fest.setChecked(app.cfg.get("festival_decor", True))
        fest.toggled.connect(lambda on: (app.cfg.__setitem__("festival_decor", bool(on)), app.save_config(), app.update(),
                                         QTimer.singleShot(0, self.refresh_layout)))
        outer.addWidget(fest)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(6)
        self.layout_scroll = self.scroll(w)
        outer.addWidget(self.layout_scroll, 1)

        def later():
            QTimer.singleShot(0, self.refresh_layout)          # 在訊號處理完才重建（不要刪掉正在送訊號的元件）

        COLS = 5

        def tile(pix, text, on, fn, enabled=True, tip=""):
            """一個圖片選項：圖在上、名稱在下；選中的框起來（點一下選用，掛畫與植物是開關）"""
            b = QToolButton()
            b.setIcon(QIcon(pix))
            b.setIconSize(pix.size() / pix.devicePixelRatio())
            b.setText(text)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setCheckable(True)
            b.setChecked(on)
            b.setEnabled(enabled)
            b.setToolTip(tip or text)
            b.setFixedWidth(124)
            b.setStyleSheet(f"QToolButton {{ border:1px solid {theme.FAINT}; border-radius:6px; padding:4px; font-size:11px; }}"
                            f"QToolButton:checked {{ border:2px solid {ACCENT}; background:#f3ead8; font-weight:bold; }}"
                            f"QToolButton:hover:!checked {{ background:#f8f1e2; }}")
            b.clicked.connect(lambda _=False: (fn(), later()))
            return b

        def grid(tiles):
            g = QGridLayout()
            g.setSpacing(6)
            for n, t in enumerate(tiles):
                g.addWidget(t, n // COLS, n % COLS)
            g.setColumnStretch(COLS, 1)                          # 圖片選項靠左排
            lay.addLayout(g)

        lay.addWidget(_dash())
        lay.addWidget(_title(T("後檯")))
        lay.addWidget(QLabel(f"<b>{T('後檯的咖啡機（做義式的營業用咖啡機）')}</b>"))
        rnd = QPixmap(int(96 * dpr), int(72 * dpr))
        rnd.setDevicePixelRatio(dpr)
        rnd.fill(Qt.transparent)
        q = QPainter(rnd)
        f = QFont()
        f.setPointSize(26)
        f.setBold(True)
        q.setFont(f)
        q.setPen(QColor("#b8a890"))
        q.drawText(QRectF(0, 0, 96, 72), Qt.AlignCenter, "?")
        q.end()
        tiles = [tile(rnd, T("隨機使用"), app.showcase == "auto", lambda: app.set_showcase("auto"))]
        for k, m in MACHINES.items():
            ok = app.machine_open(k)
            tiles.append(tile(gear_icons.machine_icon(app, m, 96, 72, not ok, dpr), T(m.name), ok and app.showcase == k,
                              lambda key=k: app.set_showcase(key), ok,
                              "" if ok else T("店鋪 Lv.{n} 解鎖", n=growth.MACHINE_LEVEL[k])))
        grid(tiles)
        lay.addWidget(QLabel(f"<b>{T('後檯擺出來的沖煮設備（店鋪等級解鎖了才有）')}</b>"))
        tiles = []
        for key in BACK_GEAR:
            ok = app.method_open(key)
            tiles.append(tile(gear_icons.station_icon(app, key, 96, 72, not ok, dpr), T(brew.METHODS[key]),
                              ok and key not in app.cfg.get("back_gear_off", []),
                              lambda k=key: app.set_back_gear(k, k in app.cfg.get("back_gear_off", [])), ok,
                              "" if ok else T("店鋪 Lv.{n} 解鎖", n=growth.METHOD_LEVEL[key])))
        grid(tiles)

        sel = app.decor_sel()
        have = decor.owned_keys(st["owned"])
        lay.addWidget(_dash())
        lay.addWidget(_title(T("裝潢（已有 {n}／{total} 款）", n=sum(1 for k in decor.ITEMS if k in have), total=len(decor.ITEMS))))
        for slot in decor.SLOTS:
            mine = [k for k, v in decor.ITEMS.items() if v[0] == slot and k in have]
            note = ""
            if slot in decor.MULTI:
                note = T("可以同時擺 {n} 個", n=decor.MAX_PAINTINGS if slot == "paintings" else decor.MAX_PLANTS)
            lay.addWidget(QLabel(f"<b>{T(decor.SLOT_NAME[slot])}</b>" + (f" <span style='color:{theme.MUTED}'>{note}</span>" if note else "")))
            if not mine:
                lay.addWidget(_muted(T("還沒有，到「商店」買")))
                continue
            grid([tile(decor_icon(k, 64, dpr), T(decor.ITEMS[k][1]),
                       (k in sel[slot]) if slot in decor.MULTI else sel[slot] == k,
                       lambda key=k: app.use_decor(key)) for k in mine])
        lay.addStretch(1)
        return top

    def refresh_layout(self):
        """重畫「佈置」分頁（預覽與選項會變），捲動位置留在原處"""
        i = self.tabs.indexOf(self.layout_page)
        if i < 0:
            return
        here = self.tabs.currentIndex() == i
        pos = self.layout_scroll.verticalScrollBar().value()
        self.tabs.blockSignals(True)                         # 換分頁會觸發 currentChanged，不要又重畫一次
        try:
            self.tabs.removeTab(i)
            self.layout_page.deleteLater()
            self.layout_page = self.layout_tab()
            self.tabs.insertTab(i, self.layout_page, T("佈置"))
            if here:
                self.tabs.setCurrentIndex(i)
        finally:
            self.tabs.blockSignals(False)
        bar = self.layout_scroll.verticalScrollBar()
        bar.setValue(pos)
        QTimer.singleShot(0, lambda: bar.setValue(pos))

    def refresh_store(self):
        """重畫商店分頁（餘額、按鈕狀態會變），捲動位置留在原處（不然每買一樣就跳回最上面）"""
        i = self.tabs.currentIndex()
        old = self.tabs.widget(i)
        sub = self.store_sub.currentIndex()
        cur = self.store_sub.currentWidget()
        pos = cur.verticalScrollBar().value() if isinstance(cur, QScrollArea) else 0
        self.tabs.removeTab(i)
        old.deleteLater()
        page = self.store_tab(sub)
        self.tabs.insertTab(i, page, T("商店"))
        self.tabs.setCurrentIndex(i)
        bar = self.store_sub.currentWidget().verticalScrollBar()
        bar.setValue(pos)                                    # 版面還沒算好時範圍是 0：等事件迴圈排完版再設一次
        QTimer.singleShot(0, lambda: bar.setValue(pos))

    def buy(self, fn, key):
        """按下購買：成功後重畫商店分頁（餘額、按鈕狀態會變）"""
        if fn(key):
            self.refresh_store()
            lay = getattr(self.app, "layout_dlg", None)          # 開著的佈置視窗：新買的款式也要出現
            if lay is not None and lay.isVisible():
                lay.refresh_layout()

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

    def ingredient_cards(self, g, r, dpr):
        """圖鑑的食材：每種一張（營業中用掉過才解鎖，灰色剪影＝還沒用過），只寫用掉幾份；滑鼠停著看用在哪些飲品"""
        used = self.app.stats.data["ing_used_by"]
        items = list(ingredients.ITEMS)
        g.addWidget(_title(T("{title}（{n}/{total}）", title=T("食材"), n=sum(1 for k in items if used.get(k)),
                             total=len(items))), r, 0, 1, 4)
        r += 1
        for i, k in enumerate(items):
            ok = bool(used.get(k))
            name, per, _price, desc = ingredients.ITEMS[k]
            drinks = "、".join(T(DRINKS[d]["name"]) for d in ingredients.drinks_using(k))
            tip = T(desc) + ("\n" + T("用在：{drinks}", drinks=drinks) if drinks else "") if ok else T("營業中用掉一份就解鎖")
            sub = T("用掉 {n} 份", n=used[k]) if ok else T("還沒用過")
            g.addWidget(self.pic_card(ingredient_icon(k, 72, dpr, ok), T(name) if ok else "？？？", sub, ok, tip),
                        r + i // 4, i % 4)
        return r + (len(items) + 3) // 4

    def dessert_cards(self, g, r, dpr):
        """圖鑑的甜點：每種一張（營業中賣出過才解鎖，灰色剪影＝還沒賣過），只寫賣出幾個"""
        st = self.app.stats.data
        sold, bought = st["dessert_sold"], st["dessert_bought"]
        items = list(ingredients.DESSERTS)
        g.addWidget(_title(T("{title}（{n}/{total}）", title=T("甜點"), n=sum(1 for k in items if sold.get(k)),
                             total=len(items))), r, 0, 1, 4)
        r += 1
        for i, k in enumerate(items):
            ok = bool(sold.get(k))
            name, per, _price, desc = ingredients.DESSERTS[k]
            tip = (T(desc) + "\n" + T("售價 {a}，加購 {b}", a=money(ingredients.DESSERT_PRICE[k]), b=money(ingredients.dessert_price(k)))
                   if ok else T("營業中賣出一個就解鎖"))
            sub = T("賣出 {n} 個", n=sold[k]) if ok else T("還沒賣過")
            g.addWidget(self.pic_card(dessert_icon(k, 72, dpr, ok), T(name) if ok else "？？？", sub, ok, tip), r + i // 4, i % 4)
        return r + (len(items) + 3) // 4

    def book_tab(self):
        """圖鑑：分成幾個小分頁——飲品（含拉花收集）、設備、牛奶、豆子產地、食材、甜點、店面裝潢"""
        col = self.app.stats.data["collection"]
        dpr = self.devicePixelRatioF()

        def page(build):
            w = QWidget()
            g = QGridLayout(w)
            r = build(g)
            for c in range(4):
                g.setColumnStretch(c, 1)
            g.setRowStretch(r, 1)
            return self.scroll(w)
        return self.group([(page(self.drink_book), T("飲品")),
                           (page(lambda g: self.gear_cards(g, 0)), T("設備")),
                           (page(lambda g: self.milk_cards(g, 0, col["milks"], dpr)), T("牛奶")),
                           (page(lambda g: self.origin_cards(g, 0, col["origins"], dpr)), T("豆子")),
                           (page(lambda g: self.ingredient_cards(g, 0, dpr)), T("食材")),
                           (page(lambda g: self.dessert_cards(g, 0, dpr)), T("甜點")),
                           (page(lambda g: self.decor_cards(g, 0, dpr)), T("店面裝潢"))])

    def drink_book(self, g):
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
            if info and growth.mastery_open(self.app.stats.data["total"]):      # 專精星級（大師之後）
                n = growth.mastery_stars(info)
                badge = QLabel("★" * n + "☆" * (5 - n))
                badge.setAlignment(Qt.AlignCenter)
                badge.setToolTip(T("專精星級：做過的杯數與最高分都要到。每顆星這種飲品的手感誤差再少 {p:.0f}%。", p=growth.MASTERY_K * 100))
                badge.setStyleSheet("color:#d29a1e;" if n else f"color:{theme.FAINT};")
                card.addWidget(badge)
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
        return r + 2
