"""主視窗：設定、選單、系統匣、滑鼠、模擬推進與繪圖排程"""
import datetime
import math
import random
import time
from dataclasses import asdict, fields

from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QPointF, QUrl
from PySide6.QtGui import (QPainter, QPixmap, QImage, QActionGroup, QLinearGradient, QRadialGradient, QColor,
                           QDesktopServices)
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QSystemTrayIcon

from . import config, update
from .gfx import pick_family
from .host import HostWindow
from .cups import Cup
from .drinks import (Session, DRINKS, DRINK_ORDER, DrinkParams, ICE_VOL, ART_CHOICES, ART_NEED,
                     MILK_KINDS, FESTIVAL_DRINKS, STATION_FAMILIES, is_milk, milk_plan, method_of)
from . import orders, beans, maintenance, festivals, brew
from .stats import Stats, ACHIEVEMENTS, TIER_OF, TIER_ICONS
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
from .render.station import StationRenderer
from .settings import SettingsDialog
from .sound import SoundBank, AMBIENCE
from .util import clamp
from .workflow import HANDLE_FULL

# 繪圖間隔（毫秒）：萃取中最順，閒置時省 CPU，縮到系統匣時不繪圖
FRAME_ACTIVE = 16      # 約 60 fps：萃取、完整流程、滴落、水花
FRAME_AMBIENT = 33     # 約 30 fps：蒸氣、指針回穩、氣泡破裂、卡片淡入淡出
FRAME_IDLE = 100       # 10 fps：只剩狀態列倒數與水溫微動
FADE_T = 0.6           # 換咖啡機／沖煮方式時，舊畫面淡出的秒數
SWITCH_PAUSE = 0.5     # 點單換了咖啡機／沖煮方式：漸變完再停這麼久才開始做
FRAME_HIDDEN = 250     # 縮到系統匣：只推進模擬（自動模式照常）
SIM_STEP = 0.05        # 模擬子步長（秒）：間隔拉長時切成多步，結果不受幀率影響
LOG_STEP = 0.1         # 萃取曲線取樣間隔（沖煮時間，秒）
WARMUP = 18.0          # 啟動時鍋爐比設定溫度低幾度，模擬預熱
UPDATE_DELAY = 10.0    # 啟動後幾秒才檢查新版本（不跟啟動搶時間）
UPDATE_RETRY = 3600.0  # 檢查失敗（沒網路）多久後再試；成功的話一天只查一次


def _inside(x, y, box):
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


