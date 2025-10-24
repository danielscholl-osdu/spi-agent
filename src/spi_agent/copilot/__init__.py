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
from spi_agent.copilot.trackers import DependsTracker, ServiceTracker, StatusTracker, TestTracker, VulnsTracker

# Import runners
from spi_agent.copilot.runners import CopilotRunner, DependsRunner, StatusRunner, VulnsRunner


__all__ = [
    "SERVICES",
    "CopilotConfig",
    "CopilotRunner",
    "DependsRunner",
    "StatusRunner",
    "VulnsRunner",
    "DependsTracker",
    "TestTracker",
    "VulnsTracker",
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


def parse_services(services_arg: Optional[str] = None, available_services: Optional[List[str]] = None) -> List[str]:
    """Parse services argument into list.

    Args:
        services_arg: Service specification string ("all", "partition", "partition,legal", etc.)
                     If None, uses available_services parameter for auto-detection.
        available_services: List of auto-detected available services (used when services_arg is None)

    Returns:
        List of service names to process

    Raises:
        ValueError: If services_arg is None and available_services is None

    Examples:
        >>> parse_services("all")
        ['partition', 'legal', 'schema', ...]
        >>> parse_services("partition,legal")
        ['partition', 'legal']
        >>> parse_services(None, available_services=["partition"])
        ['partition']
    """
    # If services_arg is None, use available_services (auto-detection mode)
    if services_arg is None:
        if available_services is None:
            raise ValueError(
                "Either services_arg or available_services must be provided. "
                "Use --service flag to specify services explicitly."
            )
        return available_services

    # Handle "all" keyword
    if services_arg.lower() == "all":
        return list(SERVICES.keys())

    # Parse comma-separated service list
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
  %(prog)s status --services partition --platform gitlab
  %(prog)s status --services partition --platform gitlab --provider azure
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
        default=config.default_branch,
        metavar="BRANCH",
        help=f"Branch name (default: {config.default_branch})",
    )

    # Status command
    status_parser = subparsers.add_parser(
        "status",
        help="Get GitHub or GitLab status for OSDU SPI service repositories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --services partition                          # GitHub (default)
  %(prog)s --services partition,legal,entitlements       # Multiple repos
  %(prog)s --services all                                # All repos
  %(prog)s --services partition --platform gitlab        # GitLab
  %(prog)s --services partition --platform gitlab --provider azure  # GitLab (azure only)

Available services:
  partition, entitlements, legal, schema, file, storage,
  indexer, indexer-queue, search, workflow

Information gathered (GitHub):
  - Open issues count and details
  - Pull requests (highlighting release PRs)
  - Recent workflow runs (Build, Test, CodeQL, etc.)
  - Workflow status (running, completed, failed)

Information gathered (GitLab):
  - Open issues filtered by provider labels
  - Merge requests filtered by provider labels
  - Recent pipeline runs (success, failed, running)
  - Provider labels highlighted in output
        """,
    )
    status_parser.add_argument(
        "--services",
        "-s",
        required=True,
        metavar="SERVICES",
        help="Service name(s): 'all', single name, or comma-separated list",
    )
    status_parser.add_argument(
        "--platform",
        choices=["github", "gitlab"],
        default="github",
        help="Platform to query (default: github)",
    )
    status_parser.add_argument(
        "--provider",
        metavar="PROVIDERS",
        help="Provider label(s) for filtering (GitLab only, default: Azure,Core)",
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

        # Run fork using direct API mode
        import asyncio
        runner = CopilotRunner(services, args.branch)
        return asyncio.run(runner.run_direct())

    # Handle status command
    if args.command == "status":
        # Determine platform
        platform = getattr(args, 'platform', 'github')

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

        # Setup providers for GitLab
        if platform == "gitlab":
            provider_arg = getattr(args, 'provider', None) or "Azure,Core"
            providers = [p.strip() for p in provider_arg.split(",")]
            runner = StatusRunner(None, services, providers)
        else:
            runner = StatusRunner(None, services)

        # Run status check using direct API mode (fast, no AI)
        import asyncio
        return asyncio.run(runner.run_direct())

    return 0


if __name__ == "__main__":
    sys.exit(main())
