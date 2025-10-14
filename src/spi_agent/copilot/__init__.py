#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "rich==14.1.0",
#   "pydantic==2.10.6",
#   "pydantic-settings==2.7.1",
#   "python-dotenv==1.0.1",
# ]
# ///
"""
Enhanced Copilot CLI Wrapper with Rich Console Output

Usage:
    spi-agent fork --services partition,legal --branch main
    spi-agent fork --services all
    spi-agent fork --services partition
    spi-agent status --services partition
"""

import argparse
import signal
import subprocess
import sys
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import List, Optional

from rich.console import Console

# Import configuration
from spi_agent.copilot.config import CopilotConfig, config, log_dir

# Import constants
from spi_agent.copilot.constants import SERVICES

# Import models
from spi_agent.copilot.models import (
    IssueInfo,
    IssuesData,
    PullRequestInfo,
    PullRequestsData,
    RepoInfo,
    ServiceData,
    StatusResponse,
    WorkflowRun,
    WorkflowsData,
)

# Import trackers
from spi_agent.copilot.trackers import ServiceTracker, StatusTracker, TestTracker, TriageTracker

# Import runners
from spi_agent.copilot.runners import CopilotRunner, StatusRunner, TestRunner, TriageRunner


__all__ = [
    "SERVICES",
    "CopilotConfig",
    "CopilotRunner",
    "StatusRunner",
    "TestRunner",
    "TriageRunner",
    "TestTracker",
    "TriageTracker",
    "parse_services",
    "get_prompt_file",
    "main",
]

console = Console()

# Global process reference for signal handling
current_process: Optional[subprocess.Popen] = None


def handle_interrupt(signum, frame):
    """Handle Ctrl+C gracefully."""
    console.print("\n[yellow]⚠ Interrupted by user[/yellow]")
    if current_process:
        console.print("[dim]Terminating copilot process...[/dim]")
        current_process.terminate()
        try:
            current_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            current_process.kill()
    sys.exit(130)  # Standard exit code for SIGINT


# Register signal handler
signal.signal(signal.SIGINT, handle_interrupt)


def get_prompt_file(name: str) -> Traversable:
    """Return a prompt resource for the given name."""
    prompt = resources.files(__name__).joinpath("prompts", name)
    if not prompt.is_file():
        raise FileNotFoundError(f"Prompt '{name}' not found in packaged resources")
    return prompt


def parse_services(services_arg: str) -> List[str]:
    """Parse services argument into list"""
    if services_arg.lower() == "all":
        return list(SERVICES.keys())
    return [s.strip() for s in services_arg.split(",")]


def main():
    parser = argparse.ArgumentParser(
        description="Enhanced GitHub Copilot CLI Automation Wrapper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s fork --services partition
  %(prog)s fork --services partition,legal,entitlements
  %(prog)s fork --services all --branch develop

  %(prog)s status --services partition
  %(prog)s status --services partition,legal,entitlements
  %(prog)s status --services all
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Fork command
    fork_parser = subparsers.add_parser(
        "fork",
        help="Fork and initialize OSDU SPI service repositories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --services partition
  %(prog)s --services partition,legal,entitlements
  %(prog)s --services all
  %(prog)s --services partition --branch develop

Available services:
  partition, entitlements, legal, schema, file, storage,
  indexer, indexer-queue, search, workflow
        """,
    )
    fork_parser.add_argument(
        "--services",
        "-s",
        required=True,
        metavar="SERVICES",
        help="Service name(s): 'all', single name, or comma-separated list",
    )
    fork_parser.add_argument(
        "--branch",
        "-b",
        default="main",
        metavar="BRANCH",
        help="Branch name (default: main)",
    )

    # Status command
    status_parser = subparsers.add_parser(
        "status",
        help="Get GitHub status for OSDU SPI service repositories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --services partition
  %(prog)s --services partition,legal,entitlements
  %(prog)s --services all

Available services:
  partition, entitlements, legal, schema, file, storage,
  indexer, indexer-queue, search, workflow

Information gathered:
  - Open issues count and details
  - Pull requests (highlighting release PRs)
  - Recent workflow runs (Build, Test, CodeQL, etc.)
  - Workflow status (running, completed, failed)
        """,
    )
    status_parser.add_argument(
        "--services",
        "-s",
        required=True,
        metavar="SERVICES",
        help="Service name(s): 'all', single name, or comma-separated list",
    )

    # Custom error handling for better UX
    try:
        args = parser.parse_args()
    except SystemExit as e:
        if e.code != 0:
            # Print hint after argparse error
            console.print(
                "\n[cyan]Hint:[/cyan] Run with --help to see examples and usage",
                style="dim",
            )
        raise

    if not args.command:
        parser.print_help()
        return 1

    # Handle fork command
    if args.command == "fork":
        try:
            prompt_file = get_prompt_file("fork.md")
        except FileNotFoundError as exc:
            console.print(
                f"[red]Error:[/red] {exc}",
                style="bold red",
            )
            return 1

        # Parse services
        services = parse_services(args.services)

        # Validate services
        invalid = [s for s in services if s not in SERVICES]
        if invalid:
            console.print(
                f"[red]Error:[/red] Invalid service(s): {', '.join(invalid)}",
                style="bold red",
            )
            console.print(f"\n[cyan]Available services:[/cyan] {', '.join(SERVICES.keys())}")
            return 1

        # Run copilot
        runner = CopilotRunner(prompt_file, services, args.branch)
        return runner.run()

    # Handle status command
    if args.command == "status":
        try:
            prompt_file = get_prompt_file("status.md")
        except FileNotFoundError as exc:
            console.print(
                f"[red]Error:[/red] {exc}",
                style="bold red",
            )
            return 1

        # Parse services
        services = parse_services(args.services)

        # Validate services
        invalid = [s for s in services if s not in SERVICES]
        if invalid:
            console.print(
                f"[red]Error:[/red] Invalid service(s): {', '.join(invalid)}",
                style="bold red",
            )
            console.print(f"\n[cyan]Available services:[/cyan] {', '.join(SERVICES.keys())}")
            return 1

        # Run status check
        runner = StatusRunner(prompt_file, services)
        return runner.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
