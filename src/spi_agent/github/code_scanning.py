"""Code scanning security tools for GitHub."""

from typing import Annotated, Optional

from github import GithubException
from pydantic import Field

from spi_agent.github.base import GitHubToolsBase


class CodeScanningTools(GitHubToolsBase):
    """Tools for managing GitHub code scanning alerts."""

    def list_code_scanning_alerts(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        state: Annotated[
            Optional[str],
            Field(description="Alert state: 'open', 'closed', 'dismissed', 'fixed' (default: open)"),
        ] = "open",
        severity: Annotated[
            Optional[str],
            Field(
                description=(
                    "Security severity: 'critical', 'high', 'medium', 'low' "
                    "(filters by security_severity_level)"
                )
            ),
        ] = None,
        limit: Annotated[int, Field(description="Maximum alerts to return")] = 30,
    ) -> str:
        """
        List code scanning alerts in a repository.

        Returns formatted string with code scanning alert list.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)

            # Build query parameters
            params = {"state": state, "per_page": min(limit, 100)}

            # Make API request using PyGithub's internal requester
            # GitHub API: GET /repos/{owner}/{repo}/code-scanning/alerts
            headers, data = gh_repo._requester.requestJsonAndCheck(
                "GET", f"{gh_repo.url}/code-scanning/alerts", parameters=params
            )

            if not data:
                return f"No {state} code scanning alerts found in {repo_full_name}"

            # Filter by severity if specified
            filtered_alerts = data
            if severity:
                filtered_alerts = [
                    alert
                    for alert in data
                    if ((alert.get("rule") or {}).get("security_severity_level") or "").lower()
                    == severity.lower()
                ]

                if not filtered_alerts:
                    return (
                        f"No {state} code scanning alerts with severity '{severity}' "
                        f"found in {repo_full_name}"
                    )

            # Limit results
            results = filtered_alerts[: min(limit, len(filtered_alerts))]

            # Format for display
            output_lines = [
                f"Found {len(results)} code scanning alert(s) in {repo_full_name}:\n\n"
            ]

            for alert_data in results:
                formatted = self._format_code_scanning_alert(alert_data)

                # Severity badge
                severity_level = formatted["rule_security_severity_level"] or "unknown"
                severity_icon = {
                    "critical": "🔴",
                    "high": "🟠",
                    "medium": "🟡",
                    "low": "🟢",
                }.get(severity_level.lower(), "⚪")

                # State badge
                state_display = {
                    "open": "🔓 Open",
                    "dismissed": "🔕 Dismissed",
                    "fixed": "✅ Fixed",
                    "closed": "🔒 Closed",
                }.get(formatted["state"], formatted["state"])

                output_lines.append(
                    f"{severity_icon} Alert #{formatted['number']}: {formatted['rule_name']}\n"
                    f"  Severity: {severity_level.title()} | State: {state_display}\n"
                    f"  Tool: {formatted['tool_name']} | Rule: {formatted['rule_id']}\n"
                    f"  File: {formatted['file_path']}"
                )

                if formatted["start_line"]:
                    output_lines.append(f":{formatted['start_line']}")
                    if formatted["end_line"] and formatted["end_line"] != formatted["start_line"]:
                        output_lines.append(f"-{formatted['end_line']}")

                output_lines.append(f"\n  URL: {formatted['html_url']}\n\n")

            return "".join(output_lines)

        except GithubException as e:
            if e.status == 403:
                return (
                    f"Access denied to code scanning alerts in {repo_full_name}. "
                    f"Ensure your token has 'security_events' scope."
                )
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error listing code scanning alerts: {str(e)}"

    def get_code_scanning_alert(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        alert_number: Annotated[
            int,
            Field(
                description=(
                    "Code scanning alert number (from URL like "
                    "github.com/org/repo/security/code-scanning/5)"
                )
            ),
        ],
    ) -> str:
        """
        Get detailed information about a specific code scanning alert.

        Returns formatted string with alert details including location, severity, and remediation.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)

            # Make API request using PyGithub's internal requester
            # GitHub API: GET /repos/{owner}/{repo}/code-scanning/alerts/{alert_number}
            headers, data = gh_repo._requester.requestJsonAndCheck(
                "GET", f"{gh_repo.url}/code-scanning/alerts/{alert_number}"
            )

            formatted = self._format_code_scanning_alert(data)

            # Severity badge
            severity_level = formatted["rule_security_severity_level"] or "unknown"
            severity_icon = {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🟢",
            }.get(severity_level.lower(), "⚪")

            # State badge
            state_display = {
                "open": "🔓 Open",
                "dismissed": "🔕 Dismissed",
                "fixed": "✅ Fixed",
                "closed": "🔒 Closed",
            }.get(formatted["state"], formatted["state"])

            # Build output
            output = [
                f"\n{severity_icon} Code Scanning Alert #{formatted['number']}: "
                f"{formatted['rule_name']}\n",
                f"{'=' * 80}\n\n",
                f"State: {state_display}\n",
                f"Severity: {severity_level.title()} ({formatted['rule_severity']})\n",
                f"Tool: {formatted['tool_name']} {formatted['tool_version']}\n",
                f"Rule ID: {formatted['rule_id']}\n",
            ]

            # Tags
            if formatted["rule_tags"]:
                output.append(f"Tags: {', '.join(formatted['rule_tags'])}\n")

            output.append(f"\n📍 Location:\n")
            output.append(f"  File: {formatted['file_path']}\n")

            if formatted["start_line"]:
                line_info = f"  Lines: {formatted['start_line']}"
                if formatted["end_line"] and formatted["end_line"] != formatted["start_line"]:
                    line_info += f"-{formatted['end_line']}"
                output.append(f"{line_info}\n")

            if formatted["start_column"]:
                col_info = f"  Columns: {formatted['start_column']}"
                if formatted["end_column"] and formatted["end_column"] != formatted["start_column"]:
                    col_info += f"-{formatted['end_column']}"
                output.append(f"{col_info}\n")

            output.append(f"  Branch: {formatted['ref']}\n")
            output.append(f"  Commit: {formatted['commit_sha'][:7]}\n")

            # Description
            if formatted["rule_description"]:
                output.append(f"\n📝 Description:\n")
                output.append(f"{formatted['rule_description']}\n")

            # Message from analysis
            if formatted["message"]:
                output.append(f"\n💬 Analysis Message:\n")
                output.append(f"{formatted['message']}\n")

            # Dismissal information
            if formatted["state"] == "dismissed":
                output.append(f"\n🔕 Dismissal Information:\n")
                if formatted["dismissed_reason"]:
                    output.append(f"  Reason: {formatted['dismissed_reason']}\n")
                if formatted["dismissed_by"]:
                    output.append(f"  Dismissed by: {formatted['dismissed_by']}\n")
                if formatted["dismissed_at"]:
                    output.append(f"  Dismissed at: {formatted['dismissed_at']}\n")
                if formatted["dismissed_comment"]:
                    output.append(f"  Comment: {formatted['dismissed_comment']}\n")

            # Timestamps
            output.append(f"\n⏰ Timeline:\n")
            output.append(f"  Created: {formatted['created_at']}\n")
            output.append(f"  Updated: {formatted['updated_at']}\n")

            # URL
            output.append(f"\n🔗 Alert URL:\n{formatted['html_url']}\n")

            return "".join(output)

        except GithubException as e:
            if e.status == 404:
                return f"Code scanning alert #{alert_number} not found in {repo_full_name}"
            elif e.status == 403:
                return (
                    f"Access denied to code scanning alert in {repo_full_name}. "
                    f"Ensure your token has 'security_events' scope."
                )
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error getting code scanning alert: {str(e)}"
