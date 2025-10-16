"""
Tool argument normalizer for Maven MCP server.

This module handles known parameter validation bugs in mvn-mcp-server 2.3.0
where Optional[List[str]] parameters are incorrectly serialized as "type": "string"
in the MCP schema, causing validation errors for both string and array inputs.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def normalize_maven_tool_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize Maven MCP tool arguments to handle known schema bugs.

    Due to a FastMCP/MCP SDK bug, parameters defined as Optional[List[str]]
    in the mvn-mcp-server are serialized as "type": "string" in the schema.
    This causes validation errors for BOTH string and array inputs.

    The server's default behavior (when these parameters are omitted) is actually
    superior for our triage use case:
    - Scans ALL modules/profiles automatically
    - Includes ALL severity levels
    - Provides comprehensive module_summary for easy comparison

    This normalizer removes broken parameters and lets the server use defaults.

    Removed parameters:
    - include_profiles: Broken validation, not needed (scan gets all profiles)
    - severity_filter: Broken validation, not needed (can filter client-side)
    - profiles: Legacy parameter (if present)

    Args:
        arguments: The tool arguments dictionary

    Returns:
        Normalized arguments with broken parameters removed

    Example:
        >>> # LLM tries to use broken parameters
        >>> args = {
        ...     "workspace": "/path",
        ...     "include_profiles": ["azure"],
        ...     "severity_filter": ["CRITICAL", "HIGH"]
        ... }
        >>> normalize_maven_tool_arguments(args)
        {'workspace': '/path'}
        # Broken parameters removed, warnings logged
    """
    if not isinstance(arguments, dict):
        return arguments

    normalized = dict(arguments)

    # Remove 'profiles' if present (legacy parameter, causes validation errors)
    if "profiles" in normalized:
        profiles_value = normalized.pop("profiles")
        logger.warning(
            f"Removed 'profiles' parameter ({profiles_value}) due to MCP server schema bug. "
            f"Server will scan all profiles by default. "
            f"Use module pattern filtering client-side if needed."
        )

    # Remove 'include_profiles' if present (v2.3.0+, causes validation errors)
    if "include_profiles" in normalized:
        profiles_value = normalized.pop("include_profiles")
        logger.warning(
            f"Removed 'include_profiles' parameter ({profiles_value}) due to MCP server schema bug. "
            f"Server will scan all profiles by default. "
            f"Use module_summary from results to filter by module pattern."
        )

    # Remove 'severity_filter' if present (v2.3.0+, causes validation errors)
    if "severity_filter" in normalized:
        severity_value = normalized.pop("severity_filter")
        logger.warning(
            f"Removed 'severity_filter' parameter ({severity_value}) due to MCP server schema bug. "
            f"Server will include all severity levels. "
            f"Filter by severity client-side using severity_counts from results."
        )

    return normalized


if __name__ == "__main__":
    # Quick tests
    print("Testing normalize_maven_tool_arguments:")
    print("=" * 70)

    print("\nTest 1: Clean arguments (no broken parameters)")
    test_args1 = {"workspace": "/path/to/workspace", "max_results": 100}
    print(f"  Input:  {test_args1}")
    result1 = normalize_maven_tool_arguments(test_args1)
    print(f"  Output: {result1}")
    print(f"  ✓ No changes needed")

    print("\nTest 2: Broken parameters (will be removed)")
    test_args2 = {
        "workspace": "/path",
        "include_profiles": ["azure", "core"],
        "severity_filter": ["CRITICAL", "HIGH"],
        "max_results": 50
    }
    print(f"  Input:  {test_args2}")
    result2 = normalize_maven_tool_arguments(test_args2)
    print(f"  Output: {result2}")
    print(f"  ✓ Broken parameters removed (warnings logged above)")

    print("\nTest 3: Legacy profiles parameter")
    test_args3 = {"workspace": "/path", "profiles": "dev,prod"}
    print(f"  Input:  {test_args3}")
    result3 = normalize_maven_tool_arguments(test_args3)
    print(f"  Output: {result3}")
    print(f"  ✓ Legacy parameter removed (warning logged above)")

    print("\n" + "=" * 70)
    print("Note: Warnings above are expected - they inform the user that")
    print("broken parameters were removed and the server will use defaults.")
