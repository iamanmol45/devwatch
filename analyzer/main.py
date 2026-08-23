"""
DevWatch CLI Main Entrypoint.

Interactive CLI for GitHub repository engineering intelligence.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

# ---------------------------------------------------------
# Windows UTF-8 support
# ---------------------------------------------------------

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------

try:
    from dotenv import load_dotenv, find_dotenv

    dotenv_path = find_dotenv(usecwd=True)

    if dotenv_path:
        load_dotenv(dotenv_path)
    else:
        load_dotenv()

except ImportError:
    pass


# ---------------------------------------------------------
# Rich CLI
# ---------------------------------------------------------

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    RICH_AVAILABLE = True

except ImportError:
    RICH_AVAILABLE = False


# ---------------------------------------------------------
# Project paths
# ---------------------------------------------------------

current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
workspace_dir = parent_dir.parent

for path in [
    str(workspace_dir),
    str(parent_dir),
    str(current_dir)
]:
    if path not in sys.path:
        sys.path.insert(0, path)


# ---------------------------------------------------------
# Imports
# ---------------------------------------------------------

try:
    from devwatch.analyzer.github import GitHubClient
    from devwatch.analyzer.analyzer import RepoAnalyzer
    from devwatch.analyzer.bedrock import BedrockAnalyzer

except ImportError:

    try:
        from analyzer.github import GitHubClient
        from analyzer.analyzer import RepoAnalyzer
        from analyzer.bedrock import BedrockAnalyzer

    except ImportError:

        from github import GitHubClient
        from analyzer import RepoAnalyzer
        from bedrock import BedrockAnalyzer


# =========================================================
# CLI DISPLAY
# =========================================================

def print_rich_dashboard(
    data: Dict[str, Any],
    console: Console
):
    """
    Display the complete DevWatch engineering report.
    """

    repo = data["repository"]
    health = data["health"]
    commit_m = data["commit_metrics"]
    churn = data["code_churn"]
    contributors = data["contributors"]
    prs = data["pull_requests"]

    # -----------------------------------------------------
    # Header
    # -----------------------------------------------------

    console.print()

    title = Text()

    title.append(
        "DEVWATCH",
        style="bold cyan"
    )

    title.append(
        "  ENGINEERING INTELLIGENCE",
        style="bold white"
    )

    subtitle = (
        f"[bold]{repo['full_name']}[/bold]\n"
        f"{repo.get('description', 'No description available.')}\n\n"
        f"⭐ {repo['stars']}    "
        f"🍴 {repo['forks']}    "
        f"🐛 {repo['open_issues']}    "
        f"💻 {repo['language']}"
    )

    console.print(
        Panel(
            subtitle,
            title=title,
            border_style="cyan",
            expand=False
        )
    )

    # -----------------------------------------------------
    # Health
    # -----------------------------------------------------

    score = health["score"]

    if score >= 85:
        color = "green"
    elif score >= 70:
        color = "yellow"
    else:
        color = "red"

    console.print()

    console.print(
        Panel(
            f"[{color}][bold]{score}/100[/bold]  "
            f"{health['rating']}[/{color}]",
            title="REPOSITORY HEALTH",
            border_style=color,
            expand=False
        )
    )

    # -----------------------------------------------------
    # Activity
    # -----------------------------------------------------

    console.print()

    activity = Table(
        title="ACTIVITY & VELOCITY",
        header_style="bold cyan",
        show_lines=False
    )

    activity.add_column(
        "Metric",
        style="bold white"
    )

    activity.add_column(
        "Value",
        justify="right",
        style="green"
    )

    activity.add_row(
        "Analysis Period",
        f"{data['metadata']['analysis_window_days']} days"
    )

    activity.add_row(
        "Total Commits",
        str(commit_m["total_commits"])
    )

    activity.add_row(
        "Commits / Day",
        str(commit_m["commits_per_day_avg"])
    )

    activity.add_row(
        "Busiest Day",
        commit_m["busiest_day"]
    )

    activity.add_row(
        "Code Additions",
        f"+{churn['additions_sampled']}"
    )

    activity.add_row(
        "Code Deletions",
        f"-{churn['deletions_sampled']}"
    )

    activity.add_row(
        "Churn Ratio",
        str(churn["churn_ratio"])
    )

    activity.add_row(
        "Pull Requests",
        str(prs["total_prs"])
    )

    activity.add_row(
        "PR Merge Success",
        f"{prs['merge_success_rate_pct']}%"
    )

    activity.add_row(
        "Avg PR Merge Time",
        f"{prs['avg_merge_hours']} hours"
    )

    console.print(activity)

    # -----------------------------------------------------
    # Team Risk
    # -----------------------------------------------------

    console.print()

    risk = contributors.get(
        "bus_factor_risk",
        "UNKNOWN"
    )

    risk_color = {
        "HIGH": "red",
        "MEDIUM": "yellow",
        "LOW": "green"
    }.get(risk, "white")

    team = Table(
        title="TEAM RISK",
        header_style="bold magenta"
    )

    team.add_column("Metric")
    team.add_column("Value")

    team.add_row(
        "Contributor Risk",
        f"[{risk_color}][bold]{risk}[/bold][/{risk_color}]"
    )

    team.add_row(
        "Unique Contributors",
        str(contributors.get("total_unique", 0))
    )

    leaderboard = contributors.get(
        "leaderboard",
        []
    )

    if leaderboard:

        top = leaderboard[0]

        team.add_row(
            "Top Contributor",
            top["author"]
        )

        team.add_row(
            "Contribution Share",
            f"{top['percentage']}%"
        )

    console.print(team)

    # -----------------------------------------------------
    # Change Intelligence
    # -----------------------------------------------------

    change_intel = data.get(
        "change_intelligence",
        {}
    )

    important_files = change_intel.get(
        "important_files",
        []
    )

    file_categories = churn.get(
        "file_categories",
        {}
    )

    if file_categories:

        console.print()

        areas = Table(
            title="CHANGE INTELLIGENCE",
            header_style="bold blue"
        )

        areas.add_column(
            "Engineering Area"
        )

        areas.add_column(
            "Changes",
            justify="right"
        )

        sorted_areas = sorted(
            file_categories.items(),
            key=lambda item: item[1],
            reverse=True
        )

        for area, count in sorted_areas:

            if count > 0:

                areas.add_row(
                    area,
                    str(count)
                )

        console.print(areas)

    # -----------------------------------------------------
    # Important files
    # -----------------------------------------------------

    if important_files:

        console.print()

        files_table = Table(
            title="KEY MODIFIED FILES",
            header_style="bold green",
            show_lines=False
        )

        files_table.add_column(
            "File",
            style="white"
        )

        files_table.add_column(
            "Area",
            style="yellow"
        )

        files_table.add_column(
            "Status",
            style="cyan"
        )

        files_table.add_column(
            "Changes",
            justify="right",
            style="magenta"
        )

        for file_data in important_files[:10]:

            files_table.add_row(
                file_data.get(
                    "filename",
                    "Unknown"
                ),
                file_data.get(
                    "area",
                    "Other"
                ),
                file_data.get(
                    "status",
                    "modified"
                ),
                str(
                    file_data.get(
                        "changes",
                        0
                    )
                )
            )

        console.print(files_table)

    # -----------------------------------------------------
    # Insights
    # -----------------------------------------------------

    console.print()

    insights = health.get(
        "insights",
        []
    )

    if insights:

        insight_text = "\n\n".join(
            f"• {item}"
            for item in insights
        )

    else:

        insight_text = (
            "No major engineering warnings detected."
        )

    console.print(
        Panel(
            insight_text,
            title="KEY INSIGHTS",
            border_style="yellow"
        )
    )

    # -----------------------------------------------------
    # AI Insights
    # -----------------------------------------------------

    ai_insights = data.get(
        "ai_insights"
    )

    if ai_insights:

        console.print()

        console.print(
            Panel(
                ai_insights,
                title="AWS BEDROCK — ENGINEERING INTELLIGENCE",
                border_style="magenta",
                expand=False
            )
        )

    # -----------------------------------------------------
    # Final Verdict
    # -----------------------------------------------------

    console.print()

    if risk == "HIGH":

        verdict = (
            "Repository is active, but high contributor "
            "concentration represents a significant "
            "engineering risk."
        )

    elif score >= 85:

        verdict = (
            "Repository demonstrates strong engineering "
            "health and consistent development activity."
        )

    elif score >= 70:

        verdict = (
            "Repository is generally healthy, but some "
            "engineering risks should be monitored."
        )

    else:

        verdict = (
            "Repository requires engineering attention "
            "based on recent activity and risk signals."
        )

    recommendations = []

    if risk == "HIGH":

        recommendations.append(
            "Reduce single-contributor dependency"
        )

    if prs["avg_merge_hours"] > 72:

        recommendations.append(
            "Investigate slow PR resolution"
        )

    if change_intel.get("test_changes", 0) == 0:

        recommendations.append(
            "Increase test coverage for recent changes"
        )

    if not recommendations:

        recommendations.append(
            "Continue monitoring repository health"
        )

    recommendation_text = "\n".join(
        f"→ {item}"
        for item in recommendations
    )

    console.print(
        Panel(
            f"[bold]{verdict}[/bold]\n\n"
            f"[bold]Recommended Actions[/bold]\n"
            f"{recommendation_text}",
            title="DEVWATCH VERDICT",
            border_style="cyan"
        )
    )

    console.print()


# =========================================================
# MARKDOWN EXPORT
# =========================================================

def export_markdown_report(
    data: Dict[str, Any],
    filepath: str
):
    """
    Export DevWatch analysis to Markdown.
    """

    repo = data["repository"]
    health = data["health"]
    commits = data["commit_metrics"]
    churn = data["code_churn"]
    contributors = data["contributors"]
    prs = data["pull_requests"]

    change_intel = data.get(
        "change_intelligence",
        {}
    )

    content = f"""# DevWatch Engineering Report

