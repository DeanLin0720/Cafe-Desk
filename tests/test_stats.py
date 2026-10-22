"""紀錄資料庫：簽章鏈、竄改偵測、成就"""
import sqlite3

import pytest

from cafe_desk import stats


def _cup(score=88.0, drink="latte", **kw):
    """預設是為客人做的一杯（成就只算訂單）"""
    c = {"drink": drink, "title": "熱拿鐵", "score": score, "comment": "", "machine": "lever", "milk": "dairy",
         "origin": "kenya", "bean_age": 10, "dose": 18, "art": "heart", "art_q": 0.7, "seed": 3, "order": True}
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
    for _ in range(stats.TIER_GROUPS["streak"][0][1]):     # 銅牌門檻（連續幾張 85 分以上）
        new += st.record(_cup(90), [])
    assert "streak" in new
    assert "rosetta" in st.record(_cup(art="rosetta"), [])
    assert "rosetta" not in st.record(_cup(art="rosetta", art_note="糊"), [])   # 已解鎖也不會重複


def _old_db(path, n=3):
    """1.1 版的資料庫：cups 只有前 19 欄，簽章也只算這 19 欄"""
    old = stats.CUP_FIELDS[:stats.CUP_FIELD_VERSIONS[0]]
    db = sqlite3.connect(path)
    cols = ", ".join(f"{c} {'REAL' if c in stats.REAL_FIELDS else 'TEXT'}" for c in old)
    db.execute(f"CREATE TABLE cups (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols}, prev TEXT, sig TEXT)")
    prev = ""
    for i in range(n):
        row = {k: None for k in old}
        row.update(ts="2026-07-31T10:00:00", day="2026-07-31", drink="latte", title="熱拿鐵", score=85.0 + i,
                   comment="", machine="lever", is_order="1", mods="0", match=100.0)
        values = [row[k] for k in old]
        sig = stats._sign(prev, values)
        db.execute(f"INSERT INTO cups ({', '.join(old)}, prev, sig) VALUES ({', '.join('?' * (len(old) + 2))})",
                   values + [prev, sig])
        prev = sig
    db.commit()
    db.close()


def test_old_database_is_migrated(cfg_path, reload):
    _old_db(stats.db_path())
    s = reload()
    have = {r[1] for r in s.db.execute("PRAGMA table_info(cups)")}
    assert set(stats.CUP_FIELDS) <= have, "舊資料庫要 ALTER TABLE 補上新欄位"
    assert s.tampered == 0, "舊列新欄位是 NULL，簽章要用當時的欄位數驗證"
    assert s.data["total"] == 3 and s.day("2026-07-31")["revenue"] == 0
    s.record(_cup(90, order=True, price=120, tip=12, wait=33.3), [])
    s2 = reload()
    assert s2.tampered == 0 and s2.data["total"] == 4
    d = s2.day()
    assert d["revenue"] == 132 and d["waited"] == 1 and d["wait_sum"] == pytest.approx(33.3)


def test_old_row_with_new_fields_filled_is_tampered(cfg_path, reload):
    _old_db(stats.db_path(), n=1)
    reload().db.close()                         # 補上欄位
    db = sqlite3.connect(stats.db_path())
    db.execute("UPDATE cups SET price = 9999 WHERE id = 1")
    db.commit()
    db.close()
    assert reload().tampered == 1


def test_revenue_walkouts_and_business_achievements(st, reload):
    new = []
    n = stats.TIER_GROUPS["no_walkout"][0][1]                # 20 位、每位 $154 → 營業額 $3,080
    for _ in range(n):
        new += st.record(_cup(90, order=True, price=140, tip=14, wait=20.0), [])
    assert "no_walkout" in new and "good_business" not in new, "銅牌營業額 $5,000 還沒到"
    for _ in range(14):
        new += st.record(_cup(90, order=True, price=140, tip=14, wait=20.0), [])
    assert "good_business" in new
    st.record_walkout("latte")
    s = reload()
    assert s.tampered == 0
    assert s.day()["revenue"] == (n + 14) * 154 and s.day()["walkouts"] == 1
    assert st.record(_cup(80), []) == []


