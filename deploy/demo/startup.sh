#!/bin/sh
set -eu
# Run from the extracted release root; App Service supplies the Python environment.
exec python -m uvicorn public_demo.app:app --host 0.0.0.0 --port 8000 --workers 2 --no-access-log
