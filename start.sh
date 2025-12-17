#!/bin/bash

# MODDA Start Script

echo "🚀 Starting MODDA Application..."

# 1. Start Database
echo "📦 Starting PostgreSQL Database..."
docker-compose up -d
echo "✅ Database started on port 5436"

# Wait for DB to be ready
echo "⏳ Waiting for database to be ready..."
sleep 5

# 2. Setup Backend
echo "🐍 Setting up Backend..."
cd backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt

# Run backend in background
echo "🚀 Starting Backend Server on port 8006..."
python app.py > ../backend.log 2>&1 &
BACKEND_PID=$!
echo "✅ Backend running (PID: $BACKEND_PID)"

# 3. Setup Frontend
echo "⚛️  Setting up Frontend..."
cd ../frontend
npm install
echo "🚀 Starting Frontend Server on port 3006..."
npm run dev > ../frontend.log 2>&1 &
FRONTEND_PID=$!
echo "✅ Frontend running (PID: $FRONTEND_PID)"

echo "🎉 MODDA is running!"
echo "   Frontend: http://localhost:3006"
echo "   Backend:  http://localhost:8006"
echo "   Database: localhost:5436"
echo ""
echo "📝 Logs are being written to backend.log and frontend.log"
echo "Press Ctrl+C to stop servers"

# Handle shutdown
trap "kill $BACKEND_PID $FRONTEND_PID; exit" SIGINT SIGTERM

wait
