# Café Desk 桌上咖啡吧

放在桌面上的咖啡機擺件。透明無邊框的視窗裡站著咖啡機、磨豆機和各種器具，點一下就用動畫和合成音效做一杯咖啡，最後給一個簡單的分數。

- 四台咖啡機（DESK·01 雙錶不鏽鋼機、復古拉桿機、小型單鍋爐機、內建磨豆的一體機），各有特性影響萃取
- 濃縮、美式、拿鐵、卡布奇諾、馥列白、摩卡、焦糖瑪奇朵、濃縮通寧、阿芙佳朵等 16 種飲品，節日期間另有 3 款季節限定
- 完整備粉流程（取把手 → 敲渣 → 磨豆 → 布粉 → 填壓 → 扣回）、打奶與拉花、顧客點單、豆子與養豆天數、清潔保養
- 每日紀錄、17 個成就、拉花收集冊
- 繁體中文／English

<p align="center">
  <img src="docs/images/desk01.png" alt="Café Desk：做完一杯拿鐵，上方是萃取曲線與拉花卡片" width="420">
</p>

## 畫面

### 一杯拿鐵的過程

| 萃取 | 打奶 | 拉花 |
|:---:|:---:|:---:|
| <img src="docs/images/brew.png" alt="萃取中" width="260"> | <img src="docs/images/steam.png" alt="打奶泡" width="260"> | <img src="docs/images/pour.png" alt="拉花" width="260"> |
| 咖啡液流進杯中，磅秤顯示重量與時間 | 蒸汽管打奶，溫度與奶泡量影響拉花 | 傾倒牛奶，拉花卡片即時顯示圖案 |

做完後狀態列給星等、分數與評語；滑鼠停在機身上會顯示萃取曲線與拉花卡片。

### 四台咖啡機

| DESK·01 | 復古拉桿機 |
|:---:|:---:|
| <img src="docs/images/desk01.png" alt="DESK·01 雙錶不鏽鋼機" width="300"> | <img src="docs/images/lever.png" alt="復古拉桿機" width="300"> |
| **小型單鍋爐機** | **內建磨豆的一體機** |
| <img src="docs/images/compact.png" alt="小型單鍋爐機" width="300"> | <img src="docs/images/allinone.png" alt="內建磨豆的一體機" width="300"> |

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
| 左鍵點咖啡機或磨豆機 | 開始沖煮 |
| 滑鼠停在機身上 | 顯示萃取曲線卡片（拿鐵類會同時顯示拉花） |
| 左鍵拖曳 | 移動位置（會記住） |
| 右鍵 | 選單：飲品、咖啡機、參數設定、豆子、清潔保養、紀錄與收集冊、自動模式、顧客點單、大小、Language、關於… |
| 系統匣圖示 | 單擊叫回咖啡機；右鍵有沖煮、自動模式、結束 |

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
