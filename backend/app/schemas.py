from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

# System request when going to send new chat message
class MessageCreate(BaseModel):
    content: str

# Response structure for a chat message
class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True

# System request when going to create new conversation
class ConversationCreate(BaseModel):
    title: Optional[str] = "New Chat"

# Response structure for conversation item
class ConversationResponse(BaseModel):
    id: str
    user_id: str
    title: str
    created_at: datetime

    class Config:
        from_attributes = True