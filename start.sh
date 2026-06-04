#!/usr/bin/env bash
# QueryForge — start all services
# Usage: bash start.sh

set -e

echo "======================================"
echo "  QueryForge SQL Optimizer"
echo "======================================"

# Check Python
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
  echo "[ERROR] Python not found. Install Python 3.8+"
  exit 1
fi

PYTHON=$(command -v python3 || command -v python)

# Check Node
if ! command -v node &>/dev/null; then
  echo "[ERROR] Node.js not found. Install Node.js 16+"
  exit 1
fi

echo "[1/3] Starting ML Service (Python Flask)..."
cd ml-model
$PYTHON -m pip install -r requirements.txt -q
$PYTHON app.py &
ML_PID=$!
cd ..

sleep 2

echo "[2/3] Starting Backend (Node.js)..."
cd backend
npm install --silent
node server.js &
BACK_PID=$!
cd ..

sleep 1

echo "[3/3] Starting Frontend (React)..."
cd frontend
npm install --silent
npm start &
FRONT_PID=$!
cd ..

echo ""
echo "======================================"
echo "  All services started!"
echo "  Frontend: http://localhost:3000"
echo "  Backend:  http://localhost:3001"
echo "  ML API:   http://localhost:5001"
echo "======================================"
echo "Press Ctrl+C to stop all services"

trap "echo 'Stopping...'; kill $ML_PID $BACK_PID $FRONT_PID 2>/dev/null; exit" INT
wait
