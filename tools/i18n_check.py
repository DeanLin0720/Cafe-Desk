"""檢查還沒有英文翻譯的介面文字（T("…") 的樣板與資料表裡的名稱）

    python tools/i18n_check.py      列出缺少的項目；沒有輸出代表都翻好了
"""
import ast
import glob
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
from cafe_desk.i18n import EN                                        # noqa: E402
from cafe_desk import drinks, beans, maintenance, festivals, stats, orders, workflow, brew   # noqa: E402
from cafe_desk.machines import MACHINES                              # noqa: E402


def has_cjk(s):
    return any("一" <= ch <= "鿿" for ch in s)


missing = set()
for f in glob.glob(os.path.join(_ROOT, "cafe_desk", "**", "*.py"), recursive=True):
    tree = ast.parse(open(f, encoding="utf-8").read())
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "T" and n.args:
            for c in ast.walk(n.args[0]):
                if isinstance(c, ast.Constant) and isinstance(c.value, str) and has_cjk(c.value) \
                        and c.value not in EN:
                    missing.add(c.value)
data = [v["name"] for v in drinks.DRINKS.values()] + list(drinks.ART_NAMES.values())
data += [v["name"] for v in drinks.MILK_KINDS.values()] + [v["prefix"] for v in drinks.MILK_KINDS.values()]
data += [v["name"] for v in drinks.SYRUPS.values()] + list(drinks.PourStage.LABEL.values())
data += [v[3] for v in drinks.ToolStage.KINDS.values()]
data += [x for o in beans.ORIGINS.values() for x in o[:3]]
data += [t[0] for t in maintenance.TASKS.values()] + [t[3] for t in maintenance.TASKS.values()]
data += [v[0] for v in festivals.FESTIVALS.values()]
data += [x for a in stats.ACHIEVEMENTS for x in a[1:]]
data += list(orders.MOD_TEXT.values()) + list(orders.CUSTOMERS) + list(workflow.STATUS.values())
data += [m.name for m in MACHINES.values()] + [m.traits.summary for m in MACHINES.values()]
data += list(brew.METHODS.values())
missing |= {d for d in data if d and has_cjk(d) and d not in EN}
for m in sorted(missing):
    print(repr(m))
sys.exit(1 if missing else 0)
