#!/usr/bin/env python3
"""Ship a docs-only branch to main in one approval: push, open a PR, wait for CI, merge.

Refuses when the branch changes anything outside docs/ or GLOSSARY.md (AGENTS.md rule 1).

Usage: python3 scripts/ship_docs.py "<PR title>" <PR body file>
"""

import subprocess
import sys
import time


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def is_docs(path):
    return path.startswith("docs/") or path == "GLOSSARY.md"


def main():
    if len(sys.argv) != 3:
        sys.exit('用法：python3 scripts/ship_docs.py "<PR 標題>" <PR 內文檔>')
    title, body_file = sys.argv[1], sys.argv[2]

    branch = git("symbolic-ref", "--short", "HEAD")
    if branch == "main":
        sys.exit("目前在 main，先開分支再 commit。")
    if git("status", "--porcelain", "--untracked-files=no"):
        sys.exit("有還沒 commit 的改動，先 commit。")

    git("fetch", "origin", "main")
    changed = git("diff", "--name-only", "origin/main...HEAD").splitlines()
    if not changed:
        sys.exit("這個分支跟 origin/main 沒有差異。")
    outside = [path for path in changed if not is_docs(path)]
    if outside:
        sys.exit("有 docs/、GLOSSARY.md 以外的檔案，要走一般 PR 流程：\n" + "\n".join(outside))

    subprocess.run(["git", "push", "-u", "origin", f"HEAD:refs/heads/{branch}"], check=True)

    pr = subprocess.run(
        ["gh", "pr", "view", branch, "--json", "state", "--jq", ".state"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    if pr != "OPEN":
        subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--base",
                "main",
                "--head",
                branch,
                "--title",
                title,
                "--body-file",
                body_file,
            ],
            check=True,
        )

    # Checks take a few seconds to register; `gh pr checks` errors until they do.
    for _ in range(30):
        listed = subprocess.run(
            ["gh", "pr", "checks", branch, "--json", "name"], capture_output=True, text=True
        )
        if listed.stdout.strip() not in ("", "[]"):
            break
        time.sleep(5)
    else:
        sys.exit("等了 150 秒還沒有 CI 出現，沒有合併。")

    if subprocess.run(["gh", "pr", "checks", branch, "--watch", "--fail-fast"]).returncode != 0:
        sys.exit("CI 沒過，沒有合併。")

    subprocess.run(["gh", "pr", "merge", branch, "--merge"], check=True)
    print(f"已合併 {branch}。記得看 main 合併 commit 的 CI。")


if __name__ == "__main__":
    main()
