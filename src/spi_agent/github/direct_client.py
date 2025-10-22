"""Direct GitHub API client for fast status gathering without AI prompts."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from github import Auth, Github, GithubException
from urllib3.util.retry import Retry

from spi_agent.config import AgentConfig

logger = logging.getLogger(__name__)


class GitHubDirectClient:
    """
    Direct async client for GitHub API calls.

    Provides fast, reliable data gathering without AI prompts.
    Uses PyGithub library with async/await for parallel API calls.
    """

    def __init__(self, config: AgentConfig):
        """
        Initialize GitHub direct client with larger connection pool for parallel requests.

        Args:
            config: Agent configuration with GitHub settings
        """
        self.config = config

        # Configure retry strategy for transient failures
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )

        # Initialize GitHub client with larger pool size for parallel requests
        if config.github_token:
            auth = Auth.Token(config.github_token)
            self.github = Github(auth=auth, pool_size=50, retry=retry)
            logger.info("Authenticated to GitHub with token")
        else:
            self.github = Github(pool_size=50, retry=retry)
            logger.info("Using GitHub without authentication (rate limited)")

    async def get_all_status(
        self,
        services: List[str]
    ) -> Dict[str, Any]:
        """
        Get GitHub status for all services in parallel.

        Args:
            services: List of service names

        Returns:
            Dictionary with structure matching StatusResponse model
        """
        # Create tasks for all services
        tasks = [
            self._get_service_status(service)
            for service in services
        ]

        # Run all service queries in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build response structure
        services_data = {}
        for service, result in zip(services, results):
            if isinstance(result, Exception):
                logger.error(f"Error getting status for {service}: {result}")
                services_data[service] = {"error": str(result)}
            else:
                services_data[service] = result

        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "services": services_data
        }

    async def _get_service_status(
        self,
        service: str
    ) -> Dict[str, Any]:
        """
        Get status for a single service.

        Args:
            service: Service name (e.g., "partition")

        Returns:
            Service status dictionary
        """
        repo_name = self.config.get_repo_full_name(service)

        try:
            # Fetch repo info, issues, PRs, and workflows in parallel
            repo_task = self._get_repo_info(repo_name)
            issues_task = self._get_issues(repo_name)
            prs_task = self._get_pull_requests(repo_name)
            workflows_task = self._get_workflow_runs(repo_name)

            repo, issues, prs, workflows = await asyncio.gather(
                repo_task, issues_task, prs_task, workflows_task
            )

            return {
                "repo": repo,
                "issues": issues,
                "pull_requests": prs,
                "workflows": workflows
            }

        except GithubException as e:
            logger.error(f"GitHub API error for {service}: {e}")
            return {"error": f"GitHub API error: {str(e)}"}

    async def _get_repo_info(self, repo_name: str) -> Dict[str, Any]:
        """
        Get repository information.

        Args:
            repo_name: Full repository name (org/repo)

        Returns:
            Repository info dictionary
        """
        try:
            repo = await asyncio.to_thread(self.github.get_repo, repo_name)

            return {
                "exists": True,
                "name": repo.name,
                "full_name": repo.full_name,
                "updated_at": repo.updated_at.isoformat() + "Z",
                "html_url": repo.html_url,
                "default_branch": repo.default_branch
            }

        except GithubException as e:
            if e.status == 404:
                return {"exists": False}
            raise

    async def _get_issues(self, repo_name: str) -> Dict[str, Any]:
        """
        Get open issues from repository.

        Args:
            repo_name: Full repository name (org/repo)

        Returns:
            Issues data dictionary
        """
        try:
            repo = await asyncio.to_thread(self.github.get_repo, repo_name)

            # Get open issues (excluding PRs)
            issues = await asyncio.to_thread(
                lambda: list(repo.get_issues(state="open"))[:30]
            )

            # Filter out pull requests
            issues = [issue for issue in issues if not issue.pull_request]

            # Take only first 10 after filtering
            issues = issues[:10]

            return {
                "count": len(issues),
                "items": [self._format_issue(issue) for issue in issues]
            }

        except GithubException as e:
            # Don't warn for 404s (repo doesn't exist) - expected condition
            if e.status == 404:
                logger.debug(f"Repository {repo_name} not found")
            else:
                logger.warning(f"Error fetching issues for {repo_name}: {e}")
            return {"count": 0, "items": []}

    async def _get_pull_requests(self, repo_name: str) -> Dict[str, Any]:
        """
        Get open pull requests from repository.

        Args:
            repo_name: Full repository name (org/repo)

        Returns:
            Pull requests data dictionary
        """
        try:
            repo = await asyncio.to_thread(self.github.get_repo, repo_name)

            # Get open pull requests
            prs = await asyncio.to_thread(
                lambda: list(repo.get_pulls(state="open"))[:10]
            )

            return {
                "count": len(prs),
                "items": [self._format_pull_request(pr) for pr in prs]
            }

        except GithubException as e:
            # Don't warn for 404s (repo doesn't exist) - expected condition
            if e.status == 404:
                logger.debug(f"Repository {repo_name} not found")
            else:
                logger.warning(f"Error fetching PRs for {repo_name}: {e}")
            return {"count": 0, "items": []}

    async def _get_workflow_runs(self, repo_name: str) -> Dict[str, Any]:
        """
        Get recent workflow runs from repository.

        Args:
            repo_name: Full repository name (org/repo)

        Returns:
            Workflow runs data dictionary
        """
        try:
            repo = await asyncio.to_thread(self.github.get_repo, repo_name)

            # Get recent workflow runs
            runs = await asyncio.to_thread(
                lambda: list(repo.get_workflow_runs())[:10]
            )

            return {
                "recent": [self._format_workflow_run(run) for run in runs]
            }

        except GithubException as e:
            # Don't warn for 404s (repo doesn't exist) - expected condition
            if e.status == 404:
                logger.debug(f"Repository {repo_name} not found")
            else:
                logger.warning(f"Error fetching workflow runs for {repo_name}: {e}")
            return {"recent": []}

    def _format_issue(self, issue: Any) -> Dict[str, Any]:
        """Format GitHub issue for JSON serialization."""
        return {
            "number": issue.number,
            "title": issue.title,
            "state": issue.state,
            "author": issue.user.login if issue.user else "unknown",
            "labels": [label.name for label in issue.labels],
            "assignees": [assignee.login for assignee in issue.assignees],
            "created_at": issue.created_at.isoformat() + "Z",
            "updated_at": issue.updated_at.isoformat() + "Z",
            "html_url": issue.html_url,
            "comments_count": issue.comments
        }

    def _format_pull_request(self, pr: Any) -> Dict[str, Any]:
        """Format GitHub pull request for JSON serialization."""
        # Detect if this is a release PR
        is_release = any(
            keyword in pr.title.lower()
            for keyword in ["release", "version", "bump"]
        )

        # Get review status
        approved_count = 0
        changes_requested = False
        try:
            reviews = list(pr.get_reviews())
            # Get latest review from each reviewer
            latest_reviews = {}
            for review in reviews:
                reviewer = review.user.login if review.user else "unknown"
                latest_reviews[reviewer] = review.state

            # Count approvals and check for changes requested
            for state in latest_reviews.values():
                if state == "APPROVED":
                    approved_count += 1
                elif state == "CHANGES_REQUESTED":
                    changes_requested = True
        except:
            pass  # If review fetch fails, continue without review data

        return {
            "number": pr.number,
            "title": pr.title,
            "state": pr.state,
            "is_draft": pr.draft,
            "is_release": is_release,
            "author": pr.user.login if pr.user else "unknown",
            "headRefName": pr.head.ref,
            "headRefOid": pr.head.sha,
            "mergeable": pr.mergeable,  # True, False, or None (computing)
            "mergeable_state": pr.mergeable_state,  # clean, unstable, blocked, dirty, etc.
            "approved_count": approved_count,
            "changes_requested": changes_requested,
            "created_at": pr.created_at.isoformat() + "Z",
            "updated_at": pr.updated_at.isoformat() + "Z",
            "html_url": pr.html_url
        }

    def _format_workflow_run(self, run: Any) -> Dict[str, Any]:
        """Format GitHub workflow run for JSON serialization."""
        return {
            "id": run.id,
            "name": run.name,
            "status": run.status,
            "conclusion": run.conclusion,
            "event": run.event,
            "head_branch": run.head_branch,
            "headSha": run.head_sha,
            "created_at": run.created_at.isoformat() + "Z",
            "updated_at": run.updated_at.isoformat() + "Z",
            "run_started_at": run.run_started_at.isoformat() + "Z" if run.run_started_at else None,
            "html_url": run.html_url
        }
