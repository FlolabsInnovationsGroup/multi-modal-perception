#!/usr/bin/env python3
"""Read-only pull-request security scan.

The scanner reads files and reports paths. It does not execute scanned files.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


VCS_DIRECTORIES = {".git", ".hg", ".svn", ".bzr"}

FORBIDDEN_BASENAMES = {
    "branch_structure.json",
    "temp_auto_push.bat",
    "temp_interactive_push.bat",
}

FONT_EXTENSIONS = {".eot", ".otf", ".ttf", ".woff", ".woff2"}

FONT_AWESOME_STEMS = {
    "fa-brands-400",
    "fa-regular-400",
    "fa-solid-900",
}

TEXT_EXTENSIONS = {
    "",
    ".bat",
    ".cfg",
    ".css",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

MAX_FONT_BYTES = 8 * 1024 * 1024
MAX_TEXT_BYTES = 2 * 1024 * 1024

GITIGNORE_SUFFIXES = (
    ".vscode/tasks.json",
    ".vscode/launch.json",
    "branch_structure.json",
    "temp_auto_push.bat",
    "temp_interactive_push.bat",
)

PAYLOAD_NEEDLES = (
    ("runon", "VS Code auto-run marker"),
    ("folderopen", "VS Code folderOpen auto-run"),
    ("folderopened", "VS Code folderOpened auto-run"),
    ("child_process", "Node child_process"),
    ("createrequire", "Node createRequire"),
    ("powershell", "PowerShell"),
    ("invoke-webrequest", "PowerShell download"),
    ("invoke-expression", "PowerShell invoke"),
    ("fromcharcode", "JavaScript obfuscation"),
    ("fromhex", "hex decoding"),
    ("curl http", "curl download"),
    ("wget http", "wget download"),
    ("bash -c", "shell execution"),
    ("/bin/sh", "shell execution"),
    ("cmd.exe", "Windows command execution"),
    ("<script", "HTML script"),
    ("eval(", "JavaScript eval"),
    ("function(", "JavaScript Function constructor"),
    ("atob(", "base64 decode in script"),
    ("wscript", "Windows script host"),
)

SECRET_PATTERNS = (
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("GitHub personal access token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("GitHub fine-grained token", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("AWS access key id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Private key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?PRIVATE KEY-----")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
)

URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)
HEX_OBFUSCATION = re.compile(r"(?:\\x[0-9a-f]{2}){8,}", re.IGNORECASE)


def is_probable_font(data: bytes, suffix: str = "") -> bool:
    if data.startswith((b"OTTO", b"\x00\x01\x00\x00", b"true", b"typ1", b"wOFF", b"wOF2")):
        return True
    if suffix == ".eot" and len(data) >= 36:
        version = data[8:12]
        marker = data[34:36]
        known_versions = {b"\x00\x00\x01\x00", b"\x01\x00\x02\x00", b"\x02\x00\x02\x00"}
        return version in known_versions and marker == b"LP"
    return False


def scan_tree(root: Path) -> list[str]:
    failures: list[str] = []
    root = root.resolve()

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [name for name in dirnames if name.lower() not in VCS_DIRECTORIES]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.is_symlink():
                continue
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                failures.append(f"Path escaped the scan root: {path}")
                continue
            failures.extend(_scan_file(path, relative))

    return failures


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    root = Path(args[1]) if len(args) > 1 else Path(".")
    failures = scan_tree(root)
    if failures:
        print("PR security scan failed:\n")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PR security scan passed.")
    return 0


def _scan_file(path: Path, relative: str) -> list[str]:
    failures: list[str] = []
    lowered = relative.lower()
    suffix = path.suffix.lower()
    basename = path.name.lower()

    if _is_forbidden(lowered):
        failures.append(f"Forbidden or suspicious file: {relative}")

    try:
        size = path.stat().st_size
    except OSError as exc:
        return failures + [f"Could not stat {relative}: {exc.strerror or exc}"]

    if basename == "tasks.json":
        data = _read_limited(path, min(size, MAX_TEXT_BYTES))
        views = "\n".join(_text_views(data)).lower()
        if "runon" in views and ("folderopen" in views or "folderopened" in views):
            failures.append(f"Auto-run task configuration: {relative}")

    if basename == ".gitignore":
        data = _read_limited(path, min(size, MAX_TEXT_BYTES))
        failures.extend(_gitignore_failures(relative, _decode_text(data)))

    if suffix in FONT_EXTENSIONS:
        if size > MAX_FONT_BYTES:
            failures.append(f"Font-like file exceeds the {MAX_FONT_BYTES} byte read limit: {relative}")
            return _unique(failures)
        data = _read_limited(path, size)
        failures.extend(_font_failures(relative, suffix, data))
        return _unique(failures)

    if suffix in TEXT_EXTENSIONS or basename in {"dockerfile", "makefile"}:
        data = _read_limited(path, min(size, MAX_TEXT_BYTES))
        for view in _text_views(data):
            failures.extend(_secret_failures(relative, view))

    return _unique(failures)


def _is_forbidden(lowered_relative: str) -> bool:
    parts = lowered_relative.split("/")
    basename = parts[-1]
    if basename in FORBIDDEN_BASENAMES:
        return True
    return any(
        parts[index] == ".vscode" and parts[index + 1] in {"tasks.json", "launch.json"}
        for index in range(len(parts) - 1)
    )


def _font_failures(relative: str, suffix: str, data: bytes) -> list[str]:
    failures: list[str] = []
    valid = is_probable_font(data, suffix)
    views = _text_views(data)
    if not valid:
        failures.append(f"Font-like file does not appear to be a valid font: {relative}")
        if any(URL_PATTERN.search(view) for view in views):
            failures.append(f"Font-like file contains a URL: {relative}")
        if any(HEX_OBFUSCATION.search(view) for view in views):
            failures.append(f"Font-like file contains obfuscated content: {relative}")
        if data.startswith(b"MZ") or data.startswith(b"\x7fELF"):
            failures.append(f"Font-like file contains an executable header: {relative}")

    combined = "\n".join(view.lower() for view in views)
    for needle, label in PAYLOAD_NEEDLES:
        if needle in combined:
            failures.append(f"Font-like file contains {label}: {relative}")
    for view in views:
        failures.extend(_secret_failures(relative, view))
    return failures


def _secret_failures(relative: str, text: str) -> list[str]:
    return [
        f"Possible {name} in {relative}"
        for name, pattern in SECRET_PATTERNS
        if pattern.search(text)
    ]


def _gitignore_failures(relative: str, text: str) -> list[str]:
    failures = []
    for raw_line in text.splitlines():
        normalized = _normalize_gitignore_entry(raw_line)
        if normalized is None:
            continue
        for suffix in GITIGNORE_SUFFIXES:
            if normalized == suffix or normalized.endswith("/" + suffix):
                failures.append(f"Suspicious .gitignore entry in {relative}: {suffix}")
    return failures


def _normalize_gitignore_entry(raw_line: str) -> str | None:
    line = raw_line.strip()
    if not line or line.startswith("#") or line.startswith("!"):
        return None
    line = line.replace("\\", "/").lstrip("/")
    while line.startswith("**/"):
        line = line[3:]
    return line.lower()


def _decode_text(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def _text_views(data: bytes) -> list[str]:
    views = [data.decode("latin-1", errors="replace")]
    if len(data) >= 2 and len(data) % 2 == 0:
        views.append(data.decode("utf-16-le", errors="replace"))
        views.append(data.decode("utf-16-be", errors="replace"))
    return views


def _read_limited(path: Path, size: int) -> bytes:
    with path.open("rb") as handle:
        return handle.read(size)


def _unique(failures: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for failure in failures:
        if failure not in seen:
            seen.add(failure)
            ordered.append(failure)
    return ordered


if __name__ == "__main__":
    sys.exit(main())