"""Pull request management tools for GitHub."""

from typing import Annotated, Optional

from github import GithubException
from github.GithubObject import NotSet
from pydantic import Field

from spi_agent.github.base import GitHubToolsBase


class PullRequestTools(GitHubToolsBase):
    """Tools for managing GitHub pull requests."""

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

            output.append("\nChanges:\n")
            output.append(f"  📝 Files changed: {pr_data['changed_files']}\n")
            output.append(f"  ➕ Additions: {pr_data['additions']} lines\n")
            output.append(f"  ➖ Deletions: {pr_data['deletions']} lines\n")
            output.append(f"  💬 Comments: {pr_data['comments_count']}\n")
            output.append(f"  💬 Review comments: {pr_data['review_comments_count']}\n")

            # Merge readiness
            output.append("\nMerge Readiness:\n")
            mergeable = pr_data['mergeable']
            if mergeable is None:
                output.append("  Mergeable: calculating...\n")
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

            if base_branch is not None:
                update_params["base"] = base_branch
                updated_fields.append("base")

            # Apply PR updates (excluding draft - handled separately)
            if update_params:
                pr.edit(**update_params)

            # Handle draft status separately using GitHub CLI (PyGithub doesn't support it)
            if draft is not None:
                import subprocess
                if draft:
                    # Mark PR as draft (convert to draft)
                    result = subprocess.run(
                        ["gh", "pr", "ready", "--undo", str(pr_number), "-R", repo_full_name],
                        capture_output=True,
                        text=True
                    )
                else:
                    # Mark PR as ready for review (remove draft status)
                    result = subprocess.run(
                        ["gh", "pr", "ready", str(pr_number), "-R", repo_full_name],
                        capture_output=True,
                        text=True
                    )

                if result.returncode == 0:
                    updated_fields.append("draft")
                else:
                    return f"Failed to update draft status: {result.stderr}"

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

    def review_pull_request(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        pr_number: Annotated[int, Field(description="Pull request number")],
        event: Annotated[
            str,
            Field(description="Review event: 'APPROVE', 'REQUEST_CHANGES', or 'COMMENT'")
        ],
        body: Annotated[
            Optional[str], Field(description="Review comment/feedback (optional for APPROVE)")
        ] = None,
    ) -> str:
        """
        Submit a review for a pull request.

        Use 'APPROVE' to approve, 'REQUEST_CHANGES' to request changes (body required),
        or 'COMMENT' for feedback without approval/rejection.

        Returns formatted string with review confirmation.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)
            pr = gh_repo.get_pull(pr_number)

            # Validate event
            valid_events = ["APPROVE", "REQUEST_CHANGES", "COMMENT"]
            event_upper = event.upper()
            if event_upper not in valid_events:
                return f"Invalid review event '{event}'. Must be one of: {', '.join(valid_events)}"

            # REQUEST_CHANGES requires a body
            if event_upper == "REQUEST_CHANGES" and not body:
                return "Review body is required when requesting changes"

            # Submit review
            review = pr.create_review(
                body=body or "",
                event=event_upper
            )

            # Format response based on event type
            event_msg = {
                "APPROVE": "✓ Approved",
                "REQUEST_CHANGES": "⚠ Requested changes on",
                "COMMENT": "💬 Commented on"
            }.get(event_upper, "Reviewed")

            output = [
                f"{event_msg} pull request #{pr_number} in {repo_full_name}\n",
                f"Title: {pr.title}\n",
                f"Review ID: {review.id}\n",
            ]

            if body:
                output.append(f"Comment: {body[:100]}{'...' if len(body) > 100 else ''}\n")

            output.append(f"PR URL: {pr.html_url}\n")

            return "".join(output)

        except GithubException as e:
            if e.status == 404:
                return f"Pull request #{pr_number} not found in {repo}"
            elif e.status == 422:
                msg = e.data.get('message', '')
                if 'review' in msg.lower():
                    return f"Cannot submit review: {msg}"
            return f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Error reviewing pull request: {str(e)}"

    def merge_pull_request(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        pr_number: Annotated[int, Field(description="Pull request number")],
        merge_method: Annotated[
            str, Field(description="Merge method: 'merge', 'squash', or 'rebase'")
        ] = "squash",
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
