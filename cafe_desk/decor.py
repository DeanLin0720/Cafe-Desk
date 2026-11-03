"""店面裝潢（櫃檯畫面）：前櫃檯、地板、牆面、菜單看板、咖啡機配色、燈光、杯子圖案，再加上掛畫與植物（可以多個）

只改外觀、不影響平衡。款式用營業額買（`price`，跟設備升級一樣花錢包）或用每日／每週挑戰的章數兌換（`stamps`，限定款）；
買到的是有簽章的紀錄（`decor_<key>`，在 Stats.data["owned"]），選用的存在設定檔 `decor`（沒買的款式讀檔時退回預設）。
畫面在 render/shop.py（paint_room、paint_counter_body、paint_decor_*），配色與開關從 `palette()` 取。
"""

# 單選的欄位：每個欄位第一個是預設款（一直擁有）；掛畫與植物可以同時擺好幾個
SINGLE = ("counter", "cabinet", "floor", "wall", "board", "machine", "lighting", "cup", "pos")
MULTI = ("paintings", "plants")
SLOTS = SINGLE + MULTI
SLOT_NAME = {"counter": "前櫃檯材質", "cabinet": "後檯櫃子", "floor": "地板", "wall": "牆面", "board": "菜單看板", "machine": "咖啡機配色",
             "lighting": "燈光", "cup": "杯子圖案", "pos": "POS 機", "paintings": "牆上掛畫", "plants": "植物與花"}
MAX_PAINTINGS = 4          # 牆上掛畫的位置數
MAX_PLANTS = 6             # 六個位置：後檯左邊兩處、前櫃檯兩處（STAND_SPOTS）＋天花板左右兩個吊盆（HANG_SPOTS）

