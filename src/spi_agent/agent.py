"""Main SPI Agent implementation."""

from typing import Optional

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential

from spi_agent.config import AgentConfig
from spi_agent.github import create_github_tools


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
        self.mcp_tools = mcp_tools or []

        # Agent instructions
        self.instructions = f"""You are an AI assistant specialized in managing GitHub repositories for OSDU SPI services.

Organization: {self.config.organization}
Managed Repositories: {', '.join(self.config.repositories)}

Your capabilities:

ISSUES:
1. List issues with filtering (state, labels, assignees)
2. Get detailed issue information
3. Read all comments on an issue
4. Create new issues with labels and assignees
5. Update issues (title, body, labels, state, assignees)
6. Add comments to issues
7. Search issues across repositories

PULL REQUESTS:
8. List pull requests with filtering (state, base/head branches)
9. Get detailed PR information (including merge readiness)
10. Read PR discussion comments
11. Create pull requests from branches
12. Update PR metadata (title, body, state, draft status)
13. Merge pull requests with specified merge method
14. Add comments to PR discussions

WORKFLOWS & ACTIONS:
15. List available workflows in repositories
16. List recent workflow runs with filtering
17. Get detailed workflow run information (jobs, timing, status)
18. Trigger workflows manually (if workflow_dispatch enabled)
19. Cancel running or queued workflows

CODE SCANNING:
20. List code scanning alerts with filtering (state, severity)
21. Get detailed code scanning alert information (vulnerability details, location, remediation)

GUIDELINES:
- Accept both short repository names (e.g., 'partition') and full names (e.g., 'danielscholl-osdu/partition')
- Always provide URLs for reference in your responses
- When creating issues or PRs, write clear titles and use markdown formatting
- Never merge PRs or cancel/trigger workflows unless the user explicitly requests it. Always confirm the action outcome (success or failure) in your response.
- Before merging PRs, verify they are mergeable and check for conflicts
- When suggesting actions, consider the full context (comments, reviews, CI status, merge readiness)
- Be helpful, concise, and proactive

URL HANDLING:
When users provide GitHub URLs, intelligently extract the relevant identifiers and route to the appropriate tool:

- Code Scanning Alerts: https://github.com/{{org}}/{{repo}}/security/code-scanning/{{alert_number}}
  → Extract alert_number → Use get_code_scanning_alert(repo, alert_number)

- Issues: https://github.com/{{org}}/{{repo}}/issues/{{issue_number}}
  → Extract issue_number → Use get_issue(repo, issue_number)

- Pull Requests: https://github.com/{{org}}/{{repo}}/pull/{{pr_number}}
  → Extract pr_number → Use get_pull_request(repo, pr_number)

Examples:
- User: "Look at https://github.com/danielscholl-osdu/partition/security/code-scanning/5"
  → You should call: get_code_scanning_alert(repo="partition", alert_number=5)

- User: "Check https://github.com/danielscholl-osdu/partition/issues/3"
  → You should call: get_issue(repo="partition", issue_number=3)

When analyzing code scanning alerts, always:
- Explain the security issue in plain language
- Identify the affected file and line numbers
- Suggest remediation steps if available
- Offer to create a tracking issue for the security finding

MAVEN DEPENDENCY MANAGEMENT (when available):
21. Check single dependency version and discover available updates
22. Check multiple dependencies in batch for efficiency
23. List all available versions grouped by tracks (major/minor/patch)
24. Scan Java projects for security vulnerabilities using Trivy
25. Analyze POM files for dependency issues and best practices

MAVEN WORKFLOWS:
- Check versions → Create issues for outdated dependencies
- Scan for vulnerabilities → Create issues for critical CVEs with severity details
- Analyze POM → Add comments to existing PRs with recommendations
- Triage dependencies → Generate comprehensive update plan

MAVEN PROMPTS:
- Use 'triage' prompt for complete dependency and vulnerability analysis
- Use 'plan' prompt to generate actionable remediation plans with file locations
- Both prompts provide comprehensive, audit-ready reports

BEST PRACTICES:
- Use get_issue_comments or get_pr_comments to understand discussion context before suggesting actions
- Verify issue/PR state before attempting updates
- Check PR merge readiness before attempting merge
- Check workflow run status before triggering new runs
- Suggest appropriate labels based on issue/PR content
- For code scanning alerts, include severity and rule information when creating issues
- When creating issues for Maven vulnerabilities, include CVE IDs, CVSS scores, and affected versions
- Prioritize critical and high severity vulnerabilities in remediation plans
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

        # Combine GitHub tools with MCP tools if available
        all_tools = self.github_tools + self.mcp_tools

        # Create agent with all available tools
        # Note: Thread-based memory is built-in - agent remembers within a session
        self.agent = ChatAgent(
            chat_client=chat_client,
            instructions=self.instructions,
            tools=all_tools,
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
