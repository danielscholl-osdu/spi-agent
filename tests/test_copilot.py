"""Tests for copilot module (TestRunner, TestTracker)."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from spi_agent.copilot import SERVICES, TestRunner, TestTracker, parse_services


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
        assert tracker.services["partition"]["icon"] == "⚙️"

    def test_update_with_phase(self):
        """Test updating service with phase."""
        tracker = TestTracker(["partition"])
        tracker.update("partition", "testing", "Running tests", phase="test")

        assert tracker.services["partition"]["status"] == "testing"
        assert tracker.services["partition"]["phase"] == "test"
        assert tracker.services["partition"]["icon"] == "🧪"

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
        assert tracker.services["partition"]["icon"] == "📊"

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

        assert table.title == "Maven Test Execution Status"
        assert len(table.columns) == 5  # Service, Status, Details, Tests, Coverage

    def test_status_icons(self):
        """Test that different statuses have correct icons."""
        tracker = TestTracker(["partition"])

        status_icon_map = {
            "pending": "⏸",
            "compiling": "⚙️",
            "testing": "🧪",
            "coverage": "📊",
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
        assert runner.compile_only is False
        assert runner.skip_coverage is False
        assert isinstance(runner.tracker, TestTracker)
        assert runner.log_file.name.startswith("test_")

    def test_initialization_with_options(self, mock_prompt_file):
        """Test TestRunner initialization with options."""
        runner = TestRunner(
            mock_prompt_file,
            ["partition"],
            provider="aws",
            compile_only=True,
            skip_coverage=True,
        )

        assert runner.provider == "aws"
        assert runner.compile_only is True
        assert runner.skip_coverage is True

    def test_load_prompt(self, mock_prompt_file):
        """Test prompt loading and augmentation."""
        with patch("spi_agent.copilot.config") as mock_config:
            mock_config.organization = "test-org"

            runner = TestRunner(mock_prompt_file, ["partition"], provider="azure")
            prompt = runner.load_prompt()

            assert "test-org" in prompt
            assert "SERVICES: partition" in prompt
            assert "PROVIDER: azure" in prompt

    def test_parse_maven_output_compilation(self, mock_prompt_file):
        """Test parsing Maven compilation output."""
        runner = TestRunner(mock_prompt_file, ["partition"])

        # Test compilation start
        runner.parse_maven_output("[INFO] --- maven-compiler-plugin:3.8.1:compile")
        assert runner.tracker.services["partition"]["status"] == "compiling"
        assert runner.tracker.services["partition"]["phase"] == "compile"

    def test_parse_maven_output_testing(self, mock_prompt_file):
        """Test parsing Maven test execution output."""
        runner = TestRunner(mock_prompt_file, ["partition"])

        # Set to compiling first
        runner.tracker.update("partition", "compiling", "Compiling", phase="compile")

        # Test execution start
        runner.parse_maven_output("[INFO] --- maven-surefire-plugin:2.22.2:test")
        assert runner.tracker.services["partition"]["status"] == "testing"
        assert runner.tracker.services["partition"]["phase"] == "test"

    def test_parse_maven_output_test_results(self, mock_prompt_file):
        """Test parsing test result lines."""
        runner = TestRunner(mock_prompt_file, ["partition"])
        runner.tracker.update("partition", "testing", "Running tests", phase="test")

        # Parse test results line (Maven format)
        runner.parse_maven_output("Tests run: 42, Failures: 2, Errors: 1, Skipped: 3")

        assert runner.tracker.services["partition"]["tests_run"] == 42
        assert runner.tracker.services["partition"]["tests_failed"] == 3  # failures + errors

    def test_parse_maven_output_test_summary(self, mock_prompt_file):
        """Test parsing copilot test summary."""
        runner = TestRunner(mock_prompt_file, ["partition"])
        runner.tracker.update("partition", "testing", "Running tests", phase="test")

        # Parse copilot's summary format
        runner.parse_maven_output("✓ **Tests**: All 61 tests passed (6.2s)")

        assert runner.tracker.services["partition"]["tests_run"] == 61
        assert runner.tracker.services["partition"]["tests_failed"] == 0

    def test_parse_maven_output_coverage(self, mock_prompt_file):
        """Test parsing coverage output."""
        runner = TestRunner(mock_prompt_file, ["partition"])
        runner.tracker.update("partition", "testing", "Tests complete", phase="test")

        # JaCoCo plugin execution
        runner.parse_maven_output("[INFO] --- jacoco-maven-plugin:0.8.7:report")
        assert runner.tracker.services["partition"]["status"] == "coverage"

        # Coverage results (Maven format)
        runner.parse_maven_output("Line coverage: 78%, Branch coverage: 65%")
        assert runner.tracker.services["partition"]["coverage_line"] == 78
        assert runner.tracker.services["partition"]["coverage_branch"] == 65

    def test_parse_maven_output_coverage_copilot_format(self, mock_prompt_file):
        """Test parsing copilot coverage summary format."""
        runner = TestRunner(mock_prompt_file, ["partition"])
        runner.tracker.update("partition", "testing", "Tests complete", phase="test")

        # Parse copilot's coverage format
        runner.parse_maven_output("- Line: 100.0% (213/213)")
        runner.parse_maven_output("- Branch: 96.5% (83/86)")

        assert runner.tracker.services["partition"]["coverage_line"] == 100
        assert runner.tracker.services["partition"]["coverage_branch"] == 96

    def test_parse_maven_output_build_success(self, mock_prompt_file):
        """Test parsing BUILD SUCCESS."""
        runner = TestRunner(mock_prompt_file, ["partition"])

        # Compile phase success
        runner.tracker.update("partition", "compiling", "Compiling", phase="compile")
        runner.parse_maven_output("[INFO] BUILD SUCCESS")
        assert runner.tracker.services["partition"]["status"] == "compile_success"

        # Test phase success
        runner.tracker.update("partition", "testing", "Testing", phase="test", tests_run=10, tests_failed=0)
        runner.parse_maven_output("[INFO] BUILD SUCCESS")
        assert runner.tracker.services["partition"]["status"] == "test_success"

    def test_parse_maven_output_build_failure(self, mock_prompt_file):
        """Test parsing BUILD FAILURE."""
        runner = TestRunner(mock_prompt_file, ["partition"])

        # Compile phase failure
        runner.tracker.update("partition", "compiling", "Compiling", phase="compile")
        runner.parse_maven_output("[INFO] BUILD FAILURE")
        assert runner.tracker.services["partition"]["status"] == "compile_failed"

        # Test phase failure
        runner.tracker.update("partition", "testing", "Testing", phase="test")
        runner.parse_maven_output("[INFO] BUILD FAILURE")
        assert runner.tracker.services["partition"]["status"] == "test_failed"

    def test_parse_maven_output_test_failures(self, mock_prompt_file):
        """Test handling test failures."""
        runner = TestRunner(mock_prompt_file, ["partition"])
        runner.tracker.update("partition", "testing", "Testing", phase="test")

        # Tests with failures
        runner.parse_maven_output("Tests run: 42, Failures: 5, Errors: 2, Skipped: 1")
        runner.parse_maven_output("[INFO] BUILD SUCCESS")  # Maven succeeds but tests failed

        assert runner.tracker.services["partition"]["tests_failed"] == 7
        assert runner.tracker.services["partition"]["status"] == "test_failed"

    def test_parse_maven_output_repo_not_found(self, mock_prompt_file):
        """Test handling repository not found error."""
        runner = TestRunner(mock_prompt_file, ["partition"])

        runner.parse_maven_output("No such file or directory: repos/partition/pom.xml")
        assert runner.tracker.services["partition"]["status"] == "error"

    def test_parse_maven_output_multiple_services(self, mock_prompt_file):
        """Test parsing output for multiple services."""
        runner = TestRunner(mock_prompt_file, ["partition", "legal"])

        # First service starts compiling
        runner.parse_maven_output("[INFO] Building partition")
        runner.parse_maven_output("[INFO] --- maven-compiler-plugin:3.8.1:compile")
        assert runner.tracker.services["partition"]["status"] == "compiling"
        assert runner.tracker.services["legal"]["status"] == "pending"

        # First service completes
        runner.tracker.update("partition", "compile_success", "Done", phase="compile")

        # Second service starts
        runner.parse_maven_output("[INFO] Building legal")
        runner.parse_maven_output("[INFO] --- maven-compiler-plugin:3.8.1:compile")
        assert runner.tracker.services["legal"]["status"] == "compiling"

    @patch("spi_agent.copilot.subprocess.Popen")
    @patch("spi_agent.copilot.console")
    def test_run_success(self, mock_console, mock_popen, mock_prompt_file):
        """Test successful test execution."""
        # Mock subprocess
        mock_process = Mock()
        mock_process.stdout = iter(
            [
                "[INFO] Building partition",
                "[INFO] --- maven-compiler-plugin:3.8.1:compile",
                "[INFO] BUILD SUCCESS",
            ]
        )
        mock_process.returncode = 0
        mock_process.wait = Mock()
        mock_popen.return_value = mock_process

        runner = TestRunner(mock_prompt_file, ["partition"])

        with patch("spi_agent.copilot.Live"):
            result = runner.run()

        assert result == 0
        # Popen is called at least once (may be called by _assess_coverage_quality too)
        assert mock_popen.call_count >= 1

    @patch("spi_agent.copilot.subprocess.Popen")
    @patch("spi_agent.copilot.console")
    def test_run_copilot_not_found(self, mock_console, mock_popen, mock_prompt_file):
        """Test handling when copilot is not installed."""
        mock_popen.side_effect = FileNotFoundError("copilot not found")

        runner = TestRunner(mock_prompt_file, ["partition"])
        result = runner.run()

        assert result == 1

    @patch("spi_agent.copilot.subprocess.Popen")
    @patch("spi_agent.copilot.console")
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

        panel = runner.get_summary_panel(1)  # Exit code 1 (failure)

        assert panel.title == "📊 Test Results Summary"
        assert panel.border_style == "red"  # Because there's a failure

    def test_create_layout(self, mock_prompt_file):
        """Test layout creation."""
        runner = TestRunner(mock_prompt_file, ["partition"])
        layout = runner.create_layout()

        assert layout is not None
        # Layout should be created successfully (Rich Layout object)
        assert hasattr(layout, "split_row")

    def test_show_config(self, mock_prompt_file):
        """Test configuration display."""
        runner = TestRunner(mock_prompt_file, ["partition"], provider="aws", compile_only=True)

        # Should not raise error
        with patch("spi_agent.copilot.console") as mock_console:
            runner.show_config()
            mock_console.print.assert_called()

    def test_extract_coverage_from_html_report(self, mock_prompt_file, tmp_path):
        """Test extracting coverage from JaCoCo HTML report."""
        runner = TestRunner(mock_prompt_file, ["partition"])

        # Create a mock JaCoCo HTML report
        jacoco_dir = tmp_path / "repos" / "partition" / "target" / "site" / "jacoco"
        jacoco_dir.mkdir(parents=True)

        html_content = """<!DOCTYPE html>
