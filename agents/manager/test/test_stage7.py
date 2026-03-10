"""
NexusSynapse — Manager Agent
Autonomous Feature Test

Tests the 3 autonomous detection functions:
    1. fetch_github_issues()   — reads GitHub bug reports
    2. check_app_health()      — pings live app
    3. check_github_actions()  — checks CI/CD pipeline
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from run import fetch_github_issues, check_app_health, check_github_actions

def test_autonomous_features():

    print("="*55)
    print("  NEXUSSYNAPSE — Manager Agent")
    print("  Autonomous Feature Test")
    print("="*55)
    passed = 0
    failed = 0

    #Test 1: GitHub Issues
    print()
    print("  Test 1: fetch_github_issues()")
    print("  " + "-"*40)

    # Function must always return a list — never crash
    result = fetch_github_issues()

    # Must return a list (even if empty)
    if isinstance(result, list):
        print(f"  ✅ Returns a list ({len(result)} issues found)")
        passed += 1
    else:
        print(f"  ❌ Must return a list, got: {type(result)}")
        failed += 1

    # Each item in the list must have required fields
    for issue in result:
        required = ["id", "title", "body", "url", "source"]
        for field in required:
            if field not in issue:
                print(f"  ❌ Issue missing field: '{field}'")
                failed += 1
            else:
                passed += 1
        # Only check first issue to keep output clean
        break

    #Test 2: App Health
    print()
    print("  Test 2: check_app_health()")
    print("  " + "-"*40)

    result = check_app_health()

    # Must return either None (healthy) or a dict (problem)
    if result is None:
        print("  ✅ App is healthy — returned None correctly")
        passed += 1
    elif isinstance(result, dict):
        print(f"  ✅ Problem detected — returned task dict correctly")
        print(f"     Issue: {result.get('title')}")

        # Check required fields in the task dict
        for field in ["title", "body", "source", "priority"]:
            if field in result:
                print(f"  ✅ Has field: '{field}'")
                passed += 1
            else:
                print(f"  ❌ Missing field: '{field}'")
                failed += 1
    else:
        print(f"  ❌ Must return None or dict, got: {type(result)}")
        failed += 1

    #Test 3: GitHub Actions
    print()
    print("  Test 3: check_github_actions()")
    print("  " + "-"*40)

    result = check_github_actions()

    # Must return either None (passing) or a dict (failure)
    if result is None:
        print("  ✅ CI/CD passing — returned None correctly")
        passed += 1
    elif isinstance(result, dict):
        print(f"  ✅ Failure detected — returned task dict correctly")
        print(f"     Issue: {result.get('title')}")
        passed += 1
    else:
        print(f"  ❌ Must return None or dict, got: {type(result)}")
        failed += 1

    #  Summary 
    print()
    print("-"*55)
    print(f"  Results: {passed} passed, {failed} failed")
    print()

    if failed == 0:
        print("  ✅ Autonomous feature test PASSED")
        print("  Manager can detect tasks without human input.")
        print("  System is ready for autonomous operation.")
    else:
        print("  ❌ Some checks failed — review output above")

    print("="*55)


if __name__ == "__main__":
    test_autonomous_features()
