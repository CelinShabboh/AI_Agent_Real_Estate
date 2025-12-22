import json
import re
import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import OpenAI
from dotenv import load_dotenv

from database import SessionLocal, UnansweredQuestion, Conversation, Message, SiteKnowledge

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI(title="Real Estate Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
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

# Models
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

class FAQCreate(BaseModel):
    question: str
    answer: str

class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None

class FAQOut(BaseModel):
    id: int
    question: str
    answer: str

    class Config:
        orm_mode = True

class UnansweredQuestionOut(BaseModel):
    id: int
    question: str
    created_at: datetime

    class Config:
        orm_mode = True


class UnansweredQuestionCreate(BaseModel):
    question: str

class KnowledgeCreate(BaseModel):
    section_name: str
    content: str

class KnowledgeOut(BaseModel):
    id: int
    section_name: str
    content: str
    created_at: datetime
    class Config: orm_mode = True

# ------------------------------
# Helper Functions
# ------------------------------

def classify_and_reply(user_text):
    prompt = f"""
    تصنف رسالة المستخدم لواحد من خيارين:
    1. 'greeting': إذا كانت تحية أو كلام عام.
    2. 'technical': إذا كان سؤال عن النظام أو العقارات.
    
    يجب أن يكون الرد بصيغة JSON حصراً كالتالي:
    {{
      "intent": "greeting أو technical",
      "reply": "اكتب رد مناسب إذا كان greeting وإلا اتركه فارغاً"
    }}
    
    رسالة المستخدم: "{user_text}"
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={ "type": "json_object" }, 
        temperature=0
    )
    return json.loads(response.choices[0].message.content)

def create_conversation_from_first_message(db: Session, first_text: str) -> Conversation:
    title = (first_text.strip()[:60]) or "محادثة جديدة"
    conv = Conversation(title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv

@app.post("/knowledge/", response_model=KnowledgeOut)

def add_site_knowledge(data: KnowledgeCreate, db: Session = Depends(get_db)):

    item = SiteKnowledge(section_name=data.section_name, content=data.content)

    db.add(item)

    db.commit()

    db.refresh(item)

    return item

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

@app.get("/unanswered/")
def list_unanswered(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    offset = (page - 1) * limit

    total = db.query(UnansweredQuestion).count()

    rows = (
        db.query(UnansweredQuestion)
        .order_by(UnansweredQuestion.created_at.desc())
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


@app.delete("/unanswered/{qid}")
def delete_unanswered(qid: int, db: Session = Depends(get_db)):
    item = db.query(UnansweredQuestion).filter(UnansweredQuestion.id == qid).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Unanswered question not found")

    db.delete(item)
    db.commit()
    return {"status": "deleted"}


@app.get("/knowledge/")

def list_knowledge(db: Session = Depends(get_db)):

    return db.query(SiteKnowledge).all()



@app.put("/knowledge/{knowledge_id}")

async def update_site_knowledge(knowledge_id: int, updated_data: KnowledgeCreate, db: Session = Depends(get_db)):

    db_knowledge = db.query(SiteKnowledge).filter(SiteKnowledge.id == knowledge_id).first()

   

    if not db_knowledge:

        raise HTTPException(status_code=404, detail="المعلومة غير موجودة")



    db_knowledge.section_name = updated_data.section_name

    db_knowledge.content = updated_data.content

    db_knowledge.updated_at = datetime.utcnow()



    db.commit()

    db.refresh(db_knowledge)

    return {"message": "تم تحديث المعلومة بنجاح", "data": db_knowledge}

# ------------------------------
# MAIN /ask/ Logic
# ------------------------------

@app.post("/ask/")
async def ask_real_estate_agent(q: Question, db: Session = Depends(get_db)):
    try:
        conv = None
        if q.conversation_id:
            conv = db.query(Conversation).filter(Conversation.id == q.conversation_id).first()
        if not conv:
            conv = create_conversation_from_first_message(db, q.question)

        user_msg = Message(conversation_id=conv.id, role="user", text=q.question)
        db.add(user_msg)
        db.commit()

        classification = classify_and_reply(q.question)

        if classification["intent"] == "greeting":
            reply = classification["reply"]
            ass_msg = Message(conversation_id=conv.id, role="assistant", text=reply)
            db.add(ass_msg)
            db.commit()
            return {"answer": reply, "conversation_id": conv.id}

        knowledge_entries = db.query(SiteKnowledge).all()
        project_story = "\n".join([f"--- {k.section_name} ---\n{k.content}" for k in knowledge_entries])

        if not project_story:
            return await handle_unanswered(q.question, conv, db)

        reasoning_prompt = f"""
أنت مساعد ذكي وخبير في "المنصة الوطنية للعقارات".
مهمتك: الإجابة على سؤال المستخدم باستخدام "الدليل" المرفق فقط.

**الدليل المتاح:**
{project_story}

**سؤال المستخدم:** {q.question}

**التعليمات:**
1. إذا سأل المستخدم عن اتجاه السوق (زيادة/نقصان)، ابحث في قسم "حركة السوق" عن "معدل التغيير".
2. إذا كانت البيانات المتاحة تظهر قيماً لعام 2025 مقابل 0 لعام 2024، وضح للمستخدم أن النظام حالياً يعرض بيانات سنة واحدة أو أن المقارنة بدأت للتو.
3. لا تجب بـ NOT_FOUND إلا إذا كان السؤال عن ميزة غير موجودة نهائياً في الدليل (مثل: كيف أغير لون الواجهة؟).
4. أجب بلهجة واثقة ومبنية على الأرقام الموجودة في الدليل.
5. أعد صياغة الإجابة الموثوقة المرفقة أعلاه (فقط) لتبدو طبيعية ومتوافقة مع **لغة ولهجة** المستخدم (عامية أو فصحى أو إنجليزية).
6. يمكن استخدام الرموز التعبيرية خاصة عند وصف المستخدم لمشاعر لديه
7. تمييز جنس المستخدم من خلال رسائله والرد عليه حسب جنسه أنثى أو ذكر أو محايد
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": reasoning_prompt}],
            temperature=0
        )
        ai_answer = response.choices[0].message.content.strip()

        if "NOT_FOUND" in ai_answer:
            return await handle_unanswered(q.question, conv, db)
        
        ass_msg = Message(conversation_id=conv.id, role="assistant", text=ai_answer)
        db.add(ass_msg)
        db.commit()
        return {"answer": ai_answer, "conversation_id": conv.id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def handle_unanswered(question, conv, db):
    new_q = UnansweredQuestion(question=question)
    db.add(new_q)
    fallback = "أعتذر، هذه المعلومة غير متوفرة لدي حالياً. تم إرسال سؤالك للإدارة."
    ass_msg = Message(conversation_id=conv.id, role="assistant", text=fallback)
    db.add(ass_msg)
    db.commit()
    return {"answer": fallback, "conversation_id": conv.id}
