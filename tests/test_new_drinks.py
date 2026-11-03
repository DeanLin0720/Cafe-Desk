"""1.7 加的飲品：咖啡延伸、不用濃縮的飲品、漂浮、日式冰手沖"""
import pytest

from cafe_desk import ingredients
from cafe_desk.drinks import DRINKS, DrinkParams, has_shot, pair_compat, cold_of
from cafe_desk.orders import ORDER_WEIGHTS, PRICES

from conftest import run_until_idle

NEW = ("con_panna", "vienna", "lemon_americano", "orange_coffee", "vanilla_latte", "hazelnut_latte", "coconut_latte",
       "iced_vanilla_latte", "iced_mocha", "iced_caramel_latte", "dirty_latte", "coffee_float", "hot_cocoa", "honey_milk",
       "ginger_milk", "matcha_latte", "tea_latte", "iced_matcha_latte", "milk_tea", "brown_sugar_milk", "italian_soda",
       "cocoa_float", "iced_pour_over")


def test_new_drinks_are_registered():
    for k in NEW:
        assert k in DRINKS and k in ORDER_WEIGHTS and k in PRICES, k


@pytest.mark.parametrize("drink", NEW)
def test_new_drink_runs_to_the_end(desk, unlocked, drink):
    desk.bag["left"] = 200
    left = desk.bag["left"]
    assert desk.start_session(drink, True)
    run_until_idle(desk)
    assert desk.result is not None and 40 < desk.result.score <= 100, desk.result
    if not has_shot(drink):
        assert desk.bag["left"] == left, "不用濃縮的飲品不扣豆子"
        assert desk.shot is None
    assert desk.cup_volume() <= desk.cup.cap, "杯子裝得下"
    desk.host.grab()


def test_noshot_drinks_skip_grinding_and_brewing(desk):
    desk.start_session("hot_cocoa", True)
    names = [type(st).__name__ for st in desk.session.stages]
    assert "PrepStage" not in names and "BrewStage" not in names
    assert names[-2:] == ["ToolStage", "ToolStage"], "最後擠鮮奶油、撒可可粉"
    run_until_idle(desk)
    assert desk.topping.get("whip") == 1.0 and desk.contents["syrup"] > 0


def test_tea_gets_darker_while_steeping(desk, unlocked):
    desk.start_session("tea_latte", True)
    seen = []
    while desk.busy():
        desk.step(0.05, 0.5)
        if desk.session and desk.session.stage_name == "teabag":
            seen.append(desk.noshot_look("tea_latte")[0])
    assert len(set(seen)) > 3, "茶包泡著，茶色越來越深"


def test_float_ball_stays_on_top(desk, unlocked):
    desk.start_session("coffee_float", True)
    run_until_idle(desk)
    ic = desk.icecream
    assert ic and ic["landed"] and ic["float"]
    assert ic["y"] < desk.liquid_surface_y(), "冰淇淋球浮在液面上"
    assert desk.surface_y() == desk.liquid_surface_y(), "冰塊照液面浮，不是照球頂"


def test_noshot_drinks_never_pair():
    dp = DrinkParams()
    assert not pair_compat("hot_cocoa", dp, "latte", dp)
    assert not pair_compat("espresso", dp, "milk_tea", dp)
    assert pair_compat("iced_mocha", dp, "vienna", dp)


def test_new_ingredients():
    assert ingredients.needs("matcha_latte") == {"milk": 1, "matcha": 1}
    assert ingredients.needs("italian_soda") == {"berry": 1, "soda": 1}
    assert ingredients.needs("lemon_americano") == {"lemon": 1}
    assert ingredients.needs("coffee_float") == {"icecream": 1}
    assert ingredients.needs("coconut_latte") == {"coconut": 1}, "椰子拿鐵固定用椰奶"
    assert ingredients.needs("iced_mocha", [("whip", "no")]) == {"milk": 1, "choc": 1}, "不擠鮮奶油就不撒可可粉"
    assert "coconut_latte" in ingredients.drinks_using("coconut")
    for k in NEW:
        for key in ingredients.needs(k):
            assert key in ingredients.ALL, (k, key)
    assert cold_of("iced_latte") == "cold_milk" and cold_of("espresso_tonic") == "tonic"
