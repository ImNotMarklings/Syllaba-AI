import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from google import genai

from app.routers import auth, classroom, ai, chat
from app.database import engine, Base

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.limiter import limiter

# Load .env
load_dotenv()

# Auto-create tables in Aiven PostgreSQL
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Google Classroom AI Agent App",
    description="Backend for Google Classroom integration and AI study helper",
    version="1.0.0"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Register sub-routes
app.include_router(auth.router)
app.include_router(classroom.router)
app.include_router(ai.router)
app.include_router(chat.router)

# Enable CORS (Cross-Origin Resource Sharing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Initialize Gemini Client
api_key = os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=api_key) if api_key else None

@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "Welcome to GClass AI Agent backend",
        "docs": "route: /docs"
    }

@app.get("/health")
def health_check():
    return { "status": "ok", "gemini_configured": gemini_client is not None }
