# main.py
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import OpenAI
import os
import difflib
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from datetime import datetime
from fastapi import Query
from database import SessionLocal, FAQ, UnansweredQuestion, Conversation, Message

# Load env
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI(title="Real Estate Assistant")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://syrialistings.com",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------------------
# Request / Response Models
# ------------------------------
class Question(BaseModel):
    question: str
    conversation_id: Optional[int] = None

class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

class MessageOut(BaseModel):
    id: int
    conversation_id: int
    role: str
    text: str
    created_at: datetime

class ConversationRename(BaseModel):
    title: str

# ------------------------------
# Helper Functions
# ------------------------------
def find_relevant_answer(question: str, db: Session):
    faqs = db.query(FAQ).all()
    if not faqs:
        return None

    all_entries = {f.id: f.question for f in faqs}

    best_match_id = max(
        all_entries,
        key=lambda id: difflib.SequenceMatcher(None, question, all_entries[id]).ratio()
    )

    similarity = difflib.SequenceMatcher(
        None, question, all_entries[best_match_id]
    ).ratio()

    if similarity < 0.6:  
        return None

    return db.query(FAQ).filter(FAQ.id == best_match_id).first().answer


def create_conversation_from_first_message(db: Session, first_text: str) -> Conversation:
    title = (first_text.strip()[:60]) or "محادثة جديدة"
    conv = Conversation(title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv

# ------------------------------
# Routes
# ------------------------------

@app.get("/conversations/")
def list_conversations(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):

    offset = (page - 1) * limit

    total = db.query(Conversation).count()

    rows = (
        db.query(Conversation)
        .order_by(Conversation.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    total_pages = (total + limit - 1) // limit

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": total_pages,
        "items": rows
    }


@app.get("/conversations/{conv_id}/messages")
def get_conversation_messages(
    conv_id: int,
    cursor: int | None = Query(None),
    limit: int = Query(30, ge=5, le=100),
    db: Session = Depends(get_db)
):

    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    query = db.query(Message).filter(Message.conversation_id == conv_id)

    if cursor is None:
        query = query.order_by(Message.id.desc()).limit(limit)
    else:
        query = (
            query.filter(Message.id < cursor)
            .order_by(Message.id.desc())
            .limit(limit)
        )

    messages = query.all()

    next_cursor = messages[-1].id if len(messages) > 0 else None

    return {
        "items": list(reversed(messages)), 
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None
    }


@app.patch("/conversations/{conv_id}/rename")
def rename_conversation(conv_id: int, data: ConversationRename, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv.title = data.title
    conv.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "updated"}


@app.delete("/conversations/{conv_id}/delete")
def delete_conversation(conv_id: int, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.delete(conv)
    db.commit()
    return {"status": "deleted"}


# ------------------------------
# MAIN /ask/ logic
# ------------------------------
@app.post("/ask/")
async def ask_real_estate_agent(q: Question, db: Session = Depends(get_db)):
    try:
        # 1) conversation handling
        conv = None

        if q.conversation_id is not None:
            conv = db.query(Conversation).filter(Conversation.id == q.conversation_id).first()

            if not conv:
                raise HTTPException(status_code=400, detail="Conversation does not exist anymore")

        if conv is None:
            conv = create_conversation_from_first_message(db, q.question)

        # 2) Save USER message
        user_msg = Message(conversation_id=conv.id, role="user", text=q.question)
        db.add(user_msg)
        db.commit()

        # 3) Try to find FAQ answer
        relevant_answer = find_relevant_answer(q.question, db)

        if not relevant_answer:
            new_q = UnansweredQuestion(question=q.question)
            db.add(new_q)

            fallback_answer = "لا يوجد جواب حاليًا لهذا السؤال. الرجاء التواصل مع فريق الدعم على الرقم 09999999"

            ass_msg = Message(
                conversation_id=conv.id,
                role="assistant",
                text=fallback_answer
            )
            db.add(ass_msg)

            conv.updated_at = datetime.utcnow()
            db.commit()

            return {"answer": fallback_answer, "conversation_id": conv.id}

        # 4) Otherwise → Use OpenAI to rewrite the FAQ answer
        prompt = f"""
السؤال: {q.question}
الإجابة التالية من قاعدة النظام العقاري:
{relevant_answer}

أعد صياغة الإجابة بشكل واضح ومباشر دون إضافة معلومات جديدة.
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "أنت مساعد متخصص في النظام العقاري."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
        )

        answer = response.choices[0].message.content.strip()

        # 5) Save assistant message
        ass_msg = Message(conversation_id=conv.id, role="assistant", text=answer)
        db.add(ass_msg)

        conv.updated_at = datetime.utcnow()
        db.commit()

        return {"answer": answer, "conversation_id": conv.id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





