import os
import requests
from openai import OpenAI

API_KEY = "sk_duin32gn_CgYRIY6dLnDN4vG8KjORbLLA"
BASE_URL = "https://api.sarvam.ai/v1"

print("========================================")
print("     Sarvam AI API Test Script")
print("========================================")

print("\n[1] Fetching available models...")
models_list = []
try:
    # We use the standard OpenAI /models endpoint to list what this key has access to
    headers = {"Authorization": f"Bearer {API_KEY}"}
    response = requests.get(f"{BASE_URL}/models", headers=headers)
    
    if response.status_code == 200:
        models = response.json().get("data", [])
        print(f"Successfully fetched {len(models)} models:")
        for m in models:
            model_id = m.get('id')
            print(f"  - {model_id}")
            models_list.append(model_id)
    else:
        print(f"Error fetching models. Status Code: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"Exception occurred: {e}")

print("\n[2] Testing Chat Completion...")
if models_list:
    # Automatically pick a text/chat model to test
    # Usually Sarvam models have "sarvam" in the name
    test_model = models_list[0]
    for m in models_list:
        if "sarvam" in m.lower():
            test_model = m
            break
            
    print(f"Sending a test request using model: '{test_model}'...")
    try:
        # Since Sarvam supports the OpenAI SDK format, we can use the same OpenAI client!
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        chat_response = client.chat.completions.create(
            model=test_model,
            messages=[{"role": "user", "content": "Hello! Please write a one-sentence greeting in Hindi."}]
        )
        print("\nSuccess! Response received:")
        print("----------------------------------------")
        print(chat_response.choices[0].message.content.strip())
        print("----------------------------------------")
    except Exception as e:
        print(f"\nChat completion error: {e}")
else:
    print("Skipping Chat Completion because no models were found.")
