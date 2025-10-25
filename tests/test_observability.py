"""Tests for observability functionality."""

import os
from unittest.mock import Mock, patch

import pytest

from spi_agent.observability import (
    record_llm_call,
    record_test_run,
    record_tool_call,
    record_vulns_scan,
    record_workflow_run,
)


class TestToolCallMetrics:
    """Tests for tool call metrics recording."""

    def test_record_tool_call_success(self):
        """Test recording successful tool call."""
        with patch("spi_agent.observability.tool_calls_counter") as mock_counter:
            with patch("spi_agent.observability.tool_duration_histogram") as mock_histogram:
                record_tool_call("list_issues", 1.5, "success")

                # Verify counter incremented
                mock_counter.add.assert_called_once_with(
                    1, {"tool": "list_issues", "status": "success"}
                )

                # Verify histogram recorded
                mock_histogram.record.assert_called_once_with(1.5, {"tool": "list_issues"})

    def test_record_tool_call_error(self):
        """Test recording failed tool call."""
        with patch("spi_agent.observability.tool_calls_counter") as mock_counter:
            with patch("spi_agent.observability.tool_duration_histogram") as mock_histogram:
                record_tool_call("create_issue", 0.5, "error")

                # Verify counter with error status
                mock_counter.add.assert_called_once_with(
                    1, {"tool": "create_issue", "status": "error"}
                )

                # Verify duration still recorded
                mock_histogram.record.assert_called_once()


class TestWorkflowMetrics:
    """Tests for workflow metrics recording."""

    def test_record_workflow_run_success(self):
        """Test recording successful workflow run."""
        with patch("spi_agent.observability.workflow_runs_counter") as mock_counter:
            with patch("spi_agent.observability.workflow_duration_histogram") as mock_histogram:
                record_workflow_run("triage", 45.2, "success", service_count=3)

                # Verify counter incremented with attributes
                mock_counter.add.assert_called_once_with(
                    1, {"workflow": "triage", "status": "success", "services": 3}
                )

                # Verify duration recorded
                mock_histogram.record.assert_called_once_with(45.2, {"workflow": "triage"})

    def test_record_workflow_run_error(self):
        """Test recording failed workflow run."""
        with patch("spi_agent.observability.workflow_runs_counter") as mock_counter:
            with patch("spi_agent.observability.workflow_duration_histogram") as mock_histogram:
                record_workflow_run("test", 10.0, "error", service_count=1)

                # Verify counter was called
                mock_counter.add.assert_called_once_with(
                    1, {"workflow": "test", "status": "error", "services": 1}
                )

                # Verify histogram was called
                mock_histogram.record.assert_called_once_with(10.0, {"workflow": "test"})


class TestTriageMetrics:
    """Tests for triage scan metrics recording."""

    def test_record_vulns_scan_with_vulnerabilities(self):
        """Test recording triage scan with vulnerabilities."""
        with patch("spi_agent.observability.triage_scans_counter") as mock_scan_counter:
            with patch(
                "spi_agent.observability.triage_vulnerabilities_counter"
            ) as mock_vuln_counter:
                record_vulns_scan("partition", critical=5, high=10, medium=3, low=1)

                # Verify scan counter incremented
                mock_scan_counter.add.assert_called_once()

                # Verify vulnerability counters by severity (4 calls for 4 severities)
                assert mock_vuln_counter.add.call_count == 4

                # Verify correct counts were recorded (first positional arg of each call)
                calls = mock_vuln_counter.add.call_args_list
                counts = [call[0][0] for call in calls]

                assert 5 in counts  # critical
                assert 10 in counts  # high
                assert 3 in counts  # medium
                assert 1 in counts  # low

    def test_record_vulns_scan_no_vulnerabilities(self):
        """Test recording triage scan with no vulnerabilities."""
        with patch("spi_agent.observability.triage_scans_counter") as mock_scan_counter:
            with patch(
                "spi_agent.observability.triage_vulnerabilities_counter"
            ) as mock_vuln_counter:
                record_vulns_scan("partition", critical=0, high=0, medium=0)

                # Scan counter should still be incremented
                mock_scan_counter.add.assert_called_once()

                # No vulnerability counters should be incremented
                mock_vuln_counter.add.assert_not_called()

    def test_record_vulns_scan_error_status(self):
        """Test recording failed triage scan."""
        with patch("spi_agent.observability.triage_scans_counter") as mock_scan_counter:
            with patch("spi_agent.observability.triage_vulnerabilities_counter"):
                record_vulns_scan("partition", critical=0, high=0, medium=0, status="error")

                # Verify error status
                mock_scan_counter.add.assert_called_once_with(
                    1, {"service": "partition", "status": "error"}
                )


