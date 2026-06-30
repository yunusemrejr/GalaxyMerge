"""Unit tests for git subsystem — Checkpoints, generate_diff, GitRepo."""

import pytest
from pathlib import Path

from galaxy_merge.git.checkpoints import Checkpoints
from galaxy_merge.git.diffs import generate_diff

pytestmark = [pytest.mark.unit]


class TestCheckpoints:
    def test_save_creates_record(self, tmp_path):
        cp = Checkpoints(tmp_path / ".gm")
        record = cp.save("cp_001", "sess_1", ["main.py"], "before refactor")
        assert record["checkpoint_id"] == "cp_001"
        assert record["session_id"] == "sess_1"
        assert record["files_changed"] == ["main.py"]
        assert record["reason"] == "before refactor"
        assert record["verified"] is False

    def test_save_persists_to_jsonl(self, tmp_path):
        gm = tmp_path / ".gm"
        cp = Checkpoints(gm)
        cp.save("cp_001", "s1", ["a.py"], "r1")
        cp.save("cp_002", "s2", ["b.py"], "r2")
        jsonl_path = gm / "git" / "checkpoints.jsonl"
        assert jsonl_path.exists()
        lines = [line for line in jsonl_path.read_text().splitlines() if line.strip()]
        assert len(lines) == 2

    def test_list_all_returns_all_records(self, tmp_path):
        cp = Checkpoints(tmp_path / ".gm")
        cp.save("cp_001", "s1", ["a.py"], "r1")
        cp.save("cp_002", "s2", ["b.py"], "r2")
        cp.save("cp_003", "s3", ["c.py"], "r3")
        records = cp.list_all()
        assert len(records) == 3
        assert records[0]["checkpoint_id"] == "cp_001"
        assert records[2]["checkpoint_id"] == "cp_003"

    def test_list_all_empty_when_no_checkpoints(self, tmp_path):
        cp = Checkpoints(tmp_path / ".gm")
        assert cp.list_all() == []

    def test_save_creates_patchsets_dir(self, tmp_path):
        gm = tmp_path / ".gm"
        _cp = Checkpoints(gm)
        assert (gm / "git" / "patchsets").exists()

    def test_save_handles_empty_files_list(self, tmp_path):
        cp = Checkpoints(tmp_path / ".gm")
        record = cp.save("cp_001", "s1", [], "no files changed")
        assert record["files_changed"] == []

    def test_save_handles_special_characters_in_reason(self, tmp_path):
        cp = Checkpoints(tmp_path / ".gm")
        _record = cp.save("cp_001", "s1", ["a.py"], 'fixed "quotes" & <tags>')
        records = cp.list_all()
        assert records[0]["reason"] == 'fixed "quotes" & <tags>'


class TestGenerateDiff:
    def test_generates_unified_diff(self):
        diff = generate_diff(Path("/tmp"), "test.py", "old\n", "new\n")
        assert "-" in diff or "+" in diff

    def test_identical_content_produces_empty_diff(self):
        diff = generate_diff(Path("/tmp"), "test.py", "same\n", "same\n")
        assert diff == "" or diff.strip() == ""

    def test_multiline_diff(self):
        old = "line1\nline2\nline3\n"
        new = "line1\nmodified\nline3\n"
        diff = generate_diff(Path("/tmp"), "test.py", old, new)
        assert "modified" in diff

    def test_empty_old_content(self):
        diff = generate_diff(Path("/tmp"), "test.py", "", "new content\n")
        assert "+" in diff

    def test_empty_new_content(self):
        diff = generate_diff(Path("/tmp"), "test.py", "old content\n", "")
        assert "-" in diff

    def test_handles_unicode_content(self):
        diff = generate_diff(Path("/tmp"), "test.py", "héllo\n", "wörld\n")
        # Should not crash
        assert isinstance(diff, str)


class TestGitRepo:
    def test_is_repo_true_on_git_dir(self, tmp_path):
        from galaxy_merge.git.repo import GitRepo

        (tmp_path / ".git").mkdir()
        repo = GitRepo(tmp_path)
        assert repo.is_repo is True

    def test_is_repo_false_without_git_dir(self, tmp_path):
        from galaxy_merge.git.repo import GitRepo

        repo = GitRepo(tmp_path)
        assert repo.is_repo is False

    def test_status_returns_dict(self, tmp_path):
        from galaxy_merge.git.repo import GitRepo

        import subprocess

        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        repo = GitRepo(tmp_path)
        result = repo.status()
        assert "stdout" in result
        assert "exit_code" in result

    def test_current_branch_returns_string(self, tmp_path):
        from galaxy_merge.git.repo import GitRepo

        import subprocess

        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        repo = GitRepo(tmp_path)
        branch = repo.current_branch()
        assert isinstance(branch, str)

    def test_is_clean_on_fresh_repo(self, tmp_path):
        from galaxy_merge.git.repo import GitRepo

        import subprocess

        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        repo = GitRepo(tmp_path)
        # Fresh repo with no commits may not be "clean" in the git sense
        result = repo.is_clean()
        assert isinstance(result, bool)

    def test_log_returns_list(self, tmp_path):
        from galaxy_merge.git.repo import GitRepo

        import subprocess

        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        repo = GitRepo(tmp_path)
        result = repo.log(count=5)
        assert isinstance(result, list)
