import pytest
from galaxy_merge.github.scanner import GitHubScanner


class TestGitHubScanner:
    def test_parse_url(self):
        scanner = GitHubScanner()
        owner, repo = scanner._parse_url("https://github.com/owner/repo")
        assert owner == "owner"
        assert repo == "repo"

    def test_parse_url_with_git_suffix(self):
        scanner = GitHubScanner()
        owner, repo = scanner._parse_url("https://github.com/owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"

    def test_parse_url_invalid(self):
        scanner = GitHubScanner()
        owner, repo = scanner._parse_url("not-a-url")
        assert owner == ""
        assert repo == ""

    def test_scan_from_git_remote(self):
        scanner = GitHubScanner()
        https_url = "git@github.com:user/repo.git".replace("git@github.com:", "https://github.com/").replace(".git", "")
        owner, repo = scanner._parse_url(https_url)
        assert owner == "user"
        assert repo == "repo"
