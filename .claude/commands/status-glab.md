# GitLab Status Command

Get comprehensive status for OSDU SPI GitLab repositories with provider-based filtering.

## Usage

```bash
spi-agent status-glab --projects PROJECTS [--provider PROVIDERS]
```

## Arguments

- `--projects, -p` (required): Project name(s) to check status
  - Single project: `partition`
  - Multiple projects: `partition,legal,entitlements`
  - All projects: `all`

- `--provider` (optional, default: `Azure,Core`): Provider labels to filter by
  - Single provider: `Azure`
  - Multiple providers: `Azure,Core`
  - Custom providers: `gcp,aws`

## Examples

```bash
# Check partition project with default providers (azure,core)
spi-agent status-glab --projects partition

# Check multiple projects with Azure provider only
spi-agent status-glab --projects partition,legal --provider azure

# Check all projects with both Azure and Core providers
spi-agent status-glab --projects all --provider azure,core

# Check single project with custom provider
spi-agent status-glab --projects storage --provider gcp
```

## What It Shows

- **Project Information**: GitLab project exists, URL, last updated
- **Open Issues**: Filtered by provider labels (azure, core, etc.)
- **Merge Requests**: Filtered by provider labels, showing draft status
- **Pipeline Runs**: Recent CI/CD pipeline status (success, failed, running)
- **Next Steps**: Actionable items for failed pipelines, open MRs

## Provider Filtering

Provider filtering uses GitLab labels on issues and merge requests:
- **Azure**: Items related to Azure provider
- **Core**: Items related to core functionality
- **GCP**: Items related to Google Cloud provider
- **AWS**: Items related to AWS provider

**Note:** GitLab labels are case-sensitive. Use capitalized names (Azure, Core, etc.).

When multiple providers are specified (e.g., `Azure,Core`), items with ANY of those labels are shown.

## Available Projects

partition, entitlements, legal, schema, file, storage, indexer, indexer-queue, search, workflow
