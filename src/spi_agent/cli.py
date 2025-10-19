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
            return "Usage: /fork <services> [--branch <branch>]\nExample: /fork partition,legal"

        services_arg = parts[1]
        branch = "main"

        # Check for --branch flag
        if "--branch" in parts:
            branch_idx = parts.index("--branch")
            if branch_idx + 1 < len(parts):
                branch = parts[branch_idx + 1]

        try:
            prompt_file = copilot_module.get_prompt_file("fork.md")
        except FileNotFoundError as exc:  # pragma: no cover - packaging guard
            return f"Error: {exc}"

        services = copilot_module.parse_services(services_arg)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            return f"Error: Invalid service(s): {', '.join(invalid)}"

        console.print(f"\n[yellow]Executing fork workflow for: {', '.join(services)}[/yellow]\n")

        # Use workflow function to store results for agent context
        from spi_agent.workflows.triage_workflow import run_fork_workflow

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
            return "Usage: /status <services>\nExample: /status partition,legal"

        services_arg = parts[1]
        try:
            prompt_file = copilot_module.get_prompt_file("status.md")
        except FileNotFoundError as exc:  # pragma: no cover - packaging guard
            return f"Error: {exc}"

        services = copilot_module.parse_services(services_arg)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            return f"Error: Invalid service(s): {', '.join(invalid)}"

        console.print(f"\n[yellow]Checking status for: {', '.join(services)}[/yellow]\n")

        # Use workflow function to store results for agent context
        from spi_agent.workflows.triage_workflow import run_status_workflow

        result = await run_status_workflow(services=services)

        # Brief acknowledgment - agent will have access to full results via context injection
        await agent.agent.run(
            f"The status check just completed for {', '.join(services)}. "
            f"You now have access to the status information. "
            f"Acknowledge briefly and offer to help analyze the results.",
            thread=thread,
        )
        return None

    if cmd == "status-glab":
        if len(parts) < 2:
            return "Usage: /status-glab <projects> [--provider <providers>]\nExample: /status-glab partition --provider azure"

        projects_arg = parts[1]
        providers = "Azure,Core"  # Default providers (capitalized to match GitLab labels)

        # Parse --provider flag
        if "--provider" in parts:
            provider_idx = parts.index("--provider")
            if provider_idx + 1 < len(parts):
                providers = parts[provider_idx + 1]

        try:
            prompt_file = copilot_module.get_prompt_file("status-glab.md")
        except FileNotFoundError as exc:  # pragma: no cover - packaging guard
            return f"Error: {exc}"

        projects = copilot_module.parse_services(projects_arg)
        invalid = [p for p in projects if p not in copilot_module.SERVICES]
        if invalid:
            return f"Error: Invalid project(s): {', '.join(invalid)}"

        console.print(f"\n[yellow]Checking GitLab status for: {', '.join(projects)} (providers: {providers})[/yellow]\n")

        # Run status-glab using StatusRunner with providers
        providers_list = [p.strip() for p in providers.split(",")]
        runner = copilot_module.StatusRunner(prompt_file, projects, providers_list)
        runner.run()

        # Brief acknowledgment - results were already displayed
        await agent.agent.run(
            f"The GitLab status check just completed for {', '.join(projects)}. "
            f"The results were displayed above. "
            f"Acknowledge briefly and offer to help analyze the status or address any issues.",
            thread=thread,
        )
        return None

    if cmd == "test":
        if len(parts) < 2:
            return "Usage: /test <services> [--provider <provider>]\nExample: /test partition --provider azure"

        services_arg = parts[1]
        provider = "core,core-plus,azure"  # Default to comprehensive core + azure coverage

        # Parse --provider flag
        if "--provider" in parts:
            provider_idx = parts.index("--provider")
            if provider_idx + 1 < len(parts):
                provider = parts[provider_idx + 1]

        try:
            prompt_file = copilot_module.get_prompt_file("test.md")
        except FileNotFoundError as exc:  # pragma: no cover - packaging guard
            return f"Error: {exc}"

        services = copilot_module.parse_services(services_arg)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            return f"Error: Invalid service(s): {', '.join(invalid)}"

        console.print(f"\n[yellow]Running Maven tests for: {', '.join(services)} (provider: {provider})[/yellow]\n")

        # Use workflow function to store results for agent context
        from spi_agent.workflows.triage_workflow import run_test_workflow

        result = await run_test_workflow(services=services, provider=provider)

        # Brief acknowledgment - agent will have access to full results via context injection
        await agent.agent.run(
            f"The test workflow just completed for {', '.join(services)}. "
            f"You now have access to the test results. "
            f"Acknowledge briefly and offer to help analyze the results or fix any issues.",
            thread=thread,
        )
        return None

    if cmd == "triage":
        if len(parts) < 2:
            return "Usage: /triage <services> [--create-issue] [--severity LEVEL] [--providers PROVIDERS] [--include-testing]\nExample: /triage partition\nExample: /triage partition --providers azure,aws --include-testing"

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
            prompt_file = copilot_module.get_prompt_file("triage.md")
        except FileNotFoundError as exc:  # pragma: no cover - packaging guard
            return f"Error: {exc}"

        services = copilot_module.parse_services(services_arg)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            return f"Error: Invalid service(s): {', '.join(invalid)}"

        severity_str = ", ".join(severity_filter).upper() if severity_filter else "ALL"
        console.print(f"\n[yellow]Running triage analysis for: {', '.join(services)} (severity: {severity_str})[/yellow]\n")

        # Use workflow function to store results for agent context
        from spi_agent.workflows.triage_workflow import run_triage_workflow

        try:
            result = await run_triage_workflow(
                agent=agent,
                services=services,
                severity_filter=severity_filter,
                providers=providers,
                include_testing=include_testing,
                create_issue=create_issue,
            )

            # Brief acknowledgment - agent will have access to full results via context injection
            await agent.agent.run(
                f"The triage workflow just completed for {', '.join(services)}. "
                f"You now have access to the full results including vulnerability counts and CVE analysis. "
                f"Acknowledge briefly and offer to help analyze the findings.",
                thread=thread,
            )
        except Exception as e:
            await agent.agent.run(
                f"The triage workflow encountered an error: {str(e)}. "
                f"Acknowledge this and offer to help troubleshoot.",
                thread=thread,
            )

        return None

    return f"Unknown command: /{cmd}\nAvailable: /fork, /status, /status-glab, /test, /triage, /help"


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
- "Run triage for partition and create issues for critical CVEs"

