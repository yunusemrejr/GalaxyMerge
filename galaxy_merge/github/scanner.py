import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from galaxy_merge.core.locks import atomic_write


class GitHubScanner:
    def __init__(self, token: str = "", cache_dir: Path | None = None):
        self.token = token
        self.base_url = "https://api.github.com"
        self.cache_dir = cache_dir
        self._init_cache()

    def _init_cache(self) -> None:
        if not self.cache_dir:
            return
        scans_dir = self.cache_dir / "github" / "scans"
        scans_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, url: str) -> str:
        import hashlib
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _get_cached(self, url: str) -> dict[str, Any] | None:
        if not self.cache_dir:
            return None
        path = self.cache_dir / "github" / "scans" / f"{self._cache_key(url)}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                return data.get("result")
            except (json.JSONDecodeError, OSError):
                return None
        return None

    def _set_cache(self, url: str, result: dict[str, Any]) -> None:
        if not self.cache_dir:
            return
        path = self.cache_dir / "github" / "scans" / f"{self._cache_key(url)}.json"
        data = {
            "url": url,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "result": result,
        }
        atomic_write(path, json.dumps(data, indent=2, default=str))

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def scan_repo(self, url: str) -> dict[str, Any]:
        cached = self._get_cached(url)
        if cached:
            cached["_cached"] = True
            return cached

        owner, repo = self._parse_url(url)
        if not owner or not repo:
            return {"error": f"could not parse repo URL: {url}"}

        repo_data = await self._get_repo(owner, repo)
        if "error" in repo_data:
            return repo_data

        contents = await self._get_contents(owner, repo)
        readme = await self._get_readme(owner, repo)
        releases = await self._get_releases(owner, repo)
        issues = await self._get_issues(owner, repo)
        prs = await self._get_pull_requests(owner, repo)

        result = {
            "owner": owner,
            "repo": repo,
            "full_name": repo_data.get("full_name", f"{owner}/{repo}"),
            "description": repo_data.get("description", ""),
            "language": repo_data.get("language", ""),
            "stars": repo_data.get("stargazers_count", 0),
            "forks": repo_data.get("forks_count", 0),
            "open_issues_count": repo_data.get("open_issues_count", 0),
            "default_branch": repo_data.get("default_branch", "main"),
            "topics": repo_data.get("topics", []),
            "license": repo_data.get("license", {}).get("spdx_id", "") if repo_data.get("license") else "",
            "file_tree": self._summarize_tree(contents),
            "readme": readme,
            "recent_releases": releases,
            "recent_issues": issues,
            "open_pull_requests": prs,
        }
        self._set_cache(url, result)
        return result

    async def scan_from_git_remote(self, remote_url: str) -> dict[str, Any]:
        https_url = remote_url.replace("git@github.com:", "https://github.com/").replace(".git", "")
        return await self.scan_repo(https_url)

    async def _get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/repos/{owner}/{repo}",
                    headers=self._headers(),
                )
                if response.status_code == 404:
                    return {"error": "repository not found"}
                if response.status_code == 403:
                    return {"error": "API rate limited"}
                response.raise_for_status()
                return response.json()
            except Exception as e:
                return {"error": str(e)}

    async def _get_contents(self, owner: str, repo: str, path: str = "") -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"
                response = await client.get(url, headers=self._headers())
                if response.status_code == 200:
                    return response.json()
                return []
            except Exception:
                return []

    async def _get_readme(self, owner: str, repo: str) -> str:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                url = f"{self.base_url}/repos/{owner}/{repo}/readme"
                response = await client.get(url, headers=self._headers())
                if response.status_code == 200:
                    data = response.json()
                    import base64
                    content = data.get("content", "")
                    if content:
                        decoded = base64.b64decode(content).decode("utf-8", errors="replace")
                        return decoded[:5000]
                return ""
            except Exception:
                return ""

    async def _get_releases(self, owner: str, repo: str, count: int = 5) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                url = f"{self.base_url}/repos/{owner}/{repo}/releases"
                response = await client.get(
                    url, headers=self._headers(),
                    params={"per_page": count},
                )
                if response.status_code == 200:
                    return [
                        {
                            "tag_name": r.get("tag_name", ""),
                            "name": r.get("name", ""),
                            "published_at": r.get("published_at", ""),
                            "prerelease": r.get("prerelease", False),
                            "body_preview": (r.get("body", "") or "")[:500],
                        }
                        for r in response.json()
                    ]
                return []
            except Exception:
                return []

    async def _get_issues(self, owner: str, repo: str, count: int = 5) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                url = f"{self.base_url}/repos/{owner}/{repo}/issues"
                response = await client.get(
                    url, headers=self._headers(),
                    params={"state": "open", "per_page": count, "sort": "updated"},
                )
                if response.status_code == 200:
                    return [
                        {
                            "number": i.get("number", 0),
                            "title": i.get("title", ""),
                            "state": i.get("state", ""),
                            "updated_at": i.get("updated_at", ""),
                            "labels": [l.get("name", "") for l in i.get("labels", [])],
                        }
                        for i in response.json()
                        if "pull_request" not in i
                    ]
                return []
            except Exception:
                return []

    async def _get_pull_requests(self, owner: str, repo: str, count: int = 5) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                url = f"{self.base_url}/repos/{owner}/{repo}/pulls"
                response = await client.get(
                    url, headers=self._headers(),
                    params={"state": "open", "per_page": count, "sort": "updated"},
                )
                if response.status_code == 200:
                    return [
                        {
                            "number": pr.get("number", 0),
                            "title": pr.get("title", ""),
                            "state": pr.get("state", ""),
                            "updated_at": pr.get("updated_at", ""),
                            "user": pr.get("user", {}).get("login", ""),
                        }
                        for pr in response.json()
                    ]
                return []
            except Exception:
                return []

    def _parse_url(self, url: str) -> tuple[str, str]:
        url = url.strip().rstrip("/").rstrip(".git")
        if "github.com/" not in url:
            return "", ""
        parts = url.split("github.com/")[-1].split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
        return "", ""

    def _summarize_tree(self, contents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        tree = []
        for item in contents[:30]:
            tree.append({
                "name": item.get("name", ""),
                "type": item.get("type", ""),
                "path": item.get("path", ""),
            })
        return tree

    async def search_code(self, query: str, owner: str | None = None, repo: str | None = None) -> list[dict[str, Any]]:
        q = query
        if owner and repo:
            q = f"{query} repo:{owner}/{repo}"
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/search/code",
                    params={"q": q, "per_page": 10},
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()
                return [
                    {"name": item.get("name", ""), "path": item.get("path", ""), "url": item.get("html_url", "")}
                    for item in data.get("items", [])
                ]
            except Exception as e:
                return [{"error": str(e)}]
