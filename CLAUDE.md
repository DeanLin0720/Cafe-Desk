# CLAUDE.md — Café Desk 桌上咖啡吧（舊名 Espresso Desk）1.0.0

## 專案概要
用 Python + PySide6 寫的桌面擺件：透明無邊框視窗裡有咖啡機、磨豆機、奶泡機與各種器具，以圖形動畫加音效模擬做咖啡。
- 套件名稱 `cafe_desk`、主元件 `CafeDesk`、設定檔 `cafe_desk.json`、圖示 `logo/cafe_desk.*`、exe 名稱 `CafeDesk`。
  舊名（espresso_desk）的設定檔與圖示檔仍會被讀取，但新程式碼一律用新名稱。
- 目標：當桌面擺件；評分不必精準；重點放在沖煮畫面的圖形化模擬與聲音。
- 使用者以繁體中文溝通。程式註解與文件使用繁體中文；UI 文字原文寫繁體中文，並經過 `i18n.T()` 支援英文（見下方「介面語言」）。
- 參考實機繪製造型時，不要放真實品牌名稱或 logo。

## 目前狀態
- **正式版**：`__version__ = "1.0.0"`。Beta 最後一版是 `1.0.0b8`（git tag `v1.0.0-beta.8`，對話裡的 v4–v8 都是 Beta）。
- 開發歷程、決策理由、已知問題與待辦清單在 **`handoff.md`**，接手時先讀它；版本變更寫在 `CHANGELOG.md`。
- 改版本號時同步：`cafe_desk/__init__.py`、`CHANGELOG.md`、`main.py` docstring 標題、本檔標題，並打 git tag。
- 自動測試在 `tests/`（pytest），開發工具在 `tools/`（見下方「測試」）。

## 執行與打包
```
pip install PySide6
python main.py                      # Windows 建議用 pythonw
python main.py --make-logo          # 重新產生 logo/cafe_desk.png、.ico
pyinstaller --noconfirm CafeDesk.spec   # 打包設定都在 spec 裡（-D、-w、logo、icon、exe 版本資訊）
python -m pytest                    # 自動測試（無頭）
```
- spec 從 `__version__` 產生 exe 的版本資訊；新增要打包的資源時加到 spec 的 `datas`。
- 設定檔存在程式旁的 `cafe_desk.json`（打包後在 exe 旁）；無法寫入時改存使用者資料夾的 `.cafe_desk.json`。
  讀寫都經過 `config.py`：新設定檔不存在時依序沿用 `paths.OLD_CONFIG_PATHS`（舊版 espresso_desk 的設定檔）。
- 設定檔有 `"schema"` 版本號（目前 1）。**要改名、刪除或改變欄位意義時**：`config.SCHEMA` 加一，在 `_MIGRATIONS`
  加一個 n→n+1 的函式，並在 `tests/test_config.py` 加測試。只是新增欄位（讀取時有預設值）不需要升版。
- 設定檔旁還有：`*_records.db`（紀錄）、`*.log`（錯誤紀錄，`errlog.py`）、`*.lock`（單一執行個體，`single.py`）。
  全部以 `paths.CONFIG_PATH` 推算，測試只要改這個路徑就會一起換到暫存資料夾。
- 音效是第一次執行時用程式合成的 WAV，存在程式旁的 `sound/`；`SFX_VERSION` 改了會重建。
- `main.py` 開頭的 docstring 是給使用者看的完整說明。新增功能時要一起更新，版本號在 `cafe_desk/__init__.py`。

## 檔案結構
```
main.py                     進入點＋使用說明 docstring
CafeDesk.spec               PyInstaller 打包設定
CHANGELOG.md                更新紀錄
tests/                      pytest 自動測試（conftest.py 設好無頭環境與暫存設定檔）
cafe_desk/
  app.py                    QApplication、命令列參數；安裝錯誤紀錄、檢查單一執行個體
  config.py                 設定檔讀寫、schema 版本與遷移、壞檔改名 .bad
  errlog.py                 錯誤紀錄 cafe_desk.log（sys.excepthook、threading、Qt 訊息、faulthandler）
  single.py                 單一執行個體：QLockFile＋QLocalServer，第二次啟動改成叫出第一個（wake 信號）
  host.py                   外層承載視窗。切換視窗化／置頂時整個重建，避免 Windows DWM 殘留邊框
  desk.py                   EspressoDesk 主元件：設定檔、選單、系統匣、滑鼠、模擬推進、自動幀率、繪圖順序、點單生命週期
  model.py                  萃取模型 simulate()、STYLES（Ristretto／Lungo 評分基準）、Shot 時間軸、Barista 自動調參、Boiler
  workflow.py               完整備粉流程：取把手→敲渣→磨豆→布粉→填壓→扣回
  drinks.py                 飲品定義、DrinkParams、牛奶與拉花模型、評分、各階段（Stage）與 Session
  orders.py                 顧客點單：產生訂單、依訂單改參數、符合度、顧客反應
  i18n.py                   介面語言：T()、LANGS、英文對照表 EN
  cups.py                   CUP_KINDS 與 Cup：杯子幾何、容量、玻璃繪製
  machines/                 base.py（Traits、Machine 基底與共用繪圖）、desk01／lever／compact／allinone
  sound.py                  音效合成與播放（QSoundEffect）
  settings.py               參數設定對話框
  layout.py                 版面常數、烘焙度色調 ROAST_LOOK、liquid_look()
  logo.py / paths.py / gfx.py / util.py
  render/                   以 mixin 形式併入 EspressoDesk
    machine.py  grinder.py  liquid.py  milk.py  particles.py  overlay.py
```

## 座標與繪圖
- 視窗大小為 `scene_w × (WIN_H + TOP_PAD)` 再乘上 `scale_f`。`WIN_H=444`；`TOP_PAD=136` 是上方透明區，放萃取曲線卡片、拉花卡片和點單紙。
- 座標有三種：
  - 場景座標：原點在 TOP_PAD 下方。
  - 機身座標：原點在 `machine.mx, machine.my`。
  - 視窗座標：卡片和狀態列用的座標。
- 背景與前景圖層用 pixmap 快取，鍵為 `(dpr, machine.key, cup.kind)`。動態物件畫進每幀重用的 QImage `_frame`，最後再疊上狀態列與卡片。
- 縮放時 pixmap 的 ratio 用 `dpr*scale`，painter 不要再額外 scale，否則會重複縮放。
- 幀率會自動調整：FRAME_ACTIVE 16、AMBIENT 33、IDLE 100、HIDDEN 250 ms。有新動畫時要在 `wanted_interval()` 加入對應條件。
- 模擬固定以子步長 `SIM_STEP=0.05` 推進。`step(dt, sdt)` 的 dt 是真實時間，sdt 是乘上播放速度後的時間。

## 飲品系統（drinks.py）
- `DRINKS[key]` 的欄位：`name`、`cup`（CUP_KINDS 的 key）、`hot`、`base`（流程家族），以及可選的 `shot`（濃縮預設）。
  - base 有 `espresso`、`americano`、`iced`、`milk` 四種。
  - shot 的欄位：`ratio`、`grind`、`dose`、`basket`、`style`。
- 飲品清單：
  - 濃縮類：濃縮、Ristretto、Lungo、雙份
  - 美式、冰美式、濃縮通寧（base iced）
  - 熱牛奶類：熱拿鐵、卡布奇諾、馥列白、可塔朵、瑪奇朵、摩卡、焦糖瑪奇朵
  - 冰拿鐵
  - 阿芙佳朵（base affogato）
- `DRINK_ORDER` 是選單分組，`None` 代表分隔線；`DRINK_KEYS` 是去掉 None 的清單；`AUTO_WEIGHTS` 是自動模式隨機選飲品的權重。
- `shot_params(drink, params)` 依濃縮預設回傳 `(params, style, preset)`。preset 的杯子不拿來給 Barista 調液重。
- `DrinkParams` 的欄位扁平存放（方便 asdict 存設定）。熱牛奶飲品透過 `MILK_SPEC` 和 `milk_plan()` 取得牛奶量、奶泡量、理想奶泡量與容許範圍。
- `evaluate_milk(dp, traits, device, rnd, drink)` 先算出 texture，再決定拉花圖案。
  - 自動模式：依細緻度分級，由差到好是 blob → heart → tulip → rosetta。
  - 指定圖案（`dp.art`）：門檻見 `ART_NEED`。差 0.14 以內時圖案照拉但會糊掉，並寫入 `art_note`；差更多就變成 blob。
  - 卡布奇諾、可塔朵有額外的難度扣減；瑪奇朵固定為 `dot`；燕麥奶的 base 乘 0.9。
