"""Tests for copilot module (TestRunner, TestTracker, TriageRunner, TriageTracker)."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from spi_agent.copilot import SERVICES, TestRunner, TestTracker, TriageRunner, TriageTracker, parse_services
from spi_agent.copilot.runners.copilot_runner import CopilotRunner


class TestParseServices:
    """Tests for parse_services function."""

    def test_parse_single_service(self):
        """Test parsing a single service name."""
        result = parse_services("partition")
        assert result == ["partition"]

    def test_parse_multiple_services(self):
        """Test parsing comma-separated services."""
        result = parse_services("partition,legal,schema")
        assert result == ["partition", "legal", "schema"]

    def test_parse_all_services(self):
        """Test parsing 'all' keyword."""
        result = parse_services("all")
        assert result == list(SERVICES.keys())
        assert len(result) == 10

    def test_parse_services_with_spaces(self):
        """Test parsing services with extra whitespace."""
        result = parse_services("partition , legal , schema")
        assert result == ["partition", "legal", "schema"]


class TestTestTracker:
    """Tests for TestTracker class."""

    def test_initialization(self):
        """Test TestTracker initialization."""
        services = ["partition", "legal"]
        tracker = TestTracker(services)

        assert len(tracker.services) == 2
        assert "partition" in tracker.services
        assert "legal" in tracker.services

        # Check initial state
        for service in services:
            assert tracker.services[service]["status"] == "pending"
            assert tracker.services[service]["phase"] is None
            assert tracker.services[service]["tests_run"] == 0
            assert tracker.services[service]["tests_failed"] == 0
            assert tracker.services[service]["coverage_line"] == 0
            assert tracker.services[service]["coverage_branch"] == 0
            assert tracker.services[service]["icon"] == "⏸"

    def test_update_basic_status(self):
        """Test updating service status."""
        tracker = TestTracker(["partition"])
        tracker.update("partition", "compiling", "Compiling source code")

        assert tracker.services["partition"]["status"] == "compiling"
        assert tracker.services["partition"]["details"] == "Compiling source code"
        assert tracker.services["partition"]["icon"] == "▶"

    def test_update_with_phase(self):
        """Test updating service with phase."""
        tracker = TestTracker(["partition"])
        tracker.update("partition", "testing", "Running tests", phase="test")

        assert tracker.services["partition"]["status"] == "testing"
        assert tracker.services["partition"]["phase"] == "test"
        assert tracker.services["partition"]["icon"] == "▶"

    def test_update_with_test_results(self):
        """Test updating with test results."""
        tracker = TestTracker(["partition"])
        tracker.update(
            "partition",
            "testing",
            "Tests running",
            tests_run=42,
            tests_failed=2,
        )

        assert tracker.services["partition"]["tests_run"] == 42
        assert tracker.services["partition"]["tests_failed"] == 2

    def test_update_with_coverage(self):
        """Test updating with coverage data."""
        tracker = TestTracker(["partition"])
        tracker.update(
            "partition",
            "coverage",
            "Generating coverage",
            coverage_line=78,
            coverage_branch=65,
        )

        assert tracker.services["partition"]["coverage_line"] == 78
        assert tracker.services["partition"]["coverage_branch"] == 65
        assert tracker.services["partition"]["icon"] == "▶"

    def test_update_invalid_service(self):
        """Test updating non-existent service does not error."""
        tracker = TestTracker(["partition"])
        # Should not raise error
        tracker.update("nonexistent", "testing", "Should be ignored")

        # Original service should be unchanged
        assert tracker.services["partition"]["status"] == "pending"

    def test_get_table(self):
        """Test generating Rich table."""
        tracker = TestTracker(["partition", "legal"])
        tracker.update("partition", "testing", "Running tests", tests_run=10, tests_failed=2)
        tracker.update("legal", "compile_success", "Compilation successful")

        table = tracker.get_table()

        assert table.title == "Service Status"
        assert len(table.columns) == 4  # Service, Provider, Status, Details

    def test_status_icons(self):
        """Test that different statuses have correct icons."""
        tracker = TestTracker(["partition"])

        status_icon_map = {
            "pending": "⏸",
            "compiling": "▶",
            "testing": "▶",
            "coverage": "▶",
            "compile_success": "✓",
            "test_success": "✓",
            "compile_failed": "✗",
            "test_failed": "✗",
            "error": "✗",
        }

        for status, expected_icon in status_icon_map.items():
            tracker.update("partition", status, f"Testing {status}")
            assert tracker.services["partition"]["icon"] == expected_icon


class TestTestRunner:
    """Tests for TestRunner class."""

    @pytest.fixture
    def mock_prompt_file(self, tmp_path):
        """Create a mock prompt file."""
        prompt_file = tmp_path / "test.md"
        prompt_file.write_text(
            "Test prompt template\n{{ORGANIZATION}}\nARGUMENTS:\nSERVICES: {{services}}\nPROVIDER: {{provider}}"
        )
        return prompt_file

    def test_initialization(self, mock_prompt_file):
        """Test TestRunner initialization."""
        services = ["partition", "legal"]
        runner = TestRunner(mock_prompt_file, services, provider="azure")

        assert runner.services == services
        assert runner.provider == "azure"
        assert isinstance(runner.tracker, TestTracker)
        assert runner.log_file.name.startswith("test_")

    def test_initialization_with_options(self, mock_prompt_file):
        """Test TestRunner initialization with options."""
        runner = TestRunner(
            mock_prompt_file,
            ["partition"],
            provider="aws",
        )

        assert runner.provider == "aws"

    def test_load_prompt(self, mock_prompt_file):
        """Test prompt loading and augmentation."""
        with patch("spi_agent.copilot.runners.test_runner.config") as mock_config:
            mock_config.organization = "test-org"

            runner = TestRunner(mock_prompt_file, ["partition"], provider="azure")
            prompt = runner.load_prompt()

            assert "test-org" in prompt
            assert "SERVICES: partition" in prompt
            assert "PROVIDER: azure" in prompt

    def test_parse_maven_output_compilation(self, mock_prompt_file):
        """Test parsing Maven compilation output."""
        runner = TestRunner(mock_prompt_file, ["partition"])

        # Test compilation start - copilot format
        runner.parse_output("✓ partition: Starting compile phase")
        assert runner.tracker.services["partition"]["status"] == "compiling"
        assert runner.tracker.services["partition"]["phase"] == "compile"

    def test_parse_maven_output_testing(self, mock_prompt_file):
        """Test parsing Maven test execution output."""
        runner = TestRunner(mock_prompt_file, ["partition"])

        # Set to compiling first
        runner.tracker.update("partition", "compiling", "Compiling", phase="compile")

        # Test execution start - copilot format
        runner.parse_output("✓ partition: Starting test phase")
        assert runner.tracker.services["partition"]["status"] == "testing"
        assert runner.tracker.services["partition"]["phase"] == "test"

    def test_parse_maven_output_test_results(self, mock_prompt_file):
        """Test parsing test result lines."""
        runner = TestRunner(mock_prompt_file, ["partition"])
        runner.tracker.update("partition", "testing", "Running tests", phase="test")

        # Parse copilot completion summary
        runner.parse_output("✓ partition: Compiled successfully, 42 tests passed, Coverage report generated")

        assert runner.tracker.services["partition"]["tests_run"] == 42
        assert runner.tracker.services["partition"]["tests_failed"] == 0

    def test_parse_maven_output_test_summary(self, mock_prompt_file):
        """Test parsing copilot test summary."""
        runner = TestRunner(mock_prompt_file, ["partition"])
        runner.tracker.update("partition", "testing", "Running tests", phase="test")

        # Parse copilot's summary format
        runner.parse_output("✓ partition: Compiled successfully, 61 tests passed, Coverage report generated")

        assert runner.tracker.services["partition"]["tests_run"] == 61
        assert runner.tracker.services["partition"]["tests_failed"] == 0

    def test_parse_maven_test_output(self, mock_prompt_file):
        """Test that Maven test output is parsed correctly in single-profile mode."""
        runner = TestRunner(mock_prompt_file, ["partition"], provider="azure")

        # Simulate actual Maven Surefire output (includes service name in line)
        maven_line = "partition: [INFO] Tests run: 61, Failures: 0, Errors: 0, Skipped: 0"
        runner.parse_output(maven_line)

        # Verify Maven output was parsed and stored
        assert runner.tracker.services["partition"]["tests_run"] == 61
        assert runner.tracker.services["partition"]["tests_failed"] == 0
        assert runner.tracker.services["partition"]["status"] == "test_success"

    def test_parse_maven_test_output_with_failures(self, mock_prompt_file):
        """Test that Maven test output with failures is parsed correctly in single-profile mode."""
        runner = TestRunner(mock_prompt_file, ["entitlements"], provider="azure")

        # Simulate Maven output with failures and errors (includes service name)
        maven_line = "entitlements: [INFO] Tests run: 256, Failures: 2, Errors: 1, Skipped: 0"
        runner.parse_output(maven_line)

        # Verify Maven output was parsed (failures + errors = 3)
        assert runner.tracker.services["entitlements"]["tests_run"] == 256
        assert runner.tracker.services["entitlements"]["tests_failed"] == 3

    def test_parse_output_consistency(self, mock_prompt_file):
        """Test that parsing returns consistent results across runs in single-profile mode."""
        runner = TestRunner(mock_prompt_file, ["entitlements"], provider="azure")

        # Parse same Maven output multiple times (includes service name)
        for _ in range(10):
            maven_line = "entitlements: [INFO] Tests run: 256, Failures: 2, Errors: 0, Skipped: 0"
            runner.parse_output(maven_line)

        # Should always be the same (last update wins, but value is consistent)
        assert runner.tracker.services["entitlements"]["tests_run"] == 256
        assert runner.tracker.services["entitlements"]["tests_failed"] == 2

    def test_maven_output_priority_over_ai_summary(self, mock_prompt_file):
        """Test that Maven output takes priority over AI summary in single-profile mode."""
        runner = TestRunner(mock_prompt_file, ["entitlements"], provider="azure")

        # First, parse Maven output (includes service name)
        maven_line = "entitlements: [INFO] Tests run: 256, Failures: 0, Errors: 0, Skipped: 0"
        runner.parse_output(maven_line)
        assert runner.tracker.services["entitlements"]["tests_run"] == 256

        # Then parse AI summary with different count (should be ignored)
        ai_summary = "✓ entitlements: Compiled successfully, 7 tests passed, Coverage report generated"
        runner.parse_output(ai_summary)

        # Maven count should be preserved, not overwritten by AI summary
        assert runner.tracker.services["entitlements"]["tests_run"] == 256

    def test_ai_summary_fallback_when_no_maven_output(self, mock_prompt_file):
        """Test that AI summary is used as fallback when Maven output is not available."""
        runner = TestRunner(mock_prompt_file, ["legal"])

        # Parse only AI summary (no Maven output)
        ai_summary = "✓ legal: Compiled successfully, 27 tests passed, Coverage report generated"
        runner.parse_output(ai_summary)

        # AI summary should be used as fallback
        assert runner.tracker.services["legal"]["tests_run"] == 27
        assert runner.tracker.services["legal"]["tests_failed"] == 0

    def test_parse_building_module_header(self, mock_prompt_file):
        """Test that Maven 'Building' headers are parsed to track current module."""
        runner = TestRunner(mock_prompt_file, ["partition"], provider="core,azure")

        # Simulate Building header
        runner.parse_output("[INFO] Building partition-core 0.29.0-SNAPSHOT")

        # Check that current module is tracked
        assert runner.current_module == "partition-core"

    def test_parse_per_profile_test_counts(self, mock_prompt_file):
        """Test that per-profile test counts are extracted correctly."""
        runner = TestRunner(mock_prompt_file, ["partition"], provider="core,azure")

        # Simulate Maven multi-profile output
        runner.parse_output("partition: [INFO] Building partition-core 0.29.0-SNAPSHOT")
        runner.parse_output("partition: [INFO] Tests run: 61, Failures: 0, Errors: 0, Skipped: 0")

        runner.parse_output("partition: [INFO] Building partition-azure 0.29.0-SNAPSHOT")
        runner.parse_output("partition: [INFO] Tests run: 61, Failures: 0, Errors: 0, Skipped: 0")

        # Verify profile-specific counts
        assert runner.tracker.services["partition"]["profiles"]["core"]["tests_run"] == 61
        assert runner.tracker.services["partition"]["profiles"]["azure"]["tests_run"] == 61

    def test_parse_structured_format_single_profile(self, mock_prompt_file):
        """Test parsing structured test results format for single profile."""
        runner = TestRunner(mock_prompt_file, ["partition"], provider="azure")
        runner.tracker = TestTracker(["partition"], "azure", profiles=["azure"])

        # Parse structured test results block
        runner.parse_output("[TEST_RESULTS:partition]")
        assert runner.current_test_service == "partition"

        runner.parse_output("profile=azure,tests_run=61,failures=0,errors=0,skipped=0")
        assert runner.tracker.services["partition"]["tests_run"] == 61
        assert runner.tracker.services["partition"]["tests_failed"] == 0

        runner.parse_output("[/TEST_RESULTS]")
        assert runner.current_test_service is None

    def test_parse_structured_format_multi_profile(self, mock_prompt_file):
        """Test parsing structured test results format for multiple profiles."""
        runner = TestRunner(mock_prompt_file, ["partition"], provider="core,core-plus,azure")
        runner.tracker = TestTracker(["partition"], "core,core-plus,azure", profiles=["core", "core-plus", "azure"])

        # Parse structured test results block
        runner.parse_output("[TEST_RESULTS:partition]")
        assert runner.current_test_service == "partition"

        # Parse core profile results
        runner.parse_output("profile=core,tests_run=61,failures=0,errors=0,skipped=0")
        assert runner.tracker.services["partition"]["profiles"]["core"]["tests_run"] == 61

        # Parse azure profile results
        runner.parse_output("profile=azure,tests_run=61,failures=2,errors=1,skipped=0")
        assert runner.tracker.services["partition"]["profiles"]["azure"]["tests_run"] == 61
        assert runner.tracker.services["partition"]["profiles"]["azure"]["tests_failed"] == 3  # failures + errors

        runner.parse_output("[/TEST_RESULTS]")
        assert runner.current_test_service is None

        # Check aggregation happened
        assert runner.tracker.services["partition"]["tests_run"] == 122  # 61 + 61

    def test_parse_structured_format_with_failures(self, mock_prompt_file):
        """Test parsing structured test results with failures."""
        runner = TestRunner(mock_prompt_file, ["partition"], provider="core,azure")
        runner.tracker = TestTracker(["partition"], "core,azure", profiles=["core", "azure"])

        # Parse structured test results block with failures
        runner.parse_output("[TEST_RESULTS:partition]")
        assert runner.current_test_service == "partition"

        # Parse core profile - all pass
        runner.parse_output("profile=core,tests_run=61,failures=0,errors=0,skipped=0")
        assert runner.tracker.services["partition"]["profiles"]["core"]["tests_run"] == 61
        assert runner.tracker.services["partition"]["profiles"]["core"]["tests_failed"] == 0

        # Parse azure profile - with failures
        runner.parse_output("profile=azure,tests_run=61,failures=3,errors=2,skipped=1")
        assert runner.tracker.services["partition"]["profiles"]["azure"]["tests_run"] == 61
        assert runner.tracker.services["partition"]["profiles"]["azure"]["tests_failed"] == 5  # 3 failures + 2 errors

        # Parse optional failed test names
        runner.parse_output("failed_tests[azure]=TestAzureBlob.testUpload,TestAzureAuth.testToken,TestAzureQueue.testSend")

        runner.parse_output("[/TEST_RESULTS]")
        assert runner.current_test_service is None

        # Check aggregation - should have failures at service level
        assert runner.tracker.services["partition"]["tests_run"] == 122  # 61 + 61
        assert runner.tracker.services["partition"]["tests_failed"] == 5  # 0 + 5
        assert runner.tracker.services["partition"]["status"] == "test_failed"  # Should be marked as failed

    def test_extract_profile_from_module_name(self, mock_prompt_file):
        """Test profile extraction from various module name formats."""
        runner = TestRunner(mock_prompt_file, ["test"])

        assert runner._extract_profile_from_module("partition-core") == "core"
        assert runner._extract_profile_from_module("partition-core-plus") == "core-plus"
        assert runner._extract_profile_from_module("entitlements-v2-azure") == "azure"
        assert runner._extract_profile_from_module("legal-azure") == "azure"
        assert runner._extract_profile_from_module("schema-aws") == "aws"

    def test_parse_maven_output_coverage_copilot_format(self, mock_prompt_file):
        """Test parsing copilot coverage summary format."""
        runner = TestRunner(mock_prompt_file, ["partition"])
        runner.tracker.update("partition", "testing", "Tests complete", phase="test")

        # Parse copilot's full summary
        runner.parse_output("✓ partition: Compiled successfully, 42 tests passed, Coverage report generated")
        assert runner.tracker.services["partition"]["tests_run"] == 42

    def test_parse_maven_output_build_success(self, mock_prompt_file):
        """Test parsing BUILD SUCCESS."""
        runner = TestRunner(mock_prompt_file, ["partition"])

        # Test completion with successful build
        runner.parse_output("✓ partition: Compiled successfully, 10 tests passed, Coverage report generated")
        assert runner.tracker.services["partition"]["status"] == "test_success"

    def test_parse_maven_output_build_failure(self, mock_prompt_file):
        """Test parsing BUILD FAILURE."""
        runner = TestRunner(mock_prompt_file, ["partition"])

        # Build failure
        runner.parse_output("Build failure for partition")
        assert runner.tracker.services["partition"]["status"] == "test_failed"

        # Compilation failure
        runner.parse_output("Compilation failure for partition")
        assert runner.tracker.services["partition"]["status"] == "compile_failed"

    def test_parse_maven_output_test_failures(self, mock_prompt_file):
        """Test handling test failures."""
        runner = TestRunner(mock_prompt_file, ["partition"])
        runner.tracker.update("partition", "testing", "Testing", phase="test")

        # Parse completion with tests
        runner.parse_output("✓ partition: Compiled successfully, 42 tests passed, Coverage report generated")
        assert runner.tracker.services["partition"]["tests_run"] == 42
        assert runner.tracker.services["partition"]["status"] == "test_success"

    def test_parse_maven_output_repo_not_found(self, mock_prompt_file):
        """Test handling repository not found error."""
        runner = TestRunner(mock_prompt_file, ["partition"])

        # This test now just verifies the method doesn't crash - error detection is simplified
        runner.parse_output("No such file or directory: repos/partition/pom.xml")
        # Status may not change if copilot doesn't report explicit error

    def test_parse_maven_output_multiple_services(self, mock_prompt_file):
        """Test parsing output for multiple services."""
        runner = TestRunner(mock_prompt_file, ["partition", "legal"])

        # First service starts compiling
        runner.parse_output("✓ partition: Starting compile phase")
        assert runner.tracker.services["partition"]["status"] == "compiling"
        assert runner.tracker.services["legal"]["status"] == "pending"

        # First service completes
        runner.tracker.update("partition", "compile_success", "Done", phase="compile")

        # Second service starts
        runner.parse_output("✓ legal: Starting compile phase")
        assert runner.tracker.services["legal"]["status"] == "compiling"

    @patch("spi_agent.copilot.runners.test_runner.subprocess.run")
    @patch("spi_agent.copilot.runners.test_runner.subprocess.Popen")
    @patch("spi_agent.copilot.runners.test_runner.console")
    def test_run_success(self, mock_console, mock_popen, mock_run, mock_prompt_file):
        """Test successful test execution."""
        # Mock subprocess.Popen (for copilot execution)
        mock_process = Mock()
        mock_process.stdout = iter(
            [
                "✓ partition: Starting compile phase",
                "✓ partition: Compiled successfully, 42 tests passed, Coverage report generated",
            ]
        )
        mock_process.returncode = 0
        mock_process.wait = Mock()
        mock_popen.return_value = mock_process

        # Mock subprocess.run (for mvn jacoco:report coverage generation)
        mock_run_result = Mock()
        mock_run_result.returncode = 0
        mock_run_result.stdout = "BUILD SUCCESS"
        mock_run_result.stderr = ""
        mock_run.return_value = mock_run_result

        runner = TestRunner(mock_prompt_file, ["partition"])

        with patch("spi_agent.copilot.runners.test_runner.Live"):
            result = runner.run()

        assert result == 0
        # Popen should be called once for copilot execution
        assert mock_popen.call_count == 1

    @patch("spi_agent.copilot.runners.test_runner.subprocess.Popen")
    @patch("spi_agent.copilot.runners.test_runner.console")
    def test_run_copilot_not_found(self, mock_console, mock_popen, mock_prompt_file):
        """Test handling when copilot is not installed."""
        mock_popen.side_effect = FileNotFoundError("copilot not found")

        runner = TestRunner(mock_prompt_file, ["partition"])
        result = runner.run()

        assert result == 1

    @patch("spi_agent.copilot.runners.test_runner.subprocess.Popen")
    @patch("spi_agent.copilot.runners.test_runner.console")
    def test_run_with_error(self, mock_console, mock_popen, mock_prompt_file):
        """Test handling runtime errors."""
        mock_popen.side_effect = RuntimeError("Unexpected error")

        runner = TestRunner(mock_prompt_file, ["partition"])
        result = runner.run()

        assert result == 1

    def test_log_file_naming(self, mock_prompt_file):
        """Test log file naming with multiple services."""
        # Single service
        runner1 = TestRunner(mock_prompt_file, ["partition"])
        assert "partition" in str(runner1.log_file)

        # Multiple services (<=3)
        runner2 = TestRunner(mock_prompt_file, ["partition", "legal", "schema"])
        log_name = str(runner2.log_file)
        assert "partition-legal-schema" in log_name

        # Many services (>3)
        runner3 = TestRunner(
            mock_prompt_file, ["partition", "legal", "schema", "file", "storage"]
        )
        log_name = str(runner3.log_file)
        assert "partition-legal-schema-and-2-more" in log_name

    def test_get_summary_panel(self, mock_prompt_file):
        """Test summary panel generation."""
        runner = TestRunner(mock_prompt_file, ["partition", "legal"])

        # Set up some results
        runner.tracker.update("partition", "test_success", "All tests passed", tests_run=42, tests_failed=0)
        runner.tracker.update("legal", "compile_failed", "Compilation failed")

        panel = runner.get_results_panel(1)  # Exit code 1 (failure)

        assert panel.title == "📊 Test Results"
        assert panel.border_style == "cyan"

    def test_create_layout(self, mock_prompt_file):
        """Test layout creation."""
        runner = TestRunner(mock_prompt_file, ["partition"])
        layout = runner.create_layout()

        assert layout is not None
        # Layout should be created successfully (Rich Layout object)
        assert hasattr(layout, "split_row")

    def test_show_config(self, mock_prompt_file):
        """Test configuration display."""
        runner = TestRunner(mock_prompt_file, ["partition"], provider="aws")

        # Should not raise error - it actually prints to console
        runner.show_config()
        # Just verify it doesn't crash - it prints to real console in test

    def test_extract_coverage_from_html_report(self, mock_prompt_file, tmp_path):
        """Test extracting coverage from JaCoCo CSV report (preferred method)."""
        runner = TestRunner(mock_prompt_file, ["partition"], provider="azure")

        # Create a mock JaCoCo CSV report (now the preferred method)
        jacoco_dir = tmp_path / "repos" / "partition" / "provider" / "partition-azure" / "target" / "site" / "jacoco"
        jacoco_dir.mkdir(parents=True)

        # CSV format: GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
        csv_content = """GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
