#!/usr/bin/env python3

import requests
import sys
import json
from datetime import datetime
import time

class ScholarAPITester:
    def __init__(self, base_url="https://academic-assist-58.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.token = None
        self.user_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
        
        result = {
            "test": name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
        if details:
            print(f"    {details}")

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'
        
        if headers:
            test_headers.update(headers)

        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers, timeout=30)

            success = response.status_code == expected_status
            details = f"Status: {response.status_code}, Expected: {expected_status}"
            
            if not success:
                try:
                    error_data = response.json()
                    details += f", Response: {error_data}"
                except:
                    details += f", Response: {response.text[:200]}"
            
            self.log_test(name, success, details)
            
            return success, response.json() if success and response.content else {}

        except Exception as e:
            self.log_test(name, False, f"Error: {str(e)}")
            return False, {}

    def test_root_endpoint(self):
        """Test root API endpoint"""
        return self.run_test("Root API Endpoint", "GET", "", 200)

    def test_pricing_info(self):
        """Test pricing info endpoint"""
        success, response = self.run_test("Pricing Info", "GET", "pricing/info", 200)
        if success:
            expected_keys = ['price_per_page', 'words_per_page', 'bulk_discount_threshold', 'bulk_discount_rate']
            missing_keys = [key for key in expected_keys if key not in response]
            if missing_keys:
                self.log_test("Pricing Info Structure", False, f"Missing keys: {missing_keys}")
            else:
                # Verify pricing values
                correct_values = (
                    response['price_per_page'] == 7.0 and
                    response['words_per_page'] == 280 and
                    response['bulk_discount_threshold'] == 10000 and
                    response['bulk_discount_rate'] == 10.0
                )
                self.log_test("Pricing Values Correct", correct_values, 
                            f"Values: {response}" if not correct_values else "All pricing values correct")
        return success

    def test_pricing_calculation(self):
        """Test pricing calculation endpoint"""
        # Test normal pricing
        success1, response1 = self.run_test("Pricing Calculation (1000 words)", "POST", "pricing/calculate", 200, {"word_count": 1000})
        
        # Test bulk discount pricing
        success2, response2 = self.run_test("Pricing Calculation (15000 words)", "POST", "pricing/calculate", 200, {"word_count": 15000})
        
        if success1 and success2:
            # Verify calculations
            expected_1000 = {"word_count": 1000, "base_price": 25.0, "discount_percent": 0.0, "final_price": 25.0}
            expected_15000_base = 15000 / 280 * 7  # Should be ~375
            expected_15000_discount = expected_15000_base * 0.1
            
            calc1_correct = (
                abs(response1['base_price'] - 25.0) < 0.01 and
                response1['discount_percent'] == 0.0 and
                abs(response1['final_price'] - 25.0) < 0.01
            )
            
            calc2_correct = (
                response2['discount_percent'] == 10.0 and
                response2['final_price'] < response2['base_price']
            )
            
            self.log_test("Pricing Calculations Correct", calc1_correct and calc2_correct,
                        f"1000w: {response1}, 15000w: {response2}")
        
        return success1 and success2

    def test_user_registration(self):
        """Test user registration"""
        timestamp = int(time.time())
        test_user = {
            "email": f"test_user_{timestamp}@test.com",
            "password": "TestPass123!",
            "name": f"Test User {timestamp}"
        }
        
        success, response = self.run_test("User Registration", "POST", "auth/register", 200, test_user)
        
        if success and 'token' in response and 'user' in response:
            self.token = response['token']
            self.user_id = response['user']['id']
            self.log_test("Registration Token Received", True, f"User ID: {self.user_id}")
            return True
        else:
            self.log_test("Registration Token Received", False, "No token in response")
            return False

    def test_user_login(self):
        """Test user login with existing credentials"""
        if not self.user_id:
            self.log_test("Login Test Skipped", False, "No registered user available")
            return False
            
        # We'll use the same credentials from registration
        timestamp = int(time.time())
        login_data = {
            "email": f"test_user_{timestamp}@test.com",
            "password": "TestPass123!"
        }
        
        success, response = self.run_test("User Login", "POST", "auth/login", 200, login_data)
        return success

    def test_auth_me(self):
        """Test getting current user info"""
        if not self.token:
            self.log_test("Auth Me Test Skipped", False, "No auth token available")
            return False
            
        success, response = self.run_test("Get Current User", "GET", "auth/me", 200)
        
        if success:
            required_fields = ['id', 'email', 'name', 'created_at']
            missing_fields = [field for field in required_fields if field not in response]
            if missing_fields:
                self.log_test("User Data Structure", False, f"Missing fields: {missing_fields}")
            else:
                self.log_test("User Data Structure", True, "All required fields present")
        
        return success

    def test_assignment_creation(self):
        """Test assignment creation"""
        if not self.token:
            self.log_test("Assignment Creation Skipped", False, "No auth token available")
            return False, None
            
        assignment_data = {
            "title": "Test Assignment - Shakespeare Analysis",
            "subject": "English Literature",
            "requirements": "Analyze the themes in Hamlet, focusing on revenge and mortality. Include specific examples from the text.",
            "word_count": 2000,
            "writing_style": "academic",
            "additional_notes": "Please focus on Act 3 scenes"
        }
        
        success, response = self.run_test("Assignment Creation", "POST", "assignments", 200, assignment_data)
        
        if success and 'id' in response:
            assignment_id = response['id']
            # Verify pricing calculation in response
            expected_price = (2000 / 280) * 7  # Should be ~50
            actual_price = response.get('final_price', 0)
            
            price_correct = abs(actual_price - expected_price) < 1.0
            self.log_test("Assignment Pricing Correct", price_correct, 
                        f"Expected: ~{expected_price:.2f}, Actual: {actual_price}")
            
            return success, assignment_id
        
        return False, None

    def test_assignment_retrieval(self, assignment_id):
        """Test getting assignment by ID"""
        if not assignment_id:
            self.log_test("Assignment Retrieval Skipped", False, "No assignment ID available")
            return False
            
        success, response = self.run_test("Get Assignment by ID", "GET", f"assignments/{assignment_id}", 200)
        
        if success:
            required_fields = ['id', 'title', 'subject', 'requirements', 'word_count', 'status', 'final_price']
            missing_fields = [field for field in required_fields if field not in response]
            if missing_fields:
                self.log_test("Assignment Data Structure", False, f"Missing fields: {missing_fields}")
            else:
                self.log_test("Assignment Data Structure", True, "All required fields present")
        
        return success

    def test_assignments_list(self):
        """Test getting user's assignments list"""
        if not self.token:
            self.log_test("Assignments List Skipped", False, "No auth token available")
            return False
            
        success, response = self.run_test("Get Assignments List", "GET", "assignments", 200)
        
        if success:
            if isinstance(response, list):
                self.log_test("Assignments List Format", True, f"Found {len(response)} assignments")
            else:
                self.log_test("Assignments List Format", False, "Response is not a list")
        
        return success

    def test_dashboard_stats(self):
        """Test dashboard statistics endpoint"""
        if not self.token:
            self.log_test("Dashboard Stats Skipped", False, "No auth token available")
            return False
            
        success, response = self.run_test("Dashboard Statistics", "GET", "stats/dashboard", 200)
        
        if success:
            required_fields = ['total_assignments', 'completed_assignments', 'paid_assignments', 'total_words', 'total_spent']
            missing_fields = [field for field in required_fields if field not in response]
            if missing_fields:
                self.log_test("Dashboard Stats Structure", False, f"Missing fields: {missing_fields}")
            else:
                self.log_test("Dashboard Stats Structure", True, "All required fields present")
        
        return success

    def test_payment_checkout_creation(self, assignment_id):
        """Test creating payment checkout session"""
        if not assignment_id or not self.token:
            self.log_test("Payment Checkout Skipped", False, "No assignment ID or auth token")
            return False
            
        checkout_data = {
            "assignment_id": assignment_id,
            "origin_url": "https://academic-assist-58.preview.emergentagent.com"
        }
        
        success, response = self.run_test("Create Payment Checkout", "POST", "payments/checkout", 200, checkout_data)
        
        if success:
            required_fields = ['url', 'session_id']
            missing_fields = [field for field in required_fields if field not in response]
            if missing_fields:
                self.log_test("Checkout Response Structure", False, f"Missing fields: {missing_fields}")
            else:
                self.log_test("Checkout Response Structure", True, "Stripe checkout URL and session ID received")
        
        return success

    def run_all_tests(self):
        """Run all backend API tests"""
        print("🚀 Starting Scholar Academic Writing Assistant API Tests")
        print(f"📍 Testing against: {self.base_url}")
        print("=" * 60)
        
        # Basic API tests
        self.test_root_endpoint()
        self.test_pricing_info()
        self.test_pricing_calculation()
        
        # Authentication tests
        self.test_user_registration()
        self.test_auth_me()
        
        # Assignment tests
        assignment_success, assignment_id = self.test_assignment_creation()
        if assignment_id:
            self.test_assignment_retrieval(assignment_id)
            self.test_payment_checkout_creation(assignment_id)
        
        self.test_assignments_list()
        self.test_dashboard_stats()
        
        # Summary
        print("=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
            return 0
        else:
            print(f"⚠️  {self.tests_run - self.tests_passed} tests failed")
            return 1

    def get_test_summary(self):
        """Get detailed test summary"""
        return {
            "total_tests": self.tests_run,
            "passed_tests": self.tests_passed,
            "failed_tests": self.tests_run - self.tests_passed,
            "success_rate": (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0,
            "test_results": self.test_results
        }

def main():
    tester = ScholarAPITester()
    exit_code = tester.run_all_tests()
    
    # Save detailed results
    summary = tester.get_test_summary()
    with open('/app/backend_test_results.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())