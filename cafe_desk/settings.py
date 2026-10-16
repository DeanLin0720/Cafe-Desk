"""沖煮參數設定視窗"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QSlider, QLabel, QGridLayout, QComboBox, QPushButton, QHBoxLayout,
                               QCheckBox)

from .drinks import DRINKS, DRINK_KEYS, DrinkParams, ART_CHOICES, MILK_KINDS, shot_params, whip_on
from .model import ROASTS, Params, simulate
from .i18n import T
from . import beans, festivals

SLIDERS = [
    ("研磨粒徑", "grind_um", 150, 500, 5, "µm"),
    ("粉量", "dose", 7, 24, 0.5, "g"),
    ("液重", "yield_g", 15, 70, 1, "g"),
    ("水溫", "temp", 85, 98, 0.5, "°C"),
    ("壓力", "pressure", 4, 12, 0.5, "bar"),
    ("預浸泡", "preinfusion", 0, 15, 1, "s"),
    ("布粉品質", "distribution", 0, 100, 5, "%"),
    ("養豆天數", "bean_age", 1, 60, 1, "天"),
]

MILK_DRINKS = ("latte", "cappuccino", "flat_white", "cortado", "macchiato", "mocha", "caramel_macchiato")
ART_DRINKS = ("latte", "cappuccino", "flat_white", "cortado", "mocha")
# (名稱, 欄位, 最小, 最大, 間隔, 單位, 適用飲品)
DRINK_SLIDERS = [
    ("牛奶量", "milk_g", 80, 200, 5, "g", ("latte",)),
    ("奶泡量", "foam", 0, 80, 5, "%", ("latte",)),
    ("牛奶量", "capp_milk_g", 60, 140, 5, "g", ("cappuccino",)),
    ("奶泡量", "capp_foam", 30, 100, 5, "%", ("cappuccino",)),
    ("牛奶量", "flat_milk_g", 60, 140, 5, "g", ("flat_white",)),
    ("奶泡量", "flat_foam", 0, 40, 2, "%", ("flat_white",)),
    ("牛奶量", "cortado_milk_g", 20, 70, 2, "g", ("cortado",)),
    ("一匙奶泡", "mac_milk_g", 8, 30, 1, "g", ("macchiato",)),
    ("牛奶量", "mocha_milk_g", 80, 180, 5, "g", ("mocha",)),
    ("巧克力醬", "choc_g", 5, 40, 1, "g", ("mocha",)),
    ("牛奶量", "cm_milk_g", 100, 180, 5, "g", ("caramel_macchiato",)),
    ("香草糖漿", "vanilla_g", 0, 25, 1, "g", ("caramel_macchiato",)),
    ("打奶溫度", "milk_temp", 40, 80, 1, "°C", MILK_DRINKS),
    ("通寧水", "tonic_g", 80, 220, 5, "g", ("espresso_tonic",)),
    ("冰淇淋", "scoop_g", 40, 120, 5, "g", ("affogato",)),
    ("熱水量", "water_g", 60, 180, 5, "g", ("americano",)),
    ("冷水量", "iced_water_g", 60, 200, 5, "g", ("iced_americano",)),
    ("冰塊", "ice", 0, 8, 1, "顆", ("iced_latte", "iced_americano", "espresso_tonic")),
    ("牛奶量", "iced_milk_g", 80, 220, 5, "g", ("iced_latte",)),
]


def _note(text=""):
    lab = QLabel(text)
    lab.setStyleSheet("color:#7a6a5a;")
    return lab


class SettingsDialog(QDialog):
    def __init__(self, app):
        super().__init__(None)
        self.app = app
        self.setWindowTitle(T("沖煮參數"))
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        grid = QGridLayout(self)
        self.sliders = {}
        for i, (label, attr, lo, hi, step, unit) in enumerate(SLIDERS):
            grid.addWidget(QLabel(T(label)), i, 0)
            sl = QSlider(Qt.Horizontal)
            sl.setRange(0, int(round((hi - lo) / step)))
            sl.setValue(int(round((getattr(app.params, attr) - lo) / step)))
            sl.setMinimumWidth(200)
            val = QLabel()
            val.setMinimumWidth(64)
            grid.addWidget(sl, i, 1)
            grid.addWidget(val, i, 2)
            self.sliders[attr] = (sl, val, lo, step, T(unit))
            if attr == "bean_age":
                sl.setEnabled(False)                # 依豆子的烘焙日自動計算
            sl.valueChanged.connect(lambda _v, a=attr: self.changed(a))

        r = len(SLIDERS)
        grid.addWidget(QLabel(T("烘焙度")), r, 0)
        self.roast = QComboBox()
        for key in ROASTS:
            self.roast.addItem(T(key), key)
        self.roast.setCurrentIndex(list(ROASTS).index(app.params.roast))
        self.roast.setEnabled(False)                # 烘焙度與養豆天數跟著目前這包豆子
        grid.addWidget(self.roast, r, 1)
        self.bean_label = _note()
        grid.addWidget(self.bean_label, r, 2)
        grid.addWidget(QLabel(T("粉碗容量 (g)")), r + 1, 0)
        self.basket = QComboBox()
        self.basket.addItems(["7", "14", "18", "20", "22"])
        self.basket.setCurrentText(f"{app.params.basket:g}")
        self.basket.currentTextChanged.connect(lambda _t: self.changed())
        grid.addWidget(self.basket, r + 1, 1)

        r += 2
        head = QLabel(T("飲品"))
        head.setStyleSheet("font-weight:bold; padding-top:8px;")
        grid.addWidget(head, r, 0)
        r += 1
        grid.addWidget(QLabel(T("飲品")), r, 0)
        self.drink = QComboBox()
        fd = festivals.festival_drink()
        self.drink_keys = list(DRINK_KEYS) + ([fd] if fd else [])
        for key in self.drink_keys:
            self.drink.addItem(T(DRINKS[key]["name"]), key)
        self.drink.setCurrentIndex(self.drink_keys.index(app.drink) if app.drink in self.drink_keys else 0)
        self.drink.currentIndexChanged.connect(lambda _i: self.drink_changed())
        grid.addWidget(self.drink, r, 1)
        r += 1
        self.preset = QLabel()
        self.preset.setStyleSheet("color:#7a6a5a;")
        grid.addWidget(self.preset, r, 0, 1, 3)
        r += 1
        self.dsliders = {}
        for i, (label, attr, lo, hi, step, unit, drinks) in enumerate(DRINK_SLIDERS):
            lab = QLabel(T(label))
            grid.addWidget(lab, r + i, 0)
            sl = QSlider(Qt.Horizontal)
            sl.setRange(0, int(round((hi - lo) / step)))
            sl.setValue(int(round((getattr(app.dp, attr) - lo) / step)))
            val = QLabel()
            grid.addWidget(sl, r + i, 1)
            grid.addWidget(val, r + i, 2)
            self.dsliders[attr] = (sl, val, lo, step, T(unit), drinks, lab)
            sl.valueChanged.connect(lambda _v, a=attr: self.dchanged(a))
        r += len(DRINK_SLIDERS)
        self.cocoa = QCheckBox(T("撒可可粉"))
        self.cocoa.setChecked(bool(app.dp.cocoa))
        self.cocoa.toggled.connect(self.cocoa_changed)
        grid.addWidget(self.cocoa, r, 1)
        self.whip = QCheckBox(T("擠鮮奶油＋可可粉"))
        self.whip.setChecked(bool(app.dp.whip))
        self.whip.toggled.connect(self.whip_changed)
        grid.addWidget(self.whip, r, 2)
        r += 1
        self.milk_label = QLabel(T("牛奶種類"))
        grid.addWidget(self.milk_label, r, 0)
        self.milk_kind = QComboBox()
        for key, d in MILK_KINDS.items():
            self.milk_kind.addItem(T(d["name"]), key)
        self.milk_kind.setCurrentIndex(list(MILK_KINDS).index(app.dp.milk_kind))
        self.milk_kind.currentIndexChanged.connect(self.milk_kind_changed)
        grid.addWidget(self.milk_kind, r, 1)
        self.milk_hint = QLabel(T("植物奶較難拉花"))
        self.milk_hint.setStyleSheet("color:#7a6a5a;")
        grid.addWidget(self.milk_hint, r, 2)
        r += 1
        self.art_label = QLabel(T("拉花圖案"))
        grid.addWidget(self.art_label, r, 0)
        self.art = QComboBox()
        for key, label in ART_CHOICES:
            self.art.addItem(T(label), key)
        self.sync_art()
        self.art.currentIndexChanged.connect(lambda _i: self.app.set_art(self.art.currentData()))
        grid.addWidget(self.art, r, 1)
        self.art_hint = QLabel(T("奶泡不夠細時會退化"))
        self.art_hint.setStyleSheet("color:#7a6a5a;")
        grid.addWidget(self.art_hint, r, 2)
        r -= 1

        self.preview = QLabel()
        self.preview.setStyleSheet("color:#8a5426; padding-top:6px;")
        grid.addWidget(self.preview, r + 2, 0, 1, 3)
        row = QHBoxLayout()
        for text, fn in ((T("沖一杯"), app.manual_brew), (T("恢復預設"), self.reset), (T("關閉"), self.hide)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        grid.addLayout(row, r + 3, 0, 1, 3)
        self.dchanged()
        self.changed()
        self.sync_bean()
        self.update_visibility()

    def sync_bean(self):
        """豆子換了：烘焙度、養豆天數跟著更新"""
        p = self.app.params
        self.roast.setCurrentIndex(list(ROASTS).index(p.roast))
        sl, val, lo, step, unit = self.sliders["bean_age"]
        sl.blockSignals(True)
        sl.setValue(int(round((min(60, p.bean_age) - lo) / step)))
        sl.blockSignals(False)
        val.setText(f"{p.bean_age:g} {unit}")
        b = self.app.bag
        self.bean_label.setText(T("{name} · 剩 {g:.0f} g", name=T(beans.bag_name(b)), g=b["left"]))

    def sync_art(self):
        keys = [k for k, _ in ART_CHOICES]
        self.art.blockSignals(True)
        self.art.setCurrentIndex(keys.index(self.app.dp.art) if self.app.dp.art in keys else 0)
        self.art.blockSignals(False)

    def drink_changed(self):
        self.app.set_drink(self.drink.currentData())
        self.app.drink_actions[self.app.drink].setChecked(True)
        self.update_visibility()

    def sync_drink(self):
        """選單換了飲品時同步下拉選單"""
        self.drink.blockSignals(True)
        if self.app.drink in self.drink_keys:
            self.drink.setCurrentIndex(self.drink_keys.index(self.app.drink))
        self.drink.blockSignals(False)
        self.update_visibility()

    def update_visibility(self):
        """只顯示目前飲品用得到的飲品參數"""
        d = self.drink.currentData()
        for a, (sl, val, lo, step, unit, drinks, lab) in self.dsliders.items():
            on = d in drinks
            for wdg in (sl, val, lab):
                wdg.setVisible(on)
        self.cocoa.setVisible(d == "cappuccino")
        self.whip.setVisible(d == "mocha")
        for wdg in (self.milk_kind, self.milk_label, self.milk_hint):
            wdg.setVisible(d in MILK_DRINKS or d == "iced_latte")
        art_on = d in ART_DRINKS and not whip_on(d, self.app.dp)     # 擠了鮮奶油就看不到拉花
        for wdg in (self.art, self.art_label, self.art_hint):
            wdg.setVisible(art_on)
        self.update_preset()
        self.adjustSize()

    def update_preset(self):
        d = self.drink.currentData()
        p, style, preset = shot_params(d, self.app.params)
        if preset:
            text = T("這杯的濃縮：{dose:g} g → {y:g} g（1:{r:.1f}）", dose=p.dose, y=p.yield_g, r=p.yield_g / p.dose)
            if style:
                text += T("，以 {style} 標準評分", style=style.capitalize())
            self.preset.setText(text)
            self.preset.setVisible(True)
        else:
            self.preset.setVisible(False)

    def whip_changed(self, v):
        self.app.dp.whip = bool(v)
        self.app.save_config()
        self.update_visibility()

    def milk_kind_changed(self, _i):
        self.app.dp.milk_kind = self.milk_kind.currentData()
        self.app.save_config()

    def cocoa_changed(self, v):
        self.app.dp.cocoa = bool(v)
        self.app.save_config()

    def dchanged(self, attr=None):
        dp = self.app.dp
        for a, (sl, val, lo, step, unit, drinks, lab) in self.dsliders.items():
            v = lo + sl.value() * step
            val.setText(f"{v:g} {unit}")
            if attr in (None, "all") or a == attr:
                setattr(dp, a, float(v))
        if attr is not None:
            self.app.save_config()

    def changed(self, attr=None):
        p = self.app.params
        for a, (sl, val, lo, step, unit) in self.sliders.items():
            v = lo + sl.value() * step
            val.setText(f"{v:g} {unit}")
            if (attr is None or a == attr) and a != "bean_age":
                setattr(p, a, float(v))
        p.basket = float(self.basket.currentText())
        res = simulate(p, self.app.machine.traits)
        if hasattr(self, "preset"):
            self.update_preset()
        self.preview.setText(T("預估 {t:.0f} 秒 · EY {ey:.1f}% · TDS {tds:.1f}% · {score:.0f} 分", t=res.time, ey=res.ey,
                               tds=res.tds, score=res.score))
        self.app.save_config()

    def reset(self):
        d = Params()
        for a, (sl, val, lo, step, unit) in self.sliders.items():
            sl.blockSignals(True)
            sl.setValue(int(round((getattr(d, a) - lo) / step)))
            sl.blockSignals(False)
        self.basket.setCurrentText(f"{d.basket:g}")
        dd = DrinkParams()
        self.cocoa.setChecked(dd.cocoa)
        self.whip.setChecked(dd.whip)
        self.milk_kind.setCurrentIndex(list(MILK_KINDS).index(dd.milk_kind))
        self.app.set_art(dd.art)
        for a, (sl, val, lo, step, unit, drinks, lab) in self.dsliders.items():
            sl.blockSignals(True)
            sl.setValue(int(round((getattr(dd, a) - lo) / step)))
            sl.blockSignals(False)
        self.dchanged("all")
        self.changed()
        self.app.sync_bag()
        self.sync_bean()