**Slash Commands:**
- `/fork partition` - Fork partition repository
- `/fork partition,legal` - Fork multiple repositories
- `/fork partition --branch develop` - Fork with custom branch
- `/status partition` - Check GitHub status for partition
- `/status partition,legal` - Check status for multiple repos
- `/status-glab partition` - Check GitLab status for partition (default providers: azure,core)
- `/status-glab partition --provider azure` - Check GitLab status with specific provider
- `/test partition` - Run Maven tests (default: core,core-plus,azure profiles)
- `/test partition --provider aws` - Run tests with specific provider
- `/triage partition` - Run dependency/vulnerability triage
- `/triage partition --create-issue` - Run triage and create issues
- `/triage partition --severity critical,high` - Filter by severity
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
            console.print("[dim]Slash commands: /fork, /status, /status-glab, /test, /triage[/dim]\n")

        thread = agent.agent.get_new_thread()

        while True:
            try:
                query = console.input("[bold cyan]You:[/bold cyan] ").strip()

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

                with console.status("[bold blue]Agent thinking...[/bold blue]", spinner="dots"):
                    result = await agent.agent.run(query, thread=thread)

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
  status              Check GitHub status (requires copilot)
  status-glab         Check GitLab status with provider filtering (requires copilot)
  test                Run Maven tests for services (requires copilot)
  triage              Run dependency/vulnerability triage (requires copilot)

