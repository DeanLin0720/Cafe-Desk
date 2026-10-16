"""顧客點單：訂單產生、依訂單改參數、符合度與最後分數"""
import random
from types import SimpleNamespace

import pytest

from cafe_desk import orders
from cafe_desk.drinks import DRINKS, DrinkParams, DrinkResult
from cafe_desk.orders import Order, make_order, order_params, evaluate, finish, mod_pool, MOD_TEXT

from conftest import run_until_idle


def _session(temp=60, foam=30, art="heart", note=""):
    return SimpleNamespace(milk=SimpleNamespace(temp=temp, foam=foam, art=art, art_note=note))


def test_make_order_is_valid():
    rnd = random.Random(5)
    for no in range(300):
        o = make_order(no, rnd)
        assert o.drink in DRINKS
        assert len(o.mods) <= 2
        kinds = [k for k, _ in o.mods]
        assert len(kinds) == len(set(kinds)), "同一類要求只能有一個"
        for m in o.mods:
            assert m in MOD_TEXT
            assert m in mod_pool(o.drink)


def test_no_festival_drink_out_of_season():
    rnd = random.Random(1)
    assert all(not DRINKS[make_order(i, rnd).drink].get("festival") for i in range(300))


def test_order_params_follow_mods():
    rnd = random.Random(0)
    dp = DrinkParams()
    o = Order(1, "Amy", "latte", [("temp", "low"), ("milk", "oat")])
    temps = [order_params(o, dp, rnd).milk_temp for _ in range(200)]
    assert 50 < sum(temps) / len(temps) < 58               # 54 度附近，有手感誤差
    assert order_params(o, dp, rnd).milk_kind == "oat"
    assert dp.milk_temp == 60.0 and dp.milk_kind == "dairy", "不能改到使用者的設定"
    d = order_params(Order(2, "Ken", "affogato", [("scoop", "big")]), dp, rnd)
    assert d.scoop_g == 95.0
    d = order_params(Order(3, "Joe", "iced_latte", [("ice", "less")]), dp, rnd)
    assert d.ice == 2.0


def test_evaluate_match():
    o = Order(1, "Amy", "latte", [("temp", "low")])
    assert evaluate(o, _session(temp=56)) == (100.0, "")
    match, complaint = evaluate(o, _session(temp=68))
    assert match < 80 and complaint == "有點燙"

    o = Order(1, "Amy", "latte", [("art", "rosetta")])
    assert evaluate(o, _session(art="rosetta"))[0] == 100
    assert evaluate(o, _session(art="rosetta", note="糊"))[0] == 50
    assert evaluate(o, _session(art="heart"))[0] == 0

    assert evaluate(Order(1, "Amy", "espresso", []), SimpleNamespace(milk=None))[0] == 100


def test_finish_combines_scores():
    o = Order(1, "Amy", "latte", [("art", "heart")])
    finish(o, _session(art="tulip"), DrinkResult("latte", 90.0, ""))
    assert o.match == 0
    assert o.score == pytest.approx(orders.ORDER_WEIGHT_DRINK * 90)
    assert o.state == "done" and o.reaction and o.complaint


def test_order_flow_in_desk(desk):
    desk.order_mode = True
    desk.auto = True
    for _ in range(3):
        desk.order = None
        desk.new_order()
        o = desk.order
        desk.make_order(False)
        run_until_idle(desk)
        assert o.state in ("done", "leaving")
        assert 0 <= o.score <= 100 and o.reaction
