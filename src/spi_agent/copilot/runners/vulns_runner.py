"""Vulnerability analysis runner for Maven dependency and CVE scanning."""

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
from spi_agent.copilot.trackers import VulnsTracker

if TYPE_CHECKING:
    from spi_agent import SPIAgent


class VulnsRunner(BaseRunner):
    """Runs vulnerability analysis using Maven MCP server with live output"""

    def __init__(
        self,
        prompt_file: Union[Path, Traversable],
        services: List[str],
        agent: "SPIAgent",
        create_issue: bool = False,
        severity_filter: Optional[List[str]] = None,
        providers: Optional[List[str]] = None,
        include_testing: bool = False,
    ):
        """Initialize vulnerability analysis runner.

        Args:
            prompt_file: Path to vulnerability analysis prompt template
            services: List of service names to analyze
            agent: SPIAgent instance with MCP tools
            create_issue: Whether to create tracking issues for findings
            severity_filter: List of severity levels to include (None = all)
            providers: Provider modules to include (default: ["azure"])
            include_testing: Whether to include testing modules (default: False)
        """
        super().__init__(prompt_file, services)
        self.agent = agent
        self.create_issue = create_issue
        self.severity_filter = severity_filter  # None = all severities
        self.providers = providers or ["azure"]  # Default to azure
        self.include_testing = include_testing
        self.tracker = VulnsTracker(services)

    @property
    def log_prefix(self) -> str:
        """Return log file prefix for this runner type."""
        return "vulns"

    def _get_filter_instructions(self) -> str:
        """Generate filtering instructions based on provider/testing flags.

        Returns:
            Instructions for which modules to analyze
        """
        # Core module is always included
        modules_to_analyze = ["core"]

        # Add requested providers
        modules_to_analyze.extend(self.providers)

        # Add testing if requested
        if self.include_testing:
            modules_to_analyze.append("testing")

        instructions = f"""From the scan results module_summary, ONLY analyze these modules:
{', '.join(modules_to_analyze)}

Use module_summary field to extract counts for each module.
Filter by matching module names (e.g., "provider/partition-azure" matches "azure").

In MODULE_BREAKDOWN section, include ONLY the modules listed above.
Do NOT include other providers or testing modules unless specified.
"""
        return instructions

    def load_prompt(self) -> str:
        """Load and augment prompt with arguments"""
        prompt = self.prompt_file.read_text(encoding="utf-8")

        # Replace organization placeholder
        prompt = prompt.replace("{{ORGANIZATION}}", config.organization)

        # Inject arguments
        services_arg = ",".join(self.services)
        severity_arg = ",".join(self.severity_filter) if self.severity_filter else "all"
        augmented = f"{prompt}\n\nARGUMENTS:\nSERVICES: {services_arg}\nSEVERITY_FILTER: {severity_arg}\nCREATE_ISSUE: {self.create_issue}"

        return augmented

    def show_config(self):
        """Display run configuration"""
        severity_str = ', '.join(self.severity_filter).upper() if self.severity_filter else 'ALL'
        providers_str = ', '.join(self.providers)
        testing_str = 'included' if self.include_testing else 'excluded'

        config_text = f"""[cyan]Services:[/cyan]     {', '.join(self.services)}
[cyan]Severity:[/cyan]     {severity_str}
[cyan]Providers:[/cyan]    {providers_str} (core always included)
[cyan]Testing:[/cyan]      {testing_str}
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
        if "analyzing" in line_lower or "vulns" in line_lower or "dependencies" in line_lower:
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


    async def run_vulns_for_service(self, service: str, layout, live) -> str:
        """Run vulnerability scan for a single service with live progress updates.

        Args:
            service: Service name to analyze
            layout: Rich layout object for display updates
            live: Rich Live context for refreshing

        Returns:
            Agent response text
        """
        import time

        # Update tracker
        self.tracker.update(service, "analyzing", "Starting vulnerability scan")

        # Load scan prompt template
        try:
            from importlib.resources import files
            scan_prompt_file = files("spi_agent.copilot.prompts").joinpath("scan.md")
            scan_template = scan_prompt_file.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error loading scan prompt template: {e}"

        # Replace template placeholders
        prompt = scan_template.replace("{{SERVICE}}", service)
        prompt = scan_template.replace("{{WORKSPACE}}", f"./repos/{service}")

        # Add filtering instructions based on provider/testing flags
        filter_instructions = self._get_filter_instructions()
        prompt = prompt.replace("{{WORKSPACE}}", f"./repos/{service}")
        prompt += f"\n\n**FILTERING INSTRUCTIONS:**\n{filter_instructions}"

        # Add issue creation if requested
        if self.create_issue:
            prompt += "\n\nAfter completing the analysis, create a GitHub tracking issue with the findings."

        try:
            # Update status to scanning
            self.tracker.update(service, "scanning", "Running vulnerability scan...")

            # Add scan initiation to output panel
            modules_to_analyze = ["core"] + self.providers
            if self.include_testing:
                modules_to_analyze.append("testing")

            self.output_lines.append(f"Starting vulnerability scan for {service}...")
            self.output_lines.append(f"✓ Scan Java project")
            self.output_lines.append(f"   $ scan_java_project_tool")
            self.output_lines.append(f"     workspace: ./repos/{service}")
            self.output_lines.append(f"     scan_all_modules: true (get complete data)")
            self.output_lines.append(f"     max_results: 100")
            self.output_lines.append(f"   ↪ Analyzing modules: {', '.join(modules_to_analyze)}")
            self.output_lines.append(f"   ↪ Scanning with Trivy (~30-60s)...")

            # Initial update - let Live auto-refresh from here
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

                # Update status message every 2 seconds (but let Live handle refreshing)
                if time.time() - last_update >= 2:
                    status_messages = [
                        f"Scanning dependencies... ({elapsed}s)",
                        f"Analyzing vulnerabilities... ({elapsed}s)",
                        f"Checking CVE database... ({elapsed}s)",
                        f"Processing results... ({elapsed}s)",
                    ]
                    msg = status_messages[(elapsed // 2) % len(status_messages)]

                    # Update tracker (Live will auto-refresh at refresh_per_second rate)
                    old_status = dict(self.tracker.services)
                    self.tracker.update(service, "scanning", msg)

                    # Only update if status changed or every 10 iterations
                    update_count += 1
                    if old_status != self.tracker.services or update_count >= 10:
                        layout["status"].update(self.tracker.get_table())
                        update_count = 0

                    last_update = time.time()

            # Get the response
            response = await agent_task

            # Update status to processing results
            self.tracker.update(service, "reporting", "Processing scan results...")

            # Parse response for vulnerability counts and CVE details
            response_str = str(response)
            self.parse_agent_response(service, response_str)

            # Failsafe: Ensure status is marked complete if still scanning/reporting
            svc_data = self.tracker.services[service]
            if svc_data['status'] in ['scanning', 'reporting', 'analyzing']:
                # Force completion with whatever counts we have (even if 0)
                self.tracker.update(
                    service,
                    "complete",
                    f"{svc_data['critical'] + svc_data['high'] + svc_data['medium']} vulnerabilities found"
                )
                svc_data = self.tracker.services[service]  # Refresh data

            # Add simple completion message
            total_vulns = svc_data['critical'] + svc_data['high'] + svc_data['medium']
            self.output_lines.append(f"✓ Analysis complete for {service}")

            # Also store in full_output for logs
            self.full_output.append(f"=== {service.upper()} SCAN RESULTS ===")
            self.full_output.append(response_str)
            self.full_output.append("")

            # Final update for this service (let Live handle the refresh)
            layout["output"].update(self._output_panel_renderable)
            layout["status"].update(self.tracker.get_table())

            return response_str

        except Exception as e:
            self.tracker.update(service, "error", f"Failed: {str(e)[:50]}")
            layout["status"].update(self.tracker.get_table())
            return f"Error analyzing {service}: {str(e)}"

    def parse_agent_response(self, service: str, response: str):
        """Parse agent response to extract vulnerability metrics and module breakdown.

        Args:
            service: Service name
            response: Agent response text
        """
        response_lower = response.lower()

        # Initialize counts
        critical = 0
        high = 0
        medium = 0

        # Parse structured output if present
        # Format: "Total: Critical=4, High=71, Medium=67, Low=19"
        summary_pattern = r'total:\s*critical=(\d+),\s*high=(\d+),\s*medium=(\d+)'
        summary_match = re.search(summary_pattern, response_lower)
        if summary_match:
            critical = int(summary_match.group(1))
            high = int(summary_match.group(2))
            medium = int(summary_match.group(3))
        else:
            # Fallback: "Critical: 4, High: 71, Medium: 67" format
            severity_counts_pattern = r'critical:\s*(\d+)[\s,]+high:\s*(\d+)[\s,]+medium:\s*(\d+)'
            match = re.search(severity_counts_pattern, response_lower)
            if match:
                critical = int(match.group(1))
                high = int(match.group(2))
                medium = int(match.group(3))
            else:
                # Last resort: Individual searches
                critical_match = re.search(r'critical[:\s]+(\d+)', response_lower)
                if critical_match:
                    critical = int(critical_match.group(1))

                high_match = re.search(r'high[:\s]+(\d+)', response_lower)
                if high_match:
                    high = int(high_match.group(1))

                medium_match = re.search(r'medium[:\s]+(\d+)', response_lower)
                if medium_match:
                    medium = int(medium_match.group(1))

        # Extract module breakdown if present in structured format
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
                            'critical': int(parts[1]) if parts[1].isdigit() else 0,
                            'high': int(parts[2]) if parts[2].isdigit() else 0,
                            'medium': int(parts[3]) if parts[3].isdigit() else 0,
                        }

        # Store module breakdown for use in Security Assessment panel
        if module_data:
            self.tracker.services[service]["modules"] = module_data

            # Recalculate totals from FILTERED modules only
            filtered_critical = sum(m.get('critical', 0) for m in module_data.values())
            filtered_high = sum(m.get('high', 0) for m in module_data.values())
            filtered_medium = sum(m.get('medium', 0) for m in module_data.values())

            # Override the totals with filtered totals
            critical = filtered_critical
            high = filtered_high
            medium = filtered_medium

        # Only check for failures if we found NO vulnerability counts at all
        # This prevents false positives where scans succeed but agent mentions errors in explanation
        if critical == 0 and high == 0 and medium == 0:
            # Common failure indicators from Maven MCP scan failures
            failure_indicators = [
                'scan failed',
                'failed to complete',
                'fatal error.*run error',  # More specific - "fatal error: run error"
                'scan.*aborted',  # More specific
                'scan.*timeout',  # More specific - "scan timeout" not just any timeout
                'could not.*scan',  # More specific
                'no vulnerability results were produced',
                'no vulnerabilities available',
                'scan did not complete',
                'database.*lock.*error',  # More specific - "database lock error"
            ]

            # Check for failure patterns
            is_failure = False
            failure_reason = "Scan failed"

            for indicator in failure_indicators:
                if re.search(indicator, response_lower):
                    is_failure = True
                    # Try to extract a concise failure reason
                    if 'database' in response_lower and 'lock' in response_lower:
                        failure_reason = "Database lock error"
                    elif 'scan' in response_lower and 'timeout' in response_lower:
                        failure_reason = "Scan timeout"
                    elif 'fatal error' in response_lower:
                        failure_reason = "Fatal error during scan"
                    elif 'no vulnerability results' in response_lower:
                        failure_reason = "Scan produced no results"
                    break

            # If scan failed, mark as error and return early
            if is_failure:
                self.tracker.update(
                    service,
                    "error",
                    failure_reason,
                    critical=0,
                    high=0,
                    medium=0,
                    dependencies=0,
                    report_id="",
                    top_cves=[],
                    remediation="",
                )
                return

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
            # Format 1: 1) CVE-2025-24813 (critical)  <- Severity in parentheses
            # Format 2: 1) CVE-2025-24813 — critical  <- Severity after em-dash
            # Format 3: - 1) CVE-2025-24813           <- With leading dash (legal format)
            # Format 4: 1) CVE-2025-24813             <- CVE alone

            cve_match = re.match(r'^-?\s*\d+\)\s+(CVE-\d{4}-\d+)(?:\s+[—-]\s+|\s+\()?([^)\n]+)?', line, re.IGNORECASE)

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
                        # Format 1: "org.springframework:spring-beans @ 5.2.7.RELEASE"
                        # Format 2: "org.springframework:spring-beans"
                        package_name = re.split(r'\s*—\s+installed|\s+—\s+installed|\(installed|@', value, maxsplit=1)[0].strip()
                        if package_name:
                            cve_data["package"] = package_name

                        # Extract inline version if present (Format: package @ version)
                        if '@' in value and not cve_data["version"]:
                            version_part = value.split('@', 1)[1].strip()
                            # Remove any trailing context
                            version_part = re.split(r'\s*\(|\s*—', version_part, maxsplit=1)[0].strip()
                            if version_part:
                                cve_data["version"] = version_part

                    # Version - look for "installed" and "version" keywords together
                    elif ('installed' in field_lower and 'version' in field_lower) and not cve_data["version"]:
                        # Extract just the version, ignore paths/locations in parentheses
                        if '(' in value:
                            cve_data["version"] = value.split('(')[0].strip()
                        else:
                            cve_data["version"] = value

                    # Fix/Recommended versions - look for "fix", "recommend", "upgrade" keywords (substring match)
                    # Matches: "Recommended fixed versions (scanner):", "Recommendation/fix:", "Recommended fixed version:"
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

    def _calculate_service_grade(self, critical: int, high: int, medium: int) -> str:
        """Calculate security grade for a service based on vulnerability counts.

        Args:
            critical: Number of critical vulnerabilities
            high: Number of high vulnerabilities
            medium: Number of medium vulnerabilities

        Returns:
            Letter grade (A, B, C, D, F)
        """
        # Security-first grading criteria
        # Grade A: 0 Critical, 0 High (Excellent - only medium/low issues)
        if critical == 0 and high == 0:
            return "A"

        # Grade B: 0 Critical, 1-5 High (Good - minor high-severity issues)
        elif critical == 0 and high <= 5:
            return "B"

        # Grade C: 0 Critical, 6-20 High OR 1-2 Critical (Needs Attention)
        elif (critical == 0 and high <= 20) or (critical <= 2 and high <= 50):
            return "C"

        # Grade D: 0 Critical, 21+ High OR 3-10 Critical (Poor - significant issues)
        elif (critical == 0 and high <= 100) or (critical <= 10):
            return "D"

        # Grade F: 11+ Critical OR (Any Critical + 50+ High) (Critical - emergency)
        else:
            return "F"

    def _calculate_overall_grade(self) -> str:
        """Calculate overall security grade across all services.

        Returns:
            Letter grade (A, B, C, D, F)
        """
        summary = self.tracker.get_summary()
        critical = summary["critical"]
        high = summary["high"]

        # Overall grade (more lenient, recognizing multiple services compound issues)
        # Both conditions must be met for each grade (AND not OR)
        if critical == 0 and high <= 15:
            return "A"
        elif critical <= 8 and high <= 75:
            return "B"
        elif critical <= 25 and high <= 200:
            return "C"
        elif critical <= 70 and high <= 400:
            return "D"
        else:
            return "F"

    def _get_risk_level(self, grade: str) -> tuple[str, str]:
        """Get risk level and color based on grade.

        Args:
            grade: Letter grade

        Returns:
            Tuple of (risk_level, color)
        """
        risk_mapping = {
            "A": ("CLEAN", "green"),
            "B": ("LOW", "blue"),
            "C": ("MODERATE", "yellow"),
            "D": ("HIGH", "red"),
            "F": ("CRITICAL", "red bold"),
        }
        return risk_mapping.get(grade, ("UNKNOWN", "white"))

    def _get_recommendation(self, critical: int, high: int, grade: str) -> str:
        """Get security recommendation based on vulnerability counts and grade.

        Args:
            critical: Number of critical vulnerabilities
            high: Number of high vulnerabilities
            grade: Letter grade

        Returns:
            Recommendation text
        """
        if grade == "A":
            return "Clean - no critical or high-severity vulnerabilities"
        elif grade == "B":
            return f"Address {high} high-severity issue{'s' if high > 1 else ''} in next sprint"
        elif grade == "C":
            if critical > 0:
                return f"PRIORITY: Patch {critical} critical CVE{'s' if critical > 1 else ''} immediately, then {high} high-severity issues"
            return f"Address {high} high-severity vulnerabilities within 2 weeks"
        elif grade == "D":
            if critical > 0:
                return f"URGENT: {critical} critical CVE{'s' if critical > 1 else ''} + {high} high-severity issues require immediate remediation plan"
            return f"URGENT: {high} high-severity vulnerabilities require immediate action"
        else:  # F
            return f"CRITICAL EMERGENCY: {critical} critical + {high} high-severity vulnerabilities - stop deployment until patched"

    def get_security_assessment_panel(self) -> Panel:
        """Generate security assessment panel with module-level breakdown.

        Returns:
            Rich Panel with security grade table showing module details
        """
        from rich.text import Text

        # Create table
        table = Table(show_header=True, header_style="bold", box=None)
        table.add_column("Module", style="cyan", width=20)
        table.add_column("Result", style="white", width=20)
        table.add_column("Grade", justify="center", width=7)
        table.add_column("Recommendation", style="white")

        # Track overall totals
        total_critical = 0
        total_high = 0
        total_medium = 0

        # Add rows for each service
        for service, data in self.tracker.services.items():
            status = data.get("status", "unknown")

            # Check if scan failed (error status)
            if status == "error":
                error_details = data.get("details", "Scan failed")
                table.add_row(
                    service,
                    Text(f"Error: {error_details}", style="red"),
                    Text("—", style="dim"),
                    "Resolve scan error and re-run"
                )
                continue

            # Get service-level counts
            critical = data.get("critical", 0)
            high = data.get("high", 0)
            medium = data.get("medium", 0)

            total_critical += critical
            total_high += high
            total_medium += medium

            # Check if we have module breakdown
            modules = data.get("modules", {})

            if modules:
                # Show overall service row first
                total = critical + high + medium
                svc_grade = self._calculate_service_grade(critical, high, medium)
                grade_style = {"A": "green bold", "B": "blue bold", "C": "yellow bold",
                              "D": "red bold", "F": "red bold"}.get(svc_grade, "white")

                result_parts = []
                if critical > 0:
                    result_parts.append(f"{critical}C")
                if high > 0:
                    result_parts.append(f"{high}H")
                if medium > 0:
                    result_parts.append(f"{medium}M")

                result_text = Text(', '.join(result_parts) if result_parts else "0 vulns",
                                 style="red" if critical > 0 else "yellow" if high > 0 else "green")

                table.add_row(
                    f"[bold]{service} (total)[/bold]",
                    result_text,
                    Text(svc_grade, style=grade_style),
                    self._get_recommendation(critical, high, svc_grade)
                )

                # Add module breakdown rows
                for module_name in ["core", "core-plus", "aws", "azure", "gc", "ibm", "testing"]:
                    if module_name in modules:
                        mod = modules[module_name]
                        mod_c = mod.get("critical", 0)
                        mod_h = mod.get("high", 0)
                        mod_m = mod.get("medium", 0)
                        mod_total = mod_c + mod_h + mod_m

                        if mod_total > 0:  # Only show modules with vulnerabilities
                            mod_grade = self._calculate_service_grade(mod_c, mod_h, mod_m)
                            mod_grade_style = {"A": "green", "B": "blue", "C": "yellow",
                                             "D": "red", "F": "red"}.get(mod_grade, "white")

                            mod_parts = []
                            if mod_c > 0:
                                mod_parts.append(f"{mod_c}C")
                            if mod_h > 0:
                                mod_parts.append(f"{mod_h}H")
                            if mod_m > 0:
                                mod_parts.append(f"{mod_m}M")

                            mod_result = Text(', '.join(mod_parts),
                                            style="red" if mod_c > 0 else "yellow" if mod_h > 0 else "dim")

                            # Short recommendation for modules
                            if mod_c > 0:
                                mod_rec = f"Fix {mod_c} critical issue{'s' if mod_c > 1 else ''}"
                            elif mod_h > 10:
                                mod_rec = f"Address {mod_h} high-severity issues"
                            elif mod_h > 0:
                                mod_rec = "Review high-severity findings"
                            else:
                                mod_rec = "Minor updates recommended"

                            table.add_row(
                                f"  ↳ {module_name}",
                                mod_result,
                                Text(mod_grade, style=mod_grade_style),
                                mod_rec
                            )
            else:
                # No module breakdown - show service row only
                total = critical + high + medium
                svc_grade = self._calculate_service_grade(critical, high, medium)
                grade_style = {"A": "green bold", "B": "blue bold", "C": "yellow bold",
                              "D": "red bold", "F": "red bold"}.get(svc_grade, "white")

                result_parts = []
                if critical > 0:
                    result_parts.append(f"{critical}C")
                if high > 0:
                    result_parts.append(f"{high}H")
                if medium > 0:
                    result_parts.append(f"{medium}M")

                result_text = Text(', '.join(result_parts) if result_parts else "0 vulns",
                                 style="red" if critical > 0 else "yellow" if high > 0 else "green")

                table.add_row(
                    service,
                    result_text,
                    Text(svc_grade, style=grade_style),
                    self._get_recommendation(critical, high, svc_grade)
                )

        # Simple subtitle with just totals (no confusing overall grade)
        total_services = len(self.tracker.services)
        subtitle = f"{total_services} service{'s' if total_services > 1 else ''} scanned | "
        subtitle += f"{total_critical}C / {total_high}H / {total_medium}M vulnerabilities"

        # Border color based on worst finding
        if total_critical > 0:
            border_color = "red"
        elif total_high >= 20:
            border_color = "yellow"
        elif total_high > 0:
            border_color = "blue"
        else:
            border_color = "green"

        return Panel(
            table,
            title="Security Assessment",
            subtitle=subtitle,
            border_style=border_color,
            padding=(1, 2)
        )

    async def _analyze_cves_with_agent(self) -> str:
        """Use agent to analyze and consolidate CVE findings across services.

        Returns:
            Agent-generated CVE analysis report
        """
        # Build log content from in-memory data (same format as saved log)
        summary = self.tracker.get_summary()

        log_parts = []
        log_parts.append("="*70)
        log_parts.append("Maven Triage Analysis Log")
        log_parts.append("="*70)
        log_parts.append(f"Timestamp: {datetime.now().isoformat()}")
        log_parts.append(f"Services: {', '.join(self.services)}")
        severity_str = ', '.join(self.severity_filter) if self.severity_filter else 'all'
        log_parts.append(f"Severity Filter: {severity_str}")
        log_parts.append(f"="*70)
        log_parts.append("")
        log_parts.append("=== TRIAGE RESULTS ===")
        log_parts.append("")

        for service, data in self.tracker.services.items():
            log_parts.append(f"{service}:")
            log_parts.append(f"  Status: {data['status']}")
            log_parts.append(f"  Critical: {data['critical']}")
            log_parts.append(f"  High: {data['high']}")
            log_parts.append(f"  Medium: {data['medium']}")
            log_parts.append("")

        log_parts.append("=== SUMMARY ===")
        log_parts.append("")
        log_parts.append(f"Total Services: {summary['total_services']}")
        log_parts.append(f"Total Critical: {summary['critical']}")
        log_parts.append(f"Total High: {summary['high']}")
        log_parts.append(f"Total Medium: {summary['medium']}")
        log_parts.append("")
        log_parts.append("=== FULL OUTPUT ===")
        log_parts.append("")
        log_parts.extend(self.full_output)

        log_content = "\n".join(log_parts)

        # Load CVE analysis prompt template
        try:
            from importlib.resources import files
            prompt_file = files("spi_agent.copilot.prompts").joinpath("cve_analysis.md")
            prompt_template = prompt_file.read_text(encoding="utf-8")

            # Replace placeholder with actual scan results
            prompt = prompt_template.replace("{{SCAN_RESULTS}}", log_content)
        except Exception as e:
            return f"Error loading CVE analysis prompt: {e}"

        try:
            # Call agent to analyze
            response = await self.agent.agent.run(
                prompt,
                thread=self.agent.agent.get_new_thread()
            )
            return str(response)
        except Exception as e:
            return f"Error analyzing CVEs: {e}"

    def get_cve_details_panel(self, cve_analysis: str = None) -> Panel:
        """Generate CVE details panel with agent-analyzed consolidated report.

        Args:
            cve_analysis: Agent-generated CVE analysis (if available)

        Returns:
            Rich Panel with CVE details (blue border, Next Steps style)
        """
        if not cve_analysis:
            return Panel(
                "[dim]CVE analysis not available yet...[/dim]",
                title="Vulnerability Analysis",
                border_style="blue"
            )

        # Display agent analysis directly (it's already well-formatted)
        return Panel(
            cve_analysis,
            title="Vulnerability Analysis",
            border_style="blue",
            padding=(1, 2)
        )

    async def run(self) -> int:
        """Execute triage analysis with live output.

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
                # Run services in parallel (max 2 at a time to avoid overwhelming display)
                from asyncio import Semaphore, gather

                # Limit concurrent scans to 2 (balance speed vs display clarity)
                semaphore = Semaphore(2)

                async def run_with_limit(service, svc_idx):
                    async with semaphore:
                        self.full_output.append(f"Starting vulnerability scan for {service}...")

                        # Update display (let Live auto-refresh)
                        layout["output"].update(self._output_panel_renderable)
                        layout["status"].update(self.tracker.get_table())

                        # Run vulnerability scan for this service
                        response = await self.run_vulns_for_service(service, layout, live)

                        # Store response for logs
                        self.full_output.append(response)

                        return response

                # Launch all services in parallel (controlled by semaphore)
                tasks = [run_with_limit(service, idx) for idx, service in enumerate(self.services, 1)]
                responses = await gather(*tasks)

                # Add scan completion message to output panel
                self.output_lines.append("✓ Scans complete for all services")
                layout["output"].update(self._output_panel_renderable)
                layout["status"].update(self.tracker.get_table())

                # Add CVE analysis message to output panel
                self.output_lines.append(f"   ↪ Analyzing CVE findings...")
                layout["output"].update(self._output_panel_renderable)

                # Analyze CVEs with agent (while still in Live context so output shows progress)
                cve_analysis = await self._analyze_cves_with_agent()

                # Add completion message to output panel
                self.output_lines.append("✓ CVE analysis complete")
                layout["output"].update(self._output_panel_renderable)
                layout["status"].update(self.tracker.get_table())

                # Final update BEFORE exiting Live context (like test runner)
                live.refresh()

            # Post-processing outside Live context
            # Display both panels together
            console.print()
            console.print(self.get_security_assessment_panel())
            console.print(self.get_cve_details_panel(cve_analysis))

            # Save log
            self._save_log(0)

            return 0

        except Exception as e:
            console.print(f"[red]Error executing vulnerability scan:[/red] {e}", style="bold red")
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
                severity_str = ', '.join(self.severity_filter) if self.severity_filter else 'all'
                f.write(f"Severity Filter: {severity_str}\n")
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
        except Exception as e:
            console.print(f"[dim]Warning: Could not save log: {e}[/dim]")

    def get_results_panel(self, return_code: int) -> Panel:
        """Generate final results panel (required by base class).

        Note: VulnsRunner uses async run() which calls get_security_assessment_panel()
        directly, so this method is not actually used in normal execution.

        Args:
            return_code: Process return code

        Returns:
            Rich Panel with security assessment
        """
        return self.get_security_assessment_panel()
