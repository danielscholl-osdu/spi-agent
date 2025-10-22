You are analyzing dependency update findings to create ACTIONABLE update lists organized by risk level.

## Your Task

Analyze the scan results and generate three lists: PATCH updates (low risk), MINOR updates (medium risk), and MAJOR updates (high risk).

## Scan Results

{{SCAN_RESULTS}}

## IMPORTANT: A dependency can appear in MULTIPLE lists

The scan results include TOP_UPDATES section with this format for each dependency:
```
1. groupId:artifactId
   Current: 1.3.60
   Patch: 1.3.72
   Minor: 1.9.25
   Major: 2.2.20
   Module: core
```

If a dependency has multiple update paths available, list it in ALL applicable categories:
- Has Patch version (not "none")? → Include in PATCH UPDATES list
- Has Minor version (not "none")? → Include in MINOR UPDATES list
- Has Major version (not "none")? → Include in MAJOR UPDATES list

Example: `org.jetbrains.kotlin:kotlin-stdlib` with Patch: 1.3.72, Minor: 1.9.25, Major: 2.2.20
- Appears in PATCH list with → Patch column showing 1.3.72
- Appears in MINOR list with → Minor column showing 1.9.25
- Appears in MAJOR list with → Major column showing 2.2.20

## Output Format

Provide your analysis in this EXACT format:

```markdown
# Dependency Update Recommendations

## Summary
- Total services analyzed: {count}
- Total dependencies scanned: {count}
- Patch updates available: {count}
- Minor updates available: {count}
- Major updates available: {count}

---

## PATCH UPDATES (Low Risk - Apply Anytime)

These updates contain only bug fixes and security patches. Safe to apply immediately.

| Dependency | Module | Current | → Patch | Services |
|------------|--------|---------|---------|----------|
| (list all dependencies with patch updates available) |

**IMPORTANT**: Include EVERY dependency that has a patch update, even if it also has minor/major updates.

**Action**: Apply all patch updates in a single batch PR per service. Low risk, high value.

---

## MINOR UPDATES (Medium Risk - Plan for Next Sprint)

These updates add new features while maintaining backward compatibility. Test thoroughly.

| Dependency | Module | Current | → Minor | Services |
|------------|--------|---------|---------|----------|
| (list all dependencies with minor updates available) |

**IMPORTANT**: Include EVERY dependency that has a minor update, even if it also has a patch or major update.

**Action**: Group related updates, update per module, run full test suite before merging.

---

## MAJOR UPDATES (High Risk - Requires Migration Planning)

These updates may contain breaking changes. Requires careful review, code changes, and testing.

| Dependency | Module | Current | → Major | Breaking Changes | Services |
|------------|--------|---------|---------|------------------|----------|
| (list all dependencies with major updates available) |

**IMPORTANT**: Include EVERY dependency that has a major update, even if it also has patch or minor updates.

**Action**: Create separate migration branches per major update. Update documentation, run regression tests, plan rollout.

---

## Next Steps

1. **Immediate (This Week)**: Apply all PATCH updates
   - Create single PR per service with all patch updates
   - Run CI/CD pipeline
   - Merge if green

2. **Short-term (Next Sprint)**: Plan MINOR updates
   - Group by module/functionality
   - Test in development environment
   - Create PRs with comprehensive testing

3. **Long-term (Next Quarter)**: Plan MAJOR updates
   - Create RFCs for major version migrations
   - Allocate dedicated time for testing
   - Plan staged rollout per service
```

## Guidelines

- Be concise and actionable
- Use tables for easy scanning
- Include module names so users know which POM to edit
- List ALL available updates (patch, minor, major) for each dependency
- DO NOT include placeholder/template rows like `{dependency} | {module}...` in the tables
- Only include actual dependencies from the scan results
- If no updates in a category, write "No patch/minor/major updates available" instead of showing an empty table
- Focus on what to do, not why (users can see the version numbers)
