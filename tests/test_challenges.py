"""每日／每週挑戰：挑戰清單、進度、蓋章與稱號"""
import pytest

from cafe_desk import challenges as ch, stats
from cafe_desk.i18n import EN

CUP = {"drink": "latte", "title": "拿鐵", "comment": "", "order": True, "price": 100, "tip": 0, "wait": 10.0, "size": "M"}


def test_sets_are_deterministic_and_scaled():
    a = ch.daily_set("2026-08-01", 5, ["latte", "mocha"])
    assert a == ch.daily_set("2026-08-01", 5, ["latte", "mocha"])
    assert len(a) == ch.DAILY_N and len({i["kind"] for i in a}) == ch.DAILY_N
    assert "festival" not in {i["kind"] for i in a}                       # 沒有節日飲品不會出
    assert ch.goal_of("orders", 10) > ch.goal_of("orders", 1)
    assert ch.goal_of("festival", 10) == 1 and ch.goal_of("revenue", 1) % 100 == 0
    w1, w2 = ch.weekly_set("2026-08-03", 3), ch.weekly_set("2026-08-09", 3)    # 同一週（週一到週日）
    assert w1 == [dict(i) for i in w2] and len(w1) == ch.WEEKLY_N
    assert ch.week_days("2026-08-05")[0] == "2026-08-03" and ch.week_days("2026-08-05")[-1] == "2026-08-09"


def test_every_text_has_english():
    for tpl in [t for _, t in {**ch.DAILY, **ch.WEEKLY}.values()] + [n for _, n in ch.TITLES]:
        assert tpl in EN, tpl


def test_progress_and_stamps(desk):
    s = desk.stats
    for score in (95, 92, 80):
        s.record(dict(CUP, score=score, size="L"), [])
    day = "2026-08-01"
    assert ch.progress({"kind": "hi", "goal": 3}, s, day) == (2, 3, False)
    assert ch.progress({"kind": "hi_drink", "drink": "latte", "goal": 2}, s, day)[0] == 2
    assert ch.progress({"kind": "large", "goal": 5}, s, day)[0] == 3
    assert ch.progress({"kind": "w_days", "goal": 4}, s, day)[0] == 1
    assert ch.done({"kind": "orders", "goal": 3}, s, day)
    s.record_walkout("latte")
    assert ch.progress({"kind": "clean", "goal": 2}, s, day)[2]                # 有客人離開：做不成
    assert not ch.done({"kind": "clean", "goal": 2}, s, day)
    assert ch.stamps_of(["d:x:0", "d:x:1", "w:x:0"]) == 2 + ch.WEEKLY_STAMPS
    assert ch.title_index(9) == -1 and ch.title_index(10) == 0 and ch.next_title(10)[1] == 20
    assert ch.card_fill(23) == (3, 2)


def test_challenge_completion_is_persistent_and_signed(desk):
    desk.cfg["challenge_set"] = {"day": "2026-08-01", "level": 1, "week": ch.week_start("2026-08-01"),
                                 "daily": [{"id": "d:2026-08-01:0", "kind": "orders", "goal": 2}],
                                 "weekly": []}
    desk.save_cup(dict(CUP, score=88))
    assert desk.stats.data["challenges"] == []
    desk.save_cup(dict(CUP, score=88))
    assert desk.stats.data["challenges"] == ["d:2026-08-01:0"]
    assert any("挑戰完成" in t[0] for t in desk.toasts)
    n = len(desk.toasts)
    desk.save_cup(dict(CUP, score=88))                                         # 不會重複蓋章
    assert len(desk.toasts) == n and desk.stats.data["challenges"] == ["d:2026-08-01:0"]
    desk.stats.load()
    assert desk.stats.data["challenges"] == ["d:2026-08-01:0"] and desk.stats.tampered == 0


def test_challenge_set_is_cached_for_the_day(desk):
    a = desk.challenge_set()
    assert a is desk.cfg["challenge_set"] and len(a["daily"]) == ch.DAILY_N and len(a["weekly"]) == ch.WEEKLY_N
    desk.shop_level = lambda: 10                                               # 當天升級也不換題目
    assert desk.challenge_set()["daily"] == a["daily"]


def test_challenge_tab_renders(desk, qapp):
    desk.open_records()
    dlg = desk.records_dlg
    names = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert "成就與挑戰" in names and "說明" not in names
    assert "挑戰" in [dlg.achv_sub.tabText(i) for i in range(dlg.achv_sub.count())]
    dlg.close()
