#!/bin/bash
# Foresight — Vercel Build Script
set -e

echo "=== Foresight: Installing Dependencies ==="
python -m pip install -r requirements.txt

echo "=== Foresight: Collecting Static Assets ==="
python manage.py collectstatic --noinput

echo "=== Foresight: Build Complete ==="
