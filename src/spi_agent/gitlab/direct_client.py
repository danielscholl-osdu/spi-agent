"""Direct GitLab API client for fast status gathering without AI prompts."""

import asyncio
import logging
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import gitlab
from gitlab.exceptions import GitlabError

from spi_agent.config import AgentConfig

logger = logging.getLogger(__name__)


class GitLabDirectClient:
    """
    Direct async client for GitLab API calls.

    Provides fast, reliable data gathering without AI prompts.
    Uses python-gitlab library with async/await for parallel API calls.
    """

    def __init__(self, config: AgentConfig):
        """
        Initialize GitLab direct client.

        Args:
            config: Agent configuration with GitLab settings
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
            try:
                self.gitlab.auth()
                logger.info(f"Authenticated to {gitlab_url}")
            except GitlabError as e:
                logger.warning(f"GitLab authentication warning: {e}")
        else:
            # Try without authentication (public projects only)
            self.gitlab = gitlab.Gitlab(url=gitlab_url)
            logger.info(f"Using {gitlab_url} without authentication")

    async def get_all_status(
        self,
        services: List[str],
        providers: List[str]
    ) -> Dict[str, Any]:
        """
        Get GitLab status for all services in parallel.

        Args:
            services: List of service names
            providers: List of provider labels to filter by

        Returns:
            Dictionary with structure matching StatusResponse model
        """
        # Create tasks for all services
        tasks = [
            self._get_service_status(service, providers)
            for service in services
        ]

        # Run all service queries in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build response structure
        projects = {}
        for service, result in zip(services, results):
            if isinstance(result, Exception):
                logger.error(f"Error getting status for {service}: {result}")
                projects[service] = {"error": str(result)}
            else:
                projects[service] = result

        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "projects": projects
        }

    async def _get_service_status(
        self,
        service: str,
        providers: List[str]
    ) -> Dict[str, Any]:
        """
        Get status for a single service.

        Args:
            service: Service name (e.g., "partition")
            providers: Provider labels to filter by

        Returns:
            Service status dictionary
        """
        # Get upstream GitLab URL from GitHub variable
        upstream_url = await self._get_upstream_url(service)
        if not upstream_url:
            return {"error": "No upstream URL found"}

        # Parse GitLab project path from URL
        project_path = self._parse_project_path(upstream_url)
        if not project_path:
            return {"error": f"Invalid upstream URL: {upstream_url}"}

        try:
            # Get GitLab project
            project = await asyncio.to_thread(
                self.gitlab.projects.get, project_path
            )

            # Fetch issues and MRs in parallel
            issues_task = self._get_issues(project, providers)
            mrs_task = self._get_merge_requests(project, providers)

            issues_data, mrs_data = await asyncio.gather(issues_task, mrs_task)

            return {
                "upstream_url": upstream_url,
                "issues": issues_data,
                "merge_requests": mrs_data
            }

        except GitlabError as e:
            logger.error(f"GitLab API error for {service}: {e}")
            return {"error": f"GitLab API error: {str(e)}"}

    async def _get_upstream_url(self, service: str) -> Optional[str]:
        """
        Get upstream GitLab URL from GitHub repository variable.

        Args:
            service: Service name

        Returns:
            Upstream GitLab URL or None
        """
        repo = f"{self.config.organization}/{service}"
        cmd = [
            "gh", "api",
            f"repos/{repo}/actions/variables/UPSTREAM_REPO_URL",
            "--jq", ".value"
        ]

        try:
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await result.communicate()

            if result.returncode == 0:
                url = stdout.decode().strip()
                # Remove .git suffix if present
                return url.rstrip('.git') if url else None

        except Exception as e:
            logger.error(f"Error getting upstream URL for {service}: {e}")

        return None

    def _parse_project_path(self, upstream_url: str) -> Optional[str]:
        """
        Parse GitLab project path from upstream URL.

        Args:
            upstream_url: Full GitLab URL

        Returns:
            Project path (e.g., "osdu/platform/system/partition")
        """
        try:
            parsed = urlparse(upstream_url)
            # Remove leading slash and .git suffix
            path = parsed.path.lstrip('/').rstrip('.git')
            return path
        except Exception as e:
            logger.error(f"Error parsing project path from {upstream_url}: {e}")
            return None

    async def _get_issues(
        self,
        project: Any,
        providers: List[str]
    ) -> Dict[str, Any]:
        """
        Get issues filtered by provider labels.

        Args:
            project: GitLab project object
            providers: Provider labels to filter by

        Returns:
            Issues data dictionary
        """
        all_issues = []
        seen_iids = set()

        # Query for each provider label
        for provider in providers:
            try:
                # Try capitalized version first (GitLab labels are case-sensitive)
                for label_variant in [provider.capitalize(), provider, provider.upper()]:
                    issues = await asyncio.to_thread(
                        project.issues.list,
                        labels=[label_variant],
                        state="opened",
                        per_page=10
                    )

                    # Add issues, avoiding duplicates
                    for issue in issues:
                        if issue.iid not in seen_iids:
                            seen_iids.add(issue.iid)
                            all_issues.append(self._format_issue(issue))

                    if issues:  # Found issues with this label variant
                        break

            except GitlabError as e:
                logger.warning(f"Error fetching issues for label {provider}: {e}")

        return {
            "count": len(all_issues),
            "items": all_issues
        }

    async def _get_merge_requests(
        self,
        project: Any,
        providers: List[str]
    ) -> Dict[str, Any]:
        """
        Get merge requests filtered by provider labels, with pipelines.

        Args:
            project: GitLab project object
            providers: Provider labels to filter by

        Returns:
            Merge requests data dictionary
        """
        all_mrs = []
        seen_iids = set()

        # Query for each provider label
        for provider in providers:
            try:
                # Try capitalized version first
                for label_variant in [provider.capitalize(), provider, provider.upper()]:
                    mrs = await asyncio.to_thread(
                        project.mergerequests.list,
                        labels=[label_variant],
                        state="opened",
                        per_page=10
                    )

                    # Add MRs, avoiding duplicates
                    for mr in mrs:
                        if mr.iid not in seen_iids:
                            seen_iids.add(mr.iid)
                            mr_data = self._format_merge_request(mr)

                            # Fetch pipelines for this MR
                            mr_data["pipelines"] = await self._get_mr_pipelines(
                                project, mr
                            )

                            all_mrs.append(mr_data)

                    if mrs:  # Found MRs with this label variant
                        break

            except GitlabError as e:
                logger.warning(f"Error fetching MRs for label {provider}: {e}")

        return {
            "count": len(all_mrs),
            "items": all_mrs
        }

    async def _get_mr_pipelines(
        self,
        project: Any,
        mr: Any
    ) -> List[Dict[str, Any]]:
        """
        Get pipelines for a merge request.

        Args:
            project: GitLab project object
            mr: Merge request object

        Returns:
            List of pipeline dictionaries
        """
        try:
            # Get pipelines for the MR's source branch
            pipelines = await asyncio.to_thread(
                project.pipelines.list,
                ref=mr.source_branch,
                per_page=10,
                order_by="updated_at",
                sort="desc"
            )

            pipeline_data = []
            for pipeline in pipelines[:5]:  # Limit to 5 most recent
                p_data = self._format_pipeline(pipeline)

                # If pipeline failed, get jobs
                if pipeline.status == "failed":
                    p_data["jobs"] = await self._get_pipeline_jobs(
                        project, pipeline
                    )

                pipeline_data.append(p_data)

            return pipeline_data

        except GitlabError as e:
            logger.warning(f"Error fetching pipelines for MR !{mr.iid}: {e}")
            return []

    async def _get_pipeline_jobs(
        self,
        project: Any,
        pipeline: Any
    ) -> List[Dict[str, Any]]:
        """
        Get jobs for a failed pipeline, including downstream jobs.

        Args:
            project: GitLab project object
            pipeline: Pipeline object

        Returns:
            List of job dictionaries (parent + downstream)
        """
        try:
            # Get parent pipeline jobs
            jobs = await asyncio.to_thread(
                pipeline.jobs.list,
                per_page=100
            )

            job_data = [self._format_job(job) for job in jobs]

            # Check if there's a trigger job
            has_trigger = any(
                job.get("name", "").startswith("trigger-")
                for job in job_data
            )

            if has_trigger:
                # Get downstream pipeline jobs
                downstream_jobs = await self._get_downstream_jobs(
                    project, pipeline
                )
                job_data.extend(downstream_jobs)

            return job_data

        except GitlabError as e:
            logger.warning(f"Error fetching jobs for pipeline {pipeline.id}: {e}")
            return []

    async def _get_downstream_jobs(
        self,
        project: Any,
        parent_pipeline: Any
    ) -> List[Dict[str, Any]]:
        """
        Get jobs from downstream pipeline (triggered by parent).

        Args:
            project: GitLab project object
            parent_pipeline: Parent pipeline object

        Returns:
            List of downstream job dictionaries
        """
        try:
            # Find downstream pipelines by matching SHA
            downstream_pipelines = await asyncio.to_thread(
                project.pipelines.list,
                sha=parent_pipeline.sha,
                source="pipeline",
                per_page=5
            )

            if not downstream_pipelines:
                return []

            # Get jobs from the first downstream pipeline
            downstream = downstream_pipelines[0]
            jobs = await asyncio.to_thread(
                downstream.jobs.list,
                per_page=100
            )

            # Format jobs and mark as downstream
            job_data = []
            for job in jobs:
                j_data = self._format_job(job)
                j_data["is_downstream"] = True
                j_data["downstream_pipeline_id"] = downstream.id
                job_data.append(j_data)

            return job_data

        except GitlabError as e:
            logger.warning(f"Error fetching downstream jobs: {e}")
            return []

    def _format_issue(self, issue: Any) -> Dict[str, Any]:
        """Format GitLab issue to dictionary."""
        return {
            "iid": issue.iid,
            "title": issue.title,
            "labels": issue.labels if hasattr(issue, "labels") else [],
            "state": issue.state,
            "assignees": [
                a.get("username", "unknown")
                for a in (issue.assignees if hasattr(issue, "assignees") else [])
            ],
            "author": (
                issue.author.get("username", "unknown")
                if hasattr(issue, "author") and issue.author
                else "unknown"
            ),
            "created_at": issue.created_at,
            "web_url": issue.web_url,
        }

    def _format_merge_request(self, mr: Any) -> Dict[str, Any]:
        """Format GitLab merge request to dictionary."""
        return {
            "iid": mr.iid,
            "title": mr.title,
            "labels": mr.labels if hasattr(mr, "labels") else [],
            "state": mr.state,
            "draft": mr.draft if hasattr(mr, "draft") else False,
            "source_branch": mr.source_branch,
            "target_branch": mr.target_branch,
            "author": (
                mr.author.get("username", "unknown")
                if hasattr(mr, "author") and mr.author
                else "unknown"
            ),
            "created_at": mr.created_at,
            "web_url": mr.web_url,
        }

    def _format_pipeline(self, pipeline: Any) -> Dict[str, Any]:
        """Format GitLab pipeline to dictionary."""
        return {
            "id": pipeline.id,
            "status": pipeline.status,
            "ref": pipeline.ref,
            "sha": pipeline.sha if hasattr(pipeline, "sha") else "unknown",
            "created_at": pipeline.created_at if hasattr(pipeline, "created_at") else None,
            "duration": pipeline.duration if hasattr(pipeline, "duration") else None,
            "web_url": pipeline.web_url,
        }

    def _format_job(self, job: Any) -> Dict[str, Any]:
        """Format GitLab job to dictionary."""
        return {
            "id": job.id,
            "name": job.name,
            "stage": job.stage,
            "status": job.status,
            "duration": job.duration if hasattr(job, "duration") else None,
            "web_url": job.web_url if hasattr(job, "web_url") else None,
        }
