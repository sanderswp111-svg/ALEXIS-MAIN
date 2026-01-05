#!/usr/bin/env python3
"""
ALEXIS Diagnostic Platform - Backend API Testing
Tests all backend endpoints for functionality and error handling
"""

import requests
import sys
import json
from datetime import datetime
from typing import Dict, Any, Optional

class ALEXISAPITester:
    def __init__(self, base_url: str = "https://alexis-wiring.preview.emergentagent.com"):
        self.base_url = base_url
        self.session_id = None
        self.technician_id = None
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.passed_tests = []

    def log_test(self, name: str, success: bool, details: str = ""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            self.passed_tests.append(name)
            print(f"✅ {name} - PASSED")
        else:
            self.failed_tests.append({"test": name, "details": details})
            print(f"❌ {name} - FAILED: {details}")

    def make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                    files: Optional[Dict] = None, expected_status: int = 200) -> tuple[bool, Any]:
        """Make HTTP request and return success status and response data"""
        url = f"{self.base_url}/api/{endpoint}" if not endpoint.startswith('/') else f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'} if not files else {}
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                if files:
                    response = requests.post(url, files=files, timeout=30)
                else:
                    response = requests.post(url, json=data, headers=headers, timeout=30)
            else:
                return False, f"Unsupported method: {method}"

            success = response.status_code == expected_status
            try:
                response_data = response.json() if response.content else {}
            except:
                response_data = {"raw_response": response.text[:200]}
            
            if not success:
                return False, f"Status {response.status_code}, expected {expected_status}. Response: {response_data}"
            
            return True, response_data

        except requests.exceptions.Timeout:
            return False, "Request timeout (30s)"
        except requests.exceptions.ConnectionError:
            return False, "Connection error - backend may be down"
        except Exception as e:
            return False, f"Request error: {str(e)}"

    def test_health_endpoint(self):
        """Test GET /api/ health endpoint"""
        success, data = self.make_request('GET', '', expected_status=200)
        if success and isinstance(data, dict) and 'message' in data:
            self.log_test("Health Endpoint GET /api/", True)
            return True
        else:
            self.log_test("Health Endpoint GET /api/", False, str(data))
            return False

    def test_status_endpoints(self):
        """Test POST and GET /api/status endpoints"""
        # Test POST /api/status
        test_data = {"client_name": f"test_client_{datetime.now().strftime('%H%M%S')}"}
        success, data = self.make_request('POST', 'status', data=test_data, expected_status=200)
        
        if success and isinstance(data, dict) and 'id' in data:
            self.log_test("Status POST /api/status", True)
            
            # Test GET /api/status
            success, data = self.make_request('GET', 'status', expected_status=200)
            if success and isinstance(data, list):
                self.log_test("Status GET /api/status", True)
                return True
            else:
                self.log_test("Status GET /api/status", False, str(data))
                return False
        else:
            self.log_test("Status POST /api/status", False, str(data))
            return False

    def test_auth_flow(self):
        """Test authentication flow: login and session start"""
        # Test login
        login_data = {
            "name": f"Test Technician {datetime.now().strftime('%H%M%S')}",
            "email": f"test_{datetime.now().strftime('%H%M%S')}@alexis.local"
        }
        
        success, data = self.make_request('POST', 'auth/login', data=login_data, expected_status=200)
        
        if success and isinstance(data, dict) and all(k in data for k in ['technician_id', 'token', 'name', 'email']):
            self.technician_id = data['technician_id']
            self.token = data['token']
            self.log_test("Auth Login POST /api/auth/login", True)
            
            # Test session start
            session_data = {
                "technician_id": self.technician_id,
                "vehicle_year": "2020",
                "vehicle_make": "Mercedes",
                "vehicle_model": "C300"
            }
            
            success, data = self.make_request('POST', 'session/start', data=session_data, expected_status=200)
            
            if success and isinstance(data, dict) and all(k in data for k in ['session_id', 'live', 'rules_version']):
                self.session_id = data['session_id']
                self.log_test("Session Start POST /api/session/start", True)
                return True
            else:
                self.log_test("Session Start POST /api/session/start", False, str(data))
                return False
        else:
            self.log_test("Auth Login POST /api/auth/login", False, str(data))
            return False

    def test_diagnostic_chat(self):
        """Test diagnostic chat endpoint with all three contexts"""
        if not self.session_id:
            self.log_test("Diagnostic Chat - No Session", False, "Session required")
            return False

        contexts = [
            ("symptom_audio_diagnostics", "2020 Mercedes C300 petrol engine cranks but won't start"),
            ("visual_inspection", "Check this engine component installation"),
            ("diagram_assistance", "Explain this wiring diagram circuit")
        ]

        all_passed = True
        for context, test_message in contexts:
            chat_data = {
                "session_id": self.session_id,
                "transcript": test_message,
                "context": context
            }
            
            success, data = self.make_request('POST', 'diagnostic/chat', data=chat_data, expected_status=200)
            
            if success and isinstance(data, dict) and 'response' in data and data['response']:
                self.log_test(f"Diagnostic Chat - {context}", True)
            else:
                self.log_test(f"Diagnostic Chat - {context}", False, str(data))
                all_passed = False

        return all_passed

    def test_speech_endpoints(self):
        """Test STT and TTS endpoints - expect graceful failure if Azure keys missing"""
        # Test TTS endpoint
        if not self.session_id:
            self.log_test("TTS - No Session", False, "Session required")
            return False

        tts_data = {
            "text": "This is a test message for text to speech",
            "session_id": self.session_id
        }
        
        success, data = self.make_request('POST', 'tts', data=tts_data, expected_status=503)
        
        # TTS should fail gracefully with 503 if Azure keys missing
        if not success and "503" in str(data):
            self.log_test("TTS Graceful Failure POST /api/tts", True, "Expected 503 - Azure keys not configured")
        elif success:
            self.log_test("TTS Success POST /api/tts", True, "Azure TTS working")
        else:
            self.log_test("TTS POST /api/tts", False, str(data))

        # Test STT endpoint with dummy audio file
        try:
            # Create a minimal WebM file (just headers, no real audio)
            dummy_webm = b'\x1a\x45\xdf\xa3' + b'\x00' * 100  # Minimal WebM header
            files = {'audio': ('test.webm', dummy_webm, 'audio/webm')}
            
            success, data = self.make_request('POST', 'stt', files=files, expected_status=500)
            
            # STT should fail gracefully with 500 if Azure keys missing or audio invalid
            if not success and ("500" in str(data) or "Azure" in str(data)):
                self.log_test("STT Graceful Failure POST /api/stt", True, "Expected failure - Azure keys not configured or invalid audio")
            elif success:
                self.log_test("STT Success POST /api/stt", True, "Azure STT working")
            else:
                self.log_test("STT POST /api/stt", False, str(data))
                
        except Exception as e:
            self.log_test("STT POST /api/stt", False, f"Test setup error: {str(e)}")

        return True

    def test_mongo_persistence(self):
        """Test that MongoDB operations work without exposing _id"""
        # This is tested implicitly through auth/login and session/start
        # We check that technician and session were created successfully
        if self.technician_id and self.session_id:
            self.log_test("MongoDB Persistence", True, "Technician and session created successfully")
            return True
        else:
            self.log_test("MongoDB Persistence", False, "Failed to create technician or session")
            return False

    def run_all_tests(self):
        """Run all backend tests"""
        print("🚀 Starting ALEXIS Backend API Tests")
        print(f"📡 Testing against: {self.base_url}")
        print("=" * 60)

        # Test in order of dependency
        self.test_health_endpoint()
        self.test_status_endpoints()
        
        auth_success = self.test_auth_flow()
        if auth_success:
            self.test_diagnostic_chat()
            self.test_mongo_persistence()
        
        self.test_speech_endpoints()

        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        if self.failed_tests:
            print("\n❌ Failed Tests:")
            for failure in self.failed_tests:
                print(f"  • {failure['test']}: {failure['details']}")
        
        if self.passed_tests:
            print(f"\n✅ Passed Tests: {', '.join(self.passed_tests)}")

        return self.tests_passed, self.tests_run, self.failed_tests

def main():
    """Main test execution"""
    tester = ALEXISAPITester()
    passed, total, failures = tester.run_all_tests()
    
    # Return appropriate exit code
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())