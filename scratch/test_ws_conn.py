import asyncio
import websockets

async def test_conn():
    url = "ws://localhost:8000/api/v1/chat/ws?token=mock-token"
    try:
        async with websockets.connect(url) as ws:
            print("Connected successfully!")
            await ws.send('{"text": "hello", "session_id": "test"}')
            res = await ws.recv()
            print("Received:", res)
    except Exception as e:
        print("Connection failed:", e)

if __name__ == "__main__":
    asyncio.run(test_conn())
