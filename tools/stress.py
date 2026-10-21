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
from cafe_desk import paths, desk, drinks, orders, festivals, maintenance, brew
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
        if d == "cold_drip":                         # 第一次只架好冰滴塔：快轉滴完再倒一杯
            w.cold["start"] -= w.cold["dur"]
            run(lambda: w.start_session(d, full))
        r = w.result
        res.append((mk, d, full, round(r.score), r.comment))
    # 清潔保養（最後一杯是冰滴，要切回咖啡機才清得到）
    w.set_method("espresso")
    print(mk, "maint before", {k: v for k, v in w.maint.items() if k != "done"}, "due", maintenance.due(w.maint))  # 這台的
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
    w.cold = brew.new_cold_batch(w.dp, w.params.roast, w.params.bean_age, w.bag["origin"])   # 有冰滴才會有人點
    w.cold.update(done=True, servings=brew.COLD_SERVINGS)
    for drink in ("latte", "pour_over", "cold_drip", "moka_pot", "siphon", "iced_americano", None, None):
        w.order = None; w.new_order(); o = w.order
        if drink:                                    # 指定幾杯，確定三種沖煮方式都會自動切換
            o.drink, o.mods, o.price = drink, [], orders.price_of(drink)
        run(lambda: w.make_order())
        assert w.method == drinks.method_of(o.drink), (o.drink, w.method)
        res.append((mk, "ORDER", o.title, o.mod_lines, round(o.score), o.reaction))
    w.set_method("espresso")
    st = w.stats.data
    print(mk, "achievements", list(st["achievements"]), "today", st["days"][festivals.today().isoformat()]["cups"],
          "art", list(st["collection"]["art"]), "toasts", len(w.toasts))
    w.open_records(); app.processEvents(); w.records_dlg.close()
    w.host.close(); w.deleteLater()
for r in res: print(r)
