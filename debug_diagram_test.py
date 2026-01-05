#!/usr/bin/env python3
"""
Debug test for diagram context binding
"""

import requests
import json

def test_diagram_context():
    base_url = "https://alexis-wiring.preview.emergentagent.com"
    
    # Login first
    login_data = {
        "name": "Debug Tester",
        "email": "debug@test.com"
    }
    
    response = requests.post(f"{base_url}/api/auth/login", json=login_data)
    if response.status_code != 200:
        print(f"Login failed: {response.text}")
        return
    
    login_result = response.json()
    technician_id = login_result['technician_id']
    
    # Start session
    session_data = {
        "technician_id": technician_id,
        "vehicle_year": "2020",
        "vehicle_make": "Mercedes",
        "vehicle_model": "C300"
    }
    
    response = requests.post(f"{base_url}/api/session/start", json=session_data)
    if response.status_code != 200:
        print(f"Session start failed: {response.text}")
        return
    
    session_result = response.json()
    session_id = session_result['session_id']
    
    print(f"Session ID: {session_id}")
    
    # Test with diagram loaded
    print("\n=== TEST 1: Diagram Loaded ===")
    chat_data = {
        "session_id": session_id,
        "transcript": "What circuits are shown on this diagram?",
        "context": "diagram_assistance",
        "diagram_context": {
            "loaded": True,
            "filename": "engine_wiring.pdf",
            "totalPages": 5,
            "currentPage": 1
        }
    }
    
    print("Request payload:")
    print(json.dumps(chat_data, indent=2))
    
    response = requests.post(f"{base_url}/api/diagnostic/chat", json=chat_data)
    print(f"\nResponse status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {result['response'][:200]}...")
        
        # Check if response acknowledges diagram
        response_text = result['response'].lower()
        acknowledges = any(phrase in response_text for phrase in [
            "i can see", "wiring diagram", "engine_wiring.pdf", "diagram"
        ])
        asks_upload = any(phrase in response_text for phrase in [
            "upload", "please upload", "+ button"
        ])
        
        print(f"Acknowledges diagram: {acknowledges}")
        print(f"Asks to upload: {asks_upload}")
        print(f"Expected: Acknowledges=True, Asks=False")
        
        if acknowledges and not asks_upload:
            print("✅ TEST 1 PASSED")
        else:
            print("❌ TEST 1 FAILED")
    else:
        print(f"Request failed: {response.text}")
    
    # Test with no diagram
    print("\n=== TEST 2: No Diagram ===")
    chat_data = {
        "session_id": session_id,
        "transcript": "Explain the relay",
        "context": "diagram_assistance",
        "diagram_context": {
            "loaded": False
        }
    }
    
    response = requests.post(f"{base_url}/api/diagnostic/chat", json=chat_data)
    print(f"Response status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {result['response'][:200]}...")
        
        response_text = result['response'].lower()
        asks_upload = any(phrase in response_text for phrase in [
            "upload", "please upload", "+ button"
        ])
        acknowledges = any(phrase in response_text for phrase in [
            "i can see", "looking at", "this diagram shows"
        ])
        
        print(f"Asks to upload: {asks_upload}")
        print(f"Acknowledges diagram: {acknowledges}")
        print(f"Expected: Asks=True, Acknowledges=False")
        
        if asks_upload and not acknowledges:
            print("✅ TEST 2 PASSED")
        else:
            print("❌ TEST 2 FAILED")
    else:
        print(f"Request failed: {response.text}")

if __name__ == "__main__":
    test_diagram_context()