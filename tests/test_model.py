"""萃取模型 simulate() 的邊界與方向性（只檢查合理，不檢查精確數值）"""
import itertools

import pytest

from cafe_desk.machines import MACHINES
from cafe_desk.model import ROASTS, Params, simulate, shot_comment, style_targets


def test_default_params_make_a_decent_shot():
    r = simulate(Params())
    assert r.score >= 70
    lo, hi, _ = style_targets("中焙")
    assert lo - 2 <= r.ey <= hi + 2
    assert 20 <= r.time <= 40


def test_simulate_stays_in_range():
    """參數掃過設定視窗允許的極端值，結果都要落在合理範圍"""
    for grind, dose, yield_g, temp, pressure, dist, age, roast in itertools.product(
            (150, 300, 500), (14, 18, 22), (20, 36, 60), (85, 93, 100), (6, 9, 12), (0, 100), (0, 10, 60),
            list(ROASTS)):
        p = Params(grind_um=grind, dose=dose, yield_g=yield_g, temp=temp, pressure=pressure, distribution=dist,
                   bean_age=age, roast=roast)
        r = simulate(p)
        assert 0 <= r.score <= 100, p
        assert 0 <= r.channeling <= 0.7, p
        assert 0 < r.ey < ROASTS[roast]["ey_max"], p
        assert r.time > 0 and r.tds > 0, p


@pytest.mark.parametrize("key", list(MACHINES))
def test_every_machine_traits_work(key):
    traits = MACHINES[key].traits
    r = simulate(Params(), traits)
    assert 0 <= r.score <= 100
    assert r.time > 0


def test_finer_grind_extracts_more_and_slower():
    coarse = simulate(Params(grind_um=380))
    fine = simulate(Params(grind_um=240))
    assert fine.ey > coarse.ey
    assert fine.time > coarse.time


def test_hotter_water_extracts_more():
    assert simulate(Params(temp=96)).ey > simulate(Params(temp=88)).ey


def test_bad_distribution_causes_channeling():
    good = simulate(Params(distribution=95))
    bad = simulate(Params(distribution=20))
    assert bad.channeling > good.channeling
    assert bad.score < good.score
    assert shot_comment(simulate(Params(distribution=0, grind_um=180)), Params()) == "有通道效應，酸苦混雜"


def test_stale_beans_score_lower():
    assert simulate(Params(bean_age=70)).score < simulate(Params(bean_age=12)).score


def test_styles_shift_targets():
    lo, hi, tds = style_targets("中焙")
    r_lo, r_hi, r_tds = style_targets("中焙", "ristretto")
    l_lo, l_hi, l_tds = style_targets("中焙", "lungo")
    assert r_lo < lo and r_tds[0] > tds[0]
    assert l_lo > lo and l_tds[1] < tds[1]
