import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn
from fastapi import FastAPI

app = FastAPI()

@app.on_event("startup")
async def startup():
    loop = asyncio.get_running_loop()
    print("CURRENT RUNNING LOOP TYPE:", type(loop), flush=True)

if __name__ == "__main__":
    config = uvicorn.Config(app, host="127.0.0.1", port=8099, loop="asyncio")
    server = uvicorn.Server(config)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(server.serve())
