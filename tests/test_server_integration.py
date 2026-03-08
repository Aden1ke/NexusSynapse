import requests
import multiprocessing
import time
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src', 'scanners')))

def run_server():
    from server import app
    app.run(port=5001) # Use different port for testing

if __name__ == '__main__':
    # Start server in a separate process
    server_process = multiprocessing.Process(target=run_server)
    server_process.daemon = True
    server_process.start()
    
    # Wait for server to boot
    time.sleep(3)
    
    # Test Payload as specified by user
    payload = {
        "code": "import os\nprint(os.getenv('SECRET'))",
        "task": "Check this code for security leaks"
    }
    
    print("Testing /review endpoint...")
    try:
        response = requests.post("http://127.0.0.1:5001/review", json=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
        
        if response.status_code == 200 and "verdict" in response.json():
            print("\n✅ Verification Successful!")
        else:
            print("\n❌ Verification Failed!")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error during testing: {e}")
        sys.exit(1)
    finally:
        server_process.terminate()
