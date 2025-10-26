"""Console entry point for SPI Agent."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from . import SPIAgent
from .config import AgentConfig
from .mcp import MavenMCPManager

console = Console()


def _create_slash_command_completer():
    """Create a completer for slash commands.

    Returns a function that generates completions when called with (document, complete_event).
    """
    from prompt_toolkit.completion import Completer, Completion

    class SlashCommandCompleter(Completer):
        """Custom completer for slash commands that triggers on '/'."""

        def __init__(self):
            self.commands = {
                '/status': 'Check GitHub/GitLab repository status',
                '/test': 'Run Maven tests for service',
                '/vulns': 'Scan for security vulnerabilities',
                '/depends': 'Check for dependency updates',
                '/fork': 'Fork and clone repositories',
                '/send': 'Send GitHub PR/Issue to GitLab',
                '/clear': 'Clear conversation history',
                'help': 'Show detailed examples',
                'exit': 'Quit Betty',
            }

        def get_completions(self, document, complete_event):
            """Generate completions for the current input."""
            text = document.text_before_cursor.lower()

            if text.startswith('/'):
                # This is a slash command
                for cmd, description in self.commands.items():
                    if cmd.lower().startswith(text):
                        yield Completion(
                            cmd,
                            start_position=-len(text),
                            display=cmd,
                            display_meta=description,
                        )
            elif not text.startswith('/'):
                # This is a plain command like 'help' or 'exit'
                for cmd, description in self.commands.items():
                    if not cmd.startswith('/') and cmd.lower().startswith(text):
                        yield Completion(
                            cmd,
                            start_position=-len(text),
                            display=cmd,
                            display_meta=description,
                        )

    return SlashCommandCompleter()


def _get_separator_line(width: Optional[int] = None) -> str:
    """Get a horizontal separator line that fits the terminal width.

    Args:
        width: Optional width override. If None, uses console width.

    Returns:
        String of horizontal line characters
    """
    if width is None:
        width = console.width
    return "─" * width


def _render_full_startup_banner(
    config: AgentConfig,
    existing_repos: int,
    total_repos: int,
    maven_mcp_available: bool,
    maven_mcp_version: str = "2.3.0",
    github_connected: bool = True,
    gitlab_connected: bool = False,
) -> None:
    """Render the full startup banner with all connection info.

    Args:
        config: Agent configuration
        existing_repos: Number of repos that exist
        total_repos: Total number of configured repos
        maven_mcp_available: Whether Maven MCP is available
        maven_mcp_version: Version of Maven MCP server
        github_connected: Whether GitHub connection is valid
        gitlab_connected: Whether GitLab connection is valid
    """
    # Header
    console.print(" [cyan]◉‿◉[/cyan]  Welcome to SPI Agent")
    console.print()

    # Description
    console.print(
        " Betty helps manage OSDU services. Describe a task to get started or enter 'help' for examples."
    )
    console.print(" Betty uses AI, check for mistakes.")
    console.print()

    # Connection status (only show active connections)
    # GitHub - show green if connected, red if not
    status_dot = "[green]●[/green]" if github_connected else "[red]●[/red]"
    status_text = "Connected" if github_connected else "Not connected"
    console.print(
        f" {status_dot} {status_text} to GitHub ([blue]{config.organization}[/blue]) · "
        f"[cyan]{existing_repos}/{total_repos}[/cyan] repos available",
        highlight=False
    )

    # Maven MCP - only show if available (server started successfully)
    if maven_mcp_available:
        console.print(f" [green]●[/green] Connected to Maven MCP Server ([cyan]v{maven_mcp_version}[/cyan])", highlight=False)

    # GitLab - show green if connected, red if token exists but invalid
    if config.gitlab_token:
        # All OSDU services use community.opengroup.org (hardcoded in GitLab tools)
        gitlab_url = "https://community.opengroup.org"
        from urllib.parse import urlparse
        domain = urlparse(gitlab_url).netloc

        status_dot = "[green]●[/green]" if gitlab_connected else "[red]●[/red]"
        status_text = "Connected" if gitlab_connected else "Not connected"
        console.print(f" {status_dot} {status_text} to GitLab ([cyan]{domain}[/cyan])", highlight=False)

    console.print()


def _render_minimal_header() -> None:
    """Render minimal header after /clear command."""
    console.print(" [cyan]◉‿◉[/cyan]  SPI Agent")
    console.print()


def _get_status_bar_content(config: AgentConfig) -> tuple[str, str]:
    """Get the status bar left and right content.

    Args:
        config: Agent configuration

    Returns:
        Tuple of (left_content, right_content)
    """
    import subprocess
    from pathlib import Path

    cwd = Path.cwd()
    home = Path.home()

    # Shorten path if it's under home directory
    try:
        display_path = f"~/{cwd.relative_to(home)}"
    except ValueError:
        display_path = str(cwd)

    # Get git branch
    branch = ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1,
            cwd=cwd,
        )
        if result.returncode == 0:
            branch = f" [⎇ {result.stdout.strip()}]"
    except Exception:
        pass

    # Build status line (without markup for length calculation)
    model_display = config.azure_openai_deployment
    left_content = f" {display_path}{branch}"
    right_content = f"{model_display} · v0.1.0"

    return left_content, right_content


def _render_prompt_area(config: AgentConfig) -> None:
    """Render the status bar and top separator only.

    The prompt itself and bottom separator are handled by prompt_toolkit.

    Args:
        config: Agent configuration
    """
    left_content, right_content = _get_status_bar_content(config)
    separator = _get_separator_line()

    # Calculate spacing for right-aligned content (using plain text length)
    available_space = console.width - len(left_content) - len(right_content)
    spacing = " " * max(0, available_space)

    # Apply color markup to right content (model and version in cyan)
    # Parse the right_content to colorize: "gpt-5-mini · v0.1.0"
    parts = right_content.split(" · ")
    if len(parts) == 2:
        right_content_colored = f"[cyan]{parts[0]}[/cyan] · [cyan]{parts[1]}[/cyan]"
    else:
        right_content_colored = f"[cyan]{right_content}[/cyan]"

    # Render status bar and top separator with explicit colors
    console.print(f"{left_content}{spacing}{right_content_colored}", highlight=False)
    console.print(separator)


# Attempt to load optional copilot workflows.
COPILOT_AVAILABLE = False
copilot_module = None

try:
    from spi_agent import copilot as copilot_module  # type: ignore[attr-defined]

    COPILOT_AVAILABLE = True
except ImportError:
    try:
        import copilot as copilot_module  # type: ignore[import]

        COPILOT_AVAILABLE = True
    except ImportError:
        # Try loading from repository root when running from source tree.
        repo_root = Path(__file__).resolve().parents[2]
        candidate = repo_root / "copilot" / "copilot.py"
        if candidate.exists():
            spec = importlib.util.spec_from_file_location("copilot", candidate)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules["copilot"] = module
                spec.loader.exec_module(module)  # type: ignore[attr-defined]
                copilot_module = module
                COPILOT_AVAILABLE = True


async def handle_slash_command(command: str, agent: SPIAgent, thread) -> Optional[str]:
    """Handle slash commands in chat mode.

    Returns:
        None if command executed successfully
        "__CLEAR_CONTEXT__" signal if context should be cleared
        Error message string if command failed
    """
    parts = command[1:].split()  # Remove leading /
    if not parts:
        return None

    cmd = parts[0].lower()

    # Handle /clear command (doesn't require copilot)
    if cmd == "clear":
        from spi_agent.workflows import get_result_store
        from spi_agent.activity import get_activity_tracker
        from spi_agent.utils.terminal import clear_screen

        result_store = get_result_store()
        await result_store.clear()

        activity_tracker = get_activity_tracker()
        await activity_tracker.reset()

        clear_screen()

        # Return special signal to indicate context should be cleared
        return "__CLEAR_CONTEXT__"

    # All other commands require copilot
    if not COPILOT_AVAILABLE or copilot_module is None:
        return "Error: Copilot module not available for slash commands"

    if cmd == "fork":
        if len(parts) < 2:
            return "Usage: /fork <service> [--branch <branch>]\nExample: /fork partition,legal"

        services_arg = parts[1]

        # Import copilot config to get default branch (consistent with CLI mode)
        from spi_agent.copilot.config import config as copilot_config
        branch = copilot_config.default_branch

        # Check for --branch flag
        if "--branch" in parts:
            branch_idx = parts.index("--branch")
            if branch_idx + 1 < len(parts):
                branch = parts[branch_idx + 1]

        if not COPILOT_AVAILABLE or copilot_module is None:
            return "Error: Copilot module not available for service validation"

        services = copilot_module.parse_services(services_arg)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            return f"Error: Invalid service(s): {', '.join(invalid)}"

        # Use workflow function to store results for agent context
        from spi_agent.workflows.vulns_workflow import run_fork_workflow

        result = await run_fork_workflow(services=services, branch=branch)
        return None

    if cmd == "status":
        # Parse --platform flag (default: github)
        platform = "github"
        if "--platform" in parts:
            platform_idx = parts.index("--platform")
            if platform_idx + 1 < len(parts):
                platform = parts[platform_idx + 1].lower()
                if platform not in ["github", "gitlab"]:
                    return f"Error: Invalid platform '{platform}'. Use 'github' or 'gitlab'"

        # Parse --provider flag (for GitLab)
        providers = None
        if "--provider" in parts:
            provider_idx = parts.index("--provider")
            if provider_idx + 1 < len(parts):
                providers = parts[provider_idx + 1]

        # Setup providers for GitLab
        if platform == "gitlab" and providers is None:
            providers = "Azure,Core"  # Default for GitLab

        # Parse --actions flag
        show_actions = "--actions" in parts

        # Auto-detect services if not specified
        services_arg = None
        available_services = None

        # Check if service is specified (not a flag)
        if len(parts) >= 2 and not parts[1].startswith("--"):
            services_arg = parts[1]
        else:
            # Auto-detect available services
            config = AgentConfig()
            available_services = await detect_available_services(config)

            if not available_services:
                return "Error: No available services found in ./repos/\nRun 'spi fork --service all' to clone repositories"

            # Display auto-detection message
            console.print(f"[cyan]{format_auto_detection_message(available_services)}[/cyan]")
            console.print()

        services = copilot_module.parse_services(services_arg, available_services=available_services)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            return f"Error: Invalid service(s): {', '.join(invalid)}"

        # Use workflow function to store results for agent context
        from spi_agent.workflows.status_workflow import run_status_workflow

        # Convert providers string to list for GitLab
        providers_list = None
        if platform == "gitlab" and providers:
            providers_list = [p.strip() for p in providers.split(",")]

        result = await run_status_workflow(
            services=services,
            platform=platform,
            providers=providers_list,
            show_actions=show_actions,
        )
        return None

    if cmd == "test":
        # Parse --provider flag
        provider = "core,azure"  # Default to core + azure coverage
        if "--provider" in parts:
            provider_idx = parts.index("--provider")
            if provider_idx + 1 < len(parts):
                provider = parts[provider_idx + 1]

        if not COPILOT_AVAILABLE or copilot_module is None:
            return "Error: Copilot module not available for service validation"

        # Auto-detect services if not specified
        services_arg = None
        available_services = None

        # Check if service is specified (not a flag)
        if len(parts) >= 2 and not parts[1].startswith("--"):
            services_arg = parts[1]
        else:
            # Auto-detect available services
            config = AgentConfig()
            available_services = await detect_available_services(config)

            if not available_services:
                return "Error: No available services found in ./repos/\nRun 'spi fork --service all' to clone repositories"

            # Display auto-detection message
            console.print(f"[cyan]{format_auto_detection_message(available_services)}[/cyan]")
            console.print()

        services = copilot_module.parse_services(services_arg, available_services=available_services)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            return f"Error: Invalid service(s): {', '.join(invalid)}"

        # Use workflow function to store results for agent context
        from spi_agent.workflows.vulns_workflow import run_test_workflow

        result = await run_test_workflow(services=services, provider=provider)
        return None

    if cmd == "vulns":
        create_issue = "--create-issue" in parts

        # Parse --severity flag (empty list = server scans all severities)
        severity_filter = []
        if "--severity" in parts:
            severity_idx = parts.index("--severity")
            if severity_idx + 1 < len(parts):
                severity_arg = parts[severity_idx + 1]
                severity_filter = [s.strip().lower() for s in severity_arg.split(",")]

        # Parse --providers flag (default: azure; core is always included)
        providers = ["azure"]
        if "--providers" in parts:
            providers_idx = parts.index("--providers")
            if providers_idx + 1 < len(parts):
                providers_arg = parts[providers_idx + 1]
                providers = [p.strip().lower() for p in providers_arg.split(",")]

        # Parse --include-testing flag
        include_testing = "--include-testing" in parts

        try:
            prompt_file = copilot_module.get_prompt_file("vulns.md")
        except FileNotFoundError as exc:  # pragma: no cover - packaging guard
            return f"Error: {exc}"

        # Auto-detect services if not specified
        services_arg = None
        available_services = None

        # Check if service is specified (not a flag)
        if len(parts) >= 2 and not parts[1].startswith("--"):
            services_arg = parts[1]
        else:
            # Auto-detect available services
            config = AgentConfig()
            available_services = await detect_available_services(config)

            if not available_services:
                return "Error: No available services found in ./repos/\nRun 'spi fork --service all' to clone repositories"

            # Display auto-detection message
            console.print(f"[cyan]{format_auto_detection_message(available_services)}[/cyan]")
            console.print()

        services = copilot_module.parse_services(services_arg, available_services=available_services)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            return f"Error: Invalid service(s): {', '.join(invalid)}"

        # Use workflow function to store results for agent context
        from spi_agent.workflows.vulns_workflow import run_vulns_workflow

        result = await run_vulns_workflow(
            agent=agent,
            services=services,
            severity_filter=severity_filter,
            providers=providers,
            include_testing=include_testing,
            create_issue=create_issue,
        )
        return None

    if cmd == "send":
        if len(parts) < 2:
            return (
                "Usage: /send <service> --pr <number> | --issue <number> | --pr <pr_num> --issue <issue_num>\n\n"
                "Examples:\n"
                "  /send partition --pr 5\n"
                "  /send legal --issue 10\n"
                "  /send partition --pr 5 --issue 10\n\n"
                "Sends GitHub Pull Requests and/or Issues to the corresponding GitLab project."
            )

        service = parts[1]

        # Validate service
        if not COPILOT_AVAILABLE or copilot_module is None:
            return "Error: Copilot module not available for service validation"

        if service not in copilot_module.SERVICES:
            return f"Error: Invalid service '{service}'"

        # Parse --pr and --issue flags
        pr_number = None
        issue_number = None

        if "--pr" in parts:
            pr_idx = parts.index("--pr")
            if pr_idx + 1 < len(parts):
                try:
                    pr_number = int(parts[pr_idx + 1])
                except ValueError:
                    return "Error: --pr requires a numeric PR number"
            else:
                return "Error: --pr requires a PR number"

        if "--issue" in parts:
            issue_idx = parts.index("--issue")
            if issue_idx + 1 < len(parts):
                try:
                    issue_number = int(parts[issue_idx + 1])
                except ValueError:
                    return "Error: --issue requires a numeric issue number"
            else:
                return "Error: --issue requires an issue number"

        # Require at least one of --pr or --issue
        if pr_number is None and issue_number is None:
            return "Error: Must specify --pr or --issue"

        # Import send workflow functions
        from spi_agent.workflows.send_workflow import send_pr_to_gitlab, send_issue_to_gitlab

        # Execute send operations
        results = []

        if pr_number is not None:
            console.print(f"[yellow]Sending GitHub PR #{pr_number} to GitLab...[/yellow]")
            pr_result = send_pr_to_gitlab(service, pr_number, agent.config)
            results.append(pr_result)

            if "✓" in pr_result:
                console.print(f"[green]{pr_result}[/green]\n")
            else:
                console.print(f"[red]{pr_result}[/red]\n")

        if issue_number is not None:
            console.print(f"[yellow]Sending GitHub Issue #{issue_number} to GitLab...[/yellow]")
            issue_result = send_issue_to_gitlab(service, issue_number, agent.config)
            results.append(issue_result)

            if "✓" in issue_result:
                console.print(f"[green]{issue_result}[/green]\n")
            else:
                console.print(f"[red]{issue_result}[/red]\n")

        # Display summary if both were sent
        if pr_number is not None and issue_number is not None:
            console.print("\n[bold]Send Summary:[/bold]")
            console.print(f"  PR #{pr_number}: {'✓ Success' if '✓' in results[0] else '✗ Failed'}")
            console.print(f"  Issue #{issue_number}: {'✓ Success' if '✓' in results[1] else '✗ Failed'}")

        return None

    if cmd == "depends":
        # Parse --providers flag (default: core,azure)
        providers = ["core", "azure"]
        if "--providers" in parts:
            providers_idx = parts.index("--providers")
            if providers_idx + 1 < len(parts):
                providers_arg = parts[providers_idx + 1]
                providers = [p.strip() for p in providers_arg.split(",")]

        # Parse --include-testing flag
        include_testing = "--include-testing" in parts

        # Parse --create-issue flag
        create_issue = "--create-issue" in parts

        if not COPILOT_AVAILABLE or copilot_module is None:
            return "Error: Copilot module not available for service validation"

        # Auto-detect services if not specified
        services_arg = None
        available_services = None

        # Check if service is specified (not a flag)
        if len(parts) >= 2 and not parts[1].startswith("--"):
            services_arg = parts[1]
        else:
            # Auto-detect available services
            config = AgentConfig()
            available_services = await detect_available_services(config)

            if not available_services:
                return "Error: No available services found in ./repos/\nRun 'spi fork --service all' to clone repositories"

            # Display auto-detection message
            console.print(f"[cyan]{format_auto_detection_message(available_services)}[/cyan]")
            console.print()

        services = copilot_module.parse_services(services_arg, available_services=available_services)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            return f"Error: Invalid service(s): {', '.join(invalid)}"

        # Use workflow function to store results for agent context
        from spi_agent.workflows.depends_workflow import run_depends_workflow

        result = await run_depends_workflow(
            agent=agent,
            services=services,
            providers=providers,
            include_testing=include_testing,
            create_issue=create_issue,
        )
        return None

    return f"Unknown command: /{cmd}\nAvailable: /fork, /status, /test, /vulns, /send, /depends (or type 'help')"


def _render_help() -> None:
    """Display help information for chat mode."""
    help_text = """
