"""Direct API client for fork operations without AI prompts."""

import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from github import Auth, Github, GithubException
from urllib3.util.retry import Retry

from spi_agent.config import AgentConfig

logger = logging.getLogger(__name__)

# Service to upstream repo mapping
SERVICE_UPSTREAM_REPOS = {
    "partition": "https://community.opengroup.org/osdu/platform/system/partition",
    "entitlements": "https://community.opengroup.org/osdu/platform/security-and-compliance/entitlements",
    "legal": "https://community.opengroup.org/osdu/platform/security-and-compliance/legal",
    "schema": "https://community.opengroup.org/osdu/platform/system/schema-service",
    "file": "https://community.opengroup.org/osdu/platform/system/file",
    "storage": "https://community.opengroup.org/osdu/platform/system/storage",
    "indexer": "https://community.opengroup.org/osdu/platform/system/indexer-service",
    "indexer-queue": "https://community.opengroup.org/osdu/platform/system/indexer-queue",
    "search": "https://community.opengroup.org/osdu/platform/system/search-service",
    "workflow": "https://community.opengroup.org/osdu/platform/data-flow/ingestion/ingestion-workflow",
}

TEMPLATE_REPO = "azure/osdu-spi"


class ForkDirectClient:
    """
    Direct client for fork operations.

    Provides fast, reliable repository forking without AI prompts.
    """

    def __init__(self, config: AgentConfig, repos_dir: Optional[Path] = None):
        """
        Initialize fork direct client.

        Args:
            config: Agent configuration with GitHub settings
            repos_dir: Directory for cloned repositories (defaults to ./repos)
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

        # Set repos directory
        self.repos_dir = repos_dir or Path.cwd() / "repos"
        self.repos_dir.mkdir(exist_ok=True)

    async def fork_service(
        self, service: str, branch: str = "main", status_callback: Optional[Callable[[str, str, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Fork a single service repository with intelligent edge case handling.

        **Edge Cases Handled:**
        1. Repository exists in GitHub + exists locally -> Pull latest changes
        2. Repository exists in GitHub + missing locally -> Clone from GitHub
        3. Repository doesn't exist -> Create from template, run workflows, clone

        Args:
            service: Service name (e.g., "partition")
            branch: Branch to use (default: "main")
            status_callback: Optional callback(service, status, details) for live updates

        Returns:
            Result dictionary with status and details
        """
        repo_name = self.config.get_repo_full_name(service)
        upstream_url = SERVICE_UPSTREAM_REPOS.get(service)

        def update_status(status: str, details: str):
            """Helper to call status callback if provided."""
            if status_callback:
                status_callback(service, status, details)

        if not upstream_url:
            update_status("error", f"Unknown service: {service}")
            return {
                "service": service,
                "status": "error",
                "message": f"Unknown service: {service}",
            }

        logger.info(f"Starting fork for {service} (branch: {branch})")
        update_status("running", "Checking if repository exists...")

        try:
            # Step 1: Check if repo already exists
            repo_exists = await self._check_repo_exists(repo_name)

            if repo_exists:
                logger.info(f"Repository {repo_name} already exists - skipping creation")

                # Check if local repo exists
                local_dir = self.repos_dir / service
                if local_dir.exists():
                    update_status("running", "Repository exists - syncing latest changes...")
                    await self._sync_local_repo(service, repo_name)
                    skip_message = "Repository exists - synced latest changes"
                else:
                    update_status("running", "Repository exists - cloning locally...")
                    await self._sync_local_repo(service, repo_name)
                    skip_message = "Repository exists - cloned locally"

                return {
                    "service": service,
                    "status": "skipped",
                    "message": skip_message,
                    "repo_url": f"https://github.com/{repo_name}",
                }

            # Step 2: Create repository from template
            logger.info(f"Creating {repo_name} from template {TEMPLATE_REPO}")
            update_status("running", "Creating repository from template...")
            create_result = await self._create_from_template(
                service, repo_name, branch
            )

            if not create_result["success"]:
                update_status("error", f"Failed to create: {create_result['error']}")
                return {
                    "service": service,
                    "status": "error",
                    "message": f"Failed to create repository: {create_result['error']}",
                }

            # Step 3: Wait for "Initialize Fork" workflow
            logger.info(f"Waiting for Initialize Fork workflow on {repo_name}")
            update_status("waiting", "Waiting for Initialize Fork workflow...")
            init_fork_result = await self._wait_for_workflow(
                repo_name, "Initialize Fork", timeout=300
            )

            if not init_fork_result["success"]:
                update_status("error", f"Initialize Fork failed: {init_fork_result['error']}")
                return {
                    "service": service,
                    "status": "error",
                    "message": f"Initialize Fork workflow failed: {init_fork_result['error']}",
                }

            # Step 4: Find and comment on initialization issue
            logger.info(f"Finding initialization issue in {repo_name}")
            update_status("running", "Commenting on initialization issue...")
            issue_result = await self._comment_on_init_issue(
                repo_name, upstream_url
            )

            if not issue_result["success"]:
                logger.warning(f"Could not comment on init issue: {issue_result['error']}")
                # Non-fatal - continue

            # Step 5: Wait for "Initialize Complete" workflow
            logger.info(f"Waiting for Initialize Complete workflow on {repo_name}")
            update_status("waiting", "Waiting for Initialize Complete workflow...")
            init_complete_result = await self._wait_for_workflow(
                repo_name, "Initialize Complete", timeout=600
            )

            if not init_complete_result["success"]:
                update_status("error", f"Initialize Complete failed: {init_complete_result['error']}")
                return {
                    "service": service,
                    "status": "error",
                    "message": f"Initialize Complete workflow failed: {init_complete_result['error']}",
                }

            # Step 6: Clone/pull repository locally
            update_status("running", "Cloning repository locally...")
            await self._sync_local_repo(service, repo_name)

            logger.info(f"Successfully forked {service}")
            return {
                "service": service,
                "status": "success",
                "message": "Repository initialized successfully",
                "repo_url": f"https://github.com/{repo_name}",
            }

        except Exception as e:
            logger.error(f"Error forking {service}: {e}", exc_info=True)
            error_msg = f"Unexpected error: {str(e)}"
            update_status("error", error_msg)
            return {
                "service": service,
                "status": "error",
                "message": error_msg,
            }

    async def _check_repo_exists(self, repo_name: str) -> bool:
        """Check if a repository exists."""
        try:
            await asyncio.to_thread(self.github.get_repo, repo_name)
            return True
        except GithubException as e:
            if e.status == 404:
                return False
            raise

    async def _create_from_template(
        self, service: str, repo_name: str, branch: str
    ) -> Dict[str, Any]:
        """Create repository from template using gh CLI."""
        try:
            # For main branch, create directly from template
            if branch == "main":
                result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "gh",
                        "repo",
                        "create",
                        repo_name,
                        "--template",
                        TEMPLATE_REPO,
                        "--clone",
                        "--public",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=self.repos_dir,
                )

                if result.returncode != 0:
                    return {
                        "success": False,
                        "error": result.stderr or result.stdout,
                    }

                return {"success": True}

            # For non-main branch, clone template first, switch branch, then create repo
            else:
                # Clone template to temporary location
                temp_dir = self.repos_dir / service
                if temp_dir.exists():
                    # Remove existing directory
                    await asyncio.to_thread(
                        subprocess.run,
                        ["rm", "-rf", str(temp_dir)],
                        timeout=30,
                    )

                # Clone template
                result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "git",
                        "clone",
                        f"https://github.com/{TEMPLATE_REPO}",
                        service,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=self.repos_dir,
                )

                if result.returncode != 0:
                    return {
                        "success": False,
                        "error": f"Failed to clone template: {result.stderr}",
                    }

                # Checkout the specified branch from template
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "checkout", branch],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=temp_dir,
                )

                if result.returncode != 0:
                    return {
                        "success": False,
                        "error": f"Failed to checkout branch '{branch}': {result.stderr}",
                    }

                # Rename branch to 'main' for the new repo
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "branch", "-M", "main"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=temp_dir,
                )

                if result.returncode != 0:
                    return {
                        "success": False,
                        "error": f"Failed to rename branch to main: {result.stderr}",
                    }

                # Remove template's origin remote before creating new repo
                # (git clone created origin -> azure/osdu-spi, but gh repo create needs to add origin -> org/service)
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "remote", "remove", "origin"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=temp_dir,
                )

                if result.returncode != 0:
                    logger.warning(f"Could not remove origin remote: {result.stderr}")

                # Create GitHub repo from local directory
                result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "gh",
                        "repo",
                        "create",
                        repo_name,
                        "--source",
                        ".",
                        "--public",
                        "--push",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=temp_dir,
                )

                if result.returncode != 0:
                    return {
                        "success": False,
                        "error": result.stderr or result.stdout,
                    }

                return {"success": True}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _wait_for_workflow(
        self, repo_name: str, workflow_name: str, timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Wait for a workflow to complete successfully.

        Args:
            repo_name: Full repository name (org/repo)
            workflow_name: Name of workflow to wait for
            timeout: Maximum seconds to wait

        Returns:
            Result dictionary with success status
        """
        start_time = datetime.now()
        poll_interval = 10  # seconds

        try:
            repo = await asyncio.to_thread(self.github.get_repo, repo_name)

            while (datetime.now() - start_time).seconds < timeout:
                # Get recent workflow runs
                def get_runs():
                    runs_paginated = repo.get_workflow_runs()
                    runs = []
                    count = 0
                    for run in runs_paginated:
                        runs.append(run)
                        count += 1
                        if count >= 10:
                            break
                    return runs

                runs = await asyncio.to_thread(get_runs)

                # Find matching workflow
                for run in runs:
                    if workflow_name.lower() in run.name.lower():
                        logger.debug(
                            f"Found {workflow_name} run: status={run.status}, conclusion={run.conclusion}"
                        )

                        if run.status == "completed":
                            if run.conclusion == "success":
                                return {
                                    "success": True,
                                    "run_id": run.id,
                                    "conclusion": run.conclusion,
                                }
                            else:
                                return {
                                    "success": False,
                                    "error": f"Workflow failed with conclusion: {run.conclusion}",
                                    "run_id": run.id,
                                }

                # Wait before polling again
                logger.debug(f"Waiting {poll_interval}s for {workflow_name}...")
                await asyncio.sleep(poll_interval)

            return {
                "success": False,
                "error": f"Workflow '{workflow_name}' did not complete within {timeout}s",
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _comment_on_init_issue(
        self, repo_name: str, upstream_url: str
    ) -> Dict[str, Any]:
        """Find initialization issue and comment with upstream URL."""
        try:
            repo = await asyncio.to_thread(self.github.get_repo, repo_name)

            # Get open issues
            issues = await asyncio.to_thread(
                lambda: list(repo.get_issues(state="open"))[:10]
            )

            # Find "Repository Initialization Required" issue
            init_issue = None
            for issue in issues:
                if "initialization required" in issue.title.lower():
                    init_issue = issue
                    break

            if not init_issue:
                return {
                    "success": False,
                    "error": "Initialization issue not found",
                }

            # Add comment with upstream URL
            await asyncio.to_thread(init_issue.create_comment, upstream_url)

            logger.info(
                f"Commented on issue #{init_issue.number} with upstream URL"
            )
            return {"success": True, "issue_number": init_issue.number}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _sync_local_repo(self, service: str, repo_name: str) -> None:
        """Clone or pull repository locally."""
        local_dir = self.repos_dir / service

        try:
            if local_dir.exists():
                # Pull latest changes
                logger.info(f"Pulling latest changes for {service}")
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "pull"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=local_dir,
                )

                if result.returncode != 0:
                    logger.warning(
                        f"Failed to pull {service}: {result.stderr}"
                    )
            else:
                # Clone repository
                logger.info(f"Cloning {service} to {local_dir}")
                result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "gh",
                        "repo",
                        "clone",
                        repo_name,
                        service,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=self.repos_dir,
                )

                if result.returncode != 0:
                    logger.warning(
                        f"Failed to clone {service}: {result.stderr}"
                    )

        except Exception as e:
            logger.warning(f"Error syncing local repo for {service}: {e}")
