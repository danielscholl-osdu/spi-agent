"""Unit tests for coverage parsing functionality in TestRunner."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from spi_agent.copilot.runners.test_runner import TestRunner
from spi_agent.copilot.trackers import TestTracker


@pytest.fixture
def test_runner():
    """Create a TestRunner instance for testing."""
    # Create a mock prompt file
    mock_prompt = MagicMock()
    mock_prompt.read_text.return_value = "Test prompt"

    runner = TestRunner(
        prompt_file=mock_prompt,
        services=["test-service"],
        provider="azure"
    )

    # Mock the logger to avoid actual logging during tests
    runner.logger = Mock(spec=logging.Logger)

    return runner


@pytest.fixture
def temp_coverage_dir(tmp_path):
    """Create a temporary directory structure for coverage reports."""
    service_dir = tmp_path / "test-service"
    jacoco_dir = service_dir / "target" / "site" / "jacoco"
    jacoco_dir.mkdir(parents=True, exist_ok=True)
    return service_dir


class TestCSVCoverageExtraction:
    """Tests for CSV-based coverage extraction."""

    def test_parse_jacoco_csv_valid(self, test_runner, temp_coverage_dir):
        """Test parsing a valid JaCoCo CSV file."""
        csv_path = temp_coverage_dir / "target" / "site" / "jacoco" / "jacoco.csv"

        # Create a sample CSV with realistic coverage data
        csv_content = """GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
com.example,com.example.service,ServiceImpl,100,500,10,40,20,80,5,15,2,8
com.example,com.example.util,HelperClass,50,250,5,20,10,40,3,7,1,4
"""
        csv_path.write_text(csv_content)

        line_cov, branch_cov = test_runner._extract_coverage_from_csv("test-service", temp_coverage_dir)

        # Expected: Line coverage = (80+40)/(20+80+10+40) = 120/150 = 80%
        #           Branch coverage = (40+20)/(10+40+5+20) = 60/75 = 80%
        assert line_cov == 80.0
        assert branch_cov == 80.0

    def test_parse_jacoco_csv_empty(self, test_runner, temp_coverage_dir):
        """Test handling of an empty CSV file."""
        csv_path = temp_coverage_dir / "target" / "site" / "jacoco" / "jacoco.csv"

        # Create an empty CSV with just the header
        csv_content = """GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
"""
        csv_path.write_text(csv_content)

        line_cov, branch_cov = test_runner._extract_coverage_from_csv("test-service", temp_coverage_dir)

        # Empty CSV should return 0% coverage
        assert line_cov == 0.0
        assert branch_cov == 0.0

    def test_parse_jacoco_csv_missing(self, test_runner, temp_coverage_dir):
        """Test handling of a missing CSV file."""
        # Don't create the CSV file

        line_cov, branch_cov = test_runner._extract_coverage_from_csv("test-service", temp_coverage_dir)

        # Missing CSV should return 0% coverage
        assert line_cov == 0.0
        assert branch_cov == 0.0

    def test_parse_jacoco_csv_malformed_rows(self, test_runner, temp_coverage_dir):
        """Test handling of malformed CSV rows."""
        csv_path = temp_coverage_dir / "target" / "site" / "jacoco" / "jacoco.csv"

        # Create a CSV with some malformed rows
        csv_content = """GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
com.example,com.example.service,ServiceImpl,100,500,10,40,20,80,5,15,2,8
invalid,row,with,not,enough,columns
com.example,com.example.util,HelperClass,50,250,5,20,10,40,3,7,1,4
"""
        csv_path.write_text(csv_content)

        line_cov, branch_cov = test_runner._extract_coverage_from_csv("test-service", temp_coverage_dir)

        # Should skip malformed row and parse valid rows
        # Expected: Line coverage = (80+40)/(20+80+10+40) = 80%
        assert line_cov == 80.0
        assert branch_cov == 80.0

    def test_parse_jacoco_csv_multiple_modules(self, test_runner, temp_coverage_dir):
        """Test parsing CSV files from multiple modules and aggregating data."""
        # Create CSV in main module
        main_csv = temp_coverage_dir / "target" / "site" / "jacoco" / "jacoco.csv"
        main_csv_content = """GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
