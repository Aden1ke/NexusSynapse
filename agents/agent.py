"""
senior-coder/agent.py — The Gatekeeper Agent.

Receives code from the Coder Agent (via the Manager).
Runs it through the security scanner.
Returns APPROVED or REJECTED with full feedback.

The Manager Agent calls: agent.review(code, task_description)
"""

import sys
import os
import json
from datetime import datetime

# Make sure we can import the scanner from anywhere
sys.path.append(os.path.join(os.path.dirname(__file__), "../../"))
from mcp.tools.security_scanner import scan_code


class SeniorCoderAgent:
    """
    The Gatekeeper. Reviews code and makes the APPROVE / REJECT decision.

    Usage (by Manager Agent):
        from agents.senior-coder.agent import SeniorCoderAgent

        reviewer = SeniorCoderAgent()
        result = reviewer.review(code=some_code, task_description="Fix login bug")

        if result["approved"]:
            # send to Deployer
        else:
            # send result["feedback"] back to Coder for fixes
    """

    def __init__(self):
        self.name = "Senior Coder Agent"
        self.role = "Gatekeeper — Code Review & Security"
        self.review_log = []          # keeps history of all reviews this session
        self.max_review_cycles = 3    # reject permanently after 3 failed attempts

    def review(self, code: str, task_description: str = "", attempt: int = 1) -> dict:
        """
        Main entry point. Reviews submitted code and returns a verdict.

        Args:
            code (str):              The Python code to review.
            task_description (str):  What the code is supposed to do.
            attempt (int):           Which attempt this is (1st, 2nd, 3rd try).

        Returns:
            dict: {
                agent:          "Senior Coder Agent",
                approved:       True / False,
                verdict:        "APPROVED" / "REJECTED" / "PERMANENTLY_REJECTED",
                score:          int 0-100,
                feedback:       string — what to fix (if rejected),
                summary:        full human-readable result,
                details:        full scan breakdown,
                timestamp:      ISO timestamp,
                attempt:        which attempt number this was
            }
        """

        self._log(f"📥 Review request received (Attempt {attempt}/{self.max_review_cycles})")
        self._log(f"📋 Task: {task_description or 'No description provided'}")
        self._log("🔍 Running lint + security scan...")

        # ── RUN THE SCANNER ──────────────────────────────────────────────
        scan_result = scan_code(code)

        # ── BUILD RESPONSE ───────────────────────────────────────────────
        verdict = "APPROVED" if scan_result["approved"] else "REJECTED"

        # If they've failed too many times, permanently reject
        if not scan_result["approved"] and attempt >= self.max_review_cycles:
            verdict = "PERMANENTLY_REJECTED"

        # Build actionable feedback for the Coder Agent
        feedback = self._build_feedback(scan_result, verdict)

        response = {
            "agent": self.name,
            "approved": scan_result["approved"],
            "verdict": verdict,
            "score": scan_result["score"],
            "feedback": feedback,
            "summary": scan_result["summary"],
            "details": {
                "lint_issues": scan_result["lint_issues"],
                "security_issues": scan_result["security_issues"],
            },
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "attempt": attempt,
        }

        # ── LOG THE RESULT ───────────────────────────────────────────────
        self.review_log.append({
            "task": task_description,
            "verdict": verdict,
            "score": scan_result["score"],
            "timestamp": response["timestamp"],
        })

        # ── PRINT CLEAR OUTPUT (visible in terminal / agent logs) ────────
        self._print_verdict(response)

        return response

    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE HELPERS
    # ─────────────────────────────────────────────────────────────────────

    def _build_feedback(self, scan_result: dict, verdict: str) -> str:
        """Turns raw scan data into clear instructions for the Coder Agent."""

        if verdict == "APPROVED":
            return "Code passed all checks. Cleared for deployment."

        if verdict == "PERMANENTLY_REJECTED":
            return (
                "⛔ PERMANENTLY REJECTED after maximum review attempts. "
                "Escalate to human developer.\n\n"
                + scan_result["summary"]
            )

        # Build specific fix instructions
        lines = ["Fix the following issues and resubmit:\n"]

        for issue in scan_result["lint_issues"]:
            if issue["type"] in ("E", "W"):
                lines.append(
                    f"  • Line {issue['line']}: [{issue['code']}] {issue['message']}"
                )

        for issue in scan_result["security_issues"]:
            if issue["severity"] in ("MEDIUM", "HIGH"):
                lines.append(
                    f"  • Line {issue['line']}: [SECURITY-{issue['severity']}] "
                    f"{issue['message']} — Test: {issue['code']}"
                )

        return "\n".join(lines)

    def _print_verdict(self, response: dict):
        """Prints a clear, formatted verdict to the terminal."""
        print()
        print("=" * 60)
        print(f"  {self.name} — Review Result")
        print("=" * 60)
        print(f"  Verdict  : {response['verdict']}")
        print(f"  Score    : {response['score']}/100")
        print(f"  Attempt  : {response['attempt']}/{self.max_review_cycles}")
        print(f"  Approved : {'✅ YES' if response['approved'] else '❌ NO'}")
        print("-" * 60)
        print(f"  Feedback : {response['feedback']}")
        print("=" * 60)
        print()

    def _log(self, message: str):
        """Simple logger with agent name prefix."""
        print(f"[{self.name}] {message}")

    def get_session_stats(self) -> dict:
        """Returns stats for all reviews done this session."""
        if not self.review_log:
            return {"total_reviews": 0}

        approved = sum(1 for r in self.review_log if r["verdict"] == "APPROVED")
        avg_score = sum(r["score"] for r in self.review_log) / len(self.review_log)

        return {
            "total_reviews": len(self.review_log),
            "approved": approved,
            "rejected": len(self.review_log) - approved,
            "average_score": round(avg_score, 1),
            "history": self.review_log,
        }


# ─────────────────────────────────────────────────────────────
# STANDALONE TEST
# Usage: python agents/senior-coder/agent.py
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":

    agent = SeniorCoderAgent()

    # ── TEST 1: Bad code (first attempt) ────────────────────
    print("\n🧪 TEST 1: Submitting bad code (attempt 1)")
    bad_code = '''
import os
SECRET_KEY = "abc123supersecret"

def process_user_input(user_input):
    os.system(user_input)
    return True
'''
    result1 = agent.review(
        code=bad_code,
        task_description="Add user input processing to API",
        attempt=1,
    )

    # ── TEST 2: Clean code ───────────────────────────────────
    print("\n🧪 TEST 2: Submitting clean code")
    good_code = '''
def process_user_input(user_input: str) -> bool:
    """
    Safely processes user input by validating it first.

    Args:
        user_input: The string input from the user.

    Returns:
        True if processed successfully.
    """
    if not isinstance(user_input, str):
        raise TypeError("Input must be a string")

    sanitized = user_input.strip()
    print(f"Processing: {sanitized}")
    return True
'''
    result2 = agent.review(
        code=good_code,
        task_description="Add user input processing to API",
        attempt=2,
    )

    # ── SESSION STATS ────────────────────────────────────────
    print("\n📊 SESSION STATS:")
    print(json.dumps(agent.get_session_stats(), indent=2))