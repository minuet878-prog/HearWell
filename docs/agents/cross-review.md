# 交叉審查怎麼叫

[回代理工作設定](README.md)

做到第 4b 步、要在背景叫審查代理時讀這份。誰審、何時必做、結果怎麼處理，以根目錄 `AGENTS.md` 為準。

## 準備

1. 分支上的改動都已 commit：審查看的是 `main...HEAD`。
2. 規格 issue 先存成檔，交給審查代理讀：`gh issue view <編號> > <暫存資料夾>/spec-<編號>.md`。審查代理的沙箱可能連不上網路，叫不了 `gh`。
3. `<資料夾>` 是分支所在的資料夾；在 worktree 工作就填 worktree 的路徑。

## 指令

兩個審查代理放背景同時跑，各寫一個結果檔。

| 代理 | 指令 |
|---|---|
| Codex | `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex exec -s read-only -C <資料夾> -o <暫存資料夾>/review-codex.md "<交辦>"` |
| Gemini | `cd <資料夾> && agy --mode plan --print-timeout 1800s -p="<交辦>" > <暫存資料夾>/review-gemini.md` |
| Claude Code | `cd <資料夾> && claude -p --permission-mode plan "<交辦>" > <暫存資料夾>/review-claude.md`（還沒試過） |

- Codex 不在 PATH 上，用 ChatGPT.app 裡附的那支。`-s read-only` 是唯讀沙箱。
- agy 的提示要寫成 `-p="..."`，`--mode` 放在它前面，否則會報錯結束。`--mode plan` 只規劃、不改檔。

## 交辦範本

第一次審查：

```
Cross-review, read-only: leave every file, commit, and remote untouched.
Run the Matt Pocock code-review skill with base `main`.
Spec: <暫存資料夾>/spec-<編號>.md. Standards: CODING_STANDARDS.md.
Read only the diff, the spec, and the standards; skip docs/verification/ and any self-review notes.
Spec axis: for every acceptance criterion, cite the test assertion that proves it as file:line.
A missing assertion, or one that does not really prove the criterion, is a finding.
Write the report in Traditional Chinese. Label each finding 要修 or 建議, with file:line and the reason.
```

複核：

```
Re-check, read-only: leave every file, commit, and remote untouched.
Base `main`. Re-check only these items, which the implementer says are fixed:
<逐項貼上>
For each item answer 已修好 or 仍要修, with file:line. Write in Traditional Chinese.
```

## 已知狀況

- 2026-11-24 試跑：Codex 和 agy 都在背景模式讀得到 `AGENTS.md` 和 code-review 技能，跑完沒有改到檔案。
- 完整審查還沒跑過：第一次正式用時確認 code-review 技能裡的平行子代理能不能在背景模式跑。
