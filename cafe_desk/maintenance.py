"""清潔保養：沖煮頭逆洗、蒸氣管／奶泡機清潔、滴水盤、敲渣盒

每杯累積髒污計數；超過門檻會在狀態列提醒，太久沒清會開始扣分。
右鍵「清潔保養」可以手動清；自動模式的咖啡師會在需要時自己清。
"""

# key：(名稱, 提醒門檻, 開始扣分的門檻, 動作文字)
TASKS = {
    "backflush": ("逆洗沖煮頭", 25, 30, "逆洗中…"),
    "wand": ("清潔蒸氣管", 6, 8, "清潔蒸氣管…"),
    "drip": ("倒滴水盤", 320, 10 ** 9, "倒掉滴水盤…"),
    "knock": ("清空敲渣盒", 10, 10 ** 9, "清空敲渣盒…"),
}
DURATION = {"backflush": 9.0, "wand": 3.2, "drip": 1.6, "knock": 1.6}
DRIP_PER_SHOT = 12.0        # 每杯滴到滴水盤的水（ml）
DRIP_FULL = 400.0


def task_name(key, traits=None):
    if key == "wand" and traits is not None and traits.milk == "frother":
        return "清洗奶泡機"
    return TASKS[key][0]


def default_state():
    return {"backflush": 0.0, "wand": 0.0, "drip": 0.0, "knock": 0.0, "done": []}


def due(state):
    """需要清的項目（依門檻）"""
    return [k for k, (_, warn, _, _) in TASKS.items() if state.get(k, 0) >= warn]


def penalty(state, drink_is_milk):
    """(扣分, 評語 key)：沖煮頭太髒苦澀、蒸氣管太髒奶味變差"""
    pen, notes = 0.0, []
    over = state.get("backflush", 0) - TASKS["backflush"][2]
    if over > 0:
        pen += min(12.0, 0.6 * over + 2)
        notes.append("backflush")
    if drink_is_milk:
        over = state.get("wand", 0) - TASKS["wand"][2]
        if over > 0:
            pen += min(10.0, 1.2 * over + 2)
            notes.append("wand")
    return pen, notes


class Job:
    """一次清潔動作（佔用咖啡機，有自己的時間軸）"""

    def __init__(self, kind):
        self.kind = kind
        self.t = 0.0
        self.total = DURATION[kind]
        self.done = False

    def update(self, dt):
        self.t += dt
        if self.t >= self.total:
            self.done = True

    @property
    def pumping(self):
        """逆洗：開 1.2 秒、停 0.6 秒，共 5 次"""
        if self.kind != "backflush":
            return False
        c = self.t % 1.8
        return c < 1.2 and self.t < 9.0

    @property
    def cycle(self):
        return min(5, int(self.t // 1.8) + 1)
