"""紀錄資料庫：簽章鏈、竄改偵測、成就"""
import sqlite3

import pytest

from cafe_desk import stats


def _cup(score=88.0, drink="latte", **kw):
    c = {"drink": drink, "title": "熱拿鐵", "score": score, "comment": "", "machine": "lever", "milk": "dairy",
         "origin": "kenya", "bean_age": 10, "dose": 18, "art": "heart", "art_q": 0.7, "seed": 3}
    c.update(kw)
    return c


@pytest.fixture
def st(cfg_path):
    s = stats.Stats()
    yield s
    s.db.close()


@pytest.fixture
def reload():
    """重新開一次資料庫（等於下次啟動程式）"""
    opened = []

    def _open():
        opened.append(stats.Stats())
        return opened[-1]
    yield _open
    for s in opened:
        s.db.close()


def test_record_and_reload(st, reload):
    for i in range(5):
        st.record(_cup(80 + i), ["latte"])
    st.record_clean("drip")
    s = reload()
    assert s.tampered == 0
    assert s.data["total"] == 5
    assert s.data["collection"]["cleaned"] == ["drip"]
    assert s.day()["cups"] == 5
    assert {"first_cup", "all_drinks"} <= set(s.data["achievements"])


def test_tamper_is_detected(st, reload):
    for i in range(5):
        st.record(_cup(80 + i), [])
    db = sqlite3.connect(stats.db_path())
    db.execute("UPDATE cups SET score = 100 WHERE id = 2")
    db.execute("DELETE FROM cups WHERE id = 4")
    db.execute("UPDATE achievements SET day = '2020-01-01' WHERE key = 'first_cup'")
    db.commit()
    db.close()
    s = reload()
    assert s.tampered == 3                 # 改分數、刪一筆（下一筆鏈斷）、改成就
    assert s.data["total"] == 3            # 被改的那一筆不採用；被刪的本來就不在
    assert "first_cup" not in s.data["achievements"]
    assert all(r["score"] != 100 for r in s.recent())


def test_appending_after_tamper_keeps_new_rows_valid(st, reload):
    st.record(_cup(), [])
    db = sqlite3.connect(stats.db_path())
    db.execute("UPDATE cups SET score = 1 WHERE id = 1")
    db.commit()
    db.close()
    st.record(_cup(), [])
    s = reload()
    assert s.tampered == 1 and s.data["total"] == 1


def test_achievement_conditions(st):
    assert "perfect" in st.record(_cup(96), [])
    new = []
    for _ in range(5):
        new += st.record(_cup(90), [])
    assert "streak" in new
    assert "rosetta" in st.record(_cup(art="rosetta"), [])
    assert "rosetta" not in st.record(_cup(art="rosetta", art_note="糊"), [])   # 已解鎖也不會重複