# key: (欄位, 名稱, 台幣價格, 挑戰章數, 說明)。價格與章數都是 0＝預設款。名稱、說明是繁中原文，顯示時才 T()
ITEMS = {
    "wood": ("counter", "暖木", 0, 0, "原本的暖木前櫃檯"),
    "marble": ("counter", "大理石", 6000, 0, "淺灰大理石前板與檯面，店名改深色字"),
    "blackwood": ("counter", "黑木", 8000, 0, "深黑胡桃木，檯面是焦糖色的木板"),
    "whitepaint": ("counter", "白漆", 5000, 0, "明亮的白漆前板，北歐風"),
    "teal": ("counter", "青綠漆", 5500, 0, "沉穩的青綠色前板，檯面是淺木色"),
    "redwood": ("counter", "紅木", 7000, 0, "深紅褐色的紅木前板，復古的老店感"),
    "concrete_c": ("counter", "清水模", 6500, 0, "灰色清水模前板，檯面是淺橡木"),
    "cab_wood": ("cabinet", "暖木櫃", 0, 0, "原本的暖木抽屜、黃銅把手"),
    "cab_black": ("cabinet", "黑木櫃", 4000, 0, "深黑胡桃木抽屜，把手是黃銅色"),
    "cab_white": ("cabinet", "白漆櫃", 3500, 0, "明亮的白漆抽屜，銀色把手"),
    "cab_green": ("cabinet", "墨綠櫃", 4000, 0, "沉穩的墨綠色烤漆抽屜"),
    "cab_navy": ("cabinet", "藏青櫃", 4000, 0, "深海藏青色抽屜，銀色把手"),
    "cab_red": ("cabinet", "紅木櫃", 4500, 0, "深紅褐色的紅木抽屜，復古老店的感覺"),
    "cab_oak": ("cabinet", "淺橡木櫃", 3500, 0, "淺色橡木抽屜配黑色把手，清爽的日系感"),
    "wood_floor": ("floor", "木地板", 0, 0, "原本的深色木地板"),
    "tile": ("floor", "黑白格磁磚", 5000, 0, "復古的黑白棋盤格地磚"),
    "concrete": ("floor", "水泥地", 3500, 0, "冷灰色的水泥地，工業風"),
    "terracotta": ("floor", "赤陶磚", 4000, 0, "暖橘紅色的赤陶地磚，地中海風"),
    "navy_tile": ("floor", "藍白磁磚", 5500, 0, "深藍與米白的棋盤格磁磚"),
    "herring": ("floor", "人字拼木地板", 6000, 0, "一片片斜拼成人字的木地板"),
    "marble_floor": ("floor", "大理石地", 5000, 0, "淺灰大理石地磚，帶著細細的紋路"),
    "dark": ("wall", "深色牆", 0, 0, "原本的暖灰深色牆"),
    "brick": ("wall", "紅磚牆", 6000, 0, "一塊一塊的紅磚牆"),
    "cream": ("wall", "奶油壁紙", 4000, 0, "淺奶油色的牆，整間店變明亮"),
    "green": ("wall", "墨綠牆", 4500, 0, "沉穩的墨綠色油漆牆"),
    "navy": ("wall", "藏青牆", 4500, 0, "深海一樣的藏青色油漆牆"),
    "pink": ("wall", "櫻花粉牆", 4500, 0, "柔和的粉紅色牆，溫柔的店面"),
    "subway": ("wall", "白色地鐵磚", 5500, 0, "一排排錯開的白色長方形磁磚"),
    "panel": ("wall", "木牆板", 6000, 0, "直條拼接的深色木牆板"),
    "chalk": ("board", "黑板", 0, 0, "原本的黑板看板"),
    "frame": ("board", "木框看板", 3000, 0, "四塊看板都裝上木框"),
    "minimal": ("board", "白底極簡", 3500, 0, "白底深字，乾淨的菜單"),
    "gold_frame": ("board", "金框看板", 4500, 0, "四塊看板都裝上黃銅色的框"),
    "kraft": ("board", "牛皮紙看板", 3500, 0, "牛皮紙色底、深褐字的手寫風菜單"),
    "neon": ("board", "霓虹看板", 0, 12, "紫黑底、粉紅霓虹字與發光邊框（挑戰限定）"),
    "silver": ("machine", "銀色", 0, 0, "原本的機身顏色（銀色、拉桿機是銅色）"),
    "black": ("machine", "霧黑", 4000, 0, "所有咖啡機改成霧黑烤漆"),
    "cream_m": ("machine", "奶油白", 4500, 0, "所有咖啡機改成復古的奶油白烤漆"),
    "green_m": ("machine", "復古綠", 5000, 0, "所有咖啡機改成老咖啡館常見的復古綠烤漆"),
    "red_m": ("machine", "霧紅", 5000, 0, "所有咖啡機改成霧面紅色烤漆"),
    "blue_m": ("machine", "霧藍", 5000, 0, "所有咖啡機改成霧面深藍色烤漆"),
    "pink_m": ("machine", "粉彩", 5000, 0, "所有咖啡機改成淡淡的粉紅色烤漆"),
    "yellow_m": ("machine", "奶油黃", 4500, 0, "所有咖啡機改成明亮的奶油黃烤漆"),
    "mint_m": ("machine", "薄荷綠", 5000, 0, "所有咖啡機改成清爽的薄荷綠烤漆"),
    "none": ("lighting", "一般照明", 0, 0, "原本的室內燈光"),
    "pendant": ("lighting", "暖黃球燈", 3000, 0, "三盞垂下來的暖黃球形吊燈"),
    "industrial": ("lighting", "工業吊燈", 4500, 0, "黑色圓罩吊燈，一束束往下打"),
    "fairy": ("lighting", "星星燈串", 3500, 0, "沿著牆面垂下來的暖黃小燈串"),
    "lantern": ("lighting", "紙燈籠", 3500, 0, "三盞圓圓的白色紙燈籠，光線柔和"),
    "edison": ("lighting", "愛迪生燈泡", 4000, 0, "裸露的復古燈泡，看得到裡面發亮的燈絲"),
    "neon_sign": ("lighting", "霓虹招牌", 0, 15, "牆上亮著粉紅與藍色的咖啡杯霓虹招牌（挑戰限定）"),
    "plain": ("cup", "素面", 0, 0, "原本的紙杯與杯盤"),
    "stripe": ("cup", "條紋", 2000, 0, "紙杯隔熱套與杯盤邊緣加上條紋"),
    "dots": ("cup", "圓點", 2500, 0, "紙杯隔熱套與杯盤邊緣加上圓點"),
    "brand": ("cup", "店標", 3500, 0, "紙杯隔熱套印上店標、杯盤邊緣一圈金線"),
    "hearts": ("cup", "愛心", 3000, 0, "紙杯隔熱套與杯盤邊緣加上小愛心"),
    "waves": ("cup", "波浪", 2800, 0, "紙杯隔熱套加上一圈圈波浪線"),
    "stars": ("cup", "星星", 2800, 0, "紙杯隔熱套與杯盤邊緣加上金色小星星"),
    "leaf": ("cup", "小葉子", 2800, 0, "紙杯隔熱套加上一排綠色小葉子"),
    "pos_white": ("pos", "經典白", 0, 0, "原本的白色螢幕、黑框 POS"),
    "pos_black": ("pos", "暗黑模式", 3500, 0, "深色螢幕、淺色字，黑色機身"),
    "pos_wood": ("pos", "木質", 4000, 0, "木框與木色立架，米色螢幕，跟暖木店面很搭"),
    "pos_pink": ("pos", "粉彩", 3500, 0, "粉紅色機身與立架，淡粉紅螢幕"),
    "pos_gold": ("pos", "黑金", 0, 18, "深色螢幕配金色字與金邊機身（挑戰限定）"),
    "art_beans": ("paintings", "咖啡豆插畫", 2500, 0, "深底色上散落的咖啡豆"),
    "art_latte": ("paintings", "拉花畫", 2500, 0, "俯視的拿鐵拉花"),
    "art_hills": ("paintings", "山景畫", 3000, 0, "遠山與朝霞"),
    "art_poster": ("paintings", "復古海報", 2800, 0, "老式咖啡廣告海報：紅底、大咖啡杯"),
    "art_map": ("paintings", "產地地圖", 3200, 0, "標著咖啡產地的世界地圖"),
    "art_clock": ("paintings", "掛鐘", 3500, 0, "圓形木框的掛鐘，指針會隨現在的時間走"),
    "art_photo": ("paintings", "老照片", 0, 8, "泛黃的老咖啡館照片（挑戰限定）"),
    "art_gold": ("paintings", "金咖啡杯", 0, 20, "深色底上閃著金光的咖啡杯（挑戰限定）"),
    "art_cherry": ("paintings", "咖啡櫻桃", 2800, 0, "枝頭上紅通通的咖啡果實"),
    "art_moka": ("paintings", "摩卡壺素描", 3000, 0, "米色紙上的摩卡壺線稿"),
    "art_abstract": ("paintings", "抽象色塊", 3200, 0, "暖色系的幾何色塊，現代感"),
    "art_cat": ("paintings", "窗邊的貓", 0, 10, "趴在窗台上曬太陽的橘貓（挑戰限定）"),
    "plant_pot": ("plants", "小盆栽", 1500, 0, "後檯上的一盆綠色小盆栽"),
    "plant_vase": ("plants", "乾燥花", 1800, 0, "前櫃檯上的乾燥花瓶"),
    "plant_hang": ("plants", "吊蘭", 2200, 0, "從天花板垂下來的吊蘭"),
    "plant_cactus": ("plants", "仙人掌", 1500, 0, "後檯左邊的一盆圓圓的仙人掌"),
    "plant_fern": ("plants", "蕨類盆栽", 2000, 0, "前櫃檯上垂著葉子的蕨類"),
    "plant_succulent": ("plants", "多肉組盆", 1600, 0, "長方形木盆裡排著三株多肉"),
    "plant_olive": ("plants", "橄欖樹", 2600, 0, "細細的枝幹和銀綠色的小葉子"),
    "plant_tulip": ("plants", "鬱金香瓶花", 2000, 0, "玻璃瓶裡插著幾支粉紅鬱金香"),
    "plant_ivy": ("plants", "黃金葛", 2400, 0, "從天花板右邊垂下來的黃金葛"),
}
DEFAULTS = {slot: next(k for k, v in ITEMS.items() if v[0] == slot) for slot in SINGLE}
# 植物的位置：檯面上四處（後檯左邊兩處、前櫃檯兩處）與天花板左右兩個吊盆。每一款有偏好的位置，被佔了就換到同類的空位
STAND_SPOTS = 4
HANG_SPOTS = 2
PLANT_HOME = {"plant_pot": 0, "plant_cactus": 1, "plant_vase": 2, "plant_fern": 3, "plant_succulent": 0,
              "plant_olive": 3, "plant_tulip": 2, "plant_hang": 0, "plant_ivy": 1}
