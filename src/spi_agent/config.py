"""Configuration management for SPI Agent."""

import os
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class AgentConfig:
    """
    Configuration for SPI Agent.

    Attributes:
        organization: GitHub organization name
        repositories: List of repository names to manage
        github_token: GitHub personal access token (optional, can use env var)
        azure_openai_endpoint: Azure OpenAI endpoint URL
        azure_openai_deployment: Azure OpenAI deployment/model name
        azure_openai_api_version: Azure OpenAI API version
        azure_openai_api_key: Azure OpenAI API key (optional if using Azure CLI auth)
    """

    organization: str = field(
        default_factory=lambda: os.getenv("SPI_AGENT_ORGANIZATION", "danielscholl-osdu")
    )

    repositories: List[str] = field(
        default_factory=lambda: os.getenv(
            "SPI_AGENT_REPOSITORIES", "partition,legal,entitlements,schema,file,storage"
        ).split(",")
    )

    github_token: Optional[str] = field(default_factory=lambda: os.getenv("GITHUB_TOKEN"))

    azure_openai_endpoint: Optional[str] = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_ENDPOINT")
    )

    azure_openai_deployment: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4")
    )

    azure_openai_api_version: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_API_VERSION")
            or os.getenv("AZURE_OPENAI_VERSION")
            or "2024-12-01-preview"
    )

    azure_openai_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_API_KEY")
    )

    # Internal Maven MCP configuration (not user-configurable)
    maven_mcp_command: str = "uvx"
    maven_mcp_args: List[str] = field(
        default_factory=lambda: [
            "--quiet",  # Suppress uvx output
            "mvn-mcp-server",
            # Note: stderr is redirected to logs/maven_mcp_*.log by QuietMCPStdioTool
        ]
    )

    def validate(self) -> None:
        """Validate configuration and raise ValueError if invalid."""
        if not self.organization:
            raise ValueError("organization is required")

        if not self.repositories or len(self.repositories) == 0:
            raise ValueError("repositories list cannot be empty")

        # Clean up repository names (strip whitespace)
        self.repositories = [repo.strip() for repo in self.repositories if repo.strip()]

    def get_repo_full_name(self, repo: str) -> str:
        """Get full repository name (org/repo)."""
        return f"{self.organization}/{repo}"

    def __post_init__(self) -> None:
        """Post-initialization validation."""
        self.validate()
