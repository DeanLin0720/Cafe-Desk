"""介面語言：繁體中文（原文）／英文

程式裡的顯示文字一律寫繁體中文原文，經過 T() 取得目前語言的版本：
    T("萃取中…")                         → "Extracting…"
    T("{name} 點了{title}", name=…, title=…)   → 先翻譯樣板，再代入（樣板可用格式，例如 {t:.0f}）
資料裡的名稱（飲品、牛奶、拉花圖案、訂單要求、咖啡機…）也是在顯示時才 T()，切換語言立即生效。
找不到翻譯時直接顯示原文。
"""
import re

LANGS = (("zh", "繁體中文"), ("en", "English"))
_lang = "zh"


def set_lang(lang):
    global _lang
    _lang = lang if lang in dict(LANGS) else "zh"


def lang():
    return _lang


# 錢：紀錄、價格、等級門檻、商店價格一律存台幣；顯示時中文用新台幣、英文用美金
# 英文的換算依物價不依匯率（實際約 30）：台灣拿鐵 NT$120 ≈ 美國精品店 US$6，菜單價看起來才像美國；不連網查
TWD_PER_USD = 20.0


def money(twd):
    """台幣金額 → 目前語言的顯示：NT$1,234／US$38.56（美金 100 元以上不顯示角分）"""
    if _lang == "en":
        usd = twd / TWD_PER_USD
        return f"US${usd:,.0f}" if abs(usd) >= 100 else f"US${usd:,.2f}"
    return f"NT${twd:,.0f}"


_MONEY = re.compile(r"\$(\d[\d,]*)")


def money_text(s):
    """固定文字裡寫的台幣金額（例如成就說明的 $2,000）換成目前語言的幣值"""
    return _MONEY.sub(lambda m: money(int(m.group(1).replace(",", ""))), s)


def T(_text, **kw):
    s = EN.get(_text, _text) if _lang == "en" else _text
    return s.format(**kw) if kw else s


_FIELD = re.compile(r"\{(\w+)(?::[^}]*)?\}")
_retext_cache = {}


def _retext_table(target):
    """retext 用的對照：{原文: 譯文}、樣板清單 [(字面字數, 開頭是不是 {…}, regex, 欄位, 譯文樣板)]、
    兩個詞直接接起來的樣板（{prefix}{name}）跟它用的詞表"""
    if target not in _retext_cache:
        table = dict(EN) if target == "en" else {}
        words = table
        if target == "zh":
            words = {}
            for zh, en in EN.items():
                table.setdefault(en, zh)
                if en not in words or len(zh) < len(words[en]):     # Latte 接在燕麥後面是「拿鐵」不是「熱拿鐵」
                    words[en] = zh
        pats, joins = [], []
        for src, dst in table.items():
            if "{" not in src:
                continue
            literal = _FIELD.sub("", src)
            if not literal.strip():                 # 例如「{prefix}{name}」：兩段都要是查得到的詞才算
                fields = _FIELD.findall(src)
                if len(fields) == 2 and src.startswith("{") and src.endswith("}"):
                    joins.append((literal, fields, dst))
                continue
            names, rx, pos = [], "", 0
            for m in _FIELD.finditer(src):
                rx += re.escape(src[pos:m.start()]) + f"(?P<f{len(names)}>.+?)"
                names.append(m.group(1))
                pos = m.end()
            rx += re.escape(src[pos:])
            pats.append((len(literal), src.startswith("{"), re.compile(rx, re.S), names, dst))
        _retext_cache[target] = (table, pats, joins, words)
    return _retext_cache[target]


def retext(s, _depth=0):
    """紀錄裡存的是做那杯時的語言（客人評價、飲品名稱…），顯示時換成目前語言：
    整句查表 → 套樣板（{…} 裡的部分再遞迴翻）→ 用「 · 」拆開分段翻；都對不上就原樣顯示。
    好幾個樣板都對得上時取最外層的（第一個 {…} 最短，例如「阿明：等有點久，還可以。」先拆「{name}：{text}」）"""
    if not s or _depth > 6:
        return s
    table, pats, joins, words = _retext_table(_lang)
    if s in table:
        return table[s]
    best = None
    for size, lead, rx, names, dst in pats:
        m = rx.fullmatch(s)
        if m:
            key = (m.end("f0") if lead else 0, -size)
            if best is None or key < best[0]:
                best = (key, m, names, dst)
    if best:
        _key, m, names, dst = best
        parts = {}
        for i, n in enumerate(names):
            parts.setdefault(n, retext(m.group(f"f{i}"), _depth + 1))
        return _FIELD.sub(lambda f: parts.get(f.group(1), f.group(0)), dst)
    for sep, (a, b), dst in joins:
        for i in range(1, len(s)):
            x, y = s[:i], s[i:]
            if y.startswith(sep) and x in words and y[len(sep):] in words:
                return dst.replace("{" + a + "}", words[x]).replace("{" + b + "}", words[y[len(sep):]])
    if " · " in s:
        return " · ".join(retext(x, _depth + 1) for x in s.split(" · "))
    return s