class CafeDesk(QWidget, MachineRenderer, GrinderRenderer, LiquidRenderer, ParticleSystem, OverlayRenderer,
                   MilkRenderer, StationRenderer):
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
        self.windowed = self.cfg.get("windowed", True)    # 視窗化（預設）：一般視窗（標題列、工作列、不透明背景）；關掉是透明桌面擺件
        self.scale_f = self.cfg.get("scale", 1.0)
        self.light_mode = self.cfg.get("light_mode", "auto")
        self.chart_on = self.cfg.get("chart", True)
        self.machine = MACHINES.get(self.cfg.get("machine"), MACHINES[DEFAULT_MACHINE])
        self.drink = self.cfg.get("drink", "espresso")
        if self.drink not in DRINKS or (self.drink in FESTIVAL_DRINKS and self.drink != festivals.festival_drink()):
            self.drink = "latte" if self.drink in DRINKS else "espresso"
        self.method = method_of(self.drink)      # 沖煮方式：espresso／pourover／colddrip（跟著飲品）
        bag = self.cfg.get("bean_bag")
        self.bag = bag if (isinstance(bag, dict) and beans.valid_bag(bag)) else beans.new_bag("house")
        saved = self.cfg.get("maintenance", {})
        self.maint_all = {}                      # 每台咖啡機各自的清潔保養計數（self.maint 是目前這台的）
        for key in MACHINES:
            st = maintenance.default_state()
            got = saved.get(key) if isinstance(saved, dict) else None
            if isinstance(got, dict):
                st.update({k: v for k, v in got.items() if k in st})
            self.maint_all[key] = st
        self.job = None                          # 正在進行的清潔保養
        cold = self.cfg.get("cold_drip")
        self.cold = cold if brew.valid_batch(cold) else None    # 冰滴：背景慢慢滴的這一壺（brew.new_cold_batch）
        self.last_brew_res = None                # 上一杯手沖／冰滴的萃取結果（杯中顏色）
        self.brew_zoom = 0.0                     # 手沖／冰滴畫面拉近的程度（0＝全景，1＝只看沖煮器具）
        self._fade = None                        # 換咖啡機／沖煮方式的漸變：(舊畫面, 開始時間)
        self._switch_wait = None                 # 點單換了咖啡機／沖煮方式後的等待：[訂單, 剩幾秒]
        self.session = None
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
        self.auto_before_orders = self.cfg.get("auto_before_orders", self.auto)   # 開點單前的自動模式，關點單時還原
        if self.order_mode:
            self.auto = False                    # 顧客點單時咖啡師自己接單，自動模式關著（選項反灰）
        self.order = None                        # 目前的訂單
        self.order_no = int(self.cfg.get("order_no", 0))
        self.next_order_at = time.perf_counter() + 2.5
        self.queue = []                          # 營業模式：排在目前訂單後面的客人
        self.arrive_in = 3.0                     # 營業模式：下一位客人幾秒後到（模擬時間）
        self.rush = False                        # 營業模式：排滿 QUEUE_MAX 位後還沒有人離開（尖峰時刻成就）
        self.order_alpha = 0.0
        self.last_cocoa = 0.0
        self.last_milk = None
        self.last_dp = None
        self._last_customer = None
        self.cup = Cup(DRINKS[self.drink]["cup"], *self.cup_anchor())
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
        self.ambience = self.cfg.get("ambience")             # 環境音：None／cafe／rain
        if self.ambience not in AMBIENCE:
            self.ambience = None
        self.amb_level = self.cfg.get("amb_level", 0.3)
        self.break_min = self.cfg.get("break_min", 0)        # 休息提醒：每幾分鐘（0＝關閉）
        self.break_t = 0.0                                   # 距離上次提醒過了幾秒（真實時間，睡眠不算）
        self.update_check = self.cfg.get("update_check", True)
        self.update_job = None                               # 進行中的 update.Checker
        self._update_at = time.perf_counter() + UPDATE_DELAY
        latest = self.cfg.get("update_latest", "")
        self.update_info = ({"tag": latest, "url": update.RELEASES_URL}
                            if self.update_check and update.is_newer(latest) else None)

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
                        light_mode=self.light_mode, chart=self.chart_on,
                        pf_used=self.pf_used, machine=self.machine.key, bean_bag=self.bag, maintenance=self.maint_all,
                        drink=self.drink, drink_params=asdict(self.dp), order_mode=self.order_mode, lang=self.lang,
                        order_no=self.order_no, cold_drip=self.cold, auto_before_orders=self.auto_before_orders,
                        ambience=self.ambience, amb_level=self.amb_level, break_min=self.break_min,
                        update_check=self.update_check)
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
        self._scene_w = self.scene_width()          # 視窗寬度（手沖／冰滴也跟咖啡機一樣寬）
        self.setFixedSize(int(self._scene_w * self.scale_f), int((WIN_H + TOP_PAD) * self.scale_f))
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
        if self.update_info:                         # 有新版本：放在最上面
            m.addAction(T("⬆ 下載新版 {tag}…", tag=self.update_info["tag"]), self.open_update_page)
            m.addSeparator()
        m.addAction(T("開始沖煮"), self.manual_brew)
        m.addAction(T("參數設定…"), self.open_settings)
        m.addSeparator()
        self.method_menu = m.addMenu(T("沖煮方式"))
        grp = QActionGroup(self.method_menu)
        self.method_actions = {}
        for key, name in brew.METHODS.items():
            act = self.method_menu.addAction(T(name))
            act.setCheckable(True)
            act.setChecked(key == self.method)
            act.triggered.connect(lambda _=False, k=key: self.set_method(k))
            grp.addAction(act)
            self.method_actions[key] = act
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
        self.drink_menu = m.addMenu(T("飲品"))
        grp = QActionGroup(self.drink_menu)
        self.drink_actions = {}
        fd = festivals.festival_drink()
        order = list(DRINK_ORDER) + ([None, fd] if fd else [])
        for key in order:
            if key is not None and method_of(key) != self.method:
                continue                                 # 不是這個沖煮方式能做的飲品
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

        # 自動模式：開關＋沖煮間隔放在同一個子選單（間隔只對自動模式有用；顧客點單時整個反灰）
        self.auto_menu = m.addMenu(T("自動模式"))
        a = self.auto_menu.addAction(T("自動模式（照設定重複沖煮）"))
        a.setCheckable(True)
        a.setChecked(self.auto)
        a.setEnabled(not self.order_mode)        # 顧客點單時取消勾選、反灰
        a.toggled.connect(self.set_auto)
        self.act_auto = a          # 系統匣選單共用同一個動作，勾選狀態會同步
        self.auto_menu.addSeparator()
        grp = QActionGroup(self.auto_menu)
        for value, label in ((20, T("20 秒")), (60, T("1 分鐘")), (180, T("3 分鐘")), (600, T("10 分鐘"))):
            act = self.auto_menu.addAction(T("每 {t} 做一杯", t=label))
            act.setCheckable(True)
            act.setChecked(abs(value - self.interval) < 1e-6)
            act.triggered.connect(lambda _=False, v=value: self.set_cfg("interval", v))
            grp.addAction(act)
        a = m.addAction(T("顧客點單模式"))
        a.setCheckable(True)
        a.setChecked(self.order_mode)
        a.toggled.connect(self.set_order_mode)
        self.act_order = a
        self.update_menu_locks()

        # 休息提醒：每隔一段時間提醒起來休息，咖啡師順便做一杯
        self.break_menu = m.addMenu(T("休息提醒"))
        grp = QActionGroup(self.break_menu)
        for value in (0, 25, 45, 60):
            act = self.break_menu.addAction(T("不提醒") if value == 0 else T("每 {m} 分鐘", m=value))
            act.setCheckable(True)
            act.setChecked(value == self.break_min)
            act.triggered.connect(lambda _=False, v=value: self.set_break(v))
            grp.addAction(act)
        self.break_menu.addSeparator()
        self.act_break_reset = self.break_menu.addAction("", self.reset_break)
        self.break_menu.aboutToShow.connect(self.update_break_menu)

        def radio(title, options, current, setter, parent=m):
            sub = parent.addMenu(title)
            grp = QActionGroup(sub)
            for value, label in options:
                act = sub.addAction(label)
                act.setCheckable(True)
                act.setChecked(value == current if isinstance(value, str) else abs(value - current) < 1e-6)
                act.triggered.connect(lambda _=False, v=value: setter(v))
                grp.addAction(act)

        radio(T("播放速度"), [(1.0, T("1×（真實時間）")), (2.0, "2×"), (4.0, "4×")],
              self.speed, lambda v: self.set_cfg("speed", v))
        m.addSeparator()

        # 聲音：開關、音量、環境音放在同一個子選單
        snd = m.addMenu(T("聲音"))
        a = snd.addAction(T("開啟聲音"))
        a.setCheckable(True)
        a.setChecked(self.sound.on)
        a.setEnabled(self.sound.enabled)
        a.toggled.connect(lambda v: (self.sound.set_on(v), self.save_config()))
        radio(T("音量"), [(0.3, T("小")), (0.65, T("中")), (1.0, T("大"))], self.sound.master,
              lambda v: (setattr(self.sound, "master", v), self.save_config()), parent=snd)
        amb = snd.addMenu(T("環境音"))
        amb.setEnabled(self.sound.enabled)
        grp = QActionGroup(amb)
        for value, label in ((None, T("不播放")), ("cafe", T("咖啡廳")), ("rain", T("雨天"))):
            act = amb.addAction(label)
            act.setCheckable(True)
            act.setChecked(value == self.ambience)
            act.triggered.connect(lambda _=False, v=value: self.set_cfg("ambience", v))
            grp.addAction(act)
        amb.addSeparator()
        grp = QActionGroup(amb)
        for value, label in ((0.15, T("小聲")), (0.3, T("中等")), (0.5, T("大聲"))):
            act = amb.addAction(label)
            act.setCheckable(True)
            act.setChecked(abs(value - self.amb_level) < 1e-6)
            act.triggered.connect(lambda _=False, v=value: self.set_cfg("amb_level", v))
            grp.addAction(act)
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
        upd = m.addMenu(T("更新"))
        a = upd.addAction(T("每天自動檢查新版本"))
        a.setCheckable(True)
        a.setChecked(self.update_check)
        a.toggled.connect(self.set_update_check)
        upd.addAction(T("立即檢查更新"), lambda: self.check_update(manual=True))
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
        if self.break_min:
            tip += "\n" + T("休息提醒：還有 {m} 分鐘", m=max(1, math.ceil(self.break_min - self.break_t / 60)))
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

    @property
    def maint(self):
        """目前這台咖啡機的清潔保養計數（每台各自計算）"""
        return self.maint_all[self.machine.key]

    def business(self):
        """營業模式＝顧客點單：客人排隊、有耐心、咖啡師自己接單、算營業額（跟自動模式無關）"""
        return self.order_mode

    def update_menu_locks(self):
        """顧客點單時沖煮方式、咖啡機、飲品、拉花圖案、豆子、清潔保養都不能動（照訂單做，咖啡師自己清）；
        咖啡機、拉花圖案、清潔保養另外只在義式咖啡機畫面可用"""
        free = not self.order_mode
        espresso = self.method == "espresso"
        self.method_menu.setEnabled(free)
        self.machine_menu.setEnabled(free and espresso)
        self.drink_menu.setEnabled(free)
        self.art_menu.setEnabled(free and espresso)
        self.bean_menu.setEnabled(free)
        self.maint_menu.setEnabled(espresso and free)    # 點單時咖啡師該清就自己清
        self.auto_menu.setEnabled(free)              # 顧客點單時咖啡師自己接單，自動模式與間隔都用不到
        if self.settings_dlg is not None:
            self.settings_dlg.sync_lock()

    def set_order_mode(self, v):
        if not v:
            self._switch_wait = None
        """顧客點單＝營業模式：咖啡師自己接單，所以自動模式取消勾選並反灰；關掉時自動模式還原成開點單前的狀態"""
        if v and not self.order_mode:
            self.auto_before_orders = self.auto
        auto = False if v else self.auto_before_orders
        self.act_auto.blockSignals(True)
        self.act_auto.setChecked(auto)
        self.act_auto.setEnabled(not v)
        self.act_auto.blockSignals(False)
        self.order_mode = v
        if auto != self.auto:
            self.set_auto(auto)
        if not v and self.order is not None and self.order.state != "making":
            self.order = None
        if not v:
            self.queue.clear()
        self.arrive_in = 3.0
        self.next_order_at = time.perf_counter() + 1.5
        self.idle_since = time.perf_counter()
        self.update_menu_locks()
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
        over = self.method == "espresso" and _inside(x, y, self.machine.hover_area)
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
            if self.method != "espresso":
                if y >= 0:                                 # 手沖／冰滴：點畫面任何地方
                    self.manual_brew()
            elif _inside(x, y, m.machine_hit) or _inside(x, y, m.grinder_hit):
                self.manual_brew()
        self._press = None

    def leaveEvent(self, _):
        self.hover = False

    # ───────────── 沖煮控制 ─────────────
    def brewing(self):
        return self.shot is not None and self.shot.phase != "done"

    def busy(self):
        return (self.session is not None or self.workflow is not None or self.brewing() or self.job is not None
                or self._switch_wait is not None)

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

    def set_method(self, method):
        """換沖煮方式：義式咖啡機／手沖／冰滴各有自己的畫面與飲品"""
        if method == self.method:
            return
        if self.busy():
            self.method_actions[self.method].setChecked(True)
            return
        self.begin_fade()
        self.method = method
        if method_of(self.drink) != method:
            self.drink = next(k for k in DRINK_ORDER if k and method_of(k) == method)
        self.steam.clear()                               # 上一個畫面的蒸氣、水滴不要帶過去
        self.drops.clear()
        self.brew_zoom = 1.0 if self.brew_focus() else 0.0    # 切過去時直接是該有的遠近
        self.reset_cup(self.drink)
        self.apply_scale()
        self.build_menu()
        if self.settings_dlg is not None:
            self.settings_dlg.sync_drink()
        self.save_config()
        self.set_frame_interval(FRAME_ACTIVE)

    def set_drink(self, key):
        if method_of(key) != self.method and not self.busy():
            self.drink = key
            self.set_method(method_of(key))
            return
        self.drink = key
        if not self.busy():
            self.reset_cup(key)
        if self.settings_dlg is not None and self.settings_dlg.drink.currentData() != key:
            self.settings_dlg.sync_drink()
        self.save_config()

    def reset_cup(self, drink):
        """換上這個飲品的空杯子"""
        self.cup = Cup(DRINKS[drink]["cup"], *self.cup_anchor())
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
        self.begin_fade()
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
        dp = dp or self.dp
        if self.cold is not None and not self.cold.get("done") and brew.cold_progress(self.cold) >= 1:
            self.finish_cold()
        if drink == "cold_drip" and self.cold is not None and not self.cold.get("done"):
            self.show_notice(T("冰滴還在滴，大約 {m} 分鐘後好", m=brew.cold_remaining_min(self.cold)))
            self.sound.once("ding_lo", 0.3)
            return False
        need = self.brew_dose(drink, dp)
        if self.bag["left"] < need:                  # 豆子不夠：自動模式、營業中自己開新包，手動就提醒
            if self.auto or self.order_mode:
                self.open_bag(None)
            else:
                self.show_notice(T("豆子用完了，右鍵「豆子」開一包新的"))
                self.sound.once("ding_lo", 0.4)
                return False
        if method_of(drink) != self.method:
            self.set_method(method_of(drink))
        if drink in self.drink_actions:
            self.drink_actions[drink].setChecked(True)
        self.drink = drink
        self.reset_cup(drink)
        if is_milk(drink) and self.machine.traits.milk == "frother":
            self.frother_fill = clamp(0.42 * milk_plan(drink, dp)[0] / 150, 0.08, 0.6)
        self.session = Session(self, drink, full_flow, dp)
        if order is not None:
            self.session.order = order
            order.state, order.t = "making", 0.0
        self.sound.once("click", 0.4)
        self.set_frame_interval(FRAME_ACTIVE)
        return True

    def brew_dose(self, drink, dp):
        """這杯要用多少豆子"""
        if drink == "pour_over":
            return dp.po_dose
        if drink == "moka_pot":
            return dp.mk_dose
        if drink == "siphon":
            return dp.sy_dose
        if drink == "cold_drip":
            return 0.0 if self.cold is not None else dp.cd_dose
        from .drinks import shot_params
        return shot_params(drink, self.params)[0].dose

    def use_beans(self, grams):
        self.bag["left"] = max(0.0, self.bag["left"] - grams)
        self.hopper = clamp(self.bag["left"] / self.bag["size"], 0.0, 1.0)

    def finish_cold(self):
        """冰滴滴完：可以做 COLD_SERVINGS 杯"""
        self.cold.update(done=True, servings=brew.COLD_SERVINGS)
        self.show_notice(T("冰滴滴完了，可以做 {n} 杯冰滴咖啡", n=brew.COLD_SERVINGS))
        self.sound.once("ding_hi", 0.4)
        self.announce(self.stats.unlock("cold_drip"))
        self.save_config()

    def finish_session(self):
        ss = self.session
        self.session = None
        if ss.cold_setup:                              # 冰滴塔架好了：開始在背景滴
            p = self.params
            self.cold = brew.new_cold_batch(ss.dp, p.roast, p.bean_age, self.bag["origin"])
            self.show_notice(T("冰滴開始了，大約 {m} 分鐘後滴完（關掉程式也會繼續滴）", m=int(brew.COLD_DUR // 60)))
            self.idle_since = time.perf_counter()
            self.save_config()
            return
        if ss.family in STATION_FAMILIES:
            self.last_brew_res = ss.brew_res
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
        if ss.family == "colddrip" and self.cold is not None:
            self.cold["servings"] -= 1
            if self.cold["servings"] <= 0:              # 這壺倒完：收起冰滴塔
                self.cold = None
        self.save_config()

    def record_cup(self, ss):
        """寫進每日紀錄與收集冊，檢查成就"""
        r, m, sh = self.result, ss.milk, self.shot
        cup = {"drink": ss.drink, "title": r.title or ss.drink, "score": r.score, "comment": r.comment,
               "machine": self.machine.key if ss.family not in STATION_FAMILIES else None, "milk": ss.dp.milk_kind if (m is not None or ss.drink == "iced_latte") else None,
               "origin": self.bag["origin"], "bean_age": sh.p.bean_age if sh else 0, "dose": sh.p.dose if sh else 0,
               "festival": DRINKS[ss.drink].get("festival")}
        if ss.family == "pourover":
            cup.update(bean_age=self.params.bean_age, dose=ss.dp.po_dose, bloom_ok=brew.bloom_ok(ss.dp))
        elif ss.family in ("moka", "siphon"):
            cup.update(bean_age=self.params.bean_age, dose=self.brew_dose(ss.drink, ss.dp))
        elif ss.family == "colddrip" and self.cold is not None:
            cup.update(bean_age=self.cold["bean_age"], dose=self.cold["dose"] / brew.COLD_SERVINGS,
                       origin=self.cold["origin"])
        if m is not None:
            cup.update(art=m.art, art_q=m.art_q, seed=ss.art_seed, art_note=m.art_note)
        if ss.order is not None:
            o = ss.order
            cup.update(order=True, mods=len(o.mods), match=o.match, price=o.price, tip=o.tip,
                       wait=round(o.wait, 1) if o.patience > 0 else None)
        new = self.stats.record(cup, [k for k in DRINKS if k not in FESTIVAL_DRINKS])
        self.announce(new)
        self.stats.save()

    def announce(self, keys):
        names = {k: n for k, n, _ in ACHIEVEMENTS}
        now = time.perf_counter()
        for i, k in enumerate(keys):
            start = max(now, self.toasts[-1][2] if self.toasts else now) + (0.6 if i or self.toasts else 0.8)
            name = T(names[k])
            if k in TIER_OF:                         # 分級成就：前面加上銅／銀／金獎牌
                name = f"{TIER_ICONS[TIER_OF[k][1]]} {name}"
            self.toasts.append((T("成就解鎖：{name}", name=name), start, start + 4.0))
        if keys:
            self.sound.once("ding_hi", 0.45)
            self.set_frame_interval(FRAME_AMBIENT)

    def show_notice(self, text, sec=5.0):
        self.notice = (text, time.perf_counter() + sec)
        self.set_frame_interval(FRAME_AMBIENT)

    def toast(self, text, sec=6.0):
        """不屬於成就的通知：跟成就通知一樣暫時取代狀態列（沖煮中也看得到），排在已有的通知後面"""
        now = time.perf_counter()
        start = max(now, self.toasts[-1][2] + 0.6) if self.toasts else now
        self.toasts.append((text, start, start + sec))
        self.set_frame_interval(FRAME_AMBIENT)

    def tray_message(self, text, ms=6000):
        if self.tray:
            self.tray.showMessage("Café Desk", text, self.icon, ms)

    # ───────────── 休息提醒 ─────────────
    def set_break(self, minutes):
        self.break_min = minutes
        self.break_t = 0.0
        self.save_config()

    def reset_break(self):
        self.break_t = 0.0

    def update_break_menu(self):
        a = self.act_break_reset
        if self.break_min:
            left = max(1, math.ceil(self.break_min - self.break_t / 60))
            a.setText(T("重新計時（還有 {m} 分鐘）", m=left))
        else:
            a.setText(T("重新計時"))
        a.setEnabled(bool(self.break_min))

    def update_break(self, dt):
        """真實時間累計（dt 每個 tick 最多 0.5 秒，所以電腦睡眠的時間不算）；時間到就提醒，咖啡師順便做一杯"""
        if not self.break_min:
            return
        self.break_t += dt
        if self.break_t < self.break_min * 60:
            return
        self.break_t = 0.0
        text = T("休息一下：起來走走、喝杯咖啡吧（已經 {m} 分鐘了）", m=self.break_min)
        self.toast(text, 8.0)
        self.tray_message(text)
        self.sound.once("ding_hi", 0.5)
        drink = self.auto_drink()                    # 冰滴還在滴就只提醒、不做
        if drink and not self.busy() and not self.order_mode:
            self.start_session(drink, True)

    # ───────────── 檢查更新 ─────────────
    def set_update_check(self, v):
        self.update_check = v
        if not v and self.update_info:               # 關掉就不再顯示「下載新版」
            self.update_info = None
            self.build_menu()
        self.save_config()

    def check_update(self, manual=False):
        if update.disabled() or (self.update_job is not None and self.update_job.result is None):
            return
        self.update_job = update.Checker(manual)
        self._update_at = time.perf_counter() + UPDATE_RETRY
        if manual:
            self.show_notice(T("檢查新版本中…"), 3.0)

    def poll_update(self, now):
        """主執行緒取走背景查詢的結果；每天自動查一次（失敗的話一小時後再試）"""
        job = self.update_job
        if job is None:
            today = datetime.date.today().isoformat()
            if self.update_check and now >= self._update_at and self.cfg.get("update_checked") != today:
                self.check_update()
            return
        res = job.result
        if res is None:
            return
        self.update_job = None
        if res["error"]:
            if job.manual:
                self.show_notice(T("無法檢查更新（請確認網路連線）"))
            return
        self.cfg["update_checked"] = datetime.date.today().isoformat()
        self.cfg["update_latest"] = res["tag"]
        if res["newer"]:
            first = res["tag"] != self.cfg.get("update_seen")
            self.update_info = res
            self.cfg["update_seen"] = res["tag"]
            self.build_menu()
            if first or job.manual:                  # 同一版只主動提醒一次，之後留在右鍵選單最上面
                text = T("有新版本 {tag}：右鍵選單最上面「下載新版」", tag=res["tag"])
                self.toast(text, 8.0)
                self.tray_message(text)
        else:
            if self.update_info:
                self.update_info = None
                self.build_menu()
            if job.manual:
                self.show_notice(T("已經是最新版本（{v}）", v=update.__version__))
        self.save_config()

    def open_update_page(self):
        QDesktopServices.openUrl(QUrl(self.update_info["url"] if self.update_info else update.RELEASES_URL))

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
        if self.business():                          # 營業中的咖啡師換了豆子會重新找參數；自動模式照使用者的設定
            self.barista.shake_up(self.params)
        self.sound.once("tap", 0.4)
        self.show_notice(T("開了一包新豆子：{name}（{roast}，{flavor}）", name=T(beans.bag_name(self.bag)),
                           roast=T(beans.bag_roast(self.bag)), flavor=T(beans.bag_flavor(self.bag))))
        if self.settings_dlg is not None:
            self.settings_dlg.sync_bean()
        self.announce(self.stats.record_bag(self.bag["origin"]))
        self.save_config()

    # ───────────── 清潔保養 ─────────────
    def start_job(self, kind):
        if self.busy() or self.method != "espresso":      # 手沖／冰滴畫面看不到咖啡機
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

    def auto_drink(self):
        """自動模式：照設定重複做目前選的飲品（參數不變）；冰滴還在滴就先等，回傳 None"""
        if self.drink == "cold_drip" and self.cold is not None and not self.cold.get("done"):
            return None
        return self.drink

    def manual_brew(self):
        """手動沖煮：一律跑完整流程（義式從取把手、敲渣、磨豆開始；手沖、冰滴本來就從磨豆開始）"""
        if self.busy():
            return
        if self.order_mode:
            self.make_order()
            return
        self.start_session(self.drink, True)

    def make_order(self):
        """點單模式：照目前的訂單做（還沒有訂單就叫下一位客人）"""
        o = self.order
        if o is None or o.state in ("done", "leaving"):
            if self.queue:
                self.next_customer()
            else:
                self.new_order()
            o = self.order
        if o is None:
            self.show_notice(T("冰滴還在滴，大約 {m} 分鐘後好", m=brew.cold_remaining_min(self.cold))
                             if self.cold else T("現在沒有可以點的飲品"))
            return
        if o.state != "waiting":
            return
        machine, method = self.machine.key, self.method
        if method_of(o.drink) == "espresso":
            self.set_machine(random.choice(list(MACHINES)))   # 客人點義式：每張訂單隨機一台咖啡機
        self.set_method(method_of(o.drink))
        if (self.machine.key, self.method) != (machine, method):
            self._switch_wait = [o, FADE_T + SWITCH_PAUSE]     # 換了畫面：漸變完、再停一下才開始做（update_order 倒數）
            return
        self.start_order(o)

    def start_order(self, o):
        dp = orders.order_params(o, self.dp)
        if method_of(o.drink) != "espresso":
            dp = brew.barista_dial(dp, self.params.roast)     # 咖啡師依烘焙度調手沖／冰滴
        self.start_session(o.drink, True, dp, order=o)        # 營業中也跑完整備粉

    def new_order(self):
        """來一位客人：營業模式下前面還有人就去排隊"""
        self.order_no += 1
        o = orders.make_order(self.order_no, last_name=self._last_customer, exclude=self.order_exclude())
        if o is None:                                    # 這個沖煮方式現在沒有可以點的（冰滴還在滴）
            self.order_no -= 1
            self.next_order_at = time.perf_counter() + 6.0
            return
        self._last_customer = o.name
        if self.business():
            o.patience = orders.patience(method=method_of(o.drink))     # 手沖比較久，客人也比較願意等
        if self.business() and self.order is not None and self.order.state in ("waiting", "making"):
            self.queue.append(o)
        else:
            self.order = o
        self.sound.once("ding_hi", 0.25)
        self.set_frame_interval(FRAME_AMBIENT)

    def order_exclude(self):
        """現在不能點的飲品：冰滴沒有滴好，或剩下的都被前面的客人點走了
        （其他飲品不分沖煮方式都能點，做的時候 start_session 會自動切過去）"""
        pending = [x for x in [self.order] + self.queue if x is not None and x.state in ("waiting", "making")]
        ready = self.cold["servings"] if (self.cold and self.cold.get("done")) else 0
        left = ready - sum(1 for x in pending if x.drink == "cold_drip")
        return () if left > 0 else ("cold_drip",)

    def next_customer(self):
        """排隊的下一位走到櫃台"""
        self.order = self.queue.pop(0)
        self.order.t = 0.0

    def update_queue(self, sdt):
        """營業模式：等待中的客人累計等待時間，耐心用完就離開；依間隔來新客人（排滿就不來）"""
        o = self.order
        waiting = ([o] if o is not None and o.state == "waiting" else []) + self.queue
        for w in waiting:
            w.wait += sdt
            if w.patience > 0 and w.wait >= w.patience:      # 沒設耐心（0）的不會走
                self.walk_out(w)
        self.arrive_in -= sdt
        if self.arrive_in <= 0:
            self.arrive_in = orders.arrival_gap()
            present = len(self.queue) + (1 if o is not None and o.state in ("waiting", "making") else 0)
            if present < orders.QUEUE_MAX:
                self.new_order()
        o = self.order
        present = len(self.queue) + (1 if o is not None and o.state in ("waiting", "making") else 0)
        if present >= orders.QUEUE_MAX:
            self.rush = True                         # 尖峰：排滿了；之後沒人離開、隊伍清空就解鎖成就
        elif present == 0 and self.rush:
            self.rush = False
            self.announce(self.stats.unlock("rush"))

    def walk_out(self, o):
        if o is self.order:
            o.state, o.t = "leaving", 0.0
        else:
            self.queue.remove(o)
        self.rush = False
        self.show_notice(T("{name} 等太久，先走了", name=T(o.name)))
        self.sound.once("ding_lo", 0.3)
        self.announce(self.stats.record_walkout(o.drink))

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
        dt_real = dt
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
        ss = self.session
        station_phase = getattr(ss.stage, "phase", "") if (ss and ss.family in STATION_FAMILIES) else ""
        grinding = (self.workflow and self.workflow.grinding) or bool(station_phase and ss.station.get("grinding"))
        self.sound.loop("grinder", 0.45 if grinding else 0.0)
        steaming = bool(ss and ss.stage_name == "steam" and self.machine.traits.milk == "wand"
                        and getattr(ss.stage, "phase", "") == "run")
        self.sound.loop("steam", 0.35 if steaming else 0.0)
        self.sound.loop("chirp", 0.3 if (steaming and ss.stretching) else 0.0)
        self.sound.loop("frother", 0.4 if (ss and ss.frother_on) else 0.0)
        vessel_pour = bool(ss and ss.vessel and ss.vessel.get("pour", 0) > 0)
        if vessel_pour:
            pour_vol = max(pour_vol, 0.3)
        if station_phase in ("bloom_pour", "pulse") and ss.station["kettle"]["pour"] > 0:
            pour_vol = max(pour_vol, 0.16)             # 細口壺：細細的水聲
        elif station_phase == "water":
            pour_vol = max(pour_vol, 0.3)              # 冰滴塔加冰水
        self.sound.loop("pour", pour_vol)
        st_ = ss.station if station_phase else None    # 摩卡壺：爐火、咕嚕聲；虹吸壺：下壺沸騰、咖啡被吸下去
        fam = ss.family if st_ else ""
        self.sound.loop("flame", 0.3 * st_["flame"] if fam == "moka" else 0.0)
        gurgle = 0.0
        if fam == "moka" and station_phase in ("brew", "sputter"):
            gurgle = 0.22 + 0.35 * st_["sputter"]
        elif fam == "siphon" and station_phase == "drawdown":
            gurgle = 0.18
        self.sound.loop("gurgle", gurgle)
        self.sound.loop("boil", 0.1 + 0.3 * st_["boil"] if fam == "siphon" and st_["boil"] > 0.02 else 0.0)
        self.sound.ambience(self.ambience, self.amb_level)
        self.update_break(dt_real)
        if ms - self._last_tip_ms > 500:
            self._last_tip_ms = ms
            self.update_tray_tip()
            self.update_light()
            self.poll_update(time.perf_counter())
        if self.isVisible():
            self.update()
        self.set_frame_interval(self.wanted_interval())

    def step(self, dt, sdt):
        """推進一個模擬子步：dt 是真實時間，sdt 是乘上播放速度後的沖煮時間"""
        now = time.perf_counter()
        if self.cold is not None and not self.cold.get("done") and brew.cold_progress(self.cold) >= 1:
            self.finish_cold()
        if self.method != "espresso":
            self.update_zoom(dt)

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
        idle_ok = now - self.idle_since >= min(self.interval, 8.0)
        if self.method == "espresso" and not self.busy() and (self.order_mode or (self.auto and idle_ok)):
            todo = maintenance.due(self.maint)
            if todo:                                     # 自動模式閒下來先清；營業中做完一杯、接下一張單前先清
                self.start_job(todo[0])
        if self.order_mode:
            self.update_order(dt, now, sdt)
        elif self.auto and not self.busy() and now - self.idle_since >= self.interval:
            drink = self.auto_drink()
            if drink is None:                            # 冰滴還在滴：等滴完
                self.idle_since = now
            else:
                self.start_session(drink, True)          # 照設定再做一杯（跑完整流程）
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
                and self.method == "espresso" and now - self._last_relay > 2:
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
        if not self.busy() and self.isVisible() and now >= self.next_idle_event and self.method == "espresso":
            self.idle_event()                            # 手沖／冰滴看不到咖啡機：不放氣、不滴水
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

    def update_order(self, dt, now, sdt):
        """點單模式：客人來點單 →（自動模式下咖啡師接單）→ 完成後顯示反應 → 離開 → 下一位

        營業模式（＝顧客點單）：客人照 arrival_gap 的間隔進來排隊，排隊的人走到櫃台後才顯示點單紙"""
        if self.business():
            self.update_queue(sdt)
        sw = self._switch_wait
        if sw is not None:                               # 換了咖啡機／沖煮方式：倒數完才開始做這張
            if sw[0] is not self.order or sw[0].state != "waiting":
                self._switch_wait = None                 # 客人等不及走了
            else:
                sw[1] -= dt
                if sw[1] <= 0:
                    self._switch_wait = None
                    self.start_order(sw[0])
        o = self.order
        if o is not None:
            o.t += dt
        if o is None:
            if self.queue:
                self.next_customer()
            elif not self.business() and not self.busy() and now >= self.next_order_at:
                self.new_order()
        elif o.state == "waiting":
            if not self.busy() and o.t >= 2.5:              # 咖啡師自己接單
                self.barista_dial_in()
                self.save_config()
                self.make_order()
        elif o.state == "done" and o.t >= (orders.SHOW_DONE if not self.queue else 4.0):   # 後面有人排隊就早點讓位
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
        if ev == "grind":                              # 手沖台磨豆：從這包扣粉量
            self.use_beans(self.brew_dose(self.session.drink, self.session.dp))
        elif ev == "cold_grind":
            self.use_beans(self.session.dp.cd_dose)
        elif ev == "ignite":                           # 點火：旋鈕「喀」、瓦斯「噗」
            self.sound.once("click", 0.4)
            self.sound.once("hiss", 0.15)
        elif ev == "flame_off":
            self.sound.once("click", 0.35)
        elif ev in ("stir", "tap"):
            self.sound.once("tap", 0.2)
        elif ev == "sputter":
            self.sound.once("hiss", 0.2)
        elif ev == "kettle_start":
            self.sound.once("tap", 0.12)
        elif ev == "valve":
            self.sound.once("click", 0.4)
        elif ev == "pour_start":
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
        if self._fade is not None:
            return FRAME_ACTIVE                    # 換咖啡機／沖煮方式的漸變
        if (self.busy() or self.drops or self.splash or self.ripples
                or any(st["head"] > 0 for st in self.stream)):
            return FRAME_ACTIVE
        if self.drink_kind() == "espresso_tonic" and self.contents["water"] > 0:
            return FRAME_AMBIENT                   # 通寧水的氣泡一直往上冒
        if self.icecream and self.icecream["melt"] < 0.98 and self.shot:
            return FRAME_AMBIENT                   # 冰淇淋慢慢融化
        if self.method != "espresso" and (0.0 < self.brew_zoom < 1.0 or self.brew_focus() != (self.brew_zoom >= 1.0)):
            return FRAME_AMBIENT                   # 手沖／冰滴畫面正在拉近或拉遠
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
        espresso = self.method == "espresso"
        key = (dpr, self.machine.key, self.cup.kind, self._scene_w, self.method)
        if self.bg_layer is None or getattr(self, "_layer_key", None) != key:
            self._layer_key = key
            self.bg_layer = self.render_layer(self.paint_background if espresso else self.paint_brew_background, dpr)
            self.front_layer = self.render_layer(self.paint_front if espresso else self.paint_brew_front, dpr)
        w, h = int(self.width() * dpr), int(self.height() * dpr)
        if self._frame is None or self._frame.width() != w or self._frame.height() != h:
            self._frame = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
            self._frame.setDevicePixelRatio(dpr)
        self._frame.fill(Qt.transparent)

        s = self.scale_f
        fp = QPainter(self._frame)
        fp.setRenderHint(QPainter.Antialiasing)
        fp.setRenderHint(QPainter.SmoothPixmapTransform)
        if espresso:
            fp.drawPixmap(QPointF(0, TOP_PAD * s), self.bg_layer)
        fp.scale(s, s)
        fp.translate(0, TOP_PAD)
        m = self.machine
        if not espresso:
            self.paint_brew_frame(fp)
            fp.end()
            self.paint_overlays()
            return
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
        self.paint_overlays()

    def paint_brew_frame(self, fp):
        """手沖／冰滴的畫面（場景座標）：器具 → 杯中液體 → 杯子前景 → 倒的壺"""
        s, m = self.scale_f, self.machine
        cup_a = self.cup_alpha()                     # 拉近看沖煮器具時杯子淡出
        if cup_a > 0.01:
            fp.save()
            fp.resetTransform()
            fp.setOpacity(cup_a)
            fp.drawPixmap(QPointF(0, TOP_PAD * s), self.bg_layer)
            fp.restore()
        self.paint_station(fp)
        fp.save()
        fp.setOpacity(cup_a)
        fp.translate(m.mx, m.my)
        self.paint_liquid(fp)
        self.paint_ice(fp)
        self.paint_pour_stream(fp)
        self.paint_particles(fp)
        fp.restore()
        fp.resetTransform()
        fp.setOpacity(cup_a)
        fp.drawPixmap(QPointF(0, TOP_PAD * s), self.front_layer)
        fp.scale(s, s)
        fp.translate(m.mx, m.my + TOP_PAD)
        self.paint_condensation(fp)
        self.paint_steam(fp)
        fp.setOpacity(1.0)
        fp.translate(-m.mx, -m.my)
        self.paint_vessel(fp, self.session.vessel if self.session else None)
        self.paint_ambient(fp)

    def begin_fade(self):
        """換咖啡機／沖煮方式前先留下目前的畫面，接下來 FADE_T 秒讓它淡出、新畫面淡入"""
        if self._frame is not None and self.isVisible():
            self._fade = (self._frame.copy(), time.perf_counter())

    def fade_amount(self):
        """漸變進度 0–1（沒有在漸變時是 None）"""
        if self._fade is None:
            return None
        k = (time.perf_counter() - self._fade[1]) / FADE_T
        if k >= 1:
            self._fade = None
            return None
        return k

    def paint_overlays(self):
        """把畫好的畫面貼到視窗，再疊上狀態列與卡片"""
        s = self.scale_f
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.windowed:
            self.paint_window_backdrop(p)
        k = self.fade_amount()
        if k is None:
            p.drawImage(0, 0, self._frame)
        else:                                        # 換咖啡機／沖煮方式：舊畫面淡出、新畫面淡入
            p.setOpacity(1 - k)
            p.drawImage(0, 0, self._fade[0])
            p.setOpacity(k)
            p.drawImage(0, 0, self._frame)
            p.setOpacity(1.0)
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
        pm = QPixmap(int(self._scene_w * self.scale_f * dpr), int(WIN_H * self.scale_f * dpr))
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

