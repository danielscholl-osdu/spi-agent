"""Triage runner for Maven dependency and vulnerability analysis."""

import asyncio
import re
from datetime import datetime
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Union

from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from spi_agent.copilot.base import BaseRunner
from spi_agent.copilot.base.runner import console
from spi_agent.copilot.config import config
from spi_agent.copilot.trackers import TriageTracker

if TYPE_CHECKING:
    from spi_agent import SPIAgent


class TriageRunner(BaseRunner):
    """Runs triage analysis using Maven MCP server with live output"""

    def __init__(
        self,
        prompt_file: Union[Path, Traversable],
        services: List[str],
        agent: "SPIAgent",
        create_issue: bool = False,
        severity_filter: Optional[List[str]] = None,
    ):
        """Initialize triage runner.

        Args:
            prompt_file: Path to triage prompt template
            services: List of service names to analyze
            agent: SPIAgent instance with MCP tools
            create_issue: Whether to create tracking issues for findings
            severity_filter: List of severity levels to include (critical, high, medium)
        """
        super().__init__(prompt_file, services)
        self.agent = agent
        self.create_issue = create_issue
        self.severity_filter = severity_filter or ["critical", "high", "medium"]
        self.tracker = TriageTracker(services)

    @property
    def log_prefix(self) -> str:
        """Return log file prefix for this runner type."""
        return "triage"

    def load_prompt(self) -> str:
        """Load and augment prompt with arguments"""
        prompt = self.prompt_file.read_text(encoding="utf-8")

        # Replace organization placeholder
        prompt = prompt.replace("{{ORGANIZATION}}", config.organization)

        # Inject arguments
        services_arg = ",".join(self.services)
        severity_arg = ",".join(self.severity_filter)
        augmented = f"{prompt}\n\nARGUMENTS:\nSERVICES: {services_arg}\nSEVERITY_FILTER: {severity_arg}\nCREATE_ISSUE: {self.create_issue}"

        return augmented

    def show_config(self):
        """Display run configuration"""
        config_text = f"""[cyan]Services:[/cyan]     {', '.join(self.services)}
[cyan]Severity:[/cyan]     {', '.join(self.severity_filter).upper()}
[cyan]Create Issue:[/cyan] {'Yes' if self.create_issue else 'No'}"""

        console.print(Panel(config_text, title="🔍 Maven Triage Analysis", border_style="blue"))
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
        if "analyzing" in line_lower or "triage" in line_lower or "dependencies" in line_lower:
            self.tracker.update(target_service, "analyzing", "Analyzing dependencies")
        elif "scan" in line_lower or "vulnerabilities" in line_lower:
            self.tracker.update(target_service, "scanning", "Scanning for vulnerabilities")
        elif "report" in line_lower or "findings" in line_lower:
            self.tracker.update(target_service, "reporting", "Generating report")

        # Extract vulnerability counts
        # Pattern: "X critical, Y high, Z medium"
        vuln_pattern = r'(\d+)\s+critical.*?(\d+)\s+high.*?(\d+)\s+medium'
        match = re.search(vuln_pattern, line_lower)
        if match:
            critical = int(match.group(1))
            high = int(match.group(2))
            medium = int(match.group(3))

            self.tracker.update(
                target_service,
                "complete",
                "Analysis complete",
                critical=critical,
                high=high,
                medium=medium,
            )

        # Alternative pattern: individual counts
        if "critical" in line_lower:
            critical_match = re.search(r'(\d+)\s+critical', line_lower)
            if critical_match:
                critical = int(critical_match.group(1))
                current = self.tracker.services[target_service]
                self.tracker.update(
                    target_service,
                    current["status"],
                    current["details"],
                    critical=critical,
                )

    async def run_triage_for_service(self, service: str, layout, live) -> str:
        """Run triage analysis for a single service with live progress updates.

        Args:
            service: Service name to analyze
            layout: Rich layout object for display updates
            live: Rich Live context for refreshing

        Returns:
            Agent response text
        """
        import time

        # Update tracker
        self.tracker.update(service, "analyzing", "Starting triage analysis")
        layout["status"].update(self.tracker.get_table())
        live.refresh()

        # Construct very direct prompt to execute the scan tool immediately
        severity_str = ','.join(self.severity_filter).upper()
        prompt = f"""Execute a complete Maven dependency and vulnerability triage for the {service} service.

**ACTION REQUIRED - DO NOT ASK FOR CONFIRMATION:**
1. Run scan_java_project_tool with these exact parameters:
   - workspace: ./repos/{service}
   - scan_mode: workspace
   - severity_filter: {severity_str}
   - max_results: 100

2. After the scan completes, provide a concise summary with:
   - Total vulnerabilities found (count by severity: Critical, High, Medium)
   - Top 5 critical/high findings with CVE IDs, CVSS scores, affected packages
   - Recommended remediation steps

**DO NOT:**
- Ask me which option to choose
- Wait for confirmation
- Show me the triage template

**EXECUTE THE SCAN NOW and return the actual vulnerability findings.**"""

        if self.create_issue:
            prompt += "\n- After the scan, create a GitHub tracking issue with the findings"

        try:
            # Update status to scanning
            self.tracker.update(service, "scanning", "Running vulnerability scan...")
            layout["status"].update(self.tracker.get_table())
            live.refresh()

            # Create a task for the agent call
            agent_task = asyncio.create_task(
                self.agent.agent.run(prompt, thread=self.agent.agent.get_new_thread())
            )

            # Show progress while waiting
            start_time = time.time()
            last_update = start_time

            while not agent_task.done():
                await asyncio.sleep(0.5)  # Check every 500ms

                elapsed = int(time.time() - start_time)

                # Update status message every 2 seconds
                if time.time() - last_update >= 2:
                    status_messages = [
                        f"Scanning dependencies... ({elapsed}s)",
                        f"Analyzing vulnerabilities... ({elapsed}s)",
                        f"Checking CVE database... ({elapsed}s)",
                        f"Processing results... ({elapsed}s)",
                    ]
                    msg = status_messages[(elapsed // 2) % len(status_messages)]

                    self.tracker.update(service, "scanning", msg)
                    layout["status"].update(self.tracker.get_table())
                    live.refresh()
                    last_update = time.time()

            # Get the response
            response = await agent_task

            # Update status to processing results
            self.tracker.update(service, "reporting", "Processing scan results...")
            layout["status"].update(self.tracker.get_table())
            live.refresh()

            # Parse response for vulnerability counts and CVE details
            response_str = str(response)
            self.parse_agent_response(service, response_str)

            # Update CVE details panel
            layout["output"].update(self.get_cve_details_panel())
            layout["status"].update(self.tracker.get_table())
            live.refresh()

            return response_str

        except Exception as e:
            self.tracker.update(service, "error", f"Failed: {str(e)[:50]}")
            layout["status"].update(self.tracker.get_table())
            live.refresh()
            return f"Error analyzing {service}: {str(e)}"

    def parse_agent_response(self, service: str, response: str):
        """Parse agent response to extract vulnerability metrics.

        Args:
            service: Service name
            response: Agent response text
        """
        response_lower = response.lower()

        # Try to extract vulnerability counts from response
        # Pattern 1: "X critical, Y high, Z medium"
        vuln_pattern = r'(\d+)\s+critical.*?(\d+)\s+high.*?(\d+)\s+medium'
        match = re.search(vuln_pattern, response_lower)

        if match:
            critical = int(match.group(1))
            high = int(match.group(2))
            medium = int(match.group(3))
        else:
            # Pattern 2: Individual lines
            critical = 0
            high = 0
            medium = 0

            critical_match = re.search(r'critical[:\s]+(\d+)', response_lower)
            if critical_match:
                critical = int(critical_match.group(1))

            high_match = re.search(r'high[:\s]+(\d+)', response_lower)
            if high_match:
                high = int(high_match.group(1))

            medium_match = re.search(r'medium[:\s]+(\d+)', response_lower)
            if medium_match:
                medium = int(medium_match.group(1))

        # Extract dependency count if available
        dependencies = 0
        dep_match = re.search(r'(\d+)\s+dependenc', response_lower)
        if dep_match:
            dependencies = int(dep_match.group(1))

        # Extract report ID if available
        report_id = ""
        report_match = re.search(r'report[- ]id[:\s]+([a-zA-Z0-9\-]+)', response_lower)
        if report_match:
            report_id = report_match.group(1)

        # Extract detailed CVE information with all metadata
        top_cves = self._extract_cve_details(response)

        # Extract remediation recommendations
        remediation = self._extract_remediation(response)

        # Update tracker with findings
        status = "complete" if critical + high + medium > 0 or "complete" in response_lower else "success"
        details = f"{critical + high + medium} vulnerabilities found" if critical + high + medium > 0 else "No critical issues"

        self.tracker.update(
            service,
            status,
            details,
            critical=critical,
            high=high,
            medium=medium,
            dependencies=dependencies,
            report_id=report_id,
            top_cves=top_cves,
            remediation=remediation,
        )

    def _extract_cve_details(self, response: str) -> list:
        """Extract detailed CVE information from agent response.

        Args:
            response: Agent response text

        Returns:
            List of CVE dictionaries with full metadata
        """
        cves = []

        # Pattern for detailed CVE format (actual format from agent - TWO FORMATS):
        # Format 1:
        # 1) CVE-2022-22965
        #    - Severity: Critical
        #    - Affected package: org.springframework:spring-beans
        #    - Installed version (example location): 5.2.7.RELEASE
        #    - Scanner recommendation: upgrade to 5.2.20.RELEASE or 5.3.18
        #    - Reference: https://nvd.nist.gov/vuln/detail/CVE-2022-22965
        #
        # Format 2:
        # 1) CVE-2025-24813 — critical
        #    - Affected artifact: org.apache.tomcat.embed:tomcat-embed-core
        #    - Installed version found: 10.1.18
        #    - Fix / recommended version: 11.0.3, 10.1.35, 9.0.99
        #    - Reference: https://nvd.nist.gov/vuln/detail/CVE-2025-24813

        lines = response.split('\n')

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Try flexible CVE header patterns
            # Format 1: CVE-2025-24813 (critical)  <- Severity in parentheses
            # Format 2: CVE-2025-24813 — critical  <- Severity after em-dash
            # Format 3: CVE-2025-24813             <- CVE alone

            cve_match = re.match(r'^\d+\)\s+(CVE-\d{4}-\d+)(?:\s+[—-]\s+|\s+\()?([^)\n]+)?', line, re.IGNORECASE)

            if cve_match:
                cve_id = cve_match.group(1)
                post_cve = cve_match.group(2)  # Could be severity or package or None
                severity = None
                initial_package = None

                # Parse what follows the CVE ID
                if post_cve:
                    post_cve = post_cve.strip().rstrip(')')  # Remove trailing paren if present

                    # Check if it's a severity keyword
                    severity_keywords = {"critical", "high", "medium", "low"}
                    tokens = post_cve.split()
                    first_token_lower = tokens[0].lower().rstrip(':') if tokens else ""

                    if first_token_lower in severity_keywords:
                        severity = tokens[0].rstrip(':').title()
                        # Rest might be package name
                        remaining = ' '.join(tokens[1:]).strip()
                        if remaining:
                            initial_package = remaining
                    else:
                        # Not a severity, might be package name
                        initial_package = post_cve

                cve_data = {
                    "cve_id": cve_id,
                    "package": None,
                    "version": None,
                    "severity": severity,
                    "fixed_versions": None,
                    "nvd_link": None,
                }

                # Set initial package if found in header
                if initial_package:
                    package_name = initial_package
                    # Remove trailing context commonly appended in reports
                    package_name = re.split(r'\(installed| - Severity', package_name, maxsplit=1)[0].strip()
                    if package_name:
                        cve_data["package"] = package_name

                # Parse the following lines for metadata
                j = i + 1
                while j < len(lines) and lines[j].strip().startswith('-'):
                    metadata_line = lines[j].strip()[1:].strip()  # Remove leading "-"
                    metadata_line_lower = metadata_line.lower()

                    # Skip empty lines
                    if not metadata_line or ':' not in metadata_line:
                        j += 1
                        continue

                    # Split field and value
                    field_part, value_part = metadata_line.split(':', 1)
                    field_lower = field_part.lower().strip()
                    value = value_part.strip()

                    # Use flexible keyword matching with substring search (not word boundaries)
                    # This handles variations like "recommendation" matching "recommend"

                    # Severity - look for "severity" keyword
                    if 'severity' in field_lower:
                        severity_word = value.split()[0] if value else ""
                        if severity_word:
                            cve_data["severity"] = severity_word.title()

                    # Package/Artifact - look for "affected", "package", or "artifact" keywords
                    elif ('affected' in field_lower or 'package' in field_lower or 'artifact' in field_lower) and not cve_data["package"]:
                        # Remove extra context like version info
                        package_name = re.split(r'\s*—\s+installed|\s+—\s+installed|\(installed', value, maxsplit=1)[0].strip()
                        if package_name:
                            cve_data["package"] = package_name

                    # Version - look for "installed" and "version" keywords together
                    elif ('installed' in field_lower and 'version' in field_lower) and not cve_data["version"]:
                        # Extract just the version, ignore paths/locations in parentheses
                        if '(' in value:
                            cve_data["version"] = value.split('(')[0].strip()
                        else:
                            cve_data["version"] = value

                    # Fix/Recommended versions - look for "fix", "recommend", "upgrade" keywords (substring match)
                    elif ('fix' in field_lower or 'recommend' in field_lower or 'upgrade' in field_lower) and not cve_data["fixed_versions"]:
                        # Remove "upgrade to" prefix if present
                        rec_part = re.sub(r'^\s*upgrade\s+to\s+', '', value, flags=re.IGNORECASE)
                        cve_data["fixed_versions"] = rec_part

                    # Reference/NVD links - look for "reference", "nvd", "cve", "link", "detail" keywords (substring match)
                    elif ('reference' in field_lower or 'nvd' in field_lower or 'cve' in field_lower or 'link' in field_lower or 'detail' in field_lower) and not cve_data["nvd_link"]:
                        # Extract URL if present
                        url_match = re.search(r'https?://[^\s]+', value)
                        if url_match:
                            cve_data["nvd_link"] = url_match.group(0)
                        else:
                            cve_data["nvd_link"] = value

                    j += 1

                # Only add if critical or high severity
                if cve_data["severity"] and cve_data["severity"].lower() in ['critical', 'high']:
                    cves.append(cve_data)

                i = j
            else:
                i += 1

        return cves[:10]  # Limit to top 10

    def _extract_remediation(self, response: str) -> str:
        """Extract remediation recommendations from agent response.

        Args:
            response: Agent response text

        Returns:
            Remediation recommendations text or empty string
        """
        # Look for remediation section - actual format: "Recommended remediation steps (prioritized)"
        patterns = [
            r'[Rr]ecommended\s+remediation\s+steps\s*(?:\([^)]+\))?\s*\n(.*?)(?:\n\n[A-Z]|\Z)',
            r'[Rr]emediation\s+[Rr]ecommendations?(?:\s*\([^)]+\))?:?\s*\n(.*?)(?:\n\n[A-Z]|\Z)',
            r'[Rr]ecommended\s+[Rr]emediation\s+[Ss]teps:?\s*\n(.*?)(?:\n\n[A-Z]|\Z)',
            r'[Kk]ey\s+[Rr]emediation\s+[Rr]ecommendations?:?\s*\n(.*?)(?:\n\n[A-Z]|\Z)',
            r'[Qq]uick\s+remediation\s+recommendations\s*(?:\([^)]+\))?\s*\n(.*?)(?:\n\n[A-Z]|\Z)',
        ]

        for pattern in patterns:
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if match:
                remediation = match.group(1).strip()
                # Clean up and return (limit to reasonable size)
                if len(remediation) > 3000:
                    remediation = remediation[:3000] + "..."
                return remediation

        return ""

    def get_cve_details_panel(self) -> Panel:
        """Generate CVE details panel showing vulnerability information.

        Returns:
            Rich Panel with CVE details
        """
        from rich.markdown import Markdown
        from rich.text import Text

        # Collect all CVEs from all services
        all_cves = []
        for service, data in self.tracker.services.items():
            cves = data.get("top_cves", [])
            for cve in cves:
                # Add service name to CVE
                cve_with_service = cve.copy()
                cve_with_service["service"] = service
                all_cves.append(cve_with_service)

        if not all_cves:
            return Panel(
                "[dim]No critical/high CVEs found yet...[/dim]",
                title="📋 CVE Report Details",
                border_style="blue"
            )

        # Create formatted output
        lines = []
        for idx, cve in enumerate(all_cves, 1):
            severity_color = "red" if cve.get("severity", "").lower() == "critical" else "yellow"
            severity_icon = "🔴" if cve.get("severity", "").lower() == "critical" else "🟡"

            lines.append(f"{idx}) {severity_icon} [{severity_color}bold]{cve['cve_id']}[/{severity_color}bold]")

            if cve.get("package"):
                lines.append(f"   [cyan]Package:[/cyan] {cve['package']}")
            if cve.get("version"):
                lines.append(f"   [cyan]Installed version:[/cyan] {cve['version']}")
            if cve.get("severity"):
                lines.append(f"   [cyan]Severity:[/cyan] [{severity_color}]{cve['severity']}[/{severity_color}]")
            if cve.get("fixed_versions"):
                lines.append(f"   [cyan]Fixed in:[/cyan] {cve['fixed_versions']}")
            if cve.get("nvd_link"):
                lines.append(f"   [cyan]NVD:[/cyan] [link={cve['nvd_link']}]{cve['nvd_link']}[/link]")

            lines.append("")  # Empty line between CVEs

        content = "\n".join(lines)
        return Panel(
            content,
            title="📋 CVE Report Details",
            border_style="red" if any(c.get("severity", "").lower() == "critical" for c in all_cves) else "yellow"
        )

    async def run(self) -> int:
        """Execute triage analysis with live output.

        Returns:
            Exit code (0 for success, 1 for error)
        """
        self.show_config()
        console.print(f"[dim]Logging to: {self.log_file}[/dim]\n")

        # Create layout
        layout = self.create_layout()
        layout["status"].update(self.tracker.get_table())
        layout["output"].update(self.get_cve_details_panel())

        try:
            # Run with Live display
            # Reduced refresh rate to minimize screen flicker (was 4)
            with Live(layout, console=console, refresh_per_second=2) as live:
                for service in self.services:
                    # Store full output for logs but don't display it
                    self.full_output.append(f"Starting triage analysis for {service}...")

                    # Initial update
                    layout["status"].update(self.tracker.get_table())
                    layout["output"].update(self.get_cve_details_panel())
                    live.refresh()

                    # Run triage (async) - status updates happen inside run_triage_for_service
                    response = await self.run_triage_for_service(service, layout, live)

                    # Store response for logs
                    self.full_output.append(response)

                    # Update CVE details panel after parsing
                    layout["output"].update(self.get_cve_details_panel())
                    layout["status"].update(self.tracker.get_table())
                    live.refresh()

                # Final update
                live.refresh()

            # Post-processing outside Live context
            console.print()

            # Print results panel
            console.print(self.get_results_panel(0))

            # Save log
            self._save_log(0)

            return 0

        except Exception as e:
            console.print(f"[red]Error executing triage:[/red] {e}", style="bold red")
            import traceback
            traceback.print_exc()
            return 1

    def _save_log(self, return_code: int):
        """Save execution log to file.

        Args:
            return_code: Process return code
        """
        try:
            with open(self.log_file, "w") as f:
                f.write(f"{'='*70}\n")
                f.write("Maven Triage Analysis Log\n")
                f.write(f"{'='*70}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Services: {', '.join(self.services)}\n")
                f.write(f"Severity Filter: {', '.join(self.severity_filter)}\n")
                f.write(f"Create Issue: {self.create_issue}\n")
                f.write(f"Exit Code: {return_code}\n")
                f.write(f"{'='*70}\n\n")

                f.write("=== TRIAGE RESULTS ===\n\n")
                for service, data in self.tracker.services.items():
                    f.write(f"{service}:\n")
                    f.write(f"  Status: {data['status']}\n")
                    f.write(f"  Critical: {data['critical']}\n")
                    f.write(f"  High: {data['high']}\n")
                    f.write(f"  Medium: {data['medium']}\n")
                    f.write(f"  Dependencies: {data['dependencies']}\n")
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
                f.write(f"Total Critical: {summary['critical']}\n")
                f.write(f"Total High: {summary['high']}\n")
                f.write(f"Total Medium: {summary['medium']}\n")

                f.write("\n=== FULL OUTPUT ===\n\n")
                f.write("\n".join(self.full_output))

            console.print(f"\n[dim]✓ Log saved to: {self.log_file}[/dim]")
        except Exception as e:
            console.print(f"[dim]Warning: Could not save log: {e}[/dim]")

    def get_results_panel(self, return_code: int) -> Panel:
        """Generate final results panel with remediation recommendations.

        Args:
            return_code: Process return code

        Returns:
            Rich Panel with remediation recommendations
        """
        summary = self.tracker.get_summary()

        # Build header with summary
        lines = []
        lines.append(f"[bold]Triage Complete[/bold] - {summary['total_services']} service(s) scanned")
        lines.append("")
        lines.append(f"[red]● Critical:[/red] {summary['critical']}  [yellow]● High:[/yellow] {summary['high']}  [blue]● Medium:[/blue] {summary['medium']}")
        lines.append("")

        # Collect remediation from all services
        all_remediation = []
        for service, data in self.tracker.services.items():
            remediation = data.get("remediation", "")
            if remediation:
                all_remediation.append(remediation)

        if all_remediation:
            lines.append("[bold cyan]Remediation Recommendations:[/bold cyan]")
            lines.append("")
            # Use the first service's remediation (they're usually similar)
            lines.append(all_remediation[0])
        else:
            # Fallback if no remediation was parsed
            lines.append("[bold cyan]Recommended Next Steps:[/bold cyan]")
            lines.append("")
            if summary["critical"] > 0:
                lines.append("1. [red]Prioritize immediate patching for all Critical findings[/red]")
                lines.append("   - Review CVE details above for specific packages and fix versions")
                lines.append("   - Plan for compatibility testing and run full test suite")
                lines.append("")
            if summary["high"] > 0:
                lines.append("2. [yellow]Address High-severity vulnerabilities[/yellow]")
                lines.append("   - Upgrade dependencies to recommended fixed versions")
                lines.append("   - Consider using dependencyManagement to override transitive versions")
                lines.append("")
            if summary["medium"] > 0:
                lines.append("3. [blue]Plan updates for Medium-severity issues[/blue]")
                lines.append("   - Schedule upgrades in upcoming sprints")
                lines.append("")

            lines.append("4. Implement CI/CD best practices")
            lines.append("   - Run vulnerability scans in CI pipeline")
            lines.append("   - Create tracking issues for findings (use --create-issue flag)")
            lines.append("   - Re-scan after each batch of upgrades")

        content = "\n".join(lines)

        # Determine panel style based on severity
        border_style = "red" if summary["critical"] > 0 else "yellow" if summary["high"] > 0 else "green"
        title_emoji = "🔴" if summary["critical"] > 0 else "🟡" if summary["high"] > 0 else "✓"

        return Panel(
            content,
            title=f"{title_emoji} Remediation Plan",
            border_style=border_style,
            padding=(1, 2)
        )
