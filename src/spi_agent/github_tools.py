"""GitHub integration tools using PyGithub."""

from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

from github import Auth, Github, GithubException
from github.GithubObject import NotSet
from pydantic import Field

from spi_agent.config import AgentConfig


class GitHubTools:
    """GitHub operations toolkit using PyGithub."""

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

    def list_issues(
        self,
        repo: Annotated[
            str, Field(description="Repository name (e.g., 'partition', not full path)")
        ],
        state: Annotated[
            str, Field(description="Issue state: 'open', 'closed', or 'all'")
        ] = "open",
        labels: Annotated[
            Optional[str],
            Field(description="Comma-separated label names to filter by (e.g., 'bug,priority:high')"),
        ] = None,
        assignee: Annotated[
            Optional[str], Field(description="GitHub username to filter by assignee")
        ] = None,
        limit: Annotated[int, Field(description="Maximum number of issues to return")] = 30,
    ) -> str:
        """
        List issues from a repository.

        Returns formatted string with issue list.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)

            # Build query parameters
            query_params = {"state": state}

            if labels:
                label_list = [label.strip() for label in labels.split(",")]
                query_params["labels"] = label_list

            if assignee:
                query_params["assignee"] = assignee

            # Get issues
            issues = gh_repo.get_issues(**query_params)

            # Format results
            results = []
            count = 0
            for issue in issues:
                if issue.pull_request:  # Skip pull requests
                    continue

                results.append(self._format_issue(issue))
                count += 1
                if count >= limit:
                    break

            if not results:
                return f"No {state} issues found in {repo_full_name}"

            # Format for display
            output_lines = [f"Found {len(results)} issue(s) in {repo_full_name}:\n"]
            for issue_data in results:
                labels_str = f" [{', '.join(issue_data['labels'])}]" if issue_data['labels'] else ""
                output_lines.append(
                    f"#{issue_data['number']}: {issue_data['title']}{labels_str}\n"
                    f"  State: {issue_data['state']} | Comments: {issue_data['comments_count']} | "
                    f"Author: {issue_data['author']}\n"
                    f"  URL: {issue_data['html_url']}\n"
                )

            return "".join(output_lines)

        except GithubException as e:
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error listing issues: {str(e)}"

    def get_issue(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        issue_number: Annotated[int, Field(description="Issue number")],
    ) -> str:
        """
        Get detailed information about a specific issue.

        Returns formatted string with issue details.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)
            issue = gh_repo.get_issue(issue_number)

            if issue.pull_request:
                return f"#{issue_number} is a pull request, not an issue"

            issue_data = self._format_issue(issue)

            output = [
                f"Issue #{issue_data['number']} in {repo_full_name}\n",
                f"Title: {issue_data['title']}\n",
                f"State: {issue_data['state']}\n",
                f"Author: {issue_data['author']}\n",
                f"Created: {issue_data['created_at']}\n",
                f"Updated: {issue_data['updated_at']}\n",
                f"Comments: {issue_data['comments_count']}\n",
            ]

            if issue_data["labels"]:
                output.append(f"Labels: {', '.join(issue_data['labels'])}\n")

            if issue_data["assignees"]:
                output.append(f"Assignees: {', '.join(issue_data['assignees'])}\n")

            if issue_data["body"]:
                output.append(f"\nDescription:\n{issue_data['body']}\n")

            output.append(f"\nURL: {issue_data['html_url']}\n")

            return "".join(output)

        except GithubException as e:
            if e.status == 404:
                return f"Issue #{issue_number} not found in {repo}"
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error getting issue: {str(e)}"

    def get_issue_comments(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        issue_number: Annotated[int, Field(description="Issue number")],
        limit: Annotated[int, Field(description="Maximum number of comments")] = 50,
    ) -> str:
        """
        Get comments from an issue.

        Returns formatted string with comment list.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)
            issue = gh_repo.get_issue(issue_number)

            if issue.pull_request:
                return f"#{issue_number} is a pull request, not an issue"

            # Get comments
            comments = issue.get_comments()

            # Format results
            results = []
            count = 0
            for comment in comments:
                results.append(self._format_comment(comment))
                count += 1
                if count >= limit:
                    break

            if not results:
                return f"No comments found on issue #{issue_number} in {repo_full_name}"

            # Format for display
            output_lines = [f"Comments on issue #{issue_number} in {repo_full_name}:\n\n"]
            for idx, comment_data in enumerate(results, 1):
                output_lines.append(
                    f"Comment #{idx} by {comment_data['author']} ({comment_data['created_at']}):\n"
                    f"  {comment_data['body']}\n"
                    f"  URL: {comment_data['html_url']}\n\n"
                )

            output_lines.append(f"Total: {len(results)} comment(s)")
            if count >= limit and issue.comments > limit:
                output_lines.append(f" (showing first {limit} of {issue.comments})")

            return "".join(output_lines)

        except GithubException as e:
            if e.status == 404:
                return f"Issue #{issue_number} not found in {repo}"
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error getting comments: {str(e)}"

    def create_issue(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        title: Annotated[str, Field(description="Issue title")],
        body: Annotated[
            Optional[str], Field(description="Issue description/body (markdown supported)")
        ] = None,
        labels: Annotated[
            Optional[str], Field(description="Comma-separated label names to add")
        ] = None,
        assignees: Annotated[
            Optional[str], Field(description="Comma-separated GitHub usernames to assign")
        ] = None,
    ) -> str:
        """
        Create a new issue in a repository.

        Returns formatted string with created issue info.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)

            # Parse labels and assignees
            label_list = [l.strip() for l in labels.split(",")] if labels else []
            assignee_list = [a.strip() for a in assignees.split(",")] if assignees else []

            # Create issue
            issue = gh_repo.create_issue(
                title=title,
                body=body or "",
                labels=label_list if label_list else NotSet,
                assignees=assignee_list if assignee_list else NotSet,
            )

            return (
                f"✓ Created issue #{issue.number} in {repo_full_name}\n"
                f"Title: {issue.title}\n"
                f"URL: {issue.html_url}\n"
            )

        except GithubException as e:
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error creating issue: {str(e)}"

    def update_issue(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        issue_number: Annotated[int, Field(description="Issue number to update")],
        title: Annotated[Optional[str], Field(description="New title")] = None,
        body: Annotated[Optional[str], Field(description="New body/description")] = None,
        state: Annotated[
            Optional[str], Field(description="New state: 'open' or 'closed'")
        ] = None,
        labels: Annotated[
            Optional[str],
            Field(description="Comma-separated labels (replaces existing labels)"),
        ] = None,
        assignees: Annotated[
            Optional[str],
            Field(description="Comma-separated assignees (replaces existing assignees)"),
        ] = None,
    ) -> str:
        """
        Update an existing issue.

        Returns formatted string with update confirmation.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)
            issue = gh_repo.get_issue(issue_number)

            if issue.pull_request:
                return f"#{issue_number} is a pull request, not an issue"

            # Build update parameters
            update_params = {}

            if title is not None:
                update_params["title"] = title

            if body is not None:
                update_params["body"] = body

            if state is not None:
                if state.lower() not in ["open", "closed"]:
                    return f"Invalid state '{state}'. Must be 'open' or 'closed'"
                update_params["state"] = state.lower()

            if labels is not None:
                label_list = [l.strip() for l in labels.split(",") if l.strip()]
                update_params["labels"] = label_list

            if assignees is not None:
                assignee_list = [a.strip() for a in assignees.split(",") if a.strip()]
                update_params["assignees"] = assignee_list

            # Apply updates
            issue.edit(**update_params)

            updates_made = ", ".join(update_params.keys())
            return (
                f"✓ Updated issue #{issue_number} in {repo_full_name}\n"
                f"Updated fields: {updates_made}\n"
                f"URL: {issue.html_url}\n"
            )

        except GithubException as e:
            if e.status == 404:
                return f"Issue #{issue_number} not found in {repo}"
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error updating issue: {str(e)}"

    def add_issue_comment(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        issue_number: Annotated[int, Field(description="Issue number to comment on")],
        comment: Annotated[str, Field(description="Comment text (markdown supported)")],
    ) -> str:
        """
        Add a comment to an existing issue.

        Returns formatted string with comment confirmation.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)
            issue = gh_repo.get_issue(issue_number)

            if issue.pull_request:
                return f"#{issue_number} is a pull request, not an issue"

            # Add comment
            issue_comment = issue.create_comment(comment)

            return (
                f"✓ Added comment to issue #{issue_number} in {repo_full_name}\n"
                f"Comment ID: {issue_comment.id}\n"
                f"URL: {issue_comment.html_url}\n"
            )

        except GithubException as e:
            if e.status == 404:
                return f"Issue #{issue_number} not found in {repo}"
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error adding comment: {str(e)}"

    def search_issues(
        self,
        query: Annotated[
            str,
            Field(
                description="Search query (e.g., 'authentication', 'CodeQL', 'is:open label:bug')"
            ),
        ],
        repos: Annotated[
            Optional[str],
            Field(description="Comma-separated repository names to search (searches all if not specified)"),
        ] = None,
        limit: Annotated[int, Field(description="Maximum number of results")] = 30,
    ) -> str:
        """
        Search issues across repositories.

        Returns formatted string with search results.
        """
        try:
            # Build search query
            if repos:
                repo_list = [r.strip() for r in repos.split(",") if r.strip()]
                repo_queries = [
                    f"repo:{self.config.get_repo_full_name(r)}" for r in repo_list
                ]
                full_query = f"{query} {' '.join(repo_queries)} is:issue"
            else:
                # Search all configured repos
                repo_queries = [
                    f"repo:{self.config.get_repo_full_name(r)}" for r in self.config.repositories
                ]
                full_query = f"{query} {' '.join(repo_queries)} is:issue"

            # Execute search
            issues = self.github.search_issues(full_query)

            # Format results
            results = []
            count = 0
            for issue in issues:
                results.append(self._format_issue(issue))
                count += 1
                if count >= limit:
                    break

            if not results:
                return f"No issues found matching query: {query}"

            # Format for display
            output_lines = [f"Found {len(results)} issue(s) matching '{query}':\n\n"]
            for issue_data in results:
                repo_name = issue_data["html_url"].split("/")[-4] + "/" + issue_data["html_url"].split("/")[-3]
                labels_str = f" [{', '.join(issue_data['labels'])}]" if issue_data['labels'] else ""
                output_lines.append(
                    f"{repo_name} #{issue_data['number']}: {issue_data['title']}{labels_str}\n"
                    f"  State: {issue_data['state']} | Author: {issue_data['author']}\n"
                    f"  URL: {issue_data['html_url']}\n"
                )

            return "".join(output_lines)

        except GithubException as e:
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error searching issues: {str(e)}"

    # ============ PULL REQUESTS ============

    def list_pull_requests(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        state: Annotated[str, Field(description="PR state: 'open', 'closed', or 'all'")] = "open",
        base_branch: Annotated[
            Optional[str], Field(description="Filter by base branch (e.g., 'main')")
        ] = None,
        head_branch: Annotated[
            Optional[str], Field(description="Filter by head branch (e.g., 'feature/auth')")
        ] = None,
        limit: Annotated[int, Field(description="Maximum number of PRs to return")] = 30,
    ) -> str:
        """
        List pull requests in a repository.

        Returns formatted string with PR list.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)

            # Get pull requests
            prs = gh_repo.get_pulls(state=state, base=base_branch or NotSet, head=head_branch or NotSet)

            # Format results
            results = []
            count = 0
            for pr in prs:
                results.append(self._format_pr(pr))
                count += 1
                if count >= limit:
                    break

            if not results:
                return f"No {state} pull requests found in {repo_full_name}"

            # Format for display
            output_lines = [f"Found {len(results)} pull request(s) in {repo_full_name}:\n\n"]
            for pr_data in results:
                state_display = f"[{pr_data['state']}]"
                if pr_data['merged']:
                    state_display = "[merged]"
                elif pr_data['draft']:
                    state_display = "[draft]"

                output_lines.append(
                    f"#{pr_data['number']}: {pr_data['title']} {state_display}\n"
                    f"  Author: {pr_data['author']} | Base: {pr_data['base_ref']} ← Head: {pr_data['head_ref']}\n"
                    f"  💬 {pr_data['comments_count']} comments | 📝 {pr_data['changed_files']} files changed\n"
                    f"  Created: {pr_data['created_at']}\n"
                    f"  URL: {pr_data['html_url']}\n\n"
                )

            return "".join(output_lines)

        except GithubException as e:
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error listing pull requests: {str(e)}"

    def get_pull_request(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        pr_number: Annotated[int, Field(description="Pull request number")],
    ) -> str:
        """
        Get detailed information about a specific pull request.

        Returns formatted string with PR details.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)
            pr = gh_repo.get_pull(pr_number)

            pr_data = self._format_pr(pr)

            output = [
                f"Pull Request #{pr_data['number']} in {repo_full_name}\n\n",
                f"Title: {pr_data['title']}\n",
                f"State: {pr_data['state']}\n",
                f"Author: {pr_data['author']}\n",
                f"Base: {pr_data['base_ref']} ← Head: {pr_data['head_ref']}\n",
                f"Created: {pr_data['created_at']}\n",
                f"Updated: {pr_data['updated_at']}\n",
            ]

            if pr_data["merged"]:
                output.append(f"Merged: {pr_data['merged_at']}\n")

            output.append(f"\nChanges:\n")
            output.append(f"  📝 Files changed: {pr_data['changed_files']}\n")
            output.append(f"  ➕ Additions: {pr_data['additions']} lines\n")
            output.append(f"  ➖ Deletions: {pr_data['deletions']} lines\n")
            output.append(f"  💬 Comments: {pr_data['comments_count']}\n")
            output.append(f"  💬 Review comments: {pr_data['review_comments_count']}\n")

            # Merge readiness
            output.append(f"\nMerge Readiness:\n")
            mergeable = pr_data['mergeable']
            if mergeable is None:
                output.append(f"  Mergeable: calculating...\n")
            elif mergeable:
                output.append(f"  Mergeable: yes ({pr_data['mergeable_state']})\n")
            else:
                output.append(f"  Mergeable: no ({pr_data['mergeable_state']})\n")
            output.append(f"  Draft: {'yes' if pr_data['draft'] else 'no'}\n")

            if pr_data["labels"]:
                output.append(f"\nLabels: {', '.join(pr_data['labels'])}\n")

            if pr_data["assignees"]:
                output.append(f"Assignees: {', '.join(pr_data['assignees'])}\n")

            if pr_data["body"]:
                output.append(f"\nDescription:\n{pr_data['body']}\n")

            output.append(f"\nURL: {pr_data['html_url']}\n")

            return "".join(output)

        except GithubException as e:
            if e.status == 404:
                return f"Pull request #{pr_number} not found in {repo}"
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error getting pull request: {str(e)}"

    def get_pr_comments(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        pr_number: Annotated[int, Field(description="Pull request number")],
        limit: Annotated[int, Field(description="Maximum number of comments")] = 50,
    ) -> str:
        """
        Get discussion comments from a pull request.

        Returns formatted string with comment list.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)
            pr = gh_repo.get_pull(pr_number)

            # Get PR comments via issue interface
            issue = pr.as_issue()
            comments = issue.get_comments()

            # Format results
            results = []
            count = 0
            for comment in comments:
                results.append(self._format_comment(comment))
                count += 1
                if count >= limit:
                    break

            if not results:
                return f"No comments found on PR #{pr_number} in {repo_full_name}"

            # Format for display
            output_lines = [f"Comments on PR #{pr_number} in {repo_full_name}:\n\n"]
            for idx, comment_data in enumerate(results, 1):
                output_lines.append(
                    f"Comment #{idx} by {comment_data['author']} ({comment_data['created_at']}):\n"
                    f"  {comment_data['body']}\n"
                    f"  URL: {comment_data['html_url']}\n\n"
                )

            output_lines.append(f"Total: {len(results)} comment(s)")
            if count >= limit and pr.comments > limit:
                output_lines.append(f" (showing first {limit} of {pr.comments})")

            return "".join(output_lines)

        except GithubException as e:
            if e.status == 404:
                return f"Pull request #{pr_number} not found in {repo}"
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error getting PR comments: {str(e)}"

    def create_pull_request(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        title: Annotated[str, Field(description="Pull request title")],
        head_branch: Annotated[
            str, Field(description="Source branch (e.g., 'feature/auth' or 'user:feature/auth')")
        ],
        base_branch: Annotated[str, Field(description="Target branch")] = "main",
        body: Annotated[
            Optional[str], Field(description="PR description (markdown supported)")
        ] = None,
        draft: Annotated[bool, Field(description="Create as draft PR")] = False,
        maintainer_can_modify: Annotated[
            bool, Field(description="Allow maintainers to edit")
        ] = True,
    ) -> str:
        """
        Create a new pull request.

        Returns formatted string with created PR info.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)

            # Create PR
            pr = gh_repo.create_pull(
                title=title,
                body=body or "",
                head=head_branch,
                base=base_branch,
                draft=draft,
                maintainer_can_modify=maintainer_can_modify,
            )

            return (
                f"✓ Created pull request #{pr.number} in {repo_full_name}\n"
                f"Title: {pr.title}\n"
                f"Base: {pr.base.ref} ← Head: {pr.head.ref}\n"
                f"Draft: {'yes' if pr.draft else 'no'}\n"
                f"URL: {pr.html_url}\n"
            )

        except GithubException as e:
            # Provide helpful guidance for branch errors
            if e.status == 422:
                msg = e.data.get('message', '')
                if 'does not exist' in msg.lower() or 'not found' in msg.lower():
                    return (
                        f"Branch not found. For same-repo PR use 'branch-name'. "
                        f"For cross-fork PR use 'owner:branch-name'. Error: {msg}"
                    )
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error creating pull request: {str(e)}"

    def update_pull_request(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        pr_number: Annotated[int, Field(description="Pull request number")],
        title: Annotated[Optional[str], Field(description="New title")] = None,
        body: Annotated[Optional[str], Field(description="New body/description")] = None,
        state: Annotated[
            Optional[str], Field(description="New state: 'open' or 'closed'")
        ] = None,
        draft: Annotated[Optional[bool], Field(description="Toggle draft status")] = None,
        base_branch: Annotated[Optional[str], Field(description="New base branch")] = None,
        labels: Annotated[
            Optional[str], Field(description="Comma-separated labels (replaces existing)")
        ] = None,
        assignees: Annotated[
            Optional[str], Field(description="Comma-separated assignees (replaces existing)")
        ] = None,
    ) -> str:
        """
        Update pull request metadata.

        Returns formatted string with update confirmation.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)
            pr = gh_repo.get_pull(pr_number)

            # Build update parameters for PR
            update_params = {}
            updated_fields = []

            if title is not None:
                update_params["title"] = title
                updated_fields.append("title")

            if body is not None:
                update_params["body"] = body
                updated_fields.append("body")

            if state is not None:
                if state.lower() not in ["open", "closed"]:
                    return f"Invalid state '{state}'. Must be 'open' or 'closed'"
                if pr.merged:
                    return f"Cannot change state of merged PR #{pr_number}"
                update_params["state"] = state.lower()
                updated_fields.append("state")

            if draft is not None:
                update_params["draft"] = draft
                updated_fields.append("draft")

            if base_branch is not None:
                update_params["base"] = base_branch
                updated_fields.append("base")

            # Apply PR updates
            if update_params:
                pr.edit(**update_params)

            # Handle labels and assignees via issue interface
            issue_params = {}
            if labels is not None:
                label_list = [l.strip() for l in labels.split(",") if l.strip()]
                issue_params["labels"] = label_list
                updated_fields.append("labels")

            if assignees is not None:
                assignee_list = [a.strip() for a in assignees.split(",") if a.strip()]
                issue_params["assignees"] = assignee_list
                updated_fields.append("assignees")

            # Apply issue updates (labels/assignees)
            if issue_params:
                issue = pr.as_issue()
                issue.edit(**issue_params)

            if not updated_fields:
                return f"No updates specified for PR #{pr_number}"

            updates_made = ", ".join(updated_fields)
            return (
                f"✓ Updated pull request #{pr_number} in {repo_full_name}\n"
                f"Updated fields: {updates_made}\n"
                f"URL: {pr.html_url}\n"
            )

        except GithubException as e:
            if e.status == 404:
                return f"Pull request #{pr_number} not found in {repo}"
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error updating pull request: {str(e)}"

    def merge_pull_request(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        pr_number: Annotated[int, Field(description="Pull request number")],
        merge_method: Annotated[
            str, Field(description="Merge method: 'merge', 'squash', or 'rebase'")
        ] = "merge",
        commit_title: Annotated[Optional[str], Field(description="Custom merge commit title")] = None,
        commit_message: Annotated[
            Optional[str], Field(description="Custom merge commit message")
        ] = None,
    ) -> str:
        """
        Merge a pull request.

        Returns formatted string with merge confirmation.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)
            pr = gh_repo.get_pull(pr_number)

            # Check merge readiness
            if pr.merged:
                return f"Pull request #{pr_number} is already merged"

            if pr.state == "closed":
                return f"Cannot merge closed PR #{pr_number}"

            # Check mergeable state
            if pr.mergeable is False:
                return (
                    f"Pull request #{pr_number} cannot be merged\n"
                    f"Status: {pr.mergeable_state}\n"
                    f"Check for conflicts, failing checks, or review requirements."
                )

            # Validate merge method
            if merge_method not in ["merge", "squash", "rebase"]:
                return f"Invalid merge method '{merge_method}'. Must be 'merge', 'squash', or 'rebase'"

            # Perform merge
            result = pr.merge(
                commit_title=commit_title or NotSet,
                commit_message=commit_message or NotSet,
                merge_method=merge_method,
            )

            if result.merged:
                return (
                    f"✓ Merged pull request #{pr_number} in {repo_full_name}\n"
                    f"Method: {merge_method}\n"
                    f"Commit SHA: {result.sha}\n"
                    f"URL: {pr.html_url}\n"
                )
            else:
                return f"Failed to merge PR #{pr_number}: {result.message}"

        except GithubException as e:
            if e.status == 404:
                return f"Pull request #{pr_number} not found in {repo}"
            elif e.status == 405:
                return f"PR #{pr_number} cannot be merged: {e.data.get('message', str(e))}"
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error merging pull request: {str(e)}"

    def add_pr_comment(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        pr_number: Annotated[int, Field(description="Pull request number")],
        comment: Annotated[str, Field(description="Comment text (markdown supported)")],
    ) -> str:
        """
        Add a comment to a pull request discussion.

        Returns formatted string with comment confirmation.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)
            pr = gh_repo.get_pull(pr_number)

            # Validate comment
            if not comment.strip():
                return "Cannot add empty comment"

            # Add comment via issue interface
            pr_comment = pr.create_issue_comment(comment)

            return (
                f"✓ Added comment to PR #{pr_number} in {repo_full_name}\n"
                f"Comment ID: {pr_comment.id}\n"
                f"URL: {pr_comment.html_url}\n"
            )

        except GithubException as e:
            if e.status == 404:
                return f"Pull request #{pr_number} not found in {repo}"
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error adding PR comment: {str(e)}"

    # ============ WORKFLOWS/ACTIONS ============

    def list_workflows(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        limit: Annotated[int, Field(description="Maximum workflows to return")] = 50,
    ) -> str:
        """
        List available workflows in a repository.

        Returns formatted string with workflow list.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)

            workflows = gh_repo.get_workflows()

            # Format results
            results = []
            count = 0
            for workflow in workflows:
                results.append(self._format_workflow(workflow))
                count += 1
                if count >= limit:
                    break

            if not results:
                return f"No workflows found in {repo_full_name}"

            # Format for display
            output_lines = [f"Workflows in {repo_full_name}:\n\n"]
            for idx, wf_data in enumerate(results, 1):
                output_lines.append(
                    f"{idx}. {wf_data['name']} ({wf_data['path'].split('/')[-1]})\n"
                    f"   ID: {wf_data['id']} | State: {wf_data['state']}\n"
                    f"   Path: {wf_data['path']}\n\n"
                )

            output_lines.append(f"Total: {len(results)} workflow(s)")

            return "".join(output_lines)

        except GithubException as e:
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error listing workflows: {str(e)}"

    def list_workflow_runs(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        workflow_name_or_id: Annotated[
            Optional[str], Field(description="Filter by workflow name or ID")
        ] = None,
        status: Annotated[
            Optional[str], Field(description="Filter by status (completed, in_progress, queued)")
        ] = None,
        branch: Annotated[Optional[str], Field(description="Filter by branch")] = None,
        limit: Annotated[int, Field(description="Maximum runs to return")] = 30,
    ) -> str:
        """
        List recent workflow runs.

        Returns formatted string with workflow run list.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)

            # Get workflow runs
            if workflow_name_or_id:
                # Try to find specific workflow first
                try:
                    workflow = gh_repo.get_workflow(workflow_name_or_id)
                    runs = workflow.get_runs()
                except:
                    # If not found by filename, try all runs and filter
                    runs = gh_repo.get_workflow_runs()
            else:
                runs = gh_repo.get_workflow_runs()

            # Format results
            results = []
            count = 0
            for run in runs:
                # Apply filters
                if status and run.status != status:
                    continue
                if branch and run.head_branch != branch:
                    continue

                results.append(self._format_workflow_run(run))
                count += 1
                if count >= limit:
                    break

            if not results:
                return f"No workflow runs found in {repo_full_name}"

            # Format for display
            output_lines = [f"Recent workflow runs in {repo_full_name}:\n\n"]
            for run_data in results:
                status_icon = "⏳" if run_data['status'] == "in_progress" else (
                    "✓" if run_data['conclusion'] == "success" else "✗"
                )

                duration = "running"
                if run_data['status'] == "completed" and run_data['run_started_at']:
                    # Calculate duration (simplified)
                    duration = "completed"

                output_lines.append(
                    f"{run_data['name']} - Run #{run_data['id']}\n"
                    f"  Status: {status_icon} {run_data['status']}"
                )
                if run_data['conclusion']:
                    output_lines.append(f" ({run_data['conclusion']})")
                output_lines.append(
                    f"\n  Branch: {run_data['head_branch']} | Commit: {run_data['head_sha']}\n"
                    f"  Triggered by: {run_data['event']}\n"
                    f"  Started: {run_data['created_at']}\n"
                    f"  URL: {run_data['html_url']}\n\n"
                )

            output_lines.append(f"Total: {len(results)} run(s) (showing most recent)")

            return "".join(output_lines)

        except GithubException as e:
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error listing workflow runs: {str(e)}"

    def get_workflow_run(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        run_id: Annotated[int, Field(description="Workflow run ID")],
    ) -> str:
        """
        Get detailed information about a specific workflow run.

        Returns formatted string with workflow run details.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)
            run = gh_repo.get_workflow_run(run_id)

            run_data = self._format_workflow_run(run)

            status_icon = "⏳" if run_data['status'] == "in_progress" else (
                "✓" if run_data['conclusion'] == "success" else "✗"
            )

            output = [
                f"Workflow Run #{run_data['id']} in {repo_full_name}\n\n",
                f"Workflow: {run_data['name']}\n",
                f"Status: {status_icon} {run_data['status']}\n",
            ]

            if run_data['conclusion']:
                output.append(f"Conclusion: {run_data['conclusion']}\n")

            output.append(
                f"Branch: {run_data['head_branch']}\n"
                f"Commit: {run_data['head_sha']}\n"
                f"Triggered by: {run_data['event']}\n"
                f"Actor: {run_data['actor']}\n"
            )

            output.append(f"\nTiming:\n")
            output.append(f"  Created: {run_data['created_at']}\n")
            if run_data['run_started_at']:
                output.append(f"  Started: {run_data['run_started_at']}\n")
            else:
                output.append(f"  Started: Not started\n")
            output.append(f"  Updated: {run_data['updated_at']}\n")

            # Get jobs
            try:
                jobs_paginated = run.get_jobs()
                job_list = []
                count = 0
                for job in jobs_paginated:
                    job_list.append(job)
                    count += 1
                    if count >= 10:  # Limit to first 10 jobs
                        break

                total_jobs = jobs_paginated.totalCount

                if job_list:
                    output.append(f"\nJobs ({len(job_list)}):\n")
                    for job in job_list:
                        job_status = "✓" if job.conclusion == "success" else (
                            "✗" if job.conclusion == "failure" else "⏳"
                        )
                        output.append(
                            f"  {job_status} {job.name} - {job.status}"
                        )
                        if job.conclusion:
                            output.append(f" ({job.conclusion})")
                        output.append(f"\n")

                    if total_jobs > 10:
                        output.append(f"  ... and {total_jobs - 10} more jobs\n")
            except:
                pass  # Jobs may not be available for all runs

            output.append(f"\nRun URL: {run_data['html_url']}\n")

            return "".join(output)

        except GithubException as e:
            if e.status == 404:
                return f"Workflow run #{run_id} not found in {repo}"
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error getting workflow run: {str(e)}"

    def trigger_workflow(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        workflow_name_or_id: Annotated[str, Field(description="Workflow filename or ID")],
        ref: Annotated[str, Field(description="Branch/tag/SHA to run on")] = "main",
        inputs: Annotated[
            Optional[str], Field(description="JSON string of workflow inputs")
        ] = None,
    ) -> str:
        """
        Manually trigger a workflow (workflow_dispatch).

        Returns formatted string with trigger confirmation.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)

            # Get workflow
            try:
                workflow = gh_repo.get_workflow(workflow_name_or_id)
            except:
                return f"Workflow '{workflow_name_or_id}' not found in {repo_full_name}"

            # Parse inputs if provided
            parsed_inputs = {}
            if inputs:
                try:
                    import json
                    parsed_inputs = json.loads(inputs)
                    # Validate all values are strings
                    for key, value in parsed_inputs.items():
                        if not isinstance(value, str):
                            return f"Workflow input '{key}' must be string, got {type(value).__name__}"
                except json.JSONDecodeError as e:
                    return f"Invalid JSON for workflow inputs: {str(e)}"

            # Create dispatch
            result = workflow.create_dispatch(ref=ref, inputs=parsed_inputs if parsed_inputs else NotSet)

            if result:
                return (
                    f"✓ Triggered workflow \"{workflow.name}\" in {repo_full_name}\n"
                    f"Branch: {ref}\n"
                    f"Status: Workflow dispatch event created\n"
                    f"Note: Check workflow runs list to see execution\n\n"
                    f"Workflow URL: {workflow.html_url}\n"
                )
            else:
                return f"Failed to trigger workflow '{workflow_name_or_id}'"

        except GithubException as e:
            if e.status == 404:
                return f"Workflow or branch not found: {e.data.get('message', str(e))}"
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error triggering workflow: {str(e)}"

    def cancel_workflow_run(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        run_id: Annotated[int, Field(description="Workflow run ID")],
    ) -> str:
        """
        Cancel a running workflow.

        Returns formatted string with cancellation confirmation.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)
            run = gh_repo.get_workflow_run(run_id)

            # Check if run is cancellable
            if run.status == "completed":
                return f"Cannot cancel completed workflow run #{run_id}"

            # Cancel the run
            result = run.cancel()

            if result:
                return (
                    f"✓ Cancelled workflow run #{run_id} in {repo_full_name}\n"
                    f"Workflow: {run.name}\n"
                    f"Previous status: {run.status}\n"
                    f"URL: {run.html_url}\n"
                )
            else:
                return f"Failed to cancel workflow run #{run_id}"

        except GithubException as e:
            if e.status == 404:
                return f"Workflow run #{run_id} not found in {repo}"
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error cancelling workflow run: {str(e)}"

    # ============ CODE SCANNING ============

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

    def close(self) -> None:
        """Close GitHub connection."""
        if self.github:
            self.github.close()


