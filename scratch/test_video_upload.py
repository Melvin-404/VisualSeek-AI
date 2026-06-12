import httpx
import asyncio
import os

async def test_upload():
    url = "http://localhost:8000/api/v1/chat/upload-video?token=mock-token"
    filepath = r"C:\Users\Mohommed Adil\Desktop\Vision Query\apps\web\public\uploads\traffic-day-night.mp4"
    
    if not os.path.exists(filepath):
        print(f"Sample video file not found at {filepath}")
        return
        
    print(f"Uploading and processing video: {filepath}...")
    headers = {"X-Tenant-ID": "22222222-2222-2222-2222-222222222222"}
    async with httpx.AsyncClient(timeout=120.0) as client:
        with open(filepath, "rb") as f:
            files = {"file": ("traffic-day-night.mp4", f, "video/mp4")}
            try:
                response = await client.post(url, files=files, headers=headers)
                print("Status code:", response.status_code)
                print("Response json:", response.json() if response.status_code == 200 else response.text)
            except Exception as e:
                print("Upload failed:", e)

if __name__ == "__main__":
    asyncio.run(test_upload())