def test_walkout_blocks_no_walkout(st):
    st.record_walkout("latte")
    new = []
    for _ in range(15):
        new += st.record(_cup(80, order=True, price=100, tip=0, wait=50.0), [])
    assert "no_walkout" not in new


def test_tier_groups_are_consistent():
    keys = [k for k, _, _ in stats.ACHIEVEMENTS]
    assert len(keys) == len(set(keys))
    for group, tiers in stats.TIER_GROUPS.items():
        assert len(tiers) == 3
        assert [n for _, n in tiers] == sorted(n for _, n in tiers), "門檻要由低到高"
        assert all(k in keys for k, _ in tiers)


def test_tiers_unlock_in_order(st):
    new = []
    for _ in range(60):                                      # 銅：50 杯、一天 40 杯；連續好杯 10／30／60
        new += st.record(_cup(90), [])
    assert {"ten_cups", "busy_day", "streak", "streak_10", "streak_20"} <= set(new)
    assert "hundred_cups" not in new and "busy_day_40" not in new
    assert set(st.tier_values()) == set(stats.TIER_GROUPS)


def test_day_streak(st, monkeypatch):
    for day in ("2026-07-29", "2026-07-30", "2026-07-31"):
        st.day(day)["cups"] = 1
    assert st.day_streak() == 3                    # 今天還沒做：算到昨天
    st.record(_cup(), [])
    assert st.day_streak() == 4
    st.data["days"]["2026-07-30"]["cups"] = 0
    assert st.day_streak() == 2


def test_new_achievements(st, reload, monkeypatch):
    assert "first_pourover" in st.record(_cup(80, drink="pour_over"), [])
    assert "pourover_90" in st.record(_cup(91, drink="pour_over"), [])
    assert "bloom" in st.record(_cup(86, drink="pour_over", bloom_ok=True), [])
    for _ in range(10):
        new = st.record_bag("kenya")
    assert new == ["bags_10"]
    assert st.unlock("rush") == ["rush"] and st.unlock("rush") == []
    monkeypatch.setattr(stats, "clock_hour", lambda: 6)
    assert "early_bird" in st.record(_cup(), [])
    monkeypatch.setattr(stats, "clock_hour", lambda: 2)
    assert "night_owl" in st.record(_cup(), [])
    for m in ("desk01", "lever", "compact"):
        st.record(_cup(92, machine=m), [])
    assert "machines_90" in st.record(_cup(92, machine="allinone"), [])
    s = reload()
    assert s.data["collection"]["bags"] == 10 and s.tampered == 0
    assert s.data["collection"]["machine_best"]["allinone"] == 92


def test_only_orders_unlock_cup_achievements(st, monkeypatch):
    """手動、自動做的杯子不解跟杯子有關的成就；保養、開豆子照舊；連續天數看有沒有營業"""
    monkeypatch.setattr(stats, "clock_hour", lambda: 6)
    for _ in range(12):
        assert st.record(_cup(97, order=False, drink="pour_over", bloom_ok=True), []) == []
    assert st.data["total"] == 12 and st.data["order_total"] == 0
    assert st.data["collection"]["drinks"]["pour_over"]["count"] == 12, "圖鑑照樣記每一杯"
    for kind in ("backflush", "wand", "drip", "knock"):
        st.record_clean(kind)
    assert st.unlocked("clean")
    got = st.record(_cup(97, drink="pour_over", bloom_ok=True), [])
    assert {"first_cup", "first_pourover", "pourover_90", "bloom", "perfect", "early_bird"} <= set(got)
    for day in ("2026-07-29", "2026-07-30", "2026-07-31"):
        st.day(day)["cups"] = 5                     # 那幾天只有自己做、沒有營業
    assert st.day_streak() == 4 and st.day_streak("orders") == 1


def test_tips_and_serve_30(st):
    new = []
    for _ in range(50):
        new += st.record(_cup(95, order=True, price=100, tip=20, wait=10.0), [])
    assert {"tips_500", "serve_30", "no_walkout", "no_walkout_30"} <= set(new)
    assert "no_walkout_50" not in new, "金牌要 100 位"
    assert st.day()["tips"] == 1000
