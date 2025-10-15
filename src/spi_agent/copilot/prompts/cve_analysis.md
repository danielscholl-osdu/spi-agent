# CVE Analysis Prompt

Analyze the following Maven triage scan results and create a consolidated CVE report.

**CRITICAL PRIORITY**: Focus on CVEs that affect MULTIPLE services - these have the biggest impact and should be fixed first.

## Output Format Required

### 1. CROSS-SERVICE VULNERABILITIES (Highest Priority)

List CVEs that appear in MULTIPLE services (e.g., partition AND legal)

For each CVE:
- CVE ID and Severity (Critical/High)
- Affected package
- Impact: brief 1-line description
- Fix: version to upgrade to
- Services: list all affected services

### 2. SERVICE-SPECIFIC CRITICAL/HIGH CVEs

List top critical/high CVEs unique to each service (top 5 max per service)

Same format as above but note which single service is affected

### 3. IMMEDIATE ACTION ITEMS

Numbered list of prioritized actions to take, grouped by:
- Priority 1: Cross-service critical CVEs
- Priority 2: Service-specific critical CVEs
- Priority 3: High-severity CVEs

**STOP after this section. Do not add any summary, recommendations, or additional commentary.**

## Guidelines

- **Keep it concise and actionable** - focus on what needs to be patched
- Prioritize by impact: cross-service vulnerabilities first, then critical, then high
- Include specific version numbers for fixes
- Use clear formatting with bullet points
- **DO NOT include**: mitigation strategies, workflow recommendations, general security advice, summaries, or recommended approaches
- **ONLY provide**: The 3 sections above (Cross-service CVEs, Service-specific CVEs, Immediate action items)
- **End the report immediately after section 3**

## Scan Results

{{SCAN_RESULTS}}

Generate the CVE report now:
