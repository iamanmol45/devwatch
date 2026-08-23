"""
GitHub REST API client module for DevWatch.
Handles authentication, rate limiting, and retrieving repository details, commits, PRs, and contributors.
"""

from datetime import datetime, timedelta, timezone
import os
from typing import Any, Dict, List, Optional
import requests


class GitHubClient:
    """Client for interacting with the GitHub REST API (v3)."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: Optional[str] = None):
        """
        Initialize the GitHub client.
        
        :param token: Personal Access Token for GitHub. If None, attempts to load from GITHUB_TOKEN env var.
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.session = requests.Session()
        
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "DevWatch-Analyzer/0.1.0",
        }
        
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            
        self.session.headers.update(headers)

    def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Helper method to handle GET requests and error handling."""
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        try:
            response = self.session.get(url, params=params, timeout=15)
            
            # Check rate limiting info
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining and int(remaining) == 0:
                reset_time = response.headers.get("X-RateLimit-Reset")
                raise RuntimeError(
                    f"GitHub API rate limit exceeded. Resets at epoch timestamp {reset_time}. "
                    "Provide a GITHUB_TOKEN to increase limit."
                )

            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            if response.status_code == 404:
                raise ValueError(f"Resource not found on GitHub: {endpoint}") from err
            elif response.status_code == 401:
                raise PermissionError("Unauthorized. Please check your GitHub access token.") from err
            raise RuntimeError(f"GitHub API error ({response.status_code}): {err}") from err
        except requests.exceptions.RequestException as err:
            raise RuntimeError(f"Network error communicating with GitHub: {err}") from err

    def parse_repo_input(self, repo_input: str) -> tuple[str, str]:
        """
        Parse owner and repo name from input strings such as:
        'owner/repo', 'https://github.com/owner/repo', or 'github.com/owner/repo'.
        """
        cleaned = repo_input.strip()
        if "github.com/" in cleaned:
            cleaned = cleaned.split("github.com/")[-1]
        cleaned = cleaned.rstrip("/").removesuffix(".git")
        
        parts = cleaned.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
        raise ValueError(f"Invalid repository specification: '{repo_input}'. Expected format 'owner/repo'.")

    def get_repo_info(self, owner: str, repo: str) -> Dict[str, Any]:
        """Fetch general metadata for a repository."""
        data = self._request(f"repos/{owner}/{repo}")
        return {
            "name": data.get("name"),
            "full_name": data.get("full_name"),
            "description": data.get("description", "No description provided."),
            "owner": data.get("owner", {}).get("login"),
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "open_issues": data.get("open_issues_count", 0),
            "language": data.get("language") or "Not specified",
            "default_branch": data.get("default_branch", "main"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "pushed_at": data.get("pushed_at"),
            "html_url": data.get("html_url"),
        }

    def get_commits(self, owner: str, repo: str, days: int = 30, max_commits: int = 100) -> List[Dict[str, Any]]:
        """Fetch recent commits within the specified day window."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        params = {"since": since, "per_page": min(max_commits, 100)}
        
        raw_commits = self._request(f"repos/{owner}/{repo}/commits", params=params)
        commits = []
        
        for c in raw_commits:
            author_data = c.get("author") or {}
            commit_data = c.get("commit", {})
            author_info = commit_data.get("author", {})
            
            commits.append({
                "sha": c.get("sha"),
                "author_login": author_data.get("login") or author_info.get("name", "Unknown"),
                "author_email": author_info.get("email"),
                "message": commit_data.get("message", "").split("\n")[0],  # Title only
                "date": author_info.get("date"),
                "html_url": c.get("html_url"),
            })
        return commits

    def get_commit_stats(
        self,
        owner: str,
        repo: str,
        sha: str
    ) -> Dict[str, Any]:
        """Fetch detailed information about files changed in a commit."""
        data = self._request(f"repos/{owner}/{repo}/commits/{sha}")

        stats = data.get("stats", {})
        files = data.get("files", [])

        changed_files = []
        for file in files:
            changed_files.append({
                "filename": file.get("filename", ""),
                "status": file.get("status", "modified"),
                "additions": file.get("additions", 0),
                "deletions": file.get("deletions", 0),
                "changes": file.get("changes", 0)
            })

        return {
            "additions": stats.get("additions", 0),
            "deletions": stats.get("deletions", 0),
            "total": stats.get("total", 0),
            "files_changed": len(files),
            "files": changed_files
        }


    def get_pull_requests(self, owner: str, repo: str, days: int = 30, max_prs: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent pull requests."""
        params = {"state": "all", "sort": "updated", "direction": "desc", "per_page": min(max_prs, 100)}
        raw_prs = self._request(f"repos/{owner}/{repo}/pulls", params=params)
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        prs = []
        
        for pr in raw_prs:
            updated_at_str = pr.get("updated_at")
            if updated_at_str:
                updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                if updated_at < cutoff:
                    continue

            user = pr.get("user") or {}
            prs.append({
                "number": pr.get("number"),
                "title": pr.get("title"),
                "state": pr.get("state"),
                "user": user.get("login", "Unknown"),
                "created_at": pr.get("created_at"),
                "closed_at": pr.get("closed_at"),
                "merged_at": pr.get("merged_at"),
                "html_url": pr.get("html_url"),
            })
        return prs

    def get_contributors(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """Fetch repository contributor activity."""
        raw_contribs = self._request(f"repos/{owner}/{repo}/contributors", params={"per_page": 30})
        contribs = []
        for c in raw_contribs:
            contribs.append({
                "login": c.get("login"),
                "contributions": c.get("contributions", 0),
                "avatar_url": c.get("avatar_url"),
                "html_url": c.get("html_url"),
            })
        return contribs

    def get_rate_limit(self) -> Dict[str, Any]:
        """Fetch current rate limit status."""
        data = self._request("rate_limit")
        core = data.get("rate", {})
        return {
            "limit": core.get("limit"),
            "remaining": core.get("remaining"),
            "reset": core.get("reset"),
        }

    def get_file_content(self, owner: str, repo: str, path: str) -> Optional[Dict[str, Any]]:
        """
        Fetch file contents/metadata for a given file path in a repository.
        Returns None if file is not found.
        """
        try:
            return self._request(f"repos/{owner}/{repo}/contents/{path.lstrip('/')}")
        except ValueError:
            return None

