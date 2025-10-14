ARGUMENTS:
    REPORT_PATH: (REQUIRED) Path to the JaCoCo HTML coverage report (index.html)
    SERVICE_NAME: (REQUIRED) Name of the service being assessed

INSTRUCTIONS:
    1. Read and analyze the JaCoCo HTML coverage report
    2. Evaluate the quality of test coverage based on industry standards
    3. Identify areas of concern and opportunities for improvement
    4. Provide a quality grade and actionable recommendations
    5. Return results ONLY as valid JSON - NO additional narrative or explanation

QUALITY_GRADING_CRITERIA:
    A (Excellent):
        - Line coverage >= 90%
        - Branch coverage >= 85%
        - Critical paths well-covered
        - No major gaps in core functionality

    B (Good):
        - Line coverage >= 80%
        - Branch coverage >= 70%
        - Most critical paths covered
        - Minor gaps in edge cases

    C (Acceptable):
        - Line coverage >= 70%
        - Branch coverage >= 60%
        - Core functionality covered
        - Some gaps in error handling

    D (Needs Improvement):
        - Line coverage >= 60%
        - Branch coverage >= 50%
        - Basic functionality covered
        - Significant gaps present

    F (Poor):
        - Line coverage < 60%
        - Branch coverage < 50%
        - Major gaps in coverage
        - Critical paths not tested

ANALYSIS_TASKS:
    1. EXTRACT_METRICS:
        - Parse the <tfoot> section for overall coverage statistics
        - Extract line, branch, instruction, and complexity coverage
        - Identify total lines, branches, and methods

    2. ANALYZE_PACKAGE_COVERAGE:
        - Review coverage by package/namespace
        - Identify packages with low coverage
        - Note packages with excellent coverage

    3. IDENTIFY_CRITICAL_GAPS:
        - Look for classes with 0% coverage
        - Identify core business logic with low coverage
        - Find error handling and edge cases not tested

    4. ASSESS_COMPLEXITY:
        - Review cyclomatic complexity coverage
        - Identify complex methods with low coverage
        - Highlight high-risk areas needing attention

    5. GENERATE_RECOMMENDATIONS:
        - Provide 3-5 specific, actionable recommendations
        - Prioritize by impact and effort
        - Include specific files or classes to focus on

OUTPUT_FORMAT:

CRITICAL: Your response must be ONLY the JSON output below. Do not include any narrative, explanations, or markdown code fences. Just raw JSON.

{
  "service": "partition",
  "timestamp": "2025-01-06T10:30:00Z",
  "metrics": {
    "line_coverage": 85.5,
    "branch_coverage": 72.3,
    "instruction_coverage": 83.2,
    "complexity_coverage": 78.9,
    "total_lines": 1250,
    "covered_lines": 1069,
    "total_branches": 186,
    "covered_branches": 134,
    "total_methods": 145,
    "covered_methods": 132
  },
  "quality_grade": "B",
  "quality_label": "Good",
  "quality_summary": "The codebase has good test coverage with most critical paths tested. Some improvements needed in error handling and edge cases.",
  "strengths": [
    "Core business logic is well-tested with 90%+ coverage",
    "All API endpoints have integration tests",
    "Critical security components have 100% coverage"
  ],
  "weaknesses": [
    "Exception handling paths have only 45% coverage",
    "Utility classes are under-tested at 60% coverage",
    "Complex validation logic in XYZ class lacks branch coverage"
  ],
  "package_analysis": [
    {
      "package": "org.opengroup.osdu.partition.provider.azure.service",
      "line_coverage": 92.5,
      "status": "excellent"
    },
    {
      "package": "org.opengroup.osdu.partition.provider.azure.utils",
      "line_coverage": 65.2,
      "status": "needs_improvement"
    }
  ],
  "high_risk_areas": [
    {
      "class": "AuthorizationService",
      "reason": "Complex authorization logic with only 55% branch coverage",
      "risk_level": "high"
    },
    {
      "class": "DataValidator",
      "reason": "Validation methods have 0% coverage",
      "risk_level": "critical"
    }
  ],
  "recommendations": [
    {
      "priority": 1,
      "effort": "low",
      "impact": "high",
      "action": "Add unit tests for DataValidator class",
      "target": "org.opengroup.osdu.partition.provider.azure.utils.DataValidator",
      "expected_improvement": "+8% overall coverage"
    },
    {
      "priority": 2,
      "effort": "medium",
      "impact": "high",
      "action": "Improve branch coverage for AuthorizationService.checkPermissions()",
      "target": "org.opengroup.osdu.partition.provider.azure.utils.AuthorizationService",
      "expected_improvement": "+5% branch coverage"
    },
    {
      "priority": 3,
      "effort": "low",
      "impact": "medium",
      "action": "Add edge case tests for exception handling paths",
      "target": "Exception handlers in service layer",
      "expected_improvement": "+3% overall coverage"
    },
    {
      "priority": 4,
      "effort": "high",
      "impact": "medium",
      "action": "Implement integration tests for error scenarios",
      "target": "API error responses",
      "expected_improvement": "Better error handling validation"
    },
    {
      "priority": 5,
      "effort": "medium",
      "impact": "low",
      "action": "Add tests for utility methods in Helper classes",
      "target": "Utility package",
      "expected_improvement": "+2% overall coverage"
    }
  ],
  "trend_suggestion": "Focus on improving branch coverage in complex business logic methods. Current trajectory suggests reaching 80% branch coverage is achievable with 2-3 days of focused testing effort."
}

IMPORTANT_RULES:
1. Always extract actual numbers from the HTML report, don't estimate
2. Base the quality grade strictly on the grading criteria above
3. Provide specific class/method names in recommendations when possible
4. Prioritize recommendations by impact-to-effort ratio
5. Keep recommendations actionable and specific
6. DO NOT wrap JSON in markdown code fences or add any explanatory text
7. Ensure all percentages are numbers (not strings) in the JSON
8. Include at least 3 but no more than 5 recommendations