import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_eval_selftest_runs_and_prints_the_results_table():
    """QA-4 plumbing: the script runs without a model and meets its targets with the oracle."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "evals" / "run_eval.py"), "--selftest"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Citation support rate" in result.stdout and "Correct-refusal rate" in result.stdout
    assert result.stdout.count("PASS") >= 32  # 30 rows + 2 metrics