HANGING = ("plant_hang", "plant_ivy")

# 每個款式的畫面設定；沒列的 key 沿用預設款（render/shop.py 的 STORE）
LOOK = {
    "marble": {"front": ("#d8d4cc", "#a8a49c"), "top": ("#f4f1ea", "#cfc9bd"), "logo": "#3a342c", "shelf": "#a8a49c"},
    "blackwood": {"front": ("#3a2a22", "#1c1410"), "top": ("#8a6a4a", "#5a4430"), "logo": "#e8c88a", "shelf": "#4a3a2e"},
    "whitepaint": {"front": ("#e8e4dc", "#c8c2b6"), "top": ("#faf7f0", "#d8d2c4"), "logo": "#6a5a48", "shelf": "#c8c2b6"},
    "teal": {"front": ("#2e5a56", "#1a3a38"), "top": ("#d8c49a", "#b0966a"), "logo": "#f0e2c0", "shelf": "#3a6a64"},
    "redwood": {"front": ("#5a2e22", "#341810"), "top": ("#a8744a", "#6a4430"), "logo": "#f0d09a", "shelf": "#6a3a2a"},
    "cab_black": {"cab": ("#3a2a22", "#1c1410"), "cab_line": "#5a4436", "handle": "#c9a35a"},
    "cab_white": {"cab": ("#e8e4dc", "#c4beb2"), "cab_line": "#faf7f0", "handle": "#9a9a9e"},
    "cab_green": {"cab": ("#2e4a3a", "#1a2c22"), "cab_line": "#4a6a56", "handle": "#c9a35a"},
    "cab_navy": {"cab": ("#2a3a5a", "#16203a"), "cab_line": "#4a5c80", "handle": "#b8c0cc"},
    "cab_red": {"cab": ("#6a3226", "#3e1c14"), "cab_line": "#8a4c3a", "handle": "#e0b86a"},
    "tile": {"floor": ("#3a3a3e", "#d8d4cc"), "floor_pat": "check"},
    "terracotta": {"floor": ("#a85c3c", "#7a4228")},
    "navy_tile": {"floor": ("#26385a", "#e0e2e6"), "floor_pat": "check"},
    "concrete": {"floor": ("#6a6c70", "#4a4c50")},
    "herring": {"floor": ("#8a6440", "#5e4228"), "floor_pat": "herring"},
    "marble_floor": {"floor": ("#d4d0c8", "#a8a49c"), "floor_pat": "marble"},
    "concrete_c": {"front": ("#8a8c8e", "#5e6062"), "top": ("#d8c4a0", "#b09a74"), "logo": "#f2eee6", "shelf": "#6e7072"},
    "cab_oak": {"cab": ("#c8a87a", "#a08258"), "cab_line": "#e0c8a0", "handle": "#2a2a2c"},
    "subway": {"wall": ("#e2ded6", "#bab4a8"), "wall_pat": "subway", "blind": "#8a8a8a"},
    "panel": {"wall": ("#5a3e28", "#36261a"), "wall_pat": "panel"},
    "brick": {"wall": ("#5a3a30", "#3a2420"), "wall_pat": "brick"},
    "cream": {"wall": ("#d8cdb8", "#b8a98c"), "blind": "#8a7a62"},
    "green": {"wall": ("#26382e", "#16241c")},
    "navy": {"wall": ("#22304a", "#141c2e"), "blind": "#a8b4c8"},
    "pink": {"wall": ("#d8b4b8", "#b48e94"), "blind": "#8a6a70"},
    "frame": {"frame": "#8a6440", "board": "#1e1c1a"},
    "gold_frame": {"frame": "#c9a35a", "board": "#1e1c1a"},
    "kraft": {"board_light": True, "board2": "#d8bc8c", "frame": "#8a6a44", "accent": "#8a4a1a"},
    "minimal": {"board_light": True, "board2": "#f4f0e6", "frame": "#cfc6b4", "accent": "#a8742a"},
    "neon": {"board": "#140c1e", "accent": "#ff6ad5", "frame": "#3a1a4a", "neon": "#ff6ad5"},
}
# 咖啡機烤漆換色：(色相 0–359 或 None＝保留原本色相、飽和度倍率、飽和度加成、明度倍率、原本是深色烤漆的地方換成多亮或 None)
MACHINE_TINT = {"black": (None, 0.2, 0.0, 0.38, None), "cream_m": (38, 0.4, 0.14, 1.06, 0.84),
                "green_m": (150, 0.3, 0.42, 0.9, 0.42), "red_m": (6, 0.3, 0.5, 0.95, 0.40),
                "blue_m": (214, 0.3, 0.44, 0.9, 0.40), "pink_m": (346, 0.4, 0.2, 1.06, 0.86),
                "yellow_m": (46, 0.4, 0.36, 1.04, 0.86), "mint_m": (158, 0.4, 0.26, 1.04, 0.80)}
