from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class Question(BaseModel):
    question: str
    conversation_id: Optional[int] = None

class ConversationRename(BaseModel):
    title: str

class MessageUpdate(BaseModel):
    text: str

class KnowledgeCreate(BaseModel):
    section_name: str
    content: str

class KnowledgeOut(BaseModel):
    id: int
    section_name: str
    content: str
    created_at: datetime
    class Config:
        orm_mode = True