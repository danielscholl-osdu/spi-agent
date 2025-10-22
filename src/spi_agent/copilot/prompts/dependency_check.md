You are analyzing Maven dependencies for the **{{SERVICE}}** service to identify available updates.

**Workspace**: {{WORKSPACE}}

## Your Task

1. **Find Module POMs**: Identify all relevant module POM files based on filtering criteria
2. **Extract Dependencies**: Use analyze_pom_file_tool on each module to collect ALL dependencies
3. **Batch Version Check**: Use check_version_batch_tool ONCE to check all dependencies against Maven Central
4. **Categorize Updates**: Classify available updates as major, minor, or patch based on semantic versioning
5. **Generate Report**: Provide a structured report with update recommendations

## IMPORTANT EFFICIENCY REQUIREMENTS

- Call analyze_pom_file_tool in PARALLEL for all module POMs (don't analyze them one-by-one)
- Collect ALL dependencies first, then make a SINGLE batch call to check_version_batch_tool
- DO NOT make individual check_version calls - always use batch
- Minimize thinking/processing time between tool calls

## Instructions

### Step 1: Analyze Parent POM First

IMPORTANT: Always start by analyzing the parent POM to understand property definitions:

```
analyze_pom_file_tool(pom_file_path="{{WORKSPACE}}/pom.xml", include_vulnerability_check=false)
```

This provides:
- Property definitions (e.g., `${spring-boot.version}`, `${lombok.version}`)
- Dependency management (BOMs and managed versions)
- Common dependencies across all modules

### Step 2: Find Module POMs

For multi-module Maven projects, module directories are typically under:
- `{{WORKSPACE}}/partition-core/pom.xml`
- `{{WORKSPACE}}/partition-core-plus/pom.xml`
- `{{WORKSPACE}}/provider/partition-azure/pom.xml`
- `{{WORKSPACE}}/provider/partition-aws/pom.xml`
- etc.

Based on the FILTER_INSTRUCTIONS below, identify which module POMs to analyze.

Common module patterns:
- Core module: `*-core` (ALWAYS include - base dependency for all)
- Core-plus module: `*-core-plus` (extended functionality - include only if filtering specifies it)
- Provider modules: `provider/*-azure`, `provider/*-aws`, `provider/*-gcp`, `provider/*-ibm`
- Testing modules: `testing/*`

IMPORTANT: The `*-core` module is ALWAYS analyzed as it's the base dependency. Other modules (core-plus, providers) are only analyzed if specified in the filter instructions.

### Step 3: Extract Dependencies in Parallel

Call analyze_pom_file_tool for ALL relevant module POMs in parallel:

```
# Example: For partition service with azure provider
# Analyze parent (for properties), core (always), and azure (requested provider)
analyze_pom_file_tool(pom_file_path="{{WORKSPACE}}/pom.xml", include_vulnerability_check=false)
analyze_pom_file_tool(pom_file_path="{{WORKSPACE}}/partition-core/pom.xml", include_vulnerability_check=false)
analyze_pom_file_tool(pom_file_path="{{WORKSPACE}}/provider/partition-azure/pom.xml", include_vulnerability_check=false)

# Example: For partition service with core-plus specified
# Analyze parent, core (always), and core-plus (requested)
analyze_pom_file_tool(pom_file_path="{{WORKSPACE}}/pom.xml", include_vulnerability_check=false)
analyze_pom_file_tool(pom_file_path="{{WORKSPACE}}/partition-core/pom.xml", include_vulnerability_check=false)
analyze_pom_file_tool(pom_file_path="{{WORKSPACE}}/partition-core-plus/pom.xml", include_vulnerability_check=false)
```

Each call returns:
- `dependencies`: Direct dependencies with resolved versions
- `managed_dependency_count`: Number of dependencies in <dependencyManagement>
- `property_references`: Number of ${...} property placeholders

### Step 4: Collect Unique Dependencies

From ALL analyze_pom_file results (parent + modules), collect unique dependencies. Format as:

```json
[
  {"dependency": "org.springframework.boot:spring-boot-starter", "version": "3.3.13"},
  {"dependency": "com.azure:azure-core", "version": "1.52.0"},
  ...
]
```

IMPORTANT: Only include dependencies with resolved versions (not ${...} placeholders or null)

### Step 5: Batch Check Versions (SINGLE CALL)

Make ONE call to check_version_batch_tool with ALL dependencies:

```
check_version_batch_tool(dependencies=[...])
```

Returns for each dependency:
- `exists`: Whether the current version exists on Maven Central
- `latest_major`: Latest major version available
- `latest_minor`: Latest minor version available
- `latest_patch`: Latest patch version available
- `has_updates`: Whether any updates are available

### Step 6: Categorize Updates

For each dependency with updates available:

**Major Update**: Current X.y.z → Latest (X+n).y.z where n > 0
- Example: 2.7.0 → 3.3.0
- Risk: May include breaking changes
- Priority: Review carefully before updating

**Minor Update**: Current x.Y.z → Latest x.(Y+n).z where Y increases
- Example: 2.15.0 → 2.18.0
- Risk: New features, backward compatible
- Priority: Medium - update when convenient

**Patch Update**: Current x.y.Z → Latest x.y.(Z+n) where only Z increases
- Example: 4.13.2 → 4.13.3
- Risk: Bug fixes only, lowest risk
- Priority: High - apply for security fixes

### Step 7: Generate Structured Report

Provide output in this EXACT format:

```
Total: {total_dependencies} dependencies scanned
Outdated: {outdated_count} dependencies
Major: {major_count} updates available
Minor: {minor_count} updates available
Patch: {patch_count} updates available

MODULE_BREAKDOWN:
{module_name} | {major} | {minor} | {patch}
...
END_MODULE_BREAKDOWN

TOP_UPDATES:
1. {groupId}:{artifactId}
   Current: {current_version}
   Patch: {patch_version or "none"}
   Minor: {minor_version or "none"}
   Major: {major_version or "none"}
   Module: {parent|core|core-plus|provider-name}
   Reason: {brief_reason}
...
END_TOP_UPDATES
```

**IMPORTANT**: For each dependency in TOP_UPDATES, include ALL available update versions from the batch check result:
- **Patch**: Latest patch version (e.g., 1.3.60 → 1.3.72) or "none" if no patch available
- **Minor**: Latest minor version (e.g., 1.3.60 → 1.9.25) or "none" if no minor available
- **Major**: Latest major version (e.g., 1.3.60 → 2.2.20) or "none" if no major available
- **Module**: Where declared (parent|core|core-plus|azure|aws|gcp|ibm)

Example:
```
1. org.jetbrains.kotlin:kotlin-stdlib
   Current: 1.3.60
   Patch: 1.3.72
   Minor: 1.9.25
   Major: 2.2.20
   Module: core
   Reason: Multiple update paths available
```

This allows the cross-service analysis to properly categorize each dependency into patch/minor/major lists.

## Filtering Instructions

{{FILTER_INSTRUCTIONS}}

## Output Format

Your response must include:

1. **Status Line**: `✓ {{SERVICE}}: Analysis complete - X major, Y minor, Z patch updates available`
2. **Summary Statistics**: Total dependencies, outdated count, percentages
3. **Module Breakdown**: Update counts per module (if multi-module project)
4. **Top Updates**: List top 10 most important updates with details
5. **Recommendations**: Prioritized action items

## Important Notes

- If POM parsing fails (tool returns error), report: "✗ Failed to parse POM file: [error details]"
- If version checking fails for a dependency, skip it and continue with others
- Focus on dependencies in the filtered modules only
- Provide clear, actionable recommendations
- Start immediately with Step 1 - don't check if files exist, just try to analyze them