# 杯子圖案：(隔熱套與杯盤的圖案, 顏色)
CUP_STYLES = {"stripe": ("stripe", "#b04a3a"), "dots": ("dots", "#e8d8b8"), "brand": ("brand", "#e8c88a"),
              "hearts": ("hearts", "#e8708a"), "waves": ("waves", "#3a6a8a"), "stars": ("stars", "#e8c84a"),
              "leaf": ("leaf", "#5a8a4a")}
# POS 機的配色（螢幕、機身、立架、收據機、刷卡機與螢幕上的字色）；沒列的 key 用 POS_BASE
POS_BASE = {"bezel": "#141516", "screen": ("#f6f8fa", "#dfe6ec"), "ink": "#2a3a4a", "ink2": "#3a4a5a", "line": "#b8c4ce",
            "muted": "#5a6a7a", "muted2": "#6a7a8a", "stand": ("#2a2b2e", "#4a4c50"), "printer": ("#3a3b3e", "#1a1b1d"),
            "reader": ("#3a3b3e", "#18191b")}
POS_LOOK = {
    "pos_black": {"bezel": "#08090a", "screen": ("#1f2a34", "#121a22"), "ink": "#e6eef6", "ink2": "#c0ccd8", "line": "#3a4a58",
                  "muted": "#9aaabb", "muted2": "#8a9aaa"},
    "pos_wood": {"bezel": "#7a5634", "screen": ("#f8f2e4", "#e6dcc6"), "ink": "#4a3626", "ink2": "#5a4636", "line": "#cdbf9f",
                 "muted": "#7a6a52", "muted2": "#8a7a62", "stand": ("#5a3e26", "#8a6440"), "printer": ("#6a4a30", "#3a2616"),
                 "reader": ("#6a4a30", "#3a2616")},
    "pos_pink": {"bezel": "#c8708a", "screen": ("#fff6f8", "#fbe4ea"), "ink": "#6a3446", "ink2": "#7a4456", "line": "#e4b8c4",
                 "muted": "#9a6a7a", "muted2": "#aa7a8a", "stand": ("#a85a74", "#e8a0b4"), "printer": ("#d88aa0", "#a85a74"),
                 "reader": ("#d88aa0", "#a85a74")},
    "pos_gold": {"bezel": "#b8923a", "screen": ("#201c14", "#12100a"), "ink": "#f0d890", "ink2": "#d8c078", "line": "#5a4a24",
                 "muted": "#b89a50", "muted2": "#a88a44", "stand": ("#8a6a28", "#e8c868"), "printer": ("#d8b458", "#8a6a28"),
                 "reader": ("#d8b458", "#8a6a28")},
}


