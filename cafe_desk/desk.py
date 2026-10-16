"""主視窗：設定、選單、系統匣、滑鼠、模擬推進與繪圖排程"""
import math
import random
import time
from dataclasses import asdict, fields

from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QPointF
from PySide6.QtGui import QPainter, QPixmap, QImage, QActionGroup, QLinearGradient, QRadialGradient, QColor
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QSystemTrayIcon

from . import config
from .gfx import pick_family
from .host import HostWindow
from .cups import Cup
from .drinks import (Session, DRINKS, DRINK_ORDER, AUTO_WEIGHTS, DrinkParams, ICE_VOL, ART_CHOICES, ART_NEED,
                     MILK_KINDS, FESTIVAL_DRINKS, is_milk, milk_plan)
from . import orders, beans, maintenance, festivals
from .stats import Stats, ACHIEVEMENTS
from .records import RecordsDialog
from .about import AboutDialog
from .i18n import T, LANGS, set_lang
from .layout import WIN_H, TOP_PAD, FLOOR
from .machines import MACHINES, DEFAULT_MACHINE
from .logo import load_icon
from .model import ROASTS, Params, Shot, Barista, Boiler
from .render.grinder import GrinderRenderer
from .render.liquid import LiquidRenderer
from .render.machine import MachineRenderer
from .render.milk import MilkRenderer
from .render.overlay import OverlayRenderer
from .render.particles import ParticleSystem
from .settings import SettingsDialog
from .sound import SoundBank
from .util import clamp
from .workflow import HANDLE_FULL

# 繪圖間隔（毫秒）：萃取中最順，閒置時省 CPU，縮到系統匣時不繪圖
FRAME_ACTIVE = 16      # 約 60 fps：萃取、完整流程、滴落、水花
FRAME_AMBIENT = 33     # 約 30 fps：蒸氣、指針回穩、氣泡破裂、卡片淡入淡出
FRAME_IDLE = 100       # 10 fps：只剩狀態列倒數與水溫微動
FRAME_HIDDEN = 250     # 縮到系統匣：只推進模擬（自動模式照常）
SIM_STEP = 0.05        # 模擬子步長（秒）：間隔拉長時切成多步，結果不受幀率影響
LOG_STEP = 0.1         # 萃取曲線取樣間隔（沖煮時間，秒）
WARMUP = 18.0          # 啟動時鍋爐比設定溫度低幾度，模擬預熱


def _inside(x, y, box):
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


