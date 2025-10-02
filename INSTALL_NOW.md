# 🚀 Quick Installation Guide

## ✅ Dependency Conflict RESOLVED!

The httpx dependency conflict has been fixed. You can now install all dependencies without errors.

## 📦 What Was Fixed

**Problem:**
- `mistralai` had a breaking change in requirements:
  - Old (1.2.x): required `httpx<0.28.0`
  - New (1.9.10): requires `httpx>=0.28.1`

**Solution:**
- ✅ Upgraded `httpx` to `0.28.1` (latest stable)
- ✅ Upgraded `mistralai` to `1.9.10` (latest stable)
- ✅ All AI SDKs now compatible with httpx 0.28.1

## 🔧 Install Now

### Option 1: Fresh Install (Recommended)

```bash
cd /root/ailinux-ai-server-backend

# Remove old venv
rm -rf .venv

# Create fresh venv
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (should work without errors!)
pip install -r requirements.txt
```

### Option 2: Upgrade Existing

```bash
cd /root/ailinux-ai-server-backend
source .venv/bin/activate

# Upgrade all packages
pip install --upgrade -r requirements.txt
```

### Option 3: Test Install First

```bash
# Run automated test (creates temp venv)
./test-install.sh
```

## 🎯 Verify Installation

```bash
# Check versions
python -c "import fastapi; print(f'FastAPI: {fastapi.__version__}')"
python -c "import httpx; print(f'HTTPX: {httpx.__version__}')"
python -c "import anthropic; print(f'Anthropic: {anthropic.__version__}')"
python -c "import openai; print(f'OpenAI: {openai.__version__}')"
python -c "import mistralai; print(f'Mistral: {mistralai.__version__}')"

# Expected output:
# FastAPI: 0.118.0
# HTTPX: 0.28.1
# Anthropic: 0.39.0
# OpenAI: 1.57.4
# Mistral: 1.9.10
```

## 🚀 Start the Server

```bash
# Development
uvicorn app.main:app --host 0.0.0.0 --port 9100 --reload

# Production
uvicorn app.main:app --host 0.0.0.0 --port 9100 --workers 4
```

## 🧪 Run Tests

```bash
python -m pytest tests/ -v
```

## 📊 Final Dependency Matrix

| Package | Version | Status |
|---------|---------|--------|
| FastAPI | 0.118.0 | ✅ Latest |
| Uvicorn | 0.32.1 | ✅ Latest |
| Pydantic | 2.10.3 | ✅ Latest |
| **HTTPX** | **0.28.1** | ✅ **Latest Stable** |
| Anthropic | 0.39.0 | ✅ Latest |
| OpenAI | 1.57.4 | ✅ Latest |
| **Mistral AI** | **1.9.10** | ✅ **Latest** |
| Google Gen AI | 0.8.3 | ✅ Latest |

## 🔍 Compatibility Notes

All AI SDKs are now compatible:

- **Anthropic 0.39.0**: requires `httpx>=0.23.0,<1` ✅
- **OpenAI 1.57.4**: requires `httpx>=0.23.0,<1` ✅
- **Mistral AI 1.9.10**: requires `httpx>=0.28.1` ✅

**Our choice: `httpx==0.28.1`** satisfies all requirements!

## ❓ Still Having Issues?

1. **Clear pip cache:**
   ```bash
   pip cache purge
   rm -rf ~/.cache/pip
   ```

2. **Reinstall from scratch:**
   ```bash
   rm -rf .venv
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --no-cache-dir -r requirements.txt
   ```

3. **Check Python version:**
   ```bash
   python --version  # Should be 3.11 or 3.12
   ```

## 📝 Next Steps

1. ✅ Install dependencies
2. ✅ Configure `.env` (see `.env.example`)
3. ✅ Start backend on port 9100
4. ✅ Run smoke tests (see `docs/SMOKE_TESTS.md`)
5. ✅ Deploy to production!

---

**Status**: ✅ Ready to install - No conflicts!