def make_remap(machine, spec):
    """某台咖啡機的烤漆換色函式 #rrggbb → #rrggbb（gfx.recolor 用）：只換這台的烤漆色——
    machine.paint_kind 是 steel 就換中性的銀灰色（不含接近白或黑的亮面與縫隙）、copper 就換銅色，
    machine.paint_extra 裡的顏色（深色顆粒烤漆）也換；錶盤、燈號、把手等其他顏色不動"""
    import colorsys
    from functools import lru_cache
    hue, s_k, s_add, v_k, dark_v = spec
    extra = set(machine.paint_extra)
    kind = machine.paint_kind

    @lru_cache(maxsize=4096)
    def remap(h):
        if len(h) != 7 or h[0] != "#":
            return h
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        hh, s, v = colorsys.rgb_to_hsv(r, g, b)
        if h in extra:
            ns = min(1.0, s * s_k + s_add)
            nv = v * v_k if dark_v is None else dark_v * min(1.0, v / 0.24)
        elif kind == "steel" and s < 0.2 and 0.28 <= v <= 0.99:
            ns, nv = min(1.0, s * s_k + s_add), min(1.0, v * v_k)
        elif kind == "copper" and 8 <= hh * 360 <= 42 and s >= 0.3 and v >= 0.15:
            ns, nv = min(1.0, s * s_k + s_add * 0.6), min(1.0, v * v_k)
        else:
            return h
        r, g, b = colorsys.hsv_to_rgb(hh if hue is None else hue / 360, ns, nv)
        return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))
    return remap


