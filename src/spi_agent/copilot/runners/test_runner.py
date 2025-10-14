"""Test runner for executing Maven tests with coverage analysis."""

import re
import subprocess
from collections import deque
from datetime import datetime
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import List, Optional, Union

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from spi_agent.copilot.config import config, log_dir
from spi_agent.copilot.trackers import TestTracker

console = Console()

# Global process reference for signal handling (will be set by parent module)
current_process: Optional[subprocess.Popen] = None


class TestRunner:
    """Runs Copilot CLI to execute Maven tests with live output"""

    def __init__(
        self,
        prompt_file: Union[Path, Traversable],
        services: List[str],
        provider: str = "azure",
    ):
        self.prompt_file = prompt_file
        self.services = services
        self.provider = provider
        self.output_lines = deque(maxlen=50)
        self.full_output = []
        self.tracker = TestTracker(services, provider)

        # Generate log file path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        services_str = "-".join(services[:3])
        if len(services) > 3:
            services_str += f"-and-{len(services)-3}-more"
        self.log_file = log_dir / f"test_{timestamp}_{services_str}.log"

    def load_prompt(self) -> str:
        """Load and augment prompt with arguments"""
        prompt = self.prompt_file.read_text(encoding="utf-8")

        # Replace organization placeholder
        prompt = prompt.replace("{{ORGANIZATION}}", config.organization)

        # Inject arguments
        services_arg = ",".join(self.services)
        augmented = f"{prompt}\n\nARGUMENTS:\nSERVICES: {services_arg}\nPROVIDER: {self.provider}"

        return augmented

    def show_config(self):
        """Display run configuration"""
        config_text = f"""[cyan]Services:[/cyan]   {', '.join(self.services)}
[cyan]Provider:[/cyan]   {self.provider}"""

        console.print(Panel(config_text, title="🧪 Maven Test Execution", border_style="blue"))
        console.print()

    def get_output_panel(self) -> Panel:
        """Create panel with scrolling output"""
        if not self.output_lines:
            output_text = Text("Waiting for output...", style="dim")
        else:
            output_text = Text()
            for line in self.output_lines:
                if line.startswith("$"):
                    output_text.append(line + "\n", style="cyan")
                elif line.startswith("✓") or "success" in line.lower():
                    output_text.append(line + "\n", style="green")
                elif line.startswith("✗") or "error" in line.lower() or "failed" in line.lower():
                    output_text.append(line + "\n", style="red")
                elif "[INFO]" in line:
                    output_text.append(line + "\n", style="blue")
                elif "[ERROR]" in line:
                    output_text.append(line + "\n", style="red")
                elif "[WARNING]" in line:
                    output_text.append(line + "\n", style="yellow")
                else:
                    output_text.append(line + "\n", style="white")

        return Panel(output_text, title="📋 Agent Output", border_style="blue")

    def parse_maven_output(self, line: str):
        """Parse copilot's task announcements for test status updates"""
        line_lower = line.lower()
        line_stripped = line.strip()

        # Strategy: Only parse copilot's task announcements, not raw Maven output
        # Copilot tells us everything we need through its task markers

        # Find which service this line is about
        target_service = None
        for service in self.services:
            # Match service name in various formats: "partition", "Partition", "**partition**"
            if service in line_lower or f"**{service}**" in line_lower:
                target_service = service
                break

        if not target_service:
            return

        # Parse copilot's status updates (matches the exact format from test.md prompt)
        # Strip leading bullets (● prefix)
        line_for_parsing = line_stripped.lstrip("●").strip()

        # Only parse lines starting with ✓ (task completion markers)
        if line_for_parsing.startswith("✓") and ":" in line_for_parsing:
            # Expected formats from prompt:
            # "✓ partition: Starting compile phase"
            # "✓ partition: Starting test phase"
            # "✓ partition: Starting coverage phase"
            # "✓ partition: Compiled successfully, 61 tests passed, Coverage report generated"

            if "starting compile phase" in line_lower:
                self.tracker.update(target_service, "compiling", "Compiling", phase="compile")

            elif "starting test phase" in line_lower:
                self.tracker.update(target_service, "testing", "Testing", phase="test")

            elif "starting coverage phase" in line_lower:
                self.tracker.update(target_service, "coverage", "Coverage", phase="coverage")

            elif "compiled successfully" in line_lower:
                # Completion summary - extract test count
                test_count_match = re.search(r'(\d+)\s+tests?\s+passed', line_lower)
                tests_run = int(test_count_match.group(1)) if test_count_match else 0

                self.tracker.update(target_service, "test_success", "Complete",
                                  phase="coverage", tests_run=tests_run, tests_failed=0)

        # Detect errors
        if "build failure" in line_lower and target_service:
            self.tracker.update(target_service, "test_failed", "Build failed", phase="test")
        elif "compilation failure" in line_lower and target_service:
            self.tracker.update(target_service, "compile_failed", "Failed", phase="compile")

    def create_layout(self) -> Layout:
        """Create split layout with status and output"""
        layout = Layout()

        # Simple split: status (left) and output (right)
        layout.split_row(
            Layout(name="status", ratio=1),
            Layout(name="output", ratio=2)
        )

        return layout

    def run(self) -> int:
        """Execute copilot to run Maven tests with live output"""
        global current_process

        self.show_config()
        console.print(f"[dim]Logging to: {self.log_file}[/dim]\n")

        prompt_content = self.load_prompt()
        command = ["copilot", "-p", prompt_content, "--allow-all-tools"]

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            current_process = process

            layout = self.create_layout()
            layout["status"].update(self.tracker.get_table())
            layout["output"].update(self.get_output_panel())

            with Live(layout, console=console, refresh_per_second=2) as live:
                if process.stdout:
                    last_update = 0
                    for line in process.stdout:
                        line = line.rstrip()
                        if line:
                            self.output_lines.append(line)
                            self.full_output.append(line)

                            # Parse output and check if status changed
                            old_status = dict(self.tracker.services)
                            self.parse_maven_output(line)

                            # Only update display if status changed or every 10 lines
                            status_changed = old_status != self.tracker.services
                            last_update += 1

                            if status_changed or last_update >= 10:
                                layout["status"].update(self.tracker.get_table())
                                layout["output"].update(self.get_output_panel())
                                last_update = 0

                process.wait()

                # Mark any remaining services as completed based on return code
                if process.returncode == 0:
                    for service in self.services:
                        status = self.tracker.services[service]["status"]
                        # Only update if not already in a completed state
                        if status not in ["compile_failed", "test_failed", "error", "test_success", "compile_success"]:
                            if status == "compiling":
                                self.tracker.update(service, "compile_success", "Compiled")
                            else:
                                # Mark as complete but don't overwrite test data
                                self.tracker.update(service, "test_success", "Complete")

                    # Final update before exiting Live
                    layout["status"].update(self.tracker.get_table())
                    live.refresh()

            # ALL post-processing happens OUTSIDE Live context to prevent panel jumping
            console.print()  # Add spacing

            # Extract coverage from JaCoCo reports (post-processing)
            self._extract_coverage_from_reports()

            # Assess coverage quality
            self._assess_coverage_quality()

            # Update quality results in tracker
            for service in self.services:
                if self.tracker.services[service].get("quality_grade"):
                    grade = self.tracker.services[service]["quality_grade"]
                    label = self.tracker.services[service].get("quality_label", "")
                    self.tracker.services[service]["details"] = f"Grade {grade}: {label}"

            # Print the final summary panel
            console.print(self.get_summary_panel(process.returncode))

            self._save_log(process.returncode)

            return process.returncode

        except FileNotFoundError:
            console.print(
                "[red]Error:[/red] 'copilot' command not found. Is GitHub Copilot CLI installed?",
                style="bold red",
            )
            return 1
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}", style="bold red")
            import traceback
            traceback.print_exc()
            return 1
        finally:
            current_process = None

    def _extract_coverage_from_reports(self):
        """Extract coverage data directly from JaCoCo HTML reports (post-processing)"""
        for service in self.services:
            if self.tracker.services[service]["coverage_line"] > 0:
                continue  # Already have coverage data

            # Look for JaCoCo report in multiple possible locations
            search_paths = [
                Path.cwd() / "repos" / service,
                Path.cwd() / service,
            ]

            report_found = False
            for base_path in search_paths:
                if not base_path.exists():
                    continue

                # Try multiple report paths
                report_paths = [
                    base_path / "target" / "site" / "jacoco" / "index.html",
                ]

                # Also check provider-specific subdirectories
                provider_dir = base_path / "provider"
                if provider_dir.exists():
                    for subdir in provider_dir.iterdir():
                        if subdir.is_dir():
                            report_paths.append(subdir / "target" / "site" / "jacoco" / "index.html")

                for report_path in report_paths:
                    if report_path.exists():
                        try:
                            content = report_path.read_text(encoding='utf-8')

                            # Parse JaCoCo HTML - extract from "X of Y" format in bar cells
                            # Structure: <tfoot><tr><td>Total</td>
                            # <td class="bar">0 of 1,036</td>  <- Instructions
                            # <td class="ctr2">100%</td>
                            # <td class="bar">3 of 86</td>     <- Branches
                            # <td class="ctr2">96%</td>
                            # Then more data for Lines, Methods, Classes...

                            total_section = re.search(r'<tfoot>.*?</tfoot>', content, re.DOTALL)
                            if total_section:
                                tfoot_html = total_section.group()

                                # Extract all "X of Y" patterns from bar cells
                                bar_matches = re.findall(r'class="bar">(\d+(?:,\d+)?) of (\d+(?:,\d+)?)</td>', tfoot_html)

                                if len(bar_matches) >= 2:
                                    # Format: "MISSED of TOTAL"
                                    # First bar cell: Instructions (missed of total)
                                    # Second bar cell: Branches (missed of total)
                                    # bar_matches[0] = (inst_missed, inst_total)
                                    # bar_matches[1] = (branch_missed, branch_total)

                                    # Parse branches
                                    branch_missed = int(bar_matches[1][0].replace(',', ''))
                                    branch_total = int(bar_matches[1][1].replace(',', ''))
                                    branch_covered = branch_total - branch_missed
                                    branch_cov = int((branch_covered / branch_total) * 100) if branch_total > 0 else 0

                                    # Now find line coverage from ctr1/ctr2 pairs
                                    # After the branch percentage, we should have:
                                    # <td class="ctr1">X</td><td class="ctr2">Y</td> for complexity
                                    # <td class="ctr1">X</td><td class="ctr2">Y</td> for lines
                                    # We want the lines pair (second one)

                                    # Extract all ctr1 values (missed counts)
                                    ctr1_values = re.findall(r'class="ctr1">(\d+(?:,\d+)?)</td>', tfoot_html)
                                    # Extract all non-percentage ctr2 values (total counts)
                                    ctr2_all = re.findall(r'class="ctr2">(\d+(?:,\d+)?)</td>', tfoot_html)
                                    ctr2_values = [v for v in ctr2_all if not v.endswith('%') and '%' not in v]

                                    # Lines should be: ctr1[1] (missed), ctr2[1] (total)
                                    # ctr1[0], ctr2[0] = complexity
                                    # ctr1[1], ctr2[1] = lines
                                    if len(ctr1_values) >= 2 and len(ctr2_values) >= 2:
                                        line_missed = int(ctr1_values[1].replace(',', ''))
                                        line_total = int(ctr2_values[1].replace(',', ''))
                                        line_cov = int(((line_total - line_missed) / line_total) * 100) if line_total > 0 else 0
                                    else:
                                        # Fallback: use instruction coverage as proxy
                                        inst_missed = int(bar_matches[0][0].replace(',', ''))
                                        inst_total = int(bar_matches[0][1].replace(',', ''))
                                        inst_covered = inst_total - inst_missed
                                        line_cov = int((inst_covered / inst_total) * 100) if inst_total > 0 else 0

                                    if line_cov > 0 or branch_cov > 0:
                                        self.tracker.update(
                                            service,
                                            self.tracker.services[service]["status"],  # Keep current status
                                            f"Coverage: {line_cov}%/{branch_cov}%",
                                            phase="coverage",
                                            coverage_line=line_cov,
                                            coverage_branch=branch_cov,
                                        )
                                        report_found = True
                                        break
                        except Exception:
                            # Silently continue if we can't parse this report
                            pass

                if report_found:
                    break

    def _assess_coverage_quality(self):
        """Assess coverage quality based on coverage metrics."""
        for service in self.services:
            line_cov = self.tracker.services[service]["coverage_line"]
            branch_cov = self.tracker.services[service]["coverage_branch"]

            if line_cov == 0 and branch_cov == 0:
                continue  # No coverage data to assess

            # Determine quality grade
            if line_cov >= 90 and branch_cov >= 85:
                grade = "A"
                label = "Excellent"
                summary = "Outstanding test coverage with all critical paths well-tested."
            elif line_cov >= 80 and branch_cov >= 70:
                grade = "B"
                label = "Good"
                summary = "Good test coverage with most critical paths tested."
            elif line_cov >= 70 and branch_cov >= 60:
                grade = "C"
                label = "Acceptable"
                summary = "Acceptable coverage but room for improvement."
            elif line_cov >= 60 and branch_cov >= 50:
                grade = "D"
                label = "Needs Improvement"
                summary = "Coverage is below recommended levels. Consider adding more tests."
            else:
                grade = "F"
                label = "Poor"
                summary = "Critical gaps in test coverage. Immediate attention needed."

            # Generate recommendations based on coverage levels
            recommendations = []

            if branch_cov < line_cov - 15:
                recommendations.append({
                    "priority": 1,
                    "action": "Improve branch coverage by testing edge cases and conditions",
                    "expected_improvement": f"+{min(10, line_cov - branch_cov)}% branch coverage"
                })

            if line_cov < 80:
                recommendations.append({
                    "priority": 1 if not recommendations else 2,
                    "action": "Add unit tests for uncovered methods and classes",
                    "expected_improvement": f"+{min(15, 80 - line_cov)}% line coverage"
                })

            if line_cov >= 80 and branch_cov < 80:
                recommendations.append({
                    "priority": len(recommendations) + 1,
                    "action": "Focus on testing complex conditional logic",
                    "expected_improvement": "Better branch coverage"
                })

            if grade in ["A", "B"] and len(recommendations) == 0:
                recommendations.append({
                    "priority": 1,
                    "action": "Maintain current coverage levels with new code",
                    "expected_improvement": "Sustained quality"
                })

            # Store assessment results
            self.tracker.services[service]["quality_grade"] = grade
            self.tracker.services[service]["quality_label"] = label
            self.tracker.services[service]["quality_summary"] = summary
            self.tracker.services[service]["recommendations"] = recommendations[:3]  # Top 3 only

    def get_quality_panel(self) -> Panel:
        """Generate quality assessment panel with clean columnar layout"""
        from rich.table import Table

        # Create a table for the results
        table = Table(expand=True, show_header=True, header_style="bold cyan")
        table.add_column("Service", style="cyan", no_wrap=True)
        table.add_column("Provider", style="blue", no_wrap=True)
        table.add_column("Result", style="yellow", no_wrap=True)
        table.add_column("Grade", justify="center", no_wrap=True)
        table.add_column("Recommendation", style="white", ratio=2)

        for service, data in self.tracker.services.items():
            # Determine result status
            result = "Pending"
            result_style = "dim"

            if data["status"] == "compile_failed":
                result = "Compile Failed"
                result_style = "red"
            elif data["status"] == "test_failed":
                result = f"Failed ({data['tests_failed']}/{data['tests_run']} tests)"
                result_style = "red"
            elif data["status"] == "test_success":
                if data["tests_run"] > 0:
                    result = f"Passed ({data['tests_run']} tests)"
                    result_style = "green"
                elif data.get("coverage_line", 0) > 0:
                    result = f"Cov: {data['coverage_line']}%/{data['coverage_branch']}%"
                    result_style = "cyan"
                else:
                    # No tests (tests_run == 0) and no coverage
                    result = "No tests"
                    result_style = "yellow"
            elif data["status"] == "compile_success":
                result = "Compiled"
                result_style = "green"
            elif data["status"] == "assessing":
                result = "Assessing..."
                result_style = "magenta"
            elif data["status"] == "compiling":
                result = "Compiling..."
                result_style = "yellow"
            elif data["status"] == "testing":
                result = "Testing..."
                result_style = "blue"
            elif data["status"] == "coverage":
                result = "Coverage..."
                result_style = "cyan"

            # Grade column
            grade = ""
            grade_style = "white"
            if data.get("quality_grade"):
                grade = data["quality_grade"]
                grade_style = {
                    "A": "green",
                    "B": "cyan",
                    "C": "yellow",
                    "D": "magenta",
                    "F": "red"
                }.get(grade, "white")

            # Recommendation column
            recommendation = ""
            if data.get("recommendations"):
                # Get first recommendation
                rec = data["recommendations"][0]
                recommendation = rec.get("action", "")
                # Truncate if too long
                if len(recommendation) > 60:
                    recommendation = recommendation[:57] + "..."
            elif data.get("quality_label"):
                recommendation = data["quality_label"]

            table.add_row(
                service,
                self.tracker.provider.capitalize(),
                f"[{result_style}]{result}[/{result_style}]",
                f"[{grade_style}]{grade}[/{grade_style}]" if grade else "",
                recommendation
            )

        # Return table in panel
        return Panel(
            table,
            title="📊 Test Results",
            border_style="cyan"
        )

    def _save_log(self, return_code: int):
        """Save execution log to file"""
        try:
            with open(self.log_file, "w") as f:
                f.write(f"{'='*70}\n")
                f.write(f"Maven Test Execution Log\n")
                f.write(f"{'='*70}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Services: {', '.join(self.services)}\n")
                f.write(f"Provider: {self.provider}\n")
                f.write(f"Exit Code: {return_code}\n")
                f.write(f"{'='*70}\n\n")

                f.write("=== TEST RESULTS ===\n\n")
                for service, data in self.tracker.services.items():
                    f.write(f"{service}:\n")
                    f.write(f"  Status: {data['status']}\n")
                    f.write(f"  Phase: {data.get('phase', 'N/A')}\n")
                    f.write(f"  Tests Run: {data['tests_run']}\n")
                    f.write(f"  Tests Failed: {data['tests_failed']}\n")
                    f.write(f"  Coverage Line: {data['coverage_line']}%\n")
                    f.write(f"  Coverage Branch: {data['coverage_branch']}%\n")
                    if data.get("quality_grade"):
                        f.write(f"  Quality Grade: {data['quality_grade']} - {data.get('quality_label', 'N/A')}\n")
                        f.write(f"  Quality Summary: {data.get('quality_summary', 'N/A')}\n")
                        if data.get("recommendations"):
                            f.write(f"  Recommendations:\n")
                            for rec in data["recommendations"][:5]:
                                f.write(f"    - {rec.get('action', 'N/A')}")
                                if rec.get("expected_improvement"):
                                    f.write(f" ({rec['expected_improvement']})")
                                f.write(f"\n")
                    f.write(f"\n")

                f.write("\n=== FULL OUTPUT ===\n\n")
                f.write("\n".join(self.full_output))

            console.print(f"\n[dim]✓ Log saved to: {self.log_file}[/dim]")
        except Exception as e:
            console.print(f"[dim]Warning: Could not save log: {e}[/dim]")

    def get_summary_panel(self, return_code: int) -> Panel:
        """Generate final summary panel - uses the same clean table format as quality panel"""
        # Simply return the quality panel which already has the clean columnar layout
        return self.get_quality_panel()


