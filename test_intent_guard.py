
import requests
import uuid

BACKEND_URL = "http://54.173.88.136:8001/agent/stream"

def test_single_prompt(prompt, domain):
    headers = {"Content-Type": "application/json", "X-Tenant-Id": domain}
    data = {
        "session_id": str(uuid.uuid4()),
        "input_type": "text",
        "text": prompt,
        "language": "en-US",
        "use_knowledge": True,
        "output_audio": False
    }
    print(f"Prompt: {prompt}")
    try:
        resp = requests.post(BACKEND_URL, json=data, headers=headers, stream=True, timeout=20)
        print(f"Status: {resp.status_code}")
        for line in resp.iter_lines(decode_unicode=True):
            if line:
                print(f"SSE: {line}")
    except Exception as e:
        print(f"Error: {e}")

def test_prompts(prompts, domain):
    print(f"\n--- Testing domain: {domain} ---")
    for prompt in prompts:
        test_single_prompt(prompt, domain)
        print()

if __name__ == "__main__":
    # 90% coverage, minimal requests: 5 per domain, 2 always-allowed, 1 off-topic
    always_allowed = [
        "hello",
        "thank you"
    ]
    religious_prompts = [
        "Tell me about Gita.",
        "What is the significance of Ramayana?",
        "Explain the concept of karma.",
        "Who is Krishna?",
        "What is a mantra?"
    ]
    education_prompts = [
        "Explain Pythagoras theorem.",
        "Teach me about cell structure.",
        "Solve this equation: 2x+3=7.",
        "What is the capital of India?",
        "Summarize the French Revolution."
    ]
    off_topic = [
        "What's the weather today?",
        "Write a Python script to sort a list."
    ]

    # Test always-allowed intents in both domains
    for prompt in always_allowed:
        test_single_prompt(prompt, "religious")
        test_single_prompt(prompt, "education")

    # Test religious domain
    test_prompts(religious_prompts, "religious")

    # Test education domain
    test_prompts(education_prompts, "education")

    # Test off-topic in both domains
    for prompt in off_topic:
        test_single_prompt(prompt, "religious")
        test_single_prompt(prompt, "education")
