"""
security_scanner.py — The Gatekeeper's scanning engine.

Runs two checks on any Python code submitted:
  1. pylint  → catches bugs, errors, bad practices
  2. bandit  → catches security vulnerabilities

Returns a structured verdict: PASS or FAIL + full details.
"""

import subprocess
import tempfile
import os
import json


# ─────────────────────────────────────────────
# CONFIGURATION
# Change FAIL_THRESHOLD to control strictness:
#   "LOW"    = fail on any security issue
#   "MEDIUM" = fail on medium/high only (recommended)
#   "HIGH"   = only fail on critical issues
# ─────────────────────────────────────────────
FAIL_THRESHOLD = os.getenv("SCANNER_FAIL_THRESHOLD", "MEDIUM")

SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def scan_code(code: str, filename: str = "submitted_code.py") -> dict:
    """
    Main function. Takes a string of Python code, scans it, returns verdict.

    Args:
        code (str): The Python source code to scan.
        filename (str): Optional label for the file (used in reports).

    Returns:
        dict: {
            verdict:          "PASS" or "FAIL",
            score:            int 0–100,
            summary:          human-readable verdict string,
            lint_issues:      list of bug/quality issues from pylint,
            security_issues:  list of security issues from bandit,
            approved:         bool
        }
    """

    # Write the code to a real temp file (pylint/bandit need a file path)
    # We close it before running subprocesses to avoid permission errors on Windows
    fd, tmp_path = tempfile.mkstemp(suffix=".py", prefix="gatekeeper_scan_")
    
    result = {
        "verdict": "PASS",
        "score": 100,
        "summary": "",
        "lint_issues": [],
        "security_issues": [],
        "approved": True,
    }

    try:
        with os.fdopen(fd, "w") as tmp:
            tmp.write(code)

        # ── PYLINT SCAN ──────────────────────────────────────────────────
        pylint_proc = subprocess.run(
            [
                "pylint",
                tmp_path,
                "--output-format=json",
                "--disable=C",          # ignore style/convention issues
                "--score=no",
            ],
            capture_output=True,
            text=True,
        )

        if pylint_proc.stdout.strip():
            try:
                pylint_data = json.loads(pylint_proc.stdout)
                for issue in pylint_data:
                    category = issue.get("type", "").lower()  # Normalize to lowercase
                    entry = {
                        "line": issue.get("line"),
                        "column": issue.get("column"),
                        "type": category[0].upper(),          # Store as "E", "W", "R", etc.
                        "code": issue.get("symbol"),          # e.g. "undefined-variable"
                        "message": issue.get("message"),
                    }
                    result["lint_issues"].append(entry)

                    # Errors and Warnings = automatic FAIL
                    if category in ("error", "warning", "e", "w"):
                        result["verdict"] = "FAIL"

            except json.JSONDecodeError:
                pass  # pylint returned no parseable output (clean code)

        # ── BANDIT SECURITY SCAN ─────────────────────────────────────────
        bandit_proc = subprocess.run(
            ["bandit", "-r", tmp_path, "-f", "json", "-q"],
            capture_output=True,
            text=True,
        )

        if bandit_proc.stdout.strip():
            try:
                bandit_data = json.loads(bandit_proc.stdout)
                for issue in bandit_data.get("results", []):
                    severity = issue.get("issue_severity", "LOW").upper()
                    entry = {
                        "line": issue.get("line_number"),
                        "severity": severity,                        # LOW / MEDIUM / HIGH
                        "confidence": issue.get("issue_confidence"), # LOW / MEDIUM / HIGH
                        "code": issue.get("test_id"),                # e.g. "B105"
                        "message": issue.get("issue_text"),
                    }
                    result["security_issues"].append(entry)

                    # Fail if severity meets or exceeds the threshold
                    if SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK.get(FAIL_THRESHOLD, 2):
                        result["verdict"] = "FAIL"

            except json.JSONDecodeError:
                pass  # bandit returned no parseable output

        # ── SCORE CALCULATION ────────────────────────────────────────────
        # Start at 100, deduct points per issue
        deductions = 0
        for issue in result["lint_issues"]:
            if issue["type"] == "E":
                deductions += 10   # Errors are serious
            elif issue["type"] == "W":
                deductions += 5    # Warnings are moderate

        for issue in result["security_issues"]:
            sev = issue["severity"]
            if sev == "HIGH":
                deductions += 20
            elif sev == "MEDIUM":
                deductions += 10
            elif sev == "LOW":
                deductions += 3

        result["score"] = max(0, 100 - deductions)

        # ── SUMMARY STRING ───────────────────────────────────────────────
        if result["verdict"] == "PASS":
            result["summary"] = (
                f"✅ APPROVED. Score: {result['score']}/100. "
                f"No critical issues found. Safe to deploy."
            )
            result["approved"] = True
        else:
            problem_lines = []

            for i in result["lint_issues"]:
                if i["type"] in ("E", "W"):
                    problem_lines.append(
                        f"  [LINT-{i['type']}] Line {i['line']}: {i['message']} ({i['code']})"
                    )

            for s in result["security_issues"]:
                if SEVERITY_RANK.get(s["severity"], 0) >= SEVERITY_RANK.get(FAIL_THRESHOLD, 2):
                    problem_lines.append(
                        f"  [SECURITY-{s['severity']}] Line {s['line']}: {s['message']} ({s['code']})"
                    )

            result["summary"] = (
                f"❌ REJECTED. Score: {result['score']}/100. "
                f"Fix these issues before resubmitting:\n"
                + "\n".join(problem_lines)
            )
            result["approved"] = False

    except Exception as e:
        result["verdict"] = "FAIL"
        result["summary"] = f"CRITICAL ERROR: Scanner failed with exception: {str(e)}"
        result["approved"] = False
    finally:
        # Always delete the temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return result


# ─────────────────────────────────────────────────────────────
# QUICK TEST — run this file directly to verify everything works
# Usage: python mcp/tools/security_scanner.py
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":

    print("=" * 60)
    print("TEST 1: BAD CODE (should FAIL)")
    print("=" * 60)

    bad_code = '''
import os
password = "hardcoded_secret_abc123"

def divide(a, b):
    return a / b

result = divide(10, 0)
print(undefined_variable)
'''
    r1 = scan_code(bad_code)
    print(f"Verdict : {r1['verdict']}")
    print(f"Score   : {r1['score']}/100")
    print(f"Summary : {r1['summary']}")
    print(f"Lint    : {len(r1['lint_issues'])} issues")
    print(f"Security: {len(r1['security_issues'])} issues")

    print()
    print("=" * 60)
    print("TEST 2: CLEAN CODE (should PASS)")
    print("=" * 60)

    good_code = '''
def add_numbers(first: int, second: int) -> int:
    """Adds two integers and returns the result."""
    return first + second


def greet(name: str) -> str:
    """Returns a greeting string."""
    return f"Hello, {name}!"
'''
    r2 = scan_code(good_code)
    print(f"Verdict : {r2['verdict']}")
    print(f"Score   : {r2['score']}/100")
    print(f"Summary : {r2['summary']}")