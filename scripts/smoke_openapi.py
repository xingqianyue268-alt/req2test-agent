"""Run the shared isolated API/worker smoke with P1-A contract scenarios enabled.

Requires REQ2TEST_ENV=test, loopback services, and database req2test_p1a_test.
Usage: python scripts/smoke_openapi.py --output-dir /tmp/req2test-p1a-smoke
"""

import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.argv.append("--openapi")
    runpy.run_path(str(Path(__file__).with_name("smoke_security.py")), run_name="__main__")
