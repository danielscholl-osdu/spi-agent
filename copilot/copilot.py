#!/usr/bin/env python3
"""Compatibility shim for legacy copilot CLI invocation."""

from spi_agent.copilot import main


if __name__ == "__main__":
    raise SystemExit(main())