<html>
<body>
<table>
<tfoot>
<tr class="total">
<td>Total</td>
<td class="bar">0 of 1,036</td>
<td class="ctr2">100%</td>
<td class="bar">3 of 86</td>
<td class="ctr2">96%</td>
<td class="ctr1">3</td>
<td class="ctr2">88</td>
<td class="ctr1">0</td>
<td class="ctr2">213</td>
<td class="ctr1">0</td>
<td class="ctr2">45</td>
<td class="ctr1">0</td>
<td class="ctr2">9</td>
</tr>
</tfoot>
</table>
</body>
</html>"""
        (jacoco_dir / "index.html").write_text(html_content)

        # Change to temp directory
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Extract coverage
            runner._extract_coverage_from_reports()

            # Verify coverage was extracted
            assert runner.tracker.services["partition"]["coverage_line"] == 100
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

        panel = runner.get_summary_panel(0)

        # Check panel properties
        assert panel.title == "📊 Test Results Summary"
        assert "✓ Tests Completed" in panel.renderable
        assert "85%" in panel.renderable
        assert "72%" in panel.renderable

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

        panel = runner.get_summary_panel(0)

        # Check panel includes quality assessment
        assert "Quality Assessment" in panel.renderable
        assert "Grade B - Good" in panel.renderable
        assert "good test coverage" in panel.renderable
        assert "DataValidator" in panel.renderable
        assert "+8% overall coverage" in panel.renderable

    def test_assess_coverage_quality(self, mock_prompt_file):
        """Test the coverage quality assessment method."""
        runner = TestRunner(mock_prompt_file, ["partition"])

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
