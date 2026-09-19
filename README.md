# Baton

A small full-stack starter with a React UI and a FastAPI backend.

## Prerequisites

- Node.js 20 or newer
- Python 3.11 or newer

## Run locally

Open two terminals from the repository root.

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

```sh
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (normally http://localhost:5173). The UI calls the API at http://localhost:8000; interactive API documentation is available at http://localhost:8000/docs.

## Project structure

```text
backend/     FastAPI application
frontend/    React + Vite application
```
