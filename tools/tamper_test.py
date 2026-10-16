"""紀錄資料庫的防竄改測試：做幾杯 → 用 SQLite 改分數、刪一筆、改成就日期 → 重新讀取應偵測到 3 筆

    python tools/tamper_test.py
"""
import sys, os, json, sqlite3
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = os.path.join(_ROOT, "tools", "out")
os.makedirs(_OUT, exist_ok=True)

os.environ.update(QT_QPA_PLATFORM="offscreen", CAFE_DESK_NO_AUDIO="1", CAFE_DESK_DATE="2026-10-20")
sys.path.insert(0, _ROOT)
from PySide6.QtWidgets import QApplication
app = QApplication([])
from cafe_desk import paths, desk, stats
d = os.path.join(_OUT, "tamper"); os.makedirs(d, exist_ok=True)
for f in os.listdir(d): os.remove(os.path.join(d, f))
paths.CONFIG_PATH = os.path.join(d, "cafe_desk.json")
json.dump({"achievements": {"first_cup": "2026-10-15", "perfect": "2026-10-16"}}, open(os.path.join(d, "cafe_desk_stats.json"), "w"))
json.dump({"x": 0, "y": 0, "machine": "lever"}, open(paths.CONFIG_PATH, "w"))
w = desk.CafeDesk(); w.show_window(); w.warming = False; w.boiler.temp = w.params.temp
print("migrated:", w.stats.data["achievements"], os.listdir(d))
for dr in ("espresso", "latte", "pumpkin_latte", "americano", "mocha"):
    w.start_session(dr, False)
    while w.busy(): w.step(0.05, 0.5)
w.start_job("drip")
while w.busy(): w.step(0.05, 0.5)
print("total", w.stats.data["total"], "today", w.stats.day()["cups"], "art", list(w.stats.data["collection"]["art"]), "cleaned", w.stats.data["collection"]["cleaned"])
s2 = stats.Stats(); print("reload total", s2.data["total"], "tampered", s2.tampered, "ach", sorted(s2.data["achievements"]))
db = sqlite3.connect(stats.db_path())
print(db.execute("select id, drink, score from cups").fetchall())
db.execute("update cups set score = 100 where id = 2"); db.execute("delete from cups where id = 4")
db.execute("update achievements set day='2020-01-01' where key='first_cup'"); db.commit()
s3 = stats.Stats(); print("after tamper total", s3.data["total"], "tampered", s3.tampered, "ach", sorted(s3.data["achievements"]))
w.stats = s3; w.open_records(); app.processEvents(); w.records_dlg.grab().save(os.path.join(_OUT, "tamper_dlg.png"))
from PySide6.QtWidgets import QTabWidget
tw = w.records_dlg.findChild(QTabWidget); tw.setCurrentIndex(2); app.processEvents(); w.records_dlg.grab().save(os.path.join(_OUT, "tamper_recent.png"))
