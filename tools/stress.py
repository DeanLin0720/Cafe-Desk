"""壓力測試：每台機器做完所有飲品、四種清潔、豆子用完、點單、開紀錄視窗

    python tools/stress.py [亂數種子] [機器,機器]
    在 tools/out/ 產生暫存設定檔與資料庫；有錯誤會丟例外
"""
import sys, os, json, random, time
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = os.path.join(_ROOT, "tools", "out")
os.makedirs(_OUT, exist_ok=True)

os.environ.update(QT_QPA_PLATFORM="offscreen", CAFE_DESK_NO_AUDIO="1")
os.environ.setdefault("CAFE_DESK_DATE", "2026-10-20")
sys.path.insert(0, _ROOT)
from PySide6.QtWidgets import QApplication
app = QApplication([])
from cafe_desk import paths, desk, drinks, orders, festivals, maintenance
random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
machines = sys.argv[2].split(",") if len(sys.argv) > 2 else ["desk01", "lever", "compact", "allinone"]
res = []
fd = festivals.festival_drink()
for mk in machines:
    paths.CONFIG_PATH = os.path.join(_OUT, f"cfg_st_{mk}.json")
    for p in (paths.CONFIG_PATH, paths.CONFIG_PATH.replace(".json", "_records.db")):
        if os.path.exists(p): os.remove(p)
    json.dump({"x": 0, "y": 0, "machine": mk, "pf_used": True}, open(paths.CONFIG_PATH, "w"))
    w = desk.CafeDesk(); w.show_window(); w.warming = False; w.boiler.temp = w.params.temp
    def run(fn):
        r = fn(); n = 0
        while w.busy():
            w.step(0.05, 0.5); n += 1
            if n % 15 == 0:
                w.host.grab()
            assert n < 8000, "stuck"
        w.host.grab()
        return r
    for d in list(drinks.DRINK_KEYS) + ([fd] if fd else []):
        w.bag["left"] = 250
        full = random.random() < 0.3
        w.dp.art = random.choice(["auto", "heart", "tulip", "rosetta"])
        w.dp.milk_kind = random.choice(list(drinks.MILK_KINDS))
        run(lambda: w.start_session(d, full))
        r = w.result
        res.append((mk, d, full, round(r.score), r.comment))
    # 清潔保養
    print(mk, "maint before", {k: v for k, v in w.maint.items() if k != "done"}, "due", maintenance.due(w.maint))
    for k in maintenance.TASKS:
        run(lambda: w.start_job(k))
    print(mk, "maint after", {k: v for k, v in w.maint.items() if k != "done"})
    # 豆子用完
    w.bag["left"] = 5; w.auto = False
    ok = w.start_session("espresso", False)
    print(mk, "empty bag start ->", ok, w.notice[0] if w.notice else None)
    w.open_bag("kenya"); print(mk, "new bag", w.params.roast, w.params.bean_age, w.params.origin)
    # 點單
    w.order_mode = True; w.auto = True
    for i in range(4):
        w.order = None; w.new_order(); o = w.order
        run(lambda: w.make_order(False))
        res.append((mk, "ORDER", o.title, o.mod_lines, round(o.score), o.reaction))
    st = w.stats.data
    print(mk, "achievements", list(st["achievements"]), "today", st["days"][festivals.today().isoformat()]["cups"],
          "art", list(st["collection"]["art"]), "toasts", len(w.toasts))
    w.open_records(); app.processEvents(); w.records_dlg.close()
    w.host.close(); w.deleteLater()
for r in res: print(r)
