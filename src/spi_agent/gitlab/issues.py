"""Issue management tools for GitLab."""

from typing import Annotated, Optional

from gitlab.exceptions import GitlabError
from pydantic import Field

from spi_agent.gitlab.base import GitLabToolsBase


class IssueTools(GitLabToolsBase):
    """Tools for managing GitLab issues."""

    def list_issues(
        self,
        project: Annotated[
            str, Field(description="GitLab project path (e.g., 'osdu/partition' or 'partition')")
        ],
        state: Annotated[
            str, Field(description="Issue state: 'opened', 'closed', or 'all'")
        ] = "opened",
        labels: Annotated[
            Optional[str],
            Field(description="Comma-separated label names to filter by (e.g., 'bug,priority::high')"),
        ] = None,
        assignee: Annotated[
            Optional[str], Field(description="GitLab username to filter by assignee")
        ] = None,
        limit: Annotated[int, Field(description="Maximum number of issues to return")] = 30,
    ) -> str:
        """
        List issues from a GitLab project.

        Returns formatted string with issue list.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)

            # Build query parameters
            query_params = {}

            if state != "all":
                query_params["state"] = state

            if labels:
                query_params["labels"] = labels

            if assignee:
                # Get user ID for assignee filtering
                try:
                    users = self.gitlab.users.list(username=assignee)
                    if users:
                        query_params["assignee_id"] = users[0].id
                except GitlabError:
                    pass  # Continue without assignee filter if lookup fails

            # Get issues
            issues = gl_project.issues.list(**query_params, per_page=limit)

            if not issues:
                return f"No {state} issues found in {project_path}"

            # Format results
            output_lines = [f"Found {len(issues)} issue(s) in {project_path}:\n"]
            for issue in issues:
                issue_data = self._format_issue(issue)
                labels_str = f" [{', '.join(issue_data['labels'])}]" if issue_data['labels'] else ""
                output_lines.append(
                    f"#{issue_data['iid']}: {issue_data['title']}{labels_str}\n"
                    f"  State: {issue_data['state']} | "
                    f"Author: {issue_data['author']}\n"
                    f"  URL: {issue_data['web_url']}\n"
                )

            return "".join(output_lines)

        except GitlabError as e:
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error listing issues: {str(e)}"

    def get_issue(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        issue_iid: Annotated[int, Field(description="Issue IID (internal ID)")],
    ) -> str:
        """
        Get detailed information about a specific issue.

        Returns formatted string with issue details.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)
            issue = gl_project.issues.get(issue_iid)

            issue_data = self._format_issue(issue)

            # Format detailed output
            output = [
                f"Issue #{issue_data['iid']}: {issue_data['title']}\n",
                f"State: {issue_data['state']}\n",
                f"Author: {issue_data['author']}\n",
                f"Created: {issue_data['created_at']}\n",
                f"Updated: {issue_data['updated_at']}\n",
            ]

            if issue_data['labels']:
                output.append(f"Labels: {', '.join(issue_data['labels'])}\n")

            if issue_data['assignees']:
                output.append(f"Assignees: {', '.join(issue_data['assignees'])}\n")

            if issue_data['description']:
                output.append(f"\nDescription:\n{issue_data['description']}\n")

            output.append(f"\nURL: {issue_data['web_url']}\n")

            return "".join(output)

        except GitlabError as e:
            if "404" in str(e):
                return f"Issue #{issue_iid} not found in {project}"
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error getting issue: {str(e)}"

    def get_issue_notes(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        issue_iid: Annotated[int, Field(description="Issue IID")],
        limit: Annotated[int, Field(description="Maximum number of notes to return")] = 20,
    ) -> str:
        """
        Get notes/comments for a specific issue.

        Returns formatted string with issue notes.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)
            issue = gl_project.issues.get(issue_iid)

            notes = issue.notes.list(per_page=limit, order_by="created_at", sort="asc")

            if not notes:
                return f"No notes found for issue #{issue_iid} in {project_path}"

            # Format results
            output_lines = [f"Found {len(notes)} note(s) for issue #{issue_iid}:\n"]
            for note in notes:
                note_data = self._format_note(note)
                system_marker = " [SYSTEM]" if note_data['system'] else ""
                output_lines.append(
                    f"\nNote by {note_data['author']}{system_marker} at {note_data['created_at']}:\n"
                    f"{note_data['body']}\n"
                )

            return "".join(output_lines)

        except GitlabError as e:
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error getting issue notes: {str(e)}"

    def create_issue(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        title: Annotated[str, Field(description="Issue title")],
        description: Annotated[
            Optional[str], Field(description="Issue description (markdown supported)")
        ] = None,
        labels: Annotated[
            Optional[str], Field(description="Comma-separated label names")
        ] = None,
        assignees: Annotated[
            Optional[str], Field(description="Comma-separated GitLab usernames to assign")
        ] = None,
    ) -> str:
        """
        Create a new issue in a GitLab project.

        Returns formatted string with created issue details.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)

            # Build issue data
            issue_data = {"title": title}

            if description:
                issue_data["description"] = description

            if labels:
                issue_data["labels"] = labels

            if assignees:
                # Convert usernames to user IDs
                assignee_ids = []
                for username in assignees.split(","):
                    username = username.strip()
                    try:
                        users = self.gitlab.users.list(username=username)
                        if users:
                            assignee_ids.append(users[0].id)
                    except GitlabError:
                        pass  # Skip invalid usernames

                if assignee_ids:
                    issue_data["assignee_ids"] = assignee_ids

            # Create issue
            issue = gl_project.issues.create(issue_data)

            return (
                f"Created issue #{issue.iid}: {issue.title}\n"
                f"State: {issue.state}\n"
                f"URL: {issue.web_url}"
            )

        except GitlabError as e:
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error creating issue: {str(e)}"

    def update_issue(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        issue_iid: Annotated[int, Field(description="Issue IID")],
        title: Annotated[Optional[str], Field(description="New issue title")] = None,
        description: Annotated[Optional[str], Field(description="New issue description")] = None,
        state: Annotated[
            Optional[str], Field(description="New state: 'opened' or 'closed'")
        ] = None,
        labels: Annotated[Optional[str], Field(description="Comma-separated labels")] = None,
        assignees: Annotated[Optional[str], Field(description="Comma-separated usernames")] = None,
    ) -> str:
        """
        Update an existing issue's properties.

        Returns formatted string with updated issue details.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)
            issue = gl_project.issues.get(issue_iid)

            # Build update data
            update_data = {}

            if title is not None:
                update_data["title"] = title

            if description is not None:
                update_data["description"] = description

            if state is not None:
                update_data["state_event"] = "close" if state == "closed" else "reopen"

            if labels is not None:
                update_data["labels"] = labels

            if assignees is not None:
                # Convert usernames to user IDs
                assignee_ids = []
                for username in assignees.split(","):
                    username = username.strip()
                    try:
                        users = self.gitlab.users.list(username=username)
                        if users:
                            assignee_ids.append(users[0].id)
                    except GitlabError:
                        pass

                update_data["assignee_ids"] = assignee_ids

            # Update issue
            for key, value in update_data.items():
                setattr(issue, key, value)
            issue.save()

            return (
                f"Updated issue #{issue.iid}: {issue.title}\n"
                f"State: {issue.state}\n"
                f"URL: {issue.web_url}"
            )

        except GitlabError as e:
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error updating issue: {str(e)}"

    def add_issue_note(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        issue_iid: Annotated[int, Field(description="Issue IID")],
        body: Annotated[str, Field(description="Note/comment body (markdown supported)")],
    ) -> str:
        """
        Add a note/comment to an issue.

        Returns formatted string confirming note addition.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)
            issue = gl_project.issues.get(issue_iid)

            # Create note
            note = issue.notes.create({"body": body})

            return (
                f"Added note to issue #{issue_iid}\n"
                f"Note ID: {note.id}\n"
                f"Author: {note.author.get('username', 'unknown')}"
            )

        except GitlabError as e:
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error adding note: {str(e)}"

    def search_issues(
        self,
        query: Annotated[str, Field(description="Search query string")],
        projects: Annotated[
            Optional[str],
            Field(description="Comma-separated project paths to search (default: all accessible)"),
        ] = None,
        limit: Annotated[int, Field(description="Maximum number of results")] = 20,
    ) -> str:
        """
        Search issues across GitLab projects.

        Returns formatted string with search results.
        """
        try:
            if projects:
                # Search in specific projects
                project_list = [p.strip() for p in projects.split(",")]
                results = []

                for project_name in project_list:
                    try:
                        project_path = self.config.get_gitlab_project_path(project_name)
                        gl_project = self.gitlab.projects.get(project_path)
                        issues = gl_project.issues.list(search=query, per_page=limit)
                        results.extend([(project_path, issue) for issue in issues])
                    except GitlabError:
                        continue  # Skip projects that can't be accessed

            else:
                # Search across all accessible projects using global search
                issues = self.gitlab.issues.list(search=query, per_page=limit)
                results = [(f"project-{issue.project_id}", issue) for issue in issues]

            if not results:
                return f"No issues found matching query: {query}"

            # Format results
            output_lines = [f"Found {len(results)} issue(s) matching '{query}':\n"]
            for project_path, issue in results[:limit]:
                issue_data = self._format_issue(issue)
                output_lines.append(
                    f"\n{project_path} - Issue #{issue_data['iid']}: {issue_data['title']}\n"
                    f"  State: {issue_data['state']} | Author: {issue_data['author']}\n"
                    f"  URL: {issue_data['web_url']}\n"
                )

            return "".join(output_lines)

        except GitlabError as e:
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error searching issues: {str(e)}"
