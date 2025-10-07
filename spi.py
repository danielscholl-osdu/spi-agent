#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "agent-framework>=1.0.0b251001",
#   "PyGithub>=2.1.1",
#   "python-dotenv>=1.0.0",
#   "pydantic>=2.0.0",
#   "pydantic-settings>=2.7.1",
#   "azure-identity>=1.15.0",
#   "rich>=13.0.0",
# ]
# ///
"""SPI Agent executable shim for running from a checked-out repository."""

import sys

from spi_agent.cli import main


if __name__ == "__main__":
    sys.exit(main())
