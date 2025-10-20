"""Console entry point for SPI Agent."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from . import SPIAgent
from .config import AgentConfig
from .mcp import MavenMCPManager

console = Console()

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
    """Handle slash commands in chat mode."""
    if not COPILOT_AVAILABLE or copilot_module is None:
        return "Error: Copilot module not available for slash commands"

    parts = command[1:].split()  # Remove leading /
    if not parts:
        return None

    cmd = parts[0].lower()

    if cmd == "fork":
        if len(parts) < 2:
            return "Usage: /fork <service> [--branch <branch>]\nExample: /fork partition,legal"

        services_arg = parts[1]
        branch = "main"

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

        console.print(f"\n[yellow]Executing fork workflow for: {', '.join(services)}[/yellow]\n")

        # Use workflow function to store results for agent context
        from spi_agent.workflows.vulns_workflow import run_fork_workflow

        result = await run_fork_workflow(services=services, branch=branch)

        # Brief acknowledgment - agent will have access to full results via context injection
        await agent.agent.run(
            f"The fork workflow just completed for {', '.join(services)} (branch: {branch}). "
            f"You now have access to the fork operation results. "
            f"Acknowledge briefly and offer to help with next steps.",
            thread=thread,
        )
        return None

    if cmd == "status":
        if len(parts) < 2:
            return "Usage: /status <service> [--platform github|gitlab] [--provider <providers>]\nExamples:\n  /status partition\n  /status partition --platform gitlab --provider azure"

        services_arg = parts[1]

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

        services = copilot_module.parse_services(services_arg)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            return f"Error: Invalid service(s): {', '.join(invalid)}"

        # Display status message
        if platform == "gitlab":
            console.print(f"\n[yellow]Checking GitLab status for: {', '.join(services)} (providers: {providers})[/yellow]\n")
            providers_list = [p.strip() for p in providers.split(",")]
            runner = copilot_module.StatusRunner(None, services, providers_list)
        else:
            console.print(f"\n[yellow]Checking GitHub status for: {', '.join(services)}[/yellow]\n")
            runner = copilot_module.StatusRunner(None, services)

        await runner.run_direct()

        # Brief acknowledgment - results were already displayed
        platform_name = "GitLab" if platform == "gitlab" else "GitHub"
        await agent.agent.run(
            f"The {platform_name} status check just completed for {', '.join(services)}. "
            f"The results were displayed above. "
            f"Acknowledge briefly and offer to help analyze the status or address any issues.",
            thread=thread,
        )
        return None

    if cmd == "test":
        if len(parts) < 2:
            return "Usage: /test <service> [--provider <provider>]\nExample: /test partition --provider azure"

        services_arg = parts[1]
        provider = "core,core-plus,azure"  # Default to comprehensive core + azure coverage

        # Parse --provider flag
        if "--provider" in parts:
            provider_idx = parts.index("--provider")
            if provider_idx + 1 < len(parts):
                provider = parts[provider_idx + 1]

        if not COPILOT_AVAILABLE or copilot_module is None:
            return "Error: Copilot module not available for service validation"

        services = copilot_module.parse_services(services_arg)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            return f"Error: Invalid service(s): {', '.join(invalid)}"

        console.print(f"\n[yellow]Running Maven tests for: {', '.join(services)} (provider: {provider})[/yellow]\n")

        # Use workflow function to store results for agent context
        from spi_agent.workflows.vulns_workflow import run_test_workflow

        result = await run_test_workflow(services=services, provider=provider)

        # Brief acknowledgment - agent will have access to full results via context injection
        await agent.agent.run(
            f"The test workflow just completed for {', '.join(services)}. "
            f"You now have access to the test results. "
            f"Acknowledge briefly and offer to help analyze the results or fix any issues.",
            thread=thread,
        )
        return None

    if cmd == "vulns":
        if len(parts) < 2:
            return "Usage: /vulns <service> [--create-issue] [--severity LEVEL] [--providers PROVIDERS] [--include-testing]\nExample: /vulns partition\nExample: /vulns partition --providers azure,aws --include-testing"

        services_arg = parts[1]
        create_issue = "--create-issue" in parts

        # Parse --severity flag (None = server scans all severities)
        severity_filter = None
        if "--severity" in parts:
            severity_idx = parts.index("--severity")
            if severity_idx + 1 < len(parts):
                severity_arg = parts[severity_idx + 1]
                severity_filter = [s.strip().lower() for s in severity_arg.split(",")]

        # Parse --providers flag (default: azure)
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

        services = copilot_module.parse_services(services_arg)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            return f"Error: Invalid service(s): {', '.join(invalid)}"

        severity_str = ", ".join(severity_filter).upper() if severity_filter else "ALL"
        console.print(f"\n[yellow]Running vulnerability analysis for: {', '.join(services)} (severity: {severity_str})[/yellow]\n")

        # Use workflow function to store results for agent context
        from spi_agent.workflows.vulns_workflow import run_vulns_workflow

        try:
            result = await run_vulns_workflow(
                agent=agent,
                services=services,
                severity_filter=severity_filter,
                providers=providers,
                include_testing=include_testing,
                create_issue=create_issue,
            )

            # Brief acknowledgment - agent will have access to full results via context injection
            await agent.agent.run(
                f"The vulnerability analysis just completed for {', '.join(services)}. "
                f"You now have access to the full results including vulnerability counts and CVE analysis. "
                f"Acknowledge briefly and offer to help analyze the findings.",
                thread=thread,
            )
        except Exception as e:
            await agent.agent.run(
                f"The vulnerability analysis encountered an error: {str(e)}. "
                f"Acknowledge this and offer to help troubleshoot.",
                thread=thread,
            )

        return None

    return f"Unknown command: /{cmd}\nAvailable: /fork, /status, /test, /vulns, /help"


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

**Slash Commands:**
- `/fork <service>` - Fork service repository
- `/fork <service>,<service>` - Fork multiple repositories
- `/fork <service> --branch develop` - Fork with custom branch
- `/status <service>` - Check GitHub status for service (default)
- `/status <service>,<service>` - Check status for multiple repos
- `/status <service> --platform gitlab` - Check GitLab status (providers: Azure,Core)
- `/status <service> --platform gitlab --provider azure` - GitLab status (azure only)
- `/test <service>` - Run Maven tests (default: core,core-plus,azure profiles)
- `/test <service> --provider aws` - Run tests with specific provider
- `/vulns <service>` - Run dependency/vulnerability analysis
- `/vulns <service> --create-issue` - Scan and create issues for vulnerabilities
- `/vulns <service> --severity critical,high` - Filter by severity
- `/help` - Show this help
"""
    console.print(Panel(Markdown(help_text), title="💡 Help", border_style="yellow"))
    console.print()


