import json
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Conversation, ChatMessage
from app.schemas import MessageResponse
from app.services.ai_agent import AIAgentService
from google.genai import types

from app.limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["Ai Agent Chat"])

class ChatRequest(BaseModel):
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    message: str = Field(..., min_length=1)


# Standard Sychronous Chat Endpoint
@router.post("/chat")
@limiter.limit("10/minute")
def chat_with_agent(
    request: Request,
    payload: ChatRequest,
    authorization: str = Header(...),
    x_refresh_token: Optional[str] = Header(None, alias="X-Refresh-Token"),
    db: Session = Depends(get_db)
):
    """
    Unified Conversational Agent Endpoint with Chat History fetching on the database
    """
    try:
        # 1. Handle Conversational ID or create a new one automatically
        if not payload.conversation_id:
            if not payload.user_id:
                raise HTTPException(status=400, detail="user_id is required when creating a new conversation")
            conversation = Conversation(user_id=payload.user_id, title="New Chat")
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
            conversation_id = conversation.id
        else:
            conversation_id = payload.conversation_id
            conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conversation:
                raise HTTPException(status=404, detail="Conversation not found")

        # 2. Get all chat history from the database
        db_history = db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conversation_id
        ).order_by(ChatMessage.created_at.asc()).all()

        chat_history = [{"role": msg.role, "content": msg.content} for msg in db_history]

        # 3. Save the new user message to the database
        user_msg = ChatMessage(
            conversation_id=conversation_id,
            role="user",
            content=payload.message
        )

        # 4. Call Gemini AI Agent
        token = authorization.replace("Bearer ", "").strip()

        reply = AIAgentService.run_chat_session(
            user_message=payload.message,
            chat_history=chat_history,
            access_token=token,
            refresh_token=x_refresh_token
        )

        # 5. Save the response of AI Agent to the database
        model_msg = ChatMessage(
            conversation_id=conversation_id,
            role="model",
            content=reply
        )
        db.add(model_msg)

        # 6. Auto-generate Title if conversation is new/default
        if conversation.title in ["New Chat", "New Conversation"]:
            try:
                client = AIAgentService.get_client()
                title_prompt = f"Summarize this initial chat prompt into a concise 3-5 word title (no quotes, no punctation): '{payload.message}'"
                title_response, _ = AIAgentService._generate_with_fallback(
                    client=client,
                    contents=[title_prompt],
                    config=types.GenerateContentConfig()
                )
                if title_response.text:
                    conversation.title = title_response.text.strip()
            except Exception as e:
                logger.warning(f"Title auto-generation skipped: {e}")

        db.commit()
        db.refresh(user_msg)
        db.refresh(model_msg)
        db.refresh(conversation)

        return {
            "conversation_id": conversation_id,
            "conversation_title": conversation.title,
            "user_message": MessageResponse.model_validate(user_msg),
            "agent_response": MessageResponse.model_validate(model_msg)
        }
    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Agent Error: {str(e)}")

# 2. Real-time streaming endpoint with dynamic AI checklist
@router.post("/chat/stream")
@limiter.limit("5/minute")
def chat_with_agent_stream(
    request: Request,
    payload: ChatRequest,
    authorization: str = Header(...),
    x_refresh_token: Optional[str] = Header(None, alias="X-Refresh-Token"),
    db: Session = Depends(get_db)
):
    token = authorization.replace("Bearer ", "").strip()

    def event_generator():
        # Helper function for standard SSE format (`data <json>\n\n`)
        def emit(event_type: str, data: dict):
            payload_data = json.dumps({"type": event_type, **data})
            return f"data: {payload_data}\n\n"

        # 1. Setup Conversation
        conv_id = payload.conversation_id

        if not conv_id or conv_id == "null" or conv_id == "undefined":
            # New Chat: Kailangan ng user_id
            if not payload.user_id:
                yield emit("error", {"message": "user_id is required for a new conversation"})
                return

            try:
                conversation = Conversation(user_id=payload.user_id, title="New Chat")
                db.add(conversation)
                db.commit()
                db.refresh(conversation)
                conv_id = conversation.id
            except Exception as e:
                db.rollback()
                yield emit("error", {"message": f"Database Error: {str(e)}"})
                return
        else:
            conversation = db.query(Conversation).filter(Conversation.id == conv_id).first()
            if not conversation:
                yield emit("error", {"message": "Conversation not found"})
                return

        # 2. Save User message
        try:
            user_msg = ChatMessage(conversation_id=conv_id, role="user", content=payload.message)
            db.add(user_msg)
            db.commit()
        except Exception as e:
            db.rollback()
            yield emit("error", {"message": f"Failed to save user message: {str(e)}"})
            return

        client = AIAgentService.get_client()

        # PHASE 1: Gemini AI Generates Dynamic Checklist Steps
        yield emit("status", {"message": "Analyzing request intent..."})

        checklist_prompt = f"""
        Analyze this user's request: "{payload.message}"
        Break down your execution plan into 3 concise UI checklist step labels.
        Return ONLY a JSON array of strings.
        Example: ["Checking enrolled classes", "Retrieving course materials", "Analyzing due dates"]
        """

        try:
            planner_res, _ = AIAgentService._generate_with_fallback(
                client=client,
                contents=[checklist_prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            ai_steps = json.loads(planner_res.text)
        except Exception as e:
            logger.warning(f"Checklist planner failed, using fallback steps: {e}")
            ai_steps = ["Analyzing intent", "Querying Google Classroom", "Preparing response"]

        checklist = [
            {"id": f"step_{idx}", "label": label, "status": "pending"}
            for idx, label in enumerate(ai_steps)
        ]

        # Send initial checklist setup to UI
        yield emit("checklist_init", {"steps": checklist})

        # PHASE 2: Simulate Step Progression
        for step in checklist:
            yield emit("step_update", {"id": step["id"], "label": step["label"], "status": "in_progress"})
            yield emit("step_update", {"id": step["id"], "label": step["label"], "status": "completed"})

        # PHASE 3: Fetch Chat History & Run Full AIAgentService
        db_history = db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conv_id
        ).order_by(ChatMessage.created_at.asc()).all()

        # Ignore the very last message since we already pass payload.message separately
        chat_history = [{"role": msg.role, "content": msg.content} for msg in db_history[:-1]] if len(db_history) > 1 else []

        final_response_text = AIAgentService.run_chat_session(
            user_message=payload.message,
            chat_history=chat_history,
            access_token=token,
            refresh_token=x_refresh_token
        )

        # Save Model Response
        model_msg = ChatMessage(conversation_id=conv_id, role="model", content=final_response_text)
        db.add(model_msg)

        # Auto title generation using the AI Agent
        if conversation.title in ["New Chat", "New Conversation"]:
            try:
                title_prompt = f"Summarize into a concise 3-5 word title (no punctuation, no quotes): '{payload.message}'"
                title_res = AIAgentService._generate_with_fallback(
                    client=client,
                    contents=[title_prompt],
                    config=types.GenerateContentConfig()
                )
                if title_res.text:
                    conversation.title = title_res.text.strip()
            except Exception as e:
                logger.warning(f"Title generation skipped: {e}")

        db.commit()
        db.refresh(conversation)

        # FINAL EVENT: Send Final Answer
        yield emit("final_response", {
            "conversation_id": conv_id,
            "conversation_title": conversation.title,
            "content": final_response_text
        })

    return StreamingResponse(event_generator(), media_type="text/event-stream")
