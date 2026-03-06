import pytest
from src.scanners.security_scanner import scan_code

def test_clean_code():
    code = """
def add(a, b):
    \"\"\"Adds two numbers.\"\"\"
    return a + b
"""
    result = scan_code(code)
    assert result["verdict"] == "PASS"
    assert result["score"] == 100
    assert result["approved"] is True

def test_vulnerable_code():
    code = """
import os
# Hardcoded secret
secret = "my-secret-key"
def run_cmd(cmd):
    # Potential injection
    os.system(cmd)
"""
    result = scan_code(code)
    assert result["verdict"] == "FAIL"
    assert result["score"] < 100
    assert result["approved"] is False
    assert any("SECURITY" in result["summary"] or result["security_issues"] for _ in [1])

def test_syntax_error_code():
    code = """
def broken_function(
    print("missing closing paren"
"""
    result = scan_code(code)
    # Pylint should catch this as an Error
    assert result["verdict"] == "FAIL"
    assert any(issue["type"] == "E" for issue in result["lint_issues"])
