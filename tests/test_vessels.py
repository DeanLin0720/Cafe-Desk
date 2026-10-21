"""倒液體的物理：液面水平、傾斜角度跟著液量、容器不撞進杯子、上寬下窄的杯子液面上升越來越慢"""
import pytest

from cafe_desk import vessels
from cafe_desk.cups import Cup, CUP_KINDS
from conftest import run_until_idle


@pytest.mark.parametrize("kind", sorted(vessels.SHAPES))
def test_pour_tilt_grows_as_vessel_empties(kind):
    tilts = [vessels.pour_tilt(kind, c) for c in (0.9, 0.7, 0.5, 0.3, 0.1)]
    assert all(a < b for a, b in zip(tilts, tilts[1:])), (kind, tilts)
    for c in (0.8, 0.4, 0.15):                  # 那個角度下，通過倒出口的水平線以下剛好是剩下的液量
        assert vessels.below_lip(kind, vessels.pour_tilt(kind, c)) == pytest.approx(c, abs=0.01)


def test_level_keeps_volume_when_tilted():
    pts = list(vessels.outline("server"))
    for tilt in (0, 30, 70):
        rot = vessels._rotate(pts, tilt)
        y = vessels.level_y(rot, 0.4)
        assert vessels._area(vessels._below(rot, y)) / vessels._area(rot) == pytest.approx(0.4, abs=0.005)


@pytest.mark.parametrize("kind", sorted(CUP_KINDS))
def test_cup_level_rises_slower_near_the_rim(kind):
    cup = Cup(kind, 0, 100)
    ys = [cup.level_y(cup.cap * f) for f in (0, 0.25, 0.5, 0.75, 1.0)]
    assert ys[0] == pytest.approx(cup.liquid_bottom) and ys[-1] == pytest.approx(cup.liquid_top)
    rises = [a - b for a, b in zip(ys, ys[1:])]
    assert all(r > 0 for r in rises)
    assert rises[0] >= rises[-1], "杯子上寬：同樣的量，靠近杯口時液面升得比較少"


@pytest.mark.parametrize("machine,drink", [("desk01", "latte"), ("lever", "latte"), ("desk01", "americano"),
                                           ("desk01", "iced_latte"), ("desk01", "espresso_tonic"),
                                           ("desk01", "pour_over"), ("desk01", "moka_pot"), ("desk01", "siphon")])
def test_vessel_never_dips_into_the_cup(desk, machine, drink):
    """倒的容器（含把手旁）任何一部分都不會低於杯口（容器從杯子上方經過，不會穿過杯子）"""
    desk.set_machine(machine)
    desk.bag["left"] = 250
    assert desk.start_session(drink, True)
    checked = 0
    while desk.busy():
        desk.step(0.05, 0.1)
        ss = desk.session
        st = ss.stage if ss else None
        v = ss.vessel if ss else None
        if v and st is not None and getattr(st, "physics", False) and v.get("alpha", 1) > 0.5:
            low = vessels.lowest_over(v["kind"], v["tilt"], st.scale, v["x"], st.cup_left, st.cup_right)
            if low is not None:
                assert v["y"] + low <= st.cup_top + 0.5, (drink, st.phase, v["y"] + low, st.cup_top)
                checked += 1
    assert checked > 0
    run_until_idle(desk)


@pytest.mark.parametrize("machine", ["desk01", "lever"])
@pytest.mark.parametrize("drink", ["pour_over", "moka_pot", "siphon"])
def test_poured_vessel_stays_inside_the_window(desk, machine, drink):
    """手沖台的壺倒進杯子時，傾斜的壺不會超出視窗右邊（杯子離右緣要留夠位置）"""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QTransform
    desk.set_machine(machine)
    desk.bag["left"] = 250
    assert desk.start_session(drink, True)
    right = 0.0
    while desk.busy():
        desk.step(0.05, 0.1)
        ss = desk.session
        st = ss.stage if ss else None
        v = ss.vessel if ss else None
        if v and getattr(st, "physics", False):
            m = QTransform().rotate(-v["tilt"])
            right = max(right, max(v["x"] + m.map(QPointF(px, py)).x() * st.scale
                                   for px, py in vessels.outline(v["kind"])))
    assert 0 < right <= desk.machine.scene_w - 2, (drink, right, desk.machine.scene_w)