async def run_chat_mode(quiet: bool = False) -> int:
    """Run interactive chat mode."""
    config = AgentConfig()

    # Initialize Maven MCP if enabled
    maven_mcp = MavenMCPManager(config)

    async with maven_mcp:
        # Create agent with Maven MCP tools if available
        agent = SPIAgent(config, mcp_tools=maven_mcp.tools)

        if not quiet:
            maven_status = "enabled" if maven_mcp.is_available else "disabled"
            tool_count = len(agent.github_tools) + len(maven_mcp.tools)

            header = f"""[cyan]Organization:[/cyan] {agent.config.organization}
[cyan]Model:[/cyan]        {agent.config.azure_openai_deployment}
[cyan]Repositories:[/cyan] {len(agent.config.repositories)} configured
[cyan]Tools:[/cyan]        {tool_count} available (Maven MCP: {maven_status})
[cyan]Memory:[/cyan]       Thread-based (within session)"""

            console.print(Panel(header, title="🤖 SPI Agent - Interactive Mode", border_style="blue"))
            console.print()
            console.print("[dim]Type 'exit', 'quit', or press Ctrl+D to end session[/dim]")
            console.print("[dim]Type 'help' or '/help' for available commands[/dim]")
            console.print("[dim]Slash commands: /fork, /status, /test, /vulns[/dim]\n")

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
            from prompt_toolkit.formatted_text import FormattedText
            from prompt_toolkit.patch_stdout import patch_stdout as pt_patch_stdout

            # Create session with history and proper key bindings
            session = PromptSession(
                history=InMemoryHistory(),
                style=PromptStyle.from_dict({
                    'prompt': 'cyan bold',
                }),
                enable_history_search=True,
                mouse_support=False,  # Disable mouse to avoid conflicts
                color_depth=ColorDepth.TRUE_COLOR,
            )
            prompt_tokens = FormattedText([('class:prompt', 'You: ')])
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
                    prompt_text = "You: "
                    query = await asyncio.to_thread(input, prompt_text)
                    query = query.strip()

                if not query:
                    continue

                if query.lower() in ["exit", "quit", "q"]:
                    console.print("\n[yellow]Goodbye![/yellow]")
                    break

                if query.lower() in ["help", "/help"]:
                    _render_help()
                    continue

                if query.startswith("/"):
                    if not COPILOT_AVAILABLE:
                        console.print("\n[red]Slash commands require the optional Copilot workflows.[/red]\n")
                        continue

                    error = await handle_slash_command(query, agent, thread)
                    if error:
                        console.print(f"\n[red]{error}[/red]\n")
                    continue

                # Use dynamic status display that updates based on agent activity
                from spi_agent.activity import get_activity_tracker

                activity_tracker = get_activity_tracker()

                # Create async task to update status dynamically
                status_handle = console.status("[bold blue]Starting...[/bold blue]", spinner="dots")
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

                console.print()
                console.print(
                    Panel(
                        Markdown(result_text),
                        title="[bold green]SPI Agent[/bold green]",
                        border_style="green",
                        padding=(1, 2),
                    )
                )
                console.print()

            except EOFError:
                console.print("\n[yellow]Goodbye![/yellow]")
                break
            except KeyboardInterrupt:
                console.print("\n\n[yellow]Interrupted. Goodbye![/yellow]")
                break
            except Exception as exc:  # pylint: disable=broad-except
                console.print(f"\n[red]Error:[/red] {exc}\n", style="bold red")

    return 0


