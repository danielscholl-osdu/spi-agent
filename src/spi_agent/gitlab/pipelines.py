"""CI/CD pipeline management tools for GitLab."""

from typing import Annotated, Optional

from gitlab.exceptions import GitlabError
from pydantic import Field

from spi_agent.gitlab.base import GitLabToolsBase


class PipelineTools(GitLabToolsBase):
    """Tools for managing GitLab CI/CD pipelines."""

    def list_pipelines(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        status: Annotated[
            Optional[str],
            Field(
                description="Pipeline status: 'created', 'waiting_for_resource', 'preparing', 'pending', 'running', 'success', 'failed', 'canceled', 'skipped', 'manual'"
            ),
        ] = None,
        ref: Annotated[Optional[str], Field(description="Branch or tag name")] = None,
        limit: Annotated[int, Field(description="Maximum number of pipelines to return")] = 20,
    ) -> str:
        """
        List pipelines from a GitLab project.

        Returns formatted string with pipeline list.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)

            # Build query parameters
            query_params = {"per_page": limit, "order_by": "updated_at", "sort": "desc"}

            if status:
                query_params["status"] = status

            if ref:
                query_params["ref"] = ref

            # Get pipelines
            pipelines = gl_project.pipelines.list(**query_params)

            if not pipelines:
                filters = []
                if status:
                    filters.append(f"status={status}")
                if ref:
                    filters.append(f"ref={ref}")
                filter_str = " with " + ", ".join(filters) if filters else ""
                return f"No pipelines found in {project_path}{filter_str}"

            # Format results
            output_lines = [f"Found {len(pipelines)} pipeline(s) in {project_path}:\n"]
            for pipeline in pipelines:
                pipeline_data = self._format_pipeline(pipeline)
                output_lines.append(
                    f"\nPipeline #{pipeline_data['id']} ({pipeline_data['ref']})\n"
                    f"  Status: {pipeline_data['status']} | SHA: {pipeline_data['sha']}\n"
                    f"  User: {pipeline_data['user']} | Created: {pipeline_data['created_at']}\n"
                    f"  URL: {pipeline_data['web_url']}\n"
                )

            return "".join(output_lines)

        except GitlabError as e:
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error listing pipelines: {str(e)}"

    def get_pipeline(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        pipeline_id: Annotated[int, Field(description="Pipeline ID")],
    ) -> str:
        """
        Get detailed information about a specific pipeline.

        Returns formatted string with pipeline details.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)
            pipeline = gl_project.pipelines.get(pipeline_id)

            pipeline_data = self._format_pipeline(pipeline)

            # Format detailed output
            output = [
                f"Pipeline #{pipeline_data['id']}\n",
                f"Status: {pipeline_data['status']}\n",
                f"Ref: {pipeline_data['ref']}\n",
                f"SHA: {pipeline_data['sha']}\n",
                f"User: {pipeline_data['user']}\n",
                f"Created: {pipeline_data['created_at']}\n",
            ]

            if pipeline_data['started_at']:
                output.append(f"Started: {pipeline_data['started_at']}\n")

            if pipeline_data['finished_at']:
                output.append(f"Finished: {pipeline_data['finished_at']}\n")

            if pipeline_data['duration']:
                output.append(f"Duration: {pipeline_data['duration']}s\n")

            output.append(f"\nURL: {pipeline_data['web_url']}\n")

            return "".join(output)

        except GitlabError as e:
            if "404" in str(e):
                return f"Pipeline #{pipeline_id} not found in {project}"
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error getting pipeline: {str(e)}"

    def get_pipeline_jobs(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        pipeline_id: Annotated[int, Field(description="Pipeline ID")],
        limit: Annotated[int, Field(description="Maximum number of jobs to return")] = 50,
    ) -> str:
        """
        Get jobs for a specific pipeline.

        Returns formatted string with job details.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)
            pipeline = gl_project.pipelines.get(pipeline_id)

            jobs = pipeline.jobs.list(per_page=limit)

            if not jobs:
                return f"No jobs found for pipeline #{pipeline_id}"

            # Format results
            output_lines = [f"Found {len(jobs)} job(s) for pipeline #{pipeline_id}:\n"]
            for job in jobs:
                job_data = self._format_pipeline_job(job)
                output_lines.append(
                    f"\nJob #{job_data['id']}: {job_data['name']}\n"
                    f"  Stage: {job_data['stage']} | Status: {job_data['status']}\n"
                    f"  User: {job_data['user']}\n"
                )

                if job_data['duration']:
                    output_lines.append(f"  Duration: {job_data['duration']}s\n")

                if job_data['web_url']:
                    output_lines.append(f"  URL: {job_data['web_url']}\n")

            return "".join(output_lines)

        except GitlabError as e:
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error getting pipeline jobs: {str(e)}"

    def trigger_pipeline(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        ref: Annotated[str, Field(description="Branch or tag name to run pipeline for")],
        variables: Annotated[
            Optional[str],
            Field(description="Pipeline variables as comma-separated key=value pairs (e.g., 'ENV=prod,DEBUG=true')"),
        ] = None,
    ) -> str:
        """
        Manually trigger a pipeline run.

        Returns formatted string with triggered pipeline details.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)

            # Build pipeline data
            pipeline_data = {"ref": ref}

            # Parse variables if provided
            if variables:
                var_list = []
                for var_pair in variables.split(","):
                    var_pair = var_pair.strip()
                    if "=" in var_pair:
                        key, value = var_pair.split("=", 1)
                        var_list.append({"key": key.strip(), "value": value.strip()})

                if var_list:
                    pipeline_data["variables"] = var_list

            # Create pipeline
            pipeline = gl_project.pipelines.create(pipeline_data)

            return (
                f"Triggered pipeline #{pipeline.id} for ref '{ref}'\n"
                f"Status: {pipeline.status}\n"
                f"URL: {pipeline.web_url}"
            )

        except GitlabError as e:
            if "403" in str(e) or "Forbidden" in str(e):
                return f"Permission denied: Cannot trigger pipeline for {ref} in {project}"
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error triggering pipeline: {str(e)}"

    def cancel_pipeline(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        pipeline_id: Annotated[int, Field(description="Pipeline ID")],
    ) -> str:
        """
        Cancel a running pipeline.

        Returns formatted string with cancellation result.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)
            pipeline = gl_project.pipelines.get(pipeline_id)

            # Check if pipeline can be canceled
            if pipeline.status not in ["created", "waiting_for_resource", "preparing", "pending", "running"]:
                return (
                    f"Cannot cancel pipeline #{pipeline_id}: "
                    f"Pipeline status is '{pipeline.status}' (not running)"
                )

            # Cancel pipeline
            pipeline.cancel()

            return (
                f"Canceled pipeline #{pipeline_id}\n"
                f"Previous status: {pipeline.status}\n"
                f"URL: {pipeline.web_url}"
            )

        except GitlabError as e:
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error canceling pipeline: {str(e)}"

    def retry_pipeline(
        self,
        project: Annotated[str, Field(description="GitLab project path")],
        pipeline_id: Annotated[int, Field(description="Pipeline ID")],
    ) -> str:
        """
        Retry a failed pipeline.

        Returns formatted string with retry result.
        """
        try:
            project_path = self.config.get_gitlab_project_path(project)
            gl_project = self.gitlab.projects.get(project_path)
            pipeline = gl_project.pipelines.get(pipeline_id)

            # Check if pipeline can be retried
            if pipeline.status not in ["failed", "canceled", "success"]:
                return (
                    f"Cannot retry pipeline #{pipeline_id}: "
                    f"Pipeline status is '{pipeline.status}' (must be failed, canceled, or success)"
                )

            # Retry pipeline
            pipeline.retry()

            return (
                f"Retrying pipeline #{pipeline_id}\n"
                f"Previous status: {pipeline.status}\n"
                f"URL: {pipeline.web_url}"
            )

        except GitlabError as e:
            return f"GitLab API error: {str(e)}"
        except Exception as e:
            return f"Error retrying pipeline: {str(e)}"
