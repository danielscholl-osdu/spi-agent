"""Base class for GitHub tools with common formatting methods."""

from typing import Any, Dict

from github import Auth, Github

from spi_agent.config import AgentConfig


class GitHubToolsBase:
    """Base class providing GitHub client and common formatting methods."""

    def __init__(self, config: AgentConfig):
        """
        Initialize GitHub tools.

        Args:
            config: Agent configuration containing GitHub token and org info
        """
        self.config = config

        # Initialize GitHub client
        if config.github_token:
            auth = Auth.Token(config.github_token)
            self.github = Github(auth=auth)
        else:
            # Try without authentication (limited API calls)
            self.github = Github()

    def _format_issue(self, issue: Any) -> Dict[str, Any]:
        """Format GitHub issue object to dict."""
        return {
            "number": issue.number,
            "title": issue.title,
            "body": issue.body or "",
            "state": issue.state,
            "labels": [label.name for label in issue.labels],
            "assignees": [assignee.login for assignee in issue.assignees],
            "created_at": issue.created_at.isoformat(),
            "updated_at": issue.updated_at.isoformat(),
            "html_url": issue.html_url,
            "comments_count": issue.comments,
            "author": issue.user.login if issue.user else "unknown",
        }

    def _format_comment(self, comment: Any) -> Dict[str, Any]:
        """Format GitHub comment to dict with truncation for long bodies."""
        body = comment.body or ""
        max_len = 1500  # Prevent overly long responses
        truncated = body[:max_len]
        if len(body) > max_len:
            truncated += "\n… (comment truncated)"
        return {
            "id": comment.id,
            "body": truncated,
            "author": comment.user.login if comment.user else "unknown",
            "created_at": comment.created_at.isoformat(),
            "updated_at": comment.updated_at.isoformat(),
            "html_url": comment.html_url,
        }

    def _format_pr(self, pr: Any) -> Dict[str, Any]:
        """Format GitHub pull request to dict."""
        return {
            "number": pr.number,
            "title": pr.title,
            "body": pr.body or "",
            "state": pr.state,
            "draft": pr.draft,
            "merged": pr.merged,
            "mergeable": pr.mergeable,
            "mergeable_state": pr.mergeable_state,
            "base_ref": pr.base.ref,
            "head_ref": pr.head.ref,
            "labels": [label.name for label in pr.labels],
            "assignees": [assignee.login for assignee in pr.assignees],
            "created_at": pr.created_at.isoformat(),
            "updated_at": pr.updated_at.isoformat(),
            "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
            "html_url": pr.html_url,
            "comments_count": pr.comments,
            "review_comments_count": pr.review_comments,
            "commits_count": pr.commits,
            "changed_files": pr.changed_files,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "author": pr.user.login if pr.user else "unknown",
        }

    def _format_workflow(self, workflow: Any) -> Dict[str, Any]:
        """Format GitHub workflow to dict."""
        return {
            "id": workflow.id,
            "name": workflow.name,
            "path": workflow.path,
            "state": workflow.state,
            "created_at": workflow.created_at.isoformat(),
            "updated_at": workflow.updated_at.isoformat(),
            "html_url": workflow.html_url,
        }

    def _format_workflow_run(self, run: Any) -> Dict[str, Any]:
        """Format GitHub workflow run to dict."""
        return {
            "id": run.id,
            "name": run.name,
            "workflow_id": run.workflow_id,
            "status": run.status,  # queued, in_progress, completed
            "conclusion": run.conclusion,  # success, failure, cancelled, skipped
            "head_branch": run.head_branch,
            "head_sha": run.head_sha[:7] if run.head_sha else "unknown",  # Short SHA
            "event": run.event,  # push, pull_request, workflow_dispatch, etc.
            "created_at": run.created_at.isoformat(),
            "updated_at": run.updated_at.isoformat(),
            "run_started_at": run.run_started_at.isoformat() if run.run_started_at else None,
            "html_url": run.html_url,
            "actor": run.actor.login if run.actor else "unknown",
        }

    def _format_code_scanning_alert(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """Format code scanning alert from API response to dict."""
        rule = alert.get("rule") or {}
        most_recent_instance = alert.get("most_recent_instance") or {}
        location = most_recent_instance.get("location") or {}
        tool = alert.get("tool") or {}
        message = most_recent_instance.get("message") or {}

        return {
            "number": alert.get("number"),
            "state": alert.get("state"),  # open, dismissed, fixed
            "dismissed_reason": alert.get("dismissed_reason"),
            "dismissed_comment": alert.get("dismissed_comment"),
            "created_at": alert.get("created_at", ""),
            "updated_at": alert.get("updated_at", ""),
            "dismissed_at": alert.get("dismissed_at"),
            "dismissed_by": (
                alert.get("dismissed_by", {}).get("login") if alert.get("dismissed_by") else None
            ),
            "html_url": alert.get("html_url", ""),
            # Rule information
            "rule_id": rule.get("id") or "unknown",
            "rule_name": rule.get("name") or "unknown",
            "rule_description": rule.get("description") or "",
            "rule_severity": rule.get("severity") or "unknown",  # none, note, warning, error
            "rule_security_severity_level": rule.get("security_severity_level")
            or "unknown",  # low, medium, high, critical
            "rule_tags": rule.get("tags") or [],
            # Tool information
            "tool_name": tool.get("name") or "unknown",
            "tool_version": tool.get("version") or "unknown",
            # Location information
            "file_path": location.get("path") or "unknown",
            "start_line": location.get("start_line"),
            "end_line": location.get("end_line"),
            "start_column": location.get("start_column"),
            "end_column": location.get("end_column"),
            # Instance information
            "message": message.get("text") or "",
            "ref": most_recent_instance.get("ref") or "unknown",
            "analysis_key": most_recent_instance.get("analysis_key") or "",
            "commit_sha": most_recent_instance.get("commit_sha") or "unknown",
        }
