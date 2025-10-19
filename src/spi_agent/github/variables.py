"""Repository variables management tools for GitHub."""

from typing import Annotated

from github import GithubException
from pydantic import Field

from spi_agent.github.base import GitHubToolsBase


class RepositoryVariableTools(GitHubToolsBase):
    """Tools for managing GitHub Actions repository variables."""

    def get_repository_variables(
        self,
        repo: Annotated[
            str, Field(description="Repository name (e.g., 'partition', not full path)")
        ],
    ) -> str:
        """
        List all GitHub Actions variables for a repository.

        This retrieves repository-level variables that are configured in GitHub Actions.
        These variables are commonly used for configuration values like UPSTREAM_REPO_URL.

        Args:
            repo: Repository name (e.g., 'partition')

        Returns:
            Formatted string listing all variables with their names and values.
            Returns error message if repository not found or access denied.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)

            # Get all repository variables
            variables = gh_repo.get_variables()

            # Collect variables into a list
            var_list = []
            for var in variables:
                var_list.append({"name": var.name, "value": var.value})

            if not var_list:
                return f"No variables found for repository '{repo_full_name}'."

            # Format output
            output_lines = [f"Variables for repository '{repo_full_name}':\n"]
            for var in var_list:
                output_lines.append(f"  {var['name']}: {var['value']}")

            return "\n".join(output_lines)

        except GithubException as e:
            if e.status == 404:
                return f"Repository '{repo}' not found or you don't have access to it."
            return f"Error retrieving variables: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Unexpected error retrieving variables: {str(e)}"

    def get_repository_variable(
        self,
        repo: Annotated[
            str, Field(description="Repository name (e.g., 'partition', not full path)")
        ],
        variable_name: Annotated[
            str, Field(description="Variable name to retrieve (e.g., 'UPSTREAM_REPO_URL')")
        ],
    ) -> str:
        """
        Get a specific GitHub Actions variable value from a repository.

        This retrieves the value of a specific repository-level variable configured
        in GitHub Actions. Commonly used to retrieve UPSTREAM_REPO_URL which points
        to the canonical GitLab upstream repository.

        Args:
            repo: Repository name (e.g., 'partition')
            variable_name: Name of the variable to retrieve (case-sensitive)

        Returns:
            Formatted string with the variable name and value.
            Returns error message if variable or repository not found.
        """
        try:
            repo_full_name = self.config.get_repo_full_name(repo)
            gh_repo = self.github.get_repo(repo_full_name)

            # Get specific variable
            variable = gh_repo.get_variable(variable_name)

            return f"{variable.name}: {variable.value}"

        except GithubException as e:
            if e.status == 404:
                # Could be repository not found or variable not found
                # Try to determine which
                try:
                    self.github.get_repo(repo_full_name)
                    return f"Variable '{variable_name}' not found in repository '{repo_full_name}'."
                except GithubException:
                    return f"Repository '{repo}' not found or you don't have access to it."
            return f"Error retrieving variable: {e.data.get('message', str(e))}"
        except Exception as e:
            return f"Unexpected error retrieving variable: {str(e)}"
