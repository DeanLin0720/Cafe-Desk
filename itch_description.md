# Café Desk 桌上咖啡吧 ／ Café Desk

放在桌面上的咖啡機擺件。透明、無邊框的視窗裡站著咖啡機、磨豆機和各種器具，點一下就用動畫與合成音效做一杯咖啡，最後給一個簡單的分數。

A desktop coffee-machine ornament. A transparent, borderless window holds espresso machines, grinders and all the bar tools. Click a machine and it brews a drink with animation and synthesized sound effects, then gives you a simple score.

---

## 特色 ／ Features

- **四台咖啡機**：DESK·01 雙錶不鏽鋼機、復古拉桿機、小型單鍋爐機、內建磨豆的一體機。每台的特性都會影響萃取結果。
  *Four machines: a dual-gauge stainless machine, a vintage lever machine, a small single-boiler machine, and an all-in-one with built-in grinder. Each one changes the extraction.*
- **16 種飲品**：濃縮、美式、拿鐵、卡布奇諾、馥列白、摩卡、焦糖瑪奇朵、濃縮通寧、阿芙佳朵等，另有節日期間才會出現的 3 款季節限定。
  *16 drinks, including espresso, americano, latte, cappuccino, flat white, mocha, caramel macchiato, espresso tonic and affogato, plus 3 seasonal drinks that appear during festivals.*
- **完整的備粉流程**：取把手 → 敲渣 → 磨豆 → 布粉 → 填壓 → 扣回。
  *The full prep routine: take out the portafilter → knock out grounds → grind → distribute → tamp → tap out.*
- **打奶與拉花**：依奶泡細緻度決定拉花圖案，從 blob、heart、tulip 到 rosetta，也可以指定圖案挑戰。
  *Steam milk and pour latte art. Patterns range from blob to heart, tulip and rosetta, and you can aim for a specific design.*
- **顧客點單**：客人會點單，依照要求（糖、奶、溫度、拉花等）調整你的操作，並給出符合度評分。
  *Customers place orders with requests (sweetness, milk, temperature, art). Match them to score well.*
- **豆子與養豆**：每包豆子有產地、烘焙度與風味，豆子會隨天數變化。
  *Beans have origin, roast and flavor, and they change as they rest.*
- **清潔保養**：沖煮後要沖水、清粉碗、清蒸氣管，不清會扣分。
  *Keep the machine clean: backflush, drip tray and steam wand. Neglect costs points.*
- **每日紀錄、17 個成就、拉花收集冊**。
  *Daily stats, 17 achievements and a latte-art collection book.*
- **中文／English** 介面，可隨時切換。
  *Traditional Chinese and English interface, switchable at any time.*
- **擺件模式**：可拖曳到桌面任意位置（會記住），可置頂、可縮放，系統匣可叫回視窗。
  *Desktop-companion mode: drag it anywhere on screen (the position is remembered), keep it on top, resize it, and recall it from the system tray.*

---

## 操作 ／ Controls

| 動作 ／ Action | 說明 ／ Description |
|---|---|
| 左鍵點咖啡機或磨豆機 ／ Left-click machine or grinder | 開始沖煮 ／ Start brewing |
| 滑鼠停在機身上 ／ Hover over a machine | 顯示萃取曲線卡片（拿鐵類會同時顯示拉花）／ Show the extraction curve card (latte-style drinks also show art) |
| 左鍵拖曳 ／ Left-drag | 移動位置（會記住）／ Move the window (position is saved) |
| 右鍵 ／ Right-click | 選單：飲品、咖啡機、參數設定、豆子、清潔保養、紀錄與收集冊、自動模式、顧客點單、大小、Language、關於… ／ Menu: drinks, machines, settings, beans, maintenance, records & collection, auto mode, orders, size, language, about… |
| 系統匣圖示 ／ Tray icon | 單擊叫回咖啡機；右鍵有沖煮、自動模式、結束 ／ Click to bring the window back; right-click for brew, auto mode and quit |

同一時間只會有一個 Café Desk 在執行，再開一次會把原本那台叫出來。
*Only one copy runs at a time. Opening it again brings the existing window back.*

---

## 安裝與執行 ／ Installation

**Windows**：下載壓縮檔，解壓縮到任意資料夾，執行 `CafeDesk.exe`。請整個資料夾一起保留，不要只拿出 exe。
**Windows**: Download the archive, extract it to any folder, and run `CafeDesk.exe`. Keep the whole folder together; the exe alone will not work.

*開發者從原始碼執行 ／ Running from source (developers):*

```
pip install PySide6
pythonw main.py
```

---

## 資料檔 ／ Data Files

所有資料都放在程式旁邊，不會上傳到任何地方。資料夾無法寫入時會改放在使用者資料夾。
*All data stays next to the program and is never uploaded anywhere. If that folder is not writable, data goes to your user folder instead.*

| 檔案 ／ File | 內容 ／ Content |
|---|---|
| `cafe_desk.json` | 設定（刪除即恢復預設）／ Settings (delete to reset) |
| `cafe_desk_records.db` | 每杯紀錄與成就（SQLite）／ Per-cup records and achievements (SQLite) |
| `cafe_desk.log` | 錯誤紀錄，回報問題時可附上 ／ Error log, useful when reporting bugs |
| `sound/` | 第一次執行時合成的音效 ／ Sound effects synthesized on first run |

---

## 授權 ／ License

[MIT License](LICENSE) © 2026 DeanLin

---

## 回饋與問題 ／ Feedback & Bugs

遇到問題歡迎留言，並附上 `cafe_desk.log` 內容。
*If you run into a problem, please leave a comment and include the contents of `cafe_desk.log`.*

感謝試玩！☕
*Thanks for playing!* ☕
