from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    documents = relationship("DocumentKnowledge", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    role = Column(String(32))
    text = Column(Text)
    type = Column(String(20), default="text")
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class SiteKnowledge(Base):
    __tablename__ = "site_knowledge"
    id = Column(Integer, primary_key=True, index=True)
    section_name = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UnansweredQuestion(Base):
    __tablename__ = "unanswered"
    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class DocumentKnowledge(Base):
    __tablename__ = "document_knowledge"
    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String(255))
    file_path = Column(String(500))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    conversation = relationship("Conversation", back_populates="documents")