com.example,com.example.main,MainClass,100,400,10,30,20,60,5,10,2,6
"""
        main_csv.write_text(main_csv_content)

        # Create CSV in provider subdirectory
        provider_dir = temp_coverage_dir / "provider" / "azure-provider" / "target" / "site" / "jacoco"
        provider_dir.mkdir(parents=True, exist_ok=True)
        provider_csv = provider_dir / "jacoco.csv"
        provider_csv_content = """GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
com.example.provider,com.example.provider.azure,AzureProvider,50,200,5,10,10,20,3,5,1,3
"""
        provider_csv.write_text(provider_csv_content)

        line_cov, branch_cov = test_runner._extract_coverage_from_csv("test-service", temp_coverage_dir)

        # Expected: Line coverage = (60+20)/(20+60+10+20) = 80/110 = 72.72%
        #           Branch coverage = (30+10)/(10+30+5+10) = 40/55 = 72.72%
        assert pytest.approx(line_cov, 0.01) == 72.72
        assert pytest.approx(branch_cov, 0.01) == 72.72

    def test_parse_jacoco_csv_zero_total_lines(self, test_runner, temp_coverage_dir):
        """Test handling when total lines and branches are zero."""
        csv_path = temp_coverage_dir / "target" / "site" / "jacoco" / "jacoco.csv"

        # CSV with all zeros
        csv_content = """GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
com.example,com.example.empty,EmptyClass,0,0,0,0,0,0,0,0,0,0
"""
        csv_path.write_text(csv_content)

        line_cov, branch_cov = test_runner._extract_coverage_from_csv("test-service", temp_coverage_dir)

        # Should handle division by zero gracefully
        assert line_cov == 0.0
        assert branch_cov == 0.0


class TestHTMLCoverageExtraction:
    """Tests for HTML-based coverage extraction (fallback)."""

    def test_extract_coverage_from_html_valid(self, test_runner, temp_coverage_dir):
        """Test parsing a valid JaCoCo HTML file."""
        html_path = temp_coverage_dir / "target" / "site" / "jacoco" / "index.html"

        # Create a sample HTML report with JaCoCo structure
        html_content = """<!DOCTYPE html>
<html>
<body>
<table>
<tfoot>
<tr>
<td>Total</td>
<td class="bar">200 of 1,000</td>
<td class="ctr2">80%</td>
<td class="bar">10 of 50</td>
<td class="ctr2">80%</td>
<td class="ctr1">20</td>
<td class="ctr2">100</td>
<td class="ctr1">10</td>
<td class="ctr2">90</td>
</tr>
</tfoot>
</table>
</body>
</html>"""
        html_path.write_text(html_content)

        line_cov, branch_cov = test_runner._extract_coverage_from_html("test-service", temp_coverage_dir)

        # Expected: Branch coverage = (50-10)/50 = 80%
        #           Line coverage = (90-10)/90 = 88%
        assert branch_cov == 80
        assert line_cov == 88

    def test_extract_coverage_from_html_missing(self, test_runner, temp_coverage_dir):
        """Test handling of missing HTML file."""
        # Don't create the HTML file

        line_cov, branch_cov = test_runner._extract_coverage_from_html("test-service", temp_coverage_dir)

        # Missing HTML should return 0% coverage
        assert line_cov == 0
        assert branch_cov == 0


class TestCoverageExtractionPriority:
    """Tests for coverage extraction priority (CSV before HTML)."""

    def test_csv_priority_over_html(self, test_runner, temp_coverage_dir):
        """Test that CSV is tried before HTML."""
        # Create both CSV and HTML with different values
        csv_path = temp_coverage_dir / "target" / "site" / "jacoco" / "jacoco.csv"
        csv_content = """GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
