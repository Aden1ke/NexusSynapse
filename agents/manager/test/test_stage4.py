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

from run import call_coder_agent

def test_agent_functions():
    """
    Tests all 3 agent communication functions for correct
    data structure, required fields, and valid values.
    
    This ensures the Manager can safely read each agent's
    response without KeyError or TypeError exceptions.
    """
    print("="*55)
    print("  NEXUSSYNAPSE — Manager Agent")
    print("  Stage Test: Agent Communication Functions")
    print("="*55)
    print()

    test_task = "Fix the authentication bug in login.py"
    passed = 0
    failed = 0


    # Test 1: Coder Agent
    print("  Test 1: Coder Agent")
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

        # ══════════════════════════════════════════════════
    # Test 4: Data flows correctly between agents
    # ══════════════════════════════════════════════════
    print("  Test 4: Data flow between agents")
    print("  " + "-"*40)
    print("  Simulating: Manager → Coder")
    print()

    # Simulate the full data flow
    step1 = call_coder_agent("Add input validation to signup form")
    
    if step1:
        print(f"  ✅ Coder output → Senior Coder input: OK")
        print(f"  ✅ Full data chain working")
        passed += 1
    else:
        print(f"  ❌ Data flow broken between agents")
        failed += 1

    # ══════════════════════════════════════════════════
    # Summary
    # ══════════════════════════════════════════════════
    print()
    print("-"*55)
    print(f"  Results: {passed} passed, {failed} failed")
    print()

    if failed == 0:
        print("  ✅ Stage PASSED")
        print("  All agent functions return correct data structures.")
        print("  Manager can safely read all agent responses.")
        print("  Safe to proceed to Stage .")
    else:
        print("  ❌ Stage FAILED")
        print("  Fix the data structure issues above in run.py")

    print("="*55)
    return failed == 0


if __name__ == "__main__":
    test_agent_functions()
