"""季節與節日的日期判斷"""
import datetime

import pytest

from cafe_desk import festivals
from cafe_desk.drinks import DRINKS
from cafe_desk.orders import ORDER_WEIGHTS


D = datetime.date


@pytest.mark.parametrize("day, key", [
    (D(2026, 2, 6), None), (D(2026, 2, 7), "valentine"), (D(2026, 2, 14), "valentine"), (D(2027, 2, 15), None),
    (D(2026, 10, 14), None), (D(2026, 10, 15), "halloween"), (D(2026, 10, 31), "halloween"), (D(2026, 11, 1), None),
    (D(2026, 12, 9), None), (D(2026, 12, 10), "christmas"), (D(2027, 12, 26), "christmas"), (D(2026, 12, 27), None),
    (D(2026, 12, 29), None), (D(2026, 12, 30), "newyear"), (D(2027, 1, 1), "newyear"), (D(2027, 1, 2), "newyear"),
    (D(2027, 1, 3), None), (D(2026, 3, 7), "white_day"), (D(2026, 3, 15), None), (D(2026, 4, 1), "children"),
    (D(2027, 4, 5), None), (D(2026, 8, 1), None), (D(2026, 8, 6), "father"), (D(2026, 8, 8), "father"),
    (D(2026, 9, 24), None), (D(2026, 9, 25), "coffee_day"), (D(2026, 10, 1), "coffee_day"), (D(2026, 10, 2), None),
    # 不固定日期：春節（2026 初一是 2/17，小年夜 2/15 到初五 2/22）、復活節（2026/4/5）、母親節（2026/5/10）、感恩節（2026/11/26）
    (D(2026, 2, 14), "valentine"), (D(2026, 2, 15), "spring_festival"), (D(2026, 2, 22), "spring_festival"), (D(2026, 2, 23), None),
    (D(2029, 2, 12), "spring_festival"), (D(2029, 2, 10), "valentine"),          # 2029 春節 2/13：重疊的日子春節優先
    (D(2026, 4, 4), "children"), (D(2026, 4, 5), "easter"), (D(2026, 4, 6), "easter"), (D(2026, 4, 7), None),
    (D(2027, 3, 22), "easter"), (D(2027, 3, 28), "easter"),
    (D(2026, 5, 3), None), (D(2026, 5, 4), "mother"), (D(2026, 5, 10), "mother"), (D(2026, 5, 11), None),
    (D(2026, 11, 22), None), (D(2026, 11, 23), "thanksgiving"), (D(2026, 11, 29), "thanksgiving"), (D(2026, 11, 30), None),
    (D(2051, 2, 1), None),                                                       # 農曆對照表外的年份就不過春節
])
def test_festival_dates(day, key):
    assert festivals.festival(day) == key


def test_festival_drinks_exist():
    for key, (_, drink, _, _, _) in festivals.FESTIVALS.items():
        assert drink in DRINKS and DRINKS[drink].get("festival") == key


def test_movable_dates():
    """照規則推算的日期：母親節＝5 月第二個星期日、感恩節＝11 月第四個星期四、復活節公式"""
    assert festivals.RULES["mother"](2026) == D(2026, 5, 10) and festivals.RULES["mother"](2027) == D(2027, 5, 9)
    assert festivals.RULES["thanksgiving"](2026) == D(2026, 11, 26) and festivals.RULES["thanksgiving"](2027) == D(2027, 11, 25)
    assert [festivals.easter(y) for y in (2024, 2025, 2026, 2027, 2038)] == [
        D(2024, 3, 31), D(2025, 4, 20), D(2026, 4, 5), D(2027, 3, 28), D(2038, 4, 25)]


def test_lunar_new_year_table_is_plausible():
    """春節對照表：每年都在 1/21–2/20，相鄰兩年差一個農曆年（354／355 天）或閏年（383／384 天）"""
    years = sorted(festivals.LUNAR_NEW_YEAR)
    assert years == list(range(years[0], years[-1] + 1)) and years[0] <= 2026 and years[-1] >= 2050
    days = [festivals.lunar_new_year(y) for y in years]
    assert all(D(d.year, 1, 21) <= d <= D(d.year, 2, 20) for d in days)
    assert all((b - a).days in (354, 355, 383, 384) for a, b in zip(days, days[1:]))


