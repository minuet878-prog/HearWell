# 聽損模擬的音檔（#486）

[回第 3 階段拷問決定](phase-3-grill-decisions.md)

說話聲用 Google Cloud Text-to-Speech 產生（ADR 0052），餐廳背景聲用 CC0 錄音。產生說話聲要用本人的 Google Cloud 帳號，所以由本人執行；代理準備指令稿、轉檔、放進 repo、寫來源紀錄。

## 說話聲的設定

| 項目 | 設定 | 原因 |
|---|---|---|
| 服務 | Google Cloud Text-to-Speech | 官方文件寫明產生的音檔可用在自己的應用程式或媒體（[配額與限制頁](https://cloud.google.com/text-to-speech/quotas)） |
| 語言 | 中文（台灣）`cmn-TW` | |
| 等級 | WaveNet | 台灣口音只有 Standard 與 WaveNet；音質較好的 Chirp 3 HD 目前不支援 `cmn-TW`（2026-11-13 查 [聲音清單](https://docs.cloud.google.com/text-to-speech/docs/list-voices-and-types)、[Chirp 3 HD](https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd)） |
| 女聲 | `cmn-TW-Wavenet-A` | 台灣口音 WaveNet 只有這一個女聲 |
| 男聲 | `cmn-TW-Wavenet-B` 或 `cmn-TW-Wavenet-C` | 兩個都產生，本人用耳朵挑一個 |
| 語速 | 1.0（不調） | 模擬的是家人平常說話的速度 |
| 取樣率 | 24 kHz、單聲道、無損 WAV | 要保留模擬器濾波用到的 8000 Hz；WaveNet 本來就是 24 kHz |
| 放上網站的格式 | AAC（.m4a）64 kbps | 實測 24 kHz 下 8000 Hz 完整保留；每秒約 6 KB，一句約 18 KB；iPhone 原生支援 |

四句話與聲音（[#485 定稿](phase-3-grill-decisions.md#聽損模擬內容定稿485)）：

| 句 | 聲音 | 句子 |
|---|---|---|
| 1 | 女 | 星期四下午三點去看醫生。 |
| 2 | 男 | 這個藥飯後吃，一天三次。 |
| 3 | 女 | 孫子說下禮拜六要回來吃飯。 |
| 4 | 男 | 謝謝你送的水果，很新鮮。 |

## 本人要做的：說話聲

1. 到 [Google Cloud 主控台](https://console.cloud.google.com/)，用既有專案或新開一個專案。
2. 啟用「Cloud Text-to-Speech API」。Google 規定要綁帳單帳戶；這四句一共約 50 個字，遠低於每月免費額度，實際費用是 0 元。
3. 到「API 和服務 → 憑證」建立 API 金鑰，在「API 限制」只勾 Cloud Text-to-Speech API。金鑰不要貼到對話裡。
4. 在 Terminal 的 repo 主資料夾執行（第一行會停下來等您貼上金鑰，貼了不會顯示）：

   ```bash
   read -s GOOGLE_TTS_API_KEY && export GOOGLE_TTS_API_KEY
   ```

   ```bash
   py313/bin/python -I .claude/worktrees/485-simulator-mockup/scripts/make_simulator_speech.py ~/Desktop/simulator-speech
   ```

   會在桌面的 `simulator-speech` 資料夾產生 6 個檔：第 1、3 句女聲各一個，第 2、4 句男聲 B、C 各一個。
5. 聽一遍，告訴我男聲選 B 還是 C，四句聽起來有沒有怪的地方（斷句、破音、讀錯字）。讀錯的話我改指令稿重產。
6. 用完可以把金鑰刪掉或停用。
7. 看一次當時的 [Google Cloud 服務條款](https://cloud.google.com/terms/service-terms)，確認音檔可以放在網站上（#486 驗收）。

## 本人要做的：餐廳背景聲

三個都是 [Freesound](https://freesound.org/) 上 CC0（公眾領域，可商用、不用標示作者）的錄音，頁面上可以直接試聽。請挑一個，登入 Freesound（免費帳號）下載 WAV，放進一個新的空資料夾（例如桌面的 `simulator-background`）。

| | 錄音 | 長度 | 檔案 | 內容 | 代價 |
|---|---|---|---|---|---|
| **建議** | [Taiwan restaurant.wav](https://freesound.org/people/Martin.Sadoux/sounds/415516/)（Martin.Sadoux） | 3:00 | WAV 48 kHz／24-bit 立體聲，49.6 MB | 2012 年台北大安區室內餐廳，人聲 | 背景是中文，有可能聽得出幾個字、跟要模擬的那句搶注意力；我會挑沒有單一人聲特別清楚的一段 |
| | [Overcrowded busy restaurant.wav](https://freesound.org/people/dersinnsspace/sounds/424974/)（dersinnsspace） | 3:35 | WAV 44.1 kHz 立體聲，72.3 MB | 捷克布爾諾很擠的餐廳：聊天、碗盤、服務生 | 背景是外語，不會搶字；但不像台灣的餐廳 |
| | [Diner in Virginia](https://freesound.org/people/Laggardson/sounds/627079/)（Laggardson） | 2:21 | WAV 48 kHz 立體聲，51.7 MB | 美國早餐店，iPhone 錄的 | 外語；手機錄音，音質比前兩個差 |

## 代理接著做的

- 說話聲：把選定的 4 個 WAV 轉成 AAC 64 kbps（macOS 內建的 `afconvert`），放進網站的靜態檔。
- 背景聲：從下載的 WAV 截一段約 10 秒、沒有單一人聲特別清楚的，轉成單聲道 24 kHz、AAC 64 kbps，頭尾淡入淡出。
- 放進 repo 前請本人再聽一次轉好的檔。
- 填好下面的來源紀錄。

## 來源紀錄

2026-11-13 放進 `screening/static/screening/simulator/`。本人選男聲 B、台北餐廳，聽過轉好的 5 個檔後同意放進 repo。Google Cloud 條款由本人請代理代讀（2026-11-13，[服務條款](https://cloud.google.com/terms/service-terms) 2026-04-02 版沒有針對 Text-to-Speech 的限制；[配額與限制頁](https://docs.cloud.google.com/text-to-speech/quotas)寫明產生的音檔可用在自己的應用程式或媒體）。

| 檔案 | 來源 | 設定 | 日期 | 授權 |
|---|---|---|---|---|
| `sentence-1.m4a`、`sentence-3.m4a` | Google Cloud Text-to-Speech，`cmn-TW-Wavenet-A`（女） | 由 `scripts/make_simulator_speech.py` 產生 LINEAR16 24 kHz 單聲道、語速 1.0；`afconvert` 轉 AAC 64 kbps | 2026-11-13 產生 | 依 Google Cloud 服務條款，產生的音檔可用在自己的應用程式 |
| `sentence-2.m4a`、`sentence-4.m4a` | Google Cloud Text-to-Speech，`cmn-TW-Wavenet-B`（男） | 同上 | 2026-11-13 產生 | 同上 |
| `restaurant.m4a` | Freesound「[Taiwan restaurant.wav](https://freesound.org/people/Martin.Sadoux/sounds/415516/)」，Martin.Sadoux，2012 年台北大安區 | 原檔 48 kHz／24-bit 立體聲 3:00；取第 152–162 秒（全檔音量最平穩、沒有突出人聲的 10 秒），轉單聲道 24 kHz、頭尾各 0.3 秒淡入淡出，`afconvert` 轉 AAC 64 kbps | 2026-11-13 下載 | CC0 1.0（公眾領域） |
