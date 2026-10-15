"""Run P0/P1-A/P1-B smoke with disposable req2test_p1b_test and loopback services."""

import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.argv.append("--data-driven")
    runpy.run_path(str(Path(__file__).with_name("smoke_security.py")), run_name="__main__")
