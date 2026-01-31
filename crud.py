from sqlalchemy.orm import Session
from sqlalchemy.orm import Session
from models import (
    Conversation,
    Message,
    UnansweredQuestion
)

import services


def save_message(db: Session, conv_id: int, role: str, text: str):
    msg = Message(conversation_id=conv_id, role=role, text=text)
    db.add(msg)
    db.commit()
    db.refresh(msg) 
    return msg

def get_chat_history(db: Session, conv_id: int, limit: int = 10):
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

def update_message_text(db: Session, message_id: int, new_text: str):
    db_message = db.query(Message).filter(Message.id == message_id).first()
    if db_message:
        db_message.text = new_text
        db.commit()
        db.refresh(db_message)
        return db_message
    return None

def delete_conversation(db: Session, conv_id: int):
    db_conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if db_conv:
        db.delete(db_conv)
        db.commit()
        return True
    return False

def rename_conversation(db: Session, conv_id: int, new_title: str):
    db_conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if db_conv:
        db_conv.title = new_title
        db.commit()
        db.refresh(db_conv)
        return db_conv
    return None