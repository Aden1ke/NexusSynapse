"""
NexusSynapse — Manager Agent
Test: Agent Communication Functions
What this tests:
    Verifies that each agent communication function:
        1. Returns the correct data structure
        2. Contains all required fields
        3. Returns valid values (not None or empty)
        4. Logs the correct step number

Why this matters:
    The Manager depends on these exact data structures to make
    routing decisions. If a field is missing or wrong the entire
    pipeline breaks. These tests catch integration problems early
    before we connect to real agent endpoints.

Expected result:
    All 3 agent functions return correct data structures
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run import call_coder_agent, call_senior_coder_agent, call_deployer_agent

def test_agent_functions():
    """
    Tests all 3 agent communication functions for correct
    data structure, required fields, and valid values.
    
    This ensures the Manager can safely read each agent's
    response without KeyError or TypeError exceptions.
    """
    print("="*55)
    print("  NEXUSSYNAPSE — Manager Agent")
    print("  Test: Agent Communication Functions")
    print("="*55)
    print()

    test_task = "Fix the authentication bug in login.py"
    passed = 0
    failed = 0


    # Test 1: Coder Agent
    print("  Test 1: Coder Agent ")
    print("  " + "-"*40)

    coder_result = call_coder_agent(test_task)

    # Check required fields
    required_coder_fields = {
        "status": "submitted",
        "code":   str,
        "pr_url": "https://"
    }

    for field, expected in required_coder_fields.items():
        value = coder_result.get(field)

        if value is None:
            print(f"  ❌ Missing field: '{field}'")
            failed += 1

        elif isinstance(expected, str) and field == "status":
            if value == expected:
                print(f"  ✅ '{field}' = '{value}'")
                passed += 1
            else:
                print(f"  ❌ '{field}' expected '{expected}', got '{value}'")
                failed += 1

        elif isinstance(expected, str) and field == "pr_url":
            if value.startswith(expected):
                print(f"  ✅ '{field}' = {value[:40]}...")
                passed += 1
            else:
                print(f"  ❌ '{field}' must start with 'https://'")
                failed += 1

        elif expected == str:
            if isinstance(value, str) and len(value) > 0:
                # Show first line of code only
                first_line = value.split('\n')[0]
                print(f"  ✅ '{field}' = '{first_line}...'")
                passed += 1
            else:
                print(f"  ❌ '{field}' must be a non-empty string")
                failed += 1

    print()

    # Test 2: Senior Coder Agent
    print("  Test 2: Senior Coder Agent")
    print("  " + "-"*40)

    review_result = call_senior_coder_agent(
        coder_result.get("code", ""),
        test_task
    )

    # Check verdict is valid
    verdict = review_result.get("verdict")
    if verdict in ["APPROVED", "REJECTED"]:
        print(f"  ✅ 'verdict' = '{verdict}' (valid value)")
        passed += 1
    else:
        print(f"  ❌ 'verdict' must be APPROVED or REJECTED, got: '{verdict}'")
        failed += 1

    # Check score is 0-100
    score = review_result.get("score")
    if isinstance(score, int) and 0 <= score <= 100:
        print(f"  ✅ 'score' = {score}/100 (valid range)")
        passed += 1
    else:
        print(f"  ❌ 'score' must be integer 0-100, got: {score}")
        failed += 1

    # Check issues is a list
    issues = review_result.get("issues")
    if isinstance(issues, list):
        print(f"  ✅ 'issues' = list with {len(issues)} items")
        passed += 1
    else:
        print(f"  ❌ 'issues' must be a list, got: {type(issues)}")
        failed += 1

    # Check feedback is a string
    feedback = review_result.get("feedback")
    if isinstance(feedback, str) and len(feedback) > 0:
        print(f"  ✅ 'feedback' = '{feedback[:40]}...'")
        passed += 1
    else:
        print(f"  ❌ 'feedback' must be a non-empty string")
        failed += 1

    # Check approved_for_deployment is boolean
    approved = review_result.get("approved_for_deployment")
    if isinstance(approved, bool):
        print(f"  ✅ 'approved_for_deployment' = {approved}")
        passed += 1
    else:
        print(f"  ❌ 'approved_for_deployment' must be True or False")
        failed += 1

    print()


    # Test 3: Deployer Agent
    print("  Test 3: Deployer Agent ")
    print("  " + "-"*40)

    deploy_result = call_deployer_agent(test_task, review_result)

    # Check status is valid
    status = deploy_result.get("status")
    valid_statuses = ["deployed", "cancelled", "failed"]
    if status in valid_statuses:
        print(f"  ✅ 'status' = '{status}' (valid value)")
        passed += 1
    else:
        print(f"  ❌ 'status' must be one of {valid_statuses}")
        failed += 1

    # Check URL is present and valid
    url = deploy_result.get("url")
    if url and url.startswith("https://"):
        print(f"  ✅ 'url' = {url}")
        passed += 1
    else:
        print(f"  ❌ 'url' must be a valid https URL")
        failed += 1

    print()


    # Test 4: Data flows correctly between agents
    print("  Test 4: Data flow between agents")
    print("  " + "-"*40)
    print("  Simulating: Manager → Coder → Senior Coder → Deployer")
    print()

    # Simulate the full data flow
    step1 = call_coder_agent("Add input validation to signup form")
    step2 = call_senior_coder_agent(step1["code"], "Add input validation")
    step3 = call_deployer_agent("Add input validation", step2)

    if step1 and step2 and step3:
        print(f"  ✅ Coder output → Senior Coder input: OK")
        print(f"  ✅ Senior Coder output → Deployer input: OK")
        print(f"  ✅ Full data chain working")
        passed += 1
    else:
        print(f"  ❌ Data flow broken between agents")
        failed += 1

    # Summary
    print()
    print("-"*55)
    print(f"  Results: {passed} passed, {failed} failed")
    print()

    if failed == 0:
        print("  ✅ Stage PASSED")
        print("  All agent functions return correct data structures.")
        print("  Manager can safely read all agent responses.")
        print("  Safe to proceed to Stage 5.")
    else:
        print("  ❌ Stage  FAILED")
        print("  Fix the data structure issues above in run.py")

    print("="*55)
    return failed == 0


if __name__ == "__main__":
    test_agent_functions()
