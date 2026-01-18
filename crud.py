from sqlalchemy.orm import Session
from database import Conversation, Message, SiteKnowledge, UnansweredQuestion
from datetime import datetime

import services

def get_or_create_conversation(db: Session, q_text: str, conv_id: int = None):
    if conv_id:
        conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
        if conv: return conv
    title = (q_text.strip()[:60]) or "محادثة جديدة"
    new_conv = Conversation(title=title)
    db.add(new_conv)
    db.commit()
    db.refresh(new_conv)
    return new_conv

def save_message(db: Session, conv_id: int, role: str, text: str):
    msg = Message(conversation_id=conv_id, role=role, text=text)
    db.add(msg)
    db.commit()

def get_chat_history(db: Session, conv_id: int, limit: int = 6):
    # جلب آخر رسائل للمحادثة لاستخدامها كذاكرة للـ AI
    return db.query(Message).filter(Message.conversation_id == conv_id)\
             .order_by(Message.id.desc()).limit(limit).all()

def add_unanswered(db: Session, question: str):
    new_q = UnansweredQuestion(question=question)
    db.add(new_q)
    db.commit()

def get_or_create_conversation(db: Session, q_text: str, conv_id: int = None):
    if conv_id:
        conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
        if conv: return conv
    
    smart_title = services.generate_chat_title(q_text)
    
    new_conv = Conversation(title=smart_title)
    db.add(new_conv)
    db.commit()
    db.refresh(new_conv)
    return new_conv