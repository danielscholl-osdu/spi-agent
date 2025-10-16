"""File system tools for local repository operations."""

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Annotated, Optional

from pydantic import Field

from spi_agent.config import AgentConfig


class FileSystemTools:
    """Tools for file system operations on local repositories."""

    def __init__(self, config: AgentConfig):
        """
        Initialize file system tools.

        Args:
            config: Agent configuration
        """
        self.config = config
        self.repos_dir = Path("./repos")

    def list_files(
        self,
        pattern: Annotated[
            str,
            Field(
                description="File pattern to match (e.g., '*.xml', 'pom.xml', '**/*.java'). "
                "Use '**/' for recursive search."
            ),
        ],
        directory: Annotated[
            Optional[str],
            Field(
                description="Directory to search in (relative to project root, e.g., 'repos/partition'). "
                "Defaults to './repos' if not specified."
            ),
        ] = None,
        limit: Annotated[
            int, Field(description="Maximum number of files to return")
        ] = 100,
    ) -> str:
        """
        List files matching a pattern in a directory.

        Returns formatted string with file paths.
        """
        try:
            search_dir = Path(directory) if directory else self.repos_dir

            if not search_dir.exists():
                return f"Directory not found: {search_dir}"

            # Use glob to find matching files
            if "**" in pattern:
                # Recursive search
                matches = list(search_dir.glob(pattern))
            else:
                # Non-recursive search
                matches = list(search_dir.glob(pattern))

            # Filter out directories, keep only files
            files = [f for f in matches if f.is_file()][:limit]

            if not files:
                return f"No files found matching pattern '{pattern}' in {search_dir}"

            # Format results
            output_lines = [
                f"Found {len(files)} file(s) matching '{pattern}' in {search_dir}:\n\n"
            ]
            for file_path in files:
                try:
                    rel_path = file_path.relative_to(Path.cwd())
                except ValueError:
                    # Path is not relative to cwd (e.g., in temp dir), use absolute
                    rel_path = file_path
                output_lines.append(f"  {rel_path}\n")

            if len(matches) > limit:
                output_lines.append(
                    f"\n(Showing first {limit} of {len(matches)} matches)"
                )

            return "".join(output_lines)

        except Exception as e:
            return f"Error listing files: {str(e)}"

    def read_file(
        self,
        file_path: Annotated[
            str,
            Field(
                description="Path to the file to read (e.g., 'repos/partition/pom.xml')"
            ),
        ],
        max_lines: Annotated[
            Optional[int],
            Field(description="Maximum number of lines to read (useful for large files)"),
        ] = None,
    ) -> str:
        """
        Read contents of a file.

        Returns formatted string with file contents.
        """
        try:
            path = Path(file_path)

            if not path.exists():
                return f"File not found: {file_path}"

            if not path.is_file():
                return f"Path is not a file: {file_path}"

            # Read file contents
            with open(path, "r", encoding="utf-8") as f:
                if max_lines:
                    lines = [f.readline() for _ in range(max_lines)]
                    lines = [l for l in lines if l]  # Filter empty strings
                    content = "".join(lines)
                    truncated = len(lines) == max_lines
                else:
                    content = f.read()
                    truncated = False

            # Check if content is too large
            if len(content) > 50000:  # 50KB limit
                content = content[:50000]
                truncated = True

            output = [f"Contents of {file_path}:\n\n", f"{content}\n"]

            if truncated:
                output.append("\n(Content truncated)")

            return "".join(output)

        except UnicodeDecodeError:
            return f"Error: Unable to read file as text (binary file?): {file_path}"
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def search_in_files(
        self,
        search_pattern: Annotated[
            str, Field(description="Text or regex pattern to search for")
        ],
        file_pattern: Annotated[
            str,
            Field(
                description="File pattern to search in (e.g., '*.xml', '**/*.java')"
            ),
        ] = "**/*",
        directory: Annotated[
            Optional[str],
            Field(description="Directory to search in (defaults to './repos')"),
        ] = None,
        context_lines: Annotated[
            int, Field(description="Number of context lines to show before/after match")
        ] = 2,
        limit: Annotated[
            int, Field(description="Maximum number of matches to return")
        ] = 50,
    ) -> str:
        """
        Search for a pattern in files (grep-like functionality).

        Returns formatted string with matches and context.
        """
        try:
            search_dir = Path(directory) if directory else self.repos_dir

            if not search_dir.exists():
                return f"Directory not found: {search_dir}"

            # Compile regex pattern
            try:
                pattern = re.compile(search_pattern)
            except re.error as e:
                return f"Invalid regex pattern: {e}"

            # Find files to search
            if "**" in file_pattern:
                files = list(search_dir.glob(file_pattern))
            else:
                files = list(search_dir.glob(file_pattern))

            files = [f for f in files if f.is_file()]

            # Search in files
            matches = []
            for file_path in files:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    for line_num, line in enumerate(lines, 1):
                        if pattern.search(line):
                            # Get context lines
                            start = max(0, line_num - context_lines - 1)
                            end = min(len(lines), line_num + context_lines)
                            context = lines[start:end]

                            try:
                                rel_path = file_path.relative_to(Path.cwd())
                            except ValueError:
                                rel_path = file_path

                            matches.append(
                                {
                                    "file": str(rel_path),
                                    "line_num": line_num,
                                    "line": line.rstrip(),
                                    "context": [l.rstrip() for l in context],
                                    "context_start": start + 1,
                                }
                            )

                            if len(matches) >= limit:
                                break

                except (UnicodeDecodeError, PermissionError):
                    # Skip binary files or files we can't read
                    continue

                if len(matches) >= limit:
                    break

            if not matches:
                return f"No matches found for pattern '{search_pattern}' in files matching '{file_pattern}'"

            # Format results
            output_lines = [
                f"Found {len(matches)} match(es) for '{search_pattern}':\n\n"
            ]

            for match in matches:
                output_lines.append(f"{match['file']}:{match['line_num']}\n")
                output_lines.append(f"  {match['line']}\n\n")

                if context_lines > 0:
                    output_lines.append("  Context:\n")
                    for i, ctx_line in enumerate(match["context"]):
                        ctx_line_num = match["context_start"] + i
                        marker = ">>>" if ctx_line_num == match["line_num"] else "   "
                        output_lines.append(
                            f"  {marker} {ctx_line_num:4d}: {ctx_line}\n"
                        )
                    output_lines.append("\n")

            return "".join(output_lines)

        except Exception as e:
            return f"Error searching files: {str(e)}"

    def parse_pom_dependencies(
        self,
        pom_file: Annotated[
            str, Field(description="Path to pom.xml file (e.g., 'repos/partition/pom.xml')")
        ],
    ) -> str:
        """
        Parse a Maven POM file and extract dependency information.

        Returns formatted string with dependencies and their versions.
        """
        try:
            path = Path(pom_file)

            if not path.exists():
                return f"POM file not found: {pom_file}"

            # Parse XML
            tree = ET.parse(path)
            root = tree.getroot()

            # Handle XML namespace
            ns = {"mvn": "http://maven.apache.org/POM/4.0.0"}
            if root.tag.startswith("{"):
                ns["mvn"] = root.tag.split("}")[0].strip("{")

            # Extract properties for version resolution
            properties = {}
            props_elem = root.find("mvn:properties", ns)
            if props_elem is not None:
                for prop in props_elem:
                    prop_name = prop.tag.split("}")[-1]  # Remove namespace
                    properties[prop_name] = prop.text

            # Extract dependencies
            dependencies = []
            deps_elem = root.find("mvn:dependencies", ns)
            if deps_elem is not None:
                for dep in deps_elem.findall("mvn:dependency", ns):
                    group_id = dep.find("mvn:groupId", ns)
                    artifact_id = dep.find("mvn:artifactId", ns)
                    version = dep.find("mvn:version", ns)
                    scope = dep.find("mvn:scope", ns)

                    if group_id is not None and artifact_id is not None:
                        version_text = version.text if version is not None else "N/A"

                        # Try to resolve property references
                        if version_text and version_text.startswith("${"):
                            prop_name = version_text[2:-1]  # Remove ${ and }
                            resolved_version = properties.get(prop_name, version_text)
                        else:
                            resolved_version = version_text

                        dependencies.append(
                            {
                                "groupId": group_id.text,
                                "artifactId": artifact_id.text,
                                "version": version_text,
                                "resolved_version": resolved_version,
                                "scope": scope.text if scope is not None else "compile",
                            }
                        )

            # Extract dependency management
            managed_deps = []
            dep_mgmt = root.find("mvn:dependencyManagement", ns)
            if dep_mgmt is not None:
                deps_elem = dep_mgmt.find("mvn:dependencies", ns)
                if deps_elem is not None:
                    for dep in deps_elem.findall("mvn:dependency", ns):
                        group_id = dep.find("mvn:groupId", ns)
                        artifact_id = dep.find("mvn:artifactId", ns)
                        version = dep.find("mvn:version", ns)

                        if group_id is not None and artifact_id is not None:
                            version_text = version.text if version is not None else "N/A"

                            # Try to resolve property references
                            if version_text and version_text.startswith("${"):
                                prop_name = version_text[2:-1]
                                resolved_version = properties.get(
                                    prop_name, version_text
                                )
                            else:
                                resolved_version = version_text

                            managed_deps.append(
                                {
                                    "groupId": group_id.text,
                                    "artifactId": artifact_id.text,
                                    "version": version_text,
                                    "resolved_version": resolved_version,
                                }
                            )

            # Format output
            output_lines = [f"Dependencies in {pom_file}:\n\n"]

            if properties:
                output_lines.append("Properties:\n")
                for key, value in list(properties.items())[:20]:  # Limit properties
                    output_lines.append(f"  {key} = {value}\n")
                output_lines.append("\n")

            if dependencies:
                output_lines.append(f"Dependencies ({len(dependencies)}):\n")
                for dep in dependencies:
                    version_str = dep["version"]
                    if dep["version"] != dep["resolved_version"]:
                        version_str = f"{dep['version']} → {dep['resolved_version']}"

                    output_lines.append(
                        f"  {dep['groupId']}:{dep['artifactId']}:{version_str} "
                        f"(scope: {dep['scope']})\n"
                    )
            else:
                output_lines.append("No direct dependencies found.\n")

            if managed_deps:
                output_lines.append(
                    f"\nDependency Management ({len(managed_deps)}):\n"
                )
                for dep in managed_deps:
                    version_str = dep["version"]
                    if dep["version"] != dep["resolved_version"]:
                        version_str = f"{dep['version']} → {dep['resolved_version']}"

                    output_lines.append(
                        f"  {dep['groupId']}:{dep['artifactId']}:{version_str}\n"
                    )

            return "".join(output_lines)

        except ET.ParseError as e:
            return f"Error parsing POM XML: {e}"
        except Exception as e:
            return f"Error parsing POM file: {str(e)}"

    def find_dependency_versions(
        self,
        group_id: Annotated[str, Field(description="Maven group ID (e.g., 'org.opengroup.osdu')")],
        artifact_id: Annotated[str, Field(description="Maven artifact ID (e.g., 'os-core-lib-azure')")],
        directory: Annotated[
            Optional[str],
            Field(description="Directory to search in (defaults to './repos')"),
        ] = None,
        provider: Annotated[
            Optional[str],
            Field(description="Filter by provider type (e.g., 'azure', 'gcp', 'aws'). Only searches POMs in providers/{provider}/ directories."),
        ] = None,
    ) -> str:
        """
        Find all versions of a specific Maven dependency across POM files.

        Intelligently filters by provider when the artifact name contains provider hints
        (e.g., 'os-core-lib-azure' automatically searches in azure provider POMs).

        Returns formatted string with services and their versions.
        """
        try:
            search_dir = Path(directory) if directory else self.repos_dir

            if not search_dir.exists():
                return f"Directory not found: {search_dir}"

            # Auto-detect provider from artifact_id if not explicitly specified
            detected_provider = provider
            if not detected_provider:
                # Common patterns: *-azure, *-gcp, *-aws, etc.
                for p in ["azure", "gcp", "aws"]:
                    if p in artifact_id.lower():
                        detected_provider = p
                        break

            # Find all pom.xml files
            if detected_provider:
                # Search in provider-specific directories
                # Pattern: repos/*/providers/{provider}/pom.xml or repos/*/providers/{provider}/**/pom.xml
                pom_files = list(search_dir.glob(f"**/providers/{detected_provider}/pom.xml"))
                pom_files.extend(search_dir.glob(f"**/providers/{detected_provider}/**/pom.xml"))
                # Remove duplicates
                pom_files = list(set(pom_files))
            else:
                # Search everywhere
                pom_files = list(search_dir.glob("**/pom.xml"))

            results = []

            for pom_path in pom_files:
                try:
                    tree = ET.parse(pom_path)
                    root = tree.getroot()

                    # Handle XML namespace
                    ns = {"mvn": "http://maven.apache.org/POM/4.0.0"}
                    if root.tag.startswith("{"):
                        ns["mvn"] = root.tag.split("}")[0].strip("{")

                    # Extract properties
                    properties = {}
                    props_elem = root.find("mvn:properties", ns)
                    if props_elem is not None:
                        for prop in props_elem:
                            prop_name = prop.tag.split("}")[-1]
                            properties[prop_name] = prop.text

                    # Search in dependencies
                    found = False
                    deps_elem = root.find("mvn:dependencies", ns)
                    if deps_elem is not None:
                        for dep in deps_elem.findall("mvn:dependency", ns):
                            g = dep.find("mvn:groupId", ns)
                            a = dep.find("mvn:artifactId", ns)
                            v = dep.find("mvn:version", ns)

                            if (
                                g is not None
                                and a is not None
                                and g.text == group_id
                                and a.text == artifact_id
                            ):
                                version_text = v.text if v is not None else "N/A"

                                # Resolve property
                                if version_text and version_text.startswith("${"):
                                    prop_name = version_text[2:-1]
                                    resolved = properties.get(prop_name, version_text)
                                else:
                                    resolved = version_text

                                try:
                                    rel_path = pom_path.relative_to(Path.cwd())
                                except ValueError:
                                    rel_path = pom_path

                                results.append(
                                    {
                                        "file": str(rel_path),
                                        "version": version_text,
                                        "resolved": resolved,
                                        "location": "dependencies",
                                    }
                                )
                                found = True

                    # Search in dependencyManagement
                    if not found:
                        dep_mgmt = root.find("mvn:dependencyManagement", ns)
                        if dep_mgmt is not None:
                            deps_elem = dep_mgmt.find("mvn:dependencies", ns)
                            if deps_elem is not None:
                                for dep in deps_elem.findall("mvn:dependency", ns):
                                    g = dep.find("mvn:groupId", ns)
                                    a = dep.find("mvn:artifactId", ns)
                                    v = dep.find("mvn:version", ns)

                                    if (
                                        g is not None
                                        and a is not None
                                        and g.text == group_id
                                        and a.text == artifact_id
                                    ):
                                        version_text = (
                                            v.text if v is not None else "N/A"
                                        )

                                        # Resolve property
                                        if version_text and version_text.startswith(
                                            "${"
                                        ):
                                            prop_name = version_text[2:-1]
                                            resolved = properties.get(
                                                prop_name, version_text
                                            )
                                        else:
                                            resolved = version_text

                                        try:
                                            rel_path = pom_path.relative_to(Path.cwd())
                                        except ValueError:
                                            rel_path = pom_path

                                        results.append(
                                            {
                                                "file": str(rel_path),
                                                "version": version_text,
                                                "resolved": resolved,
                                                "location": "dependencyManagement",
                                            }
                                        )

                except (ET.ParseError, Exception):
                    # Skip files that can't be parsed
                    continue

            if not results:
                provider_msg = f" (filtered by provider: {detected_provider})" if detected_provider else ""
                return (
                    f"No references found for {group_id}:{artifact_id} "
                    f"in POM files under {search_dir}{provider_msg}"
                )

            # Format output
            provider_msg = f" (filtered by provider: {detected_provider})" if detected_provider else ""
            output_lines = [
                f"Found {len(results)} reference(s) to {group_id}:{artifact_id}{provider_msg}:\n\n"
            ]

            # Group by service (top-level directory under repos)
            by_service = {}
            for result in results:
                parts = Path(result["file"]).parts

                # Find "repos" in the path and get the next directory
                service = "unknown"
                try:
                    repos_index = parts.index("repos")
                    if repos_index + 1 < len(parts):
                        service = parts[repos_index + 1]
                except ValueError:
                    # "repos" not in path, try to extract from relative path
                    if len(parts) >= 2:
                        service = parts[0] if parts[0] != "repos" else parts[1] if len(parts) > 1 else "unknown"

                if service not in by_service:
                    by_service[service] = []
                by_service[service].append(result)

            # Output by service
            for service in sorted(by_service.keys()):
                output_lines.append(f"Service: {service}\n")
                for result in by_service[service]:
                    version_str = result["version"]
                    if result["version"] != result["resolved"]:
                        version_str = f"{result['version']} → {result['resolved']}"

                    output_lines.append(
                        f"  {result['file']}\n"
                        f"    Version: {version_str}\n"
                        f"    Location: {result['location']}\n"
                    )
                output_lines.append("\n")

            return "".join(output_lines)

        except Exception as e:
            return f"Error finding dependency versions: {str(e)}"
