"""食材：營業模式做飲品要用的牛奶、鮮奶油、醬料、冰淇淋、通寧水…，都要用錢包買（商店「食材」分頁）

庫存以「份」計（一杯用一份），一包有固定份數；營業中客人點單時就扣掉這杯要用的份數（`needs()`），
庫存不夠的飲品客人不會點（`CafeDesk.order_exclude()`），客人要求換的植物奶沒有庫存也不會要求。
手動、自動模式不消耗食材（照樣能隨便練習）。庫存是從簽章過的事件（`ing_buy`、`ing_use`）重算出來的，開局送 `START_STOCK`。
"""
from .drinks import DRINKS, MILK_SPEC

# key：(名稱, 一包的份數, 一包的價格, 說明)。名稱與說明是繁中原文，顯示時才 T()
ITEMS = {
    "milk": ("鮮奶", 8, 80, "熱拿鐵、卡布奇諾、摩卡…所有加奶的飲品都要用，一瓶 8 份"),
    "oat": ("燕麥奶", 8, 120, "客人要求換燕麥奶時用"),
    "soy": ("豆奶", 8, 90, "客人要求換豆奶時用"),
    "almond": ("杏仁奶", 8, 130, "客人要求換杏仁奶時用"),
    "cream": ("鮮奶油", 10, 140, "摩卡與節日拿鐵擠在上面"),
    "choc": ("巧克力醬", 20, 180, "摩卡用"),
    "vanilla": ("香草糖漿", 20, 170, "焦糖瑪奇朵用"),
    "caramel": ("焦糖醬", 20, 190, "焦糖瑪奇朵淋在上面"),
    "cocoa": ("可可粉", 30, 110, "卡布奇諾與摩卡撒在上面"),
    "icecream": ("冰淇淋", 8, 180, "阿芙佳朵用，一桶 8 份"),
    "tonic": ("通寧水", 6, 100, "濃縮通寧用，一組 6 瓶"),
    "cinnamon": ("肉桂粉", 30, 100, "節日拿鐵撒在上面"),
    "pumpkin": ("南瓜醬", 15, 180, "萬聖節的南瓜香料拿鐵用"),
    "ginger": ("薑餅糖漿", 15, 160, "聖誕節的薑餅拿鐵用"),
    "rose": ("玫瑰糖漿", 15, 160, "情人節的玫瑰拿鐵用"),
}
# 甜點：跟食材一樣在商店買、庫存放在同一份 ing_stock（一份＝一個），擺在櫃檯右上的玻璃櫥窗裡。
# key：(名稱, 一盤的份數, 一盤的進貨價, 說明)；單份售價見 DESSERT_PRICE
DESSERTS = {
    "croissant": ("可頌", 6, 150, "奶油可頌，一盤 6 個"),
    "cake": ("蛋糕", 4, 200, "草莓鮮奶油蛋糕，一盤 4 片"),
    "muffin": ("馬芬", 6, 150, "巧克力馬芬，一盤 6 個"),
    "cookie": ("餅乾", 10, 120, "巧克力豆餅乾，一盤 10 片"),
}
DESSERT_PRICE = {"croissant": 55, "cake": 85, "muffin": 50, "cookie": 40}
DESSERT_COMBO_K = 0.8          # 點飲品加購甜點的折價（單點賣原價；營業中客人都是跟飲品一起點，一律打這個折）
DESSERT_P = 0.35               # 櫥窗有貨時，一位客人加購甜點的機率
DESSERT_TO_GO_P = 0.25         # 櫥窗有貨時，客人外帶的機率（原本 orders.TO_GO_P）：有甜點可以配，更多人想坐下來
DESSERT_BUYER_TO_GO_P = 0.1    # 加購甜點的客人幾乎都內用
ALL = {**ITEMS, **DESSERTS}    # 庫存、購買、自動補貨都認這個（食材分頁只列 ITEMS、甜點分頁只列 DESSERTS）
START_STOCK = {"milk": 8, "cream": 5, "choc": 10, "vanilla": 10, "caramel": 10, "cocoa": 15, "icecream": 4, "tonic": 6}
COMMON = ("milk", "oat", "soy", "almond", "cream", "choc", "vanilla", "caramel", "cocoa", "icecream", "tonic")   # 常態食材（節日的不算）
MILK_ING = {"dairy": "milk", "oat": "oat", "soy": "soy", "almond": "almond"}      # 牛奶種類 → 食材


def pack(key):
    return ALL[key][1]


def price_of(key):
    return ALL[key][2]


def dessert_price(key):
    """加購甜點的售價（已打折）"""
    return int(round(DESSERT_PRICE[key] * DESSERT_COMBO_K))


def needs(drink, mods=()):
    """一杯 drink 要用掉的食材 {key: 份}；mods 是訂單的要求 [(種類, 值)]（換植物奶、不要鮮奶油、不要可可粉、冰淇淋多一點）"""
    m = dict(mods)
    spec = DRINKS.get(drink, {})
    out = {}

    def add(key, n=1):
        out[key] = out.get(key, 0) + n
    if drink in MILK_SPEC or drink == "iced_latte":
        add(MILK_ING.get(m.get("milk", "dairy"), "milk"))
    if spec.get("syrup"):
        add(spec["syrup"])
    if drink == "caramel_macchiato":
        add("vanilla")
        add("caramel")
    whip = bool(spec.get("whip")) and m.get("whip") != "no"
    if whip:
        add("cream")
    if spec.get("dust") and (whip or drink != "mocha"):
        add(spec["dust"])
    if drink == "cappuccino" and m.get("cocoa") != "no":
        add("cocoa")
    if drink == "affogato":
        add("icecream", 2 if m.get("scoop") == "big" else 1)
    if drink == "espresso_tonic":
        add("tonic")
    return out


def drinks_using(key):
    """用到這種食材的飲品（植物奶：能換這種奶的奶類飲品）"""
    from .orders import OAT_OK
    plant = next((k for k, v in MILK_ING.items() if v == key and k != "dairy"), None)
    if plant:
        return [d for d in DRINKS if d in OAT_OK and key in needs(d, [("milk", plant)])]
    return [d for d in DRINKS if key in needs(d)]


def available(drink, stock, mods=()):
    """庫存 stock（{key: 份}）夠不夠做這杯"""
    return all(stock.get(k, 0) >= n for k, n in needs(drink, mods).items())
