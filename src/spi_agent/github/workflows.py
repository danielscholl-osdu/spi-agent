"""Workflow and Actions tools for GitHub."""

import json
import subprocess
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
        workflow_name_or_id: Annotated[str, Field(description="Workflow filename, display name, or ID")],
        ref: Annotated[str, Field(description="Branch/tag/SHA to run on")] = "main",
        inputs: Annotated[
            Optional[str], Field(description="JSON string of workflow inputs")
        ] = None,
    ) -> str:
        """
        Manually trigger a workflow (workflow_dispatch).

        Accepts workflow filename (e.g., 'codeql.yml'), display name (e.g., 'CodeQL Analysis'), or ID.
        Automatically maps display names to filenames if needed.

        Returns formatted string with trigger confirmation.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)

            # Try to get workflow by filename/ID first
            workflow = None
            try:
                workflow = gh_repo.get_workflow(workflow_name_or_id)
            except:
                # If not found by filename/ID, try to find by display name
                try:
                    workflows = gh_repo.get_workflows()
                    for wf in workflows:
                        if wf.name.lower() == workflow_name_or_id.lower():
                            workflow = wf
                            break
                except:
                    pass

            if not workflow:
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

    def check_pr_workflow_approvals(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        pr_number: Annotated[int, Field(description="Pull request number")],
    ) -> str:
        """
        Check if a PR has workflow runs waiting for approval.

        Returns formatted string with approval status.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)

            # Use gh CLI to get workflow runs for the PR
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "checks",
                    str(pr_number),
                    "-R",
                    repo_full_name,
                    "--json",
                    "name,state,bucket,startedAt,completedAt",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return f"Failed to get PR checks for #{pr_number} in {repo_full_name}\nError: {result.stderr}"

            checks = json.loads(result.stdout)

            # Check for workflow approval needed
            # GitHub shows specific states for checks
            pending_approvals = []
            running_checks = []
            passed_checks = []
            failed_checks = []

            for check in checks:
                state = check.get("state", "")
                bucket = check.get("bucket", "")
                name = check.get("name", "Unknown")
                started_at = check.get("startedAt")

                # "pending" state without start time means awaiting approval
                if state == "pending" and not started_at:
                    pending_approvals.append(name)
                elif state == "pending" or bucket == "pass":
                    running_checks.append(name)
                elif state == "success" or bucket == "pass":
                    passed_checks.append(name)
                elif state in ["failure", "error"] or bucket == "fail":
                    failed_checks.append(name)

            output_lines = [f"Workflow Status for PR #{pr_number} in {repo_full_name}:\n\n"]

            if pending_approvals:
                output_lines.append(f"⏳ Workflows awaiting approval: {len(pending_approvals)}\n")
                for name in pending_approvals[:5]:  # Limit to first 5
                    output_lines.append(f"   - {name}\n")
                if len(pending_approvals) > 5:
                    output_lines.append(f"   ... and {len(pending_approvals) - 5} more\n")
                output_lines.append("\n")

            if running_checks:
                output_lines.append(f"⏳ Running: {len(running_checks)}\n")
                for name in running_checks[:3]:
                    output_lines.append(f"   - {name}\n")
                output_lines.append("\n")

            if passed_checks:
                output_lines.append(f"✓ Passed: {len(passed_checks)}\n")

            if failed_checks:
                output_lines.append(f"✗ Failed: {len(failed_checks)}\n")
                for name in failed_checks[:3]:
                    output_lines.append(f"   - {name}\n")
                output_lines.append("\n")

            if pending_approvals:
                output_lines.append(
                    f"\n💡 Note: Approve workflows manually in GitHub UI for this PR to continue\n"
                )

            return "".join(output_lines)

        except subprocess.TimeoutExpired:
            return f"Timeout while checking PR #{pr_number} workflows"
        except FileNotFoundError:
            return "GitHub CLI (gh) is not installed or not in PATH"
        except json.JSONDecodeError:
            return f"Failed to parse workflow check data for PR #{pr_number}"
        except Exception as e:
            return f"Error checking PR workflow approvals: {str(e)}"

    def rerun_workflow_run(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        run_id: Annotated[int, Field(description="Workflow run ID")],
    ) -> str:
        """
        Rerun a workflow run. This also serves as "approval" for action_required workflows.

        Returns formatted string with rerun confirmation.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)

            # Use gh CLI to rerun the workflow
            result = subprocess.run(
                [
                    "gh",
                    "run",
                    "rerun",
                    str(run_id),
                    "-R",
                    repo_full_name,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return (
                    f"✓ Rerun workflow run #{run_id} in {repo_full_name}\n"
                    f"Status: Workflow will start running\n"
                )
            else:
                return f"Failed to rerun workflow run #{run_id}\nError: {result.stderr}"

        except subprocess.TimeoutExpired:
            return f"Timeout while rerunning workflow run #{run_id}"
        except FileNotFoundError:
            return "GitHub CLI (gh) is not installed or not in PATH"
        except Exception as e:
            return f"Error rerunning workflow run: {str(e)}"

    def approve_pr_workflows(
        self,
        repo: Annotated[str, Field(description="Repository name (e.g., 'partition')")],
        pr_number: Annotated[int, Field(description="Pull request number")],
    ) -> str:
        """
        Approve pending workflow runs for a PR.

        Uses GitHub CLI to approve workflows (for fork PRs) or rerun them (for non-fork PRs).
        Returns formatted string with approval confirmation.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)

            # First, get the PR to find its head branch
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr_number),
                    "-R",
                    repo_full_name,
                    "--json",
                    "headRefName",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return f"Failed to get PR #{pr_number} details\nError: {result.stderr}"

            pr_data = json.loads(result.stdout)
            head_branch = pr_data.get("headRefName")

            if not head_branch:
                return f"Could not find branch for PR #{pr_number}"

            # Get workflow runs for this branch that need approval
            # Note: action_required is a CONCLUSION not a status
            # Query by branch to catch workflows from all commits, not just the latest
            result = subprocess.run(
                [
                    "gh",
                    "api",
                    f"/repos/{repo_full_name}/actions/runs?branch={head_branch}",
                    "--jq",
                    ".workflow_runs[] | select(.conclusion == \"action_required\") | {id, name, status, conclusion}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return f"Failed to get workflow runs for PR #{pr_number}\nError: {result.stderr}"

            # Parse workflow runs (each line is a JSON object)
            workflow_runs = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    try:
                        workflow_runs.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            if not workflow_runs:
                return f"No workflows awaiting approval for PR #{pr_number} in {repo_full_name}"

            # Approve each workflow run
            # Try approve endpoint first (for fork PRs), fallback to rerun (for non-fork PRs)
            approved = []
            failed = []

            for run in workflow_runs:
                run_id = run.get("id")
                run_name = run.get("name", "Unknown")

                # Try approve endpoint first (works for fork PRs)
                approve_result = subprocess.run(
                    [
                        "gh",
                        "api",
                        "-X",
                        "POST",
                        f"/repos/{repo_full_name}/actions/runs/{run_id}/approve",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if approve_result.returncode == 0:
                    approved.append(run_name)
                else:
                    # If approve fails (e.g., not from fork), try rerun instead
                    rerun_result = subprocess.run(
                        [
                            "gh",
                            "run",
                            "rerun",
                            str(run_id),
                            "-R",
                            repo_full_name,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )

                    if rerun_result.returncode == 0:
                        approved.append(run_name)
                    else:
                        failed.append((run_name, f"Approve failed: {approve_result.stderr}, Rerun failed: {rerun_result.stderr}"))

            # Format output
            output_lines = []

            if approved:
                output_lines.append(
                    f"✓ Approved {len(approved)} workflow(s) for PR #{pr_number} in {repo_full_name}:\n"
                )
                for name in approved:
                    output_lines.append(f"  ✓ {name}\n")
                output_lines.append("\nWorkflows will now start running.\n")

            if failed:
                output_lines.append(f"\n✗ Failed to approve {len(failed)} workflow(s):\n")
                for name, error in failed:
                    output_lines.append(f"  ✗ {name}: {error}\n")

            return "".join(output_lines)

        except subprocess.TimeoutExpired:
            return f"Timeout while approving workflows for PR #{pr_number}"
        except FileNotFoundError:
            return "GitHub CLI (gh) is not installed or not in PATH"
        except json.JSONDecodeError as e:
            return f"Failed to parse workflow data: {str(e)}"
        except Exception as e:
            return f"Error approving PR workflows: {str(e)}"