class TestTestMetrics:
    """Tests for test run metrics recording."""

    def test_record_test_run_with_results(self):
        """Test recording test run with results."""
        with patch("spi_agent.observability.test_runs_counter") as mock_run_counter:
            with patch("spi_agent.observability.test_results_counter") as mock_result_counter:
                record_test_run("partition", passed=150, failed=2, skipped=3)

                # Verify run counter incremented
                mock_run_counter.add.assert_called_once()

                # Verify result counters by status (3 calls for passed, failed, skipped)
                assert mock_result_counter.add.call_count == 3

                # Verify correct counts were recorded
                calls = mock_result_counter.add.call_args_list
                counts = [call[0][0] for call in calls]

                assert 150 in counts  # passed
                assert 2 in counts  # failed
                assert 3 in counts  # skipped

    def test_record_test_run_all_passed(self):
        """Test recording test run with all passed."""
        with patch("spi_agent.observability.test_runs_counter") as mock_run_counter:
            with patch("spi_agent.observability.test_results_counter") as mock_result_counter:
                record_test_run("legal", passed=100, failed=0, skipped=0)

                # Only passed counter should be incremented
                mock_result_counter.add.assert_called_once_with(
                    100, {"result": "passed", "service": "legal"}
                )

    def test_record_test_run_error_status(self):
        """Test recording failed test run."""
        with patch("spi_agent.observability.test_runs_counter") as mock_run_counter:
            with patch("spi_agent.observability.test_results_counter"):
                record_test_run("partition", passed=0, failed=10, status="error")

                # Verify error status
                mock_run_counter.add.assert_called_once_with(
                    1, {"service": "partition", "status": "error"}
                )


class TestLLMMetrics:
    """Tests for LLM interaction metrics recording."""

    def test_record_llm_call(self):
        """Test recording LLM call."""
        with patch("spi_agent.observability.llm_calls_counter") as mock_call_counter:
            with patch("spi_agent.observability.llm_tokens_counter") as mock_token_counter:
                record_llm_call("gpt-4", prompt_tokens=500, completion_tokens=150, duration=2.5)

                # Verify call counter incremented
                mock_call_counter.add.assert_called_once()

                # Verify token counters (2 calls: prompt + completion)
                assert mock_token_counter.add.call_count == 2

                # Verify correct token counts were recorded
                calls = mock_token_counter.add.call_args_list
                counts = [call[0][0] for call in calls]

                assert 500 in counts  # prompt tokens
                assert 150 in counts  # completion tokens

    def test_record_llm_call_without_duration(self):
        """Test recording LLM call without duration."""
        with patch("spi_agent.observability.llm_calls_counter") as mock_call_counter:
            with patch("spi_agent.observability.llm_tokens_counter") as mock_token_counter:
                # Duration parameter is optional
                record_llm_call("gpt-4", prompt_tokens=100, completion_tokens=50)

                # Should still record call and tokens
                mock_call_counter.add.assert_called_once()
                assert mock_token_counter.add.call_count == 2


class TestTracerAndMeter:
    """Tests for tracer and meter initialization."""

    def test_tracer_initialization(self):
        """Test that tracer is initialized."""
        from spi_agent.observability import tracer

        assert tracer is not None
        # Tracer should be a valid OpenTelemetry tracer object
        assert hasattr(tracer, "start_as_current_span")

    def test_meter_initialization(self):
        """Test that meter is initialized."""
        from spi_agent.observability import meter

        assert meter is not None
        # Meter should be a valid OpenTelemetry meter object
        assert hasattr(meter, "create_counter")
        assert hasattr(meter, "create_histogram")

    def test_counters_initialized(self):
        """Test that all counters are initialized."""
        from spi_agent.observability import (
            llm_calls_counter,
            llm_tokens_counter,
            test_results_counter,
            test_runs_counter,
            tool_calls_counter,
            triage_scans_counter,
            triage_vulnerabilities_counter,
            workflow_runs_counter,
        )

        # All counters should be initialized
        assert tool_calls_counter is not None
        assert workflow_runs_counter is not None
        assert triage_scans_counter is not None
        assert triage_vulnerabilities_counter is not None
        assert test_runs_counter is not None
        assert test_results_counter is not None
        assert llm_calls_counter is not None
        assert llm_tokens_counter is not None

    def test_histograms_initialized(self):
        """Test that all histograms are initialized."""
        from spi_agent.observability import (
            tool_duration_histogram,
            workflow_duration_histogram,
        )

        # All histograms should be initialized
        assert tool_duration_histogram is not None
        assert workflow_duration_histogram is not None

    def test_otel_service_name_set_automatically(self):
        """Test that OTEL_SERVICE_NAME is set to 'spi-agent' by default."""
        # The observability module should set this on import
        assert os.getenv("OTEL_SERVICE_NAME") == "spi-agent"
