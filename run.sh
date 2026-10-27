#!/bin/bash
set -e

PORT=${PORT:-5000}
echo "=========================================================="
echo "🎬 AimIndia Video Studio - Kaggle GPU Web Orchestrator"
echo "=========================================================="
echo "🌐 Starting web interface on http://localhost:$PORT ..."
python3 app.py
