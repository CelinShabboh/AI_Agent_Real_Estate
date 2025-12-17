# main.py
import difflib
import json
import re
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import OpenAI
import os
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
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
        "https://syrianlistings.com:5174",
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


# ------------------------------
# Helper Functions
# ------------------------------

# Helper function for text normalization
def normalize_arabic(text: str) -> str:
    text = re.sub(r'[؟،!.،:؛()]', '', text)
    text = re.sub("[إأآا]", "ا", text)
    text = re.sub("ى", "ي", text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def find_relevant_answer(question: str, db: Session): 
    
    normalized_question = normalize_arabic(question)

    faqs = db.query(FAQ).all() 
    if not faqs: 
        return None 
    
    all_entries_normalized = {
        f.id: normalize_arabic(f.question) for f in faqs
    }
    
    best_match_id = max( 
        all_entries_normalized, 
        key=lambda id: difflib.SequenceMatcher(
            None, normalized_question, all_entries_normalized[id]
        ).ratio() 
    ) 
    
    similarity = difflib.SequenceMatcher( 
        None, normalized_question, all_entries_normalized[best_match_id] 
    ).ratio() 
    
    if similarity < 0.75: 
        return None 
        
    return db.query(FAQ).filter(FAQ.id == best_match_id).first().answer


def create_conversation_from_first_message(db: Session, first_text: str) -> Conversation:
    title = (first_text.strip()[:60]) or "محادثة جديدة"
    conv = Conversation(title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv

def classify_and_reply(user_text):
    prompt = f"""
أريد منك تصنيف رسالة المستخدم ضمن واحدة من الفئات التالية بدقة عالية جداً:

----------------------------------------
1) greeting → رسائل الترحيب:
   أمثلة: مرحبا، أهلين، السلام عليكم، مرحبا كيفك...
   *يسمح باستخدام رموز تعبيرية.*

----------------------------------------
2) smalltalk → الدردشة العامة + المشاعر + الغزل + الفضفضة + الشكر + الطلب العاطفي:
   يشمل كل الجُمل التالية (حتى لو فيها ؟):
   - كيفك، شو الأخبار، تمام، بخير، الحمدلله...
   - شكراً، يسلمو، يعطيك العافية...
   - أحبك، اشتقتلك، يا روحي، يا قلبي...
   - أنا زعلان/زعلانة، متضايق/متضايقة، تعبان/تعبانة...
   - ساعدني، فيك تساعدني، بدي أحكي، محتاج دعم...
   - شو تنصحني؟ كيف أكون سعيدة؟ حياتي فوضى...
   - أي فضفضة، رومانسية، مشاعر، ملل، ضحك، بكاء، نكات...
   - أي “طلب صداقة” أو “اهتمام”.

   ❗هذه الفئة ليست سؤالاً أبداً حتى لو احتوت علامة استفهام.

----------------------------------------
3) user_gender → تحديد جنس المستخدم من طريقة كلامه:
   - وجود تاء مربوطة في ضمائر المستخدم: "زعلانة، محتارة، حابة" → female
   - عدم وجودها: "زعلان، محتار، حابب" → male
   - إذا لا يوجد أي مؤشر واضح → unknown

----------------------------------------
4) صياغة الرد:
   - خاطِب المستخدم حسب جنسه هو، وليس حسب جنس المساعد.
   - إذا المستخدم أنثى → استخدم لهجة المؤنث.
   - إذا المستخدم ذكر → استخدم لهجة المذكر.
   - إذا unknown → استخدم صيغة محايدة.

   ⚠️ شخصية المساعد يجب أن تبقى ذكراً دائماً:
      - لا تسمح لنفسك بالرد بصيغة مؤنثة.
      - الصيغ المؤنثة تستخدم فقط عند مخاطبة مستخدمة أنثى.

   الرد يجب أن يكون:
      - جملة كاملة ولطيفة
      - تحتوي رموز تعبيرية مناسبة
      - وليس رمزاً واحداً فقط أبداً

----------------------------------------
5) question → الأسئلة الحقيقية فقط:
   الأسئلة التي تطلب معلومات، خطوات، شرح، أو شيء فعلي.
   مثل:
   - كيف أفعل الحساب؟
   - أين أجد الإعدادات؟
   - ما رقم الدعم؟
   - كيف أستخدم الميزة؟
   - **(مُضاف): أي سؤال عن إمكانية (فيني/هل يمكنني) القيام بخطوة أو استخدام ميزة محددة في النظام (مثل إرسال إشعار، تعديل ملف، حذف طلب) يُصنّف كـ "question".**
   - **(مُضاف): يجب تصنيف الجمل العامية التي تبدأ بأدوات استفهام (كيف، وين، شو، ليش) كسؤال حتى لو لم تنتهِ بعلامة استفهام.**

   *لا يسمح بوضع أي رموز تعبيرية هنا.*
   *ولا يُعاد reply في حالة السؤال.*

----------------------------------------

6) اللغة:
   - النص قد يكون بالعربية أو الإنجليزية أو مزيج منهما.
   - طبّق نفس قواعد التصنيف على أي لغة.
   - حدد جنس المستخدم حتى لو كتب بالإنجليزية (مثال: I'm tired → male، I'm tired girl → female، I'm sad → unknown).
   - الرد يكون بنفس لغة المستخدم دائماً.

----------------------------------------
❗ مهم جداً:
الرسائل التالية تُصنف smalltalk وليست question:
- "بدي أسألك كم سؤال"
- "فيك تساعدني؟"
- "أنا بخير فيك تساعدني بشي؟"
- "بدي أحكي معك شوي"

----------------------------------------

أرجع لي فقط JSON بدون أي كلام خارجه:

{{
  "intent": "...",
  "user_gender": "...",
  "reply": "..."
}}

⚠️ إذا كان intent = "question" أرجعه بدون reply.
⚠️ الرد يجب أن يكون جملة كاملة ولطيفة مع رموز تعبيرية حسب الحالة النفسية للشخص ضمن جملة فقط.
⚠️ لا يُسمح بإرجاع رمز تعبيري فقط، ولكن يُسمح باستخدامه ضمن جملة.

عند الرد على مشاعر المستخدم:
- إذا كان المستخدم حزين/زعلان/متضايق → يجب استخدام رموز تعبيرية حزينة مناسبة مثل 😢😔💔
- إذا كان المستخدم سعيد/مرتاح → استخدم رموز سعيدة مثل 😊✨💛
- إذا كان المستخدم يطلب دعم أو مساعدة نفسية → استخدم رموز تعبر عن التعاطف مثل 🤍🌼

أي سؤال إنجليزي يحتوى:
how, what, where, when, why
→ يصنّف "question" بدون reply.

❗ قاعدة مهمة:
أي سؤال عن قدرة المساعد أو شخصيته أو لغته أو وجوده:
(can you speak english, do you understand me, are you real, who are you)
→ يصنّف smalltalk وليس question.

❗ قاعدة اللغة:
إذا كتب المستخدم باللغة الإنكليزية، يجب أن يكون الرد باللغة الإنكليزية أيضاً،
مع الحفاظ على الشخصية الذكورية للمساعد، واستخدام رموز تعبيرية مناسبة وممكن أنها حسب حالة الشخص وممكن استخدام أكثر من رمز.
وإذا كتب بالعربية → يكون الرد بالعربية.

نص المستخدم: "{user_text}"
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    content = response.choices[0].message.content.strip()

    try:
        return json.loads(content)
    except:
        start = content.find("{")
        end = content.rfind("}") + 1
        fixed = content[start:end]
        return json.loads(fixed)

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

# ------------------------------------------------------
# FAQ CRUD
# ------------------------------------------------------

@app.get("/faqs/")
def list_faqs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):

    offset = (page - 1) * limit

    total = db.query(FAQ).count()

    rows = (
        db.query(FAQ)
        .order_by(FAQ.id.desc())
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


@app.post("/faqs/", response_model=FAQOut)
def create_faq(data: FAQCreate, db: Session = Depends(get_db)):
    faq = FAQ(question=data.question, answer=data.answer)
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return faq


@app.put("/faqs/{faq_id}", response_model=FAQOut)
def update_faq(faq_id: int, data: FAQUpdate, db: Session = Depends(get_db)):
    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")

    if data.question is not None:
        faq.question = data.question
    if data.answer is not None:
        faq.answer = data.answer

    db.commit()
    db.refresh(faq)
    return faq


@app.delete("/faqs/{faq_id}")
def delete_faq(faq_id: int, db: Session = Depends(get_db)):
    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")

    db.delete(faq)
    db.commit()
    return {"status": "deleted"}

# ------------------------------------------------------
# Unanswered Questions (View + Delete Only)
# ------------------------------------------------------

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

        classification = classify_and_reply(q.question)

        if classification["intent"] in ["greeting", "smalltalk"]:
            reply = classification["reply"]

            ass_msg = Message(
                conversation_id=conv.id,
                role="assistant",
                text=reply
            )
            db.add(ass_msg)

            conv.updated_at = datetime.utcnow()
            db.commit()

            return {"answer": reply, "conversation_id": conv.id}
        
        # 3) Try to find FAQ answer
        relevant_answer = find_relevant_answer(q.question, db)


        if not relevant_answer:
            new_q = UnansweredQuestion(question=q.question)
            db.add(new_q)

            fallback_answer = f"""
أعتذر، لم أجد إجابة محددة لهذا السؤال في قاعدة البيانات حالياً.
**لحل مشكلتك بشكل فوري:** يمكنك التواصل مباشرة مع فريق الدعم على الرقم 09999999.
كما يمكنك محاولة إعادة صياغة سؤالك بوضوح أكثر (مثل: كيف أُضيف [الميزة] كـ [الدور]؟)، وسأبذل قصارى جهدي للمساعدة! 🤍
"""

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
السؤال الذي طرحه المستخدم (لهجة المستخدم): {q.question}

الإجابة الموثوقة من قاعدة بيانات النظام العقاري (يجب الالتزام بها حرفياً في المعنى):
{relevant_answer}

**المهمة:**
1.  أعد صياغة الإجابة الموثوقة المرفقة أعلاه (فقط) لتبدو طبيعية ومتوافقة مع **لغة ولهجة** المستخدم (عامية أو فصحى أو إنجليزية).
2.  **يمنع منعاً باتاً** إضافة أي محتوى جديد، تعريفات عامة، عبارات دعم عاطفي مثل (أنا هنا لدعمك)، أو **أي رموز تعبيرية**.
3.  يجب أن يكون الرد مخصصاً ومحدداً للمعلومة المرفقة (مثل **"مخصصة فقط للمسؤولين"**).
4.  أعد الإجابة النهائية فقط بدون أي مقدمات أو شرح للمهمة.

الرد النهائي:
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
