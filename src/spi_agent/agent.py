"""Main SPI Agent implementation."""

import os
from typing import Optional

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential

from spi_agent.config import AgentConfig
from spi_agent.github_tools import create_github_tools


class SPIAgent:
    """
    AI-powered GitHub Issues management agent for OSDU SPI services.

    This agent uses Microsoft Agent Framework with Azure OpenAI and PyGithub
    to provide natural language interface for GitHub issue management.
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        """
        Initialize SPI Agent.

        Args:
            config: Agent configuration. If None, uses defaults from environment.
        """
        self.config = config or AgentConfig()
        self.github_tools = create_github_tools(self.config)

        # Agent instructions
        self.instructions = f"""You are an AI assistant specialized in managing GitHub issues for OSDU SPI services.

Organization: {self.config.organization}
Managed Repositories: {', '.join(self.config.repositories)}

Your capabilities:
1. List issues from repositories with filtering (by state, labels, assignees)
2. Get detailed information about specific issues
3. Create new issues with proper formatting
4. Update existing issues (title, body, labels, state, assignees)
5. Add comments to issues
6. Search issues across repositories

When referencing repositories, users may use short names (e.g., 'partition') or full names (e.g., 'danielscholl-osdu/partition').
Accept both formats.

When creating issues:
- Write clear, descriptive titles
- Use markdown formatting in the body
- Suggest appropriate labels based on content

When updating issues:
- Confirm what changed
- Provide the issue URL for reference

Be helpful, concise, and proactive in suggesting related actions.
"""

        # Initialize Azure OpenAI client
        # For authentication, user must run `az login` or provide API key
        client_params = {
            "credential": AzureCliCredential(),
        }

        # Add required parameters
        if self.config.azure_openai_endpoint:
            client_params["endpoint"] = self.config.azure_openai_endpoint

        if self.config.azure_openai_deployment:
            client_params["deployment_name"] = self.config.azure_openai_deployment

        if self.config.azure_openai_api_version:
            client_params["api_version"] = self.config.azure_openai_api_version

        # Handle authentication
        if self.config.azure_openai_api_key:
            # If API key provided, don't use credential
            client_params.pop("credential", None)
            client_params["api_key"] = self.config.azure_openai_api_key

        # Create chat client
        chat_client = AzureOpenAIResponsesClient(**client_params)

        # Create agent with GitHub tools
        # Note: Thread-based memory is built-in - agent remembers within a session
        self.agent = ChatAgent(
            chat_client=chat_client,
            instructions=self.instructions,
            tools=self.github_tools,
            name="SPI GitHub Issues Agent",
        )

    async def run(self, query: str) -> str:
        """
        Run agent with a natural language query.

        Args:
            query: Natural language query about GitHub issues

        Returns:
            Agent's response as string
        """
        try:
            response = await self.agent.run(query)
            return response
        except Exception as e:
            return f"Error running agent: {str(e)}"

    async def run_interactive(self) -> None:
        """
        Run agent in interactive mode (REPL).

        Allows continuous conversation with the agent.
        """
        print("=== SPI GitHub Issues Agent ===")
        print(f"Organization: {self.config.organization}")
        print(f"Repositories: {', '.join(self.config.repositories)}")
        print("\nType 'exit' or 'quit' to end the session.\n")

        while True:
            try:
                query = input("You: ").strip()

                if not query:
                    continue

                if query.lower() in ["exit", "quit", "q"]:
                    print("Goodbye!")
                    break

                response = await self.run(query)
                print(f"\nAgent: {response}\n")

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}\n")
