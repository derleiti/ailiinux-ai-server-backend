#!/bin/bash
# Quick test to verify pip install works

set -e

echo "🧪 Testing requirements.txt installation..."
echo ""

# Create test venv
echo "Creating test virtual environment..."
python3 -m venv .test-venv
source .test-venv/bin/activate

# Test install
echo "Installing dependencies..."
pip install --quiet --upgrade pip
pip install -r requirements.txt

# Verify key packages
echo ""
echo "✅ Installation successful! Verifying versions:"
echo ""
python -c "import fastapi; print(f'FastAPI: {fastapi.__version__}')"
python -c "import pydantic; print(f'Pydantic: {pydantic.__version__}')"
python -c "import httpx; print(f'HTTPX: {httpx.__version__}')"
python -c "import anthropic; print(f'Anthropic: {anthropic.__version__}')"
python -c "import openai; print(f'OpenAI: {openai.__version__}')"
python -c "import mistralai; print(f'Mistral AI: {mistralai.__version__}')"

# Cleanup
deactivate
rm -rf .test-venv

echo ""
echo "🎉 All dependencies compatible and working!"
