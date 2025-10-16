#!/usr/bin/env python3
"""Verify which hosted tools are initialized and their descriptions."""

import sys
sys.path.insert(0, 'src')

from spi_agent.config import AgentConfig
from spi_agent.hosted_tools import HostedToolsManager

# Configure to enable hosted tools
config = AgentConfig()
config.hosted_tools_enabled = True
config.hosted_tools_mode = "complement"

# Create manager
manager = HostedToolsManager(config)

# Get status
status = manager.get_status_summary()

print("=== Hosted Tools Status ===")
print(f"Enabled: {status['enabled']}")
print(f"Available: {status['available']}")
print(f"Tool Count: {status['tool_count']}")
print(f"Available Types: {status['available_types']}")
print(f"Mode: {status['mode']}")
print(f"Client Type: {status['client_type']}")

print("\n=== Initialized Tools ===")
for i, tool in enumerate(manager.tools, 1):
    tool_name = type(tool).__name__
    description = getattr(tool, 'description', 'No description')
    print(f"{i}. {tool_name}")
    print(f"   Description: {description}")
    print()

print(f"\n=== Total Tools: {len(manager.tools)} ===")
