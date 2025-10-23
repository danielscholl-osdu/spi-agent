"""Dependency update analysis runner for Maven version checking."""

import asyncio
import re
from datetime import datetime
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Union

from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from spi_agent.copilot.base import BaseRunner
from spi_agent.copilot.base.runner import console
from spi_agent.copilot.config import config
from spi_agent.copilot.trackers import DependsTracker

if TYPE_CHECKING:
    from spi_agent import SPIAgent


class DependsRunner(BaseRunner):
    """Runs dependency update analysis using Maven MCP server with live output"""

    def __init__(
        self,
        prompt_file: Union[Path, Traversable],
        services: List[str],
        agent: "SPIAgent",
        create_issue: bool = False,
        providers: Optional[List[str]] = None,
        include_testing: bool = False,
    ):
        """Initialize dependency analysis runner.

        Args:
            prompt_file: Path to dependency analysis prompt template
            services: List of service names to analyze
            agent: SPIAgent instance with MCP tools
            create_issue: Whether to create tracking issues for updates
            providers: Provider modules to include (default: ["azure"])
            include_testing: Whether to include testing modules (default: False)
        """
        super().__init__(prompt_file, services)
        self.agent = agent
        self.create_issue = create_issue
        self.providers = providers or ["azure"]
        self.include_testing = include_testing
        self.tracker = DependsTracker(services)
        self._log_file_handle = None

    @property
    def log_prefix(self) -> str:
        """Return log file prefix for this runner type."""
        return "depends"

    def _get_filter_instructions(self) -> str:
        """Generate filtering instructions based on provider/testing flags.

        Returns:
            Instructions for which modules to analyze
        """
        # Core is always included (it's the base, not a provider)
        # Providers are: core-plus, azure, aws, gcp, ibm
        # Default providers: azure

        if not self.providers or self.providers == ["all"]:
            # If no providers specified or "all", include everything
            modules_to_analyze = ["core", "core-plus", "azure", "aws", "gcp", "ibm"]
        else:
            # Always start with core (base dependency)
            # Then add the specified providers
            modules_to_analyze = ["core"] + list(self.providers)

        # Add testing if requested
        if self.include_testing:
            modules_to_analyze.append("testing")

        instructions = f"""From the dependency analysis results, ONLY analyze these modules:
{', '.join(modules_to_analyze)}

Use module paths to filter (e.g., "providers/partition-azure" matches "azure").

In MODULE_BREAKDOWN section, include ONLY the modules listed above.
Do NOT include other providers or testing modules unless specified.

IMPORTANT: "core" is always analyzed as the base dependency. Providers are: core-plus, azure, aws, gcp, ibm.
"""
        return instructions

    def load_prompt(self) -> str:
        """Load and augment prompt with arguments"""
        prompt = self.prompt_file.read_text(encoding="utf-8")

        # Replace organization placeholder
        prompt = prompt.replace("{{ORGANIZATION}}", config.organization)

        # Inject arguments
        services_arg = ",".join(self.services)
        providers_arg = ",".join(self.providers)
        augmented = f"{prompt}\n\nARGUMENTS:\nSERVICES: {services_arg}\nPROVIDERS: {providers_arg}\nINCLUDE_TESTING: {self.include_testing}\nCREATE_ISSUE: {self.create_issue}"

        return augmented

    def show_config(self):
        """Display run configuration"""
        if not self.providers or self.providers == ["all"]:
            providers_str = 'all'
        else:
            providers_str = ', '.join(self.providers)
        testing_str = 'included' if self.include_testing else 'excluded'

        config_text = f"""[cyan]Services:[/cyan]     {', '.join(self.services)}
[cyan]Modules:[/cyan]      core (always) + providers: {providers_str}
[cyan]Testing:[/cyan]      {testing_str}
[cyan]Create Issue:[/cyan] {'Yes' if self.create_issue else 'No'}"""

        console.print(Panel(config_text, title="Dependency Update Analysis", border_style="blue"))
        console.print()

    def parse_output(self, line: str) -> None:
        """Parse agent output for status updates.

        Args:
            line: Output line from agent
        """
        line_lower = line.lower()

        # Find which service this line is about
        target_service = None
        for service in self.services:
            if service in line_lower:
                target_service = service
                break

        if not target_service:
            return

        # Parse status indicators
        if "analyzing" in line_lower or "dependencies" in line_lower:
            self.tracker.update(target_service, "analyzing", "Analyzing dependencies")
        elif "checking" in line_lower or "versions" in line_lower:
            self.tracker.update(target_service, "checking", "Checking versions")
        elif "report" in line_lower or "generating" in line_lower:
            self.tracker.update(target_service, "reporting", "Generating report")

        # Extract update counts
        # Pattern: "X major, Y minor, Z patch"
        update_pattern = r'(\d+)\s+major.*?(\d+)\s+minor.*?(\d+)\s+patch'
        match = re.search(update_pattern, line_lower)
        if match:
            major = int(match.group(1))
            minor = int(match.group(2))
            patch = int(match.group(3))

            self.tracker.update(
                target_service,
                "complete",
                "Analysis complete",
                major_updates=major,
                minor_updates=minor,
                patch_updates=patch,
            )

    async def run_depends_for_service(self, service: str, layout, live) -> str:
        """Run dependency analysis for a single service with live progress updates.

        Args:
            service: Service name to analyze
            layout: Rich layout object for display updates
            live: Rich Live context for refreshing

        Returns:
            Agent response text
        """
        import time

        # Update tracker
        self.tracker.update(service, "analyzing", "Starting dependency analysis")

        # Load dependency check prompt template
        try:
            from importlib.resources import files
            check_prompt_file = files("spi_agent.copilot.prompts").joinpath("dependency_check.md")
            check_template = check_prompt_file.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error loading dependency check prompt template: {e}"

        # Replace template placeholders
        prompt = check_template.replace("{{SERVICE}}", service)
        prompt = prompt.replace("{{WORKSPACE}}", f"./repos/{service}")

        # Add filtering instructions based on provider/testing flags
        filter_instructions = self._get_filter_instructions()
        prompt = prompt.replace("{{FILTER_INSTRUCTIONS}}", filter_instructions)

        # Add issue creation if requested
        if self.create_issue:
            prompt += "\n\nAfter completing the analysis, create a GitHub tracking issue with the update recommendations."

        try:
            # Update status to checking
            self.tracker.update(service, "checking", "Checking dependency versions...")

            # Add analysis initiation to output panel
            # Use same logic as _get_filter_instructions for consistent display
            if not self.providers or self.providers == ["all"]:
                modules_to_analyze = ["core", "core-plus", "azure", "aws", "gcp", "ibm"]
            else:
                # Always start with core, then add requested providers
                modules_to_analyze = ["core"] + list(self.providers)
            if self.include_testing:
                modules_to_analyze.append("testing")

            self.output_lines.append(f"Starting dependency analysis for {service}...")
            self.output_lines.append(f"✓ Extract dependencies from POM")
            self.output_lines.append(f"   $ analyze_pom_file_tool")
            self.output_lines.append(f"     pom_file_path: ./repos/{service}/pom.xml")
            self.output_lines.append(f"✓ Batch check versions")
            self.output_lines.append(f"   $ check_version_batch_tool")
            self.output_lines.append(f"   ↪ Analyzing modules: {', '.join(modules_to_analyze)}")
            self.output_lines.append(f"   ↪ Checking Maven Central for updates...")

            # Initial update
            layout["status"].update(self.tracker.get_table())
            layout["output"].update(self._output_panel_renderable)

            # Create a task for the agent call
            agent_task = asyncio.create_task(
                self.agent.agent.run(prompt, thread=self.agent.agent.get_new_thread())
            )

            # Show progress while waiting
            start_time = time.time()
            last_update = start_time
            update_count = 0

            while not agent_task.done():
                await asyncio.sleep(0.5)  # Check every 500ms

                elapsed = int(time.time() - start_time)

                # Update status message every 2 seconds
                if time.time() - last_update >= 2:
                    status_messages = [
                        f"Extracting dependencies... ({elapsed}s)",
                        f"Checking versions on Maven Central... ({elapsed}s)",
                        f"Categorizing updates... ({elapsed}s)",
                        f"Processing results... ({elapsed}s)",
                    ]
                    msg = status_messages[(elapsed // 2) % len(status_messages)]

                    # Update tracker
                    old_status = dict(self.tracker.services)
                    self.tracker.update(service, "checking", msg)

                    # Update display periodically
                    update_count += 1
                    if old_status != self.tracker.services or update_count >= 10:
                        layout["status"].update(self.tracker.get_table())
                        update_count = 0

                    last_update = time.time()

            # Get the response
            response = await agent_task

            # Update status to processing results
            self.tracker.update(service, "reporting", "Processing analysis results...")

            # Parse response for update counts
            response_str = str(response)
            self.parse_agent_response(service, response_str)

            # Failsafe: Ensure status is marked complete if still checking/reporting
            svc_data = self.tracker.services[service]
            if svc_data['status'] in ['checking', 'reporting', 'analyzing']:
                # Force completion with whatever counts we have (even if 0)
                self.tracker.update(
                    service,
                    "complete",
                    f"{svc_data['major_updates'] + svc_data['minor_updates'] + svc_data['patch_updates']} updates found"
                )
                svc_data = self.tracker.services[service]

            # Add simple completion message
            total_updates = svc_data['major_updates'] + svc_data['minor_updates'] + svc_data['patch_updates']
            self.output_lines.append(f"✓ Analysis complete for {service}")

            # Also store in full_output for logs
            self.full_output.append(f"=== {service.upper()} DEPENDENCY ANALYSIS ===")
            self.full_output.append(response_str)
            self.full_output.append("")

            # Final update for this service
            layout["output"].update(self._output_panel_renderable)
            layout["status"].update(self.tracker.get_table())

            return response_str

        except Exception as e:
            self.tracker.update(service, "error", f"Failed: {str(e)[:50]}")
            layout["status"].update(self.tracker.get_table())
            return f"Error analyzing {service}: {str(e)}"

    def parse_agent_response(self, service: str, response: str):
        """Parse agent response to extract dependency metrics.

        Args:
            service: Service name
            response: Agent response text
        """
        response_lower = response.lower()

        # Initialize counts
        major_updates = 0
        minor_updates = 0
        patch_updates = 0
        total_dependencies = 0
        outdated_dependencies = 0

        # Parse structured output if present
        # Format: "Total: X dependencies scanned"
        total_pattern = r'total:\s*(\d+)\s+dependencies'
        total_match = re.search(total_pattern, response_lower)
        if total_match:
            total_dependencies = int(total_match.group(1))

        # Format: "Outdated: X dependencies"
        outdated_pattern = r'outdated:\s*(\d+)\s+dependencies'
        outdated_match = re.search(outdated_pattern, response_lower)
        if outdated_match:
            outdated_dependencies = int(outdated_match.group(1))

        # Format: "Major: X updates available"
        major_pattern = r'major:\s*(\d+)\s+updates?'
        major_match = re.search(major_pattern, response_lower)
        if major_match:
            major_updates = int(major_match.group(1))

        # Format: "Minor: X updates available"
        minor_pattern = r'minor:\s*(\d+)\s+updates?'
        minor_match = re.search(minor_pattern, response_lower)
        if minor_match:
            minor_updates = int(minor_match.group(1))

        # Format: "Patch: X updates available"
        patch_pattern = r'patch:\s*(\d+)\s+updates?'
        patch_match = re.search(patch_pattern, response_lower)
        if patch_match:
            patch_updates = int(patch_match.group(1))

        # Alternative format: "X major, Y minor, Z patch updates available"
        alt_pattern = r'(\d+)\s+major[,\s]+(\d+)\s+minor[,\s]+(\d+)\s+patch'
        alt_match = re.search(alt_pattern, response_lower)
        if alt_match and (major_updates == 0 and minor_updates == 0 and patch_updates == 0):
            major_updates = int(alt_match.group(1))
            minor_updates = int(alt_match.group(2))
            patch_updates = int(alt_match.group(3))

        # Extract module breakdown if present
        module_data = {}
        module_section = re.search(
            r'MODULE_BREAKDOWN:\s*\n(.*?)\nEND_MODULE_BREAKDOWN',
            response,
            re.DOTALL | re.IGNORECASE
        )
        if module_section:
            module_lines = module_section.group(1).strip().split('\n')
            for line in module_lines:
                line = line.strip()
                if '|' in line:
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) >= 4:
                        module_name = parts[0]
                        module_data[module_name] = {
                            'major': int(parts[1]) if parts[1].isdigit() else 0,
                            'minor': int(parts[2]) if parts[2].isdigit() else 0,
                            'patch': int(parts[3]) if parts[3].isdigit() else 0,
                        }

        # Store module breakdown
        if module_data:
            self.tracker.services[service]["modules"] = module_data

            # Recalculate totals from filtered modules only
            filtered_major = sum(m.get('major', 0) for m in module_data.values())
            filtered_minor = sum(m.get('minor', 0) for m in module_data.values())
            filtered_patch = sum(m.get('patch', 0) for m in module_data.values())

            # Override with filtered totals
            major_updates = filtered_major
            minor_updates = filtered_minor
            patch_updates = filtered_patch

        # Extract top updates if present
        top_updates = self._extract_top_updates(response)

        # Extract report ID if available
        report_id = ""
        report_match = re.search(r'report[:\s]+([a-zA-Z0-9\-]+)', response_lower)
        if report_match:
            report_id = report_match.group(1)

        # Update tracker with findings
        status = "complete" if major_updates + minor_updates + patch_updates > 0 else "success"
        details = f"{major_updates + minor_updates + patch_updates} updates available" if major_updates + minor_updates + patch_updates > 0 else "All up-to-date"

        self.tracker.update(
            service,
            status,
            details,
            major_updates=major_updates,
            minor_updates=minor_updates,
            patch_updates=patch_updates,
            total_dependencies=total_dependencies,
            outdated_dependencies=outdated_dependencies,
            report_id=report_id,
            top_updates=top_updates,
        )

    def _extract_top_updates(self, response: str) -> list:
        """Extract top update recommendations from agent response.

        Args:
            response: Agent response text

        Returns:
            List of update dictionaries
        """
        updates = []

        # Look for TOP_UPDATES section
        updates_section = re.search(
            r'TOP_UPDATES:\s*\n(.*?)\nEND_TOP_UPDATES',
            response,
            re.DOTALL | re.IGNORECASE
        )

        if updates_section:
            content = updates_section.group(1)
            # Parse individual updates
            # Format:
            # 1. groupId:artifactId
            #    Current: version
            #    Latest: version
            #    Category: Major|Minor|Patch
            #    Reason: description

            lines = content.split('\n')
            i = 0
            while i < len(lines):
                line = lines[i].strip()

                # Look for numbered item
                if re.match(r'^\d+\.\s+', line):
                    artifact = line.split('.', 1)[1].strip()

                    update_data = {
                        "artifact": artifact,
                        "current": None,
                        "patch": None,
                        "minor": None,
                        "major": None,
                        "latest": None,  # Keep for backward compatibility
                        "category": None,
                        "module": None,
                        "reason": None,
                    }

                    # Parse following lines for metadata
                    j = i + 1
                    while j < len(lines) and lines[j].strip() and not re.match(r'^\d+\.', lines[j]):
                        meta_line = lines[j].strip()
                        if ':' in meta_line:
                            field, value = meta_line.split(':', 1)
                            field_lower = field.lower().strip()
                            value = value.strip()

                            if 'current' in field_lower:
                                update_data["current"] = value
                            elif 'patch' in field_lower:
                                update_data["patch"] = value
                            elif 'minor' in field_lower:
                                update_data["minor"] = value
                            elif 'major' in field_lower:
                                update_data["major"] = value
                            elif 'latest' in field_lower:
                                update_data["latest"] = value
                            elif 'category' in field_lower:
                                update_data["category"] = value
                            elif 'module' in field_lower:
                                update_data["module"] = value
                            elif 'reason' in field_lower:
                                update_data["reason"] = value

                        j += 1

                    updates.append(update_data)
                    i = j
                else:
                    i += 1

        return updates[:10]  # Limit to top 10

    def _calculate_service_grade(self, outdated: int, total: int) -> str:
        """Calculate quality grade based on dependency freshness.

        Args:
            outdated: Number of outdated dependencies
            total: Total number of dependencies

        Returns:
            Letter grade (A, B, C, D, F)
        """
        if total == 0:
            return "A"

        percentage = (outdated / total) * 100

        # Grading based on percentage of outdated dependencies
        if percentage <= 5:
            return "A"  # Excellent - 0-5% outdated
        elif percentage <= 15:
            return "B"  # Good - 6-15% outdated
        elif percentage <= 30:
            return "C"  # Needs attention - 16-30% outdated
        elif percentage <= 50:
            return "D"  # Poor - 31-50% outdated
        else:
            return "F"  # Critical - >50% outdated

    def _get_risk_level(self, grade: str) -> tuple[str, str]:
        """Get risk level and color based on grade.

        Args:
            grade: Letter grade

        Returns:
            Tuple of (risk_level, color)
        """
        risk_mapping = {
            "A": ("EXCELLENT", "green"),
            "B": ("GOOD", "blue"),
            "C": ("NEEDS ATTENTION", "yellow"),
            "D": ("POOR", "red"),
            "F": ("CRITICAL", "red bold"),
        }
        return risk_mapping.get(grade, ("UNKNOWN", "white"))

    def _get_recommendation(self, major: int, minor: int, patch: int, grade: str) -> str:
        """Get recommendation based on update counts and grade.

        Args:
            major: Number of major updates
            minor: Number of minor updates
            patch: Number of patch updates
            grade: Letter grade

        Returns:
            Recommendation text
        """
        if grade == "A":
            return "All dependencies up-to-date or minimal updates needed"
        elif grade == "B":
            total = major + minor + patch
            return f"Update {total} dependencies in next sprint"
        elif grade == "C":
            if major > 0:
                return f"PRIORITY: Review {major} major update{'s' if major > 1 else ''}, then apply {minor + patch} other updates"
            return f"Update {minor + patch} dependencies within 2 weeks"
        elif grade == "D":
            if major > 0:
                return f"URGENT: {major} major update{'s' if major > 1 else ''} + {minor + patch} other updates require immediate planning"
            return f"URGENT: {minor + patch} updates needed - dependencies falling behind"
        else:  # F
            return f"CRITICAL: {major + minor + patch} updates needed - immediate action required to avoid technical debt"

    def get_dependency_assessment_panel(self) -> Panel:
        """Generate dependency assessment panel with module-level breakdown.

        Returns:
            Rich Panel with dependency table showing update counts
        """
        # Create table
        table = Table(show_header=True, header_style="bold", box=None)
        table.add_column("Service", style="cyan", width=20)
        table.add_column("Major", style="red", justify="right", width=8)
        table.add_column("Minor", style="yellow", justify="right", width=8)
        table.add_column("Patch", style="blue", justify="right", width=8)
        table.add_column("Total Deps", style="dim", justify="right", width=12)

        # Track overall totals
        total_major = 0
        total_minor = 0
        total_patch = 0
        total_deps = 0

        # Add rows for each service
        for service, data in self.tracker.services.items():
            status = data.get("status", "unknown")

            # Check if analysis failed
            if status == "error":
                error_details = data.get("details", "Analysis failed")
                table.add_row(
                    service,
                    Text("—", style="dim"),
                    Text("—", style="dim"),
                    Text("—", style="dim"),
                    Text(f"Error: {error_details}", style="red")
                )
                continue

            # Get service-level counts
            major = data.get("major_updates", 0)
            minor = data.get("minor_updates", 0)
            patch = data.get("patch_updates", 0)
            total = data.get("total_dependencies", 0)

            total_major += major
            total_minor += minor
            total_patch += patch
            total_deps += total

            # Format counts
            major_str = str(major) if major > 0 else "—"
            minor_str = str(minor) if minor > 0 else "—"
            patch_str = str(patch) if patch > 0 else "—"

            table.add_row(
                service,
                major_str,
                minor_str,
                patch_str,
                str(total)
            )

        # Subtitle with totals
        total_services = len(self.tracker.services)
        subtitle = f"{total_services} service{'s' if total_services > 1 else ''} analyzed | "
        subtitle += f"{total_major}M / {total_minor}m / {total_patch}p updates available | {total_deps} total dependencies"

        return Panel(
            table,
            title="Dependency Assessment",
            subtitle=subtitle,
            border_style="blue",
            padding=(1, 2)
        )

    def get_updates_summary_panel(self) -> Panel:
        """Generate summary table of dependency updates.

        Returns:
            Rich Panel with updates table
        """
        from rich.text import Text

        # Collect all updates from all services
        all_updates = []
        for service, data in self.tracker.services.items():
            top_updates = data.get("top_updates", [])
            for update in top_updates:
                all_updates.append({
                    "service": service,
                    "artifact": update.get("artifact", ""),
                    "current": update.get("current", ""),
                    "patch": update.get("patch"),
                    "minor": update.get("minor"),
                    "major": update.get("major"),
                    "latest": update.get("latest", ""),
                    "category": update.get("category", ""),
                    "module": update.get("module", ""),
                })

        if not all_updates:
            return Panel(
                "[dim]No dependency updates found[/dim]",
                title="📋 Dependency Updates",
                border_style="green",
                padding=(1, 2)
            )

        # Create summary table
        table = Table(show_header=True, header_style="bold", box=None, expand=True)
        table.add_column("Dependency", style="cyan", no_wrap=False, width=35)
        table.add_column("Module", style="magenta", width=12)
        table.add_column("Current", style="yellow", width=10)
        table.add_column("Latest", style="green", width=10)
        table.add_column("Type", justify="center", width=8)

        # Add rows
        for update in all_updates[:15]:  # Limit to top 15
            artifact = update["artifact"]
            module = update["module"] or "-"
            current = update["current"]

            # Determine latest version (prefer major > minor > patch > latest field)
            major_ver = update.get("major")
            minor_ver = update.get("minor")
            patch_ver = update.get("patch")

            # Check if values are valid (not None, not empty, not "none" string)
            def is_valid_version(v):
                return v and v not in ["none", "None", "-", ""]

            # Use highest available version
            if is_valid_version(major_ver):
                latest = major_ver
                type_style = "red bold"
                type_text = "Major"
            elif is_valid_version(minor_ver):
                latest = minor_ver
                type_style = "yellow"
                type_text = "Minor"
            elif is_valid_version(patch_ver):
                latest = patch_ver
                type_style = "blue"
                type_text = "Patch"
            else:
                # Fallback to old format
                latest = update.get("latest", "-")
                category = update.get("category", "")
                if category and "major" in category.lower():
                    type_style = "red bold"
                    type_text = "Major"
                elif category and "minor" in category.lower():
                    type_style = "yellow"
                    type_text = "Minor"
                elif category and "patch" in category.lower():
                    type_style = "blue"
                    type_text = "Patch"
                else:
                    type_style = "white"
                    type_text = "-"

            table.add_row(
                artifact,
                module,
                current,
                latest or "-",
                Text(type_text, style=type_style)
            )

        subtitle = f"Showing top {min(len(all_updates), 15)} of {len(all_updates)} updates"
        return Panel(
            table,
            title="Dependency Versions",
            subtitle=subtitle,
            border_style="yellow",
            padding=(1, 2)
        )

    async def _analyze_dependencies_with_agent(self) -> str:
        """Use agent to analyze and consolidate dependency findings across services.

        Returns:
            Agent-generated dependency analysis report
        """
        # Build log content from in-memory data
        summary = self.tracker.get_summary()

        log_parts = []
        log_parts.append("="*70)
        log_parts.append("Dependency Update Analysis Log")
        log_parts.append("="*70)
        log_parts.append(f"Timestamp: {datetime.now().isoformat()}")
        log_parts.append(f"Services: {', '.join(self.services)}")
        providers_str = ', '.join(self.providers)
        log_parts.append(f"Providers: {providers_str}")
        log_parts.append(f"="*70)
        log_parts.append("")
        log_parts.append("=== ANALYSIS RESULTS ===")
        log_parts.append("")

        for service, data in self.tracker.services.items():
            log_parts.append(f"{service}:")
            log_parts.append(f"  Status: {data['status']}")
            log_parts.append(f"  Major Updates: {data['major_updates']}")
            log_parts.append(f"  Minor Updates: {data['minor_updates']}")
            log_parts.append(f"  Patch Updates: {data['patch_updates']}")
            log_parts.append(f"  Total Dependencies: {data['total_dependencies']}")
            log_parts.append(f"  Outdated: {data['outdated_dependencies']}")
            log_parts.append("")

        log_parts.append("=== SUMMARY ===")
        log_parts.append("")
        log_parts.append(f"Total Services: {summary['total_services']}")
        log_parts.append(f"Total Major Updates: {summary['major_updates']}")
        log_parts.append(f"Total Minor Updates: {summary['minor_updates']}")
        log_parts.append(f"Total Patch Updates: {summary['patch_updates']}")
        log_parts.append("")
        log_parts.append("=== FULL OUTPUT ===")
        log_parts.append("")
        log_parts.extend(self.full_output)

        log_content = "\n".join(log_parts)

        # Load dependency analysis prompt template
        try:
            from importlib.resources import files
            prompt_file = files("spi_agent.copilot.prompts").joinpath("dependency_analysis.md")
            prompt_template = prompt_file.read_text(encoding="utf-8")

            # Replace placeholder with actual scan results
            prompt = prompt_template.replace("{{SCAN_RESULTS}}", log_content)
        except Exception as e:
            return f"Error loading dependency analysis prompt: {e}"

        try:
            # Call agent to analyze
            response = await self.agent.agent.run(
                prompt,
                thread=self.agent.agent.get_new_thread()
            )
            return str(response)
        except Exception as e:
            return f"Error analyzing dependencies: {e}"

    def get_update_details_panel(self, dependency_analysis: str = None) -> Panel:
        """Generate update details panel with consolidated cross-service report.

        Args:
            dependency_analysis: Agent-generated dependency analysis (if available)

        Returns:
            Rich Panel with update details
        """
        if not dependency_analysis:
            return Panel(
                "[dim]Dependency analysis not available yet...[/dim]",
                title="Dependency Analysis",
                border_style="blue"
            )

        # Display agent analysis directly
        return Panel(
            dependency_analysis,
            title="Dependency Analysis",
            border_style="blue",
            padding=(1, 2)
        )

    def _append_to_log(self, text: str):
        """Append text to log file immediately (streaming).

        Args:
            text: Text to append to log file
        """
        if self._log_file_handle is None:
            # Open log file for streaming writes
            self._log_file_handle = open(self.log_file, "w", buffering=1)  # Line buffered
            # Write header
            self._log_file_handle.write(f"{'='*70}\n")
            self._log_file_handle.write("Dependency Update Analysis Log\n")
            self._log_file_handle.write(f"{'='*70}\n")
            self._log_file_handle.write(f"Timestamp: {datetime.now().isoformat()}\n")
            self._log_file_handle.write(f"Services: {', '.join(self.services)}\n")
            providers_str = ', '.join(self.providers)
            self._log_file_handle.write(f"Providers: {providers_str}\n")
            self._log_file_handle.write(f"Include Testing: {self.include_testing}\n")
            self._log_file_handle.write(f"Create Issue: {self.create_issue}\n")
            self._log_file_handle.write(f"{'='*70}\n\n")
            self._log_file_handle.write("=== ANALYSIS OUTPUT (STREAMING) ===\n\n")
            self._log_file_handle.flush()

        # Append the text
        self._log_file_handle.write(text + "\n")
        self._log_file_handle.flush()

    async def run(self) -> int:
        """Execute dependency analysis with live output.

        Returns:
            Exit code (0 for success, 1 for error)
        """
        self.show_config()

        # Create layout
        layout = self.create_layout()
        layout["status"].update(self.tracker.get_table())
        layout["output"].update(self._output_panel_renderable)

        try:
            # Run with Live display
            with Live(layout, console=console, refresh_per_second=2) as live:
                # Run services in parallel (max 2 at a time)
                from asyncio import Semaphore, gather

                # Limit concurrent analysis to 2
                semaphore = Semaphore(2)

                async def run_with_limit(service, svc_idx):
                    async with semaphore:
                        start_msg = f"Starting dependency analysis for {service}..."
                        self.full_output.append(start_msg)
                        self._append_to_log(start_msg)

                        # Update display
                        layout["output"].update(self._output_panel_renderable)
                        layout["status"].update(self.tracker.get_table())

                        # Run dependency analysis for this service
                        response = await self.run_depends_for_service(service, layout, live)

                        # Store response for logs
                        self.full_output.append(response)
                        self._append_to_log(f"\n=== {service.upper()} ANALYSIS RESULT ===\n")
                        self._append_to_log(response)
                        self._append_to_log("")

                        return response

                # Launch all services in parallel (controlled by semaphore)
                tasks = [run_with_limit(service, idx) for idx, service in enumerate(self.services, 1)]
                responses = await gather(*tasks)

                # Add completion message
                complete_msg = "✓ Analysis complete for all services"
                self.output_lines.append(complete_msg)
                self._append_to_log(f"\n{complete_msg}")
                layout["output"].update(self._output_panel_renderable)
                layout["status"].update(self.tracker.get_table())

                # Add consolidation message
                consolidation_msg = "   ↪ Generating cross-service recommendations..."
                self.output_lines.append(consolidation_msg)
                self._append_to_log(consolidation_msg)
                layout["output"].update(self._output_panel_renderable)

                # Analyze dependencies with agent
                dependency_analysis = await self._analyze_dependencies_with_agent()

                # Add completion message
                final_msg = "✓ Dependency analysis complete"
                self.output_lines.append(final_msg)
                self._append_to_log(f"\n{final_msg}")
                self._append_to_log(f"\n=== CROSS-SERVICE ANALYSIS ===\n")
                self._append_to_log(dependency_analysis)
                layout["output"].update(self._output_panel_renderable)
                layout["status"].update(self.tracker.get_table())

                # Final update
                live.refresh()

            # Post-processing outside Live context
            # Display all panels
            console.print()
            console.print(self.get_dependency_assessment_panel())
            console.print(self.get_updates_summary_panel())
            console.print(self.get_update_details_panel(dependency_analysis))

            # Finalize log with summary
            self._finalize_log(0)

            return 0

        except Exception as e:
            console.print(f"[red]Error executing dependency analysis:[/red] {e}", style="bold red")
            import traceback
            traceback.print_exc()

            # Close log file handle on error
            if self._log_file_handle:
                self._append_to_log(f"\n=== ERROR ===\n{str(e)}")
                self._log_file_handle.close()
                self._log_file_handle = None

            return 1
        finally:
            # Ensure log file handle is closed
            if self._log_file_handle:
                self._log_file_handle.close()
                self._log_file_handle = None

    def _finalize_log(self, return_code: int):
        """Finalize log file with summary statistics.

        Args:
            return_code: Process return code
        """
        try:
            if self._log_file_handle is None:
                # Log was never opened (shouldn't happen, but handle gracefully)
                self._save_log(return_code)
                return

            # Add summary statistics at the end
            summary = self.tracker.get_summary()

            self._append_to_log(f"\n{'='*70}")
            self._append_to_log("=== FINAL SUMMARY ===")
            self._append_to_log(f"{'='*70}\n")

            self._append_to_log(f"Exit Code: {return_code}")
            self._append_to_log(f"Total Services: {summary['total_services']}")
            self._append_to_log(f"Completed: {summary['completed_services']}")
            self._append_to_log(f"Errors: {summary['error_services']}")
            self._append_to_log(f"Total Major Updates: {summary['major_updates']}")
            self._append_to_log(f"Total Minor Updates: {summary['minor_updates']}")
            self._append_to_log(f"Total Patch Updates: {summary['patch_updates']}\n")

            self._append_to_log("=== SERVICE DETAILS ===\n")
            for service, data in self.tracker.services.items():
                self._append_to_log(f"{service}:")
                self._append_to_log(f"  Status: {data['status']}")
                self._append_to_log(f"  Major Updates: {data['major_updates']}")
                self._append_to_log(f"  Minor Updates: {data['minor_updates']}")
                self._append_to_log(f"  Patch Updates: {data['patch_updates']}")
                self._append_to_log(f"  Total Dependencies: {data['total_dependencies']}")
                self._append_to_log(f"  Outdated: {data['outdated_dependencies']}")
                if data['report_id']:
                    self._append_to_log(f"  Report ID: {data['report_id']}")
                self._append_to_log(f"  Details: {data['details']}")
                self._append_to_log("")
        except Exception as e:
            console.print(f"[dim]Warning: Could not finalize log: {e}[/dim]")

    def _save_log(self, return_code: int):
        """Fallback method to save log if streaming didn't work.

        Args:
            return_code: Process return code
        """
        try:
            with open(self.log_file, "w") as f:
                f.write(f"{'='*70}\n")
                f.write("Dependency Update Analysis Log\n")
                f.write(f"{'='*70}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Services: {', '.join(self.services)}\n")
                providers_str = ', '.join(self.providers)
                f.write(f"Providers: {providers_str}\n")
                f.write(f"Include Testing: {self.include_testing}\n")
                f.write(f"Create Issue: {self.create_issue}\n")
                f.write(f"Exit Code: {return_code}\n")
                f.write(f"{'='*70}\n\n")

                f.write("=== ANALYSIS RESULTS ===\n\n")
                for service, data in self.tracker.services.items():
                    f.write(f"{service}:\n")
                    f.write(f"  Status: {data['status']}\n")
                    f.write(f"  Major Updates: {data['major_updates']}\n")
                    f.write(f"  Minor Updates: {data['minor_updates']}\n")
                    f.write(f"  Patch Updates: {data['patch_updates']}\n")
                    f.write(f"  Total Dependencies: {data['total_dependencies']}\n")
                    f.write(f"  Outdated: {data['outdated_dependencies']}\n")
                    if data['report_id']:
                        f.write(f"  Report ID: {data['report_id']}\n")
                    f.write(f"  Details: {data['details']}\n")
                    f.write("\n")

                # Add summary
                summary = self.tracker.get_summary()
                f.write("=== SUMMARY ===\n\n")
                f.write(f"Total Services: {summary['total_services']}\n")
                f.write(f"Completed: {summary['completed_services']}\n")
                f.write(f"Errors: {summary['error_services']}\n")
                f.write(f"Total Major Updates: {summary['major_updates']}\n")
                f.write(f"Total Minor Updates: {summary['minor_updates']}\n")
                f.write(f"Total Patch Updates: {summary['patch_updates']}\n")

                f.write("\n=== FULL OUTPUT ===\n\n")
                f.write("\n".join(self.full_output))
        except Exception as e:
            console.print(f"[dim]Warning: Could not save log: {e}[/dim]")

    def get_results_panel(self, return_code: int) -> Panel:
        """Generate final results panel (required by base class).

        Args:
            return_code: Process return code

        Returns:
            Rich Panel with dependency assessment
        """
        return self.get_dependency_assessment_panel()