## Repository

**Repository:** {repo['full_name']}

**Health Score:** {health['score']}/100 ({health['rating']})

**Stars:** {repo['stars']}

**Forks:** {repo['forks']}

**Open Issues:** {repo['open_issues']}

**Language:** {repo['language']}

## Activity

- Analysis Period: {data['metadata']['analysis_window_days']} days
- Total Commits: {commits['total_commits']}
- Commits / Day: {commits['commits_per_day_avg']}
- Busiest Day: {commits['busiest_day']}
- Code Additions: +{churn['additions_sampled']}
- Code Deletions: -{churn['deletions_sampled']}
- Churn Ratio: {churn['churn_ratio']}

## Pull Requests

- Total PRs: {prs['total_prs']}
- Merged PRs: {prs['merged']}
- Merge Success Rate: {prs['merge_success_rate_pct']}%
- Average Merge Time: {prs['avg_merge_hours']} hours

## Contributor Risk

- Risk Level: {contributors['bus_factor_risk']}
- Unique Contributors: {contributors['total_unique']}
"""

    leaderboard = contributors.get(
        "leaderboard",
        []
    )

    if leaderboard:

        content += """
## Top Contributors

| Rank | Author | Commits | Share |
|---|---|---:|---:|
"""

        for index, member in enumerate(
            leaderboard,
            1
        ):

            content += (
                f"| {index} | "
                f"{member['author']} | "
                f"{member['commits']} | "
                f"{member['percentage']}% |\n"
            )

    # Change intelligence

    content += """
