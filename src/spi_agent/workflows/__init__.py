"""Workflows package for SPI Agent.

This package provides workflow orchestration capabilities using Microsoft Agent Framework,
including:
- Workflow result storage for agent context
- Workflow executors for multi-step operations
- Workflow builders for different operation types
"""

from typing import Optional

from spi_agent.workflows.result_store import WorkflowResult, WorkflowResultStore

# Global singleton instance of WorkflowResultStore
_result_store: Optional[WorkflowResultStore] = None


def get_result_store() -> WorkflowResultStore:
    """Get the global WorkflowResultStore singleton instance.

    This function provides access to a shared workflow result store that
    persists across different workflow executions and is accessible from
    middleware for context injection.

    Returns:
        WorkflowResultStore: Global singleton instance

    Example:
        >>> from spi_agent.workflows import get_result_store
        >>> store = get_result_store()
        >>> await store.store(workflow_result)
        >>> recent = await store.get_recent("vulns", limit=1)
    """
    global _result_store

    if _result_store is None:
        _result_store = WorkflowResultStore(max_results_per_type=10)

    return _result_store


def reset_result_store() -> None:
    """Reset the global WorkflowResultStore singleton.

    This is primarily useful for testing to ensure a clean state.
    """
    global _result_store
    _result_store = None


__all__ = [
    "WorkflowResult",
    "WorkflowResultStore",
    "get_result_store",
    "reset_result_store",
]
