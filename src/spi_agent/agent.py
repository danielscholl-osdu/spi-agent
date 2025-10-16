"""Main SPI Agent implementation."""

from importlib import resources
from typing import Optional

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential

from spi_agent.config import AgentConfig
from spi_agent.filesystem import create_filesystem_tools
from spi_agent.github import create_github_tools
from spi_agent.middleware import (
    logging_chat_middleware,
    logging_function_middleware,
    workflow_context_agent_middleware,
)


class SPIAgent:
    """
    AI-powered GitHub Issues management agent for OSDU SPI services.

    This agent uses Microsoft Agent Framework with Azure OpenAI and PyGithub
    to provide natural language interface for GitHub issue management.
    """

    def __init__(self, config: Optional[AgentConfig] = None, mcp_tools: Optional[list] = None):
        """
        Initialize SPI Agent.

        Args:
            config: Agent configuration. If None, uses defaults from environment.
            mcp_tools: Optional list of MCP tools to integrate with agent
        """
        self.config = config or AgentConfig()
        self.github_tools = create_github_tools(self.config)
        self.filesystem_tools = create_filesystem_tools(self.config)
        self.mcp_tools = mcp_tools or []

        # Load agent instructions from system prompt
        self.instructions = self._load_system_prompt()

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

        # Combine GitHub tools, file system tools, and MCP tools
        all_tools = self.github_tools + self.filesystem_tools + self.mcp_tools

        # Create agent with all available tools and middleware
        # Note: Thread-based memory is built-in - agent remembers within a session
        # Middleware levels:
        # - Agent middleware: Intercepts agent.run() calls (workflow context injection)
        # - Function middleware: Intercepts tool calls (logging)
        # - Chat middleware: Intercepts LLM calls (logging)
        self.agent = ChatAgent(
            chat_client=chat_client,
            instructions=self.instructions,
            tools=all_tools,
            name="SPI GitHub Issues Agent",
            middleware=[workflow_context_agent_middleware],  # Agent-level middleware
            function_middleware=[logging_function_middleware],
            chat_middleware=[logging_chat_middleware],
        )

    def _load_system_prompt(self) -> str:
        """Load system prompt from prompts directory."""
        try:
            # Load system prompt file
            prompt_files = resources.files("spi_agent.copilot.prompts")
            system_prompt = (prompt_files / "system.md").read_text(encoding="utf-8")

            # Replace placeholders
            system_prompt = system_prompt.replace("{{ORGANIZATION}}", self.config.organization)
            system_prompt = system_prompt.replace("{{REPOSITORIES}}", ', '.join(self.config.repositories))

            return system_prompt
        except Exception as e:
            # Fallback to basic instructions if file not found
            return f"""You are Betty, an AI assistant for managing GitHub repositories for OSDU SPI services.
Organization: {self.config.organization}
Managed Repositories: {', '.join(self.config.repositories)}
(System prompt file not found - using fallback)"""

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
