"""Project maintenance scripts, registered as CLI entry points in pyproject.toml.

Usage:
    uv run export-requirements
"""

import subprocess
import sys


def export_requirements() -> None:
    """Export pinned requirements.txt from the uv lockfile.

    Equivalent to:
        uv export --no-hashes --format requirements-txt --output-file requirements.txt
    """
    result = subprocess.run(
        [
            "uv",
            "export",
            "--no-hashes",
            "--format",
            "requirements-txt",
            "--output-file",
            "requirements.txt",
        ],
    )
    sys.exit(result.returncode)