com.example,com.example.service,ServiceImpl,100,900,10,90,20,180,5,45,2,18
"""
        csv_path.write_text(csv_content)

        html_path = temp_coverage_dir / "target" / "site" / "jacoco" / "index.html"
        html_content = """<!DOCTYPE html>
<html>
<body>
<table>
<tfoot>
<tr>
<td>Total</td>
<td class="bar">500 of 1,000</td>
<td class="ctr2">50%</td>
<td class="bar">25 of 50</td>
<td class="ctr2">50%</td>
<td class="ctr1">50</td>
<td class="ctr2">100</td>
<td class="ctr1">25</td>
<td class="ctr2">75</td>
</tr>
</tfoot>
</table>
</body>
</html>"""
        html_path.write_text(html_content)

        line_cov, branch_cov = test_runner._extract_coverage_from_csv("test-service", temp_coverage_dir)

        # Should use CSV values (90% coverage), not HTML values (50% coverage)
        assert line_cov == 90.0
        assert branch_cov == 90.0


class TestQualityGradeCalculation:
    """Tests for quality grade calculation based on coverage."""

    def test_grade_a_excellent(self, test_runner):
        """Test grade A is assigned for excellent coverage."""
        test_runner.tracker.services["test-service"]["coverage_line"] = 95
        test_runner.tracker.services["test-service"]["coverage_branch"] = 90

        test_runner._assess_coverage_quality()

        assert test_runner.tracker.services["test-service"]["quality_grade"] == "A"
        assert test_runner.tracker.services["test-service"]["quality_label"] == "Excellent"

    def test_grade_b_good(self, test_runner):
        """Test grade B is assigned for good coverage."""
        test_runner.tracker.services["test-service"]["coverage_line"] = 85
        test_runner.tracker.services["test-service"]["coverage_branch"] = 75

        test_runner._assess_coverage_quality()

        assert test_runner.tracker.services["test-service"]["quality_grade"] == "B"
        assert test_runner.tracker.services["test-service"]["quality_label"] == "Good"

    def test_grade_c_acceptable(self, test_runner):
        """Test grade C is assigned for acceptable coverage."""
        test_runner.tracker.services["test-service"]["coverage_line"] = 75
        test_runner.tracker.services["test-service"]["coverage_branch"] = 65

        test_runner._assess_coverage_quality()

        assert test_runner.tracker.services["test-service"]["quality_grade"] == "C"
        assert test_runner.tracker.services["test-service"]["quality_label"] == "Acceptable"

    def test_grade_d_needs_improvement(self, test_runner):
        """Test grade D is assigned for coverage needing improvement."""
        test_runner.tracker.services["test-service"]["coverage_line"] = 65
        test_runner.tracker.services["test-service"]["coverage_branch"] = 55

        test_runner._assess_coverage_quality()

        assert test_runner.tracker.services["test-service"]["quality_grade"] == "D"
        assert test_runner.tracker.services["test-service"]["quality_label"] == "Needs Improvement"

    def test_grade_f_poor(self, test_runner):
        """Test grade F is assigned for poor coverage."""
        test_runner.tracker.services["test-service"]["coverage_line"] = 45
        test_runner.tracker.services["test-service"]["coverage_branch"] = 35

        test_runner._assess_coverage_quality()

        assert test_runner.tracker.services["test-service"]["quality_grade"] == "F"
        assert test_runner.tracker.services["test-service"]["quality_label"] == "Poor"

    def test_grade_f_zero_coverage(self, test_runner):
        """Test grade None with specific label is assigned for zero coverage."""
        test_runner.tracker.services["test-service"]["coverage_line"] = 0
        test_runner.tracker.services["test-service"]["coverage_branch"] = 0

        test_runner._assess_coverage_quality()

        # Zero coverage returns None grade to distinguish from actual "F" grade
        assert test_runner.tracker.services["test-service"]["quality_grade"] is None
        assert test_runner.tracker.services["test-service"]["quality_label"] == "No Coverage Data"
        assert "JaCoCo plugin" in test_runner.tracker.services["test-service"]["quality_summary"]

    def test_zero_coverage_recommendations(self, test_runner):
        """Test that zero coverage provides specific recommendations."""
        test_runner.tracker.services["test-service"]["coverage_line"] = 0
        test_runner.tracker.services["test-service"]["coverage_branch"] = 0

        test_runner._assess_coverage_quality()

        recommendations = test_runner.tracker.services["test-service"]["recommendations"]
        assert len(recommendations) >= 2
        assert "JaCoCo" in recommendations[0]["action"]
        assert "tests are being executed" in recommendations[1]["action"]

    def test_low_branch_coverage_recommendation(self, test_runner):
        """Test recommendation for low branch coverage compared to line coverage."""
        test_runner.tracker.services["test-service"]["coverage_line"] = 85
        test_runner.tracker.services["test-service"]["coverage_branch"] = 50

        test_runner._assess_coverage_quality()

        recommendations = test_runner.tracker.services["test-service"]["recommendations"]
        # Should recommend improving branch coverage
        assert any("branch coverage" in rec["action"].lower() for rec in recommendations)

    def test_low_line_coverage_recommendation(self, test_runner):
        """Test recommendation for low line coverage."""
        test_runner.tracker.services["test-service"]["coverage_line"] = 60
        test_runner.tracker.services["test-service"]["coverage_branch"] = 55

        test_runner._assess_coverage_quality()

        recommendations = test_runner.tracker.services["test-service"]["recommendations"]
        # Should recommend adding unit tests
        assert any("unit tests" in rec["action"].lower() for rec in recommendations)

    def test_high_coverage_maintenance_recommendation(self, test_runner):
        """Test that high coverage gets maintenance recommendation."""
        test_runner.tracker.services["test-service"]["coverage_line"] = 95
        test_runner.tracker.services["test-service"]["coverage_branch"] = 90

        test_runner._assess_coverage_quality()

        recommendations = test_runner.tracker.services["test-service"]["recommendations"]
        # Should recommend maintaining current levels
        assert any("maintain" in rec["action"].lower() for rec in recommendations)


class TestMultiProfileCoverageExtraction:
    """Tests for multi-profile coverage extraction."""

    @pytest.fixture
    def multi_profile_runner(self):
        """Create a TestRunner with multiple profiles."""
        mock_prompt = MagicMock()
        mock_prompt.read_text.return_value = "Test prompt"

        runner = TestRunner(
            prompt_file=mock_prompt,
            services=["partition"],
            provider="core,core-plus,azure"
        )
        runner.logger = Mock(spec=logging.Logger)
        return runner

    @pytest.fixture
    def partition_service_dir(self, tmp_path):
        """Create a realistic partition service directory structure."""
        partition_dir = tmp_path / "partition"
        partition_dir.mkdir()

        # Create core module
        core_dir = partition_dir / "partition-core"
        core_jacoco = core_dir / "target" / "site" / "jacoco"
        core_jacoco.mkdir(parents=True, exist_ok=True)

        # Create core-plus module
        core_plus_dir = partition_dir / "partition-core-plus"
        core_plus_jacoco = core_plus_dir / "target" / "site" / "jacoco"
        core_plus_jacoco.mkdir(parents=True, exist_ok=True)

        # Create azure provider module
        azure_dir = partition_dir / "providers" / "partition-azure"
        azure_jacoco = azure_dir / "target" / "site" / "jacoco"
        azure_jacoco.mkdir(parents=True, exist_ok=True)

        return partition_dir

    def test_map_profile_to_modules_core(self, multi_profile_runner, partition_service_dir):
        """Test mapping 'core' profile to module directories."""
        modules = multi_profile_runner._map_profile_to_modules("partition", partition_service_dir, "core")

        assert len(modules) == 1
        assert any("partition-core" in str(m) for m in modules)
        assert not any("core-plus" in str(m) for m in modules)

    def test_map_profile_to_modules_core_plus(self, multi_profile_runner, partition_service_dir):
        """Test mapping 'core-plus' profile to module directories."""
        modules = multi_profile_runner._map_profile_to_modules("partition", partition_service_dir, "core-plus")

        assert len(modules) == 1
        assert any("core-plus" in str(m) for m in modules)

    def test_map_profile_to_modules_azure(self, multi_profile_runner, partition_service_dir):
        """Test mapping 'azure' profile to provider module."""
        modules = multi_profile_runner._map_profile_to_modules("partition", partition_service_dir, "azure")

        assert len(modules) == 1
        assert any("partition-azure" in str(m) for m in modules)

    def test_profile_specific_csv_extraction_core(self, multi_profile_runner, partition_service_dir):
        """Test extracting coverage for core profile only."""
        # Create core module CSV
        core_csv = partition_service_dir / "partition-core" / "target" / "site" / "jacoco" / "jacoco.csv"
        core_csv.write_text("""GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
