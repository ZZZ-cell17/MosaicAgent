# MosaicAgent Service

The FastAPI runtime for the MosaicAgent multimodal knowledge Agent. See `../README.md` for setup, architecture, and API usage.

```powershell
Copy-Item .env_template .env
uv sync
uv run uvicorn server:app --host 127.0.0.1 --port 1601
```
