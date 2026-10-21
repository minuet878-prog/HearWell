#!/bin/bash
# AI 每次編輯完 .py 檔後自動跑 Ruff（check --fix，再 format）；Claude Code 與 Codex 共用這支腳本。
# 有修不掉的問題時回傳 exit 2，Ruff 的訊息會回饋給代理，讓它當場修。
# worktree 裡沒有 py313/，改用主資料夾的 Ruff；兩邊都找不到時提醒，不靜默跳過。
input=$(cat)

# Codex 不設 CLAUDE_PROJECT_DIR，改用 hook 輸入裡的 cwd。
dir=${CLAUDE_PROJECT_DIR:-$(printf '%s' "$input" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("cwd", ""))')}
cd "$dir" || exit 0

# Claude Code 的 Edit／Write 給 file_path；Codex 的 apply_patch 把檔名寫在 patch 標頭裡。
files=$(printf '%s' "$input" | python3 -c '
import json, re, sys
tool_input = json.load(sys.stdin).get("tool_input", {})
if tool_input.get("file_path"):
    print(tool_input["file_path"])
else:
    for path in re.findall(r"^\*\*\* (?:Add File|Update File|Move to): (.+)$", tool_input.get("command", ""), re.M):
        print(path)
')
py_files=$(printf '%s\n' "$files" | grep '\.py$' | while read -r f; do
  [ -f "$f" ] && echo "$f"
done)
[ -n "$py_files" ] || exit 0

ruff=py313/bin/ruff
if [ ! -x "$ruff" ]; then
  main_dir=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)")
  ruff="$main_dir/py313/bin/ruff"
fi
if [ ! -x "$ruff" ]; then
  echo "找不到 py313/bin/ruff，這次沒有跑 Ruff 檢查。" >&2
  exit 1
fi

out=$(printf '%s\n' "$py_files" | tr '\n' '\0' | xargs -0 "$ruff" check --fix --quiet 2>&1)
status=$?
printf '%s\n' "$py_files" | tr '\n' '\0' | xargs -0 "$ruff" format --quiet
[ "$status" -eq 0 ] && exit 0
echo "Ruff 發現無法自動修正的問題，請修正：" >&2
echo "$out" >&2
exit 2
