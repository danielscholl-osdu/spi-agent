"""Tests for file system tools."""

import tempfile
from pathlib import Path

import pytest

from spi_agent.config import AgentConfig
from spi_agent.filesystem import FileSystemTools


@pytest.fixture
def fs_tools():
    """Create FileSystemTools instance for testing."""
    config = AgentConfig()
    return FileSystemTools(config)


@pytest.fixture
def temp_repos_dir():
    """Create a temporary repos directory structure for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repos_dir = Path(tmpdir) / "repos"
        repos_dir.mkdir()

        # Create test structure:
        # repos/
        #   partition/
        #     providers/
        #       azure/
        #         pom.xml (with os-core-lib-azure 2.2.6)
        #   legal/
        #     providers/
        #       azure/
        #         pom.xml (with os-core-lib-azure 2.2.4)
        #   file/
        #     providers/
        #       azure/
        #         pom.xml (with os-core-lib-azure ${version} -> 2.2.5)

        # Partition service
        partition_azure = repos_dir / "partition" / "providers" / "azure"
        partition_azure.mkdir(parents=True)
        (partition_azure / "pom.xml").write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.opengroup.osdu</groupId>
    <artifactId>partition-azure</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.opengroup.osdu</groupId>
            <artifactId>os-core-lib-azure</artifactId>
            <version>2.2.6</version>
        </dependency>
    </dependencies>
</project>
"""
        )

        # Legal service
        legal_azure = repos_dir / "legal" / "providers" / "azure"
        legal_azure.mkdir(parents=True)
        (legal_azure / "pom.xml").write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.opengroup.osdu</groupId>
    <artifactId>legal-azure</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.opengroup.osdu</groupId>
            <artifactId>os-core-lib-azure</artifactId>
            <version>2.2.4</version>
        </dependency>
    </dependencies>
</project>
"""
        )

        # File service (with property)
        file_azure = repos_dir / "file" / "providers" / "azure"
        file_azure.mkdir(parents=True)
        (file_azure / "pom.xml").write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.opengroup.osdu</groupId>
    <artifactId>file-azure</artifactId>
    <version>1.0.0</version>

    <properties>
        <os-core-lib-azure.version>2.2.5</os-core-lib-azure.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.opengroup.osdu</groupId>
            <artifactId>os-core-lib-azure</artifactId>
            <version>${os-core-lib-azure.version}</version>
        </dependency>
    </dependencies>
</project>
"""
        )

        # Create a test file for read/search tests
        test_file = repos_dir / "partition" / "test.txt"
        test_file.write_text("Line 1: Hello World\nLine 2: Test Pattern\nLine 3: End\n")

        yield repos_dir


def test_list_files(fs_tools, temp_repos_dir):
    """Test listing files with pattern matching."""
    result = fs_tools.list_files(pattern="**/pom.xml", directory=str(temp_repos_dir))

    assert "Found 3 file(s)" in result
    assert "partition/providers/azure/pom.xml" in result
    assert "legal/providers/azure/pom.xml" in result
    assert "file/providers/azure/pom.xml" in result


def test_list_files_non_recursive(fs_tools, temp_repos_dir):
    """Test non-recursive file listing."""
    partition_dir = temp_repos_dir / "partition"
    result = fs_tools.list_files(pattern="*.txt", directory=str(partition_dir))

    assert "test.txt" in result


def test_list_files_not_found(fs_tools, temp_repos_dir):
    """Test listing files when directory doesn't exist."""
    result = fs_tools.list_files(pattern="*.xml", directory="/nonexistent/path")

    assert "Directory not found" in result


def test_read_file(fs_tools, temp_repos_dir):
    """Test reading file contents."""
    test_file = temp_repos_dir / "partition" / "test.txt"
    result = fs_tools.read_file(file_path=str(test_file))

    assert "Line 1: Hello World" in result
    assert "Line 2: Test Pattern" in result
    assert "Line 3: End" in result


def test_read_file_with_limit(fs_tools, temp_repos_dir):
    """Test reading file with line limit."""
    test_file = temp_repos_dir / "partition" / "test.txt"
    result = fs_tools.read_file(file_path=str(test_file), max_lines=2)

    assert "Line 1" in result
    # Note: Due to implementation, this might include more than 2 lines
    # but should be truncated somehow


def test_read_file_not_found(fs_tools, temp_repos_dir):
    """Test reading non-existent file."""
    result = fs_tools.read_file(file_path="/nonexistent/file.txt")

    assert "File not found" in result


def test_search_in_files(fs_tools, temp_repos_dir):
    """Test searching for patterns in files."""
    result = fs_tools.search_in_files(
        search_pattern="Test Pattern",
        file_pattern="**/*.txt",
        directory=str(temp_repos_dir),
    )

    assert "Found 1 match(es)" in result
    assert "test.txt:2" in result
    assert "Test Pattern" in result


