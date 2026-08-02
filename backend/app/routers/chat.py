from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models import User, Conversation, ChatMessage
from app.schemas import ConversationCreate, ConversationResponse, MessageCreate, MessageResponse

router = APIRouter(prefix="/chat", tags=["Chat & History"])

@router.post("/conversations", response_model=ConversationResponse)
def create_conversation(
    user_id: str,
    payload: ConversationCreate,
    db: Session = Depends(get_db)
):
    """Create new conversation thread on database"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found in database")

    new_conversation = Conversation(
        user_id=user_id,
        title=payload.title
    )
    db.add(new_conversation)
    db.commit()
    db.refresh(new_conversation)
    return new_conversation

@router.get("/conversations/user/{user_id}", response_model=List[ConversationResponse])
def get_user_conversations(user_id: str, db: Session = Depends(get_db)):
    """Get all chat conversation of a specific user"""
    conversations = db.query(Conversation).filter(Conversation.user_id == user_id).all()
    return conversations

@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
def get_conversation_messages(conversation_id: str, db: Session = Depends(get_db)):
    """Get all messages or chat history on a specific one conversation"""
    messages = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation_id
    ).order_by(ChatMessage.created_at.asc()).all()

    return messages

@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_200_OK)
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    """Delete a specific conversation and all assiociated chat message"""
    try:
        # 1. Find the convesation
        conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversations not found"
            )

        # 2. Delete first the assiociated chat message
        db.query(ChatMessage).filter(ChatMessage.conversation_id == conversation_id)

        # 3. Delete the conversation
        db.delete(conversation)
        db.commit()

        return {
            "success": True,
            "message": f"Conversation '{conversation_id}' deleted successfully"
        }
    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_ERROR,
            detail=f"Failed to delete conversation: {str(e)}"
        )