# Create function tools for agent (these wrap the class methods)


def create_github_tools(config: AgentConfig) -> List:
    """
    Create GitHub tool functions for the agent.

    Returns list of tool functions that can be passed to agent.
    """
    tools_instance = GitHubTools(config)

    # Return list of bound methods that work as agent tools
    return [
        # Issues (7 tools)
        tools_instance.list_issues,
        tools_instance.get_issue,
        tools_instance.get_issue_comments,
        tools_instance.create_issue,
        tools_instance.update_issue,
        tools_instance.add_issue_comment,
        tools_instance.search_issues,
        # Pull Requests (7 tools)
        tools_instance.list_pull_requests,
        tools_instance.get_pull_request,
        tools_instance.get_pr_comments,
        tools_instance.create_pull_request,
        tools_instance.update_pull_request,
        tools_instance.merge_pull_request,
        tools_instance.add_pr_comment,
        # Workflows/Actions (5 tools)
        tools_instance.list_workflows,
        tools_instance.list_workflow_runs,
        tools_instance.get_workflow_run,
        tools_instance.trigger_workflow,
        tools_instance.cancel_workflow_run,
        # Code Scanning (2 tools)
        tools_instance.list_code_scanning_alerts,
        tools_instance.get_code_scanning_alert,
    ]