- `MILK_KINDS`：dairy／oat／soy／almond，各有 texture（奶泡細緻度倍率）、foam（奶泡穩定度）、color、prefix（點單品名前綴）。
- `SYRUPS`：choc／vanilla，倒進 `contents["syrup"]`，種類記在 `app.syrup_kind`。
- `Session` 依飲品組合各個 Stage：
  1. CoolStage（鍋爐太熱時先降溫）→ PrepStage（完整流程才有）
  2. 前置：美式倒熱水；冰飲先 IceStage，再倒冷水、冰牛奶或通寧水（PourStage vessel "tonic"）；
     阿芙佳朵 ScoopStage；摩卡／焦糖瑪奇朵用 PourStage(vessel "squeeze") 擠巧克力醬／香草糖漿
  3. 一般：BrewStage → 熱牛奶類的 HeatStage → SteamStage → PourStage
     焦糖瑪奇朵相反：先牛奶（不拉花），單鍋爐要再 CoolStage，最後 BrewStage
  4. 配料：ToolStage("cocoa"／"whip"／"caramel")。進度存在 `app.topping[kind]`（0–1，換杯時清空），
     畫面用 `session.tool`（種類、透明度、是否出料）畫篩網、鮮奶油槍、焦糖醬瓶。
- 拉花圖案除了 heart/tulip/rosetta/blob，還有 dot（瑪奇朵）、mark（焦糖瑪奇朵的濃縮印子）、whip（摩卡加鮮奶油）。
  `make_art()` 另外疊加 cocoa、caramel、whip 三種配料；`art_state()` 第五個元素是 `(cocoa, caramel, whip)`。
- 阿芙佳朵的冰淇淋球是 `app.icecream`（g、r、x、y、landed、melt），由 `drop_icecream()` 建立，
  在 `update_drink_fx` 掉落與融化；`surface_y()` 會回傳球頂，讓流柱落在冰淇淋上（液面本身用 `liquid_surface_y()`）。
- Stage 只處理時間軸、位置與事件（`s.events`），不負責繪圖。事件由 `desk.on_session_event` 轉成音效或粒子。
- `score_drink()`：濃縮分數為主，依飲品加上比例分數、牛奶分數與拉花分數。

## 點單模式（orders.py）
- 一張訂單是一杯飲品加上 0–2 個要求 `mods`。要求的種類與值定義在 `MOD_TEXT`；同一類要求只會出現一個。
- `order_params()` 依訂單修改 DrinkParams，並加入咖啡師手感誤差（打奶溫度 σ 2.8、奶泡量 σ 4）。
- 分數＝0.65×飲品分數＋0.35×符合度。`reaction()` 依分數和抱怨內容產生客人的話。
- 狀態依序為 `waiting`、`making`、`done`、`leaving`，由 `desk.update_order()` 推進：
  - 自動模式下，訂單等待 2.5 秒後咖啡師自己接單。
  - 完成後顯示 `SHOW_DONE` 秒，客人才離開。
- 點單紙由 `overlay.paint_order_card` 繪製，寬度為 `ORDER_W=98`。點單紙出現時，`cards_left()` 會讓曲線卡片和拉花卡片往右讓位。

## 咖啡機（machines/）
- `Traits` 會影響模擬：溫度偏移與飄動、鍋爐加熱與降溫、通道效應、甜感、壓力上限、`profile="lever"`、`milk="frother"/"wand"`、`steam_power`、`steam_heatup`（單鍋爐）、`grinder="external"/"integrated"`。
- `Machine` 子類別負責：
  - 提供各種定位點：cup_cx、cup_base、group_pf、wand_*、frother_pos、hit 與 hover 區域、card_cx、scene_w。
  - 實作繪圖 hook：paint_static、paint_front、paint_dynamic、paint_collar、paint_overlay。
