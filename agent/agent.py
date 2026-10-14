"""
Trilan NVR Backup — Agent Core Entry Point
Refactored to separate concerns into Domain/Application layers.
"""
import sys

from src.application.backup_job import run_backup
from src.core.config import ConfigError

if __name__ == "__main__":
    try:
        run_backup("manual")
    except ConfigError as e:
        sys.exit(str(e))
