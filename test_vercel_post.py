import requests

url = "https://chatbot-tekurious.vercel.app/api/Voice/agent"
headers = {"Content-Type": "application/json"}
data = {
    "audio_b64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=",
    "sample_rate_hz": 16000,
    "domain": "education",
    "session_id": "test-session-3"
}
response = requests.post(url, json=data, headers=headers)
print(response.status_code)
print(response.text)
