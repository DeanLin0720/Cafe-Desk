# Café Desk 桌上咖啡吧

**繁體中文** ｜ [English](#english)

放在桌面上的咖啡機擺件。視窗裡站著咖啡機、磨豆機和各種器具（預設是一般視窗；右鍵取消「視窗化顯示」就變成透明無邊框、直接站在桌面上），點一下就用動畫和合成音效做一杯咖啡，最後給一個簡單的分數。

- 五種沖煮方式，各有自己的畫面：義式咖啡機、手沖、冰滴、摩卡壺、虹吸壺（冰滴約 1 小時，依架好時記下的時間計算；關掉程式時不會執行，重開時依經過的時間算出進度）
- 四台咖啡機（DESK·01 雙錶不鏽鋼機、復古拉桿機、小型單鍋爐機、內建磨豆的一體機），各有特性影響萃取
- 濃縮、美式、拿鐵、卡布奇諾、馥列白、摩卡、焦糖瑪奇朵、濃縮通寧、阿芙佳朵等 16 種義式飲品，加上手沖、冰滴、摩卡壺、虹吸；節日期間另有 3 款季節限定
- 完整備粉流程（取把手 → 敲渣 → 磨豆 → 布粉 → 填壓 → 扣回）、打奶與拉花、豆子與養豆天數、清潔保養（每台咖啡機分開計算）
- 顧客點單（營業模式）：客人排隊、有耐心、會等到離開，有價格與小費、當日營業額；客人隨機點，自動換咖啡機與沖煮方式
- 自動模式：照目前的設定重複沖煮
- 每日紀錄、51 個成就（8 組分成銅／銀／金三級）、拉花收集冊
- 繁體中文／English

<p align="center">
  <img src="docs/images/desk01.png" alt="Café Desk：做完一杯拿鐵，上方是萃取曲線與拉花卡片" width="480">
</p>

## 畫面

### 一杯拿鐵的過程

<table width="100%">
  <tr>
    <td width="33%" align="center" valign="top"><img src="docs/images/brew.png" alt="萃取中" width="240" height="278"><br><b>萃取</b><br>咖啡液流進杯中，磅秤顯示重量與時間</td>
    <td width="33%" align="center" valign="top"><img src="docs/images/steam.png" alt="打奶泡" width="240" height="278"><br><b>打奶</b><br>蒸汽管打奶，溫度與奶泡量影響拉花</td>
    <td width="33%" align="center" valign="top"><img src="docs/images/pour.png" alt="拉花" width="240" height="278"><br><b>拉花</b><br>傾倒牛奶，拉花卡片即時顯示圖案</td>
  </tr>
</table>

做完後狀態列給星等、分數與評語；滑鼠停在機身上會顯示萃取曲線與拉花卡片。

### 四台咖啡機

<table width="100%">
  <tr>
    <td width="50%" align="center" valign="top"><img src="docs/images/desk01.png" alt="DESK·01 雙錶不鏽鋼機" width="420" height="487"><br><b>DESK·01 雙錶不鏽鋼機</b></td>
    <td width="50%" align="center" valign="top"><img src="docs/images/lever.png" alt="復古拉桿機" width="420" height="487"><br><b>復古拉桿機</b></td>
  </tr>
  <tr>
    <td width="50%" align="center" valign="top"><img src="docs/images/compact.png" alt="小型單鍋爐機" width="420" height="487"><br><b>小型單鍋爐機</b></td>
    <td width="50%" align="center" valign="top"><img src="docs/images/allinone.png" alt="內建磨豆的一體機" width="420" height="487"><br><b>內建磨豆的一體機</b></td>
  </tr>
</table>

### 手沖與冰滴

<table width="100%">
  <tr>
    <td width="33%" align="center" valign="top"><img src="docs/images/pourover.png" alt="手沖注水" width="240" height="278"><br><b>手沖</b><br>沖煮時畫面拉近：悶蒸、分段繞圈注水、滴濾</td>
    <td width="33%" align="center" valign="top"><img src="docs/images/pourover_serve.png" alt="分享壺倒進杯子" width="240" height="278"><br><b>倒進杯子</b><br>沖完拉遠，分享壺倒進杯子；左邊是手沖用磨豆機</td>
    <td width="33%" align="center" valign="top"><img src="docs/images/colddrip.png" alt="冰滴塔" width="240" height="278"><br><b>冰滴</b><br>依實際經過的時間滴約 1 小時（關掉程式時間也照算），滴完可以做 4 杯</td>
  </tr>
</table>

右鍵「沖煮方式」切換義式咖啡機、手沖、冰滴；「飲品」選單只列出這個方式能做的飲品。

### 營業模式

<p align="center">
  <img src="docs/images/business.png" alt="營業模式：點單紙後面疊著排隊的訂單" width="420">
</p>

右鍵勾選「顧客點單模式」：客人隨時上門排隊（最多 4 位），點單紙後面疊著排隊的訂單、下緣是客人剩下的耐心；
咖啡師自己接單，客人點什麼就自動換到那台咖啡機或沖煮方式。狀態列顯示排隊人數與今日營業額。

## 安裝與執行

開發與測試環境：Windows 11、Python 3.14、PySide6 6.12。

```
pip install PySide6
pythonw main.py
```

Windows 用 `pythonw` 不會多開一個主控台視窗；要看錯誤訊息時改用 `python`。

## 操作

| 動作 | 說明 |
|---|---|
| 左鍵點咖啡機或磨豆機 | 開始沖煮（手沖、冰滴畫面點任何地方） |
| 滑鼠停在機身上 | 顯示萃取曲線卡片（拿鐵類會同時顯示拉花） |
| 左鍵拖曳 | 移動位置（會記住） |
| 右鍵 | 選單：沖煮方式、咖啡機、飲品、拉花圖案、參數設定、豆子、清潔保養、紀錄與收集冊、自動模式（含沖煮間隔）、顧客點單、視窗化顯示、大小、Language、關於… |
| 系統匣圖示 | 單擊叫回咖啡機；右鍵有沖煮、自動模式、顧客點單、結束 |

| 模式 | 說明 |
|---|---|
| 一般 | 點沖煮設備做目前選的飲品 |
| 自動模式 | 每隔設定的間隔，照目前的飲品與參數再做一杯（豆子用完自己開新包、該清潔時自己清） |
| 顧客點單 | 營業模式：客人隨機點、排隊、有耐心，咖啡師自己接單；點單時沖煮方式、咖啡機、飲品等選單鎖住 |

| 陪伴功能 | 說明 |
|---|---|
| 環境音 | 下雨天的咖啡廳（人聲、吧台、杯盤、窗外雨聲），或森林雨聲（偶爾遠雷）；三段音量，在右鍵「聲音」子選單，跟著「開啟聲音」 |
| 休息提醒 | 每 25／45／60 分鐘提醒休息，咖啡師順便做一杯 |
| 檢查更新 | 每天查一次 GitHub Releases，有新版時右鍵選單最上面出現「下載新版」；可在「更新」關閉 |

同一份設定檔只會有一個 Café Desk 在跑，再開一次會把原本那台叫出來。完整的功能說明在 `main.py` 開頭。

## 資料檔

都放在程式旁（打包後是 `CafeDesk.exe` 旁），資料夾無法寫入時改放使用者資料夾。右鍵「關於 Café Desk…」可以看到位置並開啟資料夾。

| 檔案 | 內容 |
|---|---|
| `cafe_desk.json` | 設定（刪除即恢復預設） |
| `cafe_desk_records.db` | 每杯紀錄與成就（SQLite，每筆有簽章） |
| `cafe_desk.log` | 錯誤紀錄（回報問題時請附上） |
| `sound/` | 第一次執行時合成的音效 |

## 打包（Windows）

```
pip install pyinstaller
pyinstaller --noconfirm CafeDesk.spec
```

輸出在 `dist/CafeDesk/`，整個資料夾一起發佈，執行 `CafeDesk.exe`。

## 開發

```
pip install pytest
python -m pytest
```

測試在無頭模式執行，不會開視窗也不會出聲。`tools/` 裡有壓力測試、各階段截圖、畫面回歸比對等工具。
架構、慣例與注意事項見 `CLAUDE.md`，開發歷程與待辦見 `handoff.md`，版本變更見 `CHANGELOG.md`。

## 授權

[MIT License](LICENSE) © 2026 DeanLin

---

<a id="english"></a>

# Café Desk

[繁體中文](#café-desk-桌上咖啡吧) ｜ **English**

A coffee machine desktop toy. A window holds an espresso machine, a grinder and assorted gear (a normal window by default; untick "Windowed" in the right-click menu to make it a transparent, borderless toy standing on your desktop). Click once and it makes a coffee with animation and synthesized sound effects, then gives you a simple score.

- Five brew methods, each with its own scene: espresso machine, pour-over, cold drip, moka pot and siphon (cold drip takes about an hour, measured from the time the tower was set up; nothing runs while the app is closed, and on the next launch the progress is worked out from the elapsed time)
- Four machines (DESK·01 dual-gauge steel machine, vintage lever machine, compact single-boiler machine, all-in-one with built-in grinder), each with traits that affect extraction
- 16 espresso drinks including espresso, americano, latte, cappuccino, flat white, mocha, caramel macchiato, espresso tonic and affogato, plus pour-over, cold drip, moka pot and siphon, and 3 seasonal specials during festivals
- Full prep workflow (take the portafilter → knock out → grind → distribute → tamp → lock in), milk steaming and latte art, beans and rest days, cleaning and maintenance (tracked per machine)
- Customer orders (business mode): customers queue up, have limited patience and may leave, pay prices and tips toward today's revenue; they order at random and the barista switches machines and brew methods to match
- Auto mode: keeps brewing your current drink with your current settings
- Daily records, 51 achievements (8 sets with bronze / silver / gold tiers), a latte art collection
- 繁體中文 / English

<p align="center">
  <img src="docs/images/desk01_en.png" alt="Café Desk: a finished latte with the extraction curve and latte art cards above" width="480">
</p>

## Screenshots

### Making a latte

<table width="100%">
  <tr>
    <td width="33%" align="center" valign="top"><img src="docs/images/brew_en.png" alt="Brewing" width="240" height="278"><br><b>Brew</b><br>Espresso flows into the cup, the scale shows weight and time</td>
    <td width="33%" align="center" valign="top"><img src="docs/images/steam_en.png" alt="Steaming milk" width="240" height="278"><br><b>Steam</b><br>The steam wand heats the milk, temperature and foam amount shape the art</td>
    <td width="33%" align="center" valign="top"><img src="docs/images/pour_en.png" alt="Pouring latte art" width="240" height="278"><br><b>Pour</b><br>Pouring milk, the art card shows the pattern live</td>
  </tr>
</table>

When a drink is done, the status bar shows stars, a score and a comment. Hover over the machine to see the extraction curve and latte art cards.

### Four machines

<table width="100%">
  <tr>
    <td width="50%" align="center" valign="top"><img src="docs/images/desk01_en.png" alt="DESK·01 dual-gauge steel machine" width="420" height="487"><br><b>DESK·01 dual-gauge steel machine</b></td>
    <td width="50%" align="center" valign="top"><img src="docs/images/lever_en.png" alt="Vintage lever machine" width="420" height="487"><br><b>Vintage lever machine</b></td>
  </tr>
  <tr>
    <td width="50%" align="center" valign="top"><img src="docs/images/compact_en.png" alt="Compact single-boiler machine" width="420" height="487"><br><b>Compact single-boiler machine</b></td>
    <td width="50%" align="center" valign="top"><img src="docs/images/allinone_en.png" alt="All-in-one with built-in grinder" width="420" height="487"><br><b>All-in-one with built-in grinder</b></td>
  </tr>
</table>

### Pour-over and cold drip

<table width="100%">
  <tr>
    <td width="33%" align="center" valign="top"><img src="docs/images/pourover_en.png" alt="Pour-over" width="240" height="278"><br><b>Pour-over</b><br>The view zooms in while brewing: bloom, pulse pours, drawdown</td>
    <td width="33%" align="center" valign="top"><img src="docs/images/pourover_serve_en.png" alt="Serving from the server" width="240" height="278"><br><b>Serve</b><br>It zooms back out and pours the server into the cup; the pour-over grinder is on the left</td>
    <td width="33%" align="center" valign="top"><img src="docs/images/colddrip_en.png" alt="Cold drip tower" width="240" height="278"><br><b>Cold drip</b><br>Takes about an hour of elapsed clock time (time keeps counting while the app is closed), then makes 4 cups</td>
  </tr>
</table>

Use "Brew Method" in the right-click menu to switch between the espresso machine, pour-over and cold drip; the drinks menu lists only what that method can make.

### Business mode

<p align="center">
  <img src="docs/images/business_en.png" alt="Business mode: queued orders stacked behind the order slip" width="420">
</p>

Tick "Customer orders" in the right-click menu: customers keep arriving and queue up (up to 4), queued orders stack behind the slip and the bar at its bottom shows how much patience is left.
The barista takes the orders and switches to the machine or brew method each drink needs. The status bar shows the queue and today's revenue.

## Install and run

Developed and tested on Windows 11, Python 3.14, PySide6 6.12.

```
pip install PySide6
pythonw main.py
```

On Windows, `pythonw` avoids opening an extra console window, use `python` when you need to see error messages.

## Controls

| Action | What it does |
|---|---|
| Left-click the machine or grinder | Start brewing (anywhere in the pour-over and cold drip scenes) |
| Hover over the machine | Show the extraction curve card (with latte art for milk drinks) |
| Left-drag | Move the window (position is remembered) |
| Right-click | Menu: brew method, machine, drinks, latte art, settings, beans, cleaning, records and collection, auto mode (with interval), customer orders, windowed, size, Language, About… |
| Tray icon | Click to bring the machine back, right-click for brew, auto mode, customer orders, quit |

| Mode | What it does |
|---|---|
| Normal | Click the brewer to make the selected drink |
| Auto mode | Makes the selected drink again with your settings at the chosen interval (opens a new bag and cleans when needed) |
| Customer orders | Business mode: random orders, a queue and patience, the barista takes orders itself; brew method, machine, drink and similar menus are locked while it runs |

| Extra | What it does |
|---|---|
| Ambience | Rainy-day café (chatter, the bar, cups, rain outside), or forest rain with distant thunder; three volume levels, in the right-click Sound submenu (follows "Sound on") |
| Break reminder | Reminds you to take a break every 25/45/60 minutes, and the barista makes a cup |
| Updates | Checks GitHub Releases once a day; when a new version is out, "Download" appears at the top of the right-click menu. Can be turned off under Updates |

Only one Café Desk runs per config file, launching it again brings the running one to the front. A full feature description is at the top of `main.py`.

## Data files

Stored next to the program (next to `CafeDesk.exe` when packaged), or in the user folder if that folder is not writable. Right-click "About Café Desk…" to see the location and open the folder.

| File | Contents |
|---|---|
| `cafe_desk.json` | Settings (delete to reset to defaults) |
| `cafe_desk_records.db` | Per-cup records and achievements (SQLite, each row signed) |
| `cafe_desk.log` | Error log (please attach it when reporting issues) |
| `sound/` | Sound effects synthesized on first run |

## Packaging (Windows)

```
pip install pyinstaller
pyinstaller --noconfirm CafeDesk.spec
```

The output is in `dist/CafeDesk/`. Distribute the whole folder and run `CafeDesk.exe`.

## Development

```
pip install pytest
python -m pytest
```

Tests run headless: no windows, no sound. `tools/` has stress tests, per-stage screenshots and render regression tools.
See `CLAUDE.md` for architecture and conventions, `handoff.md` for history and TODOs, and `CHANGELOG.md` for version changes.

## License

[MIT License](LICENSE) © 2026 DeanLin
