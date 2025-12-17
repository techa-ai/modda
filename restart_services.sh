#!/bin/bash

echo "Stopping all services..."
pkill -9 -f gunicorn
pkill -9 -f "vite.*3006"
pkill -9 node

sleep 3

echo "Starting backend on port 8006..."
cd /Users/sunny/Applications/bts/jpmorgan/mortgage/modda/backend
source venv/bin/activate
gunicorn -w 2 -b 0.0.0.0:8006 app:app --timeout 120 --access-logfile - --error-logfile - > backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend started with PID: $BACKEND_PID"

sleep 3

echo "Starting frontend on port 3006..."
cd /Users/sunny/Applications/bts/jpmorgan/mortgage/modda/frontend
npm run dev -- --port 3006 > frontend.log 2>&1 &
FRONTEND_PID=$!
echo "Frontend started with PID: $FRONTEND_PID"

sleep 5

echo ""
echo "✓ Services started successfully!"
echo "  Backend:  http://localhost:8006"
echo "  Frontend: http://localhost:3006"
echo ""
echo "To view logs:"
echo "  Backend:  tail -f /Users/sunny/Applications/bts/jpmorgan/mortgage/modda/backend/backend.log"
echo "  Frontend: tail -f /Users/sunny/Applications/bts/jpmorgan/mortgage/modda/frontend/frontend.log"
