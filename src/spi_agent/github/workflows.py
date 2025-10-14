"""Workflow and Actions tools for GitHub."""

import json
from typing import Annotated, Optional

from github import GithubException
from github.GithubObject import NotSet
from pydantic import Field

from spi_agent.github.base import GitHubToolsBase


class WorkflowTools(GitHubToolsBase):
    """Tools for managing GitHub Actions workflows."""

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

            output.append("\nTiming:\n")
            output.append(f"  Created: {run_data['created_at']}\n")
            if run_data['run_started_at']:
                output.append(f"  Started: {run_data['run_started_at']}\n")
            else:
                output.append("  Started: Not started\n")
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
                        output.append("\n")

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
