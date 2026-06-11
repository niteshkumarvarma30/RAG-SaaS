import httpx
import asyncio

url = "http://localhost:8000/api/v1/chat"

test_cases = [
    {
        "tenant_id": "619f50ab-df74-4057-9305-05a70fdc2474",
        "message": "How do I setup Postgres replication?"
    },
    {
        "tenant_id": "a7f179d0-83b7-4960-843f-3cac536797f3",
        "message": "How do I configure an AWS Lambda function?"
    }
]

async def test_chat():
    async with httpx.AsyncClient() as client:
        for test in test_cases:
            print(f"\n==============================================")
            print(f"Testing Tenant: {test['tenant_id']}")
            print(f"Question: {test['message']}")
            print(f"==============================================")
            try:
                # We use a longer timeout because the LangGraph loop makes a few LLM calls
                response = await client.post(url, json=test, timeout=60.0)
                
                if response.status_code == 200:
                    print(f"\nAnswer:\n{response.json()['answer']}\n")
                else:
                    print(f"Status Code: {response.status_code}")
                    print(f"Error: {response.text}")
            except Exception as e:
                print(f"Connection failed. Is the FastAPI server running? Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_chat())
