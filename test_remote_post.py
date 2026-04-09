import requests

url = "http://3.227.24.237:8001/agent/stream"
headers = {
    "Content-Type": "application/json",
    "X-Tenant-Id": "education"
}
data = {
    "prompt": "What is photosynthesis?",
    "domain": "education",
    "session_id": "test-session-1"
}

response = requests.post(url, json=data, headers=headers, stream=True)
print(response.status_code)
print(response.text)
