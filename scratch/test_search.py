import asyncio
import os
import sys
from pathlib import Path

# Add packages/ai-pipeline/src and apps/api to path
root = Path(__file__).resolve().parents[1]
sys.path.append(str(root / "apps" / "api"))
sys.path.append(str(root / "packages" / "ai-pipeline" / "src"))

# Load env variables from apps/api/.env
from dotenv import load_dotenv
load_dotenv(root / "apps" / "api" / ".env")

# Ensure PYTHONPATH or system configs match
os.environ["API_ENV"] = "development"

from app.services.vector_search import VectorSearchService

async def main():
    service = VectorSearchService()
    print("VectorSearchService initialized.")
    
    # Try a search query
    query = "grey car"
    print(f"Running query: {query}")
    res = await service.search(query_text=query, limit=5)
    print("Results count:", res.get("count"))
    for idx, r in enumerate(res.get("results", [])):
        print(f"Result {idx+1}:")
        print(f"  ID: {r.get('id')}")
        print(f"  Camera: {r.get('camera_id')}")
        print(f"  Score: {r.get('score')}")
        print(f"  Description: {r.get('raw_labels', {}).get('description')}")

if __name__ == "__main__":
    asyncio.run(main())