- 新增機器時，在 `machines/__init__.py` 的 `MACHINES` 註冊。

## 豆子、季節、清潔、紀錄（v7）
- `beans.py`：`ORIGINS`（產地、烘焙度、風味、甜感加成）。目前這包存在設定檔 `bean_bag`（origin、roasted、left、size）。
  `CafeDesk.sync_bag()` 把 params 的 roast／origin／bean_age 對齊這包豆子（bean_age 依真實日期），
  所以設定視窗的烘焙度與養豆天數是唯讀。`start_brew` 從這包扣粉量，豆不夠時 `start_session` 回傳 False
  （自動模式會先 `open_bag`）。`Params.origin` 進 simulate 的甜感。
- `festivals.py`：只用國曆固定日期的節日（`FESTIVALS` 裡寫開始與結束的月日）；`festival()`／`season()`／`adjust_weights()`；日期用 `today()`，測試可設環境變數
  `CAFE_DESK_DATE=YYYY-MM-DD`。季節限定飲品在 `DRINKS` 有 `festival` 欄位，只有當季出現在選單與隨機權重中。
  加醬的牛奶飲品用 DRINKS 欄位 `syrup`、`syrup_g`、`whip`（True／"opt"）、`dust`（cocoa／cinnamon）。
- `maintenance.py`：計數存在設定檔 `maintenance`；`start_brew` 加 backflush 與 drip，`finish_session` 加 wand，
  敲渣事件加 knock。`Job` 是清潔動作的時間軸（`CafeDesk.job`，會讓 `busy()` 為真）。
  `penalty()` 在 `finish_session` 扣分並在評語提醒；自動模式在閒置時先清該清的。
- `stats.py`：紀錄存在設定檔旁的 SQLite `*_records.db`（cups、events、achievements 三張表）。
  每列有 HMAC 簽章並串成鏈（`prev` 是上一列的簽章）；`load()` 只採用驗證通過的列，從頭重算所有統計，
  驗證失敗的筆數記在 `Stats.tampered`，紀錄視窗會提醒。金鑰在程式裡，只能防隨手改資料庫，不是密碼學保護。
  `Stats.record(cup)` 寫一列並回傳新解鎖成就；`announce()` 加入 `toasts` 通知。成就清單在 `ACHIEVEMENTS`，
  條件在 `Stats.check()`。新增 cups 欄位時要加到 `CUP_FIELDS` 尾端（簽章依欄位順序計算），並處理舊資料庫的
  `ALTER TABLE`。v7 的 `*_stats.json` 第一次啟動時只匯入成就，然後改名 .bak。
- `records.py`：紀錄與收集冊視窗（今天、近兩週圖表、成就、拉花收集、圖鑑）。
- 右鍵選單「Language」刻意不翻譯。

## 介面語言（i18n.py）
- 所有顯示文字都用 `T("繁體中文原文")`；有變數時寫成樣板：`T("{name} 點了{title}", name=…, title=…)`。
  T 的第一個參數名是 `_text`，所以樣板變數可以叫 text。
- 資料裡的名稱（DRINKS、MILK_KINDS、ART_NAMES、MOD_TEXT、CUSTOMERS、機器 name／summary、STATUS、PourStage.LABEL…）
  維持中文，在顯示的地方才 `T()`，所以切換語言會立即生效。
- 新增文字時記得在 `EN` 加上英文；沒有對照就直接顯示中文。
- 切換語言 `CafeDesk.set_language()`：重建右鍵選單、系統匣、設定視窗。英文較長，點單紙與卡片標題用
  `OverlayRenderer.fit_text()` 自動縮字或加刪節號。
- 烘焙度 key（淺焙／中焙／深焙）是內部資料與設定檔的值，只在顯示時翻譯。

