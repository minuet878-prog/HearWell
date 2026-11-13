# 聽損模擬可以播放典型程度（#487，規格 #484）

日期：2026-11-13。分支：`feat/485-simulator-mockup`（#485 設計圖、#486 音檔、#487 同一條分支）。規格：[#484](https://github.com/minuet878-prog/HearWell/issues/484)；票：[#487](https://github.com/minuet878-prog/HearWell/issues/487)；設計圖選定與內容定稿：[第 3 階段拷問決定](../planning/redesign/phase-3-grill-decisions.md#設計圖選定)；ADR [0052](../adr/0052-hearing-loss-simulator-tts-and-dsp.md)、[0053](../adr/0053-simulator-dark-player-exception.md)。

狀態：自動測試、自審都已完成；2026-11-13 本人在電腦上實際操作、聽過四種程度後回覆「沒問題」。iPhone 靜音開關一項等部署後在手機上確認。不需要交叉審查：沒有碰計分、分級、門檻、會動資料的 migration、權限（頁面不用登入、不讀任何紀錄）。

## 本人決定

1. 2026-11-13 自審發現濾波器串會疊加，實際調小的量約是聽力圖的兩倍（中度 1000 Hz 要小 50 dB 卻小了約 105 dB）。本人選 **B**：改成一個照聽力圖連線算出的卷積濾波器，不用規格寫的濾波器串。已記進 ADR 0052。
2. 驗收 4「看得到四種程度與各自一句說明」**以設計圖為準**：膠囊只寫名稱，選中的那一種在聲音條上方寫說明（#485 選的 E1＋V1）。

## 實作時的做法（請本人知道）

- **安靜｜餐廳**：這張先**不出現**，#488 再加（票上要實作者說明選哪一種）。
- **回去的路**：照網站子頁的寫法放在頁尾「回到了解」，不放設計圖頁首的「‹ 了解」。
- **入口圖示**：用新的喇叭圖示，不用設計圖的耳朵。家人專區的「助聽器」那列已經是耳朵，兩列同圖會分不清。
- **暫停**：按「暫停」是停下，再按「播放」從這句的頭開始（一句只有 2.5–3 秒）。
- **審定日期**：寫在 `screening/simulator.py` 開頭的說明，頁面不顯示（內容是本人審定的，不是引用外部資料，沒有出處要標）。

## 自動測試

提交 `01e9d90`，2026-11-13：

| 項目 | 結果 |
|---|---|
| Django 測試 | 2019 項通過 |
| 端對端測試 | 407 項通過 |
| 前端測試 | 455 項通過（含首屏 JS ≤ 80 KB、CSS 不超過上限） |
| 前端建置、`ruff check`、`ruff format --check` | 通過 |

## 自審

`/mattpocock-skills:code-review`，基準 `6ea6112`。

- Standards：按下沒有變色（ADR 0028）、沒人用的 `SIMULATOR_CHECKED_ON`、方塊數 6 和 8 各寫兩次。**都已修**。
- Spec：濾波器疊加（見本人決定 1，已修）；驗收 4 與設計圖不同（本人決定 2）；測試缺：e2e 看到暫停、再按收起、前一句停止、44×44 與 18px、鍵盤、用有紀錄的帳號驗不帶資料。**都已補**。

## 驗收條件

測試名稱：**頁面**在 `screening/tests/test_simulator.py`，**計算**在 `frontend/src/simulator.test.js`，**元件**在 `frontend/src/SimulatorApp.test.jsx`，**瀏覽器**在 `e2e/main_flow.py` 的 `HearingLossSimulatorTest`。背景聲（驗收 10、11）屬於 #488，素材（23）屬於 #486。

### 入口

- [x] 1 沒登入，「了解」有聽損模擬一列，點進去打得開。頁面 `test_learn_lists_it_after_the_family_zone`、`test_anyone_opens_it_and_it_marks_the_learn_tab`；瀏覽器 `test_from_learn_pick_a_degree_play_and_show_the_sentence`
- [x] 2 家人專區首頁第一列是聽損模擬。頁面 `test_family_zone_opens_with_it`
- [x] 3 登入（帳號有一筆分級紀錄）跟沒登入的頁面相同，沒有那筆紀錄的分級、分數、帳號名稱。頁面 `test_anyone_opens_it_and_it_marks_the_learn_tab`

