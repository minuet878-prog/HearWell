# 聽損模擬加上餐廳背景聲（#488，規格 #484）

日期：2026-11-13。分支：`feat/485-simulator-mockup`。規格：[#484](https://github.com/minuet878-prog/HearWell/issues/484)；票：[#488](https://github.com/minuet878-prog/HearWell/issues/488)；音檔來源：[simulator-audio.md](../planning/redesign/simulator-audio.md)；前一張：[issue-487.md](issue-487.md)。

狀態：自動測試、自審都已完成；**等本人用耳朵聽餐廳背景下的四種程度**。不需要交叉審查：沒有碰計分、分級、門檻、會動資料的 migration、權限。

## 本人決定

1. 2026-11-13 同意多一個測試切入點：用假的瀏覽器聲音元件測真正的聲音引擎，證明背景聲與說話聲先混在一起才經過濾波。

## 做法

- 「安靜｜餐廳」在「模擬｜正常聽」下面，附房子與刀叉圖示（#485 設計圖）；讀螢幕軟體念「在哪裡」群組與目前狀態。
- 說話聲與背景聲在同一個混音點會合，再一起經過照聽力圖的濾波器：聽損把兩個一起變悶。
- 背景聲照定稿的訊噪比 +5 dB：說話聲與背景聲的響度都只算有聲音的部分（頭尾靜音不算）。背景聲循環播放，一句播完跟著停；開始與停止都淡入淡出。
- 第一次在餐廳播放時，等背景聲也下載好，兩個一起開始；播放中才選餐廳，背景聲下載好就加進來。背景聲下載失敗時句子照播，只是沒有背景。
- 兩個聲音會合處整體小 2 dB：第 2 句本身到滿格，加上背景會破音 1.2%。模擬與正常聽一起變小，比例不變。
- 沒選餐廳前不下載背景聲。

## 自動測試

提交 `19e75bf`，2026-11-13：

| 項目 | 結果 |
|---|---|
| Django 測試 | 2019 項通過 |
| 端對端測試 | 407 項通過 |
| 前端測試 | 471 項通過（含首屏 JS ≤ 80 KB、CSS 不超過上限） |
| 前端建置、`ruff check`、`ruff format --check` | 通過 |

## 自審

`/mattpocock-skills:code-review`，基準 `6d2de55`。

- Standards：沒有硬性違規；判斷題五項（測試輔助函式命名與重複、`background` 名字容易跟聲音混、背景響度重算、下載失敗沒有註解）。**都已修**。
- Spec：引擎的停止與下載時機逐行看過，沒有漏停或重複播。發現三項並**都已修**：第一次在餐廳播放時背景比句子晚進來；響度連靜音一起算，實際訊噪比 5.6–6.1 dB（用本人審定的音檔實測），第 2 句加背景破音 1.2%；背景開始與停止沒有淡入淡出。另補測試：鍵盤切餐廳、背景播放中換程度不停、圖示。

## 驗收條件

測試名稱：**元件**在 `frontend/src/SimulatorApp.test.jsx`，**引擎**在 `frontend/src/simulator-engine.test.js`，**計算**在 `frontend/src/simulator.test.js`，**頁面**在 `screening/tests/test_simulator.py`，**瀏覽器**在 `e2e/main_flow.py` 的 `HearingLossSimulatorTest`。

- [x] #484-10 選餐廳播放，說話聲與背景聲一起播；模擬時背景也經過同一個濾波。引擎 `mixes the restaurant into the speech before the filter, never round it`、`starts the restaurant with the sentence the first time, not after it`
- [x] #484-11 一句播完背景也停。引擎 `stops the restaurant when the sentence ends`；元件 `keeps 餐廳 picked when a sentence ends, for the next one`
- [x] 播放中切安靜／餐廳、正常聽／模擬、程度，都不中斷。元件 `switches to 餐廳 and back while playing without starting again`；引擎 `keeps the restaurant going when the degree or 正常聽 changes`、`takes the restaurant away without stopping the sentence`
- [x] 沒選餐廳前不下載背景聲。元件 `opens on 安靜 without asking for the restaurant`；引擎 `downloads the restaurant only once picked, and starts it under what already plays`；瀏覽器 `test_from_learn_pick_a_degree_play_and_show_the_sentence`
- [x] 訊噪比 +5 dB（定稿）。頁面 `test_one_heading_and_the_player_gets_degrees_and_sentences`；計算 `sets the restaurant so the speech is the given dB above it`、`leaves the silence before and after a sentence out of its loudness`；引擎 `plays the restaurant 5 dB under the speech, over and over`
- [x] 不破音、不喀一聲。引擎 `turns the two down 2 dB where they meet, so the loudest sentence does not clip`、`fades the restaurant in and out instead of clicking`
- [x] 狀態與 aria、圖示、鍵盤、按下變色、按鈕大小。元件 `opens on 安靜 without asking for the restaurant`；瀏覽器 `test_keyboard_alone_picks_a_degree_and_switches_to_normal_hearing`、`test_controls_change_colour_when_pressed`、`test_every_control_is_big_enough_and_every_word_at_least_body_size`
- [x] e2e 切到餐廳再播放。瀏覽器 `test_from_learn_pick_a_degree_play_and_show_the_sentence`

## 等本人確認

- [ ] 餐廳背景下的四種程度聽起來合理，句子在正常聽時還聽得清楚
- [ ] 背景聲開始、停止、播放中切換都沒有喀聲或中斷
- [ ] 一句播完背景跟著停
