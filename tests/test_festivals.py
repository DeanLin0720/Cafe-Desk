"""季節與節日的日期判斷"""
import datetime

import pytest

from cafe_desk import festivals
from cafe_desk.drinks import DRINKS, AUTO_WEIGHTS


D = datetime.date


@pytest.mark.parametrize("day, key", [
    (D(2026, 2, 6), None), (D(2026, 2, 7), "valentine"), (D(2026, 2, 14), "valentine"), (D(2026, 2, 15), None),
    (D(2026, 10, 14), None), (D(2026, 10, 15), "halloween"), (D(2026, 10, 31), "halloween"), (D(2026, 11, 1), None),
    (D(2026, 12, 9), None), (D(2026, 12, 10), "christmas"), (D(2027, 12, 26), "christmas"), (D(2026, 12, 27), None),
])
def test_festival_dates(day, key):
    assert festivals.festival(day) == key


def test_festival_drinks_exist():
    for _, drink, _, _, _ in festivals.FESTIVALS.values():
        assert drink in DRINKS and DRINKS[drink].get("festival")


@pytest.mark.parametrize("month, season", [(1, "winter"), (3, "spring"), (6, "summer"), (8, "summer"),
                                           (9, "autumn"), (11, "autumn"), (12, "winter")])
def test_season(month, season):
    assert festivals.season(D(2026, month, 10)) == season


def test_adjust_weights():
    summer = festivals.adjust_weights(AUTO_WEIGHTS, DRINKS, D(2026, 7, 1))
    winter = festivals.adjust_weights(AUTO_WEIGHTS, DRINKS, D(2026, 1, 20))
    assert summer["iced_latte"] > winter["iced_latte"]
    assert winter["latte"] > summer["latte"]
    xmas = festivals.adjust_weights(AUTO_WEIGHTS, DRINKS, D(2026, 12, 20))
    assert xmas["gingerbread_latte"] >= 0.18
    assert "pumpkin_latte" not in xmas


def test_env_date_override(monkeypatch):
    monkeypatch.setenv("CAFE_DESK_DATE", "2030-02-10")
    assert festivals.today() == D(2030, 2, 10)
    monkeypatch.setenv("CAFE_DESK_DATE", "not-a-date")
    assert festivals.today() == D.today()
