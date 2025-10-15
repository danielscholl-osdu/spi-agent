"""Tests for workflows functionality."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from spi_agent.workflows import WorkflowResult, WorkflowResultStore, get_result_store, reset_result_store


class TestWorkflowResult:
    """Tests for WorkflowResult dataclass."""

    def test_workflow_result_creation(self):
        """Test creating a WorkflowResult."""
        result = WorkflowResult(
            workflow_type="triage",
            timestamp=datetime.now(),
            services=["partition", "legal"],
            status="success",
            summary="Analysis complete",
            detailed_results={"exit_code": 0},
        )

        assert result.workflow_type == "triage"
        assert len(result.services) == 2
        assert result.status == "success"
        assert result.vulnerabilities is None  # Optional field

    def test_workflow_result_with_triage_data(self):
        """Test WorkflowResult with triage-specific data."""
        result = WorkflowResult(
            workflow_type="triage",
            timestamp=datetime.now(),
            services=["partition"],
            status="success",
            summary="5 critical vulnerabilities",
            detailed_results={},
            vulnerabilities={"partition": {"critical": 5, "high": 10, "medium": 3}},
            cve_analysis="CVE-2025-12345 (Critical)...",
        )

        assert result.vulnerabilities is not None
        assert result.vulnerabilities["partition"]["critical"] == 5
        assert result.cve_analysis is not None

    def test_workflow_result_with_test_data(self):
        """Test WorkflowResult with test-specific data."""
        result = WorkflowResult(
            workflow_type="test",
            timestamp=datetime.now(),
            services=["partition"],
            status="success",
            summary="Tests passed",
            detailed_results={},
            test_results={"partition": {"passed": 150, "failed": 0, "skipped": 3}},
        )

        assert result.test_results is not None
        assert result.test_results["partition"]["passed"] == 150


class TestWorkflowResultStore:
    """Tests for WorkflowResultStore."""

    @pytest.fixture
    def store(self):
        """Create a fresh store for each test."""
        return WorkflowResultStore(max_results_per_type=5)

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, store):
        """Test storing and retrieving results."""
        result = WorkflowResult(
            workflow_type="triage",
            timestamp=datetime.now(),
            services=["partition"],
            status="success",
            summary="Test result",
            detailed_results={},
        )

        await store.store(result)
        results = await store.get_recent("triage", limit=1)

        assert len(results) == 1
        assert results[0].workflow_type == "triage"
        assert results[0].services == ["partition"]

    @pytest.mark.asyncio
    async def test_get_recent_with_type_filter(self, store):
        """Test filtering results by workflow type."""
        # Store different types
        triage_result = WorkflowResult(
            workflow_type="triage",
            timestamp=datetime.now(),
            services=["partition"],
            status="success",
            summary="Triage",
            detailed_results={},
        )

        test_result = WorkflowResult(
            workflow_type="test",
            timestamp=datetime.now(),
            services=["partition"],
            status="success",
            summary="Test",
            detailed_results={},
        )

        await store.store(triage_result)
        await store.store(test_result)

        # Get only triage results
        triage_results = await store.get_recent("triage", limit=10)
        assert len(triage_results) == 1
        assert triage_results[0].workflow_type == "triage"

        # Get only test results
        test_results = await store.get_recent("test", limit=10)
        assert len(test_results) == 1
        assert test_results[0].workflow_type == "test"

    @pytest.mark.asyncio
    async def test_get_recent_limit(self, store):
        """Test limiting number of results returned."""
        # Store 5 results
        for i in range(5):
            result = WorkflowResult(
                workflow_type="triage",
                timestamp=datetime.now(),
                services=[f"service-{i}"],
                status="success",
                summary=f"Result {i}",
                detailed_results={},
            )
            await store.store(result)

        # Get only 3 most recent
        results = await store.get_recent("triage", limit=3)
        assert len(results) == 3

        # Results should be most recent first
        assert results[0].services[0] == "service-4"  # Most recent
        assert results[2].services[0] == "service-2"  # 3rd most recent

    @pytest.mark.asyncio
    async def test_get_context_summary_with_triage(self, store):
        """Test context summary generation with triage data."""
        result = WorkflowResult(
            workflow_type="triage",
            timestamp=datetime(2025, 10, 15, 14, 30),
            services=["partition", "legal"],
            status="success",
            summary="Vulnerabilities found",
            detailed_results={},
            vulnerabilities={
                "partition": {"critical": 5, "high": 10, "medium": 3},
                "legal": {"critical": 0, "high": 2, "medium": 1},
            },
            cve_analysis="CVE-2025-12345: Critical vulnerability in Spring...",
        )

        await store.store(result)
        summary = await store.get_context_summary(limit=1)

        # Verify summary contains key information
        assert "Recent Workflow Results" in summary
        assert "Triage" in summary
        assert "partition" in summary
        assert "5 critical" in summary
        assert "10 high" in summary
        assert "CVE" in summary

    @pytest.mark.asyncio
    async def test_get_context_summary_with_test(self, store):
        """Test context summary generation with test data."""
        result = WorkflowResult(
            workflow_type="test",
            timestamp=datetime(2025, 10, 15, 15, 0),
            services=["partition"],
            status="success",
            summary="Tests passed",
            detailed_results={},
            test_results={
                "partition": {
                    "passed": 150,
                    "failed": 2,
                    "skipped": 3,
                    "total_tests": 152,
                    "quality_grade": "A",
                    "coverage_line": 85,
                    "coverage_branch": 78,
                }
            },
        )

        await store.store(result)
        summary = await store.get_context_summary(limit=1)

        assert "Test" in summary
        assert "partition" in summary
        assert "152 tests" in summary
        assert "Grade: A" in summary
        assert "coverage" in summary.lower()

    @pytest.mark.asyncio
    async def test_get_context_summary_empty(self, store):
        """Test context summary with no results."""
        summary = await store.get_context_summary(limit=5)
        assert summary == ""

    @pytest.mark.asyncio
    async def test_cleanup_old_results(self, store):
        """Test automatic cleanup of old results."""
        # Store more results than max_results_per_type (5)
        for i in range(10):
            result = WorkflowResult(
                workflow_type="triage",
                timestamp=datetime.now(),
                services=[f"service-{i}"],
                status="success",
                summary=f"Result {i}",
                detailed_results={},
            )
            await store.store(result)

        # Should only keep 5 most recent
        results = await store.get_recent("triage", limit=100)
        assert len(results) <= 5

    @pytest.mark.asyncio
    async def test_clear_all_results(self, store):
        """Test clearing all results."""
        # Store some results
        result = WorkflowResult(
            workflow_type="triage",
            timestamp=datetime.now(),
            services=["partition"],
            status="success",
            summary="Test",
            detailed_results={},
        )
        await store.store(result)

        # Clear all
        await store.clear()

        results = await store.get_recent(limit=10)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_clear_by_type(self, store):
        """Test clearing results by workflow type."""
        # Store different types
        triage_result = WorkflowResult(
            workflow_type="triage",
            timestamp=datetime.now(),
            services=["partition"],
            status="success",
            summary="Triage",
            detailed_results={},
        )

        test_result = WorkflowResult(
            workflow_type="test",
            timestamp=datetime.now(),
            services=["partition"],
            status="success",
            summary="Test",
            detailed_results={},
        )

        await store.store(triage_result)
        await store.store(test_result)

        # Clear only triage
        await store.clear("triage")

        triage_results = await store.get_recent("triage")
        test_results = await store.get_recent("test")

        assert len(triage_results) == 0
        assert len(test_results) == 1

    @pytest.mark.asyncio
    async def test_get_stats(self, store):
        """Test getting statistics."""
        # Store some results
        for workflow_type in ["triage", "triage", "test"]:
            result = WorkflowResult(
                workflow_type=workflow_type,
                timestamp=datetime.now(),
                services=["partition"],
                status="success",
                summary="Test",
                detailed_results={},
            )
            await store.store(result)

        stats = await store.get_stats()

        assert stats["total_results"] == 3
        assert stats["by_type"]["triage"] == 2
        assert stats["by_type"]["test"] == 1
        assert stats["oldest_timestamp"] is not None
        assert stats["newest_timestamp"] is not None


class TestSingletonPattern:
    """Tests for singleton pattern."""

    def test_get_result_store_singleton(self):
        """Test that get_result_store returns singleton."""
        reset_result_store()  # Ensure clean state

        store1 = get_result_store()
        store2 = get_result_store()

        # Should be same instance
        assert store1 is store2

    @pytest.mark.asyncio
    async def test_singleton_persists_data(self):
        """Test that singleton persists data across calls."""
        reset_result_store()

        store1 = get_result_store()
        result = WorkflowResult(
            workflow_type="triage",
            timestamp=datetime.now(),
            services=["partition"],
            status="success",
            summary="Test",
            detailed_results={},
        )
        await store1.store(result)

        # Get store again
        store2 = get_result_store()
        results = await store2.get_recent("triage", limit=1)

        # Should have the result from first store
        assert len(results) == 1

        # Cleanup
        reset_result_store()

    def test_reset_result_store(self):
        """Test resetting the singleton."""
        reset_result_store()

        store1 = get_result_store()
        reset_result_store()
        store2 = get_result_store()

        # Should be different instances after reset
        assert store1 is not store2


class TestWorkflowIntegration:
    """Integration tests for workflow functions."""

    @pytest.mark.asyncio
    async def test_run_triage_workflow_integration(self):
        """Test triage workflow integration with result store."""
        from spi_agent.workflows import get_result_store
        from spi_agent.workflows.triage_workflow import run_triage_workflow

        # Mock agent
        mock_agent = Mock()
        mock_agent.agent = Mock()
        mock_agent.agent.run = AsyncMock(return_value="Analysis complete: 3 critical")

        # Mock TriageRunner from the copilot module where it's actually imported
        with patch("spi_agent.copilot.runners.triage_runner.TriageRunner") as MockRunner:
            mock_runner = Mock()
            mock_runner.run = AsyncMock(return_value=0)  # Success exit code
            mock_runner.tracker = Mock()
            mock_runner.tracker.services = {
                "partition": {
                    "critical": 3,
                    "high": 5,
                    "medium": 12,
                    "status": "complete",
                }
            }
            mock_runner.full_output = ["Scan complete"]
            MockRunner.return_value = mock_runner

            # Mock get_prompt_file
            with patch("spi_agent.copilot.get_prompt_file") as mock_get_prompt:
                mock_prompt = Mock()
                mock_get_prompt.return_value = mock_prompt

                # Reset store
                reset_result_store()

                # Run workflow
                result = await run_triage_workflow(
                    agent=mock_agent,
                    services=["partition"],
                    severity_filter=["critical", "high"],
                    maven_profiles=["azure"],
                    create_issue=False,
                )

                # Verify result
                assert result.workflow_type == "triage"
                assert result.status == "success"
                assert result.services == ["partition"]

                # Verify stored in result store
                store = get_result_store()
                stored_results = await store.get_recent("triage", limit=1)
                assert len(stored_results) == 1
                assert stored_results[0].workflow_type == "triage"

                # Cleanup
                reset_result_store()
