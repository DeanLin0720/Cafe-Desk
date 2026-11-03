"""沖煮頭：每個沖煮頭（每杯）各自一份的狀態。

單頭機只有一個 BrewHead；雙頭機有兩個（CafeDesk.heads）。CafeDesk 上的 self.cup、self.shot、self.session…
是 HeadFields 產生的 property，讀寫的是目前的沖煮頭 self.head；on_twin() 把 self.head 換成第二個，
所以做第二杯、畫第二杯都可以直接沿用單杯的程式。

新增「每杯各一份」的狀態：在 BrewHead.__init__ 加上欄位與預設值就好（HEAD_FIELDS 由它產生）。
"""


def _empty_contents():
    return {"water": 0.0, "milk": 0.0, "foam": 0.0, "syrup": 0.0}


class BrewHead:
    """一個沖煮頭下面那杯的狀態：飲品進度、杯子與杯中內容、萃取、流柱與粒子、壓力錶、曲線卡片與拉花卡片"""

    def __init__(self, spouts=(), drink=None, old=None):
        """spouts：機器的出水口（每個一條流柱）；old：同一個沖煮頭的上一份狀態（把手裡的粉餅與壓力錶延續下去）"""
        self.session = None
        self.cup = None                          # None＝這個沖煮頭下面沒有杯子（雙頭機的第二杯）
        self.contents = _empty_contents()
        self.syrup_kind = "choc"
        self.topping = {}                        # 杯面配料：cocoa／whip／caramel（0–1）
        self.icecream = None                     # 阿芙佳朵的冰淇淋球
        self.ice = []
        self.condense = 0.0
        self.mix_t = 0.0
        self.mix_clock = 0.0
        self.shot = None
        self.stream = [{"head": 0.0, "tail": 0.0} for _ in spouts]
        self.last_flow = 0.0
        self.drops = []
        self.splash = []
        self.ripples = []
        self.bubbles = []
        self.crema_h = 0.0
        self.film_h = 0.0
        self.swirl = 0.0
        self.pf_used = old.pf_used if old else False    # 把手裡有沒有上一杯的粉餅
        self.workflow = None
        self.gauge = old.gauge if old else 0.0
        self.gauge_v = old.gauge_v if old else 0.0
        self._log_clock = 0.0
        self._ripple_clock = 0.0
        self.last_drink = drink
        self.shot_frac = 1.0                     # 濃縮有多少在杯子裡（營業模式先萃取到量杯，倒進來才算；其他時候 1）
        self.wand_angle = 0.0
        self.card_alpha = 0.0                    # 這杯的曲線卡片與拉花卡片
        self.art_alpha = 0.0
        self.last_art = None
        self.last_milk = None
        self.art_show_until = 0.0
        self._art_cache = None


HEAD_FIELDS = tuple(vars(BrewHead()))


def _head_property(name):
    return property(lambda self: getattr(self.head, name),
                    lambda self, v: setattr(self.head, name, v),
                    doc=f"目前沖煮頭的 {name}（BrewHead）")


class HeadFields:
    """mixin：把 HEAD_FIELDS 轉給 self.head（目前的沖煮頭）"""


for _name in HEAD_FIELDS:
    setattr(HeadFields, _name, _head_property(_name))
del _name
