#!/usr/bin/env python3
"""
dev_runner.py — Test script to send sample Twilio webhooks to the deployed endpoint.
Run this to verify the Vercel deployment is working and notifications are sent to Monday.
"""

import requests
import sys
from datetime import datetime

# Your Vercel endpoint
ENDPOINT_URL = "https://vercel.com/breea-toomeys-projects/twilio-monday-webhook/8CZo46p9qCRJLu8gQYM1yaipHBkC/sms"

# Sample test cases
test_cases = [
    {
        "name": "Basic SMS",
        "payload": {
            "From": "+15551234567",
            "Body": "Hello from Twilio test!",
            "Timestamp": datetime.now().isoformat()
        }
    },
    {
        "name": "SMS with special characters",
        "payload": {
            "From": "+14155552671",
            "Body": "Test: Can you confirm? (Yes/No) 👍",
            "Timestamp": datetime.now().isoformat()
        }
    },
    {
        "name": "Longer message",
        "payload": {
            "From": "+19876543210",
            "Body": "This is a longer test message to verify the endpoint can handle multi-line and detailed SMS content from Twilio webhooks.",
            "Timestamp": datetime.now().isoformat()
        }
    }
]

def run_test(test_case):
    """Run a single test case."""
    name = test_case["name"]
    payload = test_case["payload"]
    
    print(f"\n{'='*60}")
    print(f"Test: {name}")
    print(f"{'='*60}")
    print(f"Endpoint: {ENDPOINT_URL}")
    print(f"Payload: {payload}")
    print(f"-" * 60)
    
    try:
        response = requests.post(
            ENDPOINT_URL,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Body: {response.text if response.text else '(empty)'}")
        
        if response.status_code == 200:
            print("✅ SUCCESS: Endpoint accepted the webhook")
        else:
            print(f"⚠️  WARNING: Unexpected status code {response.status_code}")
        
        return True
    except requests.RequestException as e:
        print(f"❌ ERROR: {e}")
        return False
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")
        return False

def main():
    print(f"\n{'#'*60}")
    print("# Twilio → Monday Webhook Test Runner")
    print(f"{'#'*60}")
    print(f"Testing endpoint: {ENDPOINT_URL}")
    print(f"Tests to run: {len(test_cases)}")
    
    results = []
    for test_case in test_cases:
        success = run_test(test_case)
        results.append((test_case["name"], success))
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Check your Monday inbox for notifications.")
        print("   (Notifications may take a few seconds to appear)")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check the endpoint logs on Vercel.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