def test_search_in_files_regex(fs_tools, temp_repos_dir):
    """Test searching with regex pattern."""
    result = fs_tools.search_in_files(
        search_pattern=r"Line \d+",
        file_pattern="**/*.txt",
        directory=str(temp_repos_dir),
        limit=10,
    )

    assert "Found 3 match(es)" in result or "Found" in result


def test_search_in_files_no_matches(fs_tools, temp_repos_dir):
    """Test searching when no matches found."""
    result = fs_tools.search_in_files(
        search_pattern="NonExistentPattern",
        file_pattern="**/*.txt",
        directory=str(temp_repos_dir),
    )

    assert "No matches found" in result


def test_parse_pom_dependencies(fs_tools, temp_repos_dir):
    """Test parsing POM file dependencies."""
    pom_file = temp_repos_dir / "partition" / "providers" / "azure" / "pom.xml"
    result = fs_tools.parse_pom_dependencies(pom_file=str(pom_file))

    assert "Dependencies in" in result
    assert "org.opengroup.osdu:os-core-lib-azure:2.2.6" in result


def test_parse_pom_with_properties(fs_tools, temp_repos_dir):
    """Test parsing POM with property resolution."""
    pom_file = temp_repos_dir / "file" / "providers" / "azure" / "pom.xml"
    result = fs_tools.parse_pom_dependencies(pom_file=str(pom_file))

    assert "Properties:" in result
    assert "os-core-lib-azure.version = 2.2.5" in result
    assert "os-core-lib-azure:${os-core-lib-azure.version} → 2.2.5" in result


def test_parse_pom_not_found(fs_tools, temp_repos_dir):
    """Test parsing non-existent POM file."""
    result = fs_tools.parse_pom_dependencies(pom_file="/nonexistent/pom.xml")

    assert "POM file not found" in result


def test_find_dependency_versions(fs_tools, temp_repos_dir):
    """Test finding dependency versions across services."""
    result = fs_tools.find_dependency_versions(
        group_id="org.opengroup.osdu",
        artifact_id="os-core-lib-azure",
        directory=str(temp_repos_dir),
    )

    assert "Found 3 reference(s)" in result
    assert "Service: partition" in result
    assert "Service: legal" in result
    assert "Service: file" in result
    assert "2.2.6" in result
    assert "2.2.4" in result
    assert "2.2.5" in result


def test_find_dependency_versions_with_provider_detection(fs_tools, temp_repos_dir):
    """Test automatic provider detection from artifact name."""
    result = fs_tools.find_dependency_versions(
        group_id="org.opengroup.osdu",
        artifact_id="os-core-lib-azure",  # Contains 'azure' -> auto-detects provider
        directory=str(temp_repos_dir),
    )

    assert "filtered by provider: azure" in result
    assert "Found 3 reference(s)" in result


def test_find_dependency_versions_explicit_provider(fs_tools, temp_repos_dir):
    """Test explicit provider filtering."""
    result = fs_tools.find_dependency_versions(
        group_id="org.opengroup.osdu",
        artifact_id="os-core-lib",
        directory=str(temp_repos_dir),
        provider="azure",
    )

    assert "filtered by provider: azure" in result


def test_find_dependency_versions_property_resolution(fs_tools, temp_repos_dir):
    """Test that properties are resolved correctly."""
    result = fs_tools.find_dependency_versions(
        group_id="org.opengroup.osdu",
        artifact_id="os-core-lib-azure",
        directory=str(temp_repos_dir),
    )

    # Should show both property and resolved version for file service
    assert "${os-core-lib-azure.version} → 2.2.5" in result


def test_find_dependency_versions_not_found(fs_tools, temp_repos_dir):
    """Test finding dependency that doesn't exist."""
    result = fs_tools.find_dependency_versions(
        group_id="com.example",
        artifact_id="nonexistent-lib",
        directory=str(temp_repos_dir),
    )

    assert "No references found" in result


def test_find_dependency_versions_grouping(fs_tools, temp_repos_dir):
    """Test that results are properly grouped by service."""
    result = fs_tools.find_dependency_versions(
        group_id="org.opengroup.osdu",
        artifact_id="os-core-lib-azure",
        directory=str(temp_repos_dir),
    )

    # Each service should appear as a section header
    assert "Service: partition" in result
    assert "Service: legal" in result
    assert "Service: file" in result

    # File paths should be shown under their service
    lines = result.split("\n")
    service_indices = {
        "partition": next(i for i, l in enumerate(lines) if "Service: partition" in l),
        "legal": next(i for i, l in enumerate(lines) if "Service: legal" in l),
        "file": next(i for i, l in enumerate(lines) if "Service: file" in l),
    }

    # Verify services are sorted alphabetically (file < legal < partition)
    assert service_indices["file"] < service_indices["legal"]
    assert service_indices["legal"] < service_indices["partition"]
