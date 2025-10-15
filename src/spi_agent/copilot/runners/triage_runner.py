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
        maven_profiles: Optional[List[str]] = None,
    ):
        """Initialize triage runner.

        Args:
            prompt_file: Path to triage prompt template
            services: List of service names to analyze
            agent: SPIAgent instance with MCP tools
            create_issue: Whether to create tracking issues for findings
            severity_filter: List of severity levels to include (critical, high, medium)
            maven_profiles: Maven profiles to activate during scan (default: azure)
        """
        super().__init__(prompt_file, services)
        self.agent = agent
        self.create_issue = create_issue
        self.severity_filter = severity_filter or ["critical", "high", "medium"]
        self.maven_profiles = maven_profiles or ["azure"]
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
[cyan]Maven Profile:[/cyan] {', '.join(self.maven_profiles)}
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

        # Construct very direct prompt to execute the scan tool immediately
        # Note: include_profiles and severity_filter will be supported in future MCP server versions
        # For now, we scan everything and filter results by severity afterward
        severity_str = ', '.join([s.upper() for s in self.severity_filter])
        profiles_str = ', '.join(self.maven_profiles)

        prompt = f"""Execute a complete Maven dependency and vulnerability triage for the {service} service.

**ACTION REQUIRED - DO NOT ASK FOR CONFIRMATION:**

Call scan_java_project_tool with these exact parameters:
- workspace: ./repos/{service}
- max_results: 100

After the scan completes, filter the results to show ONLY vulnerabilities with severity: {severity_str}.

Provide a concise summary with:
- Total vulnerabilities found (count by severity: Critical, High, Medium) - ONLY for {severity_str} severities
- Top 5 critical/high findings with CVE IDs, CVSS scores, affected packages
- Recommended remediation steps

**NOTE**: This scan will use the default Maven configuration. In a future version, it will activate Maven profiles: {profiles_str}

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

            # Add scan initiation to output panel (status command style)
            self.output_lines.append(f"Starting triage analysis for {service}...")
            self.output_lines.append(f"✓ Scan Java project")
            self.output_lines.append(f"   $ scan_java_project_tool workspace: ./repos/{service}")
            self.output_lines.append(f"   ↪ Running Trivy security scan...")

            layout["status"].update(self.tracker.get_table())
            layout["output"].update(self.get_output_panel())
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

                    # Update tracker (status table shows progress with elapsed time)
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

            # Update display with agent response
            layout["output"].update(self.get_output_panel())
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

        # Try to extract vulnerability counts from response FIRST
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
        # Grade criteria (more lenient for real-world dependency management)
        # Both conditions must be met for each grade (AND not OR)
        if critical == 0 and high <= 10:
            return "A"
        elif critical <= 3 and high <= 40:
            return "B"
        elif critical <= 15 and high <= 100:
            return "C"
        elif critical <= 40 and high <= 200:
            return "D"
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
            return "Excellent security posture - maintain current standards"
        elif grade == "B":
            if high > 0:
                return f"Address {high} high-severity vulnerabilities in next sprint"
            return "Good security posture - schedule routine updates"
        elif grade == "C":
            if critical > 0:
                return f"PRIORITY: Patch {critical} critical CVE(s) immediately, then address high-severity issues"
            return f"Address {high} high-severity vulnerabilities within 2 weeks"
        elif grade == "D":
            if critical > 0:
                return f"URGENT: Patch {critical} critical CVE(s) this week and create remediation plan for {high} high-severity issues"
            return f"Create immediate remediation plan for {high} high-severity vulnerabilities"
        else:  # F
            return f"CRITICAL: Immediate action required - {critical} critical and {high} high-severity vulnerabilities pose significant risk"

    def get_security_assessment_panel(self) -> Panel:
        """Generate security assessment panel with table format like test results.

        Returns:
            Rich Panel with security grade table
        """
        from rich.text import Text

        # Create table
        table = Table(show_header=True, header_style="bold", box=None)
        table.add_column("Service", style="cyan", width=12)
        table.add_column("Result", style="white", width=40)
        table.add_column("Grade", justify="center", width=7)
        table.add_column("Recommendation", style="white")

        # Add rows for each service
        for service, data in self.tracker.services.items():
            status = data.get("status", "unknown")

            # Check if scan failed (error status)
            if status == "error":
                # Display error status instead of grades
                error_details = data.get("details", "Scan failed")
                result_text = Text(f"Error: {error_details}", style="red")
                grade_text = Text("—", style="dim")  # Use em-dash for no grade
                recommendation = "Resolve scan error and re-run (check logs for details)"

                table.add_row(
                    service,
                    result_text,
                    grade_text,
                    recommendation
                )
                continue

            # Normal processing for successful scans
            critical = data.get("critical", 0)
            high = data.get("high", 0)
            medium = data.get("medium", 0)
            total = critical + high + medium

            # Calculate grade
            svc_grade = self._calculate_service_grade(critical, high, medium)

            # Grade styling
            grade_style = {
                "A": "green bold",
                "B": "blue bold",
                "C": "yellow bold",
                "D": "red bold",
                "F": "red bold"
            }.get(svc_grade, "white")

            # Result text with breakdown (concise format: just counts)
            if total == 0:
                result_text = Text("0C, 0H, 0M", style="green")
            else:
                result_parts = []
                if critical > 0:
                    result_parts.append(f"{critical}C")
                if high > 0:
                    result_parts.append(f"{high}H")
                if medium > 0:
                    result_parts.append(f"{medium}M")

                result_str = ', '.join(result_parts)
                if critical > 0:
                    result_text = Text(result_str, style="red")
                elif high > 0:
                    result_text = Text(result_str, style="yellow")
                else:
                    result_text = Text(result_str, style="blue")

            # Get recommendation
            recommendation = self._get_recommendation(critical, high, svc_grade)

            # Add row
            table.add_row(
                service,
                result_text,
                Text(svc_grade, style=grade_style),
                recommendation
            )

        # Calculate overall assessment
        summary = self.tracker.get_summary()
        overall_grade = self._calculate_overall_grade()
        risk_level, risk_color = self._get_risk_level(overall_grade)

        # Create subtitle with overall stats
        total_services = len(self.tracker.services)
        subtitle = f"Overall Grade: [{risk_color}]{overall_grade}[/{risk_color}] | "
        subtitle += f"Risk Level: [{risk_color}]{risk_level}[/{risk_color}] | "
        subtitle += f"{total_services} service{'s' if total_services > 1 else ''} scanned | "
        subtitle += f"{summary['critical']}C / {summary['high']}H / {summary['medium']}M vulnerabilities"

        # Determine border color based on overall grade
        border_color = {
            "A": "green",
            "B": "blue",
            "C": "yellow",
            "D": "red",
            "F": "red"
        }.get(overall_grade, "blue")

        return Panel(
            table,
            title="🛡️ Security Assessment",
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
        log_parts.append(f"Severity Filter: {', '.join(self.severity_filter)}")
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
                title="🔍 Priority CVE Report",
                border_style="blue"
            )

        # Display agent analysis directly (it's already well-formatted)
        return Panel(
            cve_analysis,
            title="🔍 Priority CVE Report",
            subtitle="Cross-service vulnerabilities listed first",
            border_style="blue",
            padding=(1, 2)
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
        layout["output"].update(self.get_output_panel())

        try:
            # Run with Live display
            # Reduced refresh rate to minimize screen flicker (was 4)
            with Live(layout, console=console, refresh_per_second=2) as live:
                # Run services in parallel (max 2 at a time to avoid overwhelming display)
                from asyncio import Semaphore, gather

                # Limit concurrent scans to 2 (balance speed vs display clarity)
                semaphore = Semaphore(2)

                async def run_with_limit(service, svc_idx):
                    async with semaphore:
                        self.full_output.append(f"Starting triage analysis for {service}...")

                        # Update display
                        layout["output"].update(self.get_output_panel())
                        layout["status"].update(self.tracker.get_table())
                        live.refresh()

                        # Run triage for this service
                        response = await self.run_triage_for_service(service, layout, live)

                        # Store response for logs
                        self.full_output.append(response)

                        return response

                # Launch all services in parallel (controlled by semaphore)
                tasks = [run_with_limit(service, idx) for idx, service in enumerate(self.services, 1)]
                responses = await gather(*tasks)

                # Add scan completion message to output panel
                self.output_lines.append("")
                self.output_lines.append("✓ Scans complete for all services")
                layout["output"].update(self.get_output_panel())
                layout["status"].update(self.tracker.get_table())
                live.refresh()

                # Add CVE analysis message to output panel
                self.output_lines.append(f"   ↪ Analyzing CVE findings...")
                layout["output"].update(self.get_output_panel())
                live.refresh()

                # Analyze CVEs with agent (while still in Live context so output shows progress)
                cve_analysis = await self._analyze_cves_with_agent()

                # Add completion message to output panel
                self.output_lines.append("✓ CVE analysis complete")
                layout["output"].update(self.get_output_panel())
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
        """Generate final results panel (required by base class).

        Note: TriageRunner uses async run() which calls get_security_assessment_panel()
        directly, so this method is not actually used in normal execution.

        Args:
            return_code: Process return code

        Returns:
            Rich Panel with security assessment
        """
        return self.get_security_assessment_panel()
