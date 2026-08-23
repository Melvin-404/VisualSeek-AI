#!/bin/sh

# Start the FastAPI backend in the background
echo "Starting FastAPI backend..."
cd /app && uv run --frozen --package api uvicorn app.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# Start the Next.js frontend in the background
echo "Starting Next.js frontend..."
cd /app && pnpm --filter web dev --hostname 0.0.0.0 &
WEB_PID=$!

# Function to handle shutdown signals
cleanup() {
    echo "Stopping services..."
    kill -TERM "$API_PID" 2>/dev/null
    kill -TERM "$WEB_PID" 2>/dev/null
    exit 0
}

trap cleanup INT TERM

# Monitor processes
while true; do
    if ! kill -0 "$API_PID" 2>/dev/null; then
        echo "API backend stopped unexpectedly."
        exit 1
    fi
    if ! kill -0 "$WEB_PID" 2>/dev/null; then
        echo "Web frontend stopped unexpectedly."
        exit 1
    fi
    sleep 2
done
