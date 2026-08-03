import requests
import time

BASE_URL = "http://localhost:8000"


def test_rate_limiting():
    print("\n--- Testing Rate Limiter on /auth/login ---")
    url = f"{BASE_URL}/auth/login"
    payload = {"email": "test@example.com", "password": "wrongpassword"}

    for i in range(1, 7):
        response = requests.post(url, json=payload)
        print(
            f"Request {i}: Status {response.status_code} -> Response: {response.text}"
        )
        time.sleep(0.2)


def test_unauthenticated_protected_route():
    print("\n--- Testing Auth Dependency on Protected Route ---")
    url = f"{BASE_URL}/user/me"
    response = requests.get(url)
    print(f"Status: {response.status_code} -> Response: {response.text}")


if __name__ == "__main__":
    try:
        test_rate_limiting()
        test_unauthenticated_protected_route()
    except Exception as e:
        print(f"Connection failed: {e}")