org.opengroup.osdu.partition.core,org.opengroup.osdu.partition.core.service,CoreService,20,180,10,90,10,90,5,45,2,18
""")

        line_cov, branch_cov = multi_profile_runner._extract_coverage_from_csv("partition", partition_service_dir, profile="core")

        # Expected: 90% line and branch coverage
        assert line_cov == 90.0
        assert branch_cov == 90.0

    def test_profile_specific_csv_extraction_azure(self, multi_profile_runner, partition_service_dir):
        """Test extracting coverage for azure profile only."""
        # Create azure module CSV
        azure_csv = partition_service_dir / "providers" / "partition-azure" / "target" / "site" / "jacoco" / "jacoco.csv"
        azure_csv.write_text("""GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
org.opengroup.osdu.partition.azure,org.opengroup.osdu.partition.azure.provider,AzureProvider,4,96,2,48,2,48,1,24,0,12
""")

        line_cov, branch_cov = multi_profile_runner._extract_coverage_from_csv("partition", partition_service_dir, profile="azure")

        # Expected: 96% line, 96% branch coverage
        assert line_cov == 96.0
        assert branch_cov == 96.0

    def test_profile_isolation_core_vs_core_plus(self, multi_profile_runner, partition_service_dir):
        """Test that core and core-plus profiles are properly isolated."""
        # Create core CSV
        core_csv = partition_service_dir / "partition-core" / "target" / "site" / "jacoco" / "jacoco.csv"
        core_csv.write_text("""GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
