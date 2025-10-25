"""Tests for result formatting."""

from spi_agent.display.result_formatter import format_tool_result


def test_format_github_list_issues():
    """Test formatting gh_list_issues result."""
    result = [{"number": 1}, {"number": 2}, {"number": 3}]
    formatted = format_tool_result("gh_list_issues", result)
    assert formatted == "Found 3 issue(s)"


def test_format_github_get_issue():
    """Test formatting gh_get_issue result."""
    result = {"number": 42, "title": "Test issue"}
    formatted = format_tool_result("gh_get_issue", result)
    assert formatted == "Issue #42"


def test_format_github_create_issue():
    """Test formatting gh_create_issue result."""
    result = {"number": 123, "title": "New issue"}
    formatted = format_tool_result("gh_create_issue", result)
    assert formatted == "Created issue #123"


def test_format_github_list_pull_requests():
    """Test formatting gh_list_pull_requests result."""
    result = [{"number": 1}, {"number": 2}]
    formatted = format_tool_result("gh_list_pull_requests", result)
    assert formatted == "Found 2 PR(s)"


def test_format_read_file():
    """Test formatting read_file result."""
    result = "line1\nline2\nline3"
    formatted = format_tool_result("read_file", result)
    assert formatted == "Read 3 line(s)"


def test_format_list_directory():
    """Test formatting list_directory result."""
    result = ["file1.py", "file2.py", "file3.py"]
    formatted = format_tool_result("list_directory", result)
    assert formatted == "Found 3 item(s)"


def test_format_scan_java_project_with_vulns():
    """Test formatting scan_java_project with vulnerabilities."""
    result = {
        "total_dependencies": 50,
        "vulnerabilities": {
            "critical": [{"id": "CVE-1"}],
            "high": [{"id": "CVE-2"}, {"id": "CVE-3"}],
        },
    }
    formatted = format_tool_result("scan_java_project_tool", result)
    assert "50 dependencies" in formatted
    # Should mention vulnerabilities
    assert "vulnerability" in formatted.lower() or "vulnerabilit" in formatted.lower()


def test_format_scan_java_project_no_vulns():
    """Test formatting scan_java_project without vulnerabilities."""
    result = {"total_dependencies": 25, "vulnerabilities": {}}
    formatted = format_tool_result("scan_java_project_tool", result)
    assert formatted == "Scanned 25 dependencies"


def test_format_none_result():
    """Test formatting None result."""
    formatted = format_tool_result("any_tool", None)
    assert formatted == "Completed"


def test_format_unknown_tool():
    """Test formatting result for unknown tool."""
    result = {"some": "data"}
    formatted = format_tool_result("unknown_tool", result)
    # Should return generic message
    assert len(formatted) > 0


def test_format_long_string_truncation():
    """Test that long strings are truncated."""
    long_string = "a" * 200
    formatted = format_tool_result("unknown_tool", long_string)
    assert len(formatted) <= 104  # 100 chars + "..."
    assert formatted.endswith("...")
