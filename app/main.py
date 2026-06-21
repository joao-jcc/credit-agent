"""
app/main.py — Entry point da aplicação FastAPI
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from app.api.chat import router as chat_router

app = FastAPI(
    title="Credit Negotiation Agent",
    description="Agente de renegociação de dívidas via LangGraph + FastAPI",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def frontend():
    return FileResponse("chat.html")
