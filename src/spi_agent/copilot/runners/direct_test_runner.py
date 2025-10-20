"""Direct test runner for executing Maven tests without AI intermediary."""

import asyncio
import logging
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from spi_agent.copilot.base.runner import console
from spi_agent.copilot.config import config
from spi_agent.copilot.trackers import TestTracker

# Maximum depth for recursive JaCoCo CSV discovery
JACOCO_CSV_MAX_SEARCH_DEPTH = 8

logger = logging.getLogger(__name__)


class DirectTestRunner:
    """Direct Maven test execution with parallel processing."""

    def __init__(
        self,
        services: List[str],
        provider: str = "core,core-plus,azure",
    ):
        self.services = services
        self.provider = provider
        self.profiles = self._parse_provider_to_profiles(provider)
        self.tracker = TestTracker(services, provider, profiles=self.profiles if len(self.profiles) > 1 else [])

        # Track current module being built (for per-profile test count parsing)
        self.current_module = None

    def _parse_provider_to_profiles(self, provider: str) -> List[str]:
        """Parse provider string into list of profiles."""
        if provider.lower() == "all":
            return ["core", "core-plus", "azure", "aws", "gc", "ibm"]
        elif "," in provider:
            return [p.strip().lower() for p in provider.split(",")]
        else:
            return [provider.strip().lower()]

    def _extract_profile_from_module(self, module_name: str) -> str:
        """Extract profile name from Maven module name."""
        module_lower = module_name.lower()

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

    def show_config(self):
        """Display run configuration."""
        if len(self.profiles) > 1:
            profiles_display = [p if p != "core-plus" else "core+" for p in self.profiles]
            profiles_str = ', '.join(profiles_display)
            config_text = f"""[cyan]Services:[/cyan]   {', '.join(self.services)}
[cyan]Profiles:[/cyan]   {profiles_str}"""
        else:
            provider_display = self.provider.replace("core-plus", "core+")
            config_text = f"""[cyan]Services:[/cyan]   {', '.join(self.services)}
[cyan]Provider:[/cyan]   {provider_display}"""

        console.print(Panel(config_text, title="🧪 Maven Test Execution", border_style="blue"))
        console.print()

    async def _run_maven_command(
        self,
        cmd: List[str],
        cwd: Path,
        service: str,
        phase: str,
        timeout: int = 600
    ) -> Tuple[int, str]:
        """Execute Maven command and capture output.

        Args:
            cmd: Maven command to execute
            cwd: Working directory
            service: Service name for tracking
            phase: Build phase (compile, test)
            timeout: Command timeout in seconds

        Returns:
            Tuple of (return_code, output)
        """
        logger.info(f"[{service}] Executing {phase}: {' '.join(cmd)}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL,
            )

            output_lines = []

            # Read output line by line
            if process.stdout:
                async for line_bytes in process.stdout:
                    line = line_bytes.decode('utf-8', errors='replace').rstrip()
                    output_lines.append(line)

                    # Parse Maven output for module tracking
                    if phase == "test":
                        self._parse_maven_output(service, line)

            # Wait for completion
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(f"[{service}] {phase} timed out after {timeout}s")
                process.kill()
                await process.wait()
                return (-1, "\n".join(output_lines))

            return_code = process.returncode
            output = "\n".join(output_lines)

            logger.info(f"[{service}] {phase} completed with code {return_code}")
            return (return_code, output)

        except Exception as e:
            logger.error(f"[{service}] Error executing {phase}: {e}", exc_info=True)
            return (-1, str(e))

    def _parse_maven_output(self, service: str, line: str):
        """Parse Maven output for progress tracking."""
        # Track current module for profile mapping
        building_match = re.search(r'\[INFO\]\s+Building\s+([\w\-]+)', line)
        if building_match:
            self.current_module = building_match.group(1)
            logger.debug(f"[{service}] Detected Maven module: {self.current_module}")

    def _count_tests_from_surefire(
        self,
        service: str,
        base_path: Path,
        profile: str = None
    ) -> Tuple[int, int]:
        """Count tests by parsing surefire-reports/*.xml files.

        Args:
            service: Service name
            base_path: Base path to search for surefire reports
            profile: Optional profile name to filter by module

        Returns:
            Tuple of (tests_run, tests_failed)
        """
        tests_run = 0
        tests_failed = 0

        profile_prefix = f"[{service}:{profile}] " if profile else f"[{service}] "

        # Map profile to module directories
        if profile:
            module_dirs = self._map_profile_to_modules(service, base_path, profile)
        else:
            # Get all modules
            module_dirs = [base_path]
            for provider_dir_name in ["provider", "providers"]:
                provider_dir = base_path / provider_dir_name
                if provider_dir.exists():
                    for item in provider_dir.iterdir():
                        if item.is_dir():
                            module_dirs.append(item)
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

                    tests = int(root.get('tests', 0))
                    failures = int(root.get('failures', 0))
                    errors = int(root.get('errors', 0))

                    tests_run += tests
                    tests_failed += failures + errors

                    logger.debug(f"{profile_prefix}Parsed {xml_file.name}: {tests} tests, {failures + errors} failed")

                except Exception as e:
                    logger.warning(f"{profile_prefix}Failed to parse {xml_file}: {e}")
                    continue

        if xml_files_found > 0:
            logger.info(f"{profile_prefix}Surefire XML parsing: {tests_run} tests run, {tests_failed} failed from {xml_files_found} file(s)")
        else:
            logger.debug(f"{profile_prefix}No surefire XML reports found")

        return (tests_run, tests_failed)

    def _map_profile_to_modules(self, service: str, base_path: Path, profile: str) -> List[Path]:
        """Map a profile to its corresponding Maven module directories."""
        module_paths = []
        profile_lower = profile.lower()
        profile_normalized = profile_lower.replace("-", "")

        logger.debug(f"[{service}:{profile}] Mapping profile to module directories in {base_path}")

        # Pattern 1: {service}-{profile}/
        direct_module = base_path / f"{service}-{profile}"
        if direct_module.exists() and direct_module.is_dir():
            logger.debug(f"[{service}:{profile}] Found direct module: {direct_module.name}")
            module_paths.append(direct_module)

        # Pattern 2: providers/{service}-{profile}/
        providers_module = base_path / "providers" / f"{service}-{profile}"
        if providers_module.exists() and providers_module.is_dir():
            logger.debug(f"[{service}:{profile}] Found providers module: {providers_module.name}")
            module_paths.append(providers_module)

        # Pattern 3: provider/{service}-{profile}/
        provider_module = base_path / "provider" / f"{service}-{profile}"
        if provider_module.exists() and provider_module.is_dir():
            logger.debug(f"[{service}:{profile}] Found provider module: {provider_module.name}")
            module_paths.append(provider_module)

        # Pattern 4: Check all subdirectories for matching names
        for item in base_path.iterdir():
            if not item.is_dir() or item.name in ["target", "src", ".git", "provider", "providers"]:
                continue

            item_normalized = item.name.lower().replace("-", "")

            if profile == "core-plus":
                if "coreplus" in item_normalized or "core-plus" in item.name.lower():
                    if item not in module_paths:
                        logger.debug(f"[{service}:{profile}] Found matching module: {item.name}")
                        module_paths.append(item)
            elif profile == "core":
                if "core" in item_normalized and "coreplus" not in item_normalized:
                    if item not in module_paths:
                        logger.debug(f"[{service}:{profile}] Found matching module: {item.name}")
                        module_paths.append(item)
            else:
                if profile_normalized in item_normalized:
                    if item not in module_paths:
                        logger.debug(f"[{service}:{profile}] Found matching module: {item.name}")
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
                            logger.debug(f"[{service}:{profile}] Found provider submodule: {item.name}")
                            module_paths.append(item)
                elif profile == "core":
                    if "core" in item_normalized and "coreplus" not in item_normalized:
                        if item not in module_paths:
                            logger.debug(f"[{service}:{profile}] Found provider submodule: {item.name}")
                            module_paths.append(item)
                else:
                    if profile_normalized in item_normalized:
                        if item not in module_paths:
                            logger.debug(f"[{service}:{profile}] Found provider submodule: {item.name}")
                            module_paths.append(item)

        if module_paths:
            logger.info(f"[{service}:{profile}] Mapped profile to {len(module_paths)} module(s): {[p.name for p in module_paths]}")
        else:
            logger.warning(f"[{service}:{profile}] No module directories found for profile")

        return module_paths

    async def test_service(self, service: str) -> Dict:
        """Execute Maven tests for a single service.

        Args:
            service: Service name to test

        Returns:
            Dict with test results
        """
        logger.info(f"[{service}] Starting test execution")

        # Locate service directory
        base_path = Path.cwd() / "repos" / service
        if not base_path.exists():
            base_path = Path.cwd() / service

        if not base_path.exists():
            error_msg = "Service directory not found"
            logger.error(f"[{service}] {error_msg}")
            self.tracker.update(service, "error", error_msg)
            return {"service": service, "status": "error", "message": error_msg}

        pom_path = base_path / "pom.xml"
        if not pom_path.exists():
            error_msg = "No pom.xml found"
            logger.error(f"[{service}] {error_msg}")
            self.tracker.update(service, "error", error_msg)
            return {"service": service, "status": "error", "message": error_msg}

        # Build Maven profile args
        profile_args = f"-P{','.join(self.profiles)}"

        try:
            # Phase 1: Compile
            self.tracker.update(service, "compiling", "Compiling", phase="compile")
            compile_cmd = ["mvn", "clean", "compile", profile_args]
            compile_code, compile_output = await self._run_maven_command(
                compile_cmd, base_path, service, "compile", timeout=600
            )

            if compile_code != 0:
                self.tracker.update(service, "compile_failed", "Failed", phase="compile")
                return {"service": service, "status": "compile_failed", "message": "Compilation failed"}

            self.tracker.update(service, "compile_success", "Compiled", phase="compile")

            # Phase 2: Test
            self.tracker.update(service, "testing", "Testing", phase="test")
            test_cmd = ["mvn", "test", profile_args, "-DskipITs"]
            test_code, test_output = await self._run_maven_command(
                test_cmd, base_path, service, "test", timeout=900
            )

            # Parse test results from surefire reports (deterministic)
            if len(self.profiles) > 1:
                # Multi-profile: count per profile
                for profile in self.profiles:
                    tests_run, tests_failed = self._count_tests_from_surefire(service, base_path, profile=profile)
                    status = "test_failed" if tests_failed > 0 else "test_success"
                    self.tracker.update(
                        service, status, f"{tests_run} tests",
                        phase="test", profile=profile,
                        tests_run=tests_run, tests_failed=tests_failed
                    )

                # Aggregate profile data
                self.tracker._aggregate_profile_data(service)
            else:
                # Single profile: count all
                tests_run, tests_failed = self._count_tests_from_surefire(service, base_path)
                status = "test_failed" if tests_failed > 0 else "test_success"
                self.tracker.update(
                    service, status, f"{tests_run} tests",
                    phase="test", tests_run=tests_run, tests_failed=tests_failed
                )

            return {
                "service": service,
                "status": "success" if test_code == 0 and tests_failed == 0 else "test_failed",
                "tests_run": self.tracker.services[service]["tests_run"],
                "tests_failed": self.tracker.services[service]["tests_failed"]
            }

        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            logger.error(f"[{service}] {error_msg}", exc_info=True)
            self.tracker.update(service, "error", error_msg)
            return {"service": service, "status": "error", "message": error_msg}

    def _generate_coverage_for_service(self, service: str) -> Tuple[bool, str]:
        """Generate coverage reports for a single service."""
        base_path = Path.cwd() / "repos" / service
        if not base_path.exists():
            base_path = Path.cwd() / service

        if not base_path.exists():
            msg = "Service directory not found"
            logger.warning(f"[{service}] {msg}")
            return (False, msg)

        pom_path = base_path / "pom.xml"
        if not pom_path.exists():
            msg = "No pom.xml found"
            logger.warning(f"[{service}] {msg}")
            return (False, msg)

        try:
            pom_content = pom_path.read_text(encoding='utf-8')
        except Exception as exc:
            pom_content = ""
            logger.debug(f"[{service}] Failed to read pom.xml: {exc}")

        has_root_jacoco = "jacoco-maven-plugin" in pom_content

        # Identify module directories for each requested profile
        modules_by_profile: Dict[str, List[Path]] = {}
        for profile in self.profiles:
            try:
                module_dirs = self._map_profile_to_modules(service, base_path, profile)
            except Exception as exc:
                logger.debug(f"[{service}] Failed mapping profile '{profile}': {exc}")
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
                logger.warning(f"[{service}] {msg}")
                return (False, msg)

        coverage_timeout = 60
        success_modules: List[str] = []
        failed_modules: List[str] = []
        failure_messages: List[str] = []

        for module_dir, profiles in modules_to_process.items():
            module_rel = (
                module_dir.relative_to(base_path).as_posix()
                if module_dir != base_path else "."
            )
            profile_label = ",".join(sorted(profiles)) if profiles else "all"
            logger.info(
                f"[{service}] Generating coverage for module {module_rel} (profiles: {profile_label})"
            )

            cmd = ["mvn", "jacoco:report", "-DskipTests"]
            logger.debug(f"[{service}] Command ({module_rel}): {' '.join(cmd)}")

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
                    logger.info(
                        f"[{service}] ✓ Coverage generation succeeded for module {module_rel}"
                    )
                    if "BUILD SUCCESS" in result.stdout:
                        logger.debug(
                            f"[{service}] {module_rel}: Maven reported BUILD SUCCESS"
                        )
                    success_modules.append(module_rel)
                else:
                    stderr_preview = result.stderr[:500] if result.stderr else "No stderr"
                    msg = (
                        f"{module_rel} failed (exit code {result.returncode}) - {stderr_preview}"
                    )
                    logger.error(f"[{service}] ✗ {msg}")
                    if result.stdout:
                        logger.debug(f"[{service}] {module_rel} stdout:\n{result.stdout}")
                    if result.stderr:
                        logger.debug(f"[{service}] {module_rel} stderr:\n{result.stderr}")
                    failed_modules.append(module_rel)
                    failure_messages.append(msg)

            except subprocess.TimeoutExpired:
                msg = f"{module_rel} timed out after {coverage_timeout}s"
                logger.error(f"[{service}] ✗ {msg}")
                failed_modules.append(module_rel)
                failure_messages.append(msg)

            except FileNotFoundError:
                msg = "Maven command not found"
                logger.error(f"[{service}] ✗ {msg}")
                return (False, msg)

            except Exception as exc:
                msg = f"{module_rel} unexpected error: {exc}"
                logger.error(f"[{service}] ✗ {msg}")
                import traceback
                logger.debug(f"[{service}] Traceback:\n{traceback.format_exc()}")
                failed_modules.append(module_rel)
                failure_messages.append(msg)

        if success_modules:
            summary = f"{len(success_modules)}/{len(modules_to_process)} module(s) generated coverage"
            if len(success_modules) <= 3:
                summary += f" ({', '.join(success_modules)})"
            return (True, summary)

        msg = failure_messages[0] if failure_messages else "Coverage generation failed"
        return (False, msg)

    def _find_all_jacoco_csvs(self, service: str, base_path: Path) -> List[Tuple[Path, str]]:
        """Recursively find jacoco.csv files under base_path."""
        csv_files: List[Tuple[Path, str]] = []
        seen: Set[Path] = set()

        for csv_path in base_path.rglob("jacoco.csv"):
            if csv_path in seen:
                continue
            seen.add(csv_path)

            relative = csv_path.relative_to(base_path)

            if len(relative.parts) > JACOCO_CSV_MAX_SEARCH_DEPTH:
                logger.debug(f"[{service}] Skipping {csv_path} (exceeds depth limit)")
                continue

            if "test-classes" in relative.parts:
                logger.debug(f"[{service}] Skipping {csv_path} (test-classes artifact)")
                continue

            module_hint = next(
                (part for part in reversed(relative.parent.parts) if part not in {"target", "site", "jacoco"}),
                relative.parent.name,
            )
            csv_files.append((csv_path, f"discovered:{module_hint}"))

        logger.info(
            f"[{service}] Recursive search found {len(csv_files)} jacoco.csv file(s)"
        )
        return csv_files

    def _extract_coverage_from_csv(
        self,
        service: str,
        base_path: Path,
        profile: str = None
    ) -> Tuple[float, float]:
        """Extract coverage data from JaCoCo CSV reports."""
        profile_prefix = f"[{service}:{profile}] " if profile else f"[{service}] "

        csv_paths = []

        if profile:
            logger.info(f"{profile_prefix}Starting profile-specific coverage extraction")

            module_dirs = self._map_profile_to_modules(service, base_path, profile)

            if module_dirs:
                for module_dir in module_dirs:
                    module_csv = module_dir / "target" / "site" / "jacoco" / "jacoco.csv"
                    if module_csv.exists():
                        csv_paths.append((module_csv, f"module:{module_dir.name}"))
                        logger.debug(f"{profile_prefix}Queued module CSV: {module_csv}")
                    else:
                        logger.warning(f"{profile_prefix}Module {module_dir.name} has no jacoco.csv")

            if not csv_paths:
                logger.warning(f"{profile_prefix}No module-specific CSVs found, trying recursive search")
                all_discovered = self._find_all_jacoco_csvs(service, base_path)

                profile_normalized = profile.lower().replace("-", "")
                for csv_path, source_hint in all_discovered:
                    path_str = str(csv_path).lower()

                    matched = False
                    if profile == "core-plus":
                        if "core-plus" in path_str or "coreplus" in path_str:
                            matched = True
                    elif profile == "core":
                        if "core" in path_str and "coreplus" not in path_str and "core-plus" not in path_str:
                            matched = True
                    else:
                        if profile_normalized in path_str.replace("-", ""):
                            matched = True

                    if matched:
                        csv_paths.append((csv_path, f"discovered:filtered:{source_hint.split(':')[1]}"))
                        logger.info(f"{profile_prefix}Matched discovered CSV: {csv_path}")
        else:
            logger.info(f"{profile_prefix}Starting service-level coverage extraction")

            aggregated_csv = base_path / "target" / "site" / "jacoco" / "jacoco.csv"
            if aggregated_csv.exists():
                csv_paths.append((aggregated_csv, "aggregated"))

            provider_dir = base_path / "provider"
            if provider_dir.exists():
                for subdir in provider_dir.iterdir():
                    if subdir.is_dir():
                        subdir_csv = subdir / "target" / "site" / "jacoco" / "jacoco.csv"
                        if subdir_csv.exists():
                            csv_paths.append((subdir_csv, f"provider:{subdir.name}"))

            for item in base_path.iterdir():
                if item.is_dir() and item.name not in ["target", "src", ".git", "provider", "providers"]:
                    item_csv = item / "target" / "site" / "jacoco" / "jacoco.csv"
                    if item_csv.exists() and (item_csv, f"module:{item.name}") not in csv_paths:
                        csv_paths.append((item_csv, f"module:{item.name}"))

        logger.info(f"{profile_prefix}Found {len(csv_paths)} CSV file(s) to process")

        total_line_covered = 0
        total_line_missed = 0
        total_branch_covered = 0
        total_branch_missed = 0
        files_parsed = 0
        rows_matched = 0

        for csv_path, csv_source in csv_paths:
            try:
                logger.debug(f"{profile_prefix}Processing CSV: {csv_path} (source: {csv_source})")
                content = csv_path.read_text(encoding='utf-8')
                lines = content.strip().split('\n')

                if len(lines) < 2:
                    logger.warning(f"{profile_prefix}CSV file is empty: {csv_path}")
                    continue

                csv_rows_matched = 0

                for i, line in enumerate(lines[1:], start=2):
                    if not line.strip():
                        continue

                    parts = line.split(',')
                    if len(parts) < 9:
                        logger.debug(f"{profile_prefix}Skipping malformed CSV row {i}")
                        continue

                    try:
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
                        logger.debug(f"{profile_prefix}Skipping malformed CSV row {i}: {e}")
                        continue

                files_parsed += 1
                rows_matched += csv_rows_matched

                logger.info(f"{profile_prefix}Parsed {csv_path.name}: {csv_rows_matched} rows")

            except Exception as e:
                logger.error(f"{profile_prefix}Failed to parse CSV at {csv_path}: {e}")
                continue

        # Calculate percentages
        line_cov = 0.0
        branch_cov = 0.0

        if total_line_covered + total_line_missed > 0:
            line_cov = (total_line_covered / (total_line_covered + total_line_missed)) * 100

        if total_branch_covered + total_branch_missed > 0:
            branch_cov = (total_branch_covered / (total_branch_covered + total_branch_missed)) * 100

        if files_parsed > 0:
            logger.info(f"{profile_prefix}Coverage: {line_cov:.1f}% line, {branch_cov:.1f}% branch from {files_parsed} file(s)")
        else:
            logger.warning(f"{profile_prefix}No CSV files parsed")

        return (line_cov, branch_cov)

    def _extract_coverage_from_reports(self):
        """Extract coverage data from JaCoCo reports."""
        for service in self.services:
            search_paths = [
                Path.cwd() / "repos" / service,
                Path.cwd() / service,
            ]

            base_path = None
            for path in search_paths:
                if path.exists():
                    base_path = path
                    break

            if not base_path:
                logger.warning(f"[{service}] No valid path found for coverage extraction")
                continue

            logger.debug(f"[{service}] Searching for coverage reports in: {base_path}")

            if len(self.profiles) > 1:
                for profile in self.profiles:
                    line_cov, branch_cov = self._extract_coverage_from_csv(service, base_path, profile=profile)

                    if line_cov > 0 or branch_cov > 0:
                        self.tracker.update(
                            service,
                            "test_success",
                            f"Coverage: {int(line_cov)}%/{int(branch_cov)}%",
                            profile=profile,
                            coverage_line=int(line_cov),
                            coverage_branch=int(branch_cov),
                        )
                    else:
                        self.tracker.update(
                            service,
                            "test_success",
                            "No coverage",
                            profile=profile,
                            coverage_line=0,
                            coverage_branch=0,
                        )

                self.tracker._aggregate_profile_data(service)

            else:
                if self.tracker.services[service]["coverage_line"] > 0:
                    continue

                line_cov, branch_cov = self._extract_coverage_from_csv(service, base_path)

                if line_cov > 0 or branch_cov > 0:
                    self.tracker.update(
                        service,
                        self.tracker.services[service]["status"],
                        f"Coverage: {int(line_cov)}%/{int(branch_cov)}%",
                        phase="coverage",
                        coverage_line=int(line_cov),
                        coverage_branch=int(branch_cov),
                    )
                else:
                    self.tracker.update(
                        service,
                        self.tracker.services[service]["status"],
                        "No coverage",
                        phase="coverage",
                        coverage_line=0,
                        coverage_branch=0,
                    )

    def _assess_profile_coverage(
        self,
        line_cov: int,
        branch_cov: int,
        profile: str = None
    ) -> Tuple:
        """Assess coverage quality for a profile or service."""
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

        recommendations = []
        profile_context = f" in {profile}" if profile else ""

        if line_cov == 0 and branch_cov == 0:
            recommendations.append({
                "priority": 1,
                "action": f"Ensure JaCoCo is configured for {profile} module" if profile else "Ensure JaCoCo Maven plugin is configured in pom.xml",
                "expected_improvement": "Enable coverage reporting"
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

        return (grade, label, recommendations[:3])

    def _assess_coverage_quality(self):
        """Assess coverage quality based on coverage metrics."""
        for service in self.services:
            if len(self.profiles) > 1:
                for profile in self.profiles:
                    profile_data = self.tracker.services[service]["profiles"][profile]
                    line_cov = profile_data.get("coverage_line", 0)
                    branch_cov = profile_data.get("coverage_branch", 0)

                    grade, label, recommendations = self._assess_profile_coverage(
                        line_cov, branch_cov, profile=profile
                    )

                    self.tracker.update(
                        service,
                        "test_success",
                        f"Grade {grade}: {label}",
                        profile=profile,
                        quality_grade=grade,
                        quality_label=label,
                        recommendations=recommendations,
                    )

                self.tracker._aggregate_profile_data(service)

                worst_grade = self.tracker.services[service].get("quality_grade", "F")
                self.tracker.services[service]["quality_summary"] = f"Profile grades vary - worst: {worst_grade}"

            else:
                line_cov = self.tracker.services[service]["coverage_line"]
                branch_cov = self.tracker.services[service]["coverage_branch"]

                grade, label, recommendations = self._assess_profile_coverage(line_cov, branch_cov)

                self.tracker.services[service]["quality_grade"] = grade
                self.tracker.services[service]["quality_label"] = label

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
        """Generate profile breakdown panel with hierarchical display."""
        from rich.text import Text

        table = Table(show_header=True, header_style="bold", box=None, expand=True)
        table.add_column("Service", style="cyan", width=25)
        table.add_column("Provider", style="blue", width=15)
        table.add_column("Result", style="white", width=20)
        table.add_column("Grade", justify="center", width=7)
        table.add_column("Recommendation", style="white")

        worst_grade_value = 6
        grade_values = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}

        service_count = 0
        total_services = len(self.tracker.services)

        for service, data in self.tracker.services.items():
            service_count += 1
            svc_line_cov = data["coverage_line"]
            svc_branch_cov = data["coverage_branch"]
            svc_grade = data.get("quality_grade")

            if svc_grade and grade_values.get(svc_grade, 0) < worst_grade_value:
                worst_grade_value = grade_values[svc_grade]

            if data["status"] == "test_failed" or data["tests_failed"] > 0:
                passed = data["tests_run"] - data["tests_failed"]
                result_text = Text(f"{data['tests_failed']} failed / {passed} passed", style="red bold")
                svc_grade_text = Text("FAIL", style="red bold")
                svc_rec = "Fix test failures"
            elif data["status"] == "compile_failed":
                result_text = Text("Compile Failed", style="red bold")
                svc_grade_text = Text("—", style="dim")
                svc_rec = "Fix compilation errors"
            elif svc_grade:
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

            table.add_row(
                f"[bold]{service} (total)[/bold]",
                "",
                result_text,
                svc_grade_text,
                svc_rec
            )

            profiles = data.get("profiles", {})
            if profiles:
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

                    profile_display = "core+" if profile_name == "core-plus" else profile_name

                    if p_grade and grade_values.get(p_grade, 0) < worst_grade_value:
                        worst_grade_value = grade_values[p_grade]

                    if p_tests_failed > 0:
                        p_result = Text(f"{p_tests_failed}/{p_tests_run} failed", style="red")
                        p_grade_text = Text("FAIL", style="red")
                        p_rec = "Fix test failures in this profile"
                    elif p_tests_run == 0 and p_line_cov == 0 and p_branch_cov == 0:
                        p_result = Text("No data", style="dim")
                        p_grade_text = Text("—", style="dim")
                        p_rec = profile_data.get("quality_label", "") if profile_data.get("quality_label") else ""
                    elif p_grade:
                        p_result = Text(f"{p_line_cov}%/{p_branch_cov}%",
                                      style="green" if p_grade in ["A", "B"] else "yellow" if p_grade == "C" else "orange1")
                        p_grade_style = {"A": "green", "B": "blue", "C": "yellow",
                                        "D": "red", "F": "red"}.get(p_grade, "white")
                        p_grade_text = Text(p_grade, style=p_grade_style)

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

            if service_count < total_services:
                table.add_row("", "", "", "", "")

        total_tests = 0
        total_failed = 0

        for service_data in self.tracker.services.values():
            total_tests += service_data["tests_run"]
            total_failed += service_data["tests_failed"]

        total_passed = total_tests - total_failed

        if total_failed > 0:
            border_color = "red"
        else:
            border_color_map = {5: "green", 4: "blue", 3: "yellow", 2: "orange1", 1: "red"}
            border_color = border_color_map.get(worst_grade_value, "cyan")

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
        """Generate quality assessment panel with clean columnar layout."""
        table = Table(expand=True, show_header=True, header_style="bold cyan")
        table.add_column("Service", style="cyan", no_wrap=True)
        table.add_column("Provider", style="blue", no_wrap=True)
        table.add_column("Result", style="yellow", no_wrap=True)
        table.add_column("Grade", justify="center", no_wrap=True)
        table.add_column("Recommendation", style="white", ratio=2)

        for service, data in self.tracker.services.items():
            result = "Pending"
            result_style = "dim"

            if data["status"] == "compile_failed":
                result = "Compile Failed"
                result_style = "red"
            elif data["status"] == "test_failed":
                result = f"Failed ({data['tests_failed']}/{data['tests_run']} tests)"
                result_style = "red"
            elif data["status"] == "test_success":
                if data.get("quality_grade"):
                    result = f"Cov: {data['coverage_line']}%/{data['coverage_branch']}%"
                    result_style = "green"
                elif data["tests_run"] > 0:
                    result = f"Passed ({data['tests_run']} tests)"
                    result_style = "green"
                else:
                    result = "No tests"
                    result_style = "yellow"
            elif data["status"] == "compile_success":
                result = "Compiled"
                result_style = "green"

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

            recommendation = ""
            if data.get("recommendations"):
                rec = data["recommendations"][0]
                recommendation = rec.get("action", "")
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

        return Panel(
            table,
            title="📊 Test Results",
            border_style="cyan"
        )

    async def run(self) -> int:
        """Execute Maven tests for all services with parallel execution."""
        self.show_config()

        try:
            # Execute tests in parallel
            with Live(self.tracker.get_table(), console=console, refresh_per_second=4) as live:
                tasks = [self.test_service(service) for service in self.services]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Final table update
                live.update(self.tracker.get_table())

            # Post-processing outside Live context
            console.print()

            # Generate coverage reports
            console.print("📊 Generating Coverage Reports...")
            for service in self.services:
                self.tracker.update(service, "coverage", "Generating coverage", phase="coverage")
                console.print(f"  → {service}: generating coverage…")

                success, message = self._generate_coverage_for_service(service)

                if success:
                    console.print(f"    ✓ {service}: {message}")
                    self.tracker.update(service, "test_success", message, phase="coverage")
                else:
                    console.print(f"    ⚠ {service}: {message}")
                    self.tracker.update(service, "test_success", f"Coverage: {message}", phase="coverage")

            console.print("Coverage generation complete\n")

            # Extract coverage from reports
            self._extract_coverage_from_reports()

            # Assess coverage quality
            self._assess_coverage_quality()

            # Update quality results in tracker
            for service in self.services:
                if self.tracker.services[service].get("quality_grade"):
                    grade = self.tracker.services[service]["quality_grade"]
                    label = self.tracker.services[service].get("quality_label", "")
                    self.tracker.services[service]["details"] = f"Grade {grade}: {label}"

            # Print final results panel
            if len(self.profiles) > 1:
                console.print(self.get_profile_breakdown_panel())
            else:
                console.print(self.get_quality_panel())

            # Determine return code
            all_ok = all(
                self.tracker.services[s]["status"] in ["test_success", "compile_success"]
                and self.tracker.services[s]["tests_failed"] == 0
                for s in self.services
            )
            return_code = 0 if all_ok else 1

            return return_code

        except Exception as e:
            console.print(f"[red]Error:[/red] {e}", style="bold red")
            import traceback
            traceback.print_exc()
            return 1
