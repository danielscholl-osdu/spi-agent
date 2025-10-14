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

        runner = copilot_module.CopilotRunner(prompt_file, services, branch)
        exit_code = runner.run()

        if exit_code == 0:
            summary = f"Successfully forked repositories: {', '.join(services)} (branch: {branch})"
        else:
            summary = f"Fork command failed with exit code {exit_code} for services: {', '.join(services)}"

        await agent.agent.run(
            f"SYSTEM NOTE: The user just ran a fork command. {summary}. "
            f"Acknowledge this briefly and offer to help with next steps.",
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

        runner = copilot_module.StatusRunner(prompt_file, services)
        runner.run()

        summary = f"Status check completed for: {', '.join(services)}"
        await agent.agent.run(
            f"SYSTEM NOTE: The user just checked GitHub status. {summary}. "
            f"The status information was displayed. Acknowledge briefly and offer to help analyze the results.",
            thread=thread,
        )
        return None

    if cmd == "test":
        if len(parts) < 2:
            return "Usage: /test <services> [--provider <provider>]\nExample: /test partition --provider azure"

        services_arg = parts[1]
        provider = "azure"  # Default to azure

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

        runner = copilot_module.TestRunner(prompt_file, services, provider)
        exit_code = runner.run()

        if exit_code == 0:
            summary = f"Maven tests completed for: {', '.join(services)}"
        else:
            summary = f"Maven test command failed with exit code {exit_code} for services: {', '.join(services)}"

        await agent.agent.run(
            f"SYSTEM NOTE: The user just ran Maven tests. {summary}. "
            f"Acknowledge this briefly and offer to help analyze the results or fix any issues.",
            thread=thread,
        )
        return None

    return f"Unknown command: /{cmd}\nAvailable: /fork, /status, /test, /help"


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
- `/test partition` - Run Maven tests (default: azure provider)
- `/test partition --provider aws` - Run tests with specific provider
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
            console.print("[dim]Slash commands: /fork <services>, /status <services>, /test <services>[/dim]\n")

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
  test                Run Maven tests for services (requires copilot)

Examples:
  spi-agent                                    # Interactive chat
  spi-agent -p "List issues in partition"      # One-shot query
  spi-agent fork --services partition          # Fork repos
  spi-agent status --services partition,legal  # Check status
  spi-agent test --services partition          # Run Maven tests
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
            default="azure",
            help="Cloud provider(s): azure, aws, gc, ibm, core, all (default: azure)",
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

    if parsed.prompt:
        return await run_single_query(parsed.prompt, parsed.quiet)

    return await run_chat_mode(parsed.quiet)


def main() -> int:
    """Synchronous entry point for console_scripts."""
    return asyncio.run(async_main())
