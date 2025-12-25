
import requests
import time
import sys

def test_endpoint():
    url = "http://localhost:8000/set_problem"
    problem = "Prove that there are infinitely many primes."
    
    print(f"Sending request to {url} with problem: {problem}")
    try:
        response = requests.post(url, json={"problem": problem}, timeout=30)
        if response.status_code == 200:
            print("Success! Response:")
            print(response.json())
        else:
            print(f"Failed with status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Wait a bit for server to start if running immediately
    time.sleep(2)
    test_endpoint()
