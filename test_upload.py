import httpx
import asyncio

url = "http://localhost:8000/api/v1/ingest"

files_to_upload = [
    ("619f50ab-df74-4057-9305-05a70fdc2474", "tenant_a_postgres_sample.pdf"),
    ("3780bb27-250a-4a2c-be4b-9252b8e8ce9a", "tenant_b_intel_sample.pdf"),
    ("a7f179d0-83b7-4960-843f-3cac536797f3", "tenant_c_aws_sample.pdf"),
]

async def upload_files():
    async with httpx.AsyncClient() as client:
        for tenant_id, filename in files_to_upload:
            print(f"Uploading {filename} for tenant {tenant_id}...")
            try:
                with open(filename, "rb") as f:
                    files = {"file": (filename, f, "application/pdf")}
                    data = {"tenant_id": tenant_id}
                    # Upload file to the ingestion endpoint
                    response = await client.post(url, data=data, files=files, timeout=30.0)
                    print(f"Status: {response.status_code}")
                    print(f"Response: {response.text}\n")
            except FileNotFoundError:
                print(f"Error: Could not find file '{filename}'. Make sure you are running this from c:\\AI\\Projects\\RAG SaaS\n")

if __name__ == "__main__":
    asyncio.run(upload_files())
