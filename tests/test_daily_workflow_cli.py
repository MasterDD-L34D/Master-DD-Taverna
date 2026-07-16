import os
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _make_stub_python(tmp_path: Path) -> Path:
    stub_python = tmp_path / "python"
    stub_python.write_text(
        """#!/usr/bin/env bash
# Stub python to short-circuit commands
exit 0
"""
    )
    stub_python.chmod(0o755)
    return stub_python


_BASH_PATH: str | None = None


def _bash_available() -> bool:
    global _BASH_PATH
    if _BASH_PATH is not None:
        return True
    bash = shutil.which("bash")
    if bash is None:
        return False
    try:
        result = subprocess.run(
            [bash, "-c", "echo ok"],
            text=True,
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0 and "ok" in result.stdout:
            _BASH_PATH = bash
            return True
        return False
    except Exception:
        return False


def _run_daily_workflow(args, env):
    if not _bash_available():
        pytest.skip("bash not available in this environment")
    # Use the discovered absolute path to avoid Windows resolving ``bash`` to
    # a WSL app-execution alias when the script name is passed.
    return subprocess.run(
        [_BASH_PATH, str(PROJECT_ROOT / "tools" / "daily_workflow.sh"), *args],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )


def _assert_in_order(output_lines, substrings):
    positions = []
    for needle in substrings:
        for idx, line in enumerate(output_lines):
            if needle in line:
                positions.append(idx)
                break
        else:
            raise AssertionError(f"Missing expected output containing: {needle}")
    assert positions == sorted(positions), "Phases are not in the expected order"


def test_daily_workflow_help_message():
    result = _run_daily_workflow(["--help"], env=os.environ.copy())
    assert result.returncode == 0
    assert "Usage: tools/daily_workflow.sh" in result.stdout


@pytest.mark.usefixtures("tmp_path")
def test_check_only_run_uses_stubbed_commands(tmp_path):
    stub_python = _make_stub_python(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{stub_python.parent}:{env.get('PATH', '')}"

    result = _run_daily_workflow(
        ["--check-only", "--plan-path", str(tmp_path / "plan.md")], env=env
    )

    assert result.returncode == 0, result.stderr

    stdout_lines = result.stdout.splitlines()
    _assert_in_order(
        stdout_lines,
        [
            "Starting: Refresh module reports (--check)",
            "Completed: Refresh module reports (--check)",
            "Starting: Generate module plan",
            "Completed: Generate module plan",
            "Starting: Run static analysis",
            "Completed: Run static analysis",
        ],
    )


@pytest.mark.usefixtures("tmp_path")
def test_missing_plan_path_argument_exits_with_error(tmp_path):
    result = _run_daily_workflow(["--plan-path"], env=os.environ.copy())
    assert result.returncode != 0
    assert "Missing argument for --plan-path" in result.stderr
