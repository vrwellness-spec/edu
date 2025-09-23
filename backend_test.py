#!/usr/bin/env python3
"""
Comprehensive Backend Testing for YouTube-Style LMS
Tests all backend functionality including authentication, video management, notes, quizzes, and admin features.
"""

import requests
import json
import os
import tempfile
from pathlib import Path
import time

# Load environment variables
from dotenv import load_dotenv
load_dotenv('/app/frontend/.env')

# Get backend URL from environment
BACKEND_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001')
API_BASE_URL = f"{BACKEND_URL}/api"

print(f"Testing backend at: {API_BASE_URL}")

class LMSBackendTester:
    def __init__(self):
        self.session = requests.Session()
        self.tokens = {}  # Store tokens for different users
        self.users = {}   # Store user data
        self.test_results = {
            'authentication': [],
            'video_management': [],
            'notes_management': [],
            'quiz_system': [],
            'admin_features': [],
            'errors': []
        }
    
    def log_result(self, category, test_name, success, message, details=None):
        """Log test results"""
        result = {
            'test': test_name,
            'success': success,
            'message': message,
            'details': details or {}
        }
        self.test_results[category].append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name} - {message}")
        if not success and details:
            print(f"   Details: {details}")
    
    def create_test_file(self, content, filename, content_type="text/plain"):
        """Create a temporary test file"""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=filename)
        if content_type.startswith('text/'):
            if isinstance(content, str):
                temp_file.write(content.encode())
            else:
                temp_file.write(content)
        else:
            temp_file.write(content)
        temp_file.close()
        return temp_file.name
    
    def test_health_check(self):
        """Test basic API health"""
        try:
            response = self.session.get(f"{API_BASE_URL}/health")
            if response.status_code == 200:
                print("✅ API Health Check: Backend is running")
                return True
            else:
                print(f"❌ API Health Check: Backend returned {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ API Health Check: Cannot connect to backend - {str(e)}")
            return False
    
    def test_authentication_system(self):
        """Test complete authentication system"""
        print("\n=== Testing Authentication System ===")
        
        # Test user registration with different roles
        test_users = [
            {"email": "student@test.com", "name": "Test Student", "password": "password123", "role": "student"},
            {"email": "faculty@test.com", "name": "Test Faculty", "password": "password123", "role": "faculty"},
            {"email": "admin@test.com", "name": "Test Admin", "password": "password123", "role": "admin"}
        ]
        
        for user_data in test_users:
            try:
                response = self.session.post(f"{API_BASE_URL}/auth/register", json=user_data)
                if response.status_code == 200:
                    user_info = response.json()
                    self.users[user_data['role']] = user_info
                    self.log_result('authentication', f'Register {user_data["role"]}', True, 
                                  f"Successfully registered {user_data['role']} user")
                elif response.status_code == 400 and "already registered" in response.text:
                    # User already exists, that's fine for testing
                    self.log_result('authentication', f'Register {user_data["role"]}', True, 
                                  f"User {user_data['role']} already exists (expected for repeated tests)")
                else:
                    self.log_result('authentication', f'Register {user_data["role"]}', False, 
                                  f"Registration failed: {response.text}", {'status_code': response.status_code})
            except Exception as e:
                self.log_result('authentication', f'Register {user_data["role"]}', False, 
                              f"Registration error: {str(e)}")
        
        # Test user login and JWT token generation
        for role in ['student', 'faculty', 'admin']:
            try:
                login_data = {"email": f"{role}@test.com", "password": "password123"}
                response = self.session.post(f"{API_BASE_URL}/auth/login", json=login_data)
                if response.status_code == 200:
                    login_response = response.json()
                    self.tokens[role] = login_response['access_token']
                    self.users[role] = login_response['user']
                    self.log_result('authentication', f'Login {role}', True, 
                                  f"Successfully logged in {role} user")
                else:
                    self.log_result('authentication', f'Login {role}', False, 
                                  f"Login failed: {response.text}", {'status_code': response.status_code})
            except Exception as e:
                self.log_result('authentication', f'Login {role}', False, 
                              f"Login error: {str(e)}")
        
        # Test invalid credentials
        try:
            invalid_login = {"email": "student@test.com", "password": "wrongpassword"}
            response = self.session.post(f"{API_BASE_URL}/auth/login", json=invalid_login)
            if response.status_code == 401:
                self.log_result('authentication', 'Invalid credentials', True, 
                              "Correctly rejected invalid credentials")
            else:
                self.log_result('authentication', 'Invalid credentials', False, 
                              f"Should reject invalid credentials but got: {response.status_code}")
        except Exception as e:
            self.log_result('authentication', 'Invalid credentials', False, 
                          f"Error testing invalid credentials: {str(e)}")
        
        # Test protected endpoint access
        for role in ['student', 'faculty', 'admin']:
            if role in self.tokens:
                try:
                    headers = {'Authorization': f'Bearer {self.tokens[role]}'}
                    response = self.session.get(f"{API_BASE_URL}/auth/me", headers=headers)
                    if response.status_code == 200:
                        user_info = response.json()
                        if user_info['role'] == role:
                            self.log_result('authentication', f'Protected access {role}', True, 
                                          f"Successfully accessed protected endpoint as {role}")
                        else:
                            self.log_result('authentication', f'Protected access {role}', False, 
                                          f"Role mismatch: expected {role}, got {user_info['role']}")
                    else:
                        self.log_result('authentication', f'Protected access {role}', False, 
                                      f"Protected access failed: {response.text}")
                except Exception as e:
                    self.log_result('authentication', f'Protected access {role}', False, 
                                  f"Protected access error: {str(e)}")
    
    def test_video_management(self):
        """Test video management system"""
        print("\n=== Testing Video Management System ===")
        
        # Create test video file
        video_content = b"fake video content for testing"
        video_file = self.create_test_file(video_content, ".mp4")
        
        # Test video upload - should work for faculty/admin, fail for students
        for role in ['student', 'faculty', 'admin']:
            if role in self.tokens:
                try:
                    headers = {'Authorization': f'Bearer {self.tokens[role]}'}
                    files = {'file': ('test_video.mp4', open(video_file, 'rb'), 'video/mp4')}
                    data = {'title': f'Test Video by {role}', 'description': f'Test video uploaded by {role}'}
                    
                    response = self.session.post(f"{API_BASE_URL}/videos", 
                                               headers=headers, files=files, data=data)
                    
                    if role == 'student':
                        if response.status_code == 403:
                            self.log_result('video_management', f'Video upload {role}', True, 
                                          "Correctly blocked student from uploading video")
                        else:
                            self.log_result('video_management', f'Video upload {role}', False, 
                                          f"Should block student upload but got: {response.status_code}")
                    else:  # faculty or admin
                        if response.status_code == 200:
                            video_data = response.json()
                            self.log_result('video_management', f'Video upload {role}', True, 
                                          f"Successfully uploaded video as {role}")
                        else:
                            self.log_result('video_management', f'Video upload {role}', False, 
                                          f"Video upload failed: {response.text}")
                    
                    files['file'][1].close()
                except Exception as e:
                    self.log_result('video_management', f'Video upload {role}', False, 
                                  f"Video upload error: {str(e)}")
        
        # Test video listing - should work for all authenticated users
        for role in ['student', 'faculty', 'admin']:
            if role in self.tokens:
                try:
                    headers = {'Authorization': f'Bearer {self.tokens[role]}'}
                    response = self.session.get(f"{API_BASE_URL}/videos", headers=headers)
                    if response.status_code == 200:
                        videos = response.json()
                        self.log_result('video_management', f'Video listing {role}', True, 
                                      f"Successfully retrieved {len(videos)} videos as {role}")
                    else:
                        self.log_result('video_management', f'Video listing {role}', False, 
                                      f"Video listing failed: {response.text}")
                except Exception as e:
                    self.log_result('video_management', f'Video listing {role}', False, 
                                  f"Video listing error: {str(e)}")
        
        # Test video detail retrieval with view counting
        if 'faculty' in self.tokens:
            try:
                headers = {'Authorization': f'Bearer {self.tokens["faculty"]}'}
                # First get list of videos
                response = self.session.get(f"{API_BASE_URL}/videos", headers=headers)
                if response.status_code == 200:
                    videos = response.json()
                    if videos:
                        video_id = videos[0]['id']
                        # Get video details
                        response = self.session.get(f"{API_BASE_URL}/videos/{video_id}", headers=headers)
                        if response.status_code == 200:
                            video_detail = response.json()
                            self.log_result('video_management', 'Video detail retrieval', True, 
                                          f"Successfully retrieved video details with {video_detail['views']} views")
                        else:
                            self.log_result('video_management', 'Video detail retrieval', False, 
                                          f"Video detail failed: {response.text}")
                    else:
                        self.log_result('video_management', 'Video detail retrieval', False, 
                                      "No videos available for testing")
            except Exception as e:
                self.log_result('video_management', 'Video detail retrieval', False, 
                              f"Video detail error: {str(e)}")
        
        # Clean up
        try:
            os.unlink(video_file)
        except:
            pass
    
    def test_notes_management(self):
        """Test notes management system"""
        print("\n=== Testing Notes Management System ===")
        
        # Create test note file
        note_content = "This is a test note file for the LMS system."
        note_file = self.create_test_file(note_content, ".pdf")
        
        # Test notes upload - should work for faculty/admin, fail for students
        for role in ['student', 'faculty', 'admin']:
            if role in self.tokens:
                try:
                    headers = {'Authorization': f'Bearer {self.tokens[role]}'}
                    files = {'file': ('test_note.pdf', open(note_file, 'rb'), 'application/pdf')}
                    data = {'title': f'Test Note by {role}', 'description': f'Test note uploaded by {role}'}
                    
                    response = self.session.post(f"{API_BASE_URL}/notes", 
                                               headers=headers, files=files, data=data)
                    
                    if role == 'student':
                        if response.status_code == 403:
                            self.log_result('notes_management', f'Notes upload {role}', True, 
                                          "Correctly blocked student from uploading notes")
                        else:
                            self.log_result('notes_management', f'Notes upload {role}', False, 
                                          f"Should block student upload but got: {response.status_code}")
                    else:  # faculty or admin
                        if response.status_code == 200:
                            note_data = response.json()
                            self.log_result('notes_management', f'Notes upload {role}', True, 
                                          f"Successfully uploaded note as {role}")
                        else:
                            self.log_result('notes_management', f'Notes upload {role}', False, 
                                          f"Notes upload failed: {response.text}")
                    
                    files['file'][1].close()
                except Exception as e:
                    self.log_result('notes_management', f'Notes upload {role}', False, 
                                  f"Notes upload error: {str(e)}")
        
        # Test notes listing - should work for all authenticated users
        for role in ['student', 'faculty', 'admin']:
            if role in self.tokens:
                try:
                    headers = {'Authorization': f'Bearer {self.tokens[role]}'}
                    response = self.session.get(f"{API_BASE_URL}/notes", headers=headers)
                    if response.status_code == 200:
                        notes = response.json()
                        self.log_result('notes_management', f'Notes listing {role}', True, 
                                      f"Successfully retrieved {len(notes)} notes as {role}")
                    else:
                        self.log_result('notes_management', f'Notes listing {role}', False, 
                                      f"Notes listing failed: {response.text}")
                except Exception as e:
                    self.log_result('notes_management', f'Notes listing {role}', False, 
                                  f"Notes listing error: {str(e)}")
        
        # Clean up
        try:
            os.unlink(note_file)
        except:
            pass
    
    def test_quiz_system(self):
        """Test quiz system"""
        print("\n=== Testing Quiz System ===")
        
        # Test quiz creation - should work for faculty/admin, fail for students
        quiz_data = {
            "title": "Sample Quiz",
            "description": "A test quiz for the LMS system",
            "questions": [
                {
                    "question": "What is 2 + 2?",
                    "type": "multiple_choice",
                    "options": ["3", "4", "5", "6"],
                    "correct_answer": "4"
                },
                {
                    "question": "What is the capital of France?",
                    "type": "multiple_choice", 
                    "options": ["London", "Berlin", "Paris", "Madrid"],
                    "correct_answer": "Paris"
                }
            ],
            "time_limit": 30
        }
        
        for role in ['student', 'faculty', 'admin']:
            if role in self.tokens:
                try:
                    headers = {'Authorization': f'Bearer {self.tokens[role]}'}
                    quiz_data['title'] = f"Quiz by {role}"
                    
                    response = self.session.post(f"{API_BASE_URL}/quizzes", 
                                               headers=headers, json=quiz_data)
                    
                    if role == 'student':
                        if response.status_code == 403:
                            self.log_result('quiz_system', f'Quiz creation {role}', True, 
                                          "Correctly blocked student from creating quiz")
                        else:
                            self.log_result('quiz_system', f'Quiz creation {role}', False, 
                                          f"Should block student quiz creation but got: {response.status_code}")
                    else:  # faculty or admin
                        if response.status_code == 200:
                            quiz_response = response.json()
                            self.log_result('quiz_system', f'Quiz creation {role}', True, 
                                          f"Successfully created quiz as {role}")
                        else:
                            self.log_result('quiz_system', f'Quiz creation {role}', False, 
                                          f"Quiz creation failed: {response.text}")
                except Exception as e:
                    self.log_result('quiz_system', f'Quiz creation {role}', False, 
                                  f"Quiz creation error: {str(e)}")
        
        # Test quiz listing - should work for all authenticated users
        for role in ['student', 'faculty', 'admin']:
            if role in self.tokens:
                try:
                    headers = {'Authorization': f'Bearer {self.tokens[role]}'}
                    response = self.session.get(f"{API_BASE_URL}/quizzes", headers=headers)
                    if response.status_code == 200:
                        quizzes = response.json()
                        self.log_result('quiz_system', f'Quiz listing {role}', True, 
                                      f"Successfully retrieved {len(quizzes)} quizzes as {role}")
                    else:
                        self.log_result('quiz_system', f'Quiz listing {role}', False, 
                                      f"Quiz listing failed: {response.text}")
                except Exception as e:
                    self.log_result('quiz_system', f'Quiz listing {role}', False, 
                                  f"Quiz listing error: {str(e)}")
    
    def test_admin_features(self):
        """Test admin-only features"""
        print("\n=== Testing Admin Features ===")
        
        # Test user listing - should work for admin only
        for role in ['student', 'faculty', 'admin']:
            if role in self.tokens:
                try:
                    headers = {'Authorization': f'Bearer {self.tokens[role]}'}
                    response = self.session.get(f"{API_BASE_URL}/admin/users", headers=headers)
                    
                    if role == 'admin':
                        if response.status_code == 200:
                            users = response.json()
                            self.log_result('admin_features', f'User listing {role}', True, 
                                          f"Successfully retrieved {len(users)} users as admin")
                        else:
                            self.log_result('admin_features', f'User listing {role}', False, 
                                          f"Admin user listing failed: {response.text}")
                    else:  # student or faculty
                        if response.status_code == 403:
                            self.log_result('admin_features', f'User listing {role}', True, 
                                          f"Correctly blocked {role} from accessing user list")
                        else:
                            self.log_result('admin_features', f'User listing {role}', False, 
                                          f"Should block {role} from user listing but got: {response.status_code}")
                except Exception as e:
                    self.log_result('admin_features', f'User listing {role}', False, 
                                  f"User listing error: {str(e)}")
        
        # Test user status updates - should work for admin only
        if 'admin' in self.tokens and 'student' in self.users:
            try:
                headers = {'Authorization': f'Bearer {self.tokens["admin"]}'}
                student_id = self.users['student']['id']
                
                # Test suspending user
                response = self.session.patch(f"{API_BASE_URL}/admin/users/{student_id}/status?status=suspended", 
                                            headers=headers)
                if response.status_code == 200:
                    self.log_result('admin_features', 'User status update', True, 
                                  "Successfully updated user status to suspended")
                    
                    # Test reactivating user
                    response = self.session.patch(f"{API_BASE_URL}/admin/users/{student_id}/status?status=active", 
                                                headers=headers)
                    if response.status_code == 200:
                        self.log_result('admin_features', 'User status reactivation', True, 
                                      "Successfully reactivated user")
                    else:
                        self.log_result('admin_features', 'User status reactivation', False, 
                                      f"User reactivation failed: {response.text}")
                else:
                    self.log_result('admin_features', 'User status update', False, 
                                  f"User status update failed: {response.text}")
            except Exception as e:
                self.log_result('admin_features', 'User status update', False, 
                              f"User status update error: {str(e)}")
        
        # Test non-admin trying to update user status
        if 'faculty' in self.tokens and 'student' in self.users:
            try:
                headers = {'Authorization': f'Bearer {self.tokens["faculty"]}'}
                student_id = self.users['student']['id']
                
                response = self.session.patch(f"{API_BASE_URL}/admin/users/{student_id}/status?status=suspended", 
                                            headers=headers)
                if response.status_code == 403:
                    self.log_result('admin_features', 'Non-admin status update', True, 
                                  "Correctly blocked non-admin from updating user status")
                else:
                    self.log_result('admin_features', 'Non-admin status update', False, 
                                  f"Should block non-admin status update but got: {response.status_code}")
            except Exception as e:
                self.log_result('admin_features', 'Non-admin status update', False, 
                              f"Non-admin status update error: {str(e)}")
    
    def run_all_tests(self):
        """Run all backend tests"""
        print("🚀 Starting YouTube-Style LMS Backend Testing")
        print("=" * 60)
        
        # Check if backend is running
        if not self.test_health_check():
            print("❌ Backend is not accessible. Stopping tests.")
            return False
        
        # Run all test suites
        self.test_authentication_system()
        self.test_video_management()
        self.test_notes_management()
        self.test_quiz_system()
        self.test_admin_features()
        
        # Print summary
        self.print_summary()
        return True
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        
        total_tests = 0
        total_passed = 0
        
        for category, tests in self.test_results.items():
            if category == 'errors':
                continue
            
            passed = sum(1 for test in tests if test['success'])
            total = len(tests)
            total_tests += total
            total_passed += passed
            
            print(f"\n{category.upper().replace('_', ' ')}:")
            print(f"  ✅ Passed: {passed}/{total}")
            
            # Show failed tests
            failed_tests = [test for test in tests if not test['success']]
            if failed_tests:
                print(f"  ❌ Failed tests:")
                for test in failed_tests:
                    print(f"    - {test['test']}: {test['message']}")
        
        print(f"\n🎯 OVERALL RESULTS:")
        print(f"   Total Tests: {total_tests}")
        print(f"   Passed: {total_passed}")
        print(f"   Failed: {total_tests - total_passed}")
        print(f"   Success Rate: {(total_passed/total_tests*100):.1f}%" if total_tests > 0 else "No tests run")
        
        if self.test_results['errors']:
            print(f"\n⚠️  CRITICAL ERRORS:")
            for error in self.test_results['errors']:
                print(f"   - {error}")

def main():
    """Main test execution"""
    tester = LMSBackendTester()
    success = tester.run_all_tests()
    
    if not success:
        exit(1)

if __name__ == "__main__":
    main()