org.opengroup.osdu.partition.core,org.opengroup.osdu.partition.core.service,CoreService,10,90,5,45,5,45,2,23,1,11
""")

        # Create core-plus CSV
        core_plus_csv = partition_service_dir / "partition-core-plus" / "target" / "site" / "jacoco" / "jacoco.csv"
        core_plus_csv.write_text("""GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
org.opengroup.osdu.partition.coreplus,org.opengroup.osdu.partition.coreplus.service,CorePlusService,20,80,10,40,10,40,5,20,2,10
""")

        # Extract coverage for core (should not include core-plus)
        core_line, core_branch = multi_profile_runner._extract_coverage_from_csv("partition", partition_service_dir, profile="core")
        assert core_line == 90.0
        assert core_branch == 90.0

        # Extract coverage for core-plus (should not include core)
        plus_line, plus_branch = multi_profile_runner._extract_coverage_from_csv("partition", partition_service_dir, profile="core-plus")
        assert plus_line == 80.0
        assert plus_branch == 80.0

    def test_multi_profile_consistency(self, multi_profile_runner, partition_service_dir):
        """Test that multiple runs return consistent results."""
        # Create CSV files
        core_csv = partition_service_dir / "partition-core" / "target" / "site" / "jacoco" / "jacoco.csv"
        core_csv.write_text("""GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
