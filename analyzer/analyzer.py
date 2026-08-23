"""
Repository analysis module for DevWatch.
Calculates contributor stats, commit velocity, code churn, PR latency, file change intelligence, and repository health metrics.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from github import GitHubClient


class RepoAnalyzer:
    """Analyzer engine processing raw GitHub API responses into actionable insights."""

    def __init__(self, client: GitHubClient, owner: str, repo: str, days: int = 30):
        self.client = client
        self.owner = owner
        self.repo = repo
        self.days = days

    def classify_file(self, filename: str) -> str:
        """Classify a changed file into an engineering area."""
        name = filename.lower()

        # Authentication / security
        if any(word in name for word in [
            "auth", "authentication", "authorize", "authorization",
            "login", "logout", "session", "permission", "permissions",
            "security", "jwt", "oauth", "token"
        ]):
            return "Authentication"

        # Dependencies
        if any(word in name for word in [
            "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
            "bun.lock", "requirements.txt", "pyproject.toml", "cargo.toml", "go.mod"
        ]):
            return "Dependencies"

        # API / backend routes
        if any(word in name for word in [
            "/api/", "/routes/", "/route.", "/controller", "/controllers/",
            "/endpoint", "/endpoints/", "graphql", "resolver"
        ]):
            return "API"

        # Database
        if any(word in name for word in [
            "migration", "migrations/", "/models/", "/model.", "schema",
            "schemas/", "database", "db/", "prisma", "sequelize", "mongoose"
        ]):
            return "Database"

        # Tests
        if any(word in name for word in [
            ".test.", ".spec.", "test/", "tests/", "__tests__/", "__test__/", "test_"
        ]):
            return "Tests"

        # Configuration / deployment
        if any(word in name for word in [
            "config", ".env", "dockerfile", "docker-compose", "webpack",
            "vite.config", "tsconfig", "eslint", "prettier", ".github/workflows/"
        ]):
            return "Configuration"

        # Frontend
        if any(word in name for word in [
            "components/", "component.", "pages/", "views/", "screens/",
            "hooks/", "frontend/", "client/", "styles/", ".tsx", ".jsx"
        ]):
            return "Frontend"

        # Documentation
        if any(word in name for word in [
            "readme", "docs/", ".md", "documentation/"
        ]):
            return "Documentation"

        return "Other"


    def analyze_changed_files(self, commits: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze files changed and calculate code churn metrics from recent commits."""
        changed_files = set()
        important_files = []
        areas = Counter()
        total_additions = 0
        total_deletions = 0

        for commit in commits:
            try:
                stats = self.client.get_commit_stats(
                    self.owner,
                    self.repo,
                    commit["sha"]
                )

                total_additions += stats.get("additions", 0)
                total_deletions += stats.get("deletions", 0)

                for file in stats.get("files", []):
                    filename = file.get("filename", "")
                    if not filename:
                        continue
                    changed_files.add(filename)

                    area = self.classify_file(filename)
                    areas[area] += 1

                    if area != "Other":
                        important_files.append({
                            "filename": filename,
                            "area": area,
                            "status": file.get("status", "modified"),
                            "changes": file.get("changes", 0)
                        })

            except Exception:
                continue

        # Remove duplicate files while maintaining order
        unique_important_files = {}
        for file in important_files:
            unique_important_files[file["filename"]] = file

        important_files_list = list(unique_important_files.values())

        # Check whether important code changed without corresponding test modifications
        non_test_areas = [
            area for area in areas
            if area not in ["Tests", "Other"]
        ]

        test_changes = areas.get("Tests", 0)
        warnings = []

        if non_test_areas and test_changes == 0:
            warnings.append(
                "Important application code changed, but no test files were modified."
            )

        net_lines = total_additions - total_deletions
        churn_ratio = round(total_additions / (total_deletions if total_deletions > 0 else 1), 2)

        return {
            "additions_sampled": total_additions,
            "deletions_sampled": total_deletions,
            "net_lines_sampled": net_lines,
            "churn_ratio": churn_ratio,
            "total_files_changed": len(changed_files),
            "areas": dict(areas),
            "important_files": important_files_list[:20],
            "test_changes": test_changes,
            "warnings": warnings,
            "sampled_commit_count": len(commits)
        }

    def analyze(self, fetch_churn_details: bool = True, max_churn_commits: int = 15) -> Dict[str, Any]:
        """
        Run comprehensive analysis on the repository.
        
        :param fetch_churn_details: Whether to fetch line addition/deletion stats for individual commits.
        :param max_churn_commits: Limit detailed commit fetches to avoid exceeding API limits.
        """
        repo_info = self.client.get_repo_info(self.owner, self.repo)
        commits = self.client.get_commits(self.owner, self.repo, days=self.days)
        prs = self.client.get_pull_requests(self.owner, self.repo, days=self.days)
        contributors = self.client.get_contributors(self.owner, self.repo)

        # 1. Commit Analysis & Contributor Activity
        author_commit_counts = Counter()
        day_of_week_counts = Counter()
        commits_per_day = defaultdict(int)

        # Sample commit details for code churn & change intelligence if requested
        sample_commits = commits[:max_churn_commits] if fetch_churn_details else []
        change_intelligence = self.analyze_changed_files(sample_commits)

        for c in commits:
            author = c["author_login"]
            author_commit_counts[author] += 1
            
            if c["date"]:
                try:
                    dt = datetime.fromisoformat(c["date"].replace("Z", "+00:00"))
                    day_name = dt.strftime("%A")
                    date_str = dt.strftime("%Y-%m-%d")
                    day_of_week_counts[day_name] += 1
                    commits_per_day[date_str] += 1
                except ValueError:
                    pass

        # 2. Contributor Leaderboard
        total_commits = len(commits)
        leaderboard = []
        for author, count in author_commit_counts.most_common(10):
            percentage = (count / total_commits * 100) if total_commits > 0 else 0
            leaderboard.append({
                "author": author,
                "commits": count,
                "percentage": round(percentage, 1),
            })

        # Single Contributor Concentration Risk
        top_contributor_share = leaderboard[0]["percentage"] if leaderboard else 0.0
        bus_factor_risk = "HIGH" if top_contributor_share > 60.0 else ("MEDIUM" if top_contributor_share > 40.0 else "LOW")

        # 3. Pull Request Analysis
        pr_states = Counter()
        merged_durations_hours = []
        
        for pr in prs:
            state = pr["state"]
            if pr.get("merged_at"):
                pr_states["merged"] += 1
                
                # Calculate merge turnaround time
                try:
                    created = datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00"))
                    merged = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
                    duration = (merged - created).total_seconds() / 3600.0
                    merged_durations_hours.append(duration)
                except (ValueError, TypeError):
                    pass
            elif state == "closed":
                pr_states["closed_unmerged"] += 1
            else:
                pr_states["open"] += 1

        total_prs = len(prs)
        merged_prs = pr_states["merged"]
        merge_success_rate = (merged_prs / total_prs * 100) if total_prs > 0 else 0.0
        avg_pr_merge_hours = (sum(merged_durations_hours) / len(merged_durations_hours)) if merged_durations_hours else 0.0

        # 4. DevWatch Health Score Calculation (0-100)
        health_score = 100.0
        insights = []

        # Deduct for bus factor risk
        if bus_factor_risk == "HIGH":
            health_score -= 20
            insights.append(f"⚠️ High contributor concentration: '{leaderboard[0]['author']}' accounts for {top_contributor_share}% of recent commits.")
        elif bus_factor_risk == "MEDIUM":
            health_score -= 10
            insights.append(f"ℹ️ Moderate contributor concentration ({top_contributor_share}% by top committer).")

        # Deduct for slow PR merges
        if avg_pr_merge_hours > 72:
            health_score -= 15
            insights.append(f"🐢 Slow PR resolution speed: Average PR merge time is {round(avg_pr_merge_hours / 24, 1)} days.")
        elif avg_pr_merge_hours > 0:
            insights.append(f"⚡ Healthy PR turnaround: Average PR merge time is {round(avg_pr_merge_hours, 1)} hours.")

        # Check commit frequency
        commits_per_day_avg = round(total_commits / self.days, 2)
        if commits_per_day_avg == 0:
            health_score -= 25
            insights.append("🛑 Low repository activity: Zero commits detected in the selected time window.")
        else:
            insights.append(f"🔥 Active repository velocity: ~{commits_per_day_avg} commits per day over last {self.days} days.")

        # Check for change intelligence warnings
        for warn in change_intelligence.get("warnings", []):
            health_score -= 5
            insights.append(f"⚠️ {warn}")

        # PR merge rate check
        if total_prs > 0 and merge_success_rate < 50.0:
            health_score -= 10
            insights.append(f"⚠️ Low PR merge success rate: Only {round(merge_success_rate, 1)}% of PRs were merged.")

        health_score = max(0.0, min(100.0, health_score))

        return {
            "metadata": {
                "owner": self.owner,
                "repo": self.repo,
                "analysis_window_days": self.days,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            "repository": repo_info,
            "commit_metrics": {
                "total_commits": total_commits,
                "commits_per_day_avg": commits_per_day_avg,
                "busiest_day": day_of_week_counts.most_common(1)[0][0] if day_of_week_counts else "N/A",
                "day_distribution": dict(day_of_week_counts),
            },
            "code_churn": {
                "additions_sampled": change_intelligence["additions_sampled"],
                "deletions_sampled": change_intelligence["deletions_sampled"],
                "net_lines_sampled": change_intelligence["net_lines_sampled"],
                "churn_ratio": change_intelligence["churn_ratio"],
                "sampled_commit_count": change_intelligence["sampled_commit_count"],
                "file_categories": change_intelligence["areas"],
            },
            "change_intelligence": change_intelligence,
            "contributors": {
                "total_unique": len(contributors),
                "leaderboard": leaderboard,
                "bus_factor_risk": bus_factor_risk,
                "top_contributor_share_pct": top_contributor_share,
            },
            "pull_requests": {
                "total_prs": total_prs,
                "merged": merged_prs,
                "open": pr_states["open"],
                "closed_unmerged": pr_states["closed_unmerged"],
                "merge_success_rate_pct": round(merge_success_rate, 1),
                "avg_merge_hours": round(avg_pr_merge_hours, 1),
            },
            "health": {
                "score": round(health_score, 1),
                "rating": "EXCELLENT" if health_score >= 85 else ("GOOD" if health_score >= 70 else ("NEEDS IMPROVEMENT" if health_score >= 50 else "POOR")),
                "insights": insights,
            },
        }
