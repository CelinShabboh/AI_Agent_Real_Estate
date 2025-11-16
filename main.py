from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import OpenAI
import os
import difflib
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

from database import SessionLocal, FAQ, UnansweredQuestion

# Load the key
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI(title="Real Estate Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://syrialistings.com:5174"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# A function to create a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class Question(BaseModel):
    question: str

# Searching for the most suitable answer from the FAQ table
def find_relevant_answer(question: str, db: Session):
    faqs = db.query(FAQ).all()
    if not faqs:
        return None

    all_entries = {f.id: f.question for f in faqs}
    best_match_id = max(all_entries, key=lambda id: difflib.SequenceMatcher(None, question, all_entries[id]).ratio())
    similarity = difflib.SequenceMatcher(None, question, all_entries[best_match_id]).ratio()

    if similarity < 0.5:  # If the question is strange or unrelated to any previous question
        return None
    return db.query(FAQ).filter(FAQ.id == best_match_id).first().answer


@app.post("/ask/")
async def ask_real_estate_agent(q: Question, db: Session = Depends(get_db)):
    try:
        relevant_answer = find_relevant_answer(q.question, db)

        # If no similar answer exists
        if not relevant_answer:
            # Save the question in the unanswered questions table
            new_q = UnansweredQuestion(question=q.question)
            db.add(new_q)
            db.commit()
            return {
                "answer": "لا يوجد جواب حاليًا لهذا السؤال. الرجاء التواصل مع فريق الدعم على الرقم 0999999999."
            }

        # Rewriting the answer using OpenAI (without generating a new one)
        prompt = f"""
        السؤال: {q.question}
        الإجابة التالية من قاعدة النظام العقاري:
        {relevant_answer}

        أعد صياغة الإجابة بشكل واضحة ومباشرة دون إضافة معلومات جديدة.
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "أنت مساعد متخصص في النظام العقاري، تجيب فقط بناءً على النص المقدم"},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
        )

        answer = response.choices[0].message.content.strip()
        return {"answer": answer}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
