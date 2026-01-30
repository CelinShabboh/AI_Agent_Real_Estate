from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class Question(BaseModel):
    question: str
    conversation_id: Optional[int] = None

class ConversationRename(BaseModel):
    title: str

class KnowledgeCreate(BaseModel):
    section_name: str
    content: str

class KnowledgeOut(BaseModel):
    id: int
    section_name: str
    content: str
    created_at: datetime
    class Config: orm_mode = True

class UnansweredQuestionOut(BaseModel):
    id: int
    question: str
    created_at: datetime
    class Config: orm_mode = True

class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

class DocumentOut(BaseModel):
    id: int
    file_name: str
    created_at: datetime
    class Config: orm_mode = True

class MessageUpdate(BaseModel):
    text: str