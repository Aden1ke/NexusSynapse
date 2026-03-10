import sys
import os
import json

# Add the project directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agents', 'senior-coder')))

try:
    from security_scanner import scan_code
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)

def test_ai_feedback():
    print("--- 🧪 Testing AI-Generated Fix Instructions 🧪 ---")
    
    # Test 1: Scanner rejection (Lint error)
    print("\n[TEST 1] Scanner rejection Feedack")
    code_with_lint = """
import os
def my_func():
    print(undefined_var) # This is a lint error (E)
"""
    result = scan_code(code_with_lint, task="Print a variable.")
    
    print(f"Verdict: {result['verdict']}")
    print(f"Summary Preview: {result['summary'][:200]}...")
    
    if "Line" in result['summary'] and ":" in result['summary']:
        print("✅ Success: Found line-specific instructions in summary.")
    else:
        print("❌ Failure: Missing line-specific instructions in summary.")

    # Test 2: AI Review rejection (Wrong logic)
    print("\n[TEST 2] AI Review rejection Feedback")
    code_wrong_logic = """
def add(a, b):
    return a - b # Wrong logic for 'add' task
"""
    result = scan_code(code_wrong_logic, task="Create a function that adds two numbers.")
    print(f"Verdict: {result['verdict']}")
    print(f"Summary: {result['summary']}")
    
    if "Fixes required:" in result['summary'] or "Line" in result['summary']:
        print("✅ Success: Found AI-generated fix instructions.")
    else:
        print("❌ Failure: Missing AI-provided instructions.")

if __name__ == "__main__":
    test_ai_feedback()
