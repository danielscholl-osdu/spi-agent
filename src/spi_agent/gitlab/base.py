"""Base class for GitLab tools with common formatting methods."""

from typing import Any, Dict, Optional

import gitlab
from gitlab.exceptions import GitlabError

from spi_agent.config import AgentConfig


class GitLabToolsBase:
    """Base class providing GitLab client and common formatting methods."""

    def __init__(self, config: AgentConfig):
        """
        Initialize GitLab tools.

        Args:
            config: Agent configuration containing GitLab URL and token
        """
        self.config = config

        # All OSDU services use community.opengroup.org
        gitlab_url = "https://community.opengroup.org"

        # Initialize GitLab client
        if config.gitlab_token:
            self.gitlab = gitlab.Gitlab(
                url=gitlab_url,
                private_token=config.gitlab_token,
            )
            # Authenticate to verify token
            try:
                self.gitlab.auth()
            except GitlabError as e:
                # Log but don't fail - tools will handle errors individually
                import logging
                logging.warning(f"GitLab authentication warning: {e}")
        else:
            # Create unauthenticated client for public projects
            self.gitlab = gitlab.Gitlab(url=gitlab_url)

    def _format_issue(self, issue: Any) -> Dict[str, Any]:
        """Format GitLab issue object to dict."""
        return {
            "iid": issue.iid,  # Internal ID (project-scoped)
            "id": issue.id,  # Global ID
            "title": issue.title,
            "description": issue.description or "",
            "state": issue.state,
            "labels": issue.labels if hasattr(issue, "labels") else [],
            "assignees": [
                assignee.get("username", "unknown")
                for assignee in (issue.assignees if hasattr(issue, "assignees") else [])
            ],
            "author": issue.author.get("username", "unknown") if hasattr(issue, "author") else "unknown",
            "created_at": issue.created_at,
            "updated_at": issue.updated_at,
            "web_url": issue.web_url,
            "upvotes": issue.upvotes if hasattr(issue, "upvotes") else 0,
            "downvotes": issue.downvotes if hasattr(issue, "downvotes") else 0,
        }

    def _format_note(self, note: Any) -> Dict[str, Any]:
        """Format GitLab note/comment to dict with truncation for long bodies."""
        body = note.body or ""
        max_len = 1500  # Prevent overly long responses
        truncated = body[:max_len]
        if len(body) > max_len:
            truncated += "\n… (note truncated)"
        return {
            "id": note.id,
            "body": truncated,
            "author": note.author.get("username", "unknown") if hasattr(note, "author") else "unknown",
            "created_at": note.created_at,
            "updated_at": note.updated_at,
            "system": note.system if hasattr(note, "system") else False,
        }

    def _format_merge_request(self, mr: Any) -> Dict[str, Any]:
        """Format GitLab merge request to dict."""
        return {
            "iid": mr.iid,  # Internal ID (project-scoped)
            "id": mr.id,  # Global ID
            "title": mr.title,
            "description": mr.description or "",
            "state": mr.state,
            "draft": mr.draft if hasattr(mr, "draft") else False,
            "merged_at": mr.merged_at if hasattr(mr, "merged_at") else None,
            "source_branch": mr.source_branch,
            "target_branch": mr.target_branch,
            "labels": mr.labels if hasattr(mr, "labels") else [],
            "assignees": [
                assignee.get("username", "unknown")
                for assignee in (mr.assignees if hasattr(mr, "assignees") else [])
            ],
            "author": mr.author.get("username", "unknown") if hasattr(mr, "author") else "unknown",
            "created_at": mr.created_at,
            "updated_at": mr.updated_at,
            "web_url": mr.web_url,
            "merge_status": mr.merge_status if hasattr(mr, "merge_status") else "unknown",
            "has_conflicts": mr.has_conflicts if hasattr(mr, "has_conflicts") else False,
            "changes_count": mr.changes_count if hasattr(mr, "changes_count") else "unknown",
            "upvotes": mr.upvotes if hasattr(mr, "upvotes") else 0,
            "downvotes": mr.downvotes if hasattr(mr, "downvotes") else 0,
        }

    def _format_pipeline(self, pipeline: Any) -> Dict[str, Any]:
        """Format GitLab pipeline to dict."""
        return {
            "id": pipeline.id,
            "iid": pipeline.iid if hasattr(pipeline, "iid") else pipeline.id,
            "status": pipeline.status,
            "ref": pipeline.ref,
            "sha": pipeline.sha[:7] if hasattr(pipeline, "sha") and pipeline.sha else "unknown",
            "created_at": pipeline.created_at if hasattr(pipeline, "created_at") else None,
            "updated_at": pipeline.updated_at if hasattr(pipeline, "updated_at") else None,
            "started_at": pipeline.started_at if hasattr(pipeline, "started_at") else None,
            "finished_at": pipeline.finished_at if hasattr(pipeline, "finished_at") else None,
            "duration": pipeline.duration if hasattr(pipeline, "duration") else None,
            "web_url": pipeline.web_url,
            "user": (
                pipeline.user.get("username", "unknown")
                if hasattr(pipeline, "user") and pipeline.user
                else "unknown"
            ),
        }

    def _format_pipeline_job(self, job: Any) -> Dict[str, Any]:
        """Format GitLab pipeline job to dict."""
        return {
            "id": job.id,
            "name": job.name,
            "status": job.status,
            "stage": job.stage,
            "ref": job.ref if hasattr(job, "ref") else "unknown",
            "created_at": job.created_at if hasattr(job, "created_at") else None,
            "started_at": job.started_at if hasattr(job, "started_at") else None,
            "finished_at": job.finished_at if hasattr(job, "finished_at") else None,
            "duration": job.duration if hasattr(job, "duration") else None,
            "web_url": job.web_url if hasattr(job, "web_url") else None,
            "user": (
                job.user.get("username", "unknown")
                if hasattr(job, "user") and job.user
                else "unknown"
            ),
        }
