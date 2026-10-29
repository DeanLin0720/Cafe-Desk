"""飲品：牛奶與拉花模型、各飲品評分、每台機器 × 每種飲品的 Session 都能跑完"""
import random

import pytest

from cafe_desk import drinks
from cafe_desk.orders import ORDER_WEIGHTS
from cafe_desk.drinks import (DRINKS, DRINK_KEYS, DrinkParams, MILK_SPEC, evaluate_milk, milk_plan,
                              band_score, shot_params)
from cafe_desk.machines import MACHINES
from cafe_desk.model import Params

from conftest import run_until_idle

WAND = MACHINES["lever"].traits                 # 蒸氣強的機器


def _milk(dp=None, drink="latte", device="wand", seed=1):
    return evaluate_milk(dp or DrinkParams(), WAND, device, random.Random(seed), drink)


# ───────────── 資料表一致性 ─────────────
def test_drink_tables_consistent():
    for k in DRINK_KEYS:
        assert k in DRINKS
        assert k in ORDER_WEIGHTS, k
        assert DRINKS[k]["base"] in ("espresso", "americano", "iced", "milk", "affogato", "pourover", "colddrip", "moka", "siphon"), k
    for k, spec in DRINKS.items():
        if spec["base"] == "milk":
            assert k in MILK_SPEC, k


def test_shot_presets():
    p, style, preset = shot_params("ristretto", Params())
    assert preset and style == "ristretto" and p.yield_g < p.dose * 1.6
    p, style, preset = shot_params("doppio", Params())
    assert preset and p.basket == 22
    p, style, preset = shot_params("latte", Params(dose=18, yield_g=36))
    assert not preset and p.yield_g == 36


def test_band_score():
    assert band_score(5, 4, 6, 10) == 100
    assert band_score(3, 4, 6, 10) == 90
    assert band_score(-100, 4, 6, 10) == 0


# ───────────── 牛奶與拉花 ─────────────
def test_milk_result_in_range():
    for drink in MILK_SPEC:
        for temp in (40, 60, 80):
            for kind in drinks.MILK_KINDS:
                dp = DrinkParams(milk_temp=temp, milk_kind=kind)
                for device in ("wand", "frother"):
                    m = _milk(dp, drink, device)
                    assert 0 <= m.texture <= 1
                    assert 0 <= m.score <= 100
                    assert m.art in drinks.ART_NAMES


def test_scalding_milk_comment():
    assert _milk(DrinkParams(milk_temp=78)).comment == "奶溫過高，甜感流失"
    assert _milk(DrinkParams(milk_temp=45)).comment == "奶溫偏低"


def test_good_milk_beats_bad_milk():
    good = [_milk(DrinkParams(milk_temp=60, foam=30), seed=s).score for s in range(20)]
    bad = [_milk(DrinkParams(milk_temp=75, foam=80), seed=s).score for s in range(20)]
    assert sum(good) > sum(bad)


def test_requested_art_degrades_when_foam_is_rough():
    """指定葉子但奶泡很粗：退化成糊掉的葉子或白點，並寫入 art_note"""
    dp = DrinkParams(milk_temp=74, foam=85, art="rosetta", milk_kind="almond")
    m = _milk(dp, device="frother")
    assert m.art in ("rosetta", "blob")
    assert m.art_note


def test_fixed_art_drinks():
    assert _milk(drink="macchiato").art == "dot"
    assert _milk(drink="caramel_macchiato").art == "mark"
    assert _milk(DrinkParams(whip=True), drink="mocha").art == "whip"


def test_milk_plan_uses_drink_fields():
    dp = DrinkParams(capp_milk_g=111, capp_foam=66)
    assert milk_plan("cappuccino", dp)[:2] == (111, 66)
    assert milk_plan("cortado", dp)[1] == 15.0


# ───────────── 完整 Session（無頭） ─────────────
@pytest.mark.parametrize("machine", list(MACHINES))
def test_every_drink_finishes_on_every_machine(qapp, cfg_path, machine):
    import json
    from cafe_desk.desk import CafeDesk
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"x": 0, "y": 0, "machine": machine}, f)
    random.seed(3)
    w = CafeDesk()
    try:
        w.show_window()
        w.warming = False
        w.boiler.temp = w.params.temp
        for i, d in enumerate(DRINK_KEYS):
            w.bag["left"] = 250
            assert w.start_session(d, i % 3 == 0), d     # 每三杯有一杯跑完整備粉流程
            run_until_idle(w)
            if d == "cold_drip":                          # 第一次是架冰滴塔；快轉滴完再倒一杯
                assert w.result is None and w.cold is not None
                w.cold["start"] -= w.cold["dur"]
                assert w.start_session(d, False)
                run_until_idle(w)
            r = w.result
            assert r is not None and r.drink == d
            assert 0 <= r.score <= 100, (d, r.score)
            assert r.comment
        assert w.stats.data["total"] == len(DRINK_KEYS)
    finally:
        w.timer.stop()
        if w.stats.db is not None:
            w.stats.db.close()
        w.host.close()
        w.deleteLater()


def test_empty_bag_refuses_to_brew(desk):
    desk.auto = False
    desk.bag["left"] = 3
    assert desk.start_session("espresso", False) is False
    assert desk.open_bag("kenya") is False, "庫存沒有：不會有免費的豆子"
    assert desk.buy_beans("kenya") and desk.open_bag("kenya")
    assert desk.start_session("espresso", False)
    run_until_idle(desk)


def test_maintenance_jobs_finish(desk):
    from cafe_desk import maintenance
    for k in maintenance.TASKS:
        desk.start_job(k)
        run_until_idle(desk)
    assert sorted(desk.stats.data["collection"]["cleaned"]) == sorted(maintenance.TASKS)


def test_settings_hides_art_when_mocha_has_whip(desk, qapp):
    """摩卡擠鮮奶油時看不到拉花：設定視窗不顯示拉花圖案選項"""
    from cafe_desk.settings import SettingsDialog
    dlg = SettingsDialog(desk)
    dlg.show()
    dlg.drink.setCurrentIndex(dlg.drink.findData("mocha"))
    dlg.whip.setChecked(True)
    qapp.processEvents()
    assert not dlg.art.isVisible()
    dlg.whip.setChecked(False)
    qapp.processEvents()
    assert dlg.art.isVisible()
    dlg.drink.setCurrentIndex(dlg.drink.findData("latte"))
    qapp.processEvents()
    assert dlg.art.isVisible()
    dlg.close()
