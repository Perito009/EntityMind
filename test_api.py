#!/usr/bin/env python3
"""
Test script for Entity Mind facial recognition system
"""
import requests
import json
import time

# Configuration
API_BASE_URL = "http://localhost:8001"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

def login():
    """Login and get access token"""
    response = requests.post(
        f"{API_BASE_URL}/api/auth/login",
        data={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD
        }
    )
    
    if response.status_code == 200:
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    else:
        print(f"Login failed: {response.text}")
        return None

def test_basic_apis(headers):
    """Test basic API endpoints"""
    print("Testing basic APIs...")
    
    # Test health endpoint
    response = requests.get(f"{API_BASE_URL}/api/health")
    print(f"Health check: {response.status_code} - {response.json()}")
    
    # Test user profile
    response = requests.get(f"{API_BASE_URL}/api/users/me", headers=headers)
    print(f"User profile: {response.status_code} - {response.json()}")
    
    # Test current count
    response = requests.get(f"{API_BASE_URL}/api/count/current", headers=headers)
    print(f"Current count: {response.status_code} - {response.json()}")
    
    # Test history
    response = requests.get(f"{API_BASE_URL}/api/count/history", headers=headers)
    print(f"History: {response.status_code} - {len(response.json()['history'])} records")

def simulate_people_counting(headers):
    """Simulate people counting for demo purposes"""
    print("\nSimulating people counting...")
    
    # Simulate different counts over time
    test_counts = [0, 2, 5, 8, 6, 3, 1, 0]
    
    for count in test_counts:
        response = requests.post(
            f"{API_BASE_URL}/api/simulate/count",
            params={"count": count},
            headers=headers
        )
        
        if response.status_code == 200:
            print(f"Simulated count: {count} people")
        else:
            print(f"Failed to simulate count: {response.text}")
        
        time.sleep(1)  # Wait 1 second between updates

def main():
    print("Entity Mind API Test")
    print("=" * 50)
    
    # Login
    headers = login()
    if not headers:
        print("Failed to login. Exiting.")
        return
    
    print("Login successful!")
    
    # Test basic APIs
    test_basic_apis(headers)
    
    # Simulate people counting
    simulate_people_counting(headers)
    
    # Final count check
    response = requests.get(f"{API_BASE_URL}/api/count/current", headers=headers)
    print(f"\nFinal count: {response.json()}")
    
    print("\nTest completed successfully!")

if __name__ == "__main__":
    main()