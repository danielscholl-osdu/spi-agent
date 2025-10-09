---
description: Install & Prime - Install dependencies and run setup scripts
mode: agent
tools: ['search', 'runCommands']
model: Copilot-SWE (Internal) (copilot)
---

# Install & Prime

## Read and Execute
@.claude/commands/prime.md
uv run @scripts/map_env.py [.env.sample] [.env]

## Run
Install agent dependencies