## Change Intelligence

"""

    content += (
        f"- Sampled Files Changed: "
        f"{change_intel.get('total_files_changed', 0)}\n"
    )

    content += (
        f"- Test File Changes: "
        f"{change_intel.get('test_changes', 0)}\n"
    )

    important_files = change_intel.get(
        "important_files",
        []
    )

    if important_files:

        content += """
### Key Modified Files

| File | Area | Status | Changes |
|---|---|---|---:|
"""

        for item in important_files[:10]:

            content += (
                f"| `{item['filename']}` | "
                f"{item['area']} | "
                f"{item['status']} | "
                f"{item['changes']} |\n"
            )

    # Insights

    content += "\n## Key Insights\n\n"

    for insight in health.get(
        "insights",
        []
    ):

        content += f"- {insight}\n"

    # AI

    if data.get("ai_insights"):

        content += (
            "\n## AWS Bedrock Engineering Intelligence\n\n"
            f"{data['ai_insights']}\n"
        )

    with open(
        filepath,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(content)


# =========================================================
# MAIN
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "DevWatch - GitHub Repository "
            "Engineering Intelligence"
        )
    )

    parser.add_argument(
        "--repo",
        "-r",
        type=str,
        help=(
            "GitHub repository in "
            "'owner/repo' format or URL"
        )
    )

    parser.add_argument(
        "--token",
        "-t",
        type=str,
        help=(
            "GitHub Personal Access Token "
            "(defaults to GITHUB_TOKEN)"
        )
    )

    parser.add_argument(
        "--days",
        "-d",
        type=int,
        default=30,
        help="Number of days to analyze"
    )

    parser.add_argument(
        "--ai",
        action="store_true",
        help=(
            "Generate AI engineering insights "
            "using AWS Bedrock"
        )
    )

    parser.add_argument(
        "--model",
        type=str,
        default="amazon.nova-micro-v1:0",
        help="AWS Bedrock model ID"
    )

    parser.add_argument(
        "--export",
        "-e",
        choices=["json", "md"],
        help="Export report format"
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output file path"
    )

    args = parser.parse_args()

    # -----------------------------------------------------
    # Repository input
    # -----------------------------------------------------

    repo_input = args.repo

    if not repo_input:

        if sys.stdin.isatty():

            repo_input = input(
                "\nEnter GitHub repository "
                "(owner/repo or URL): "
            ).strip()

        else:

            print(
                "Error: --repo argument is required.",
                file=sys.stderr
            )

            sys.exit(1)

    if not repo_input:

        print(
            "Error: Repository cannot be empty.",
            file=sys.stderr
        )

        sys.exit(1)

    try:

        # -------------------------------------------------
        # GitHub
        # -------------------------------------------------

        client = GitHubClient(
            token=args.token
        )

        owner, repo_name = (
            client.parse_repo_input(
                repo_input
            )
        )

        if RICH_AVAILABLE:

            console = Console()

            console.print(
                f"\n[bold cyan]DEVWATCH[/bold cyan] "
                f"[dim]starting analysis...[/dim]"
            )

            console.print(
                f"[bold]Repository:[/bold] "
                f"{owner}/{repo_name}"
            )

            console.print(
                f"[bold]Window:[/bold] "
                f"{args.days} days\n"
            )

        else:

            print(
                f"\nAnalyzing "
                f"{owner}/{repo_name} "
                f"over {args.days} days...\n"
            )

        # -------------------------------------------------
        # Analyze
        # -------------------------------------------------

        analyzer = RepoAnalyzer(
            client,
            owner,
            repo_name,
            days=args.days
        )

        report_data = analyzer.analyze()

        # -------------------------------------------------
        # Bedrock
        # -------------------------------------------------

        if args.ai:

            if RICH_AVAILABLE:

                console.print(
                    f"[bold magenta]"
                    f"Generating AWS Bedrock "
                    f"engineering intelligence..."
                    f"[/bold magenta]"
                )

            else:

                print(
                    "Generating AWS Bedrock "
                    "engineering intelligence..."
                )

            try:

                bedrock = BedrockAnalyzer(
                    model_id=args.model
                )

                report_data["ai_insights"] = (
                    bedrock.generate_ai_insights(
                        report_data
                    )
                )

            except Exception as ai_error:

                report_data["ai_insights"] = (
                    "AWS Bedrock analysis is currently "
                    "unavailable.\n\n"
                    f"Reason: {ai_error}"
                )

        # -------------------------------------------------
        # Display
        # -------------------------------------------------

        if RICH_AVAILABLE:

            console = Console()

            print_rich_dashboard(
                report_data,
                console
            )

        else:

            print(
                json.dumps(
                    report_data,
                    indent=2
                )
            )

        # -------------------------------------------------
        # Export
        # -------------------------------------------------

        if args.export:

            export_format = args.export

            output_file = (
                args.output
                or
                f"devwatch_"
                f"{owner}_"
                f"{repo_name}."
                f"{export_format}"
            )

            if export_format == "json":

                with open(
                    output_file,
                    "w",
                    encoding="utf-8"
                ) as file:

                    json.dump(
                        report_data,
                        file,
                        indent=2
                    )

            elif export_format == "md":

                export_markdown_report(
                    report_data,
                    output_file
                )

            print(
                f"\nReport exported to:\n"
                f"{os.path.abspath(output_file)}"
            )

    except Exception as error:

        print(
            f"\n[DevWatch Error]: {error}",
            file=sys.stderr
        )

        sys.exit(1)


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    main()