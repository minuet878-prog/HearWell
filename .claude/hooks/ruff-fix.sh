#!/bin/bash
# AI 每次編輯完 .py 檔後自動跑 Ruff（check --fix）。
# 有修不掉的問題時回傳 exit 2，Ruff 的訊息會回饋給 Claude，讓它當場修。
cd "$CLAUDE_PROJECT_DIR" || exit 0
[ -x py313/bin/ruff ] || exit 0

file=$(py313/bin/python -c 'import json, sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))')
case "$file" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0

if out=$(py313/bin/ruff check --fix --quiet "$file" 2>&1); then
  exit 0
fi
echo "Ruff 發現無法自動修正的問題，請修正：" >&2
echo "$out" >&2
exit 2
