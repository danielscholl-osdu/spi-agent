"""Merge request management tools for GitLab."""

from typing import Annotated, Optional

from gitlab.exceptions import GitlabError
from pydantic import Field

from spi_agent.gitlab.base import GitLabToolsBase


class MergeRequestTools(GitLabToolsBase):
    """Tools for managing GitLab merge requests."""

    def list_merge_requests(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        state: Annotated[
            str, Field(description="MR state: 'opened', 'closed', 'merged', or 'all'")
        ] = "opened",
        labels: Annotated[
            Optional[str], Field(description="Comma-separated label names")
        ] = None,
        assignee: Annotated[Optional[str], Field(description="GitLab username")] = None,
        limit: Annotated[int, Field(description="Maximum number of MRs to return")] = 30,
    ) -> str:
        """
        List merge requests from a GitLab project.

        Returns formatted string with MR list.
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
                try:
                    users = self.gitlab.users.list(username=assignee)
                    if users:
                        query_params["assignee_id"] = users[0].id
                except GitlabError:
                    pass

            # Get merge requests
            merge_requests = gl_project.mergerequests.list(**query_params, per_page=limit)

            if not merge_requests:
                return f"No {state} merge requests found in {project_path}"

            # Format results
            output_lines = [f"Found {len(merge_requests)} merge request(s) in {project_path}:\n"]
            for mr in merge_requests:
                mr_data = self._format_merge_request(mr)
                labels_str = f" [{', '.join(mr_data['labels'])}]" if mr_data['labels'] else ""
                draft_marker = " [DRAFT]" if mr_data['draft'] else ""
                output_lines.append(
                    f"!{mr_data['iid']}: {mr_data['title']}{draft_marker}{labels_str}\n"
                    f"  {mr_data['source_branch']} → {mr_data['target_branch']}\n"
                    f"  State: {mr_data['state']} | Merge status: {mr_data['merge_status']}\n"
                    f"  Author: {mr_data['author']} | URL: {mr_data['web_url']}\n"
                )

            return "".join(output_lines)

        except GitlabError as e:
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error listing merge requests: {str(e)}"

    def get_merge_request(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        mr_iid: Annotated[int, Field(description="Merge request IID")],
    ) -> str:
        """
        Get detailed information about a specific merge request.

        Returns formatted string with MR details.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)
            mr = gl_project.mergerequests.get(mr_iid)

            mr_data = self._format_merge_request(mr)

            # Format detailed output
            output = [
                f"Merge Request !{mr_data['iid']}: {mr_data['title']}\n",
                f"State: {mr_data['state']}\n",
                f"Branches: {mr_data['source_branch']} → {mr_data['target_branch']}\n",
                f"Author: {mr_data['author']}\n",
                f"Created: {mr_data['created_at']}\n",
                f"Updated: {mr_data['updated_at']}\n",
                f"Merge Status: {mr_data['merge_status']}\n",
                f"Has Conflicts: {mr_data['has_conflicts']}\n",
                f"Changes: {mr_data['changes_count']}\n",
            ]

            if mr_data['draft']:
                output.append("Draft: Yes\n")

            if mr_data['merged_at']:
                output.append(f"Merged At: {mr_data['merged_at']}\n")

            if mr_data['labels']:
                output.append(f"Labels: {', '.join(mr_data['labels'])}\n")

            if mr_data['assignees']:
                output.append(f"Assignees: {', '.join(mr_data['assignees'])}\n")

            if mr_data['description']:
                output.append(f"\nDescription:\n{mr_data['description']}\n")

            output.append(f"\nURL: {mr_data['web_url']}\n")

            return "".join(output)

        except GitlabError as e:
            if "404" in str(e):
                return f"Merge request !{mr_iid} not found in {project}"
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error getting merge request: {str(e)}"

    def get_mr_notes(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        mr_iid: Annotated[int, Field(description="Merge request IID")],
        limit: Annotated[int, Field(description="Maximum number of notes to return")] = 20,
    ) -> str:
        """
        Get discussion notes for a specific merge request.

        Returns formatted string with MR notes.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)
            mr = gl_project.mergerequests.get(mr_iid)

            notes = mr.notes.list(per_page=limit, order_by="created_at", sort="asc")

            if not notes:
                return f"No notes found for merge request !{mr_iid} in {project_path}"

            # Format results
            output_lines = [f"Found {len(notes)} note(s) for merge request !{mr_iid}:\n"]
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
            return f"Error getting MR notes: {str(e)}"

    def create_merge_request(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        source_branch: Annotated[str, Field(description="Source branch name")],
        target_branch: Annotated[str, Field(description="Target branch name")],
        title: Annotated[str, Field(description="Merge request title")],
        description: Annotated[
            Optional[str], Field(description="MR description (markdown supported)")
        ] = None,
    ) -> str:
        """
        Create a new merge request in a GitLab project.

        Returns formatted string with created MR details.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)

            # Build MR data
            mr_data = {
                "source_branch": source_branch,
                "target_branch": target_branch,
                "title": title,
            }

            if description:
                mr_data["description"] = description

            # Create merge request
            mr = gl_project.mergerequests.create(mr_data)

            return (
                f"Created merge request !{mr.iid}: {mr.title}\n"
                f"Branches: {mr.source_branch} → {mr.target_branch}\n"
                f"State: {mr.state}\n"
                f"URL: {mr.web_url}"
            )

        except GitlabError as e:
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error creating merge request: {str(e)}"

    def update_merge_request(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        mr_iid: Annotated[int, Field(description="Merge request IID")],
        title: Annotated[Optional[str], Field(description="New MR title")] = None,
        description: Annotated[Optional[str], Field(description="New MR description")] = None,
        state: Annotated[
            Optional[str], Field(description="New state: 'opened' or 'closed'")
        ] = None,
        labels: Annotated[Optional[str], Field(description="Comma-separated labels")] = None,
        assignees: Annotated[Optional[str], Field(description="Comma-separated usernames")] = None,
    ) -> str:
        """
        Update an existing merge request's properties.

        Returns formatted string with updated MR details.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)
            mr = gl_project.mergerequests.get(mr_iid)

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

            # Update merge request
            for key, value in update_data.items():
                setattr(mr, key, value)
            mr.save()

            return (
                f"Updated merge request !{mr.iid}: {mr.title}\n"
                f"State: {mr.state}\n"
                f"URL: {mr.web_url}"
            )

        except GitlabError as e:
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error updating merge request: {str(e)}"

    def merge_merge_request(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        mr_iid: Annotated[int, Field(description="Merge request IID")],
        merge_commit_message: Annotated[
            Optional[str], Field(description="Custom merge commit message")
        ] = None,
        should_remove_source_branch: Annotated[
            bool, Field(description="Remove source branch after merge")
        ] = False,
    ) -> str:
        """
        Merge a merge request.

        Returns formatted string with merge result.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)
            mr = gl_project.mergerequests.get(mr_iid)

            # Check if mergeable
            if mr.has_conflicts:
                return (
                    f"Cannot merge !{mr_iid}: Merge request has conflicts\n"
                    f"Please resolve conflicts before merging"
                )

            if mr.merge_status != "can_be_merged":
                return (
                    f"Cannot merge !{mr_iid}: Merge status is '{mr.merge_status}'\n"
                    f"Merge request may have conflicts or pending checks"
                )

            # Build merge parameters
            merge_params = {
                "should_remove_source_branch": should_remove_source_branch,
            }

            if merge_commit_message:
                merge_params["merge_commit_message"] = merge_commit_message

            # Perform merge
            mr.merge(**merge_params)

            return (
                f"Successfully merged !{mr.iid}: {mr.title}\n"
                f"Branches: {mr.source_branch} → {mr.target_branch}\n"
                f"Source branch removed: {should_remove_source_branch}\n"
                f"URL: {mr.web_url}"
            )

        except GitlabError as e:
            if "405" in str(e) or "Cannot merge" in str(e):
                return f"Cannot merge !{mr_iid}: {str(e)}"
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error merging merge request: {str(e)}"

    def add_mr_note(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        mr_iid: Annotated[int, Field(description="Merge request IID")],
        body: Annotated[str, Field(description="Note body (markdown supported)")],
    ) -> str:
        """
        Add a note/comment to a merge request.

        Returns formatted string confirming note addition.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)
            mr = gl_project.mergerequests.get(mr_iid)

            # Create note
            note = mr.notes.create({"body": body})

            return (
                f"Added note to merge request !{mr_iid}\n"
                f"Note ID: {note.id}\n"
                f"Author: {note.author.get('username', 'unknown')}"
            )

        except GitlabError as e:
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error adding note: {str(e)}"
