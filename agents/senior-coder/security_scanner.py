import sys
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
import re
from azure.ai.contentsafety import ContentSafetyClient
from azure.ai.contentsafety.models import AnalyzeTextOptions, TextCategory
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI          # ← CHANGED: replaces ChatCompletionsClient
from dotenv import load_dotenv

load_dotenv()


# ─────────────────────────────────────────────
# CONFIGURATION
# Change FAIL_THRESHOLD to control strictness:
#   "LOW"    = fail on any security issue
#   "MEDIUM" = fail on medium/high only (recommended)
#   "HIGH"   = only fail on critical issues
# ─────────────────────────────────────────────

FAIL_THRESHOLD = os.getenv("SCANNER_FAIL_THRESHOLD", "MEDIUM")
SEVERITY_RANK  = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def _get_openai_client():
    """Single place to build the AzureOpenAI client — used by both AI functions."""
    return AzureOpenAI(
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key        = os.getenv("AZURE_API_KEY"),
        api_version    = "2024-08-01-preview"
    )


def generate_ai_fix_instructions(code: str, issues: list) -> str:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")   # ← CHANGED: was PROJECT_CONNECTION_STRING
    key      = os.getenv("AZURE_API_KEY")

    if not endpoint or not key:
        return "Internal scanner error details: " + str(issues[:3])

    try:
        client = _get_openai_client()                # ← CHANGED: was ChatCompletionsClient

        prompt = f"""
        Act as a senior mentor. Convert these raw scanner issues into specific, actionable fix instructions.
        Format each as: 'Line X: [Actionable instruction]'.

        CODE:
        {code}

        ISSUES:
        {json.dumps(issues)}
        """

        response = client.chat.completions.create(   # ← CHANGED: was client.complete()
            model    = os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4o"),
            messages = [
                {"role": "system", "content": "You generate specific line-by-line coding fix instructions."},
                {"role": "user",   "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Fix Generation failed. Raw issues: {str(issues[:2])}"


def get_ai_review_score(code: str, task: str) -> tuple:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")   # ← CHANGED: was PROJECT_CONNECTION_STRING
    key      = os.getenv("AZURE_API_KEY")

    if not endpoint or not key:
        return (70, "AI Review skipped (missing credentials). Basic pass assumed.")

    try:
        client = _get_openai_client()                # ← CHANGED: was ChatCompletionsClient

        prompt = f"""
        Evaluate the following Python code based on the user's task.
        If rejecting, provide a list of specific fix instructions with line numbers.

        TASK: {task}
        CODE:
        {code}

        Provide your response in JSON format:
        {{
            "score": <int 0-100>,
            "feedback": "<brief overall feedback>",
            "instructions": ["Line X: ...", "Line Y: ..."]
        }}
        """

        response = client.chat.completions.create(   # ← CHANGED: was client.complete()
            model    = os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4o"),
            messages = [
                {"role": "system", "content": "You are a senior code reviewer. You provide JSON feedback with 'score', 'feedback', and 'instructions'."},
                {"role": "user",   "content": prompt}
            ]
        )

        content = response.choices[0].message.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()

        review           = json.loads(content)
        combined_feedback = review.get("feedback", "")
        if review.get("instructions"):
            combined_feedback += "\nFixes required:\n" + "\n".join(review["instructions"])

        return (review.get("score", 0), combined_feedback)

    except Exception as e:
        print(f"AI Review failed: {e}")
        return (50, f"AI Review encountered an error: {str(e)}")


def check_azure_content_safety(text: str) -> tuple:
    endpoint     = os.getenv("CONTENT_SAFETY_ENDPOINT")
    key          = os.getenv("CONTENT_SAFETY_KEY")
    safety_score = 100
    issues       = []

    if not endpoint or not key:
        return (safety_score, issues)

    client = ContentSafetyClient(endpoint, AzureKeyCredential(key))

    try:
        analysis_result = client.analyze_text(AnalyzeTextOptions(text=text))

        for category_result in analysis_result.categories_analysis:
            if category_result.severity > 0:
                safety_score -= category_result.severity * 10
                issues.append({
                    "type":     "AZURE-SAFETY",
                    "severity": "HIGH" if category_result.severity > 4 else "MEDIUM",
                    "code":     str(category_result.category),
                    "message":  f"Azure AI detected {category_result.category} content (Severity: {category_result.severity})"
                })

        injection_keywords = ["IGNORE PREVIOUS INSTRUCTIONS", "YOU ARE NOW", "DAN MODE", "SYSTEM OVERRIDE"]
        for kw in injection_keywords:
            if kw in text.upper():
                safety_score -= 50
                issues.append({"type": "AZURE-SAFETY", "severity": "HIGH", "code": "PROMPT-INJECTION",
                                "message": f"Potential Prompt Injection detected: '{kw}'"})

        pii_patterns = {
            "EMAIL":   r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "PHONE":   r"\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}",
            "API-KEY": r"(?:api_key|secret|token|password|auth)[\s:=]+['\"]([a-zA-Z0-9]{32,})['\"]"
        }
        for p_type, pattern in pii_patterns.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                safety_score -= 40
                issues.append({"type": "AZURE-SAFETY", "severity": "HIGH",
                                "code": f"LEAKED-{p_type}",
                                "message": f"Potential {p_type} leak detected: '{match.group(0)[:10]}...'"})

    except Exception as e:
        print(f"Azure Content Safety Check failed: {e}")

    return (max(0, safety_score), issues)


def scan_code(code: str, task: str = "No task description provided.", filename: str = "submitted_code.py") -> dict:
    fd, tmp_path = tempfile.mkstemp(suffix=".py", prefix="gatekeeper_scan_")

    result = {
        "verdict": "APPROVED",
        "score":   0,
        "summary": "",
        "individual_scores": {"safety": 100, "scanner": 100, "ai": 0},
        "details": {"lint": [], "security": [], "ai_review": ""},
        "approved": True,
    }

    try:
        with os.fdopen(fd, "w") as tmp:
            tmp.write(code)

        # GATE 1 — Content Safety
        safety_score, safety_issues = check_azure_content_safety(code)
        result["individual_scores"]["safety"] = safety_score
        result["details"]["security"].extend(safety_issues)

        if safety_score < 30:
            result["verdict"]  = "PERMANENTLY_REJECTED"
            result["approved"] = False
            fix_instructions   = generate_ai_fix_instructions(code, safety_issues)
            result["summary"]  = (
                f"🚨 PERMANENTLY REJECTED: Content Safety Gate failed ({safety_score}/100).\n"
                f"{fix_instructions}\nThis has been escalated to humans."
            )
            return result

        # GATE 2 — Pylint + Bandit
        pylint_proc = subprocess.run(
            [sys.executable, "-m", "pylint", tmp_path, "--output-format=json", "--disable=C", "--score=no"],
            capture_output=True, text=True
        )
        if pylint_proc.stdout.strip():
            try:
                for issue in json.loads(pylint_proc.stdout):
                    category = issue.get("type", "").lower()
                    result["details"]["lint"].append({
                        "line": issue.get("line"), "type": category[0].upper(),
                        "symbol": issue.get("symbol"), "message": issue.get("message")
                    })
            except json.JSONDecodeError:
                pass

        bandit_proc = subprocess.run(
            [sys.executable, "-m", "bandit", "-r", tmp_path, "-f", "json", "-q"],
            capture_output=True, text=True
        )
        if bandit_proc.stdout.strip():
            try:
                for issue in json.loads(bandit_proc.stdout).get("results", []):
                    result["details"]["security"].append({
                        "line": issue.get("line_number"),
                        "severity": issue.get("issue_severity"),
                        "message": issue.get("issue_text")
                    })
            except json.JSONDecodeError:
                pass

        scanner_deductions = 0
        all_scanner_issues = []
        for issue in result["details"]["lint"]:
            all_scanner_issues.append(issue)
            if issue["type"] == "E":   scanner_deductions += 10
            elif issue["type"] == "W": scanner_deductions += 5

        for issue in result["details"]["security"]:
            if "severity" in issue and issue.get("type") != "AZURE-SAFETY":
                all_scanner_issues.append(issue)
                sev = issue["severity"].upper()
                if sev == "HIGH":     scanner_deductions += 20
                elif sev == "MEDIUM": scanner_deductions += 10
                elif sev == "LOW":    scanner_deductions += 3

        scanner_score = max(0, 100 - scanner_deductions)
        result["individual_scores"]["scanner"] = scanner_score

        if scanner_score < 50:
            result["verdict"]  = "REJECTED"
            result["approved"] = False
            fix_instructions   = generate_ai_fix_instructions(code, all_scanner_issues)
            result["summary"]  = f"❌ REJECTED: Scanner Gate failed ({scanner_score}/100).\n{fix_instructions}"
            return result

        # GATE 3 — AI Review
        ai_score, ai_feedback = get_ai_review_score(code, task)
        result["individual_scores"]["ai"]  = ai_score
        result["details"]["ai_review"]     = ai_feedback

        if ai_score < 60:
            result["verdict"]  = "REJECTED"
            result["approved"] = False
            result["summary"]  = f"❌ REJECTED: AI Review Gate failed ({ai_score}/100). {ai_feedback}"
            return result

        final_score    = (ai_score * 0.50) + (scanner_score * 0.35) + (safety_score * 0.15)
        result["score"]   = int(final_score)
        result["verdict"] = "APPROVED"
        result["approved"] = True
        result["summary"]  = f"✅ APPROVED. Gatekeeper score: {result['score']}/100. (AI: {ai_score}, Scanner: {scanner_score}, Safety: {safety_score})"

    except Exception as e:
        result["verdict"]  = "REJECTED"
        result["summary"]  = f"CRITICAL ERROR: Gatekeeper failed: {str(e)}"
        result["approved"] = False
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return result

# ─────────────────────────────────────────────────────────────
# QUICK TEST — run this file directly to verify everything works
# Usage: python mcp/tools/security_scanner.py
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("TEST 1: BAD CODE (should REJECT)")
    print("=" * 60)
    bad_code = '''
import os
password = "hardcoded_secret_abc123"
def divide(a, b):
    return a / b
result = divide(10, 0)
print(undefined_variable)
'''
    r1 = scan_code(bad_code, task="Write a function to divide numbers safely.")
    print(f"Verdict : {r1['verdict']}")
    print(f"Score   : {r1['score']}/100")
    print(f"Summary : {r1['summary'][:100]}")

    print()
    print("=" * 60)
    print("TEST 2: CLEAN CODE (should APPROVE)")
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
    print(f"Summary : {r2['summary'][:100]}")


