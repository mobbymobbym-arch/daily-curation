#!/usr/bin/env python3

"""Compatibility launcher for the repo-local X watch automation.

The X watch workflow is owned by this repository. This wrapper exists so any
older Codex skill or automation call that still invokes this filename simply
delegates to the fixed repo script instead of depending on ~/.codex/skills.
"""

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_SCRIPT = ROOT / "scripts" / "run_x_watch_workflow.py"


def main():
    parser = argparse.ArgumentParser(
        description="Run the repo-local X watch workflow. This is a compatibility wrapper.",
    )
    parser.add_argument("--hours", type=int, help="Override lookback window in hours")
    parser.add_argument("--skip-rerun", action="store_true", help="Skip single-handle reruns")
    args = parser.parse_args()

    if not WORKFLOW_SCRIPT.exists():
        raise SystemExit(f"workflow script not found: {WORKFLOW_SCRIPT}")

    command = [sys.executable, str(WORKFLOW_SCRIPT)]
    if args.hours is not None:
        command.extend(["--hours", str(args.hours)])
    if args.skip_rerun:
        command.append("--skip-rerun")

    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
