"""
backend_log_tail.py — tail the backend log and surface error patterns.

Patterns tracked:
  - posthog.*capture\\(\\) takes 1 positional  (the SAC / chroma 0.4.24 bug)
  - ERROR lines (anything logged at ERROR level by our format)
  - WARNING lines
  - Tracebacks

Each match is appended to backend/logs/error_findings.jsonl with a timestamp.

Usage:
    python scripts/backend_log_tail.py backend/logs/e2e_backend.log
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime

PATTERNS = {
    "chroma_telemetry": re.compile(r"posthog.*capture\(\) takes 1 positional"),
    "error_line":       re.compile(r"\[ERROR\]"),
    "warning_line":     re.compile(r"\[WARNING\]"),
    "traceback":        re.compile(r"^Traceback \(most recent call last\)"),
}


def main(path: str) -> int:
    findings_path = os.path.join(os.path.dirname(path), "error_findings.jsonl")
    print(f"backend_log_tail: watching {path}")
    print(f"backend_log_tail: findings -> {findings_path}")

    # Wait for the log file to exist (uvicorn may still be booting)
    for _ in range(60):
        if os.path.exists(path):
            break
        time.sleep(0.5)
    else:
        print(f"backend_log_tail: {path} never appeared (60s)", file=sys.stderr)
        return 1

    counts = {k: 0 for k in PATTERNS}

    with open(path, "r", encoding="utf-8", errors="replace") as f, \
         open(findings_path, "a", encoding="utf-8") as findings:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.2)
                continue

            for name, rx in PATTERNS.items():
                if rx.search(line):
                    counts[name] += 1
                    rec = {
                        "ts": datetime.now().isoformat(timespec="seconds"),
                        "pattern": name,
                        "count_so_far": counts[name],
                        "line": line.rstrip("\n")[:500],
                    }
                    findings.write(json.dumps(rec) + "\n")
                    findings.flush()
                    # Emit to stdout so Monitor-style watchers see it
                    print(f"[TAIL] {name} #{counts[name]}: {line.rstrip()}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: backend_log_tail.py <path-to-log>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
