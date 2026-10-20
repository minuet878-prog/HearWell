#!/usr/bin/env python3
"""規則 1：不直接改 main。在 main 上執行 git commit 前，跳出確認讓本人決定。

不直接擋下，因為本人可以在個別 session 允許直接改 main。
"""

import json
import re
import subprocess
import sys

data = json.load(sys.stdin)
command = data.get("tool_input", {}).get("command", "")
if not re.search(r"\bgit\b.*\bcommit\b", command):
    sys.exit(0)

branch = subprocess.run(
    ["git", "-C", data.get("cwd", "."), "symbolic-ref", "--short", "HEAD"],
    capture_output=True,
    text=True,
).stdout.strip()
if branch != "main":
    sys.exit(0)

reason = "目前在 main 分支上 commit。規則 1 要在分支上工作，確定要直接 commit 到 main 嗎？"
output = {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": reason,
    }
}
print(json.dumps(output, ensure_ascii=False))
