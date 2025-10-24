"""GitHub-to-GitLab send workflow for Issues and Pull Requests.

This module provides functionality to transfer GitHub Issues and Pull Requests
to corresponding GitLab projects. For PRs, it uses a git-based workflow that:
1. Creates a new branch from GitLab upstream
2. Cherry-picks commits from the GitHub PR
3. Pushes to GitLab and creates a Merge Request

This enables seamless contribution from GitHub forks back to canonical
GitLab upstream repositories (the OSDU workflow).
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from github import GithubException

from spi_agent.config import AgentConfig
from spi_agent.git.tools import GitRepositoryTools
from spi_agent.github.issues import IssueTools
from spi_agent.github.pull_requests import PullRequestTools
from spi_agent.gitlab.issues import IssueTools as GitLabIssueTools
from spi_agent.gitlab.merge_requests import MergeRequestTools

logger = logging.getLogger(__name__)


def extract_pr_data(service: str, pr_number: int, config: AgentConfig) -> Optional[Dict]:
    """
    Extract pull request data from GitHub.

    Args:
        service: Service name (e.g., 'partition')
        pr_number: Pull request number
        config: Agent configuration

    Returns:
        Dictionary with PR data, or None if PR not found
    """
    try:
        pr_tools = PullRequestTools(config)
        result = pr_tools.get_pull_request(service, pr_number)

        # Check if PR was not found (specific error pattern from GitHub API)
        if result.startswith(f"Pull request #{pr_number} not found"):
            logger.warning(f"PR #{pr_number} not found in {service}")
            return None

        # Parse the formatted string to extract structured data
        # The result is a formatted string, we need to extract fields
        pr_data = {}

        # Extract title
        title_match = re.search(r"Title: (.+)", result)
        if title_match:
            pr_data["title"] = title_match.group(1).strip()

        # Extract state
        state_match = re.search(r"State: (\w+)", result)
        if state_match:
            pr_data["state"] = state_match.group(1).strip()

        # Extract author
        author_match = re.search(r"Author: (.+)", result)
        if author_match:
            pr_data["author"] = author_match.group(1).strip()

        # Extract branches
        branches_match = re.search(r"Base: (\S+) ← Head: (\S+)", result)
        if branches_match:
            pr_data["base_ref"] = branches_match.group(1).strip()
            pr_data["head_ref"] = branches_match.group(2).strip()

        # Extract description (everything after "Description:" up to "URL:")
        desc_match = re.search(r"Description:\s*\n(.+?)(?=\nURL:)", result, re.DOTALL)
        if desc_match:
            pr_data["body"] = desc_match.group(1).strip()
        else:
            # Try simpler match
            desc_match = re.search(r"Description:\s*\n(.+)", result, re.DOTALL)
            if desc_match:
                pr_data["body"] = desc_match.group(1).strip()
            else:
                pr_data["body"] = ""

        # Extract URL
        url_match = re.search(r"URL: (.+)", result)
        if url_match:
            pr_data["html_url"] = url_match.group(1).strip()

        # Store PR number
        pr_data["number"] = pr_number

        # Extract labels if present
        labels_match = re.search(r"Labels: (.+)", result)
        if labels_match:
            labels_str = labels_match.group(1).strip()
            pr_data["labels"] = [label.strip() for label in labels_str.split(",")]
        else:
            pr_data["labels"] = []

        logger.info(f"Successfully extracted PR #{pr_number} data from {service}")
        return pr_data

    except Exception as e:
        logger.error(f"Error extracting PR data: {e}", exc_info=True)
        return None


def extract_issue_data(service: str, issue_number: int, config: AgentConfig) -> Optional[Dict]:
    """
    Extract issue data from GitHub.

    Args:
        service: Service name (e.g., 'partition')
        issue_number: Issue number
        config: Agent configuration

    Returns:
        Dictionary with issue data, or None if issue not found
    """
    try:
        issue_tools = IssueTools(config)
        result = issue_tools.get_issue(service, issue_number)

        # Check if issue was not found (specific error pattern from GitHub API)
        if result.startswith(f"Issue #{issue_number} not found"):
            logger.warning(f"Issue #{issue_number} not found in {service}")
            return None

        # Parse the formatted string to extract structured data
        issue_data = {}

        # Extract title
        title_match = re.search(r"Title: (.+)", result)
        if title_match:
            issue_data["title"] = title_match.group(1).strip()

        # Extract state
        state_match = re.search(r"State: (\w+)", result)
        if state_match:
            issue_data["state"] = state_match.group(1).strip()

        # Extract author
        author_match = re.search(r"Author: (.+)", result)
        if author_match:
            issue_data["author"] = author_match.group(1).strip()

        # Extract description
        desc_match = re.search(r"Description:\s*\n(.+?)(?=\nURL:)", result, re.DOTALL)
        if desc_match:
            issue_data["body"] = desc_match.group(1).strip()
        else:
            # Try simpler match
            desc_match = re.search(r"Description:\s*\n(.+)", result, re.DOTALL)
            if desc_match:
                issue_data["body"] = desc_match.group(1).strip()
            else:
                issue_data["body"] = ""

        # Extract URL
        url_match = re.search(r"URL: (.+)", result)
        if url_match:
            issue_data["html_url"] = url_match.group(1).strip()

        # Store issue number
        issue_data["number"] = issue_number

        # Extract labels if present
        labels_match = re.search(r"Labels: (.+)", result)
        if labels_match:
            labels_str = labels_match.group(1).strip()
            issue_data["labels"] = [label.strip() for label in labels_str.split(",")]
        else:
            issue_data["labels"] = []

        logger.info(f"Successfully extracted Issue #{issue_number} data from {service}")
        return issue_data

    except Exception as e:
        logger.error(f"Error extracting issue data: {e}", exc_info=True)
        return None


def build_description_with_reference(original_desc: str, github_url: str) -> str:
    """
    Build GitLab description with GitHub reference.

    Adds a footer to the description linking back to the original GitHub item.

    Args:
        original_desc: Original description from GitHub
        github_url: GitHub URL to reference

    Returns:
        Description with GitHub reference appended
    """
    if not original_desc or original_desc.strip() == "":
        original_desc = "(No description provided)"

    # Add reference footer
    return f"{original_desc}\n\n---\n**Original GitHub Item:** {github_url}"


def transform_pr_to_mr_data(pr_data: Dict, github_url: str) -> Dict:
    """
    Transform GitHub PR data to GitLab MR format.

    Args:
        pr_data: GitHub PR data dictionary
        github_url: GitHub PR URL for reference

    Returns:
        Dictionary suitable for GitLab MR creation
    """
    # Build description with GitHub reference
    description = build_description_with_reference(pr_data.get("body", ""), github_url)

    return {
        "title": pr_data.get("title", "Untitled"),
        "description": description,
        "source_branch": pr_data.get("head_ref"),
        "target_branch": pr_data.get("base_ref", "main"),
    }


def transform_issue_data(issue_data: Dict, github_url: str) -> Dict:
    """
    Transform GitHub issue data to GitLab format.

    Args:
        issue_data: GitHub issue data dictionary
        github_url: GitHub issue URL for reference

    Returns:
        Dictionary suitable for GitLab issue creation
    """
    # Build description with GitHub reference
    description = build_description_with_reference(issue_data.get("body", ""), github_url)

    return {
        "title": issue_data.get("title", "Untitled"),
        "description": description,
    }


def ensure_upstream_configured(service: str, config: AgentConfig) -> Tuple[bool, str]:
    """
    Ensure upstream remote is configured for the repository.

    Automatically configures the upstream remote by fetching the GitLab URL
    from GitHub repository variables if not already configured.

    Args:
        service: Service name
        config: Agent configuration

    Returns:
        Tuple of (success, message)
    """
    try:
        git_tools = GitRepositoryTools(config)
        repo_path = git_tools._get_repo_path(service)

        # Validate repository exists
        is_valid, error = git_tools._validate_repository(repo_path)
        if not is_valid:
            return False, f"Repository not found: {error}"

        # Check if upstream remote exists
        returncode, stdout, stderr = git_tools._execute_git_command(
            repo_path, ["git", "remote", "get-url", "upstream"]
        )

        if returncode == 0:
            # Upstream already exists - use existing URL
            upstream_url = stdout.strip()
            logger.info(f"Upstream remote already exists: {upstream_url}")
        else:
            # Need to add upstream remote
            logger.info(f"Upstream remote not found, auto-configuring...")

            # Get GitLab URL from GitHub variables
            try:
                import subprocess
                repo = config.get_repo_full_name(service)
                result = subprocess.run(
                    ["gh", "api", f"repos/{repo}/actions/variables/UPSTREAM_REPO_URL", "--jq", ".value"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if result.returncode == 0 and result.stdout.strip():
                    upstream_url = result.stdout.strip()
                    logger.info(f"Found GitLab URL from GitHub variables: {upstream_url}")
                else:
                    # Fallback: construct from project path
                    gitlab_project_path = config.get_gitlab_project_path(service)
                    gitlab_base = config.gitlab_url or "https://gitlab.com"
                    upstream_url = f"{gitlab_base}/{gitlab_project_path}.git"
                    logger.info(f"Using constructed GitLab URL: {upstream_url}")
            except Exception as e:
                # Fallback: construct from project path
                gitlab_project_path = config.get_gitlab_project_path(service)
                gitlab_base = config.gitlab_url or "https://gitlab.com"
                upstream_url = f"{gitlab_base}/{gitlab_project_path}.git"
                logger.info(f"Using constructed GitLab URL (fallback): {upstream_url}")

            # Add upstream remote
            returncode, stdout, stderr = git_tools._execute_git_command(
                repo_path, ["git", "remote", "add", "upstream", upstream_url]
            )

            if returncode != 0:
                return False, f"Failed to add upstream remote: {stderr}"

        # Always fetch from upstream to get latest branches
        logger.info(f"Fetching from upstream: {upstream_url}")
        returncode, stdout, stderr = git_tools._execute_git_command(
            repo_path, ["git", "fetch", "upstream"], timeout=120
        )

        if returncode != 0:
            return False, f"Failed to fetch from upstream: {stderr}"

        logger.info(f"Successfully configured and fetched upstream remote for {service}: {upstream_url}")
        return True, f"Configured upstream remote: {upstream_url}"

    except Exception as e:
        logger.error(f"Error configuring upstream: {e}", exc_info=True)
        return False, f"Error configuring upstream: {str(e)}"


def remove_upstream_remote(service: str, config: AgentConfig) -> None:
    """
    Remove the upstream remote from the repository.

    This is called after the send operation completes to clean up.

    Args:
        service: Service name
        config: Agent configuration
    """
    try:
        git_tools = GitRepositoryTools(config)
        repo_path = git_tools._get_repo_path(service)

        logger.info(f"Removing upstream remote for {service}...")
        returncode, stdout, stderr = git_tools._execute_git_command(
            repo_path, ["git", "remote", "remove", "upstream"]
        )

        if returncode == 0:
            logger.info(f"Successfully removed upstream remote for {service}")
        else:
            logger.warning(f"Failed to remove upstream remote (non-fatal): {stderr}")

    except Exception as e:
        logger.warning(f"Error removing upstream remote (non-fatal): {e}")


def get_pr_commits(service: str, pr_number: int, config: AgentConfig) -> Optional[List[str]]:
    """
    Get list of commit SHAs from a GitHub PR.

    Args:
        service: Service name
        pr_number: PR number
        config: Agent configuration

    Returns:
        List of commit SHAs, or None on error
    """
    try:
        # Use GitHub API to get PR commits
        pr_tools = PullRequestTools(config)
        repo_full_name = config.get_repo_full_name(service)

        # Get the PR object directly from PyGithub
        gh_repo = pr_tools.github.get_repo(repo_full_name)
        pr = gh_repo.get_pull(pr_number)

        # Get commits
        commits = pr.get_commits()
        commit_shas = [commit.sha for commit in commits]

        logger.info(f"Found {len(commit_shas)} commits in PR #{pr_number}")
        return commit_shas

    except GithubException as e:
        logger.error(f"GitHub API error getting PR commits: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting PR commits: {e}", exc_info=True)
        return None


def create_mr_branch_from_upstream(
    service: str, pr_number: int, base_branch: str, config: AgentConfig
) -> Tuple[bool, str]:
    """
    Create MR branch from upstream remote.

    Creates a new branch named 'spi/pr-{pr_number}-{timestamp}' from upstream/{base_branch}.
    The timestamp ensures re-runs don't conflict with existing branches.
    Automatically maps GitHub branch names to GitLab equivalents (e.g., main → master).

    Args:
        service: Service name
        pr_number: PR number (used in branch name)
        base_branch: Base branch name from GitHub PR (e.g., 'main')
        config: Agent configuration

    Returns:
        Tuple of (success, message/branch_name)
    """
    try:
        git_tools = GitRepositoryTools(config)
        repo_path = git_tools._get_repo_path(service)

        # Generate timestamped branch name for idempotent re-runs
        timestamp = datetime.now().strftime('%Y%m%d-%H%M')
        mr_branch = f"spi/pr-{pr_number}-{timestamp}"

        # Smart branch mapping: Check if base_branch exists on upstream
        # If not, try common alternatives (main ↔ master)
        upstream_branch = base_branch
        returncode, stdout, stderr = git_tools._execute_git_command(
            repo_path, ["git", "rev-parse", "--verify", f"upstream/{base_branch}"], timeout=5
        )

        if returncode != 0:
            # Branch doesn't exist, try alternatives
            logger.info(f"upstream/{base_branch} not found, checking alternatives...")

            if base_branch == "main":
                # Try master
                returncode, _, _ = git_tools._execute_git_command(
                    repo_path, ["git", "rev-parse", "--verify", "upstream/master"], timeout=5
                )
                if returncode == 0:
                    upstream_branch = "master"
                    logger.info(f"Mapped GitHub 'main' → GitLab 'master'")
            elif base_branch == "master":
                # Try main
                returncode, _, _ = git_tools._execute_git_command(
                    repo_path, ["git", "rev-parse", "--verify", "upstream/main"], timeout=5
                )
                if returncode == 0:
                    upstream_branch = "main"
                    logger.info(f"Mapped GitHub 'master' → GitLab 'main'")

            # Verify the mapped branch exists
            returncode, stdout, stderr = git_tools._execute_git_command(
                repo_path, ["git", "rev-parse", "--verify", f"upstream/{upstream_branch}"], timeout=5
            )
            if returncode != 0:
                return False, f"Base branch not found on upstream: tried '{base_branch}' and '{upstream_branch}'"

        logger.info(f"Using upstream branch: {upstream_branch}")

        # Create branch from upstream/upstream_branch
        logger.info(f"Creating branch {mr_branch} from upstream/{upstream_branch}...")
        returncode, stdout, stderr = git_tools._execute_git_command(
            repo_path, ["git", "checkout", "-b", mr_branch, f"upstream/{upstream_branch}"]
        )

        if returncode != 0:
            # Check if branch already exists
            if "already exists" in stderr:
                # Delete existing branch and retry
                logger.info(f"Branch {mr_branch} exists, deleting and recreating...")
                git_tools._execute_git_command(repo_path, ["git", "checkout", base_branch])
                git_tools._execute_git_command(repo_path, ["git", "branch", "-D", mr_branch])
                returncode, stdout, stderr = git_tools._execute_git_command(
                    repo_path, ["git", "checkout", "-b", mr_branch, f"upstream/{upstream_branch}"]
                )
                if returncode != 0:
                    return False, f"Failed to create branch after cleanup: {stderr}"
            else:
                return False, f"Failed to create branch: {stderr}"

        logger.info(f"Successfully created branch {mr_branch}")
        return True, mr_branch

    except Exception as e:
        logger.error(f"Error creating MR branch: {e}", exc_info=True)
        return False, f"Error creating branch: {str(e)}"


def cherry_pick_commits(
    service: str, commit_shas: List[str], config: AgentConfig
) -> Tuple[bool, str]:
    """
    Cherry-pick commits into current branch.

    Args:
        service: Service name
        commit_shas: List of commit SHAs to cherry-pick
        config: Agent configuration

    Returns:
        Tuple of (success, message)
    """
    try:
        git_tools = GitRepositoryTools(config)
        repo_path = git_tools._get_repo_path(service)

        # Fetch from origin to ensure we have all PR commits locally
        logger.info(f"Fetching from origin to get PR commits...")
        returncode, stdout, stderr = git_tools._execute_git_command(
            repo_path, ["git", "fetch", "origin"], timeout=60
        )

        if returncode != 0:
            logger.warning(f"Failed to fetch from origin (non-fatal): {stderr}")

        logger.info(f"Cherry-picking {len(commit_shas)} commits...")

        for sha in commit_shas:
            returncode, stdout, stderr = git_tools._execute_git_command(
                repo_path, ["git", "cherry-pick", sha], timeout=60
            )

            if returncode != 0:
                # Check if commit is empty (changes already in upstream)
                if "nothing to commit" in stderr or "previous cherry-pick is now empty" in stderr:
                    logger.info(f"Skipping empty commit {sha[:7]} (changes already in upstream)")
                    # Skip this commit
                    git_tools._execute_git_command(repo_path, ["git", "cherry-pick", "--skip"])
                    continue

                # Cherry-pick failed with real conflicts
                # Abort the cherry-pick
                git_tools._execute_git_command(repo_path, ["git", "cherry-pick", "--abort"])

                error_msg = (
                    f"Cherry-pick failed for commit {sha[:7]} with conflicts.\n\n"
                    f"This usually means the changes in the GitHub PR conflict with "
                    f"the GitLab upstream state.\n\n"
                    f"Please resolve conflicts manually:\n"
                    f"  1. cd repos/{service}\n"
                    f"  2. git cherry-pick {sha}\n"
                    f"  3. Resolve conflicts\n"
                    f"  4. git cherry-pick --continue\n"
                    f"  5. Retry the /send command or create MR manually\n\n"
                    f"Error: {stderr}"
                )
                return False, error_msg

        logger.info("Successfully cherry-picked all commits")
        return True, "All commits cherry-picked successfully"

    except Exception as e:
        logger.error(f"Error cherry-picking commits: {e}", exc_info=True)
        return False, f"Error cherry-picking commits: {str(e)}"


def push_branch_to_gitlab(service: str, branch: str, config: AgentConfig) -> Tuple[bool, str]:
    """
    Push branch to GitLab upstream.

    Pushes timestamped branch (spi/pr-{number}-{timestamp}) to GitLab.
    Since branch names include timestamps, each push is unique and
    doesn't conflict with previous runs.

    Args:
        service: Service name
        branch: Branch name to push (e.g., 'spi/pr-5-20250123-1430')
        config: Agent configuration

    Returns:
        Tuple of (success, message)
    """
    try:
        git_tools = GitRepositoryTools(config)
        repo_path = git_tools._get_repo_path(service)

        logger.info(f"Pushing branch {branch} to upstream...")
        returncode, stdout, stderr = git_tools._execute_git_command(
            repo_path, ["git", "push", "upstream", branch], timeout=120
        )

        if returncode != 0:
            # Check for common authentication errors
            if "authentication" in stderr.lower() or "permission denied" in stderr.lower():
                error_msg = (
                    f"Git push failed - authentication required.\n\n"
                    f"Please configure git credentials for GitLab:\n\n"
                    f"Option A (SSH - Recommended):\n"
                    f"  1. Generate SSH key: ssh-keygen -t ed25519 -C 'your_email@example.com'\n"
                    f"  2. Add to GitLab: Settings → SSH Keys\n"
                    f"  3. Ensure upstream remote uses SSH: git@gitlab.com:group/project.git\n\n"
                    f"Option B (HTTPS with Token):\n"
                    f"  1. Create GitLab personal access token with 'write_repository' scope\n"
                    f"  2. Configure git credential helper: git config --global credential.helper store\n"
                    f"  3. Next push will prompt for username (use 'oauth2') and password (use token)\n\n"
                    f"Then retry /send command\n\n"
                    f"Error: {stderr}"
                )
                return False, error_msg
            else:
                return False, f"Failed to push branch: {stderr}"

        logger.info(f"Successfully pushed branch {branch} to upstream")
        return True, "Branch pushed successfully"

    except Exception as e:
        logger.error(f"Error pushing branch: {e}", exc_info=True)
        return False, f"Error pushing branch: {str(e)}"


def cleanup_mr_branch(service: str, branch: str, config: AgentConfig) -> None:
    """
    Clean up local MR branch after successful transfer.

    Args:
        service: Service name
        branch: Branch name to delete
        config: Agent configuration
    """
    try:
        git_tools = GitRepositoryTools(config)
        repo_path = git_tools._get_repo_path(service)

        logger.info(f"Cleaning up local branch {branch}...")

        # Checkout a different branch first
        git_tools._execute_git_command(repo_path, ["git", "checkout", "main"])

        # Delete the MR branch
        returncode, stdout, stderr = git_tools._execute_git_command(
            repo_path, ["git", "branch", "-D", branch]
        )

        if returncode == 0:
            logger.info(f"Successfully deleted local branch {branch}")
        else:
            logger.warning(f"Failed to delete branch {branch}: {stderr}")

    except Exception as e:
        logger.warning(f"Error during branch cleanup (non-fatal): {e}")


def send_pr_to_gitlab(service: str, pr_number: int, config: AgentConfig) -> str:
    """
    Send a GitHub PR to GitLab as a Merge Request.

    This function orchestrates the complete workflow:
    1. Extract PR data from GitHub
    2. Auto-configure upstream remote (temporary)
    3. Create MR branch from upstream
    4. Cherry-pick PR commits
    5. Push branch to GitLab
    6. Create GitLab MR
    7. Clean up local branch and upstream remote

    Args:
        service: Service name
        pr_number: GitHub PR number
        config: Agent configuration

    Returns:
        Success or error message with URLs
    """
    try:
        logger.info(f"Starting send PR workflow for {service} PR #{pr_number}")

        # Extract PR data
        pr_data = extract_pr_data(service, pr_number, config)
        if not pr_data:
            return f"Error: GitHub PR #{pr_number} not found in {service}"

        github_url = pr_data.get("html_url", f"https://github.com/{config.get_repo_full_name(service)}/pull/{pr_number}")

        # Ensure upstream is configured (auto-adds if not present)
        success, msg = ensure_upstream_configured(service, config)
        if not success:
            return f"Error: {msg}"

        # Get PR commits
        commit_shas = get_pr_commits(service, pr_number, config)
        if not commit_shas:
            remove_upstream_remote(service, config)
            return f"Error: Could not retrieve commits from PR #{pr_number}"

        # Create MR branch from upstream
        # Note: base_branch from GitHub PR (e.g., 'main')
        # create_mr_branch_from_upstream will map to GitLab branch (e.g., 'master')
        base_branch = pr_data.get("base_ref", "main")
        success, result = create_mr_branch_from_upstream(service, pr_number, base_branch, config)
        if not success:
            remove_upstream_remote(service, config)
            return f"Error creating MR branch: {result}"

        mr_branch = result

        # Determine actual GitLab target branch (might be different from GitHub)
        # Check what branch we actually created from
        git_tools = GitRepositoryTools(config)
        repo_path = git_tools._get_repo_path(service)
        returncode, stdout, stderr = git_tools._execute_git_command(
            repo_path, ["git", "rev-parse", "--abbrev-ref", f"{mr_branch}@{{u}}"], timeout=5
        )

        # Extract upstream branch name (e.g., "upstream/master" → "master")
        if returncode == 0 and stdout.strip().startswith("upstream/"):
            gitlab_target_branch = stdout.strip().replace("upstream/", "")
        else:
            # Fallback: try to map main → master
            gitlab_target_branch = "master" if base_branch == "main" else base_branch

        logger.info(f"GitLab target branch: {gitlab_target_branch} (GitHub PR targeted: {base_branch})")

        # Cherry-pick commits
        success, msg = cherry_pick_commits(service, commit_shas, config)
        if not success:
            # Clean up branch on failure
            cleanup_mr_branch(service, mr_branch, config)
            remove_upstream_remote(service, config)
            return f"Error: {msg}"

        # Push branch to GitLab
        success, msg = push_branch_to_gitlab(service, mr_branch, config)
        if not success:
            # Clean up branch on failure
            cleanup_mr_branch(service, mr_branch, config)
            remove_upstream_remote(service, config)
            return f"Error: {msg}"

        # Transform PR data to MR format (use GitLab target branch, not GitHub's)
        mr_data = transform_pr_to_mr_data(pr_data, github_url)
        mr_data["target_branch"] = gitlab_target_branch  # Override with actual GitLab branch

        # Create GitLab MR
        mr_tools = MergeRequestTools(config)
        result = mr_tools.create_merge_request(
            project=service,
            source_branch=mr_branch,
            target_branch=mr_data["target_branch"],
            title=mr_data["title"],
            description=mr_data["description"],
        )

        # Clean up local branch and upstream remote
        cleanup_mr_branch(service, mr_branch, config)
        remove_upstream_remote(service, config)

        # Check if MR creation was successful
        if "error" in result.lower():
            return f"Error creating GitLab MR: {result}"

        # Extract GitLab MR URL from result
        url_match = re.search(r"URL: (.+)", result)
        gitlab_url = url_match.group(1).strip() if url_match else "URL not found"

        success_msg = (
            f"✓ Sent PR #{pr_number} from GitHub to GitLab\n"
            f"GitHub: {github_url}\n"
            f"GitLab: {gitlab_url}"
        )

        logger.info(f"Successfully sent PR #{pr_number} to GitLab")
        return success_msg

    except Exception as e:
        logger.error(f"Error in send PR workflow: {e}", exc_info=True)
        # Clean up upstream remote on exception
        remove_upstream_remote(service, config)
        return f"Error sending PR to GitLab: {str(e)}"


def send_issue_to_gitlab(service: str, issue_number: int, config: AgentConfig) -> str:
    """
    Send a GitHub Issue to GitLab.

    Args:
        service: Service name
        issue_number: GitHub issue number
        config: Agent configuration

    Returns:
        Success or error message with URLs
    """
    try:
        logger.info(f"Starting send issue workflow for {service} Issue #{issue_number}")

        # Extract issue data
        issue_data = extract_issue_data(service, issue_number, config)
        if not issue_data:
            return f"Error: GitHub Issue #{issue_number} not found in {service}"

        github_url = issue_data.get("html_url", f"https://github.com/{config.get_repo_full_name(service)}/issues/{issue_number}")

        # Transform issue data
        gitlab_issue_data = transform_issue_data(issue_data, github_url)

        # Create GitLab issue
        issue_tools = GitLabIssueTools(config)
        result = issue_tools.create_issue(
            project=service,
            title=gitlab_issue_data["title"],
            description=gitlab_issue_data["description"],
        )

        # Check if issue creation was successful
        if "error" in result.lower():
            return f"Error creating GitLab issue: {result}"

        # Extract GitLab issue URL from result
        url_match = re.search(r"URL: (.+)", result)
        gitlab_url = url_match.group(1).strip() if url_match else "URL not found"

        success_msg = (
            f"✓ Sent Issue #{issue_number} from GitHub to GitLab\n"
            f"GitHub: {github_url}\n"
            f"GitLab: {gitlab_url}"
        )

        logger.info(f"Successfully sent Issue #{issue_number} to GitLab")
        return success_msg

    except Exception as e:
        logger.error(f"Error in send issue workflow: {e}", exc_info=True)
        return f"Error sending issue to GitLab: {str(e)}"


def send_multiple_items(
    service: str, items: List[Tuple[str, int]], config: AgentConfig
) -> str:
    """
    Send multiple GitHub items to GitLab.

    Args:
        service: Service name
        items: List of tuples (item_type, item_number) where item_type is 'pr' or 'issue'
        config: Agent configuration

    Returns:
        Summary of operations
    """
    results = []
    successes = 0
    failures = 0

    for item_type, item_number in items:
        if item_type == "pr":
            result = send_pr_to_gitlab(service, item_number, config)
        elif item_type == "issue":
            result = send_issue_to_gitlab(service, item_number, config)
        else:
            result = f"Error: Unknown item type '{item_type}'"

        results.append(f"\n{item_type.upper()} #{item_number}: {result}")

        if "✓" in result or "success" in result.lower():
            successes += 1
        else:
            failures += 1

    summary = (
        f"Batch send complete: {successes} succeeded, {failures} failed\n"
        f"{''.join(results)}"
    )

    return summary