## 新增飲品的清單
1. 在 `DRINKS`、`DRINK_ORDER`、`AUTO_WEIGHTS`、`ORDER_WEIGHTS`（orders.py）加上新飲品；需要新杯子時加到 `CUP_KINDS`，並注意容量要裝得下（PourStage 在杯子滿 97% 時停止倒）。
2. 需要新參數時：在 `DrinkParams` 加欄位，熱牛奶類另外加 `MILK_SPEC`，再到 settings.py 的 `DRINK_SLIDERS` 加滑桿並設定適用的飲品。
3. 在 `Session.__init__` 組合流程，在 `score_drink()` 加評分規則。
4. 繪圖：`render/milk.py` 的 `paint_mixed_liquid` 依 `drink_kind()` 分支；`liquid.py` 的 `paint_liquid` 負責切換到混合液體的畫法。
5. 在 `overlay.paint_status` 的資訊列加上這杯的參數，並在 orders.py 的 `mod_pool()` 加上可點的要求。
6. 新的文字加到 i18n.py 的 `EN`。
7. 有持續動畫（氣泡、融化）時，在 `wanted_interval()` 讓幀率維持 AMBIENT。
8. 更新 `main.py` 的 docstring。

## 測試（無頭環境）
- **`python -m pytest`**：自動測試，改完程式一定要跑。`conftest.py` 的 `cfg_path` fixture 把設定檔、資料庫、紀錄檔、
  鎖檔都換到暫存資料夾，`desk` fixture 給一個預熱好的 CafeDesk，`run_until_idle(w)` 推進到流程結束（卡住會失敗）。
  日期固定 2026-08-01（沒有節日）。新增飲品、機器、設定欄位、成就時，記得補對應的測試。
- `tools/stress.py`：所有機器 × 所有飲品、清潔、豆子用完、點單、紀錄視窗（有錯誤會丟例外）
- `tools/run_drinks.py`：做指定飲品並在各階段截圖
- `tools/render_regression.py`：固定狀態渲染，新舊版逐像素比對
- `tools/tamper_test.py`：紀錄資料庫防竄改測試
- `tools/i18n_check.py`：列出缺英文翻譯的文字（全部翻好時沒有輸出、exit 0）
- 產出放在 `tools/out/`（不要提交）
- 環境變數設 `QT_QPA_PLATFORM=offscreen` 和 `CAFE_DESK_NO_AUDIO=1`（舊名 ESPRESSO_DESK_NO_AUDIO 也有效）。把 `paths.CONFIG_PATH` 改到暫存檔。
- 截圖要用 `w.host.grab()`；`w.grab()` 會畫成灰底。
- 快速驗證時，直接迴圈呼叫 `w.step(0.05, 0.5)` 推進到 `not w.busy()`，中間偶爾呼叫 `w.host.grab()` 觸發繪圖。
- 回歸測試：舊版與新版用同一組固定狀態渲染，再用 ImageMagick 的 `compare -metric AE` 比對，應為 0。v7 對 v5 的結果是 0（固定在沒有節日的日期，避免狀態列節日圖示）。
- 無法在無頭環境驗證的項目：實際聲音播放、Windows 系統匣、視窗化模式的邊框（要在 Windows 實機看）。
- 單一執行個體的測試用子行程當第二個實例：同一個 process 裡測不到，因為 Windows 具名管道要對方的事件迴圈在跑。

## 已知陷阱
- 單一執行個體的喚醒：送出端要等伺服器讀完後斷線（`waitForDisconnected`）才離開；先斷線的話 Windows 具名管道裡
  還沒讀的資料會被丟掉。不要用 `QLockFile.removeStaleLockFile()`，它會連活著的鎖一起刪；`tryLock` 本身就會接手失效的鎖。
- `QSoundEffect.setLoopCount` 要傳 int：`int(getattr(inf, "value", inf))`。
- `WA_TranslucentBackground` 必須在視窗第一次顯示前設定，所以切換模式時要重建 HostWindow。
- 每個 tick 只呼叫一次 `sound.loop("pour", vol)`。每幀重設會讓音效一直重頭播放。
- 自動模式的打奶參數是在使用者設定附近變動的單杯副本，不要寫回 `self.dp`，否則數值會隨機漂移。
- 拉花卡片的狀態 `art_state()` 是五元組 `(圖案, 進度, 品質, 種子, (可可粉, 焦糖, 鮮奶油))`。
- `contents` 有 water／milk／foam／syrup 四個 key；`cup_volume()` 另外加上冰塊與融化的冰淇淋。