EN = {
    # ───── 選單、系統匣 ─────
    "開始沖煮": "Brew",
    "關於 Café Desk…": "About Café Desk…",
    "關於 Café Desk": "About Café Desk",
    "桌上咖啡吧": "Desktop espresso bar",
    "版本 {v}": "Version {v}",
    "放在桌面上的咖啡機擺件：點一下，做一杯咖啡。": "A coffee machine that lives on your desktop: click it to make a cup.",
    "設定檔": "Settings file",
    "紀錄資料庫": "Records database",
    "錯誤紀錄": "Error log",
    "（還沒產生）": " (not created yet)",
    "資料夾": "Folder",
    "開啟資料夾": "Open folder",
    "參數設定…": "Settings…",
    "飲品": "Drink",
    "咖啡機": "Machine",
    "拉花圖案": "Latte art",
    "自動模式（照設定重複沖煮）": "Auto mode (repeat my drink)",
    "顧客點單模式": "Customer orders",
    "20 秒": "20 s", "1 分鐘": "1 min", "3 分鐘": "3 min", "10 分鐘": "10 min",
    "播放速度": "Speed",
    "1×（真實時間）": "1× (real time)",
    "聲音": "Sound",
    "音量": "Volume",
    "小": "Low", "中": "Medium", "大": "High",
    "環境光": "Ambient light",
    "依時間變化": "Follow the clock", "白天": "Day", "黃昏": "Dusk", "夜晚": "Night",
    "滑鼠停留顯示萃取曲線": "Show extraction chart on hover",
    "大小": "Size",
    "視窗化顯示": "Windowed",
    "視窗置頂": "Always on top",
    "語言": "Language",
    "縮到系統匣": "Hide to tray",
    "結束": "Quit",
    "顯示咖啡機": "Show",
    "咖啡機在系統匣裡，點一下圖示就能叫回來。": "Café Desk is in the tray. Click the icon to bring it back.",
    "待機中": "Idle",
    "上一杯{name} {score:.0f} 分 · {comment}": "Last: {name} {score:.0f} pts · {comment}",
    "訂單 #{no} {name}：{title}": "Order #{no} {name}: {title}",
    "自動模式：{sec} 秒後沖下一杯": "Auto mode: next drink in {sec} s",
    "{name}：{status}": "{name}: {status}",

    # ───── 飲品 ─────
    "濃縮": "Espresso",
    "Ristretto": "Ristretto",
    "Lungo": "Lungo",
    "雙份濃縮": "Doppio",
    "美式": "Americano",
    "冰美式": "Iced Americano",
    "熱拿鐵": "Latte",
    "拿鐵": "Latte",
    "卡布奇諾": "Cappuccino",
    "馥列白": "Flat White",
    "可塔朵": "Cortado",
    "瑪奇朵": "Macchiato",
    "冰拿鐵": "Iced Latte",
    "摩卡": "Mocha",
    "焦糖瑪奇朵": "Caramel Macchiato",
    "濃縮通寧": "Espresso Tonic",
    "阿芙佳朵": "Affogato",

    # ───── 拉花、牛奶、配料 ─────
    "愛心": "Heart", "鬱金香": "Tulip", "葉子": "Rosetta", "白點（沒拉成）": "Blob (no pattern)",
    "白點": "Blob", "奶泡點": "Foam dot", "焦糖格紋": "Caramel grid", "鮮奶油": "Whipped cream",
    "自動（看奶泡狀況）": "Auto (depends on the foam)",
    "牛奶": "Milk", "燕麥奶": "Oat milk", "豆奶": "Soy milk", "杏仁奶": "Almond milk",
    "燕麥": "Oat", "杏仁": "Almond",
    "巧克力醬": "Chocolate sauce", "香草糖漿": "Vanilla syrup",
    "{name}有點糊": "{name} came out smudged",
    "想拉{name}，奶泡不夠細": "Tried a {name}, foam too coarse",
    "奶溫過高，甜感流失": "Milk too hot, sweetness lost",
    "奶溫偏低": "Milk a bit cool",
    "奶泡太厚": "Foam too thick",
    "奶泡太薄": "Foam too thin",
    "奶泡細緻如絲": "Silky microfoam",
    "奶泡尚可": "Decent foam",
    "奶泡偏粗": "Coarse foam",
    "杏仁奶奶泡很快就消了": "Almond foam collapsed quickly",
    "比例剛好": "Ratio spot on",
    "偏淡": "A bit weak",
    "偏濃": "A bit strong",
    "分層漂亮、比例剛好": "Clean layers, good ratio",
    "通寧水偏多": "Too much tonic",
    "咖啡偏濃": "Coffee too strong",
    "冰淇淋與濃縮剛好": "Ice cream and espresso balanced",
    "冰淇淋太多": "Too much ice cream",
    "濃縮蓋過冰淇淋": "Espresso overpowers the ice cream",
    "奶咖比例剛好": "Milk/coffee ratio spot on",
    "奶味偏重": "Too milky",
    "奶咖 1:1 剛好": "1:1 milk ratio spot on",
    "拉花：{art}": "Art: {art}",
    "拉花沒成形": "No pattern formed",
    "焦糖格紋 · {comment}": "Caramel grid · {comment}",
    "鮮奶油 · {comment}": "Whipped cream · {comment}",

    # ───── 流程狀態 ─────
    "鍋爐降溫中…  {t:.0f}°C": "Cooling boiler…  {t:.0f}°C",
    "切換蒸氣模式，加熱中…  {t:.0f}°C": "Steam mode, heating…  {t:.0f}°C",
    "加入冰塊…": "Adding ice…",
    "注入熱水…": "Adding hot water…",
    "倒入冷水…": "Adding cold water…",
    "倒入冰牛奶…": "Pouring cold milk…",
    "注入牛奶融合…": "Pouring milk…",
    "倒入通寧水…": "Pouring tonic…",
    "擠入巧克力醬…": "Adding chocolate sauce…",
    "加入香草糖漿…": "Adding vanilla syrup…",
    "拉花中…": "Pouring latte art…",
    "點上奶泡…": "Spooning foam…",
    "倒入熱牛奶…": "Pouring steamed milk…",
    "{label}  {g:.0f} g": "{label}  {g:.0f} g",
    "拉花杯移到蒸氣管…": "Pitcher to steam wand…",
    "打奶泡…  {t:.0f}°C": "Steaming milk…  {t:.0f}°C",
    "奶泡機運轉中…  {t:.0f}°C": "Frothing…  {t:.0f}°C",
    "撒可可粉…": "Dusting cocoa…",
    "擠上鮮奶油…": "Topping with whipped cream…",
    "淋上焦糖醬…": "Drizzling caramel…",
    "放入一球香草冰淇淋…": "Adding a scoop of vanilla ice cream…",
    "拉下拉桿，預浸泡中…": "Lever down, pre-infusing…",
    "預浸泡中…": "Pre-infusing…",
    "加壓中…": "Building pressure…",
    "萃取中…": "Extracting…",
    "收尾滴落…": "Last drips…",
    "取下把手…": "Removing portafilter…",
    "敲掉粉渣…": "Knocking out the puck…",
    "移到磨豆機…": "To the grinder…",
    "磨豆中…": "Grinding…",
    "磨豆中…  {g:.1f} g": "Grinding…  {g:.1f} g",
    "布粉…": "Distributing…",
    "填壓…": "Tamping…",
    "裝回沖煮頭…": "Back to the group…",
    "扣上把手…": "Locking in…",

    # ───── 萃取評語 ─────
    "有通道效應，酸苦混雜": "Channeling: sour and bitter",
    "萃取不足，偏酸單薄": "Under-extracted: sour and thin",
    "略酸，明亮但收尾短": "Slightly sour, bright but short",
    "過度萃取，苦澀乾口": "Over-extracted: bitter and dry",
    "略苦，尾韻偏乾": "Slightly bitter, dry finish",
    "平衡但偏淡": "Balanced but light",
    "濃郁厚重": "Rich and heavy",
    "甜感飽滿、平衡乾淨": "Sweet, balanced and clean",
    "淺焙": "Light roast", "中焙": "Medium roast", "深焙": "Dark roast",

    # ───── 咖啡機 ─────
    "DESK·01 雙錶不鏽鋼機": "DESK·01 twin-gauge steel",
    "復古拉桿機": "Retro lever",
    "小型單鍋爐機": "Compact single boiler",
    "一體機（內建磨豆）": "All-in-one (built-in grinder)",
    "PID 溫控穩定、恆壓幫浦；搭配獨立奶泡機": "Stable PID, constant-pressure pump; separate milk frother",
    "彈簧拉桿：壓力隨萃取遞減、甜感高；大鍋爐蒸氣強、沖煮頭偏熱":
        "Spring lever: declining pressure, extra sweetness; big boiler, strong steam, hot group",
    "單鍋爐：水溫飄動大、洩壓閥偏高；打奶前要等鍋爐升溫":
        "Single boiler: temperature swings, high OPV; waits for steam temperature",
    "內建磨豆機一台搞定；研磨均勻度稍差、熱塊水溫會飄、蒸氣稍弱":
        "Built-in grinder; less uniform grind, thermoblock drift, weaker steam",

    # ───── 點單 ─────
    "小陳": "Chen", "阿哲": "Jay", "小美": "May", "王先生": "Mr. Wang", "林小姐": "Ms. Lin", "小雨": "Rain",
    "阿凱": "Kai", "老張": "Mr. Chang", "阿明": "Ming", "陳太太": "Mrs. Chen", "測試": "Test",
    "不要太燙": "Not too hot", "熱一點": "Extra hot",
    "換燕麥奶": "Oat milk", "換豆奶": "Soy milk", "換杏仁奶": "Almond milk",
    "不要鮮奶油": "No whipped cream", "冰淇淋多一點": "Bigger scoop",
    "多一點奶泡": "Extra foam", "奶泡少一點": "Less foam",
    "想要愛心": "Heart, please", "想要鬱金香": "Tulip, please", "想要葉子": "Rosetta, please",
    "不要可可粉": "No cocoa",
    "濃一點": "Stronger", "淡一點": "Lighter",
    "少冰": "Less ice", "多冰": "Extra ice",
    "有點燙": "A bit too hot",
    "不夠熱": "Not hot enough",
    "奶泡跟我想的不太一樣": "Not the foam I wanted",
    "{name}糊糊的": "The {name} is smudged",
    "不是我要的{name}": "That's not a {name}",
    "{c}，不過好喝！": "{c}, but tasty!",
    "{c}，還可以。": "{c}, it's OK.",
    "嗯…{c}": "Hmm… {c}",
    "太好喝了，下次還來！": "Delicious, I'll be back!",
    "好喝，謝謝！": "Tasty, thanks!",
    "還不錯。": "Not bad.",
    "普普通通。": "So-so.",
    "嗯…（默默喝完）": "Hmm… (drinks it quietly)",
    "{prefix}{name}": "{prefix} {name}",

    # ───── 拉花卡片、狀態列、曲線卡片、點單紙 ─────
    "拉花": "Latte art",
    "拉花 · 指定{name}": "Art · {name} requested",
    "拉花 · {name}": "Art · {name}",
    "鮮奶油 · 可可粉": "Whipped cream · cocoa",
    "預熱中…  {t:.1f}°C": "Warming up…  {t:.1f}°C",
    "{name} 點了{title}，咖啡師準備中…": "{name} ordered: {title} · barista on it…",
    "{name} 點了{title} · 點擊咖啡機開始製作": "{name} ordered: {title} · click the machine to make it",
    "等待客人點單…": "Waiting for a customer…",
    "點擊咖啡機開始沖煮{name}": "Click the machine to brew: {name}",
    "  {name} {score:.0f} 分 · {comment}": "  {name} {score:.0f} pts · {comment}",
    "{name}：{text}": "{name}: {text}",
    " · 巧克力醬 {g:.0f}g": " · chocolate {g:.0f}g",
    " · 香草糖漿 {g:.0f}g": " · vanilla {g:.0f}g",
    " · 拉{name}": " · {name}",
    " · 熱水 {g:.0f}g": " · water {g:.0f}g",
    " · 冰塊 {n:.0f} · 冷水 {g:.0f}g": " · ice {n:.0f} · water {g:.0f}g",
    " · 冰塊 {n:.0f} · {milk} {g:.0f}g": " · ice {n:.0f} · {milk} {g:.0f}g",
    " · 冰塊 {n:.0f} · 通寧水 {g:.0f}g": " · ice {n:.0f} · tonic {g:.0f}g",
    " · 香草冰淇淋 {g:.0f}g": " · vanilla ice cream {g:.0f}g",
    " · {milk} {g:.0f}g {t:.0f}°C": " · {milk} {g:.0f}g {t:.0f}°C",
    " · 以 {name} 標準評分": " · judged as {name}",
    "顧客點單模式 · 下一位客人約 {sec}s 後到 · ": "Orders · next customer in ~{sec}s · ",
    "訂單 #{no} · ": "Order #{no} · ",
    "營業中 Lv.{lv} · 排隊 {n} · 今日 {rev} · ": "Open Lv.{lv} · queue {n} · today {rev} · ",
    # 成長：店鋪等級、咖啡師熟練度、小費罐、打烊日報
    "路邊小攤": "Street Stall", "巷口咖啡": "Corner Cart", "街角小店": "Corner Shop", "社區咖啡館": "Neighborhood Café",
    "人氣小店": "Popular Spot", "城市咖啡館": "City Café", "咖啡名所": "Coffee Landmark",
    "傳說咖啡館": "Legendary Café", "夢想咖啡館": "Dream Café",
    "新手": "Rookie", "熟手": "Skilled", "老手": "Veteran", "職人": "Artisan", "大師": "Master",
    "店鋪升級：Lv.{n} {name}！": "Shop level up: Lv.{n} {name}!",
    "咖啡師晉升：{name}！手感更穩了": "Barista promoted: {name}! Steadier hands now",
    "小有名氣": "Making a Name", "遠近馳名": "Known Far and Wide", "夢想成真": "Dream Come True",
    "店鋪升到 Lv.3": "Reach shop Lv.3", "店鋪升到 Lv.6": "Reach shop Lv.6", "店鋪升到 Lv.10": "Reach shop Lv.10",
    "小費": "TIPS",
    "打烊日報": "Closing Report", "打烊日報 {day}：服務 {n} 位，營業額 {rev}": "Closing report {day}: {n} served, {rev} revenue",
    "服務客人": "Served", "{n} 位": "{n}", "等太久離開": "Walked out", "　其中小費": "  incl. tips",
    "最佳一杯": "Best cup", "比上一個營業日": "vs. last business day", "升級！Lv.{a} → Lv.{b}": "Level up! Lv.{a} → Lv.{b}",
    "距離 Lv.{n}": "To Lv.{n}", "還差 {m}": "{m} to go", "已經是最高等級": "Top level reached",
    "今天解鎖 {n} 個成就": "{n} achievements unlocked today", "點一下收起": "Click to close",
    "店鋪": "Shop", "店鋪 Lv.{n} {name}": "Shop Lv.{n} {name}", "累積營業額": "Total revenue", "下一級": "Next level",
    "Lv.{n}：還差 {m}": "Lv.{n}: {m} to go", "來客": "Customers", "比開店時多 {p:.0f}%": "{p:.0f}% more than at opening",
    "客人耐心": "Patience", "多 {p:.0f}%": "+{p:.0f}%", "排隊上限": "Queue limit",
    "店鋪等級依營業模式的累積營業額（含小費）計算，等級越高客人越多、越有耐心。":
        "Shop level is based on total business-mode revenue (tips included). Higher levels bring more, and more patient, customers.",
    "咖啡師：{name}": "Barista: {name}", "做過的咖啡": "Cups made", "下一個稱號": "Next title",
    "{name}：還差 {n} 杯": "{name}: {n} cups to go", "已經是最高稱號": "Top title reached",
    "手感誤差": "Hand error", "新手的 {p:.0f}%": "{p:.0f}% of a rookie's",
    "每做一杯都算（手動、自動、營業）。越熟練，打奶溫度、奶泡量、研磨與拉花的誤差越小。":
        "Every cup counts (manual, auto, business). The more practiced, the smaller the errors in milk temperature, foam, grind and latte art.",
    "最近的營業日": "Recent business days", "服務 {n} 位 · {rev} · 小費 {tip}": "{n} served · {rev} · tips {tip}",
    "{arrow} {pct:.0f}%（{day}：{rev}）": "{arrow} {pct:.0f}% ({day}: {rev})",
    "成就紀錄": "Achievements", "已解鎖 {n} / {total}": "{n} / {total} unlocked", "分級成就": "TIERED",
    "單項成就": "SINGLE", "未解鎖": "locked", "— 還有 {n} 個等你解鎖 —": "— {n} more to unlock —",
    "全部解鎖了，謝謝光臨！": "All unlocked. Thank you, come again!",
    # 音樂播放
    "音樂": "Music", "♪ 正在播放：{title}": "♪ Now playing: {title}", "♪ 已暫停：{title}": "♪ Paused: {title}",
    "♪ 清單是空的": "♪ Playlist is empty", "播放": "Play", "暫停": "Pause", "下一首": "Next", "上一首": "Previous",
    "播放清單（{n} 首）": "Playlist ({n})", "加入音檔…": "Add files…", "加入資料夾…": "Add folder…",
    "加入音檔": "Add files", "加入資料夾": "Add folder", "從清單移除目前這首": "Remove current track",
    "清空清單": "Clear playlist", "播放順序": "Order", "依序循環": "Repeat all", "隨機": "Shuffle",
    "單曲循環": "Repeat one", "加入了 {n} 首": "Added {n} tracks", "沒有新的音檔（重複的已略過）": "No new tracks (duplicates skipped)",
    "找不到或無法播放 {name}，已跳過": "Can't play {name}, skipped",
    "音樂清單是空的：右鍵「音樂」加入音檔或資料夾": "Playlist is empty: right-click › Music to add files or a folder",
    "音樂：播放／暫停": "Music: play / pause", "音樂：下一首": "Music: next",
    # 商店：咖啡機升級、精品豆
    "商店": "Store", "錢包 {m}": "Wallet {m}",
    "累積營業額 {a} － 已花 {b}。店鋪等級照累積營業額計算，花錢不會掉級。":
        "Total revenue {a} − spent {b}. Shop level uses total revenue, so spending never lowers it.",
    "咖啡機升級": "Machine upgrades", "已購買": "Owned", "{machine} 升級：{name}": "{machine} upgraded: {name}",
    "已升級：{names}": "Upgrades: {names}",
    "專業奶泡機": "Pro Milk Frother", "換成專業奶泡機：奶泡更細，拉花更容易成功": "A pro frother: finer foam, latte art succeeds more often",
    "沖煮頭恆溫套環": "Thermal Group Collar", "沖煮頭水溫更穩：每杯飄動從 ±0.5°C 降到 ±0.2°C":
        "Steadier group temperature: per-cup drift drops from ±0.5°C to ±0.2°C",
    "PID 溫控套件": "PID Kit", "單鍋爐加裝 PID：每杯水溫飄動從 ±1.4°C 降到 ±0.4°C":
        "A PID for the single boiler: per-cup drift drops from ±1.4°C to ±0.4°C",
    "精密刀盤": "Precision Burrs", "內建磨豆機換成精密刀盤：研磨均勻，通道效應跟獨立磨豆機一樣":
        "Precision burrs for the built-in grinder: an even grind, with no more channeling than a standalone grinder",
    "精品咖啡豆": "Specialty beans", "精品豆（用營業額購買）…": "Specialty beans (buy with revenue)…",
    "一包 {g:.0f} g，取代目前這包：咖啡師沒在忙就馬上開封，正在做飲品就這杯做完換上（營業中也能買）。甜感比一般豆高，營業中用這包做的飲品售價 ×{k:g}。":
        "{g:.0f} g per bag, replacing the current one: opened right away if the barista is free, or swapped in after the current drink (you can buy during business too). Sweeter than regular beans; drinks made with it sell for ×{k:g} in business mode.",
    "{roast} · 甜感 +{s:g}": "{roast} · sweetness +{s:g}", "買一包 {m}": "Buy a bag {m}",
    "咖啡師正在忙，等這杯做完": "The barista is busy; wait for this cup to finish",
    "（正在用這包，剩 {g:.0f} g）": " (in use, {g:.0f} g left)",
    "巴拿馬 藝妓": "Panama Geisha", "茉莉、佛手柑、蜂蜜": "jasmine, bergamot, honey",
    "牙買加 藍山": "Jamaica Blue Mountain", "堅果、柔順、低酸": "nutty, smooth, low acidity",
    "夏威夷 可娜": "Hawaii Kona", "奶油、熱帶水果、紅糖": "butter, tropical fruit, brown sugar",
    # 重新遊玩
    "重新遊玩…": "Start over…", "重新遊玩": "Start over", "取消": "Cancel", "刪除並重新開始": "Delete and start over",
    "確定要從頭開始嗎？這個動作無法復原。": "Start over from scratch? This can't be undone.",
    "會刪除：每一杯的紀錄、成就、拉花收集與圖鑑、店鋪等級與咖啡師稱號、錢包與商店買的升級和精品豆、清潔保養計數、目前的豆子與冰滴。\n\n會保留：沖煮參數、聲音與音樂清單、語言、視窗位置與大小。":
        "Deletes: every cup on record, achievements, the latte-art collection and drink book, shop level and barista title, "
        "your wallet with store upgrades and specialty beans, maintenance counters, and the current beans and cold drip.\n\n"
        "Keeps: brew settings, sound and music playlist, language, window position and size.",
    "咖啡師正在做飲品，等這杯做完再試一次。": "The barista is making a drink. Try again once this cup is done.",
    "已重新開始：紀錄、等級與錢包都清空了": "Started over: records, levels and wallet are cleared",
    # 設備依店鋪等級解鎖
    "（Lv.{n} 解鎖）": " (unlocks at Lv.{n})", "{name}要店鋪 Lv.{n} 才解鎖": "{name} unlocks at shop Lv.{n}",
    "解鎖新設備：{names}": "New equipment unlocked: {names}",
    "店鋪 Lv.{n} 解鎖後才能升級": "Available after unlocking it at shop Lv.{n}",
    "獨立磨豆機": "Standalone grinder", "手沖用磨豆機": "Brew-station grinder",
    "平刀盤": "Flat Burrs", "鬼齒刀盤": "Ghost-Tooth Burrs",
    "獨立磨豆機換成平刀盤：研磨更均勻、通道效應更少，三台用獨立磨豆機的咖啡機都受惠":
        "Flat burrs for the standalone grinder: a more even grind with less channeling, for all three machines that use it",
    "手沖用磨豆機換成鬼齒刀盤：細粉更少，手沖、冰滴、摩卡壺、虹吸壺喝起來更乾淨、更甜，研磨偏細也比較不會萃取不均":
        "Ghost-tooth burrs for the brew-station grinder: fewer fines, so pour-over, cold drip, moka pot and siphon taste cleaner and sweeter, and fine grinds extract more evenly",
    "{n} 杯 · 最高 {s:.0f} 分": "{n} made · best {s:.0f}", "店鋪 Lv.{n} 解鎖": "Unlocks at shop Lv.{n}",
    "還沒做過": "Not made yet", "飲品（{n}/{total}）": "Drinks ({n}/{total})",
    # 模式三選一
    "手動：點一下做一杯": "Manual: one cup per click", "自動：照設定一直做同一杯": "Auto: keep making my drink",
    "營業：客人點單、賺營業額": "Business: take orders and earn", "自動間隔": "Auto interval",
    # 遊戲說明
    "說明": "Guide", "遊戲說明": "How to Play", "Lv.{lv}：{names}": "Lv.{lv}: {names}", "基本操作": "Basics",
    "點一下咖啡機（或沖煮台）做一杯；左鍵拖曳移動視窗；右鍵打開選單；滑鼠停在機身上看萃取曲線。":
        "Click the machine (or brew station) to make a drink; drag with the left button to move the window; right-click for the menu; hover the machine for the extraction chart.",
    "右鍵「參數設定…」調研磨、粉量、水溫等參數，下方會預估這組參數拿幾分。":
        "Right-click › Settings… to adjust grind, dose, temperature and more; the bottom line estimates the score.",
    "三種模式（右鍵選單上方三選一）": "Three modes (pick one at the top of the right-click menu)",
    "<b>手動</b>：點一下做一杯。": "<b>Manual</b>: one drink per click.",
    "<b>自動</b>：照目前的飲品與參數一直做同一杯，間隔在「自動間隔」選；適合當擺件。":
        "<b>Auto</b>: keeps making your current drink with your settings, at the pace set in Auto interval; good as a desk ornament.",
    "<b>營業</b>：客人排隊點單，咖啡師自己接單、賺營業額；這是遊戲的主體。":
        "<b>Business</b>: customers queue up and order, the barista serves them and you earn revenue; this is the main game.",
    "手動": "Manual", "自動": "Auto", "營業": "Business", "咖啡師稱號": "Barista title", "營業額、錢包": "Revenue, wallet",
    "店鋪等級、設備解鎖": "Shop level, unlocks", "成就（跟杯子有關的）": "Drink achievements", "客人、耐心、小費": "Customers, patience, tips",
    "營業怎麼玩": "Running the shop",
    "客人陸續進門排隊，每位都有耐心（點單紙下緣的細條），等太久會離開。":
        "Customers keep arriving and queue up; each has limited patience (the bar under the order slip) and leaves after waiting too long.",
    "分數＝飲品 65%＋照訂單要求 35%，等太久會扣分；84 分以上給 10% 小費，92 分以上 20%。":
        "Score = 65% drink + 35% following the order, minus a penalty for long waits; 84+ earns a 10% tip, 92+ earns 20%.",
    "離開營業模式或跨過午夜時，會出一張打烊日報。": "Leaving business mode or passing midnight brings up a closing report.",
    "店鋪等級：看累積營業額": "Shop level: based on total revenue",
    "等級越高，客人越多、越有耐心、出杯越快，排隊上限也變多；最高 Lv.{n}。":
        "Higher levels bring more, and more patient, customers, faster service and a longer queue; the top is Lv.{n}.",
    "設備依店鋪等級解鎖：<br>{list}": "Equipment unlocks by shop level:<br>{list}",
    "咖啡師稱號：看做過的總杯數（三種模式都算）": "Barista title: based on total drinks made (all modes count)",
    "{name} {n} 杯": "{name} {n} cups",
    "越熟練手感越穩、奶泡越細；而且 {base:.0f} 分以上的部分依稱號打折：{pct}。":
        "More practice means steadier hands and finer foam; the part of a score above {base:.0f} is also scaled by title: {pct}.",
    "錢包與商店（「商店」分頁）": "Wallet and store (Store tab)",
    "錢包＝累積營業額 － 已花的錢；花錢不會掉級。": "Wallet = total revenue − money spent; spending never lowers your level.",
    "咖啡機與磨豆機升級讓設備更穩、更好喝；精品豆比較甜，營業中用它做的飲品售價 ×{k:g}。":
        "Machine and grinder upgrades make your gear steadier and the coffee better; specialty beans are sweeter and drinks made with them sell for ×{k:g} in business mode.",
    "成就": "Achievements",
    "跟杯子有關的成就只算營業模式裡為客人做的杯子；清潔保養、開豆子、等冰滴照常算。":
        "Drink achievements only count drinks made for customers in business mode; cleaning, opening beans and cold drip count as usual.",
    "分級成就有銅、銀、金三級，「成就」分頁會顯示下一級還差多少。":
        "Tiered achievements have bronze, silver and gold; the Achievements tab shows how far the next tier is.",
    "小技巧": "Tips",
    "豆子烘焙後 7–21 天最好喝；豆子用完要開新包（自動、營業時咖啡師會自己開）。":
        "Beans taste best 7–21 days off roast; open a new bag when they run out (the barista does it in auto and business).",
    "狀態列出現 ⚠ 就是該清潔保養了，太久沒清會扣分。": "A ⚠ in the status bar means maintenance is due; skipping it too long costs points.",
    "冰滴要先架冰滴塔，之後在背景滴約 1 小時（關掉程式也照算）。":
        "Cold drip needs the tower set up first, then drips in the background for about an hour (even with the app closed).",
    "右鍵「聲音」可以開環境音，「音樂」可以播放自己的音檔。":
        "Right-click › Sound for ambience; Music plays your own audio files.",
    # 休息提醒自訂、播放速度
    "自訂…": "Custom…", "自訂（每 {m} 分鐘）…": "Custom (every {m} min)…", "每幾分鐘提醒一次？（5–240）": "Remind me every how many minutes? (5–240)",
    "確定": "OK", "播放速度（營業中固定 1×）": "Speed (fixed at 1× in business)",
    # 這杯做完換豆子
    "待換上：{name}（這杯做完換）": "Next bag: {name} (after this drink)", "已經有一包{name}等著換上": "A bag of {name} is already waiting",
    "已買{name}，這杯做完換上": "Bought {name}; swapping it in after this drink", "這杯做完換上{name}": "Switching to {name} after this drink",
    "已經有一包精品豆等著換上": "A bag of specialty beans is already waiting",
    "咖啡師正在做飲品：這杯做完換上": "The barista is busy: it goes in after this drink",
    "（已買，這杯做完換上）": " (bought, goes in after this drink)", "待換上": "Waiting",
    # 遊玩流程修正
    "沒有客人：咖啡師去架冰滴塔": "No customers: the barista sets up the cold drip tower",
    "歡迎！右鍵選「營業」開店，賺錢升級、解鎖新設備": "Welcome! Right-click › Business to open the shop and level up",
    "玩法說明：右鍵「紀錄與收集冊」→「說明」": "How to play: right-click › Records › Guide",
    # 飲品依咖啡師稱號解鎖
    "（{rank}解鎖）": " (unlocks at {rank})", "{name}要咖啡師「{rank}」才解鎖": "{name} unlocks when the barista reaches {rank}",
    "解鎖新飲品：{names}": "New drinks unlocked: {names}", "咖啡師「{rank}」解鎖": "Unlocks at {rank}",
    "{rank}：{names}": "{rank}: {names}", "節日限定": "Seasonal specials",
    "飲品依咖啡師稱號解鎖（沖煮台的飲品看店鋪等級）：<br>{list}":
        "Drinks unlock with the barista title (brew-station drinks follow the shop level):<br>{list}",
    # 設備圖鑑
    "設備（{n}/{total}）": "Equipment ({n}/{total})", "還沒用過": "Not used yet", "Lv.1 就有": "Available from Lv.1",
    "跟著手沖解鎖": "Comes with pour-over",
    "DESK·01、復古拉桿、小型單鍋爐共用": "Shared by DESK·01, the lever and the compact single boiler",
    "手沖、冰滴、摩卡壺、虹吸壺共用": "Shared by pour-over, cold drip, moka pot and siphon",
    "濾杯加細口壺，悶蒸後分段注水": "Dripper and gooseneck kettle: bloom, then pour in stages",
    "冰水一滴一滴滴過咖啡粉，約一小時": "Ice water drips through the grounds for about an hour",
    "爐火加熱下壺，蒸氣壓把咖啡推上來": "The stove heats the base and steam pressure pushes the coffee up",
    "酒精燈把水推上上壺，熄火後咖啡被吸回": "A spirit lamp pushes water to the top; off the heat, the coffee is drawn back down",
    # 手藝壓縮高分
    "{comment} · {rank}手感（實力 {raw:.0f} 分）": "{comment} · {rank} hands (true {raw:.0f})",
    "（{rank}手感：{score:.0f} 分）": " ({rank} hands: {score:.0f} pts)",
    "{name} 等太久，先走了": "{name} got tired of waiting and left",
    "等有點久": "Took a while",
    "營業額": "Revenue", "等太久離開的客人": "Customers who left", "平均等待": "Average wait", "{s:.0f} 秒": "{s:.0f}s",
    "生意興隆": "Booming Business", "一天營業額達 $15,000": "Take $15,000 in one day",
    "沒人久等": "No One Left Waiting", "一天服務 20 位客人，沒有人等到離開": "Serve 20 customers in a day with no walkouts",
    "兩千杯職人": "2,000-Cup Artisan", "為客人做了 2000 杯": "Make 2,000 drinks for customers",
    "排隊名店": "Famous Spot", "一天為客人做 80 杯": "Make 80 drinks for customers in one day",
    "全速運轉": "Full Throttle", "一天為客人做 150 杯": "Make 150 drinks for customers in one day",
    "每天一杯": "A Cup a Day", "連續 7 天都有營業": "Open for business 7 days in a row",
    "咖啡成癮": "Hooked", "連續 30 天都有營業": "Open for business 30 days in a row",
    "百日修行": "100-Day Practice", "連續 100 天都有營業": "Open for business 100 days in a row",
    "手感正熱": "On a Roll", "連續 30 張訂單 85 分以上": "Score 85+ on 30 orders in a row",
    "職人水準": "Master Level", "連續 60 張訂單 85 分以上": "Score 85+ on 60 orders in a row",
    "拉花圖鑑": "Art Collector", "為客人做出拉花收集的七種圖案": "Serve customers all seven latte art patterns",
    "節日巡禮": "Holiday Tour", "為客人做過每一款節日限定飲品": "Make every seasonal special for customers",
    "人機合一": "One with the Machine", "四台咖啡機都為客人沖出 90 分": "Serve a 90+ drink from all four machines",
    "人氣咖啡師": "Popular Barista", "300 張訂單拿到 84 分以上": "Score 84+ on 300 orders",
    "城裡最好喝": "Best in Town", "1000 張訂單拿到 84 分以上": "Score 84+ on 1,000 orders",
    "產地探索": "Origin Explorer", "用 4 個產地的豆子為客人做過咖啡": "Serve customers beans from 4 origins",
    "全產地制霸": "Every Origin", "用全部 10 個產地的豆子為客人做過咖啡（含精品豆）": "Serve customers beans from all 10 origins (specialty beans included)",
    "豆子愛好者": "Bean Lover", "開過 10 包豆子": "Open 10 bags of beans",
    "早起的咖啡師": "Early Bird", "早上 5–7 點為客人做一杯咖啡": "Serve a customer between 5 and 7 am",
    "夜貓子": "Night Owl", "晚上 11 點到凌晨 4 點為客人做一杯咖啡": "Serve a customer between 11 pm and 4 am",
    "第一杯手沖": "First Pour-Over", "為客人沖第一杯手沖咖啡": "Make your first pour-over for a customer",
    "手沖職人": "Pour-Over Pro", "為客人手沖出 90 分以上": "Serve a customer a 90+ pour-over",
    "悶蒸剛好": "Perfect Bloom", "悶蒸 30–45 秒、分 2 次以上注水，為客人沖出 85 分": "Bloom 30–45 s, pour in 2+ stages and serve a customer an 85+",
    "慢慢等": "Worth the Wait", "等一壺冰滴滴完": "Wait for a cold drip batch to finish",
    "高朋滿座": "Packed House", "一天營業額達 $5,000": "Take $5,000 in one day",
    "日進斗金": "Money Maker", "一天營業額達 $30,000": "Take $30,000 in one day",
    "服務周到": "Attentive Service", "一天服務 100 位客人，沒有人等到離開": "Serve 100 customers in a day with no walkouts",
    "零客訴": "Zero Complaints", "一天服務 50 位客人，沒有人等到離開": "Serve 50 customers in a day with no walkouts",
    "一日店長": "Shop Manager", "營業模式一天服務 30 位客人": "Serve 30 customers in business mode in one day",
    "小費罐滿了": "Full Tip Jar", "一天收到 $500 小費": "Get $500 in tips in one day",
    "尖峰時刻": "Rush Hour", "排了 4 位客人時沒有人離開，一路做到隊伍清空":
        "Clear a full 4-person queue with no one leaving",
    # ───── 手沖與冰滴 ─────
    "沖煮方式": "Brew Method", "自動模式": "Auto Mode", "每 {t} 做一杯": "One cup every {t}", "義式咖啡機": "Espresso machine", "手沖": "Pour-over", "冰滴": "Cold drip",
    "現在沒有可以點的飲品": "Nothing to order right now",
    "預估 {m}:{s:02d} · EY {ey:.1f}% · TDS {tds:.2f}% · {score:.0f} 分":
        "Est. {m}:{s:02d} · EY {ey:.1f}% · TDS {tds:.2f}% · {score:.0f} pts",
    "相當於滴 {h:.1f} 小時 · EY {ey:.1f}% · TDS {tds:.2f}% · {score:.0f} 分":
        "Like {h:.1f} h of dripping · EY {ey:.1f}% · TDS {tds:.2f}% · {score:.0f} pts",
    "手沖咖啡": "Pour-Over", "冰滴咖啡": "Cold Drip",
    "倒進杯子…": "Pouring into the cup…", "倒入冰滴咖啡…": "Pouring cold drip…",
    "準備濾杯與濾紙…": "Setting up dripper and filter…", "研磨 {g:.0f}g（{um:.0f}µm）…": "Grinding {g:.0f}g ({um:.0f}µm)…",
    "手沖壺就位…  {t:.0f}°C": "Kettle ready…  {t:.0f}°C", "悶蒸注水  {g:.0f} g": "Bloom pour  {g:.0f} g",
    "悶蒸中…  {t:.0f}/{b:.0f}s": "Blooming…  {t:.0f}/{b:.0f}s", "第 {n} 段注水  {clock}": "Pour {n}  {clock}",
    "滴濾中…  {clock}": "Drawing down…  {clock}", "拿掉濾杯…": "Removing dripper…",
    "架好冰滴塔…": "Setting up the drip tower…", "加入冰水 {g:.0f}g…": "Adding ice water {g:.0f}g…",
    "調整滴速：每 10 秒 {n:.0f} 滴": "Setting drip rate: {n:.0f} drops per 10 s",
    "萃取不均，味道混濁": "Uneven extraction, muddy", "乾淨但偏淡": "Clean but weak",
    "乾淨明亮、甜感飽滿": "Clean, bright and sweet",
    "冰滴滴完了，可以做 {n} 杯冰滴咖啡": "Cold drip is done: {n} cups ready",
    "冰滴還在滴，大約 {m} 分鐘後好": "Cold drip still dripping, about {m} min to go",
    "冰滴開始了，大約 {m} 分鐘後滴完（關掉程式也會繼續滴）":
        "Cold drip started, done in about {m} min (keeps dripping while the app is closed)",
    "{name} · {roast} {dose:g}g：{water:.0f}g · {um:.0f}µm · {t:g}°C · 悶蒸 {b:.0f}s · {n:.0f} 段注水":
        "{name} · {roast} {dose:g}g:{water:.0f}g · {um:.0f}µm · {t:g}°C · bloom {b:.0f}s · {n:.0f} pours",
    "{name} · {roast} {dose:g}g：{water:.0f}g · {um:.0f}µm · 每 10 秒 {r:.0f} 滴":
        "{name} · {roast} {dose:g}g:{water:.0f}g · {um:.0f}µm · {r:.0f} drops / 10 s",
    " · 約 {m} 分鐘後滴完": " · done in ~{m} min", " · 還有 {n} 杯": " · {n} cups left",
    "粉水比 1:": "Ratio 1:", "研磨": "Grind", "悶蒸": "Bloom", "注水段數": "Pours", "滴速（每 10 秒）": "Drip rate (per 10 s)",
    "秒": "s", "段": "", "滴": "drops",
    "{desc}（目前 {n}）": "{desc} (now {n})", "下一級：{desc}": "Next: {desc}", "已達最高級：{desc}": "Top tier: {desc}",
    "自動模式 · 下一杯 {sec}s · ": "Auto · next in {sec}s · ",
    "{machine} · 右鍵開啟選單 · 滑鼠停在機身上可看萃取曲線":
        "{machine} · right-click for the menu · hover the machine for the chart",
    "· 照一般做法": "· As usual",
    "等待製作{dots}": "Waiting{dots}",
    "製作中…": "Making…",
    "分": "pts",
    "還沒有萃取紀錄": "No extraction yet",
    "萃取曲線": "Extraction",
    "{score:.0f} 分": "{score:.0f} pts",
    "壓力 bar": "Pressure bar",
    "流速 g/s": "Flow g/s",
    "重量 g": "Weight g",

    # ───── 設定視窗 ─────
    "沖煮參數": "Brew settings",
    "研磨粒徑": "Grind size",
    "粉量": "Dose",
    "液重": "Yield",
    "水溫": "Water temp",
    "壓力": "Pressure",
    "預浸泡": "Pre-infusion",
    "布粉品質": "Distribution",
    "養豆天數": "Days off roast",
    "天": "d",
    "顆": "pcs",
    "烘焙度": "Roast",
    "粉碗容量 (g)": "Basket (g)",
    "牛奶量": "Milk",
    "奶泡量": "Foam",
    "一匙奶泡": "Spoon of foam",
    "打奶溫度": "Milk temp",
    "通寧水": "Tonic",
    "冰淇淋": "Ice cream",
    "熱水量": "Hot water",
    "冷水量": "Cold water",
    "冰塊": "Ice",
    "撒可可粉": "Dust with cocoa",
    "擠鮮奶油＋可可粉": "Whipped cream + cocoa",
    "牛奶種類": "Milk type",
    "植物奶較難拉花": "Plant milks foam less finely",
    "奶泡不夠細時會退化": "Degrades if the foam is too coarse",
    "沖一杯": "Brew one",
    "恢復預設": "Reset",
    "關閉": "Close",
    "這杯的濃縮：{dose:g} g → {y:g} g（1:{r:.1f}）": "Shot for this drink: {dose:g} g → {y:g} g (1:{r:.1f})",
    "，以 {style} 標準評分": ", judged as {style}",
    "預估 {t:.0f} 秒 · EY {ey:.1f}% · TDS {tds:.1f}% · {score:.0f} 分":
        "Estimate {t:.0f} s · EY {ey:.1f}% · TDS {tds:.1f}% · {score:.0f} pts",
    # ───── v7：紀錄、成就、豆子、季節、清潔 ─────
    "、": ", ",
    "{name}（{roast}）": "{name} ({roast})",
    "{n} 杯": "×{n}",
    "{name} · {score:.0f} 分": "{name} · {score:.0f} pts",
    "{title}（{n}/{total}）": "{title} ({n}/{total})",
    "（{fest}限定）": " ({fest} only)",
    "季節限定": "Seasonal",
    "季節限定：{name}": "Seasonal: {name}",
    "情人節": "Valentine's", "萬聖節": "Halloween", "聖誕節": "Christmas",
    "南瓜香料拿鐵": "Pumpkin Spice Latte", "薑餅拿鐵": "Gingerbread Latte",
    "玫瑰拿鐵": "Rose Latte",
    "南瓜香料醬": "Pumpkin spice sauce", "薑餅糖漿": "Gingerbread syrup",
    "玫瑰糖漿": "Rose syrup",
    "加入南瓜香料醬…": "Adding pumpkin spice…", "加入薑餅糖漿…": "Adding gingerbread syrup…",
    "加入玫瑰糖漿…": "Adding rose syrup…",
    "撒肉桂粉…": "Dusting cinnamon…",
    "鮮奶油 · 肉桂粉": "Whipped cream · cinnamon",
    # 豆子
    "豆子": "Beans",
    "目前：{name}（{roast}）": "Now: {name} ({roast})",
    "烘焙後第 {days} 天 · 剩 {g:.0f} g · {flavor}": "Day {days} off roast · {g:.0f} g left · {flavor}",
    "開一包新豆子": "Open a new bag",
    "隨機開一包": "Open a random bag",
    "開了一包新豆子：{name}（{roast}，{flavor}）": "Opened a new bag: {name} ({roast}, {flavor})",
    "豆子用完了，右鍵「豆子」開一包新的": "Out of beans: right-click > Beans to open a new bag",
    "{name} · 剩 {g:.0f} g": "{name} · {g:.0f} g left",
    "衣索比亞 耶加雪菲": "Ethiopia Yirgacheffe", "肯亞 AA": "Kenya AA", "哥倫比亞 薇拉": "Colombia Huila",
    "瓜地馬拉 安提瓜": "Guatemala Antigua", "桌上綜合配方": "Desk House Blend", "巴西 喜拉朵": "Brazil Cerrado",
    "印尼 曼特寧": "Sumatra Mandheling",
    "茉莉花香、柑橘": "jasmine, citrus", "黑醋栗、明亮果酸": "blackcurrant, bright acidity",
    "焦糖、紅莓": "caramel, red berries", "可可、香料": "cocoa, spice", "堅果、牛奶巧克力": "nuts, milk chocolate",
    "堅果、黑巧克力": "nuts, dark chocolate", "草本、黑糖、厚實": "herbal, brown sugar, heavy body",
    # 清潔保養
    "清潔保養": "Maintenance",
    "逆洗沖煮頭": "Backflush group", "清潔蒸氣管": "Clean steam wand", "清洗奶泡機": "Wash frother",
    "倒滴水盤": "Empty drip tray", "清空敲渣盒": "Empty knock box",
    "逆洗中…": "Backflushing…", "清潔蒸氣管…": "Cleaning steam wand…", "清洗奶泡機…": "Washing frother…",
    "倒掉滴水盤…": "Emptying drip tray…", "清空敲渣盒…": "Emptying knock box…",
    "逆洗沖煮頭（第 {n}/5 次）…": "Backflushing ({n}/5)…",
    "已沖 {n:.0f} 杯": "{n:.0f} shots", "已打 {n:.0f} 次奶": "{n:.0f} steamings", "{n:.0f} ml": "{n:.0f} ml",
    "{n:.0f} 個粉餅": "{n:.0f} pucks",
    "⚠ 該{task}了 · ": "⚠ Time to {task} · ",
    "{comment} · 該{task}了": "{comment} · time to {task}",
    # 紀錄與收集冊
    "紀錄與收集冊…": "Records & collection…",
    "紀錄與收集冊": "Records & collection",
    "今天": "Today", "近兩週": "Two weeks", "成就 {n}/{total}": "Achievements {n}/{total}",
    "拉花收集": "Latte art", "圖鑑": "Collection",
    "今天 {date}": "Today {date}", "杯數": "Cups", "平均分數": "Average", "點單": "Orders", "用掉的豆子": "Beans used",
    "今天最好的一杯": "Best cup today", "今天還沒有做咖啡": "No coffee yet today", "今天做了什麼": "Made today",
    "長條：杯數\u3000藍點：平均分數": "Bars: cups   Dots: average score",
    "兩週共 {n} 杯，平均 {avg} 分；累計 {all} 杯": "{n} cups in two weeks, average {avg}; {all} cups all-time",
    "每種圖案保留拉得最好的一次": "Your best pour of each pattern",
    "品質 {q:.0f} · {date}": "Quality {q:.0f} · {date}",
    "最高 {s:.0f} 分": "Best {s:.0f}",
    "豆子產地": "Bean origins",
    "成就解鎖：{name}": "Achievement unlocked: {name}",
    "第一杯": "First Cup", "為第一位客人做咖啡": "Make a drink for your first customer",
    "上手了": "Getting the Hang of It", "為客人做了 50 杯": "Make 50 drinks for customers",
    "五百杯咖啡師": "500-Cup Barista", "為客人做了 500 杯": "Make 500 drinks for customers",
    "忙碌的一天": "Busy Day", "一天為客人做 40 杯": "Make 40 drinks for customers in one day",
    "完美一杯": "Perfect Cup", "為客人做出 95 分以上的一杯": "Serve a customer a drink scoring 95+",
    "穩定發揮": "Consistent", "連續 10 張訂單 85 分以上": "Score 85+ on 10 orders in a row",
    "葉子拉成了": "Rosetta!", "為客人拉出一片漂亮的葉子": "Pour a clean rosetta for a customer",
    "拉花三連": "Art Trio", "為客人拉出愛心、鬱金香、葉子": "Pour a heart, tulip and rosetta for customers",
    "全品項": "Full Menu", "客人點的每一種常態飲品都做過": "Make every regular drink for customers",
    "機器收藏家": "Machine Collector", "四台咖啡機都為客人沖過": "Serve customers from all four machines",
    "植物奶玩家": "Plant-Based", "為客人用過燕麥奶、豆奶、杏仁奶": "Use oat, soy and almond milk for customers",
    "熟客滿意": "Happy Regulars", "50 張訂單拿到 84 分以上": "Score 84+ on 50 orders",
    "搞定挑剔的客人": "Picky Customer", "兩個要求的訂單完全符合": "Nail an order with two requests",
    "季節限定": "Seasonal", "為客人做一杯節日限定飲品": "Make a seasonal special for a customer",
    "賞味期": "Peak Freshness", "用烘焙後 7–21 天的豆子為客人沖出 90 分": "Serve a 90+ drink with beans 7–21 days off roast",
    "環遊世界": "Around the World", "用 7 個產地的豆子為客人做過咖啡": "Serve customers beans from 7 origins",
    "乾淨的吧台": "Clean Bar", "四種清潔保養都做過": "Do all four maintenance tasks",
    # ───── v8 ─────
    "⚠ 偵測到 {n} 筆紀錄被修改或刪除，這些紀錄不列入統計": "⚠ {n} record(s) were modified or deleted and are excluded from the stats",
    "最近幾杯": "Recent",
    "還沒有紀錄": "No records yet",
    "（點單）": "(order)",
    # ───── 環境音、休息提醒、檢查更新 ─────
    "開啟聲音": "Sound on", "環境音": "Ambience","不播放": "Off", "咖啡廳": "Café", "雨天": "Rain",
    "小聲": "Quiet", "中等": "Medium", "大聲": "Loud",
    "休息提醒": "Break reminder", "不提醒": "Off", "每 {m} 分鐘": "Every {m} min",
    "重新計時": "Restart timer", "重新計時（還有 {m} 分鐘）": "Restart timer ({m} min left)",
    "休息一下：起來走走、喝杯咖啡吧（已經 {m} 分鐘了）": "Time for a break: stretch and grab a coffee ({m} min)",
    "休息提醒：還有 {m} 分鐘": "Break in {m} min",
    "更新": "Updates", "每天自動檢查新版本": "Check for updates daily", "立即檢查更新": "Check for updates now",
    "檢查新版本中…": "Checking for updates…",
    "無法檢查更新（請確認網路連線）": "Couldn't check for updates (check your connection)",
    "有新版本 {tag}：右鍵選單最上面「下載新版」": "Version {tag} is available: see \"Download\" at the top of the right-click menu",
    "已經是最新版本（{v}）": "You're up to date ({v})",
    "⬆ 下載新版 {tag}…": "⬆ Download {tag}…",
    # ───── 摩卡壺、虹吸壺 ─────
    "摩卡壺": "Moka pot", "虹吸壺": "Siphon", "摩卡壺咖啡": "Moka Pot Coffee", "虹吸咖啡": "Siphon Coffee",
    "火力": "Heat", "浸泡": "Steep",
    "{name} · {roast} {dose:g}g · {um:.0f}µm · 火力 {h:g}": "{name} · {roast} {dose:g}g · {um:.0f}µm · heat {h:g}",
    "{name} · {roast} {dose:g}g：{water:.0f}g · {um:.0f}µm · {t:g}°C · 浸泡 {s:.0f}s":
        "{name} · {roast} {dose:g}g:{water:.0f}g · {um:.0f}µm · {t:g}°C · steep {s:.0f}s",
    "轉開摩卡壺、下壺加水…": "Unscrewing the pot, filling the base…",
    "裝粉、鎖緊上壺…": "Filling the basket, screwing it shut…",
    "點火（火力 {h:g}）…": "Lighting the stove (heat {h:g})…",
    "等水煮開…  {clock}": "Waiting for the water to boil…  {clock}",
    "咖啡冒出來了…  {clock}": "Coffee's coming up…  {clock}",
    "咕嚕咕嚕…快好了  {clock}": "Gurgling… almost done  {clock}",
    "關火…": "Turning off the heat…",
    "下壺加入 {g:.0f}g 熱水…": "Adding {g:.0f}g hot water to the bottom globe…",
    "點燈…": "Lighting the lamp…",
    "加熱下壺…  {clock}": "Heating the bottom globe…  {clock}",
    "水被推上上壺…": "Water rising into the top chamber…",
    "下粉…  {t:.0f}°C": "Adding the grounds…  {t:.0f}°C",
    "攪拌…": "Stirring…",
    "浸泡中…  {t:.0f}/{b:.0f}s": "Steeping…  {t:.0f}/{b:.0f}s",
    "第二次攪拌、熄火…": "Second stir, flame off…",
    "咖啡被吸回下壺…": "Coffee drawing back down…",
    "拿掉上壺…": "Removing the top chamber…",
    "火太大，帶焦苦味": "Heat too high, scorched and bitter",
    "粉太細卡住濾布，味道混濁": "Grind too fine, filter clogged, muddy",
    "濃郁厚實、帶焦糖甜感": "Rich and heavy, caramel sweetness",
    "圓潤乾淨、香氣飽滿": "Round and clean, very aromatic",
    "爐火純青": "Stovetop Master", "摩卡壺為客人沖出 85 分": "Serve a customer an 85+ moka pot coffee",
    "虹吸達人": "Siphon Pro", "虹吸壺為客人沖出 85 分": "Serve a customer an 85+ siphon coffee",
    "沖煮方式全制霸": "Every Method",
    "義式、手沖、冰滴、摩卡壺、虹吸壺都為客人做過": "Serve customers espresso, pour-over, cold drip, moka pot and siphon",
}
