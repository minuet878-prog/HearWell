"""scripts/ship_docs.py: which files a branch changes, read from a throwaway git repository."""

import importlib.util
import os
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

SCRIPT = Path(settings.BASE_DIR) / "scripts" / "ship_docs.py"
spec = importlib.util.spec_from_file_location("ship_docs", SCRIPT)
ship_docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ship_docs)


def run_git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


class ChangedPathsTest(SimpleTestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        run_git(self.repo, "init", "-q", "-b", "work")
        Path(self.repo, "README.md").write_text("start\n")
        run_git(self.repo, "add", ".")
        run_git(self.repo, "commit", "-q", "-m", "start")
        # The script compares against origin/main; point it at the starting commit.
        run_git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        previous = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, previous)

    def commit(self, *paths):
        for path in paths:
            Path(self.repo, path).parent.mkdir(parents=True, exist_ok=True)
            Path(self.repo, path).write_bytes(b"x")
        run_git(self.repo, "add", ".")
        run_git(self.repo, "commit", "-q", "-m", "change")

    def test_a_chinese_file_name_under_docs_counts_as_docs(self):
        # PR #729: git quoted a Chinese name as "docs/design/\345...", which read as outside docs/.
        self.commit("docs/design/定稿首頁.png", "docs/notes.md")

        changed = ship_docs.changed_paths()

        self.assertEqual(sorted(changed), ["docs/design/定稿首頁.png", "docs/notes.md"])
        self.assertTrue(all(ship_docs.is_docs(path) for path in changed))

    def test_a_file_outside_docs_is_still_caught(self):
        self.commit("docs/notes.md", "README.md")

        outside = [path for path in ship_docs.changed_paths() if not ship_docs.is_docs(path)]

        self.assertEqual(outside, ["README.md"])