def test_festivals_do_not_overlap():
    """2026–2050 逐日檢查：同一天只有 PRIORITY 允許的重疊（春節與情人節、兒童節與復活節），每個節日每年都出現"""
    allowed = ({"spring_festival", "valentine"}, {"children", "easter"})
    for year in range(2026, 2051):
        seen = set()
        day = D(year, 1, 1)
        while day.year == year:
            hits = festivals.festivals_on(day)
            assert len(hits) <= 1 or set(hits) in allowed, (day, hits)
            if hits:
                seen.add(festivals.festival(day))
            day += datetime.timedelta(days=1)
        assert seen == set(festivals.FESTIVALS), (year, set(festivals.FESTIVALS) - seen)


def test_festival_icons_paint(desk):
    """每個節日的狀態列小圖示都畫得出東西"""
    from PySide6.QtGui import QImage, QPainter
    for key, (_, _, icon, _, _) in festivals.FESTIVALS.items():
        img = QImage(24, 24, QImage.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        desk.paint_festival_icon(p, icon, 12, 12)
        p.end()
        assert any(img.pixel(x, y) >> 24 for x in range(24) for y in range(24)), key


@pytest.mark.parametrize("month, season", [(1, "winter"), (3, "spring"), (6, "summer"), (8, "summer"),
                                           (9, "autumn"), (11, "autumn"), (12, "winter")])
def test_season(month, season):
    assert festivals.season(D(2026, month, 10)) == season


def test_adjust_weights():
    summer = festivals.adjust_weights(ORDER_WEIGHTS, DRINKS, D(2026, 7, 1))
    winter = festivals.adjust_weights(ORDER_WEIGHTS, DRINKS, D(2026, 1, 20))
    assert summer["iced_latte"] > winter["iced_latte"]
    assert winter["latte"] > summer["latte"]
    xmas = festivals.adjust_weights(ORDER_WEIGHTS, DRINKS, D(2026, 12, 20))
    assert xmas["gingerbread_latte"] >= 0.18
    assert "pumpkin_latte" not in xmas


def test_env_date_override(monkeypatch):
    monkeypatch.setenv("CAFE_DESK_DATE", "2030-02-10")
    assert festivals.today() == D(2030, 2, 10)
    monkeypatch.setenv("CAFE_DESK_DATE", "not-a-date")
    assert festivals.today() == D.today()


def test_status_icon_only_while_making_festival_drink(desk, monkeypatch):
    from conftest import run_until_idle
    monkeypatch.setenv("CAFE_DESK_DATE", "2026-10-20")      # 萬聖節期間
    assert desk.status_festival() is None                   # 節日期間但沒在做節日飲品
    desk.start_session("latte", False)
    assert desk.status_festival() is None
    run_until_idle(desk)
    desk.start_session("pumpkin_latte", False)
    assert desk.status_festival() == "halloween"
    run_until_idle(desk)
    assert desk.status_festival() is None                   # 做完就收起來


def test_guide_lists_every_festival(qapp, monkeypatch):
    """說明頁的節日表：每個節日都列出今年的日期與限定飲品，今天的節日標「進行中」"""
    from PySide6.QtWidgets import QLabel
    from cafe_desk.records import RecordsDialog
    monkeypatch.setenv("CAFE_DESK_DATE", "2026-02-18")
    page = RecordsDialog.guide_tab()
    texts = [lab.text() for lab in page.findChildren(QLabel)]
    for name, drink, *_ in festivals.FESTIVALS.values():
        assert any(name in t for t in texts) and any(t == DRINKS[drink]["name"] for t in texts), name
    assert "2/15–2/22" in texts and "12/30–1/2" in texts and "11/23–11/29" in texts
    assert sum("進行中" in t for t in texts) == 1 and any("春節" in t and "進行中" in t for t in texts)