class CafeDesk(QWidget, MachineRenderer, GrinderRenderer, LiquidRenderer, ParticleSystem, OverlayRenderer,
                   MilkRenderer):
    def __init__(self):
        super().__init__()
        self.cfg = self.load_config()
        names = {f.name for f in fields(Params)}
        self.params = Params(**{k: v for k, v in self.cfg.get("params", {}).items() if k in names})
        if self.params.roast not in ROASTS:
            self.params.roast = "中焙"
        self.auto = self.cfg.get("auto", False)
        self.interval = self.cfg.get("interval", 60)
        self.speed = self.cfg.get("speed", 1.0)
        self.topmost = self.cfg.get("topmost", False)
        self.windowed = self.cfg.get("windowed", False)   # 視窗化：一般視窗（標題列、工作列、不透明背景）
        self.scale_f = self.cfg.get("scale", 1.0)
        self.full_flow = self.cfg.get("full_flow", True)
        self.light_mode = self.cfg.get("light_mode", "auto")
        self.chart_on = self.cfg.get("chart", True)
        self.machine = MACHINES.get(self.cfg.get("machine"), MACHINES[DEFAULT_MACHINE])
        self.drink = self.cfg.get("drink", "espresso")
        if self.drink not in DRINKS or (self.drink in FESTIVAL_DRINKS and self.drink != festivals.festival_drink()):
            self.drink = "latte" if self.drink in DRINKS else "espresso"
        bag = self.cfg.get("bean_bag")
        self.bag = bag if (isinstance(bag, dict) and beans.valid_bag(bag)) else beans.new_bag("house")
        self.maint = maintenance.default_state()
        self.maint.update({k: v for k, v in self.cfg.get("maintenance", {}).items() if k in self.maint})
        self.job = None                          # 正在進行的清潔保養
        self.stats = Stats()
        self.toasts = []                         # 成就解鎖等短暫通知：(文字, 結束時間)
        self.notice = None                       # 狀態列的臨時提示：(文字, 結束時間)
        self.records_dlg = None
        self.about_dlg = None
        self.sync_bag()
        dnames = {f.name for f in fields(DrinkParams)}
        self.dp = DrinkParams(**{k: v for k, v in self.cfg.get("drink_params", {}).items() if k in dnames})
        if self.dp.art not in ART_NEED:
            self.dp.art = "auto"
        if self.dp.milk_kind not in MILK_KINDS:
            self.dp.milk_kind = "dairy"
        self.lang = self.cfg.get("lang", "zh")
        set_lang(self.lang)
        self.order_mode = self.cfg.get("order_mode", False)
        self.order = None                        # 目前的訂單
        self.order_no = int(self.cfg.get("order_no", 0))
        self.next_order_at = time.perf_counter() + 2.5
        self.order_alpha = 0.0
        self.last_cocoa = 0.0
        self.last_milk = None
        self.last_dp = None
        self._last_customer = None
        self.cup = Cup(DRINKS[self.drink]["cup"], self.machine.cup_cx, self.machine.cup_base)
        self.session = None
        self.result = None
        self.last_drink = self.drink
        self.last_art = None
        self.contents = {"water": 0.0, "milk": 0.0, "foam": 0.0, "syrup": 0.0}
        self.syrup_kind = "choc"
        self.topping = {}                        # 杯面配料：cocoa／whip／caramel（0–1）
        self.icecream = None                     # 阿芙佳朵的冰淇淋球
        self.ice = []
        self.condense = 0.0
        self.mix_t = 0.0
        self.mix_clock = 0.0
        self.vortex = 0.0
        self.frother_fill = 0.42
        self.wand_angle = 0.0
        self.art_alpha = 0.0
        self.art_show_until = 0.0

        self.ui = pick_family(("Microsoft JhengHei UI", "Microsoft JhengHei", "PingFang TC",
                               "Noto Sans CJK TC", "Noto Sans TC"), "Sans Serif")
        self.mono = pick_family(("Consolas", "Menlo", "DejaVu Sans Mono"), "Monospace")

        self.sound = SoundBank()
        self.sound.master = self.cfg.get("volume", 0.65)
        self.sound.set_on(self.cfg.get("sound", True))

        # 畫面本身是子元件，放在外層承載視窗（host.py）裡；視窗化模式由 paint_window_backdrop 畫不透明背景
        self.setMouseTracking(True)
        self.host = None
        self.apply_scale()
        scr = QApplication.primaryScreen().availableGeometry()
        x = self.cfg.get("x", scr.right() - self.width() - 30)
        y = self.cfg.get("y", scr.bottom() - self.height() - 30)
        if "y" in self.cfg and self.cfg.get("top_pad") != TOP_PAD:
            y -= (TOP_PAD - self.cfg.get("top_pad", 0)) * self.scale_f   # 舊設定：讓咖啡機留在原位
        self.cfg["top_pad"] = TOP_PAD
        self.build_host(int(x), int(y), show=False)

        # 動態狀態
        self.shot = None
        self.workflow = None
        self.pf_used = self.cfg.get("pf_used", False)     # 把手裡有沒有上一杯的粉餅
        self.boiler = Boiler(self.params.temp)
        self.apply_traits()
        self.boiler.temp = self.params.temp - WARMUP
        self.warming = True
        self._last_set = self.params.temp
        self.gauge, self.gauge_v = 0.0, 0.0
        self.stream = [{"head": 0.0, "tail": 0.0} for _ in self.machine.spouts]
        self.last_flow = 0.0
        self.drops, self.splash, self.ripples, self.steam, self.bubbles = [], [], [], [], []
        self.crema_h = 0.0
        self.film_h = 0.0
        self.swirl = 0.0
        self.anim_t = 0.0
        self.idle_since = time.perf_counter()
        self.next_idle_event = time.perf_counter() + random.uniform(20, 40)
        self.barista = Barista()
        self.card_alpha = 0.0
        self.hover = False
        self.hover_since = 0.0
        self._ripple_clock = 0.0
        self._log_clock = 0.0
        self._last_relay = 0.0
        self._press = None
        self._frame = None
        self.settings_dlg = None
        rnd = random.Random(42)
        self.speckles = [(math.sqrt(rnd.random()), rnd.random() * 6.283, rnd.uniform(0.5, 1.6),
                          rnd.random() < 0.6) for _ in range(80)]
        self.update_light(force=True)

        self.icon = load_icon()
        self.host.setWindowIcon(self.icon)
        self.build_menu()
        self.build_tray()
        self._last_tip_ms = 0
        self.clock = QElapsedTimer()
        self.clock.start()
        self.last_ms = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(FRAME_ACTIVE)

    # ───────────── 設定檔 ─────────────
    @staticmethod
    def load_config():
        return config.load()                 # 含舊版設定沿用與格式遷移（config.py）

    def save_config(self):
        self.cfg.update(params=asdict(self.params), x=self.host.geometry().x(), y=self.host.geometry().y(), auto=self.auto,
                        interval=self.interval, speed=self.speed, topmost=self.topmost, windowed=self.windowed,
                        scale=self.scale_f, sound=self.sound.user_on, volume=self.sound.master,
                        full_flow=self.full_flow, light_mode=self.light_mode, chart=self.chart_on,
                        pf_used=self.pf_used, machine=self.machine.key, bean_bag=self.bag, maintenance=self.maint,
                        drink=self.drink, drink_params=asdict(self.dp), order_mode=self.order_mode, lang=self.lang,
                        order_no=self.order_no)
        config.save(self.cfg)

    # ───────────── 視窗 ─────────────
    def build_host(self, x, y, show=True):
        """建立全新的外層視窗並把畫面搬進去（無邊框／視窗化、置頂切換都走這裡，避免殘留邊框）"""
        old = self.host
        host = HostWindow(self, self.windowed, self.topmost)
        if hasattr(self, "icon"):
            host.setWindowIcon(self.icon)
        self.setParent(host)
        self.move(0, 0)
        host.setFixedSize(self.size())
        host.setGeometry(x, y, self.width(), self.height())    # 以內容區域定位（不含標題列）
        self.host = host
        self.show()
        if old is not None:
            old.retired = True
            old.hide()
            old.close()
            old.deleteLater()
        if show:
            host.show()
            host.raise_()
            host.activateWindow()

    def rebuild_host(self):
        if self.host is None:
            return
        visible = self.host.isVisible()
        pos = self.host.geometry().topLeft()       # 以內容區域為準，切換時咖啡機不跳位
        self.build_host(pos.x(), pos.y(), show=visible)
        self.set_frame_interval(FRAME_ACTIVE)

    def set_windowed(self, v):
        self.windowed = v
        self.rebuild_host()
        self.save_config()
        self.update()

    def show_window(self):
        self.host.show()

    def apply_scale(self):
        self.setFixedSize(int(self.machine.scene_w * self.scale_f), int((WIN_H + TOP_PAD) * self.scale_f))
        if self.host is not None:
            self.host.setFixedSize(self.size())
        self.bg_layer = self.front_layer = None      # 下一次繪圖時重建
        self._frame = None
        self._bean_cache = None

    # ───────────── 選單 ─────────────
    def build_menu(self):
        old = getattr(self, "menu", None)
        if old is not None:
            old.deleteLater()
        m = QMenu(self)
        m.addAction(T("開始沖煮"), self.manual_brew)
        m.addAction(T("參數設定…"), self.open_settings)
        m.addSeparator()
        self.drink_menu = m.addMenu(T("飲品"))
        grp = QActionGroup(self.drink_menu)
        self.drink_actions = {}
        fd = festivals.festival_drink()
        order = list(DRINK_ORDER) + ([None, fd] if fd else [])
        for key in order:
            if key is None:
                self.drink_menu.addSeparator()
                continue
            name = T(DRINKS[key]["name"])
            if key == fd:
                name = T("季節限定：{name}", name=name)
            act = self.drink_menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(key == self.drink)
            act.triggered.connect(lambda _=False, k=key: self.set_drink(k))
            grp.addAction(act)
            self.drink_actions[key] = act
        self.machine_menu = m.addMenu(T("咖啡機"))
        grp = QActionGroup(self.machine_menu)
        self.machine_actions = {}
        for key, mach in MACHINES.items():
            act = self.machine_menu.addAction(T(mach.name))
            act.setCheckable(True)
            act.setChecked(key == self.machine.key)
            act.setToolTip(T(mach.traits.summary))
            act.triggered.connect(lambda _=False, k=key: self.set_machine(k))
            grp.addAction(act)
            self.machine_actions[key] = act
        self.machine_menu.setToolTipsVisible(True)
        self.art_menu = m.addMenu(T("拉花圖案"))
        grp = QActionGroup(self.art_menu)
        self.art_actions = {}
        for key, label in ART_CHOICES:
            act = self.art_menu.addAction(T(label))
            act.setCheckable(True)
            act.setChecked(key == self.dp.art)
            act.triggered.connect(lambda _=False, k=key: self.set_art(k))
            grp.addAction(act)
            self.art_actions[key] = act
        # 豆子：目前這包的資訊、開新包（選產地）
        self.bean_menu = m.addMenu(T("豆子"))
        self.bean_menu.aboutToShow.connect(self.fill_bean_menu)
        # 清潔保養
        self.maint_menu = m.addMenu(T("清潔保養"))
        self.maint_menu.aboutToShow.connect(self.fill_maint_menu)
        m.addAction(T("紀錄與收集冊…"), self.open_records)
        m.addSeparator()

        a = m.addAction(T("手動沖煮使用完整流程"))
        a.setCheckable(True)
        a.setChecked(self.full_flow)
        a.toggled.connect(lambda v: self.set_cfg("full_flow", v))
        a = m.addAction(T("自動模式（咖啡師自己調參、隨機飲品）"))
        a.setCheckable(True)
        a.setChecked(self.auto)
        a.toggled.connect(self.set_auto)
        self.act_auto = a          # 系統匣選單共用同一個動作，勾選狀態會同步
        a = m.addAction(T("顧客點單模式"))
        a.setCheckable(True)
        a.setChecked(self.order_mode)
        a.toggled.connect(self.set_order_mode)
        self.act_order = a

        def radio(title, options, current, setter):
            sub = m.addMenu(title)
            grp = QActionGroup(sub)
            for value, label in options:
                act = sub.addAction(label)
                act.setCheckable(True)
                act.setChecked(value == current if isinstance(value, str) else abs(value - current) < 1e-6)
                act.triggered.connect(lambda _=False, v=value: setter(v))
                grp.addAction(act)

        radio(T("自動沖煮間隔"), [(20, T("20 秒")), (60, T("1 分鐘")), (180, T("3 分鐘")), (600, T("10 分鐘"))],
              self.interval, lambda v: self.set_cfg("interval", v))
        radio(T("播放速度"), [(1.0, T("1×（真實時間）")), (2.0, "2×"), (4.0, "4×")],
              self.speed, lambda v: self.set_cfg("speed", v))
        m.addSeparator()

        a = m.addAction(T("聲音"))
        a.setCheckable(True)
        a.setChecked(self.sound.on)
        a.setEnabled(self.sound.enabled)
        a.toggled.connect(lambda v: (self.sound.set_on(v), self.save_config()))
        radio(T("音量"), [(0.3, T("小")), (0.65, T("中")), (1.0, T("大"))], self.sound.master,
              lambda v: (setattr(self.sound, "master", v), self.save_config()))
        radio(T("環境光"), [("auto", T("依時間變化")), ("day", T("白天")), ("dusk", T("黃昏")), ("night", T("夜晚"))],
              self.light_mode, self.set_light_mode)
        a = m.addAction(T("滑鼠停留顯示萃取曲線"))
        a.setCheckable(True)
        a.setChecked(self.chart_on)
        a.toggled.connect(lambda v: self.set_cfg("chart_on", v))
        radio(T("大小"), [(0.8, "80%"), (1.0, "100%"), (1.25, "125%"), (1.5, "150%")],
              self.scale_f, self.set_scale)
        radio("Language", list(LANGS), self.lang, self.set_language)      # 不翻譯：看不懂目前語言也找得到
        a = m.addAction(T("視窗化顯示"))
        a.setCheckable(True)
        a.setChecked(self.windowed)
        a.toggled.connect(self.set_windowed)
        a = m.addAction(T("視窗置頂"))
        a.setCheckable(True)
        a.setChecked(self.topmost)
        a.toggled.connect(self.set_topmost)
        m.addSeparator()
        a = m.addAction(T("縮到系統匣"), self.hide_to_tray)
        a.setEnabled(QSystemTrayIcon.isSystemTrayAvailable())
        m.addAction(T("關於 Café Desk…"), self.open_about)
        m.addAction(T("結束"), self.quit_app)
        self.menu = m

    def build_tray(self):
        self.tray = None
        self._tray_hint_shown = False
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(self.icon, self)
        tray.setToolTip("Café Desk")
        tm = QMenu()
        tm.addAction(T("顯示咖啡機"), self.restore_from_tray)
        tm.addAction(T("開始沖煮"), self.manual_brew)
        tm.addAction(self.act_auto)
        tm.addAction(self.act_order)
        tm.addSeparator()
        tm.addAction(T("關於 Café Desk…"), self.open_about)
        tm.addAction(T("結束"), self.quit_app)
        tray.setContextMenu(tm)
        tray.activated.connect(self.on_tray_activated)
        tray.show()
        self.tray_menu = tm        # 保留參考，避免被回收
        self.tray = tray

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible():
                self.hide_to_tray()
            else:
                self.restore_from_tray()

    def hide_to_tray(self):
        if not self.tray:
            return
        self.save_config()
        self.host.hide()
        self.sound.set_muted(True)
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.tray.showMessage("Café Desk", T("咖啡機在系統匣裡，點一下圖示就能叫回來。"),
                                  self.icon, 3000)

    def restore_from_tray(self):
        self.sound.set_muted(False)
        if self.host.isMinimized():
            self.host.showNormal()
        self.host.show()
        self.host.raise_()
        self.host.activateWindow()
        self.set_frame_interval(FRAME_ACTIVE)

    def update_tray_tip(self):
        if not self.tray:
            return
        if self.session:
            tip = T("{name}：{status}", name=T(DRINKS[self.session.drink]["name"]), status=self.session.status())
        elif self.result is None:
            tip = T("待機中")
        else:
            r = self.result
            tip = T("上一杯{name} {score:.0f} 分 · {comment}", name=r.title or T(DRINKS[r.drink]["name"]),
                    score=r.score, comment=r.comment)
        if self.order is not None and self.order.state == "waiting":
            o = self.order
            tip += "\n" + T("訂單 #{no} {name}：{title}", no=o.no, name=T(o.name), title=o.title)
        elif self.auto and not self.busy() and not self.order_mode:
            tip += "\n" + T("自動模式：{sec} 秒後沖下一杯",
                             sec=max(0, int(self.interval - (time.perf_counter() - self.idle_since))))
        self.tray.setToolTip("Café Desk\n" + tip)

    def set_cfg(self, key, v):
        setattr(self, key, v)
        self.save_config()

    def set_auto(self, v):
        self.auto = v
        self.idle_since = time.perf_counter()
        self.save_config()

    def fill_bean_menu(self):
        menu = self.bean_menu
        menu.clear()
        b = self.bag
        info = menu.addAction(T("目前：{name}（{roast}）", name=T(beans.bag_name(b)), roast=T(beans.bag_roast(b))))
        info.setEnabled(False)
        info2 = menu.addAction(T("烘焙後第 {days} 天 · 剩 {g:.0f} g · {flavor}", days=beans.bag_age(b), g=b["left"],
                                 flavor=T(beans.bag_flavor(b))))
        info2.setEnabled(False)
        menu.addSeparator()
        sub = menu.addMenu(T("開一包新豆子"))
        for key, (name, roast, flavor, _) in beans.ORIGINS.items():
            act = sub.addAction(T("{name}（{roast}）", name=T(name), roast=T(roast)))
            act.setToolTip(T(flavor))
            act.triggered.connect(lambda _=False, k=key: self.open_bag(k))
        sub.setToolTipsVisible(True)
        act = menu.addAction(T("隨機開一包"), lambda: self.open_bag(random.choice(list(beans.ORIGINS))))
        if self.busy():
            sub.setEnabled(False)
            act.setEnabled(False)

    def fill_maint_menu(self):
        menu = self.maint_menu
        menu.clear()
        st = self.maint
        due = maintenance.due(st)
        units = {"backflush": T("已沖 {n:.0f} 杯"), "wand": T("已打 {n:.0f} 次奶"),
                 "drip": T("{n:.0f} ml"), "knock": T("{n:.0f} 個粉餅")}
        for key in maintenance.TASKS:
            label = T(maintenance.task_name(key, self.machine.traits))
            text = T("{name}（{roast}）", name=label, roast=units[key].format(n=st.get(key, 0)))
            if key in due:
                text = "⚠ " + text
            act = menu.addAction(text, lambda k=key: self.start_job(k))
            act.setEnabled(not self.busy())

    def open_records(self):
        if self.records_dlg is not None:
            self.records_dlg.close()
            self.records_dlg.deleteLater()
        self.records_dlg = RecordsDialog(self)
        self.records_dlg.show()
        self.records_dlg.raise_()

    def open_about(self):
        if self.about_dlg is not None:             # 每次重建：語言與檔案狀態都是最新的
            self.about_dlg.close()
            self.about_dlg.deleteLater()
        self.about_dlg = AboutDialog(self)
        self.about_dlg.show()
        self.about_dlg.raise_()
        self.about_dlg.activateWindow()

    def set_art(self, v):
        self.dp.art = v
        if v in self.art_actions:
            self.art_actions[v].setChecked(True)
        if self.settings_dlg is not None:
            self.settings_dlg.sync_art()
        self.save_config()

    def set_order_mode(self, v):
        self.order_mode = v
        if not v and self.order is not None and self.order.state != "making":
            self.order = None
        self.next_order_at = time.perf_counter() + 1.5
        self.idle_since = time.perf_counter()
        self.save_config()

    def set_language(self, v):
        """切換介面語言：重建右鍵選單、系統匣選單與設定視窗"""
        if v == self.lang:
            return
        self.lang = v
        set_lang(v)
        self.build_menu()
        if self.tray:
            self.tray.hide()
            self.tray.deleteLater()
        self.build_tray()
        if self.settings_dlg is not None:
            visible = self.settings_dlg.isVisible()
            self.settings_dlg.close()
            self.settings_dlg.deleteLater()
            self.settings_dlg = None
            if visible:
                self.open_settings()
        self.save_config()
        self.update()

    def set_light_mode(self, v):
        self.light_mode = v
        self.update_light(force=True)
        self.save_config()
        self.update()

    def set_topmost(self, v):
        self.topmost = v
        self.rebuild_host()
        self.save_config()

    def set_scale(self, v):
        self.scale_f = v
        self.apply_scale()
        self.save_config()

    def quit_app(self):
        self.save_config()
        self.sound.stop_all()
        if self.tray:
            self.tray.hide()
        QApplication.quit()

    def open_settings(self):
        if self.settings_dlg is None:
            self.settings_dlg = SettingsDialog(self)
        self.settings_dlg.show()
        self.settings_dlg.raise_()

    # ───────────── 滑鼠 ─────────────
    def logical(self, e):
        """滑鼠位置換成場景座標（扣掉上方透明區）"""
        pos = e.position()
        return pos.x() / self.scale_f, pos.y() / self.scale_f - TOP_PAD

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.menu.exec(e.globalPosition().toPoint())
            return
        if e.button() == Qt.LeftButton:
            self._press = (e.globalPosition().toPoint(), self.host.pos(), self.logical(e))
            self._moved = False

    def mouseMoveEvent(self, e):
        x, y = self.logical(e)
        over = _inside(x, y, self.machine.hover_area)
        if over and not self.hover:
            self.hover_since = time.perf_counter()
        self.hover = over
        if not self._press:
            return
        g0, p0, _ = self._press
        d = e.globalPosition().toPoint() - g0
        if abs(d.x()) + abs(d.y()) > 4:
            self._moved = True
        if self._moved:
            self.host.move(p0 + d)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or not self._press:
            return
        if self._moved:
            self.save_config()
        else:
            x, y = self._press[2]
            m = self.machine
            if _inside(x, y, m.machine_hit) or _inside(x, y, m.grinder_hit):
                self.manual_brew()
        self._press = None

    def leaveEvent(self, _):
        self.hover = False

    # ───────────── 沖煮控制 ─────────────
    def brewing(self):
        return self.shot is not None and self.shot.phase != "done"

    def busy(self):
        return self.session is not None or self.workflow is not None or self.brewing() or self.job is not None

    def cup_volume(self):
        """杯中內容物總量（g）：決定液面高度；冰塊被液體淹到的部分也佔體積"""
        c = self.contents
        liquid = (self.shot.weight if self.shot else 0.0) + c["water"] + c["milk"] + c["syrup"]
        ice = sum(1 for cube in self.ice if cube["landed"]) * ICE_VOL * clamp(liquid / 60, 0, 1)
        ic = self.icecream
        melted = ic["g"] * ic["melt"] * 0.8 if ic else 0.0       # 冰淇淋融化成液體的部分
        return liquid + c["foam"] + ice + melted

    def scale_weight(self):
        """磅秤讀數：杯中所有東西的重量"""
        c = self.contents
        ic = self.icecream
        return ((self.shot.weight if self.shot else 0.0) + c["water"] + c["milk"] + c["syrup"] + len(self.ice) * 14
                + (ic["g"] if ic and ic["landed"] else 0.0))

    def set_drink(self, key):
        self.drink = key
        if not self.busy():
            self.reset_cup(key)
        if self.settings_dlg is not None and self.settings_dlg.drink.currentData() != key:
            self.settings_dlg.sync_drink()
        self.save_config()

    def reset_cup(self, drink):
        """換上這個飲品的空杯子"""
        self.cup = Cup(DRINKS[drink]["cup"], self.machine.cup_cx, self.machine.cup_base)
        self.contents = {"water": 0.0, "milk": 0.0, "foam": 0.0, "syrup": 0.0}
        self.topping = {}
        self.icecream = None
        self.ice = []
        self.condense = 0.0
        self.mix_t = 0.0
        self.shot = None
        self.result = None
        self.last_drink = drink
        self.last_art = None
        self.last_milk = None
        self.steam.clear()
        self.bubbles.clear()
        self.crema_h = self.film_h = 0.0
        self.update()

    def drop_icecream(self, grams, x, y):
        """阿芙佳朵：冰淇淋球從勺子掉進杯裡（機身座標）"""
        r = 23.0 * (grams / 70) ** (1 / 3)
        cup = self.cup
        self.icecream = {"g": grams, "r": r, "x": x, "y": y, "vy": 0.0, "landed": False, "melt": 0.0,
                         "rest": cup.liquid_bottom - r * 0.78, "rot": random.uniform(0, 6.28)}
        self.set_frame_interval(FRAME_ACTIVE)

    def apply_traits(self):
        t = self.machine.traits
        self.boiler.HEAT = t.boiler_heat
        self.boiler.DRAW = t.boiler_draw

    def set_machine(self, key):
        if key == self.machine.key:
            return
        if self.busy():                      # 沖煮中不能換機器
            self.machine_actions[self.machine.key].setChecked(True)
            return
        self.machine = MACHINES[key]
        self.apply_traits()
        self.stream = [{"head": 0.0, "tail": 0.0} for _ in self.machine.spouts]
        self.wand_angle = 0.0
        self.reset_cup(self.drink)
        self.apply_scale()
        self.save_config()
        self.set_frame_interval(FRAME_ACTIVE)

    def start_session(self, drink, full_flow, dp=None, order=None):
        if self.busy():
            return
        self.sync_bag()
        from .drinks import shot_params
        need = shot_params(drink, self.params)[0].dose
        if self.bag["left"] < need:                  # 豆子不夠：自動模式自己開新包，手動就提醒
            if self.auto:
                self.open_bag(None)
            else:
                self.show_notice(T("豆子用完了，右鍵「豆子」開一包新的"))
                self.sound.once("ding_lo", 0.4)
                return False
        if drink in self.drink_actions:
            self.drink_actions[drink].setChecked(True)
        self.drink = drink
        self.reset_cup(drink)
        dp = dp or self.dp
        if is_milk(drink) and self.machine.traits.milk == "frother":
            self.frother_fill = clamp(0.42 * milk_plan(drink, dp)[0] / 150, 0.08, 0.6)
        self.session = Session(self, drink, full_flow, dp)
        if order is not None:
            self.session.order = order
            order.state, order.t = "making", 0.0
        self.sound.once("click", 0.4)
        self.set_frame_interval(FRAME_ACTIVE)
        return True

    def finish_session(self):
        ss = self.session
        self.session = None
        if is_milk(ss.drink):
            self.maint["wand"] += 1
        pen, notes = maintenance.penalty(self.maint, is_milk(ss.drink))
        if pen > 0:                                    # 太久沒清潔：扣分並在評語提醒
            r = ss.result
            words = [T(maintenance.task_name(n, self.machine.traits)) for n in notes]
            ss.result = type(r)(r.drink, max(0.0, r.score - pen),
                                T("{comment} · 該{task}了", comment=r.comment, task=T("、").join(words)), r.milk, r.title)
        self.result = ss.result
        self.last_drink = ss.drink
        self.last_cocoa = ss.cocoa
        if ss.order is not None:
            o = ss.order
            orders.finish(o, ss, ss.result)
            r = ss.result
            self.result = type(r)(r.drink, o.score, T("{name}：{text}", name=T(o.name), text=o.reaction), r.milk, o.title)
        self.last_dp = ss.dp
        self.last_milk = ss.milk
        if ss.milk is not None:
            t = self.topping
            self.last_art = (ss.milk.art, 1.0, ss.milk.art_q, ss.art_seed, dict(t))
            self.art_show_until = time.perf_counter() + 6
            self.frother_fill = 0.04 if self.machine.traits.milk == "frother" else self.frother_fill
        self.idle_since = time.perf_counter()
        self.sound.once("ding_hi" if self.result.score >= 80 else "ding_lo", 0.55)
        self.record_cup(ss)
        self.save_config()

    def record_cup(self, ss):
        """寫進每日紀錄與收集冊，檢查成就"""
        r, m, sh = self.result, ss.milk, self.shot
        cup = {"drink": ss.drink, "title": r.title or ss.drink, "score": r.score, "comment": r.comment,
               "machine": self.machine.key, "milk": ss.dp.milk_kind if (m is not None or ss.drink == "iced_latte") else None,
               "origin": self.bag["origin"], "bean_age": sh.p.bean_age if sh else 0, "dose": sh.p.dose if sh else 0,
               "festival": DRINKS[ss.drink].get("festival")}
        if m is not None:
            cup.update(art=m.art, art_q=m.art_q, seed=ss.art_seed, art_note=m.art_note)
        if ss.order is not None:
            cup.update(order=True, mods=len(ss.order.mods), match=ss.order.match)
        new = self.stats.record(cup, [k for k in DRINKS if k not in FESTIVAL_DRINKS])
        self.announce(new)
        self.stats.save()

    def announce(self, keys):
        names = {k: n for k, n, _ in ACHIEVEMENTS}
        now = time.perf_counter()
        for i, k in enumerate(keys):
            start = max(now, self.toasts[-1][2] if self.toasts else now) + (0.6 if i or self.toasts else 0.8)
            self.toasts.append((T("成就解鎖：{name}", name=T(names[k])), start, start + 4.0))
        if keys:
            self.sound.once("ding_hi", 0.45)
            self.set_frame_interval(FRAME_AMBIENT)

    def show_notice(self, text, sec=5.0):
        self.notice = (text, time.perf_counter() + sec)
        self.set_frame_interval(FRAME_AMBIENT)

    # ───────────── 豆子 ─────────────
    def sync_bag(self):
        """沖煮參數的烘焙度、產地、養豆天數跟著目前這包豆子（養豆天數依真實日期）"""
        b = self.bag
        self.params.roast = beans.bag_roast(b)
        self.params.origin = b["origin"]
        self.params.bean_age = float(beans.bag_age(b))
        self.hopper = clamp(b["left"] / b["size"], 0.0, 1.0)

    def open_bag(self, origin):
        if self.busy() and origin is not None:
            return
        self.bag = beans.new_bag(origin)
        self.sync_bag()
        if self.auto or origin is None:
            self.barista.shake_up(self.params)
        self.sound.once("tap", 0.4)
        self.show_notice(T("開了一包新豆子：{name}（{roast}，{flavor}）", name=T(beans.bag_name(self.bag)),
                           roast=T(beans.bag_roast(self.bag)), flavor=T(beans.bag_flavor(self.bag))))
        if self.settings_dlg is not None:
            self.settings_dlg.sync_bean()
        self.save_config()

    # ───────────── 清潔保養 ─────────────
    def start_job(self, kind):
        if self.busy():
            return False
        self.job = maintenance.Job(kind)
        if kind == "wand":
            if self.machine.traits.milk == "wand":
                self.purge_wand()
                self.sound.once("hiss", 0.45)
            else:
                self.frother_fill = 0.0
                self.sound.once("click", 0.4)
        elif kind == "drip":
            self.sound.once("tap", 0.4)
        elif kind == "knock":
            self.sound.once("knock", 0.5)
        elif kind == "backflush":
            self.sound.once("click", 0.4)
        self.set_frame_interval(FRAME_ACTIVE)
        return True

    def finish_job(self):
        kind = self.job.kind
        self.job = None
        self.maint[kind] = 0.0
        if kind == "wand" and self.machine.traits.milk == "frother":
            self.frother_fill = 0.42
        self.sound.once("ding_hi", 0.3)
        self.idle_since = time.perf_counter()
        self.announce(self.stats.record_clean(kind))
        self.stats.save()
        self.save_config()

    def job_status(self):
        j = self.job
        if j.kind == "backflush":
            return T("逆洗沖煮頭（第 {n}/5 次）…", n=j.cycle)
        if j.kind == "wand":
            return T("清洗奶泡機…") if self.machine.traits.milk == "frother" else T("清潔蒸氣管…")
        return T(maintenance.TASKS[j.kind][3])

    def pick_auto_drink(self):
        """自動模式：隨機選飲品；咖啡師每杯手感不同，打奶溫度與奶泡量在設定值附近小幅變動"""
        weights = festivals.adjust_weights(AUTO_WEIGHTS, DRINKS)
        keys = list(weights)
        drink = random.choices(keys, weights=[weights[k] for k in keys])[0]
        dp = self.dp.copy()
        dp.milk_temp = clamp(dp.milk_temp + random.gauss(0, 2.5), 45, 72)
        dp.foam = clamp(dp.foam + random.gauss(0, 5), 5, 70)
        dp.capp_foam = clamp(dp.capp_foam + random.gauss(0, 5), 30, 90)
        dp.flat_foam = clamp(dp.flat_foam + random.gauss(0, 3), 3, 40)
        return drink, dp

    def manual_brew(self):
        """手動沖煮：依設定跑完整流程或直接萃取"""
        if self.busy():
            return
        if self.order_mode:
            self.make_order(self.full_flow)
            return
        self.start_session(self.drink, self.full_flow)

    def make_order(self, full_flow):
        """點單模式：照目前的訂單做（還沒有訂單就叫下一位客人）"""
        o = self.order
        if o is None or o.state in ("done", "leaving"):
            self.new_order()
            o = self.order
        if o.state != "waiting":
            return
        if not self.start_session(o.drink, full_flow, orders.order_params(o, self.dp), order=o):
            return

    def new_order(self):
        self.order_no += 1
        self.order = orders.make_order(self.order_no, last_name=self._last_customer)
        self._last_customer = self.order.name
        self.sound.once("ding_hi", 0.25)
        self.set_frame_interval(FRAME_AMBIENT)

    def start_brew(self, params=None, style=None, preset=False):
        if self.brewing():
            return
        self.shot = Shot((params or self.params).copy(), self.machine.traits, style)
        self.shot.preset = preset
        self.bag["left"] = max(0.0, self.bag["left"] - self.shot.p.dose)     # 用掉這杯的豆子
        self.hopper = clamp(self.bag["left"] / self.bag["size"], 0.0, 1.0)
        self.maint["backflush"] += 1
        self.maint["drip"] += maintenance.DRIP_PER_SHOT
        self.stream = [{"head": 0.0, "tail": 0.0} for _ in self.machine.spouts]
        self.drops.clear()
        self.splash.clear()
        self.ripples.clear()
        self.bubbles.clear()
        self.crema_h = self.film_h = 0.0
        self._log_clock = 0.0
        self.pf_used = True
        self.sound.once("click", 0.5)
        self.set_frame_interval(FRAME_ACTIVE)

    def barista_dial_in(self):
        self.barista.dial_in(self.params, self.shot)

    # ───────────── 主迴圈 ─────────────
    def tick(self):
        ms = self.clock.elapsed()
        dt = min(0.5, (ms - self.last_ms) / 1000.0)
        self.last_ms = ms
        self.anim_t += dt
        while dt > 1e-6:                     # 切成小步推進，幀率高低都得到同樣的模擬結果
            step = min(SIM_STEP, dt)
            self.step(step, step * self.speed)
            dt -= step

        # 聲音
        s = self.shot
        if (s and s.phase == "brew") or (self.job and self.job.pumping):
            self.sound.loop("pump", 0.10 + 0.45 * clamp(self.gauge / 9, 0, 1.2))
        else:
            self.sound.loop("pump", 0.0)
        stream_vis = any(st["head"] > 0 and st["tail"] < 0.9 for st in self.stream)
        pour_vol = clamp(self.last_flow / 2.4, 0, 1) * 0.4 if stream_vis else 0.0
        self.sound.loop("grinder", 0.45 if (self.workflow and self.workflow.grinding) else 0.0)
        ss = self.session
        steaming = bool(ss and ss.stage_name == "steam" and self.machine.traits.milk == "wand"
                        and getattr(ss.stage, "phase", "") == "run")
        self.sound.loop("steam", 0.35 if steaming else 0.0)
        self.sound.loop("chirp", 0.3 if (steaming and ss.stretching) else 0.0)
        self.sound.loop("frother", 0.4 if (ss and ss.frother_on) else 0.0)
        vessel_pour = bool(ss and ss.vessel and ss.vessel.get("pour", 0) > 0)
        if vessel_pour:
            pour_vol = max(pour_vol, 0.3)
        self.sound.loop("pour", pour_vol)
        if ms - self._last_tip_ms > 500:
            self._last_tip_ms = ms
            self.update_tray_tip()
            self.update_light()
        if self.isVisible():
            self.update()
        self.set_frame_interval(self.wanted_interval())

    def step(self, dt, sdt):
        """推進一個模擬子步：dt 是真實時間，sdt 是乘上播放速度後的沖煮時間"""
        now = time.perf_counter()

        # 完整流程（備粉）
        wf = self.workflow
        if wf:
            wf.update(sdt)
            for ev in wf.events:
                self.on_workflow_event(ev)
            wf.events.clear()

        s = self.shot
        if s and s.phase != "done":
            s.update(sdt)
            self._log_clock += sdt
            if self._log_clock >= LOG_STEP or not s.log:
                self._log_clock = 0.0
                s.log.append((s.t, self.gauge, s.flow, s.weight))
            if s.phase == "done":
                self.mix_clock = now

        # 飲品流程
        ss = self.session
        if ss:
            ss.update(sdt)
            for ev in ss.events:
                self.on_session_event(ev)
            ss.events.clear()
            if ss.done:
                self.finish_session()
        if self.job:
            self.job.update(sdt)
            if self.job.done:
                self.finish_job()
        if self.auto and not self.busy() and now - self.idle_since >= min(self.interval, 8.0):
            todo = maintenance.due(self.maint)
            if todo:                                     # 自動模式：該清的先清
                self.start_job(todo[0])
        if self.order_mode:
            self.update_order(dt, now)
        elif self.auto and not self.busy() and now - self.idle_since >= self.interval:
            self.barista_dial_in()
            drink, dp = self.pick_auto_drink()
            self.save_config()
            self.start_session(drink, False, dp)
        s = self.shot

        # 鍋爐水溫
        flow = s.flow if (s and s.phase in ("brew", "tail")) else 0.0
        if self.params.temp - self._last_set > 3:          # 設定水溫大幅調高：重新預熱
            self.warming = True
        self._last_set = self.params.temp
        if self.warming and self.boiler.temp >= self.params.temp - 0.5:
            self.warming = False
        mode = self.session.boiler_mode if self.session else self.idle_boiler_mode()
        setpoint = self.machine.traits.steam_temp if mode == "steam" else self.params.temp
        if mode != "cool" and self.boiler.update(sdt, setpoint, flow) and self.isVisible() \
                and now - self._last_relay > 2:
            self._last_relay = now
            self.sound.once("relay", 0.12)

        # 壓力錶：彈簧阻尼，會稍微衝過頭再回穩
        target = s.pressure_target() if s else 0.0
        if self.job and self.job.pumping:                # 逆洗：盲碗加壓到 9 bar 再洩掉
            target = 9.0
        if s and s.phase == "brew" and s.t > s.t_drip:
            target += random.uniform(-1, 1) * (0.05 + s.res.channeling * 0.9)
        self.gauge_v += ((target - self.gauge) * 38 - self.gauge_v * 8) * dt
        self.gauge = max(0.0, self.gauge + self.gauge_v * dt)

        # 流柱生長／收回（收尾時流速遞減，低於門檻才斷成水滴）
        on = bool(s and s.phase in ("brew", "tail") and s.flow >= 0.55)
        if s and s.flow > 0:
            self.last_flow = s.flow
        for st in self.stream:
            if on:
                st["head"] = min(1.0, st["head"] + sdt * 6)
                st["tail"] = 0.0
            elif st["head"] > 0:
                st["tail"] = min(1.0, st["tail"] + sdt * 5)
                if st["tail"] >= 1.0:
                    st["head"] = st["tail"] = 0.0

        self.update_crema(dt, sdt)
        self.film_h = max(self.film_h, self.crema_h * 0.8)
        self.update_particles(dt, sdt)
        self.update_drink_fx(dt, sdt)

        # 待機時偶爾放氣或滴水
        if not self.busy() and self.isVisible() and now >= self.next_idle_event:
            self.idle_event()
            self.next_idle_event = now + random.uniform(25, 60)

        # 曲線卡片淡入淡出
        show_card = (self.chart_on and self.hover and not self._press
                     and now - self.hover_since > 0.35)
        self.card_alpha += ((1.0 if show_card else 0.0) - self.card_alpha) * min(1.0, dt * 8)
        ss = self.session
        pouring_art = bool(ss and ss.milk is not None and (
            (ss.stage_name == "pour" and getattr(ss.stage, "art", False)) or ss.stage_name in ("whip", "cocoa", "caramel")
            or (ss.drink == "caramel_macchiato" and ss.stage_name == "brew")))
        show_art = (pouring_art or now < self.art_show_until or
                    (show_card and (self.last_art is not None or (ss and ss.milk is not None))))
        self.art_alpha += ((1.0 if show_art else 0.0) - self.art_alpha) * min(1.0, dt * 6)

    def update_order(self, dt, now):
        """點單模式：客人來點單 →（自動模式下咖啡師接單）→ 完成後顯示反應 → 離開 → 下一位"""
        o = self.order
        if o is not None:
            o.t += dt
        if o is None:
            if not self.busy() and now >= self.next_order_at:
                self.new_order()
        elif o.state == "waiting":
            if self.auto and not self.busy() and o.t >= 2.5:
                self.barista_dial_in()
                self.save_config()
                self.make_order(False)
        elif o.state == "done" and o.t >= orders.SHOW_DONE:
            o.state, o.t = "leaving", 0.0
        elif o.state == "leaving" and o.t >= 0.7:
            self.order = None
            gap = self.interval if self.auto else 6.0
            self.next_order_at = now + gap
            self.idle_since = now
        show = o is not None and not (o.state == "leaving")
        self.order_alpha += ((1.0 if show else 0.0) - self.order_alpha) * min(1.0, dt * 6)

    def idle_boiler_mode(self):
        """單鍋爐打完奶，閒置時鍋爐仍停在蒸氣溫度，直到下一杯先降溫"""
        t = self.machine.traits
        if t.steam_heatup and self.boiler.temp > self.params.temp + 3 and is_milk(self.last_drink):
            return "hold"
        return "brew"

    def on_session_event(self, ev):
        if ev == "pour_start":
            self.sound.once("tap", 0.2)
        elif ev == "steam_start":
            self.sound.once("hiss", 0.35)
        elif ev == "purge":
            self.purge_wand()
            self.sound.once("hiss", 0.45)
        elif ev == "frother_start":
            self.sound.once("click", 0.4)
        elif ev == "frother_stop":
            self.sound.once("beep", 0.4)
        elif ev == "vent":
            vx, vy = self.machine.vent
            for i in range(5):
                self.steam.append({"x": vx + random.uniform(-1, 1), "y": vy - 2, "vx": random.uniform(4, 14),
                                   "vy": random.uniform(-38, -24), "age": -i * 0.05,
                                   "life": random.uniform(1.0, 1.6), "ph": random.random() * 6.28,
                                   "boost": 70, "s0": 2, "s1": 12})
            self.sound.once("hiss", 0.2)

    def on_workflow_event(self, ev):
        wf = self.workflow
        if ev == "lock":
            self.sound.once("lock", 0.5)
        elif ev in ("knock", "knock2"):
            self.sound.once("knock", 0.55)
            if ev == "knock":
                self.maint["knock"] += 1
        elif ev == "thud":
            self.sound.once("tamp", 0.25)
        elif ev in ("tap", "tap2"):
            self.sound.once("tap", 0.45)
        elif ev == "tamp":
            self.sound.once("tamp", 0.6)
        elif ev == "grind_start":
            pass                                # 豆子在萃取開始時從這包扣掉（start_brew）

    # ───────────── 自動幀率 ─────────────
    def wanted_interval(self):
        if not self.isVisible() or self.host.isMinimized():
            return FRAME_HIDDEN
        if (self.busy() or self.drops or self.splash or self.ripples
                or any(st["head"] > 0 for st in self.stream)):
            return FRAME_ACTIVE
        if self.drink_kind() == "espresso_tonic" and self.contents["water"] > 0:
            return FRAME_AMBIENT                   # 通寧水的氣泡一直往上冒
        if self.icecream and self.icecream["melt"] < 0.98 and self.shot:
            return FRAME_AMBIENT                   # 冰淇淋慢慢融化
        card_moving = (0.01 < self.card_alpha < 0.99 or (self.card_alpha > 0.5 and not self.hover)
                       or 0.01 < self.art_alpha < 0.99 or (self.art_alpha > 0.5 and not self.hover)
                       or any(not c["landed"] for c in self.ice)
                       or 0.01 < self.order_alpha < 0.99 or (self.order and self.order.state == "done")
                       or bool(self.toasts))                # 成就通知淡入淡出
        if (self.steam or self.bubbles or card_moving or (self.ice and self.mix_t < 60)
                or abs(self.gauge) > 0.02 or abs(self.gauge_v) > 0.05):
            return FRAME_AMBIENT
        return FRAME_IDLE

    def set_frame_interval(self, ms):
        if self.timer.interval() != ms:
            self.timer.setInterval(ms)

    # ───────────── 繪圖 ─────────────
    def portafilter_state(self):
        """把手位置與濾杯內容：流程中由流程決定，否則扣在沖煮頭上"""
        wf = self.workflow
        if not wf:
            gx, gy = self.machine.pf_group_scene
            return {"x": gx, "y": gy, "handle": HANDLE_FULL, "tilt": 0.0}, None, self.machine.tamper_rest
        contents = None
        if wf.name not in ("unlock", "lock"):
            contents = {"puck": wf.has_puck, "grounds": wf.ground_g, "dose": wf.p.dose,
                        "level": wf.level, "tamped": wf.tamped, "uneven": wf.unevenness}
        return wf.pf, contents, wf.tamper

    def paintEvent(self, _):
        dpr = self.devicePixelRatioF()
        key = (dpr, self.machine.key, self.cup.kind)
        if self.bg_layer is None or getattr(self, "_layer_key", None) != key:
            self._layer_key = key
            self.bg_layer = self.render_layer(self.paint_background, dpr)
            self.front_layer = self.render_layer(self.paint_front, dpr)
        w, h = int(self.width() * dpr), int(self.height() * dpr)
        if self._frame is None or self._frame.width() != w or self._frame.height() != h:
            self._frame = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
            self._frame.setDevicePixelRatio(dpr)
        self._frame.fill(Qt.transparent)

        s = self.scale_f
        fp = QPainter(self._frame)
        fp.setRenderHint(QPainter.Antialiasing)
        fp.setRenderHint(QPainter.SmoothPixmapTransform)
        fp.drawPixmap(QPointF(0, TOP_PAD * s), self.bg_layer)
        fp.scale(s, s)
        fp.translate(0, TOP_PAD)
        m = self.machine
        if m.traits.grinder == "external":
            self.paint_grinder_dynamic(fp)
        m.paint_dynamic_scene(self, fp)
        if m.traits.milk == "frother":
            self.paint_frother(fp)
        fp.save()
        fp.translate(m.mx, m.my)
        m.paint_dynamic(self, fp)
        self.paint_drip_water(fp)
        m.paint_needles(self, fp)
        self.paint_liquid(fp)
        self.paint_ice(fp)
        self.paint_streams(fp)
        self.paint_pour_stream(fp)
        self.paint_tool(fp)
        self.paint_particles(fp)
        fp.restore()
        pf, contents, tamper = self.portafilter_state()
        self.paint_portafilter(fp, pf, contents)
        fp.save()
        fp.translate(m.mx, m.my)
        m.paint_collar(self, fp, pf)           # 環座蓋住濾杯上緣：看起來是鎖進沖煮頭
        m.paint_overlay(self, fp)
        fp.restore()
        if self.workflow and self.workflow.puck:
            self.paint_puck(fp, self.workflow.puck)
        self.paint_tamper(fp, tamper)
        fp.resetTransform()
        fp.drawPixmap(QPointF(0, TOP_PAD * s), self.front_layer)
        fp.scale(s, s)
        fp.translate(m.mx, m.my + TOP_PAD)
        self.paint_condensation(fp)
        self.paint_steam(fp)
        self.paint_lcd(fp)
        fp.translate(-m.mx, -m.my)
        self.paint_vessel(fp, self.session.vessel if self.session else None)
        self.paint_ambient(fp)
        fp.end()

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.windowed:
            self.paint_window_backdrop(p)
        p.drawImage(0, 0, self._frame)
        p.scale(s, s)
        p.save()
        p.translate(0, TOP_PAD)
        self.paint_status(p)
        p.restore()
        self.paint_chart(p)
        self.paint_art_card(p)
        self.paint_order_card(p)
        self.paint_toasts(p)
        p.end()

    def render_layer(self, fn, dpr):
        pm = QPixmap(int(self.machine.scene_w * self.scale_f * dpr), int(WIN_H * self.scale_f * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(self.scale_f, self.scale_f)
        fn(p)
        p.end()
        return pm

    def paint_window_backdrop(self, p):
        """視窗化模式的背景：深色暖調漸層 + 檯面 + 暗角，取代桌面透出來的透明背景"""
        w, h, s = self.width(), self.height(), self.scale_f
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor("#2b2522"))
        g.setColorAt(0.75, QColor("#1b1715"))
        g.setColorAt(1, QColor("#120f0e"))
        p.fillRect(self.rect(), g)
        counter = (TOP_PAD + FLOOR) * s               # 檯面：磨豆機在後、咖啡機較靠前（底部較低）
        c = QLinearGradient(0, counter, 0, h)
        c.setColorAt(0, QColor("#4a3a30"))
        c.setColorAt(0.04, QColor("#3a2d25"))
        c.setColorAt(1, QColor("#1e1814"))
        p.fillRect(0, int(counter), w, h - int(counter), c)
        v = QRadialGradient(w / 2, h * 0.45, max(w, h) * 0.75)
        v.setColorAt(0.55, QColor(0, 0, 0, 0))
        v.setColorAt(1, QColor(0, 0, 0, 120))
        p.fillRect(self.rect(), v)

