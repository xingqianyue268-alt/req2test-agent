"""Source-checkout entry point for the Evaluation Center regression gate."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

if __name__ == "__main__":
    from req2test.evaluation.cli import main

    main()
