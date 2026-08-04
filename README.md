# PODX AI CONNECT V2

Clean WhatsApp-first FastAPI foundation.

## Included

- FastAPI application
- Health endpoint
- WhatsApp webhook verification
- Incoming text message parsing
- Outgoing WhatsApp text replies
- SQLite user storage
- Per-user session state
- Registration flow
- Main menu
- Railway-compatible startup

## Local setup

1. Copy `.env.example` to `.env`.
2. Add real Meta WhatsApp values.
3. Install dependencies:

   `pip install -r requirements.txt`

4. Run:

   `uvicorn server:app --host 0.0.0.0 --port 8000 --reload`

5. Open:

   `http://127.0.0.1:8000/docs`

## Railway start command

`uvicorn server:app --host 0.0.0.0 --port $PORT`

## Main menu

1. ఉద్యోగం కావాలి
2. వర్కర్స్ కావాలి
3. నా ప్రొఫైల్
4. సహాయం
