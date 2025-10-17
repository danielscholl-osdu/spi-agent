"""Test runner for executing Maven tests with coverage analysis."""

import logging
import os
import re
import subprocess
from datetime import datetime
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Dict, List, Set, Union

from rich.live import Live
from rich.panel import Panel

from spi_agent.copilot.base import BaseRunner
from spi_agent.copilot.base.runner import console
from spi_agent.copilot.config import config
from spi_agent.copilot.trackers import TestTracker

# Maximum depth for recursive JaCoCo CSV discovery (prevents runaway searches)
# Depth of 8 accommodates nested structures like providers/azure/service-azure/target/site/jacoco/jacoco.csv (7 parts)
JACOCO_CSV_MAX_SEARCH_DEPTH = 8


class TestRunner(BaseRunner):
    """Runs Copilot CLI to execute Maven tests with live output and coverage analysis"""

    def __init__(
        self,
        prompt_file: Union[Path, Traversable],
        services: List[str],
        provider: str = "core,core-plus,azure",
    ):
        super().__init__(prompt_file, services)
        self.provider = provider

        # Parse provider into profiles list
        self.profiles = self._parse_provider_to_profiles(provider)

        # Create tracker with profiles if multiple specified
        self.tracker = TestTracker(services, provider, profiles=self.profiles if len(self.profiles) > 1 else [])

        # Initialize logger for coverage extraction debugging
        # Configure to write only to log file, not console
        self.logger = logging.getLogger(f"{__name__}.{id(self)}")  # Unique logger per instance
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False  # Prevent propagation to root logger (blocks console output)

        # Add file handler
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setFormatter(
            logging.Formatter('[%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s] %(message)s')
        )
        self.logger.addHandler(file_handler)

        # Track current Maven module being built (for per-profile test count parsing)
        self.current_module = None

        # Track current service for structured test results parsing
        self.current_test_service = None

    @property
    def log_prefix(self) -> str:
        """Return log file prefix for this runner type."""
        return "test"

    def _parse_provider_to_profiles(self, provider: str) -> List[str]:
        """Parse provider string into list of profiles.

        Args:
            provider: Provider string (e.g., "azure", "azure,aws", "all")

        Returns:
            List of profile names (normalized to lowercase)
        """
        if provider.lower() == "all":
            return ["core", "core-plus", "azure", "aws", "gc", "ibm"]
        elif "," in provider:
            # Multiple providers specified - normalize to lowercase
            return [p.strip().lower() for p in provider.split(",")]
        else:
            # Single provider - normalize to lowercase
            return [provider.strip().lower()]

    def _extract_profile_from_module(self, module_name: str) -> str:
        """Extract profile name from Maven module name.

        Args:
            module_name: Maven module name (e.g., "partition-core", "entitlements-v2-azure")

        Returns:
            Profile name (e.g., "core", "azure") or None if not recognized
        """
        module_lower = module_name.lower()

        # Check for each profile in order of specificity (core-plus before core)
        if "core-plus" in module_lower or "coreplus" in module_lower:
            return "core-plus"
        elif "-core" in module_lower or module_lower.endswith("core"):
            return "core"
        elif "azure" in module_lower:
            return "azure"
        elif "aws" in module_lower:
            return "aws"
        elif "gc" in module_lower or "gcp" in module_lower:
            return "gc"
        elif "ibm" in module_lower:
            return "ibm"

        return None

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
        if len(self.profiles) > 1:
            # Convert "core-plus" to "core+" for display
            profiles_display = [p if p != "core-plus" else "core+" for p in self.profiles]
            profiles_str = ', '.join(profiles_display)
            config_text = f"""[cyan]Services:[/cyan]   {', '.join(self.services)}
[cyan]Profiles:[/cyan]   {profiles_str}"""
        else:
            # Convert "core-plus" to "core+" for display
            provider_display = self.provider.replace("core-plus", "core+")
            config_text = f"""[cyan]Services:[/cyan]   {', '.join(self.services)}
[cyan]Provider:[/cyan]   {provider_display}"""

        console.print(Panel(config_text, title="🧪 Maven Test Execution", border_style="blue"))
        console.print()

    def parse_output(self, line: str) -> None:
        """Parse copilot's task announcements and Maven build output for test status updates"""
        line_lower = line.lower()
        line_stripped = line.strip()

        # PRIORITY 0: Parse structured test results blocks (NEW FORMAT)
        # Pattern: [TEST_RESULTS:service]
        #          profile=azure,tests_run=61,failures=0,errors=0,skipped=0
        #          [/TEST_RESULTS]
        if line_stripped.startswith("[TEST_RESULTS:"):
            # Extract service name from [TEST_RESULTS:service] - allow hyphens in service names (e.g., indexer-queue)
            match = re.match(r'\[TEST_RESULTS:([\w-]+)\]', line_stripped)
            if match:
                self.current_test_service = match.group(1)
                self.logger.debug(f"Detected structured test results block for: {self.current_test_service}")
                return

        # Parse structured test result lines
        if hasattr(self, 'current_test_service') and self.current_test_service:
            if line_stripped == "[/TEST_RESULTS]":
                self.logger.debug(f"End of test results block for: {self.current_test_service}")
                # Aggregate profile data if in multi-profile mode
                if len(self.profiles) > 1:
                    self.tracker._aggregate_profile_data(self.current_test_service)
                self.current_test_service = None
                return

            # Parse: profile=azure,tests_run=61,failures=0,errors=0,skipped=0
            result_match = re.match(r'profile=(\w+(?:-\w+)?),tests_run=(\d+),failures=(\d+),errors=(\d+),skipped=(\d+)', line_stripped)
            if result_match:
                profile = result_match.group(1)
                tests_run = int(result_match.group(2))
                failures = int(result_match.group(3))
                errors = int(result_match.group(4))
                skipped = int(result_match.group(5))
                tests_failed = failures + errors

                self.logger.info(f"[{self.current_test_service}:{profile}] Structured test results: {tests_run} tests run, {tests_failed} failed")

                # Determine status based on failures
                status = "test_failed" if tests_failed > 0 else "test_success"

                # Update tracker with structured test counts
                if len(self.profiles) > 1 and profile in self.profiles:
                    # Multi-profile mode: update profile-specific data
                    self.tracker.update(self.current_test_service, status, f"{tests_run} tests",
                                      phase="test", profile=profile, tests_run=tests_run, tests_failed=tests_failed)
                elif len(self.profiles) == 1:
                    # Single-profile mode: update service-level data
                    self.tracker.update(self.current_test_service, status, f"{tests_run} tests",
                                      phase="test", tests_run=tests_run, tests_failed=tests_failed)
                return

            # Parse optional failed test names
            # Single-profile: failed_tests=TestA,TestB,TestC
            # Multi-profile: failed_tests[profile]=TestA,TestB,TestC
            failed_match = re.match(r'failed_tests(?:\[(\w+(?:-\w+)?)\])?=(.+)', line_stripped)
            if failed_match:
                profile = failed_match.group(1)  # May be None for single-profile
                failed_tests = failed_match.group(2).split(',')

                self.logger.info(f"[{self.current_test_service}:{profile or 'default'}] Failed tests: {failed_tests}")

                # Store failed test names for future display (optional enhancement)
                # For now, just log them
                return

        # PRIORITY 1: Track Maven module being built (for fallback per-profile test counts)
        # Pattern: "[INFO] Building partition-core 0.29.0-SNAPSHOT"
        building_match = re.search(r'\[INFO\]\s+Building\s+([\w\-]+)', line)
        if building_match:
            self.current_module = building_match.group(1)
            self.logger.debug(f"Detected Maven module: {self.current_module}")
            return

        # Find which service this line is about
        target_service = None
        for service in self.services:
            # Match service name in various formats: "partition", "Partition", "**partition**"
            if service in line_lower or f"**{service}**" in line_lower:
                target_service = service
                break

        if not target_service:
            return

        # PRIORITY 1: Parse Maven module test results (per-profile, from "Results:" section)
        # Pattern: "[INFO] Tests run: 61, Failures: 0, Errors: 0, Skipped: 0" in Results section
        # Only parse if we have tracked a current module and are in multi-profile mode
        if self.current_module and len(self.profiles) > 1:
            # Check if this is a Results summary line (not individual test output)
            # Results summaries appear in the "Results:" section after all tests complete
            maven_result_match = re.search(r'\[INFO\]\s+Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+)', line)
            if maven_result_match:
                # Extract profile from current module name
                profile = self._extract_profile_from_module(self.current_module)

                if profile and profile in self.profiles:
                    tests_run = int(maven_result_match.group(1))
                    tests_failed = int(maven_result_match.group(2)) + int(maven_result_match.group(3))

                    # Update tracker with profile-specific test count
                    self.logger.debug(f"[{target_service}:{profile}] Detected Maven test results for module {self.current_module}: {tests_run} tests run, {tests_failed} failed")
                    self.tracker.update(target_service, "test_success", f"{tests_run} tests",
                                      phase="test", profile=profile, tests_run=tests_run, tests_failed=tests_failed)
                    return

        # PRIORITY 2: Parse actual Maven test output for single-profile mode (reliable, deterministic)
        # Maven Surefire always outputs: "Tests run: X, Failures: Y, Errors: Z, Skipped: N"
        if len(self.profiles) == 1:
            maven_test_match = re.search(r'Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+)', line)
            if maven_test_match:
                tests_run = int(maven_test_match.group(1))
                tests_failed = int(maven_test_match.group(2)) + int(maven_test_match.group(3))

                # Update tracker immediately when Maven reports test results
                self.logger.debug(f"[{target_service}] Detected Maven test output: {tests_run} tests run, {tests_failed} failed")
                self.tracker.update(target_service, "test_success", f"{tests_run} tests",
                                  phase="test", tests_run=tests_run, tests_failed=tests_failed)
                return

        # Parse copilot's status updates (matches the exact format from test.md prompt)
        # Strip leading bullets (● prefix)
        line_for_parsing = line_stripped.lstrip("●").strip()

        # Only parse lines starting with ✓ (task completion markers)
        if line_for_parsing.startswith("✓") and ":" in line_for_parsing:
            # Expected formats from prompt:
            # "✓ partition: Starting compile phase"
            # "✓ partition: Starting test phase"
            # "✓ partition: Compiled successfully, 61 tests passed"

            if "starting compile phase" in line_lower:
                self.tracker.update(target_service, "compiling", "Compiling", phase="compile")

            elif "starting test phase" in line_lower:
                self.tracker.update(target_service, "testing", "Testing", phase="test")

            elif "compiled successfully" in line_lower:
                # PRIORITY 2: Parse AI summary (fallback for compatibility)
                # Only update if we don't already have test count from Maven output
                current_tests = self.tracker.services[target_service]["tests_run"]

                if current_tests == 0:
                    # Extract test count from AI summary as fallback
                    test_count_match = re.search(r'(\d+)\s+tests?\s+passed', line_lower)
                    tests_run = int(test_count_match.group(1)) if test_count_match else 0

                    self.logger.debug(f"[{target_service}] Using AI summary test count as fallback: {tests_run} tests")
                    self.tracker.update(target_service, "test_success", "Complete",
                                      phase="test", tests_run=tests_run, tests_failed=0)
                else:
                    # Maven already provided test count, just update phase
                    self.logger.debug(f"[{target_service}] Maven test count already captured ({current_tests}), skipping AI summary")
                    self.tracker.update(target_service, "test_success", "Complete", phase="test")

        # Detect errors
        if "build failure" in line_lower and target_service:
            self.tracker.update(target_service, "test_failed", "Build failed", phase="test")
        elif "compilation failure" in line_lower and target_service:
            self.tracker.update(target_service, "compile_failed", "Failed", phase="compile")

    def run(self) -> int:
        """Execute copilot to run Maven tests with live output"""
        global current_process

        self.show_config()
        console.print(f"[dim]Logging to: {self.log_file}[/dim]\n")

        prompt_content = self.load_prompt()

        # Use model from environment or default to Claude Sonnet 4.5
        model = os.getenv("SPI_AGENT_COPILOT_MODEL", "claude-sonnet-4.5")
        command = ["copilot", "--model", model, "-p", prompt_content, "--allow-all-tools"]

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
            layout["output"].update(self._output_panel_renderable)

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
                            self.parse_output(line)

                            # Update output panel every line (deque handles scrolling)
                            # Only update status table if status changed or every 10 lines
                            status_changed = old_status != self.tracker.services
                            last_update += 1

                            if status_changed or last_update >= 10:
                                layout["status"].update(self.tracker.get_table())
                                last_update = 0

                            # Always update output to show new lines in scrolling window
                            layout["output"].update(self._output_panel_renderable)

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

            # Validate test counts against surefire reports (ensures deterministic, accurate counts)
            self._validate_test_counts()

            # Generate coverage reports in parallel (Python-driven, deterministic)
            self._generate_coverage_reports()

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

            # Print the final results panel
            console.print(self.get_results_panel(process.returncode))

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

    def _map_profile_to_modules(self, service: str, base_path: Path, profile: str) -> List[Path]:
        """
        Map a profile to its corresponding Maven module directories.

        This method detects which module directories belong to a specific profile
        by examining the directory structure and naming conventions.

        Args:
            service: Service name
            base_path: Base path to search for modules
            profile: Profile name (e.g., "core", "azure", "core-plus")

        Returns:
            List of Path objects pointing to module directories that match the profile
        """
        module_paths = []
        profile_lower = profile.lower()
        profile_normalized = profile_lower.replace("-", "")

        self.logger.debug(f"[{service}:{profile}] Mapping profile to module directories in {base_path}")

        # Pattern 1: {service}-{profile}/ (e.g., partition-core/, partition-azure/)
        direct_module = base_path / f"{service}-{profile}"
        if direct_module.exists() and direct_module.is_dir():
            self.logger.debug(f"[{service}:{profile}] Found direct module: {direct_module.name}")
            module_paths.append(direct_module)

        # Pattern 2: providers/{service}-{profile}/ (e.g., providers/partition-azure/)
        providers_module = base_path / "providers" / f"{service}-{profile}"
        if providers_module.exists() and providers_module.is_dir():
            self.logger.debug(f"[{service}:{profile}] Found providers module: {providers_module.name}")
            module_paths.append(providers_module)

        # Pattern 3: provider/{service}-{profile}/ (singular "provider")
        provider_module = base_path / "provider" / f"{service}-{profile}"
        if provider_module.exists() and provider_module.is_dir():
            self.logger.debug(f"[{service}:{profile}] Found provider module: {provider_module.name}")
            module_paths.append(provider_module)

        # Pattern 4: Check all subdirectories for matching names
        # This handles variations like: core/, partition-core-plus/, etc.
        for item in base_path.iterdir():
            if not item.is_dir() or item.name in ["target", "src", ".git", "provider", "providers"]:
                continue

            item_normalized = item.name.lower().replace("-", "")

            # Match if profile name appears in directory name
            if profile == "core-plus":
                # Special handling: only match if "coreplus" or "core-plus" in name
                if "coreplus" in item_normalized or "core-plus" in item.name.lower():
                    if item not in module_paths:
                        self.logger.debug(f"[{service}:{profile}] Found matching module: {item.name}")
                        module_paths.append(item)
            elif profile == "core":
                # Core should not match core-plus
                if "core" in item_normalized and "coreplus" not in item_normalized:
                    if item not in module_paths:
                        self.logger.debug(f"[{service}:{profile}] Found matching module: {item.name}")
                        module_paths.append(item)
            else:
                # Regular profile matching
                if profile_normalized in item_normalized:
                    if item not in module_paths:
                        self.logger.debug(f"[{service}:{profile}] Found matching module: {item.name}")
                        module_paths.append(item)

        # Pattern 5: Check providers/ and provider/ subdirectories
        for provider_dir in [base_path / "providers", base_path / "provider"]:
            if not provider_dir.exists():
                continue

            for item in provider_dir.iterdir():
                if not item.is_dir():
                    continue

                item_normalized = item.name.lower().replace("-", "")

                if profile == "core-plus":
                    if "coreplus" in item_normalized or "core-plus" in item.name.lower():
                        if item not in module_paths:
                            self.logger.debug(f"[{service}:{profile}] Found provider submodule: {item.name}")
                            module_paths.append(item)
                elif profile == "core":
                    if "core" in item_normalized and "coreplus" not in item_normalized:
                        if item not in module_paths:
                            self.logger.debug(f"[{service}:{profile}] Found provider submodule: {item.name}")
                            module_paths.append(item)
                else:
                    if profile_normalized in item_normalized:
                        if item not in module_paths:
                            self.logger.debug(f"[{service}:{profile}] Found provider submodule: {item.name}")
                            module_paths.append(item)

        if module_paths:
            self.logger.info(f"[{service}:{profile}] Mapped profile to {len(module_paths)} module(s): {[p.name for p in module_paths]}")
        else:
            self.logger.warning(f"[{service}:{profile}] No module directories found for profile")

        return module_paths

    def _find_all_jacoco_csvs(
        self,
        service: str,
        base_path: Path,
    ) -> List[tuple[Path, str]]:
        """Recursively find jacoco.csv files under base_path while guarding depth.

        This method discovers JaCoCo coverage reports regardless of directory structure,
        making it resilient to inconsistent Maven module layouts.

        Args:
            service: Service name for logging
            base_path: Base directory to search

        Returns:
            List of (csv_path, source_description) tuples
        """
        csv_files: list[tuple[Path, str]] = []
        seen: set[Path] = set()

        for csv_path in base_path.rglob("jacoco.csv"):
            # Deduplication guard
            if csv_path in seen:
                continue
            seen.add(csv_path)

            # Calculate relative path for depth checking
            relative = csv_path.relative_to(base_path)

            # Depth guard: Prevent searching too deep (e.g., node_modules, .m2 cache)
            if len(relative.parts) > JACOCO_CSV_MAX_SEARCH_DEPTH:
                self.logger.debug(f"[{service}] Skipping {csv_path} (exceeds depth limit {JACOCO_CSV_MAX_SEARCH_DEPTH})")
                continue

            # Filter out test-scoped JaCoCo reports
            if "test-classes" in relative.parts:
                self.logger.debug(f"[{service}] Skipping {csv_path} (test-classes artifact)")
                continue

            # Extract module hint from path (for source attribution in logs)
            # Walk backwards through directory parts (excluding filename), skip standard Maven directories
            module_hint = next(
                (part for part in reversed(relative.parent.parts) if part not in {"target", "site", "jacoco"}),
                relative.parent.name,
            )
            csv_files.append((csv_path, f"discovered:{module_hint}"))

        self.logger.info(
            f"[{service}] Recursive search found {len(csv_files)} jacoco.csv file(s) (depth ≤ {JACOCO_CSV_MAX_SEARCH_DEPTH})"
        )
        return csv_files

    def _verify_coverage_generated(self, service: str, base_path: Path) -> bool:
        """Check if Maven actually generated coverage reports.

        This pre-flight validation prevents the parser from attempting extraction
        when JaCoCo reports don't exist, providing clear diagnostic messages.

        Args:
            service: Service name
            base_path: Base path to check for reports

        Returns:
            True if at least one jacoco.csv exists anywhere under base_path
        """
        jacoco_files = [
            csv_path
            for csv_path, _ in self._find_all_jacoco_csvs(service, base_path)
        ]

        if not jacoco_files:
            self.logger.error(
                f"[{service}] No jacoco.csv files found anywhere in {base_path}. "
                f"Possible causes:\n"
                f"  1. jacoco-maven-plugin not configured in pom.xml\n"
                f"  2. Maven 'jacoco:report' goal did not run\n"
                f"  3. Coverage reports were deleted by 'mvn clean'"
            )
            return False

        self.logger.info(f"[{service}] Verified coverage generation: {len(jacoco_files)} report(s) exist")
        return True

    def _count_tests_from_surefire(self, service: str, base_path: Path, profile: str = None) -> tuple[int, int]:
        """
        Count tests by parsing surefire-reports/*.xml files directly.

        This provides an independent, deterministic count of tests that doesn't rely
        on AI parsing. Surefire XML reports are always present after test execution
        and provide accurate test counts.

        Args:
            service: Service name
            base_path: Base path to search for surefire reports
            profile: Optional profile name to filter by module

        Returns:
            Tuple of (tests_run, tests_failed)
        """
        import xml.etree.ElementTree as ET

        tests_run = 0
        tests_failed = 0

        profile_prefix = f"[{service}:{profile}] " if profile else f"[{service}] "

        # Map profile to module directories
        if profile:
            module_dirs = self._map_profile_to_modules(service, base_path, profile)
        else:
            # Get all modules
            module_dirs = [base_path]
            # Add provider subdirectories
            for provider_dir_name in ["provider", "providers"]:
                provider_dir = base_path / provider_dir_name
                if provider_dir.exists():
                    for item in provider_dir.iterdir():
                        if item.is_dir():
                            module_dirs.append(item)
            # Add top-level module subdirectories
            for item in base_path.iterdir():
                if item.is_dir() and item.name not in ["target", "src", ".git", "provider", "providers"]:
                    module_dirs.append(item)

        # Parse surefire XML reports
        xml_files_found = 0
        for module_dir in module_dirs:
            surefire_dir = module_dir / "target" / "surefire-reports"
            if not surefire_dir.exists():
                continue

            for xml_file in surefire_dir.glob("TEST-*.xml"):
                xml_files_found += 1
                try:
                    tree = ET.parse(xml_file)
                    root = tree.getroot()

                    # Parse testsuite attributes
                    tests = int(root.get('tests', 0))
                    failures = int(root.get('failures', 0))
                    errors = int(root.get('errors', 0))

                    tests_run += tests
                    tests_failed += failures + errors

                    self.logger.debug(f"{profile_prefix}Parsed {xml_file.name}: {tests} tests, {failures + errors} failed")

                except Exception as e:
                    self.logger.warning(f"{profile_prefix}Failed to parse {xml_file}: {e}")
                    continue

        if xml_files_found > 0:
            self.logger.info(f"{profile_prefix}Surefire XML parsing: {tests_run} tests run, {tests_failed} failed from {xml_files_found} file(s)")
        else:
            self.logger.debug(f"{profile_prefix}No surefire XML reports found")

        return (tests_run, tests_failed)

    def _validate_test_counts(self):
        """
        Validate AI-reported test counts against actual surefire reports.
        Corrects discrepancies and logs warnings when AI counts don't match reality.

        This runs after the AI agent completes but before displaying final results,
        ensuring that displayed test counts are always accurate and deterministic.
        """
        self.logger.info("Starting test count validation against surefire reports")

        for service in self.services:
            base_path = Path.cwd() / "repos" / service
            if not base_path.exists():
                base_path = Path.cwd() / service

            if not base_path.exists():
                self.logger.warning(f"[{service}] No valid path found for validation")
                continue

            if len(self.profiles) > 1:
                # Multi-profile mode: validate each profile
                for profile in self.profiles:
                    ai_count = self.tracker.services[service]["profiles"][profile].get("tests_run", 0)
                    ai_failed = self.tracker.services[service]["profiles"][profile].get("tests_failed", 0)

                    actual_count, actual_failed = self._count_tests_from_surefire(service, base_path, profile)

                    # Only correct if there's a mismatch AND we found actual tests
                    if actual_count > 0 and (ai_count != actual_count or ai_failed != actual_failed):
                        self.logger.warning(
                            f"[{service}:{profile}] Test count mismatch - "
                            f"AI reported {ai_count} tests ({ai_failed} failed), "
                            f"surefire shows {actual_count} tests ({actual_failed} failed). "
                            f"Using surefire as source of truth."
                        )
                        # Correct the count
                        status = "test_failed" if actual_failed > 0 else "test_success"
                        self.tracker.update(
                            service, status, f"{actual_count} tests",
                            profile=profile, tests_run=actual_count, tests_failed=actual_failed
                        )
                    elif actual_count > 0:
                        self.logger.info(f"[{service}:{profile}] Test count validated: {actual_count} tests")

                # Re-aggregate after corrections
                self.tracker._aggregate_profile_data(service)

            else:
                # Single-profile mode
                ai_count = self.tracker.services[service].get("tests_run", 0)
                ai_failed = self.tracker.services[service].get("tests_failed", 0)

                actual_count, actual_failed = self._count_tests_from_surefire(service, base_path)

                # Only correct if there's a mismatch AND we found actual tests
                if actual_count > 0 and (ai_count != actual_count or ai_failed != actual_failed):
                    self.logger.warning(
                        f"[{service}] Test count mismatch - "
                        f"AI reported {ai_count} tests ({ai_failed} failed), "
                        f"surefire shows {actual_count} tests ({actual_failed} failed). "
                        f"Using surefire as source of truth."
                    )
                    status = "test_failed" if actual_failed > 0 else "test_success"
                    self.tracker.update(
                        service, status, f"{actual_count} tests",
                        tests_run=actual_count, tests_failed=actual_failed
                    )
                elif actual_count > 0:
                    self.logger.info(f"[{service}] Test count validated: {actual_count} tests")

        self.logger.info("Test count validation complete")

    def _generate_coverage_for_service(self, service: str) -> tuple[bool, str]:
        """Generate coverage reports for a single service."""
        # Locate service directory
        base_path = Path.cwd() / "repos" / service
        if not base_path.exists():
            base_path = Path.cwd() / service

        if not base_path.exists():
            msg = "Service directory not found"
            self.logger.warning(f"[{service}] {msg}")
            return (False, msg)

        pom_path = base_path / "pom.xml"
        if not pom_path.exists():
            msg = "No pom.xml found"
            self.logger.warning(f"[{service}] {msg}")
            return (False, msg)

        try:
            pom_content = pom_path.read_text(encoding='utf-8')
        except Exception as exc:
            pom_content = ""
            self.logger.debug(f"[{service}] Failed to read pom.xml: {exc}")

        has_root_jacoco = "jacoco-maven-plugin" in pom_content

        # Identify module directories for each requested profile
        modules_by_profile: Dict[str, List[Path]] = {}
        for profile in self.profiles:
            try:
                module_dirs = self._map_profile_to_modules(service, base_path, profile)
            except Exception as exc:
                self.logger.debug(f"[{service}] Failed mapping profile '{profile}': {exc}")
                module_dirs = []

            if module_dirs:
                modules_by_profile[profile] = module_dirs

        modules_to_process: Dict[Path, Set[str]] = {}
        for profile, module_dirs in modules_by_profile.items():
            for module_dir in module_dirs:
                modules_to_process.setdefault(module_dir, set()).add(profile)

        if has_root_jacoco and base_path not in modules_to_process:
            modules_to_process[base_path] = set()

        if not modules_to_process:
            if has_root_jacoco:
                modules_to_process[base_path] = set()
            else:
                msg = "JaCoCo plugin not configured for requested profiles"
                self.logger.warning(f"[{service}] {msg}")
                return (False, msg)

        coverage_timeout = 60  # seconds
        success_modules: List[str] = []
        failed_modules: List[str] = []
        failure_messages: List[str] = []

        for module_dir, profiles in modules_to_process.items():
            module_rel = (
                module_dir.relative_to(base_path).as_posix()
                if module_dir != base_path else "."
            )
            profile_label = ",".join(sorted(profiles)) if profiles else "all"
            self.logger.info(
                f"[{service}] Generating coverage for module {module_rel} (profiles: {profile_label})"
            )

            cmd = ["mvn", "jacoco:report", "-DskipTests"]
            self.logger.debug(f"[{service}] Command ({module_rel}): {' '.join(cmd)}")

            try:
                result = subprocess.run(
                    cmd,
                    cwd=module_dir,
                    capture_output=True,
                    text=True,
                    timeout=coverage_timeout,
                    check=False,
                )

                if result.returncode == 0:
                    self.logger.info(
                        f"[{service}] ✓ Coverage generation succeeded for module {module_rel}"
                    )
                    if "BUILD SUCCESS" in result.stdout:
                        self.logger.debug(
                            f"[{service}] {module_rel}: Maven reported BUILD SUCCESS"
                        )
                    success_modules.append(module_rel)
                else:
                    stderr_preview = result.stderr[:500] if result.stderr else "No stderr"
                    msg = (
                        f"{module_rel} failed (exit code {result.returncode}) - {stderr_preview}"
                    )
                    self.logger.error(f"[{service}] ✗ {msg}")
                    if result.stdout:
                        self.logger.debug(f"[{service}] {module_rel} stdout:\n{result.stdout}")
                    if result.stderr:
                        self.logger.debug(f"[{service}] {module_rel} stderr:\n{result.stderr}")
                    failed_modules.append(module_rel)
                    failure_messages.append(msg)

            except subprocess.TimeoutExpired:
                msg = f"{module_rel} timed out after {coverage_timeout}s"
                self.logger.error(f"[{service}] ✗ {msg}")
                failed_modules.append(module_rel)
                failure_messages.append(msg)

            except FileNotFoundError:
                msg = "Maven command not found"
                self.logger.error(f"[{service}] ✗ {msg}")
                return (False, msg)

            except Exception as exc:
                msg = f"{module_rel} unexpected error: {exc}"
                self.logger.error(f"[{service}] ✗ {msg}")
                import traceback
                self.logger.debug(f"[{service}] Traceback:\n{traceback.format_exc()}")
                failed_modules.append(module_rel)
                failure_messages.append(msg)

        if success_modules:
            summary = f"{len(success_modules)}/{len(modules_to_process)} module(s) generated coverage"
            if len(success_modules) <= 3:
                summary += f" ({', '.join(success_modules)})"
            return (True, summary)

        msg = failure_messages[0] if failure_messages else "Coverage generation failed"
        return (False, msg)

    def _generate_coverage_reports(self):
        """Generate JaCoCo coverage reports with sequential feedback."""
        # Add blank line and header to output panel
        self.output_lines.append("")
        self.output_lines.append("📊 Generating Coverage Reports...")
        self.full_output.append("")
        self.full_output.append("📊 Generating Coverage Reports...")

        for service in self.services:
            self.tracker.update(service, "coverage", "Generating coverage", phase="coverage")

        for service in self.services:
            msg = f"  → {service}: generating coverage…"
            self.output_lines.append(msg)
            self.full_output.append(msg)

            success, message = self._generate_coverage_for_service(service)

            if success:
                result_msg = f"    ✓ {service}: {message}"
                self.output_lines.append(result_msg)
                self.full_output.append(result_msg)
                self.tracker.update(service, "test_success", message, phase="coverage")
            else:
                result_msg = f"    ⚠ {service}: {message}"
                self.output_lines.append(result_msg)
                self.full_output.append(result_msg)
                self.tracker.update(service, "test_success", f"Coverage: {message}", phase="coverage")

        completion_msg = "Coverage generation complete"
        self.output_lines.append(completion_msg)
        self.full_output.append(completion_msg)

    def _extract_coverage_from_csv(self, service: str, base_path: Path, profile: str = None) -> tuple[float, float]:
        """
        Extract coverage data from JaCoCo CSV reports.

        CSV format is stable and reliable across JaCoCo versions.
        Returns (line_coverage_percent, branch_coverage_percent).

        Args:
            service: Service name
            base_path: Base path to search for coverage reports
            profile: Optional profile name to filter coverage by module
        """
        profile_prefix = f"[{service}:{profile}] " if profile else f"[{service}] "

        # Strategy: For profile-specific extraction, prioritize per-module CSV files
        # This is more reliable than filtering aggregated CSV rows
        csv_paths = []

        if profile:
            # Profile-specific mode: Find CSV files from modules that match this profile
            self.logger.info(f"{profile_prefix}Starting profile-specific coverage extraction")

            # Map profile to module directories
            module_dirs = self._map_profile_to_modules(service, base_path, profile)

            if module_dirs:
                # Read CSV from each matched module
                for module_dir in module_dirs:
                    module_csv = module_dir / "target" / "site" / "jacoco" / "jacoco.csv"
                    if module_csv.exists():
                        csv_paths.append((module_csv, f"module:{module_dir.name}"))
                        self.logger.debug(f"{profile_prefix}Queued module CSV: {module_csv} (source: {module_dir.name})")
                    else:
                        self.logger.warning(f"{profile_prefix}Module {module_dir.name} has no jacoco.csv at expected location")

            # Fallback: If no module-specific CSVs found, try filtering aggregated CSV
            if not csv_paths:
                self.logger.warning(f"{profile_prefix}No module-specific CSVs found, falling back to aggregated CSV filtering")
                aggregated_csv = base_path / "target" / "site" / "jacoco" / "jacoco.csv"
                if aggregated_csv.exists():
                    csv_paths.append((aggregated_csv, "aggregated:filtered"))
                    self.logger.debug(f"{profile_prefix}Using aggregated CSV with row filtering: {aggregated_csv}")

            # FINAL FALLBACK: Recursive discovery when all heuristics fail
            if not csv_paths:
                self.logger.warning(
                    f"{profile_prefix}Module and aggregated CSVs not found at expected paths, "
                    f"trying recursive search (depth ≤ {JACOCO_CSV_MAX_SEARCH_DEPTH})"
                )
                all_discovered = self._find_all_jacoco_csvs(service, base_path)

                # Filter discovered CSVs to only include those matching the requested profile
                # This prevents cross-profile contamination (e.g., azure profile parsing aws coverage)
                profile_normalized = profile.lower().replace("-", "")
                for csv_path, source_hint in all_discovered:
                    path_str = str(csv_path).lower()

                    # Check if profile name appears in the path
                    matched = False
                    if profile == "core-plus":
                        if "core-plus" in path_str or "coreplus" in path_str:
                            matched = True
                    elif profile == "core":
                        # Core must not match core-plus
                        if "core" in path_str and "coreplus" not in path_str and "core-plus" not in path_str:
                            matched = True
                    else:
                        # Regular profile matching
                        if profile_normalized in path_str.replace("-", ""):
                            matched = True

                    if matched:
                        # Tag as filtered so CSV parser knows to apply package filtering
                        csv_paths.append((csv_path, f"discovered:filtered:{source_hint.split(':')[1]}"))
                        self.logger.info(f"{profile_prefix}Matched discovered CSV: {csv_path}")
                    else:
                        self.logger.debug(f"{profile_prefix}Skipped discovered CSV (profile mismatch): {csv_path}")

                if not csv_paths:
                    self.logger.warning(f"{profile_prefix}Recursive search found {len(all_discovered)} CSV(s) but none matched profile '{profile}'")
        else:
            # Service-level mode: Collect all CSV files
            self.logger.info(f"{profile_prefix}Starting service-level coverage extraction")

            # Parent/aggregated report
            aggregated_csv = base_path / "target" / "site" / "jacoco" / "jacoco.csv"
            if aggregated_csv.exists():
                csv_paths.append((aggregated_csv, "aggregated"))

            # Provider subdirectories
            provider_dir = base_path / "provider"
            if provider_dir.exists():
                for subdir in provider_dir.iterdir():
                    if subdir.is_dir():
                        subdir_csv = subdir / "target" / "site" / "jacoco" / "jacoco.csv"
                        if subdir_csv.exists():
                            csv_paths.append((subdir_csv, f"provider:{subdir.name}"))

            # Multi-module structures
            for item in base_path.iterdir():
                if item.is_dir() and item.name not in ["target", "src", ".git", "provider", "providers"]:
                    item_csv = item / "target" / "site" / "jacoco" / "jacoco.csv"
                    if item_csv.exists() and (item_csv, f"module:{item.name}") not in csv_paths:
                        csv_paths.append((item_csv, f"module:{item.name}"))

        self.logger.info(f"{profile_prefix}Found {len(csv_paths)} CSV file(s) to process")

        total_line_covered = 0
        total_line_missed = 0
        total_branch_covered = 0
        total_branch_missed = 0
        files_parsed = 0
        rows_matched = 0
        rows_skipped = 0

        for csv_path, csv_source in csv_paths:
            try:
                self.logger.debug(f"{profile_prefix}Processing CSV: {csv_path} (source: {csv_source})")
                content = csv_path.read_text(encoding='utf-8')
                lines = content.strip().split('\n')

                if len(lines) < 2:
                    self.logger.warning(f"{profile_prefix}CSV file is empty or has no data rows: {csv_path}")
                    continue

                csv_rows_matched = 0
                csv_rows_skipped = 0

                # Skip header row, parse data rows
                for i, line in enumerate(lines[1:], start=2):
                    if not line.strip():
                        continue

                    parts = line.split(',')
                    if len(parts) < 9:
                        self.logger.debug(f"{profile_prefix}Skipping malformed CSV row {i}: insufficient columns")
                        csv_rows_skipped += 1
                        continue

                    # Profile filtering: apply for aggregated and discovered (filtered) CSV sources
                    if profile and ("aggregated:filtered" in csv_source or "discovered:filtered:" in csv_source):
                        # CSV columns: GROUP,PACKAGE,CLASS,...
                        group = parts[0].lower()
                        package = parts[1].lower()

                        profile_normalized = profile.lower().replace("-", "")
                        module_path = f"{group}.{package}"

                        # Check for profile match using improved logic
                        matched = False
                        if profile == "core-plus":
                            if "coreplus" in module_path or "core-plus" in module_path:
                                matched = True
                        elif profile == "core":
                            if "core" in module_path and "coreplus" not in module_path and "core-plus" not in module_path:
                                matched = True
                        else:
                            if profile_normalized in module_path.replace("-", ""):
                                matched = True

                        if not matched:
                            csv_rows_skipped += 1
                            continue

                    try:
                        # CSV columns: GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,
                        #              BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,...
                        branch_missed = int(parts[5])
                        branch_covered = int(parts[6])
                        line_missed = int(parts[7])
                        line_covered = int(parts[8])

                        total_line_covered += line_covered
                        total_line_missed += line_missed
                        total_branch_covered += branch_covered
                        total_branch_missed += branch_missed
                        csv_rows_matched += 1

                    except (ValueError, IndexError) as e:
                        self.logger.debug(f"{profile_prefix}Skipping malformed CSV row {i}: {e}")
                        csv_rows_skipped += 1
                        continue

                files_parsed += 1
                rows_matched += csv_rows_matched
                rows_skipped += csv_rows_skipped

                self.logger.info(f"{profile_prefix}Parsed {csv_path.name} ({csv_source}): {csv_rows_matched} rows matched, {csv_rows_skipped} rows skipped")
                self.logger.debug(f"{profile_prefix}Running totals - Lines: {total_line_covered} covered / {total_line_missed} missed, Branches: {total_branch_covered} covered / {total_branch_missed} missed")

            except Exception as e:
                self.logger.error(f"{profile_prefix}Failed to parse CSV at {csv_path}: {e}")
                import traceback
                self.logger.debug(f"{profile_prefix}Traceback: {traceback.format_exc()}")
                continue

        # Calculate percentages
        line_cov = 0.0
        branch_cov = 0.0

        if total_line_covered + total_line_missed > 0:
            line_cov = (total_line_covered / (total_line_covered + total_line_missed)) * 100

        if total_branch_covered + total_branch_missed > 0:
            branch_cov = (total_branch_covered / (total_branch_covered + total_branch_missed)) * 100

        # Log results with detailed diagnostics
        if files_parsed > 0:
            self.logger.info(f"{profile_prefix}✓ CSV parsing succeeded: {line_cov:.1f}% line, {branch_cov:.1f}% branch coverage from {files_parsed} file(s), {rows_matched} rows")
        else:
            self.logger.warning(f"{profile_prefix}✗ No CSV files found or successfully parsed")

        # Validation: warn if we found CSV files but got 0% coverage
        if files_parsed > 0 and line_cov == 0 and branch_cov == 0 and rows_matched == 0:
            if profile and rows_skipped > 0:
                self.logger.error(f"{profile_prefix}VALIDATION FAILURE: Found {files_parsed} CSV file(s) with {rows_skipped} rows, but profile filtering returned 0 matches. This indicates a module naming mismatch.")
            else:
                self.logger.warning(f"{profile_prefix}VALIDATION WARNING: CSV files exist but contain no coverage data. JaCoCo may not be configured or tests may not have run.")

        return (line_cov, branch_cov)

    def _extract_coverage_from_html(self, service: str, base_path: Path) -> tuple[int, int]:
        """
        Extract coverage data from JaCoCo HTML reports (DEPRECATED - use CSV).

        HTML parsing is fragile and version-dependent. Use CSV parsing instead.
        Returns (line_coverage_percent, branch_coverage_percent).
        """
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
            if not report_path.exists():
                continue

            try:
                self.logger.debug(f"[{service}] Found HTML report: {report_path}")
                content = report_path.read_text(encoding='utf-8')

                # Parse JaCoCo HTML - extract from "X of Y" format in bar cells
                total_section = re.search(r'<tfoot>.*?</tfoot>', content, re.DOTALL)
                if total_section:
                    tfoot_html = total_section.group()

                    # Extract all "X of Y" patterns from bar cells
                    bar_matches = re.findall(r'class="bar">(\d+(?:,\d+)?) of (\d+(?:,\d+)?)</td>', tfoot_html)

                    if len(bar_matches) >= 2:
                        # Parse branches
                        branch_missed = int(bar_matches[1][0].replace(',', ''))
                        branch_total = int(bar_matches[1][1].replace(',', ''))
                        branch_covered = branch_total - branch_missed
                        branch_cov = int((branch_covered / branch_total) * 100) if branch_total > 0 else 0

                        # Extract all ctr1 values (missed counts)
                        ctr1_values = re.findall(r'class="ctr1">(\d+(?:,\d+)?)</td>', tfoot_html)
                        # Extract all non-percentage ctr2 values (total counts)
                        ctr2_all = re.findall(r'class="ctr2">(\d+(?:,\d+)?)</td>', tfoot_html)
                        ctr2_values = [v for v in ctr2_all if not v.endswith('%') and '%' not in v]

                        # Lines should be: ctr1[1] (missed), ctr2[1] (total)
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
                            self.logger.debug(f"[{service}] HTML parsing succeeded: {line_cov}% line, {branch_cov}% branch")
                            return (line_cov, branch_cov)

            except Exception as e:
                self.logger.debug(f"[{service}] Failed to parse HTML at {report_path}: {e}")
                continue

        self.logger.debug(f"[{service}] No HTML files found or parsed")
        return (0, 0)

    def _extract_coverage_from_reports(self):
        """
        Extract coverage data from JaCoCo reports (post-processing).

        Prioritizes CSV parsing (stable, reliable) with HTML fallback (deprecated).
        If multiple profiles specified, extracts coverage for each profile separately.
        """
        for service in self.services:
            # Look for JaCoCo report in multiple possible locations
            search_paths = [
                Path.cwd() / "repos" / service,
                Path.cwd() / service,
            ]

            # Find valid base path
            base_path = None
            for path in search_paths:
                if path.exists():
                    base_path = path
                    break

            if not base_path:
                self.logger.warning(f"[{service}] No valid path found for coverage extraction")
                continue

            self.logger.debug(f"[{service}] Searching for coverage reports in: {base_path}")

            # Pre-flight validation: Check if coverage reports exist
            if not self._verify_coverage_generated(service, base_path):
                # Mark all profiles as having no coverage data
                if len(self.profiles) > 1:
                    for profile in self.profiles:
                        self.tracker.update(
                            service, "test_success", "No coverage plugin",
                            profile=profile, coverage_line=0, coverage_branch=0
                        )
                    self.tracker._aggregate_profile_data(service)
                else:
                    # Preserve existing status (don't overwrite test_failed with test_success)
                    current_status = self.tracker.services[service]["status"]
                    self.tracker.update(
                        service, current_status, "No coverage plugin",
                        phase="coverage", coverage_line=0, coverage_branch=0
                    )
                continue

            if len(self.profiles) > 1:
                # Multi-profile mode: extract coverage for each profile
                for profile in self.profiles:
                    line_cov, branch_cov = self._extract_coverage_from_csv(service, base_path, profile=profile)

                    if line_cov > 0 or branch_cov > 0:
                        self.logger.info(f"[{service}:{profile}] CSV parsing succeeded: {line_cov:.1f}% line, {branch_cov:.1f}% branch")
                        self.tracker.update(
                            service,
                            "test_success",
                            f"Coverage: {int(line_cov)}%/{int(branch_cov)}%",
                            profile=profile,
                            coverage_line=int(line_cov),
                            coverage_branch=int(branch_cov),
                        )
                    else:
                        # No coverage data found - update tracker with 0% to mark coverage phase as complete
                        self.logger.warning(f"[{service}:{profile}] No coverage data found for profile")
                        self.tracker.update(
                            service,
                            "test_success",
                            "No coverage",
                            profile=profile,
                            coverage_line=0,
                            coverage_branch=0,
                        )

                # Aggregate profile data to service level
                self.tracker._aggregate_profile_data(service)

            else:
                # Single-profile mode (original behavior)
                if self.tracker.services[service]["coverage_line"] > 0:
                    continue  # Already have coverage data

                # PRIORITY 1: Try CSV extraction (stable, reliable)
                line_cov, branch_cov = self._extract_coverage_from_csv(service, base_path)

                if line_cov > 0 or branch_cov > 0:
                    self.logger.info(f"[{service}] CSV parsing succeeded: {line_cov:.1f}% line, {branch_cov:.1f}% branch")
                    self.tracker.update(
                        service,
                        self.tracker.services[service]["status"],  # Keep current status
                        f"Coverage: {int(line_cov)}%/{int(branch_cov)}%",
                        phase="coverage",
                        coverage_line=int(line_cov),
                        coverage_branch=int(branch_cov),
                    )
                else:
                    # PRIORITY 2: Fallback to HTML parsing (deprecated, fragile)
                    self.logger.warning(f"[{service}] CSV parsing returned 0% coverage, falling back to HTML parsing (deprecated)")
                    line_cov_html, branch_cov_html = self._extract_coverage_from_html(service, base_path)

                    if line_cov_html > 0 or branch_cov_html > 0:
                        self.logger.warning(f"[{service}] HTML parsing succeeded (deprecated): {line_cov_html}% line, {branch_cov_html}% branch")
                        self.tracker.update(
                            service,
                            self.tracker.services[service]["status"],  # Keep current status
                            f"Coverage: {line_cov_html}%/{branch_cov_html}%",
                            phase="coverage",
                            coverage_line=line_cov_html,
                            coverage_branch=branch_cov_html,
                        )
                    else:
                        # No coverage data found - update tracker with 0% to mark coverage phase as complete
                        self.logger.warning(f"[{service}] Both CSV and HTML parsing failed to extract coverage")
                        self.tracker.update(
                            service,
                            self.tracker.services[service]["status"],  # Keep current status
                            "No coverage",
                            phase="coverage",
                            coverage_line=0,
                            coverage_branch=0,
                        )

    def _assess_profile_coverage(self, line_cov: int, branch_cov: int, profile: str = None) -> tuple:
        """Assess coverage quality for a profile or service.

        Args:
            line_cov: Line coverage percentage
            branch_cov: Branch coverage percentage
            profile: Profile name (for profile-specific recommendations)

        Returns:
            Tuple of (grade, label, recommendations)
        """
        # Determine quality grade
        # Don't grade if no coverage data (likely missing plugin or no tests)
        if line_cov == 0 and branch_cov == 0:
            grade = None
            label = "No Coverage Data"
        elif line_cov >= 90 and branch_cov >= 85:
            grade = "A"
            label = "Excellent"
        elif line_cov >= 80 and branch_cov >= 70:
            grade = "B"
            label = "Good"
        elif line_cov >= 70 and branch_cov >= 60:
            grade = "C"
            label = "Acceptable"
        elif line_cov >= 60 and branch_cov >= 50:
            grade = "D"
            label = "Needs Improvement"
        else:
            grade = "F"
            label = "Poor"

        # Generate recommendations
        recommendations = []
        profile_context = f" in {profile}" if profile else ""

        if line_cov == 0 and branch_cov == 0:
            recommendations.append({
                "priority": 1,
                "action": f"Ensure JaCoCo is configured for {profile} module" if profile else "Ensure JaCoCo Maven plugin is configured in pom.xml",
                "expected_improvement": "Enable coverage reporting"
            })
            recommendations.append({
                "priority": 2,
                "action": f"Verify tests are being executed during Maven build{profile_context}",
                "expected_improvement": "Generate coverage data"
            })
        else:
            if branch_cov < line_cov - 15:
                recommendations.append({
                    "priority": 1,
                    "action": f"Improve branch coverage by testing edge cases{profile_context}",
                    "expected_improvement": f"+{min(10, line_cov - branch_cov)}% branch coverage"
                })

            if line_cov < 80:
                recommendations.append({
                    "priority": 1 if not recommendations else 2,
                    "action": f"Add unit tests for uncovered methods and classes{profile_context}",
                    "expected_improvement": f"+{min(15, 80 - line_cov)}% line coverage"
                })

            if line_cov >= 80 and branch_cov < 80:
                recommendations.append({
                    "priority": len(recommendations) + 1,
                    "action": f"Focus on testing complex conditional logic{profile_context}",
                    "expected_improvement": "Better branch coverage"
                })

            if grade in ["A", "B"] and len(recommendations) == 0:
                recommendations.append({
                    "priority": 1,
                    "action": f"Maintain current coverage levels with new code{profile_context}",
                    "expected_improvement": "Sustained quality"
                })

        return (grade, label, recommendations[:3])

    def _assess_coverage_quality(self):
        """Assess coverage quality based on coverage metrics."""
        for service in self.services:
            if len(self.profiles) > 1:
                # Multi-profile mode: assess each profile individually
                for profile in self.profiles:
                    profile_data = self.tracker.services[service]["profiles"][profile]
                    line_cov = profile_data.get("coverage_line", 0)
                    branch_cov = profile_data.get("coverage_branch", 0)

                    grade, label, recommendations = self._assess_profile_coverage(line_cov, branch_cov, profile=profile)

                    # Update profile data
                    self.tracker.update(
                        service,
                        "test_success",
                        f"Grade {grade}: {label}",
                        profile=profile,
                        quality_grade=grade,
                        quality_label=label,
                        recommendations=recommendations,
                    )

                # Re-aggregate after assessment
                self.tracker._aggregate_profile_data(service)

                # Set service-level summary
                worst_grade = self.tracker.services[service].get("quality_grade", "F")
                self.tracker.services[service]["quality_summary"] = f"Profile grades vary - worst: {worst_grade}"

            else:
                # Single-profile mode (original behavior)
                line_cov = self.tracker.services[service]["coverage_line"]
                branch_cov = self.tracker.services[service]["coverage_branch"]

                grade, label, recommendations = self._assess_profile_coverage(line_cov, branch_cov)

                # Store assessment results
                self.tracker.services[service]["quality_grade"] = grade
                self.tracker.services[service]["quality_label"] = label

                # Set quality summary based on grade
                if line_cov == 0 and branch_cov == 0:
                    summary = "No coverage data detected. Ensure JaCoCo plugin is properly configured."
                elif grade == "A":
                    summary = "Outstanding test coverage with all critical paths well-tested."
                elif grade == "B":
                    summary = "Good test coverage with most critical paths tested."
                elif grade == "C":
                    summary = "Acceptable coverage but room for improvement."
                elif grade == "D":
                    summary = "Coverage is below recommended levels. Consider adding more tests."
                else:
                    summary = "Critical gaps in test coverage. Immediate attention needed."

                self.tracker.services[service]["quality_summary"] = summary
                self.tracker.services[service]["recommendations"] = recommendations

    def get_profile_breakdown_panel(self) -> Panel:
        """Generate profile breakdown panel with hierarchical display.

        Returns:
            Rich Panel with hierarchical table showing service (total) and profile rows
        """
        from rich.table import Table
        from rich.text import Text

        # Create table
        table = Table(show_header=True, header_style="bold", box=None, expand=True)
        table.add_column("Service", style="cyan", width=25)
        table.add_column("Provider", style="blue", width=15)
        table.add_column("Result", style="white", width=20)
        table.add_column("Grade", justify="center", width=7)
        table.add_column("Recommendation", style="white")

        # Track overall worst grade for border color
        worst_grade_value = 6
        grade_values = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}

        service_count = 0
        total_services = len(self.tracker.services)

        for service, data in self.tracker.services.items():
            service_count += 1
            # Get service-level metrics
            svc_line_cov = data["coverage_line"]
            svc_branch_cov = data["coverage_branch"]
            svc_grade = data.get("quality_grade")

            if svc_grade and grade_values.get(svc_grade, 0) < worst_grade_value:
                worst_grade_value = grade_values[svc_grade]

            # Determine service-level result with better failure visibility
            if data["status"] == "test_failed" or data["tests_failed"] > 0:
                # Show test failures prominently
                passed = data["tests_run"] - data["tests_failed"]
                result_text = Text(f"{data['tests_failed']} failed / {passed} passed", style="red bold")
                svc_grade_text = Text("FAIL", style="red bold")
                svc_rec = "Fix test failures"
            elif data["status"] == "compile_failed":
                result_text = Text("Compile Failed", style="red bold")
                svc_grade_text = Text("—", style="dim")
                svc_rec = "Fix compilation errors"
            elif svc_grade:
                # All tests passed, show coverage (no test count or "cov" suffix - already clear from context)
                result_text = Text(f"{svc_line_cov}%/{svc_branch_cov}%",
                                 style="green" if svc_grade in ["A", "B"] else "yellow" if svc_grade == "C" else "orange1")
                grade_style = {"A": "green bold", "B": "blue bold", "C": "yellow bold",
                              "D": "red bold", "F": "red bold"}.get(svc_grade, "white")
                svc_grade_text = Text(svc_grade, style=grade_style)
                svc_rec = data.get("quality_label", "")
            else:
                result_text = Text("Pending", style="dim")
                svc_grade_text = Text("—", style="dim")
                svc_rec = ""

            # Add service (total) row
            table.add_row(
                f"[bold]{service} (total)[/bold]",
                "",  # No provider for total row
                result_text,
                svc_grade_text,
                svc_rec
            )

            # Add profile rows
            profiles = data.get("profiles", {})
            if profiles:
                # Show profiles in standard order
                profile_order = ["core", "core-plus", "azure", "aws", "gc", "ibm", "testing"]
                for profile_name in profile_order:
                    if profile_name not in profiles:
                        continue

                    profile_data = profiles[profile_name]
                    p_tests_run = profile_data.get("tests_run", 0)
                    p_tests_failed = profile_data.get("tests_failed", 0)
                    p_line_cov = profile_data.get("coverage_line", 0)
                    p_branch_cov = profile_data.get("coverage_branch", 0)
                    p_grade = profile_data.get("quality_grade")

                    # Display name: convert "core-plus" to "core+" for shorter display
                    profile_display = "core+" if profile_name == "core-plus" else profile_name

                    # Track worst grade
                    if p_grade and grade_values.get(p_grade, 0) < worst_grade_value:
                        worst_grade_value = grade_values[p_grade]

                    # Format profile result with failure info
                    if p_tests_failed > 0:
                        # Profile has test failures
                        p_passed = p_tests_run - p_tests_failed
                        p_result = Text(f"{p_tests_failed}/{p_tests_run} failed", style="red")
                        p_grade_text = Text("FAIL", style="red")
                        p_rec = "Fix test failures in this profile"
                    elif p_tests_run == 0 and p_line_cov == 0 and p_branch_cov == 0:
                        # No data for this profile
                        p_result = Text("No data", style="dim")
                        p_grade_text = Text("—", style="dim")
                        p_rec = profile_data.get("quality_label", "") if profile_data.get("quality_label") else ""
                    elif p_grade:
                        # Tests passed, show coverage only (test count in Status table)
                        p_result = Text(f"{p_line_cov}%/{p_branch_cov}%",
                                      style="green" if p_grade in ["A", "B"] else "yellow" if p_grade == "C" else "orange1")
                        p_grade_style = {"A": "green", "B": "blue", "C": "yellow",
                                        "D": "red", "F": "red"}.get(p_grade, "white")
                        p_grade_text = Text(p_grade, style=p_grade_style)

                        # Get first recommendation
                        p_recs = profile_data.get("recommendations", [])
                        if p_recs:
                            p_rec = p_recs[0].get("action", "")
                            if len(p_rec) > 50:
                                p_rec = p_rec[:47] + "..."
                        else:
                            p_rec = profile_data.get("quality_label", "")
                    else:
                        p_result = Text("No data", style="dim")
                        p_grade_text = Text("—", style="dim")
                        p_rec = ""

                    table.add_row(
                        f"  ↳ {profile_display}",
                        profile_display,
                        p_result,
                        p_grade_text,
                        p_rec
                    )

            # Add blank separator row between services (but not after the last service)
            if service_count < total_services:
                table.add_row("", "", "", "", "")

        # Calculate summary statistics
        total_tests = 0
        total_failed = 0
        total_passed = 0

        for service_data in self.tracker.services.values():
            total_tests += service_data["tests_run"]
            total_failed += service_data["tests_failed"]

        total_passed = total_tests - total_failed

        # Determine border color based on failures and worst grade
        if total_failed > 0:
            border_color = "red"
        else:
            border_color_map = {5: "green", 4: "blue", 3: "yellow", 2: "orange1", 1: "red"}
            border_color = border_color_map.get(worst_grade_value, "cyan")

        # Build subtitle with test summary
        profile_info = f"{len(self.services)} service{'s' if len(self.services) > 1 else ''} × {len(self.profiles)} profiles"

        if total_tests > 0:
            if total_failed > 0:
                test_summary = f"{total_failed} failed / {total_passed} passed / {total_tests} total"
            else:
                test_summary = f"All {total_tests} tests passed"
            subtitle = f"{profile_info} | {test_summary}"
        else:
            subtitle = profile_info

        return Panel(
            table,
            title="📊 Test Results",
            subtitle=subtitle,
            border_style=border_color,
            padding=(1, 2)
        )

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
                # Show coverage if we have a quality grade (even if 0%)
                # This ensures consistent display and explains the grade
                if data.get("quality_grade"):
                    result = f"Cov: {data['coverage_line']}%/{data['coverage_branch']}%"
                    result_style = "green"
                elif data["tests_run"] > 0:
                    # Fallback to test count only if no grade assigned
                    result = f"Passed ({data['tests_run']} tests)"
                    result_style = "green"
                else:
                    # No tests and no coverage
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
                self.tracker.provider,
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
        """Save execution log to file (append mode to preserve FileHandler debug logs)"""
        try:
            with open(self.log_file, "a") as f:
                f.write(f"{'='*70}\n")
                f.write("Maven Test Execution Log\n")
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
                            f.write("  Recommendations:\n")
                            for rec in data["recommendations"][:5]:
                                f.write(f"    - {rec.get('action', 'N/A')}")
                                if rec.get("expected_improvement"):
                                    f.write(f" ({rec['expected_improvement']})")
                                f.write("\n")

                    # Add profile breakdown if multiple profiles
                    profiles = data.get("profiles", {})
                    if profiles:
                        f.write("\n  Profile Breakdown:\n")
                        for profile_name in ["core", "core-plus", "azure", "aws", "gc", "ibm", "testing"]:
                            if profile_name not in profiles:
                                continue
                            profile_data = profiles[profile_name]
                            f.write(f"    {profile_name}:\n")
                            f.write(f"      Tests Run: {profile_data.get('tests_run', 0)}\n")
                            f.write(f"      Tests Failed: {profile_data.get('tests_failed', 0)}\n")
                            f.write(f"      Coverage Line: {profile_data.get('coverage_line', 0)}%\n")
                            f.write(f"      Coverage Branch: {profile_data.get('coverage_branch', 0)}%\n")
                            if profile_data.get("quality_grade"):
                                f.write(f"      Quality Grade: {profile_data['quality_grade']} - {profile_data.get('quality_label', 'N/A')}\n")
                                if profile_data.get("recommendations"):
                                    f.write("      Recommendations:\n")
                                    for rec in profile_data["recommendations"][:3]:
                                        f.write(f"        - {rec.get('action', 'N/A')}")
                                        if rec.get("expected_improvement"):
                                            f.write(f" ({rec['expected_improvement']})")
                                        f.write("\n")

                    f.write("\n")

                f.write("\n=== FULL OUTPUT ===\n\n")
                f.write("\n".join(self.full_output))

            console.print(f"\n[dim]✓ Log saved to: {self.log_file}[/dim]")
        except Exception as e:
            console.print(f"[dim]Warning: Could not save log: {e}[/dim]")

    def get_results_panel(self, return_code: int) -> Panel:
        """Generate final results panel.

        Args:
            return_code: Process return code

        Returns:
            Rich Panel with test results (hierarchical if multiple profiles, flat otherwise)
        """
        # If multiple profiles, use hierarchical breakdown panel
        if len(self.profiles) > 1:
            return self.get_profile_breakdown_panel()
        else:
            # Single profile: use original quality panel
            return self.get_quality_panel()
