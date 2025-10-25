"""Result summary formatting for tool execution results."""

from typing import Any, Dict


def format_tool_result(tool_name: str, result: Any) -> str:
    """Format tool execution result into a concise summary.

    Args:
        tool_name: Name of the tool that was executed
        result: Tool execution result

    Returns:
        Human-readable summary string
    """
    # Handle None results
    if result is None:
        return "Completed"

    # GitHub Issues
    if tool_name == "gh_list_issues":
        if isinstance(result, list):
            return f"Found {len(result)} issue(s)"
        return "Listed issues"

    if tool_name == "gh_get_issue":
        if isinstance(result, dict) and "number" in result:
            return f"Issue #{result['number']}"
        return "Read issue"

    if tool_name == "gh_create_issue":
        if isinstance(result, dict) and "number" in result:
            return f"Created issue #{result['number']}"
        return "Created issue"

    # GitHub Pull Requests
    if tool_name == "gh_list_pull_requests":
        if isinstance(result, list):
            return f"Found {len(result)} PR(s)"
        return "Listed pull requests"

    if tool_name == "gh_get_pull_request":
        if isinstance(result, dict) and "number" in result:
            return f"PR #{result['number']}"
        return "Read pull request"

    # GitHub Workflows
    if tool_name == "gh_list_workflow_runs":
        if isinstance(result, list):
            return f"Found {len(result)} run(s)"
        return "Listed workflow runs"

    if tool_name == "gh_trigger_workflow":
        return "Triggered workflow"

    # Code Scanning
    if tool_name == "gh_list_code_scanning_alerts":
        if isinstance(result, list):
            return f"Found {len(result)} alert(s)"
        return "Listed security alerts"

    # GitLab
    if tool_name.startswith("glab_list_"):
        if isinstance(result, list):
            return f"Found {len(result)} item(s)"
        return "Listed items"

    # Filesystem tools
    if tool_name == "list_directory":
        if isinstance(result, list):
            return f"Found {len(result)} item(s)"
        return "Listed directory"

    if tool_name == "read_file":
        if isinstance(result, str):
            lines = result.count("\n") + 1
            return f"Read {lines} line(s)"
        return "Read file"

    if tool_name == "search_files":
        if isinstance(result, list):
            return f"Found {len(result)} match(es)"
        return "Searched files"

    # Search and dependency tools
    if tool_name == "search_in_files":
        if isinstance(result, str):
            # Count matches (result contains match lines)
            match_count = result.count("\n") if result else 0
            return f"Found {match_count} match(es)"
        elif isinstance(result, list):
            return f"Found {len(result)} match(es)"
        return "Searched files"

    if tool_name == "find_dependency_versions":
        # Parse result to extract key info
        if isinstance(result, str):
            if "No references found" in result:
                return "No references found"
            elif "Found" in result:
                # Extract count if present
                return result.split('\n')[0] if '\n' in result else result[:60]
        return "Searched dependencies"

    if tool_name == "list_files":
        if isinstance(result, list):
            return f"Found {len(result)} file(s)"
        elif isinstance(result, str):
            # Count lines if result is string with file list
            file_count = result.count("\n") if result else 0
            return f"Found {file_count} file(s)"
        return "Listed files"

    # Maven MCP tools
    if "check_version" in tool_name:
        if isinstance(result, dict):
            if "updates_available" in result:
                return f"Updates available" if result.get("updates_available") else "Up to date"
        return "Checked version"

    if "scan_java_project" in tool_name:
        if isinstance(result, dict):
            vuln_count = 0
            if "vulnerabilities" in result:
                if isinstance(result["vulnerabilities"], dict):
                    vuln_count = sum(
                        len(v) if isinstance(v, list) else 0
                        for v in result["vulnerabilities"].values()
                    )
                elif isinstance(result["vulnerabilities"], list):
                    vuln_count = len(result["vulnerabilities"])

            dep_count = result.get("total_dependencies", 0)
            if vuln_count > 0:
                return f"Scanned {dep_count} dependencies, {vuln_count} vulnerability(ies)"
            return f"Scanned {dep_count} dependencies"
        return "Scanned project"

    if "analyze_pom" in tool_name:
        if isinstance(result, dict):
            dep_count = len(result.get("dependencies", []))
            return f"Analyzed POM, {dep_count} dependencies"
        return "Analyzed POM"

    # Generic result handling
    if isinstance(result, list):
        return f"Returned {len(result)} item(s)"

    if isinstance(result, dict):
        if "success" in result:
            return "Success" if result["success"] else "Failed"
        if "count" in result:
            return f"Found {result['count']} item(s)"

    if isinstance(result, str):
        # Truncate long strings
        if len(result) > 100:
            return f"{result[:100]}..."
        return result

    return "Completed"