**Natural Language Queries:**

**GitHub Issues:**
- "List issues in partition"
- "Show me issues labeled bug in legal"
- "Tell me about issue #2 in partition"
- "Search for CodeQL across all repositories"
- "Create an issue in partition: Fix authentication bug"
- "Add comment to issue #2 in partition: This is resolved"

**Maven Dependencies** (when enabled):
- "Check if spring-core 5.3.0 has any updates available"
- "Scan partition service for security vulnerabilities"
- "Show all available versions of commons-lang3"
- "Analyze the pom.xml in partition for issues"
- "Run vulnerability scan for partition and create issues for critical CVEs"

**Commands:**
- `/fork <service>` - Fork service repository
- `/fork <service>,<service>` - Fork multiple repositories
- `/fork <service> --branch develop` - Fork with custom branch
- `/status <service>` - Check GitHub status for service (default)
- `/status <service>,<service>` - Check status for multiple repos
- `/status <service> --platform gitlab` - Check GitLab status (providers: Azure,Core)
- `/status <service> --platform gitlab --provider azure` - GitLab status (azure only)
- `/test <service>` - Run Maven tests (default: core,azure profiles)
- `/test <service> --provider aws` - Run tests with specific provider
- `/vulns <service>` - Run dependency/vulnerability analysis
- `/vulns <service> --create-issue` - Scan and create issues for vulnerabilities
- `/vulns <service> --severity critical,high` - Filter by severity
- `/depends <service>` - Analyze dependency updates (default: azure provider)
- `/depends <service> --providers azure,core` - Check updates for specific providers
- `/depends <service> --create-issue` - Create issues for available updates
- `/send <service> --pr <number>` - Send GitHub PR to GitLab as Merge Request
- `/send <service> --issue <number>` - Send GitHub Issue to GitLab
- `/send <service> --pr <num> --issue <num>` - Send both PR and Issue
- `clear` - Clear conversation context and reset chat session
- `help` - Show this help
"""
    console.print(Panel(Markdown(help_text), title="💡 Help", border_style="yellow"))
    console.print()


async def _validate_github_connection(config: AgentConfig) -> bool:
    """Validate that we can actually connect to GitHub.

    Args:
        config: Agent configuration

    Returns:
        True if GitHub connection works, False otherwise
    """
    import subprocess

    try:
        # Use gh auth status to check if we're authenticated
        result = await asyncio.to_thread(
            subprocess.run,
            ["gh", "auth", "status"],
            capture_output=True,
            timeout=5
        )
        # gh auth status returns 0 if authenticated
        return result.returncode == 0
    except Exception:
        return False


async def _validate_gitlab_connection(config: AgentConfig) -> bool:
    """Validate that we can actually connect to GitLab.

    Args:
        config: Agent configuration

    Returns:
        True if GitLab connection works, False otherwise
    """
    if not config.gitlab_token:
        return False

    try:
        import aiohttp

        # All OSDU services use community.opengroup.org (hardcoded in GitLab tools)
        gitlab_url = "https://community.opengroup.org"
        url = f"{gitlab_url}/api/v4/user"
        headers = {"PRIVATE-TOKEN": config.gitlab_token}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                return response.status == 200
    except Exception:
        return False


async def _count_existing_repos(config: AgentConfig) -> int:
    """Count how many configured repositories actually exist in GitHub.

    Args:
        config: Agent configuration with organization and repositories

    Returns:
        Number of repositories that exist
    """
    from spi_agent.github.direct_client import GitHubDirectClient

    client = GitHubDirectClient(config)

    # Check all repos in parallel
    async def check_repo(service: str) -> bool:
        """Check if a single repo exists."""
        repo_name = config.get_repo_full_name(service)
        try:
            repo_info = await client._get_repo_info(repo_name)
            return repo_info.get("exists", False)
        except:
            return False

    # Check all repos concurrently
    results = await asyncio.gather(
        *[check_repo(service) for service in config.repositories],
        return_exceptions=True
    )

    # Count successful checks (True values, not exceptions)
    return sum(1 for r in results if r is True)


async def detect_available_services(config: AgentConfig) -> List[str]:
    """Detect services that exist both locally and on GitHub.

    This function performs a dual check:
    1. Local existence: Service directory exists at ./repos/<service>/
    2. Remote existence: Repository exists in the configured GitHub organization

    Only services passing both checks are returned. This ensures commands
    operate only on services that are actually available and accessible.

    Args:
        config: Agent configuration with organization and repositories

    Returns:
        List of available service names (sorted alphabetically)
    """
    from spi_agent.github.direct_client import GitHubDirectClient

    repos_dir = Path("./repos")

    # Check if repos directory exists
    if not repos_dir.exists() or not repos_dir.is_dir():
        return []

    # Get list of local service directories
    try:
        local_services = [
            item.name
            for item in repos_dir.iterdir()
            if item.is_dir() and item.name in config.repositories
        ]
    except (OSError, PermissionError):
        # Handle permission errors or other file system issues gracefully
        return []

    if not local_services:
        return []

    # Verify each local service exists on GitHub
    client = GitHubDirectClient(config)

    async def check_service(service: str) -> tuple[str, bool]:
        """Check if a service exists on GitHub."""
        repo_name = config.get_repo_full_name(service)
        try:
            repo_info = await client._get_repo_info(repo_name)
            return (service, repo_info.get("exists", False))
        except:
            return (service, False)

    # Check all local services concurrently
    results = await asyncio.gather(
        *[check_service(service) for service in local_services],
        return_exceptions=True
    )

    # Filter to only services that exist on GitHub (not exceptions)
    available_services = [
        service
        for service, exists in results
        if not isinstance((service, exists), BaseException) and exists
    ]

    return sorted(available_services)


def format_auto_detection_message(services: List[str]) -> str:
    """Format a user-friendly message about auto-detected services.

    Args:
        services: List of detected service names

    Returns:
        Formatted message string
    """
    if not services:
        return "No available services found in ./repos/"

    count = len(services)
    service_word = "service" if count == 1 else "services"
    service_list = ", ".join(services)

    return f"Auto-detected {count} {service_word}: {service_list}"


async def run_chat_mode(quiet: bool = False, verbose: bool = False) -> int:
    """Run interactive chat mode.

    Args:
        quiet: Suppress status display
        verbose: Show verbose execution tree with all phases
    """
    config = AgentConfig()

    # Set execution context for interactive mode
    from spi_agent.display import ExecutionContext, set_execution_context

    execution_context = ExecutionContext(
        is_interactive=True, show_visualization=not quiet
    )
    set_execution_context(execution_context)

    # Initialize Maven MCP if enabled
    maven_mcp = MavenMCPManager(config)

    async with maven_mcp:
        # Create agent with Maven MCP tools if available
        agent = SPIAgent(config, mcp_tools=maven_mcp.tools)

        if not quiet:
            # Validate connections and count existing repositories (run in parallel)
            github_connected, gitlab_connected, existing_count = await asyncio.gather(
                _validate_github_connection(config),
                _validate_gitlab_connection(config),
                _count_existing_repos(config),
            )
            total_count = len(config.repositories)

            # Render full startup banner with connection status
            _render_full_startup_banner(
                config=config,
                existing_repos=existing_count,
                total_repos=total_count,
                maven_mcp_available=maven_mcp.is_available,
                maven_mcp_version="2.3.0",
                github_connected=github_connected,
                gitlab_connected=gitlab_connected,
            )

            # Render prompt area
            _render_prompt_area(config)

        thread = agent.agent.get_new_thread()

        # Use prompt_toolkit for better terminal handling (backspace, arrows, history)
        session = None
        prompt_tokens = None
        patch_stdout = None
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.history import InMemoryHistory
            from prompt_toolkit.styles import Style as PromptStyle
            from prompt_toolkit.output import ColorDepth
            from prompt_toolkit.formatted_text import FormattedText, HTML
            from prompt_toolkit.patch_stdout import patch_stdout as pt_patch_stdout

            # Create custom slash command completer
            completer = _create_slash_command_completer()

            # Create session with history and command completion
            session = PromptSession(
                history=InMemoryHistory(),
                completer=completer,
                complete_while_typing=True,  # Show completions as user types
                style=PromptStyle.from_dict({
                    'prompt': 'ansicyan',
                    'completion-menu': 'bg:#262626 #ffffff',
                    'completion-menu.completion': 'bg:#262626 #00ffff',  # cyan text
                    'completion-menu.completion.current': 'bg:#00ffff #000000',  # current selection
                    'completion-menu.meta.completion': 'bg:#262626 #6c6c6c',  # dim description
                    'completion-menu.meta.completion.current': 'bg:#00ffff #000000',
                }),
                enable_history_search=True,
                mouse_support=False,  # Disable mouse to avoid conflicts
                color_depth=ColorDepth.TRUE_COLOR,
                placeholder=HTML('<ansibrightblack>  Type / then Tab for commands, or ask naturally</ansibrightblack>'),
            )
            prompt_tokens = FormattedText([('class:prompt', '> ')])
            patch_stdout = pt_patch_stdout
            use_prompt_toolkit = True
        except ImportError:
            # Fallback to basic input if prompt_toolkit not available
            use_prompt_toolkit = False
            console.print("[dim]prompt_toolkit not available; using basic input (no color styling).[/dim]\n")

        while True:
            try:
                if use_prompt_toolkit:
                    # Use prompt_toolkit's async prompt so arrow keys/history work consistently
                    assert session is not None  # for type checkers
                    assert prompt_tokens is not None
                    assert patch_stdout is not None

                    with patch_stdout(raw=True):
                        query = await session.prompt_async(prompt_tokens)
                    query = query.strip()
                else:
                    # Fallback to standard input running in a background thread so
                    # readline-based editing (arrows, backspace) remains usable.
                    prompt_text = "> "
                    query = await asyncio.to_thread(input, prompt_text)
                    query = query.strip()

                if not query:
                    continue

                if query.lower() in ["exit", "quit", "q"]:
                    console.print("\n[yellow]Goodbye![/yellow]")
                    break

                if query.lower() in ["help", "/help"]:
                    _render_help()
                    # Print separator after help (dimmed)
                    separator = _get_separator_line()
                    console.print(separator, style="dim")
                    continue

                if query.startswith("/"):
                    # Handle slash commands (includes /clear which doesn't require copilot)
                    result = await handle_slash_command(query, agent, thread)

                    # Check for special __CLEAR_CONTEXT__ signal
                    if result == "__CLEAR_CONTEXT__":
                        # Reprint minimal header and prompt area
                        if not quiet:
                            _render_minimal_header()
                            _render_prompt_area(config)

                        # Replace thread
                        thread = agent.agent.get_new_thread()
                        continue

                    # Handle errors
                    if result:
                        console.print(f"\n[red]{result}[/red]\n")

                    # Print separator after slash command (dimmed)
                    separator = _get_separator_line()
                    console.print(separator, style="dim")
                    continue

                # Use execution tree display if visualization enabled, otherwise simple status
                if execution_context.show_visualization:
                    from spi_agent.display.execution_tree import ExecutionTreeDisplay, DisplayMode
                    from spi_agent.display.interrupt_handler import InterruptHandler

                    # Create interrupt handler for graceful cancellation
                    interrupt_handler = InterruptHandler()

                    # Choose display mode based on verbose flag
                    display_mode = DisplayMode.VERBOSE if verbose else DisplayMode.MINIMAL

                    # Create execution tree display
                    # Show completion summary in MINIMAL mode (not in VERBOSE - redundant with phase tree)
                    tree_display = ExecutionTreeDisplay(
                        console=console,
                        display_mode=display_mode,
                        show_completion_summary=not verbose  # Show in MINIMAL, not in VERBOSE
                    )

                    try:
                        # Start tree display (event processing runs in background)
                        await tree_display.start()

                        # Ensure EventEmitter sees interactive mode flag right before spawning task
                        # This is critical because agent framework tasks need to see this state
                        from spi_agent.display.events import get_event_emitter
                        emitter = get_event_emitter()
                        emitter.set_interactive_mode(True, execution_context.show_visualization)

                        # Create agent query task (will inherit interactive mode from EventEmitter)
                        agent_task = asyncio.create_task(agent.agent.run(query, thread=thread))
                        interrupt_handler.register_cancellable_task(agent_task)

                        # Wait for agent task
                        result = await agent_task

                    except asyncio.CancelledError:
                        # Operation was cancelled (Ctrl+C)
                        console.print("\n[yellow]Operation cancelled[/yellow]\n")
                        continue
                    finally:
                        # Stop tree display
                        await tree_display.stop()

                        # Reset interactive mode flag after task completes
                        emitter.set_interactive_mode(False, False)

                else:
                    # Fallback to simple status display (--quiet mode)
                    from spi_agent.activity import get_activity_tracker

                    activity_tracker = get_activity_tracker()

                    status_handle = console.status("[bold blue]Thinking...[/bold blue]", spinner="dots")
                    status_handle.start()

                    async def update_status():
                        """Background task to poll activity tracker and update status."""
                        try:
                            while True:
                                activity = activity_tracker.get_current()
                                status_handle.update(f"[bold blue]{activity}[/bold blue]")
                                await asyncio.sleep(0.1)  # Update 10x per second
                        except asyncio.CancelledError:
                            pass

                    # Start background status updater
                    update_task = asyncio.create_task(update_status())

                    try:
                        result = await agent.agent.run(query, thread=thread)
                    finally:
                        # Stop status updater and clear status line
                        update_task.cancel()
                        try:
                            await update_task
                        except asyncio.CancelledError:
                            pass
                        status_handle.stop()

                result_text = str(result) if not isinstance(result, str) else result

                # Render response with minimal Betty-style formatting
                console.print()

                # Render with Betty's face prefix (preserving markdown formatting)
                from rich.text import Text
                prefix = Text("◉‿◉ ", style="cyan")

                # Render the markdown content
                markdown_content = Markdown(result_text)

                # Print prefix on same line, then markdown
                console.print(prefix, end="")
                console.print(markdown_content)
                console.print()

                # Re-render separator for next input (dimmed to reduce visual clutter in scrollback)
                separator = _get_separator_line()
                console.print(separator, style="dim")

            except EOFError:
                console.print("\n[yellow]Goodbye![/yellow]")
                break
            except KeyboardInterrupt:
                console.print("\n\n[yellow]Interrupted. Goodbye![/yellow]")
                break
            except Exception as exc:  # pylint: disable=broad-except
                console.print(f"\n[red]Error:[/red] {exc}\n", style="bold red")

    return 0


async def run_single_query(prompt: str, quiet: bool = False, verbose: bool = False) -> int:
    """Run a single query with Rich output.

    Args:
        prompt: Query to execute
        quiet: Suppress output headers
        verbose: Show detailed execution tree with tool calls
    """
    # CRITICAL: Set execution context FIRST, before any agent initialization
    # This ensures EventEmitter has interactive mode set when SPIAgent initializes
    if verbose:
        from spi_agent.display import ExecutionContext, set_execution_context
        from spi_agent.display.events import get_event_emitter

        execution_context = ExecutionContext(
            is_interactive=True, show_visualization=True
        )
        set_execution_context(execution_context)

        # Also set on EventEmitter immediately (before agent initialization)
        emitter = get_event_emitter()
        emitter.set_interactive_mode(True, True)

    # Now safe to create agent (will see interactive mode if verbose=True)
    config = AgentConfig()

    # Initialize Maven MCP if enabled
    maven_mcp = MavenMCPManager(config)

    async with maven_mcp:
        # Create agent with Maven MCP tools if available
        agent = SPIAgent(config, mcp_tools=maven_mcp.tools)

        # Show header for both default and verbose modes (not quiet)
        if not quiet:
            maven_status = "enabled" if maven_mcp.is_available else "disabled"
            console.print(" [cyan]◉‿◉[/cyan]  SPI Agent")
            console.print(f" Model: [cyan]{agent.config.azure_openai_deployment}[/cyan] · Maven MCP: [cyan]{maven_status}[/cyan]")

        try:
            if verbose:
                # Use execution tree display for verbose mode
                from spi_agent.display.execution_tree import ExecutionTreeDisplay, DisplayMode
                from spi_agent.display.events import get_event_emitter

                # Use VERBOSE mode to show all details when --verbose flag is used
                tree_display = ExecutionTreeDisplay(console=console, display_mode=DisplayMode.VERBOSE)

                # Create a new thread for the single query
                thread = agent.agent.get_new_thread()

                async with tree_display:
                    # Interactive mode already set at function start
                    result = await agent.agent.run(prompt, thread=thread)

            elif not quiet:
                # Use MINIMAL execution tree display for normal mode (non-quiet, non-verbose)
                from spi_agent.display import ExecutionContext, set_execution_context
                from spi_agent.display.execution_tree import ExecutionTreeDisplay, DisplayMode
                from spi_agent.display.events import get_event_emitter

                # Set execution context for MINIMAL display
                execution_context = ExecutionContext(
                    is_interactive=True, show_visualization=True
                )
                set_execution_context(execution_context)

                # Enable event emitter interactive mode
                emitter = get_event_emitter()
                emitter.set_interactive_mode(True, True)

                try:
                    # Use MINIMAL mode to show only active phase, without completion summary
                    tree_display = ExecutionTreeDisplay(
                        console=console,
                        display_mode=DisplayMode.MINIMAL,
                        show_completion_summary=False  # Don't show completion line in prompt mode
                    )

                    async with tree_display:
                        # Create a new thread for the single query
                        thread = agent.agent.get_new_thread()
                        result = await agent.agent.run(prompt, thread=thread)
                finally:
                    # Reset interactive mode
                    emitter.set_interactive_mode(False, False)

            else:
                # Quiet mode - no display, just execute
                thread = agent.agent.get_new_thread()
                result = await agent.agent.run(prompt, thread=thread)

            result_text = str(result) if not isinstance(result, str) else result

            if quiet:
                console.print(result_text)
            else:
                # Add blank line before separator (for spacing after header or verbose tree)
                console.print()
                # Print separator with Betty face
                width = console.width
                label = " ◉‿◉ "
                label_len = len(label)
                left_len = (width - label_len) // 2
                right_len = width - left_len - label_len
                console.print(f"{'─' * left_len}[cyan]{label}[/cyan]{'─' * right_len}")
                console.print()
                # Print markdown result directly
                console.print(Markdown(result_text))

            return 0

        except Exception as exc:  # pylint: disable=broad-except
            console.print(f"[red]Error:[/red] {exc}", style="bold red")
            return 1

        finally:
            # Reset EventEmitter interactive mode if it was set
            if verbose:
                from spi_agent.display.events import get_event_emitter
                emitter = get_event_emitter()
                emitter.set_interactive_mode(False, False)


def build_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="SPI Agent - Unified CLI for OSDU SPI Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  (none)              Interactive chat mode (default)
  -p PROMPT           Single query mode
  fork                Fork and initialize repositories (requires copilot)
  status              Check GitHub/GitLab status (requires copilot)
  test                Run Maven tests for services (requires copilot)
  vulns               Run dependency/vulnerability analysis (requires copilot)
  depends             Analyze dependency updates (requires copilot)
  send                Send GitHub PRs/Issues to GitLab (requires copilot)

Examples:
  spi                                    # Interactive chat
  spi -p "List issues in partition"      # One-shot query
  spi fork --service partition          # Fork repos
  spi status --service partition        # Check GitHub status (default)
  spi status --service partition --platform gitlab  # Check GitLab status
  spi test --service partition          # Run Maven tests
  spi vulns --service partition         # Run vulnerability analysis
  spi depends --service partition       # Analyze dependency updates
  spi send --service partition --pr 5   # Send PR to GitLab
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    if COPILOT_AVAILABLE:
        # Import copilot config to get default branch
        from spi_agent.copilot.config import config as copilot_config

        fork_parser = subparsers.add_parser(
            "fork",
            help="Fork and initialize OSDU SPI service repositories",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        fork_parser.add_argument(
            "--service",
            "-s",
            required=True,
            help="Service name(s): 'all', single name, or comma-separated list (required)",
        )
        fork_parser.add_argument(
            "--branch",
            "-b",
            default=copilot_config.default_branch,
            help=f"Branch name (default: {copilot_config.default_branch})",
        )

        status_parser = subparsers.add_parser(
            "status",
            help="Get GitHub or GitLab status for OSDU SPI service repositories",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        status_parser.add_argument(
            "--service",
            "-s",
            default=None,
            help="Service name(s): 'all', single name, or comma-separated list (default: auto-detect available services)",
        )
        status_parser.add_argument(
            "--platform",
            choices=["github", "gitlab"],
            default="github",
            help="Platform to query (default: github)",
        )
        status_parser.add_argument(
            "--provider",
            help="Provider label(s) for filtering (GitLab only, default: Azure,Core)",
        )
        status_parser.add_argument(
            "--actions",
            action="store_true",
            help="Show detailed workflow/pipeline action status table (hidden by default)",
        )

        test_parser = subparsers.add_parser(
            "test",
            help="Run Maven tests for OSDU SPI service repositories",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        test_parser.add_argument(
            "--service",
            "-s",
            default=None,
            help="Service name(s): 'all', single name, or comma-separated list (default: auto-detect available services)",
        )
        test_parser.add_argument(
            "--provider",
            "-p",
            default="core,azure",
            help="Cloud provider(s): azure, aws, gc, ibm, core, all (default: core,azure)",
        )

        vulns_parser = subparsers.add_parser(
            "vulns",
            help="Run Maven dependency and vulnerability analysis",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        vulns_parser.add_argument(
            "--service",
            "-s",
            default=None,
            help="Service name(s): 'all', single name, or comma-separated list (default: auto-detect available services)",
        )
        vulns_parser.add_argument(
            "--create-issue",
            action="store_true",
            help="Create GitHub tracking issues for critical/high findings",
        )
        vulns_parser.add_argument(
            "--severity",
            default=None,
            help="Severity filter: critical, high, medium, low (default: all severities)",
        )
        vulns_parser.add_argument(
            "--providers",
            default="azure",
            help="Provider(s) to include: azure, aws, gc, ibm, core, or comma-separated list (default: azure)",
        )
        vulns_parser.add_argument(
            "--include-testing",
            action="store_true",
            help="Include testing modules in analysis (default: excluded)",
        )

        send_parser = subparsers.add_parser(
            "send",
            help="Send GitHub Pull Requests and Issues to GitLab",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        send_parser.add_argument(
            "--service",
            "-s",
            required=True,
            help="Service name (e.g., 'partition', 'legal')",
        )
        send_parser.add_argument(
            "--pr",
            type=int,
            help="GitHub Pull Request number to send",
        )
        send_parser.add_argument(
            "--issue",
            type=int,
            help="GitHub Issue number to send",
        )

        depends_parser = subparsers.add_parser(
            "depends",
            help="Analyze Maven dependencies for available updates",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        depends_parser.add_argument(
            "--service",
            "-s",
            default=None,
            help="Service name(s): 'all', single name, or comma-separated list (default: auto-detect available services)",
        )
        depends_parser.add_argument(
            "--providers",
            default="core,azure",
            help="Provider(s) to include: core, azure, aws, gcp, or comma-separated list (default: core,azure)",
        )
        depends_parser.add_argument(
            "--include-testing",
            action="store_true",
            help="Include testing modules in analysis (default: excluded)",
        )
        depends_parser.add_argument(
            "--create-issue",
            action="store_true",
            help="Create GitHub tracking issues for available updates",
        )

    parser.add_argument(
        "-p",
        "--prompt",
        help="Natural language query (omit for interactive chat mode)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Minimal output",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed execution tree with tool calls (single-query mode only)",
    )

    return parser


async def async_main(args: Optional[list[str]] = None) -> int:
    """Entry point that supports asyncio execution."""
    parser = build_parser()
    parsed = parser.parse_args(args=args)

    if parsed.command == "fork":
        if not COPILOT_AVAILABLE:
            console.print("[red]Error:[/red] Copilot module not available", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        services = copilot_module.parse_services(parsed.service)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            console.print(f"[red]Error:[/red] Invalid service(s): {', '.join(invalid)}", style="bold red")
            return 1

        # Use CopilotRunner with direct API mode (fast, no AI)
        runner = copilot_module.CopilotRunner(services, parsed.branch)
        return await runner.run_direct()

    if parsed.command == "status":
        if not COPILOT_AVAILABLE:
            console.print("[red]Error:[/red] Copilot module not available", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        # Determine platform
        platform = parsed.platform

        # Auto-detect available services if --service not specified
        available_services = None
        if parsed.service is None:
            config = AgentConfig()
            available_services = await detect_available_services(config)

            if not available_services:
                console.print("[red]Error:[/red] No available services found in ./repos/", style="bold red")
                console.print("[dim]Run 'spi fork --service all' to clone repositories[/dim]")
                return 1

            # Display auto-detection message
            console.print(f"[cyan]{format_auto_detection_message(available_services)}[/cyan]")
            console.print()

        services = copilot_module.parse_services(parsed.service, available_services=available_services)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            console.print(f"[red]Error:[/red] Invalid service(s): {', '.join(invalid)}", style="bold red")
            return 1

        # Extract show_actions flag
        show_actions = parsed.actions if hasattr(parsed, 'actions') else False

        # Setup providers for GitLab
        if platform == "gitlab":
            provider_arg = parsed.provider if parsed.provider else "Azure,Core"
            providers = [p.strip() for p in provider_arg.split(",")]
            runner = copilot_module.StatusRunner(None, services, providers, show_actions)
        else:
            runner = copilot_module.StatusRunner(None, services, None, show_actions)

        # Use StatusRunner with direct API mode (fast, no AI)
        return await runner.run_direct()

    if parsed.command == "test":
        if not COPILOT_AVAILABLE:
            console.print("[red]Error:[/red] Copilot module not available", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        # Auto-detect available services if --service not specified
        available_services = None
        if parsed.service is None:
            config = AgentConfig()
            available_services = await detect_available_services(config)

            if not available_services:
                console.print("[red]Error:[/red] No available services found in ./repos/", style="bold red")
                console.print("[dim]Run 'spi fork --service all' to clone repositories[/dim]")
                return 1

            # Display auto-detection message
            console.print(f"[cyan]{format_auto_detection_message(available_services)}[/cyan]")
            console.print()

        services = copilot_module.parse_services(parsed.service, available_services=available_services)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            console.print(f"[red]Error:[/red] Invalid service(s): {', '.join(invalid)}", style="bold red")
            return 1

        # Use DirectTestRunner for fast, reliable test execution
        from spi_agent.copilot.runners.direct_test_runner import DirectTestRunner

        runner = DirectTestRunner(
            services=services,
            provider=parsed.provider,
        )
        return await runner.run()

    if parsed.command == "vulns":
        if not COPILOT_AVAILABLE:
            console.print("[red]Error:[/red] Copilot module not available", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        try:
            prompt_file = copilot_module.get_prompt_file("vulns.md")
        except FileNotFoundError as exc:
            console.print(f"[red]Error:[/red] {exc}", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        # Auto-detect available services if --service not specified
        available_services = None
        if parsed.service is None:
            config = AgentConfig()
            available_services = await detect_available_services(config)

            if not available_services:
                console.print("[red]Error:[/red] No available services found in ./repos/", style="bold red")
                console.print("[dim]Run 'spi fork --service all' to clone repositories[/dim]")
                return 1

            # Display auto-detection message
            console.print(f"[cyan]{format_auto_detection_message(available_services)}[/cyan]")
            console.print()

        services = copilot_module.parse_services(parsed.service, available_services=available_services)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            console.print(f"[red]Error:[/red] Invalid service(s): {', '.join(invalid)}", style="bold red")
            return 1

        # Parse severity filter (None = server scans all severities)
        severity_filter = None
        if parsed.severity:
            severity_filter = [s.strip().lower() for s in parsed.severity.split(",")]

        # Parse providers filter (default: azure + core modules always included)
        providers = [p.strip().lower() for p in parsed.providers.split(",")]

        # Include testing if flag set
        include_testing = parsed.include_testing

        # Create agent with MCP tools for triage
        config = AgentConfig()
        maven_mcp = MavenMCPManager(config)

        async with maven_mcp:
            if not maven_mcp.is_available:
                console.print("[red]Error:[/red] Maven MCP not available", style="bold red")
                console.print("[dim]Maven MCP is required for vulnerability analysis[/dim]")
                return 1

            agent = SPIAgent(config, mcp_tools=maven_mcp.tools)

            runner = copilot_module.VulnsRunner(
                prompt_file,
                services,
                agent,
                parsed.create_issue,
                severity_filter,
                providers,
                include_testing,
            )
            return await runner.run()

    if parsed.command == "send":
        if not COPILOT_AVAILABLE:
            console.print("[red]Error:[/red] Copilot module not available", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        # Validate service
        service = parsed.service
        if service not in copilot_module.SERVICES:
            console.print(f"[red]Error:[/red] Invalid service '{service}'", style="bold red")
            console.print(f"[dim]Available services: {', '.join(sorted(copilot_module.SERVICES))}[/dim]")
            return 1

        # Require at least one of --pr or --issue
        if not parsed.pr and not parsed.issue:
            console.print("[red]Error:[/red] Must specify --pr or --issue", style="bold red")
            console.print("[dim]Usage: spi send --service <name> --pr <num> | --issue <num>[/dim]")
            return 1

        # Import send workflow functions
        from spi_agent.workflows.send_workflow import send_pr_to_gitlab, send_issue_to_gitlab

        config = AgentConfig()
        results = []
        github_urls = []
        gitlab_urls = []
        has_error = False

        # Send PR if specified
        if parsed.pr:
            with console.status(f"[bold blue]Sending GitHub PR #{parsed.pr} to GitLab...[/bold blue]", spinner="dots"):
                pr_result = send_pr_to_gitlab(service, parsed.pr, config)
                results.append(("PR", parsed.pr, pr_result))

                # Extract URLs from result
                if "✓" in pr_result:
                    # Success - extract URLs
                    for line in pr_result.split("\n"):
                        if line.startswith("GitHub:"):
                            github_urls.append(("PR", line.replace("GitHub:", "").strip()))
                        elif line.startswith("GitLab:"):
                            gitlab_urls.append(("MR", line.replace("GitLab:", "").strip()))
                else:
                    has_error = True

        # Send Issue if specified
        if parsed.issue:
            with console.status(f"[bold blue]Sending GitHub Issue #{parsed.issue} to GitLab...[/bold blue]", spinner="dots"):
                issue_result = send_issue_to_gitlab(service, parsed.issue, config)
                results.append(("Issue", parsed.issue, issue_result))

                # Extract URLs from result
                if "✓" in issue_result:
                    # Success - extract URLs
                    for line in issue_result.split("\n"):
                        if line.startswith("GitHub:"):
                            github_urls.append(("Issue", line.replace("GitHub:", "").strip()))
                        elif line.startswith("GitLab:"):
                            gitlab_urls.append(("Issue", line.replace("GitLab:", "").strip()))
                else:
                    has_error = True

        # Display results
        console.print()

        if len(results) == 1:
            # Single item - display simple panel
            item_type, item_num, result = results[0]

            if "✓" in result:
                # Success
                output_lines = [f"[green]✓ Sent {item_type} #{item_num} from GitHub to GitLab[/green]\n"]
                for url_type, url in github_urls + gitlab_urls:
                    output_lines.append(f"{url_type}: {url}")

                console.print(
                    Panel(
                        "\n".join(output_lines),
                        title="[bold green]Send Complete[/bold green]",
                        border_style="green",
                        padding=(1, 2),
                    )
                )
            else:
                # Error
                # Extract error message (remove "Error: " prefix if present)
                error_msg = result.replace("Error:", "").strip()
                console.print(
                    Panel(
                        f"[red]{error_msg}[/red]",
                        title="[bold red]Error[/bold red]",
                        border_style="red",
                        padding=(1, 2),
                    )
                )
        else:
            # Multiple items - display summary
            summary_lines = []
            for item_type, item_num, result in results:
                if "✓" in result:
                    summary_lines.append(f"[green]{item_type} #{item_num}: ✓ Success[/green]")
                else:
                    summary_lines.append(f"[red]{item_type} #{item_num}: ✗ Failed[/red]")

            summary_lines.append("")  # Blank line

            # Add URLs
            for url_type, url in github_urls + gitlab_urls:
                summary_lines.append(f"{url_type}: {url}")

            console.print(
                Panel(
                    "\n".join(summary_lines),
                    title="[bold cyan]Send Summary[/bold cyan]",
                    border_style="cyan",
                    padding=(1, 2),
                )
            )

        console.print()
        return 1 if has_error else 0

    if parsed.command == "depends":
        if not COPILOT_AVAILABLE:
            console.print("[red]Error:[/red] Copilot module not available", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        try:
            prompt_file = copilot_module.get_prompt_file("depends.md")
        except FileNotFoundError as exc:
            console.print(f"[red]Error:[/red] {exc}", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        # Auto-detect available services if --service not specified
        available_services = None
        if parsed.service is None:
            config = AgentConfig()
            available_services = await detect_available_services(config)

            if not available_services:
                console.print("[red]Error:[/red] No available services found in ./repos/", style="bold red")
                console.print("[dim]Run 'spi fork --service all' to clone repositories[/dim]")
                return 1

            # Display auto-detection message
            console.print(f"[cyan]{format_auto_detection_message(available_services)}[/cyan]")
            console.print()

        services = copilot_module.parse_services(parsed.service, available_services=available_services)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            console.print(f"[red]Error:[/red] Invalid service(s): {', '.join(invalid)}", style="bold red")
            return 1

        # Parse providers filter (default: azure + core modules always included)
        providers = [p.strip().lower() for p in parsed.providers.split(",")]

        # Include testing if flag set
        include_testing = parsed.include_testing

        # Create agent with MCP tools for dependency analysis
        config = AgentConfig()
        maven_mcp = MavenMCPManager(config)

        async with maven_mcp:
            if not maven_mcp.is_available:
                console.print("[red]Error:[/red] Maven MCP not available", style="bold red")
                console.print("[dim]Maven MCP is required for dependency analysis[/dim]")
                return 1

            agent = SPIAgent(config, mcp_tools=maven_mcp.tools)

            runner = copilot_module.DependsRunner(
                prompt_file,
                services,
                agent,
                parsed.create_issue,
                providers,
                include_testing,
            )
            return await runner.run()

    if parsed.prompt:
        return await run_single_query(parsed.prompt, parsed.quiet, parsed.verbose)

    return await run_chat_mode(parsed.quiet, parsed.verbose)


def main() -> int:
    """Synchronous entry point for console_scripts."""
    return asyncio.run(async_main())