Examples:
  spi-agent                                    # Interactive chat
  spi-agent -p "List issues in partition"      # One-shot query
  spi-agent fork --services partition          # Fork repos
  spi-agent status --services partition,legal  # Check GitHub status
  spi-agent status-glab --projects partition   # Check GitLab status
  spi-agent status-glab --projects partition --provider azure  # GitLab status (azure only)
  spi-agent test --services partition          # Run Maven tests
  spi-agent triage --services partition        # Run triage analysis
  spi-agent triage --services partition --create-issue  # Triage + create issues
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
            "--services",
            "-s",
            required=True,
            help="Service name(s): 'all', single name, or comma-separated list",
        )
        fork_parser.add_argument(
            "--branch",
            "-b",
            default="main",
            help="Branch name (default: main)",
        )

        status_parser = subparsers.add_parser(
            "status",
            help="Get GitHub status for OSDU SPI service repositories",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        status_parser.add_argument(
            "--services",
            "-s",
            required=True,
            help="Service name(s): 'all', single name, or comma-separated list",
        )

        status_glab_parser = subparsers.add_parser(
            "status-glab",
            help="Get GitLab status for OSDU SPI service repositories",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        status_glab_parser.add_argument(
            "--projects",
            "-p",
            required=True,
            help="Project name(s): 'all', single name, or comma-separated list",
        )
        status_glab_parser.add_argument(
            "--provider",
            default="Azure,Core",
            help="Provider label(s) for filtering (default: Azure,Core)",
        )

        test_parser = subparsers.add_parser(
            "test",
            help="Run Maven tests for OSDU SPI service repositories",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        test_parser.add_argument(
            "--services",
            "-s",
            required=True,
            help="Service name(s): 'all', single name, or comma-separated list",
        )
        test_parser.add_argument(
            "--provider",
            "-p",
            default="core,core-plus,azure",
            help="Cloud provider(s): azure, aws, gc, ibm, core, all (default: core,core-plus,azure)",
        )

        triage_parser = subparsers.add_parser(
            "triage",
            help="Run Maven dependency and vulnerability triage analysis",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        triage_parser.add_argument(
            "--services",
            "-s",
            required=True,
            help="Service name(s): 'all', single name, or comma-separated list",
        )
        triage_parser.add_argument(
            "--create-issue",
            action="store_true",
            help="Create GitHub tracking issues for critical/high findings",
        )
        triage_parser.add_argument(
            "--severity",
            default=None,
            help="Severity filter: critical, high, medium, low (default: all severities)",
        )
        triage_parser.add_argument(
            "--providers",
            default="azure",
            help="Provider(s) to include: azure, aws, gc, ibm, core, or comma-separated list (default: azure)",
        )
        triage_parser.add_argument(
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

        try:
            prompt_file = copilot_module.get_prompt_file("fork.md")
        except FileNotFoundError as exc:
            console.print(f"[red]Error:[/red] {exc}", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        services = copilot_module.parse_services(parsed.services)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            console.print(f"[red]Error:[/red] Invalid service(s): {', '.join(invalid)}", style="bold red")
            return 1

        runner = copilot_module.CopilotRunner(prompt_file, services, parsed.branch)
        return runner.run()

    if parsed.command == "status":
        if not COPILOT_AVAILABLE:
            console.print("[red]Error:[/red] Copilot module not available", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        try:
            prompt_file = copilot_module.get_prompt_file("status.md")
        except FileNotFoundError as exc:
            console.print(f"[red]Error:[/red] {exc}", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        services = copilot_module.parse_services(parsed.services)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            console.print(f"[red]Error:[/red] Invalid service(s): {', '.join(invalid)}", style="bold red")
            return 1

        runner = copilot_module.StatusRunner(prompt_file, services)
        return runner.run()

    if parsed.command == "status-glab":
        if not COPILOT_AVAILABLE:
            console.print("[red]Error:[/red] Copilot module not available", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        try:
            prompt_file = copilot_module.get_prompt_file("status-glab.md")
        except FileNotFoundError as exc:
            console.print(f"[red]Error:[/red] {exc}", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        projects = copilot_module.parse_services(parsed.projects)
        invalid = [p for p in projects if p not in copilot_module.SERVICES]
        if invalid:
            console.print(f"[red]Error:[/red] Invalid project(s): {', '.join(invalid)}", style="bold red")
            return 1

        providers = [p.strip() for p in parsed.provider.split(",")]

        # Use StatusRunner with providers for GitLab status
        runner = copilot_module.StatusRunner(prompt_file, projects, providers)
        return runner.run()

    if parsed.command == "test":
        if not COPILOT_AVAILABLE:
            console.print("[red]Error:[/red] Copilot module not available", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        try:
            prompt_file = copilot_module.get_prompt_file("test.md")
        except FileNotFoundError as exc:
            console.print(f"[red]Error:[/red] {exc}", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        services = copilot_module.parse_services(parsed.services)
        invalid = [s for s in services if s not in copilot_module.SERVICES]
        if invalid:
            console.print(f"[red]Error:[/red] Invalid service(s): {', '.join(invalid)}", style="bold red")
            return 1

        runner = copilot_module.TestRunner(
            prompt_file,
            services,
            parsed.provider,
        )
        return runner.run()

    if parsed.command == "triage":
        if not COPILOT_AVAILABLE:
            console.print("[red]Error:[/red] Copilot module not available", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        try:
            prompt_file = copilot_module.get_prompt_file("triage.md")
        except FileNotFoundError as exc:
            console.print(f"[red]Error:[/red] {exc}", style="bold red")
            console.print("[dim]Clone the repository to access Copilot workflows[/dim]")
            return 1

        services = copilot_module.parse_services(parsed.services)
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
                console.print("[dim]Maven MCP is required for triage analysis[/dim]")
                return 1

            agent = SPIAgent(config, mcp_tools=maven_mcp.tools)

            runner = copilot_module.TriageRunner(
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