### 選程度與播放

- [x] 4 打開不出聲，預設高頻下降與模擬（說明照設計圖，本人決定 2）。元件 `opens silent on 高頻下降 and 模擬, its bars and its curve`
- [x] 5 選中度按播放，播那一句、按鈕變暫停。元件 `plays the sentence and offers to pause it`；瀏覽器看到「暫停」
- [x] 6 播放中換一句，前一句先停、改播新的。元件 `plays the next sentence instead when moving on while playing, and wraps round`
- [x] 7 播放中換程度，不中斷、不重播，換成新程度的濾波。元件 `changes degree while playing without stopping or starting again`

### 正常聽與模擬

- [x] 8 播放中切正常聽再切回，不中斷，聲音條全滿再縮回。元件 `switches to 正常聽 and back while playing, the bars full, without starting again`；計算 `leaves normal hearing as it is, delayed as much as a degree`（正常聽與各程度延遲相同，切換不跳拍）
- [x] 9 正常聽時選程度，自動切回模擬。元件 `goes back to 模擬 when a degree is picked during 正常聽`

### 顯示這句話

- [x] 12 按了才顯示，再按收起；換句自動收起。元件 `shows the sentence only when asked, and folds it again for the next one`
- [x] 13 讀螢幕軟體念得出展開／收合與狀態（`aria-expanded`）。同上

### 說明與下一步

- [x] 14 限制說明一直在；高頻下降另加一句。元件 `tells the limits always and the 高頻下降 note only on 高頻下降`；頁面 `test_one_heading_and_the_player_gets_degrees_and_sentences`
- [x] 15 聽不到聲音的提示。同上
- [x] 16 下一步連到「怎麼跟他說話」與選配指引，再來是回到了解。頁面 `test_next_steps_lead_to_talking_and_the_guide_then_back_to_learn`

### 程度與句子的內容

- [x] 17 輕度、中度、中重度的四頻平均落在各自程度；高頻下降低頻正常、4000 Hz 以上 ≥60（四頻平均 38.75，網站判斷輕度）。頁面 `test_averages_fall_in_their_degrees`
- [x] 18 程度、說明、四句話是本人在 #485 審定的版本。頁面 `test_one_heading_and_the_player_gets_degrees_and_sentences`
- [x] 濾波照聽力圖：各頻率與頻率之間都在 1 dB 以內（44.1、48 kHz）。計算 `turns each frequency down by the degree's dB HL`、`follows the audiogram's line between its frequencies`

### 無障礙與效能

- [x] 19 320px、200% 字級不左右捲，播放鈕自己一排還是圓的；390px 時每個按鈕至少 44×44、字至少 18px。瀏覽器 `test_fits_a_phone_at_double_text_size`、`test_every_control_is_big_enough_and_every_word_at_least_body_size`。對比在設計圖第 ⑦ 組實測，全部 ≥4.5:1
- [x] 20 只用鍵盤（Tab、Enter、空白鍵）選程度、切正常聽，狀態念得出來。瀏覽器 `test_keyboard_alone_picks_a_degree_and_switches_to_normal_hearing`
- [x] 按下變色（ADR 0028）。瀏覽器 `test_controls_change_colour_when_pressed`
- [x] 21 按播放前不下載音檔，按了才下載那一句；首屏 JS 在上限內。瀏覽器 `test_from_learn_pick_a_degree_play_and_show_the_sentence`；前端 `bundle.test.js`
- [x] 22 沒開 JavaScript 看得到四句話、說明與「需要開啟 JavaScript 才能播放。」。頁面 `test_without_javascript_the_words_are_there_and_it_says_why_nothing_plays`（Playwright 關掉 JavaScript 時不顯示 `<noscript>`，照聽力圖輸入頁的前例只在頁面測試驗）

## 等本人確認

測試瀏覽器（Playwright 的 Chromium）解不開 AAC，**聲音只能本人聽**：

- [x] 四種程度聽起來合理（高頻下降：聽得到、聽不清楚；中重度：幾乎聽不到）
- [x] 播放中切正常聽／模擬、換程度，聲音不中斷、沒有爆音
- [ ] 手機（iPhone）開著靜音開關時也聽得到，或提示看得懂（部署後在手機上確認）
- [x] 畫面跟設計圖選定的 E1＋V1 一致