org.opengroup.osdu.partition.core,org.opengroup.osdu.partition.core.service,CoreService,2,98,1,49,1,49,1,24,0,12
""")

        # Run extraction multiple times
        results = []
        for _ in range(3):
            line_cov, branch_cov = multi_profile_runner._extract_coverage_from_csv("partition", partition_service_dir, profile="core")
            results.append((line_cov, branch_cov))

        # All results should be identical
        assert len(set(results)) == 1
        assert results[0][0] == 98.0
        assert results[0][1] == 98.0

    def test_module_naming_variations(self, multi_profile_runner, tmp_path):
        """Test various module naming conventions."""
        service_dir = tmp_path / "test-service"
        service_dir.mkdir()

        # Test different naming patterns
        patterns = [
            "test-service-azure",     # Pattern: {service}-{profile}
            "azure",                  # Pattern: {profile} only
            "provider-azure",         # Pattern: provider-{profile}
        ]

        for pattern in patterns:
            module_dir = service_dir / pattern
            jacoco_dir = module_dir / "target" / "site" / "jacoco"
            jacoco_dir.mkdir(parents=True, exist_ok=True)

            csv_path = jacoco_dir / "jacoco.csv"
            csv_path.write_text("""GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
com.example,com.example.azure,AzureImpl,10,90,5,45,5,45,2,23,1,11
""")

        # Should find all azure modules
        modules = multi_profile_runner._map_profile_to_modules("test-service", service_dir, "azure")
        assert len(modules) >= 1

    def test_fallback_to_aggregated_csv_filtering(self, multi_profile_runner, tmp_path):
        """Test fallback to aggregated CSV when no module directories found."""
        service_dir = tmp_path / "test-service"
        service_dir.mkdir()

        # Create aggregated CSV at root level with profile-specific packages
        aggregated_csv = service_dir / "target" / "site" / "jacoco"
        aggregated_csv.mkdir(parents=True, exist_ok=True)
        csv_path = aggregated_csv / "jacoco.csv"

        csv_path.write_text("""GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
org.example.core,org.example.core.service,CoreService,10,90,5,45,5,45,2,23,1,11
org.example.azure,org.example.azure.provider,AzureProvider,20,80,10,40,10,40,5,20,2,10
""")

        # Extract for core profile - should filter rows
        line_cov, branch_cov = multi_profile_runner._extract_coverage_from_csv("test-service", service_dir, profile="core")
        assert line_cov == 90.0
        assert branch_cov == 90.0

        # Extract for azure profile - should filter rows
        line_cov, branch_cov = multi_profile_runner._extract_coverage_from_csv("test-service", service_dir, profile="azure")
        assert line_cov == 80.0
        assert branch_cov == 80.0


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_csv_with_non_numeric_values_in_coverage_columns(self, test_runner, temp_coverage_dir):
        """Test handling of CSV with non-numeric values in coverage columns."""
        csv_path = temp_coverage_dir / "target" / "site" / "jacoco" / "jacoco.csv"

        # CSV with invalid numeric values in coverage columns (columns 5-8)
        csv_content = """GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
com.example,com.example.service,ServiceImpl,100,500,invalid,40,20,80,5,15,2,8
"""
        csv_path.write_text(csv_content)

        line_cov, branch_cov = test_runner._extract_coverage_from_csv("test-service", temp_coverage_dir)

        # Should skip the row with invalid coverage values and return 0%
        assert line_cov == 0.0
        assert branch_cov == 0.0

    def test_partial_coverage_only_lines(self, test_runner):
        """Test grade calculation when only line coverage exists."""
        test_runner.tracker.services["test-service"]["coverage_line"] = 80
        test_runner.tracker.services["test-service"]["coverage_branch"] = 0

        test_runner._assess_coverage_quality()

        # Should still assign a grade based on available data
        grade = test_runner.tracker.services["test-service"]["quality_grade"]
        assert grade in ["A", "B", "C", "D", "F"]

    def test_partial_coverage_only_branches(self, test_runner):
        """Test grade calculation when only branch coverage exists."""
        test_runner.tracker.services["test-service"]["coverage_line"] = 0
        test_runner.tracker.services["test-service"]["coverage_branch"] = 80

        test_runner._assess_coverage_quality()

        # Should still assign a grade
        grade = test_runner.tracker.services["test-service"]["quality_grade"]
        assert grade in ["A", "B", "C", "D", "F"]