def price_of(key):
    return ITEMS[key][2]


def stamps_of(key):
    return ITEMS[key][3]


def is_default(key):
    return DEFAULTS.get(ITEMS[key][0]) == key


def owned_keys(owned):
    """商店紀錄 owned（"decor_<key>"）→ 已擁有的款式（預設款一直擁有）"""
    return {k for k in ITEMS if is_default(k) or f"decor_{k}" in owned}


def selection(raw, owned):
    """設定檔的 decor（可能被改過）→ 目前選用：單選欄位是 key、掛畫與植物是 key 的 list；沒買的退回預設"""
    have = owned_keys(owned)
    raw = raw if isinstance(raw, dict) else {}
    sel = {}
    for slot in SINGLE:
        k = raw.get(slot)
        sel[slot] = k if k in have and ITEMS[k][0] == slot else DEFAULTS[slot]
    for slot, limit in (("paintings", MAX_PAINTINGS), ("plants", MAX_PLANTS)):
        ks = raw.get(slot)
        ks = [k for k in (ks if isinstance(ks, list) else []) if k in have and ITEMS[k][0] == slot]
        sel[slot] = list(dict.fromkeys(ks))[:limit]
    hang = [k for k in sel["plants"] if k in HANGING][:HANG_SPOTS]       # 檯面與吊盆各自的位置數也不能超過
    stand = [k for k in sel["plants"] if k not in HANGING][:STAND_SPOTS]
    sel["plants"] = [k for k in sel["plants"] if k in hang or k in stand]
    return sel


def plant_spots(plants):
    """擺上的植物 → [(key, 吊盆嗎, 位置索引)]：照擺上的順序，先放偏好的位置（PLANT_HOME），被佔了換同類的第一個空位；沒空位的不畫"""
    taken, out = set(), []
    for k in plants:
        hang = k in HANGING
        home = PLANT_HOME.get(k, 0)
        i = home if (hang, home) not in taken else next(
            (j for j in range(HANG_SPOTS if hang else STAND_SPOTS) if (hang, j) not in taken), None)
        if i is not None:
            taken.add((hang, i))
            out.append((k, hang, i))
    return out


def plant_full(plants, key):
    """再擺上 key 時，同類（檯面或吊盆）的位置是不是已經滿了"""
    hang = key in HANGING
    return sum(1 for k in plants if (k in HANGING) == hang) >= (HANG_SPOTS if hang else STAND_SPOTS)


def palette(base, sel):
    """預設配色 base（shop.STORE）套上選用款式的設定"""
    pal = dict(base)
    pal.update({"cab": ("#6e4c30", "#4e3420"), "cab_line": "#8a6440", "handle": "#c9a35a"})     # 後檯櫃子的預設（暖木）
    pal.update({"floor_pat": None, "wall_pat": None, "frame": None, "neon": None, "board_light": False, "board2": "#f2ece0"})
    for slot in ("counter", "cabinet", "floor", "wall", "board"):
        pal.update(LOOK.get(sel[slot], {}))
    return pal


def cup_style(sel):
    return CUP_STYLES.get(sel["cup"], (None, None))


def pos_look(sel):
    """目前選用的 POS 機配色（POS_BASE 套上選用款的設定）"""
    look = dict(POS_BASE)
    look.update(POS_LOOK.get(sel["pos"], {}))
    return look


def machine_tint(sel):
    return MACHINE_TINT.get(sel["machine"])


def collection(owned):
    """(已擁有的非預設款式數, 非預設款式總數)：圖鑑的裝潢收集"""
    extra = [k for k in ITEMS if not is_default(k)]
    return sum(1 for k in extra if f"decor_{k}" in owned), len(extra)