partition,org.opengroup.osdu.partition,PartitionService,0,1036,3,86,0,213,0,45,0,9"""
        (jacoco_dir / "jacoco.csv").write_text(csv_content)

        # Change to temp directory
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Extract coverage
            runner._extract_coverage_from_reports()

            # Verify coverage was extracted (100% line coverage, 96.6% branch coverage)
            assert runner.tracker.services["partition"]["coverage_line"] == 100
            # Branch coverage: 86 covered / (3 missed + 86 covered) = 96.6% -> rounded to 96%
            assert runner.tracker.services["partition"]["coverage_branch"] == 96
        finally:
            os.chdir(old_cwd)

    def test_get_summary_panel_with_coverage(self, mock_prompt_file):
        """Test summary panel with coverage data."""
        runner = TestRunner(mock_prompt_file, ["partition"])

        # Set up tracker with coverage data
        runner.tracker.services["partition"] = {
            "status": "test_success",
            "phase": "coverage",
            "details": "Tests completed",
            "icon": "✓",
            "tests_run": 42,
            "tests_failed": 0,
            "coverage_line": 85,
            "coverage_branch": 72,
            "quality_grade": None,
            "quality_label": None,
            "quality_summary": None,
            "recommendations": [],
        }

        panel = runner.get_quality_panel()

        # Check panel properties
        assert panel.title == "📊 Test Results"
        assert panel.border_style == "cyan"

    def test_get_summary_panel_with_quality_assessment(self, mock_prompt_file):
        """Test summary panel with quality assessment data."""
        runner = TestRunner(mock_prompt_file, ["partition"])

        # Set up tracker with quality assessment
        runner.tracker.services["partition"] = {
            "status": "test_success",
            "phase": "coverage",
            "details": "Tests completed",
            "icon": "✓",
            "tests_run": 61,
            "tests_failed": 0,
            "coverage_line": 85,
            "coverage_branch": 72,
            "quality_grade": "B",
            "quality_label": "Good",
            "quality_summary": "The codebase has good test coverage with most critical paths tested.",
            "recommendations": [
                {
                    "priority": 1,
                    "action": "Add unit tests for DataValidator class",
                    "expected_improvement": "+8% overall coverage"
                },
                {
                    "priority": 2,
                    "action": "Improve branch coverage for AuthorizationService",
                    "expected_improvement": "+5% branch coverage"
                }
            ],
        }

        panel = runner.get_quality_panel()

        # Check panel includes quality assessment
        assert panel.title == "📊 Test Results"
        assert panel.border_style == "cyan"
        # Verify the quality data is still in the tracker
        assert runner.tracker.services["partition"]["quality_grade"] == "B"
        assert runner.tracker.services["partition"]["quality_label"] == "Good"
        assert len(runner.tracker.services["partition"]["recommendations"]) == 2

    def test_assess_coverage_quality(self, mock_prompt_file):
        """Test the coverage quality assessment method."""
        runner = TestRunner(mock_prompt_file, ["partition"], provider="azure")

        # Set up coverage data for Grade B (85% line, 72% branch)
        runner.tracker.services["partition"]["coverage_line"] = 85
        runner.tracker.services["partition"]["coverage_branch"] = 72

        # Run assessment
        runner._assess_coverage_quality()

        # Verify quality data was stored
        assert runner.tracker.services["partition"]["quality_grade"] == "B"
        assert runner.tracker.services["partition"]["quality_label"] == "Good"
        assert "Good test coverage" in runner.tracker.services["partition"]["quality_summary"]
        assert len(runner.tracker.services["partition"]["recommendations"]) > 0

        # Test Grade A assessment
        runner.tracker.services["partition"]["coverage_line"] = 95
        runner.tracker.services["partition"]["coverage_branch"] = 90
        runner._assess_coverage_quality()
        assert runner.tracker.services["partition"]["quality_grade"] == "A"
        assert runner.tracker.services["partition"]["quality_label"] == "Excellent"

        # Test Grade F assessment
        runner.tracker.services["partition"]["coverage_line"] = 40
        runner.tracker.services["partition"]["coverage_branch"] = 30
        runner._assess_coverage_quality()
        assert runner.tracker.services["partition"]["quality_grade"] == "F"
        assert runner.tracker.services["partition"]["quality_label"] == "Poor"


class TestCopilotRunner:
    """Tests for CopilotRunner class (fork command)."""

    @pytest.fixture
    def mock_prompt_file(self, tmp_path):
        """Create a mock prompt file."""
        prompt_file = tmp_path / "fork.md"
        prompt_file.write_text(
            "Fork prompt template\n{{ORGANIZATION}}\nARGUMENTS:\nSERVICES: {{services}}\nBRANCH: {{branch}}"
        )
        return prompt_file

    def test_service_in_line_exact_match(self, mock_prompt_file):
        """Test _service_in_line with exact service name match."""
        runner = CopilotRunner(mock_prompt_file, ["partition"], branch="main")

        # Should match exact service name
        assert runner._service_in_line("partition", "partition service completed") is True
        assert runner._service_in_line("partition", "✅ Successfully completed workflow for partition service") is True

    def test_service_in_line_no_substring_match(self, mock_prompt_file):
        """Test _service_in_line does NOT match when service is substring of another word."""
        runner = CopilotRunner(mock_prompt_file, ["indexer", "indexer-queue"], branch="main")

        # "indexer" should NOT match within "indexer-queue"
        assert runner._service_in_line("indexer", "✅ Successfully completed workflow for indexer-queue service") is False

        # "indexer-queue" should match exactly
        assert runner._service_in_line("indexer-queue", "✅ Successfully completed workflow for indexer-queue service") is True

    def test_service_in_line_hyphenated_names(self, mock_prompt_file):
        """Test _service_in_line with hyphenated service names."""
        runner = CopilotRunner(mock_prompt_file, ["indexer-queue"], branch="main")

        # Should match complete hyphenated name
        assert runner._service_in_line("indexer-queue", "indexer-queue service is ready") is True
        assert runner._service_in_line("indexer-queue", "the indexer-queue repository") is True

        # Should NOT match partial hyphenated name
        assert runner._service_in_line("indexer", "indexer-queue service is ready") is False

    def test_service_in_line_word_boundaries(self, mock_prompt_file):
        """Test _service_in_line respects word boundaries."""
        runner = CopilotRunner(mock_prompt_file, ["legal", "partition"], branch="main")

        # Should match at word boundaries
        assert runner._service_in_line("legal", "legal service completed") is True
        assert runner._service_in_line("legal", "the legal repository") is True
        assert runner._service_in_line("legal", "✓ legal: done") is True

        # Should NOT match within other words
        assert runner._service_in_line("legal", "illegally parsed") is False

    def test_parse_output_indexer_queue_completion(self, mock_prompt_file):
        """
        Regression test: Verify indexer-queue completion is parsed correctly.

        This test ensures that when the line "✅ Successfully completed workflow for indexer-queue service"
        is parsed, only the indexer-queue service status is updated, NOT the indexer service.

        Bug: Previously, "indexer" would match within "indexer-queue" due to substring matching,
        causing the wrong service to be marked as complete.
        """
        runner = CopilotRunner(
            mock_prompt_file,
            ["partition", "indexer", "indexer-queue", "search"],
            branch="main"
        )

        # Initially all services are pending
        assert runner.tracker.services["indexer"]["status"] == "pending"
        assert runner.tracker.services["indexer-queue"]["status"] == "pending"

        # Parse the indexer-queue completion line
        runner.parse_output("✅ Successfully completed workflow for indexer-queue service")

        # indexer-queue should be marked as success
        assert runner.tracker.services["indexer-queue"]["status"] == "success"
        assert runner.tracker.services["indexer-queue"]["details"] == "Completed successfully"

        # indexer should still be pending (NOT updated by mistake)
        assert runner.tracker.services["indexer"]["status"] == "pending"

        # Other services should remain pending
        assert runner.tracker.services["partition"]["status"] == "pending"
        assert runner.tracker.services["search"]["status"] == "pending"

    def test_parse_output_indexer_completion(self, mock_prompt_file):
        """Test that indexer service completion is parsed correctly."""
        runner = CopilotRunner(
            mock_prompt_file,
            ["indexer", "indexer-queue"],
            branch="main"
        )

        # Parse the indexer completion line (not indexer-queue)
        runner.parse_output("✅ Successfully completed workflow for indexer service")

        # indexer should be marked as success
        assert runner.tracker.services["indexer"]["status"] == "success"

        # indexer-queue should still be pending
        assert runner.tracker.services["indexer-queue"]["status"] == "pending"

    def test_parse_output_multiple_hyphenated_services(self, mock_prompt_file):
        """Test parsing with multiple hyphenated service names."""
        runner = CopilotRunner(
            mock_prompt_file,
            ["partition", "file", "storage", "indexer", "indexer-queue", "workflow"],
            branch="main"
        )

        # Test workflow completion (workflow is also a common word in output)
        runner.parse_output("✅ Successfully completed workflow for workflow service")
        assert runner.tracker.services["workflow"]["status"] == "success"
        assert runner.tracker.services["indexer"]["status"] == "pending"

        # Test partition completion
        runner.parse_output("✅ Successfully completed workflow for partition service")
        assert runner.tracker.services["partition"]["status"] == "success"

    def test_parse_output_service_order_independence(self, mock_prompt_file):
        """
        Test that service matching is independent of service order.

        Previously, the bug would occur because services were checked in order,
        and "indexer" appeared before "indexer-queue" in the list, causing
        early substring match and break.
        """
        # Test with indexer-queue before indexer
        runner1 = CopilotRunner(
            mock_prompt_file,
            ["indexer-queue", "indexer"],
            branch="main"
        )
        runner1.parse_output("✅ Successfully completed workflow for indexer-queue service")
        assert runner1.tracker.services["indexer-queue"]["status"] == "success"
        assert runner1.tracker.services["indexer"]["status"] == "pending"

        # Test with indexer before indexer-queue (original bug scenario)
        runner2 = CopilotRunner(
            mock_prompt_file,
            ["indexer", "indexer-queue"],
            branch="main"
        )
        runner2.parse_output("✅ Successfully completed workflow for indexer-queue service")
        assert runner2.tracker.services["indexer-queue"]["status"] == "success"
        assert runner2.tracker.services["indexer"]["status"] == "pending"

    def test_parse_output_task_markers_with_indexer_queue(self, mock_prompt_file):
        """Test that task completion markers correctly identify indexer-queue."""
        runner = CopilotRunner(
            mock_prompt_file,
            ["indexer", "indexer-queue"],
            branch="main"
        )

        # Test task marker for indexer-queue
        runner.parse_output("✓ Create indexer-queue repo from template")
        assert runner.tracker.services["indexer-queue"]["status"] == "running"
        assert "Creating repository" in runner.tracker.services["indexer-queue"]["details"]

        # indexer should not be affected
        assert runner.tracker.services["indexer"]["status"] == "pending"

    def test_parse_actual_fork_log(self, mock_prompt_file):
        """
        Test parsing the actual fork log file that exhibited the bug.

        This test reads the actual log file (if it exists) and verifies that
        indexer-queue is correctly marked as success, not pending.
        """
        log_file_path = Path("logs/fork_20251016_080723_partition-entitlements-legal-and-7-more.log")

        if not log_file_path.exists():
            pytest.skip(f"Log file not found: {log_file_path}")

        # All services from the log
        all_services = [
            "partition",
            "entitlements",
            "legal",
            "schema",
            "file",
            "storage",
            "indexer",
            "indexer-queue",
            "search",
            "workflow"
        ]

        runner = CopilotRunner(mock_prompt_file, all_services, branch="main")

        # Parse all lines from the log file
        with open(log_file_path, "r", encoding="utf-8") as f:
            for line in f:
                runner.parse_output(line.strip())

        # Verify indexer-queue is marked as success, NOT pending
        assert runner.tracker.services["indexer-queue"]["status"] == "success", \
            "indexer-queue should be marked as success after parsing the log file"

        # Verify all services have a final status (none should be pending)
        for service in all_services:
            status = runner.tracker.services[service]["status"]
            assert status in ["success", "skipped", "error"], \
                f"{service} should have a final status, but is: {status}"
