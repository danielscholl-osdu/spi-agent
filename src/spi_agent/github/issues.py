"""Issue management tools for GitHub."""

from typing import Annotated, Optional

from github import GithubException
from github.GithubObject import NotSet
from pydantic import Field

from spi_agent.github.base import GitHubToolsBase


class IssueTools(GitHubToolsBase):
    """Tools for managing GitHub issues."""

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
