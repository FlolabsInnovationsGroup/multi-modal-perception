#!/usr/bin/env python3
"""Read-only PR security scan for Multi-Modal Perception."""

from pathlib import Path
import sys

FAILURES = []

SUSPICIOUS_PATHS = [
    ".vscode/tasks.json",
    ".vscode/launch.json",
    "branch_structure.json",
    "temp_auto_push.bat",
    "temp_interactive_push.bat",
]

SUSPICIOUS_EXTENSIONS = {
    ".eot", ".otf", ".ttf", ".woff", ".woff2"
}

SUSPICIOUS_PATTERNS = [
    b"runOn",
    b"folderOpen",
    b"folderOpened",
    b"curl http",
    b"curl -",
    b"wget http",
    b"powershell",
    b"Invoke-WebRequest",
    b"eval(",
    b"createRequire",
    b"child_process",
    b"fromhex",
    b"sk-ant-",
    b"ghp_",
    b"github_pat_",
    b"AKIA",
]

for path in Path(".").rglob("*"):
    if not path.is_file():
        continue

    relative = path.as_posix()

    if any(part in relative for part in SUSPICIOUS_PATHS):
        FAILURES.append(f"Forbidden or suspicious file: {relative}")

    if path.suffix.lower() in SUSPICIOUS_EXTENSIONS:
        data = path.read_bytes()

        if any(pattern.lower() in data.lower() for pattern in SUSPICIOUS_PATTERNS):
            FAILURES.append(
                f"Font-like file contains suspicious content: {relative}"
            )

for path in [Path(".gitignore"), *Path(".").rglob(".gitignore")]:
    if path.is_file():
        text = path.read_text(errors="ignore").lower()

        for bad in [
            "branch_structure.json",
            "temp_auto_push.bat",
            "temp_interactive_push.bat",
            ".vscode/tasks.json",
        ]:
            if bad in text:
                FAILURES.append(
                    f"Suspicious .gitignore entry in {path}: {bad}"
                )

if FAILURES:
    print("PR security scan failed:\n")
    for failure in FAILURES:
        print(f"- {failure}")
    sys.exit(1)

print("PR security scan passed.")