async def run_single_query(prompt: str, quiet: bool = False) -> int:
    """Run a single query with Rich output."""
    config = AgentConfig()

    # Initialize Maven MCP if enabled
    maven_mcp = MavenMCPManager(config)

    async with maven_mcp:
        # Create agent with Maven MCP tools if available
        agent = SPIAgent(config, mcp_tools=maven_mcp.tools)

        if not quiet:
            maven_status = "enabled" if maven_mcp.is_available else "disabled"
            console.print(
                Panel(
                    f"[cyan]Model:[/cyan] {agent.config.azure_openai_deployment}\n"
                    f"[cyan]Maven MCP:[/cyan] {maven_status}\n"
                    f"[cyan]Query:[/cyan] {prompt}",
                    title="🤖 SPI Agent",
                    border_style="blue",
                )
            )
            console.print()

        try:
            with console.status("[bold blue]Processing query...[/bold blue]", spinner="dots"):
                result = await agent.run(prompt)

            result_text = str(result) if not isinstance(result, str) else result

            if quiet:
                console.print(result_text)
            else:
                console.print(
                    Panel(
                        Markdown(result_text),
                        title="[bold green]Result[/bold green]",
                        border_style="green",
                        padding=(1, 2),
                    )
                )

            return 0

        except Exception as exc:  # pylint: disable=broad-except
            console.print(f"[red]Error:[/red] {exc}", style="bold red")
            return 1


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

Examples:
  spi                                    # Interactive chat
  spi -p "List issues in partition"      # One-shot query
  spi fork --service partition          # Fork repos
  spi status --service partition        # Check GitHub status (default)
  spi status --service partition --platform gitlab  # Check GitLab status
  spi test --service partition          # Run Maven tests
  spi vulns --service partition         # Run vulnerability analysis
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    if COPILOT_AVAILABLE:
        fork_parser = subparsers.add_parser(
            "fork",
            help="Fork and initialize OSDU SPI service repositories",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        fork_parser.add_argument(
            "--service",
            "-s",
            default="all",
            help="Service name(s): 'all', single name, or comma-separated list (default: all)",
        )
        fork_parser.add_argument(
            "--branch",
            "-b",
            default="main",
            help="Branch name (default: main)",
        )

        status_parser = subparsers.add_parser(
            "status",
            help="Get GitHub or GitLab status for OSDU SPI service repositories",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        status_parser.add_argument(
            "--service",
            "-s",
            default="all",
            help="Service name(s): 'all', single name, or comma-separated list (default: all)",
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

        test_parser = subparsers.add_parser(
            "test",
            help="Run Maven tests for OSDU SPI service repositories",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        test_parser.add_argument(
            "--service",
            "-s",
            default="all",
            help="Service name(s): 'all', single name, or comma-separated list (default: all)",
        )
        test_parser.add_argument(
            "--provider",
            "-p",
            default="core,core-plus,azure",
            help="Cloud provider(s): azure, aws, gc, ibm, core, all (default: core,core-plus,azure)",
        )

        vulns_parser = subparsers.add_parser(
            "vulns",
            help="Run Maven dependency and vulnerability analysis",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        vulns_parser.add_argument(
            "--service",
            "-s",
            default="all",
            help="Service name(s): 'all', single name, or comma-separated list (default: all)",
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

        services = copilot_module.parse_services(parsed.service)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            console.print(f"[red]Error:[/red] Invalid service(s): {', '.join(invalid)}", style="bold red")
            return 1

        # Setup providers for GitLab
        if platform == "gitlab":
            provider_arg = parsed.provider if parsed.provider else "Azure,Core"
            providers = [p.strip() for p in provider_arg.split(",")]
            runner = copilot_module.StatusRunner(None, services, providers)
        else:
            runner = copilot_module.StatusRunner(None, services)

        # Use StatusRunner with direct API mode (fast, no AI)
        return await runner.run_direct()

    if parsed.command == "test":
        if not COPILOT_AVAILABLE:
            console.print("[red]Error:[/red] Copilot module not available", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        services = copilot_module.parse_services(parsed.service)
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

        services = copilot_module.parse_services(parsed.service)
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

    if parsed.prompt:
        return await run_single_query(parsed.prompt, parsed.quiet)

    return await run_chat_mode(parsed.quiet)


def main() -> int:
    """Synchronous entry point for console_scripts."""
    return asyncio.run(async_main())
