import os, json
from openai import OpenAI
from sqlalchemy.orm import Session
from database import SiteKnowledge
import crud
import PyPDF2
from io import BytesIO
from database import DocumentKnowledge

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def classify_intent(user_text):
    prompt = f"""تصنف رسالة المستخدم لـ 'greeting' أو 'technical' أو 'out_of_scope'.
    - 'greeting': سلام أو ترحيب.
    - 'technical': سؤال عن العقارات، المنصة، أو الملفات المرفوعة.
    - 'out_of_scope': مواضيع شخصية، عاطفية، سياسية، أو أي شيء خارج العقارات.

    رد بـ JSON: 
    {{
      "intent": "...",
      "reply": "إذا كان out_of_scope، رد باعتذار مهني يوضح أنك خبير عقاري فقط. إذا كان greeting، رد بترحيب مهني."
    }}
    
    الرسالة: {user_text}"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={ "type": "json_object" },
        temperature=0
    )
    return json.loads(response.choices[0].message.content)

def extract_text_from_pdf(file_content: bytes):
    pdf_reader = PyPDF2.PdfReader(BytesIO(file_content))
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() or ""
    return text

def get_ai_answer(db: Session, question: str, conv):
    manual_k = db.query(SiteKnowledge).all()
    manual_text = "\n".join([f"--- {k.section_name} ---\n{k.content}" for k in manual_k])
    
    docs_k = db.query(DocumentKnowledge).all()
    docs_text = "\n".join([f"--- ملف: {d.file_name} ---\n{d.content}" for d in docs_k])
    
    history = crud.get_chat_history(db, conv.id)
    chat_context = [{"role": m.role, "content": m.text} for m in reversed(history)]

    system_prompt = f"""أنت مساعد خبير في المنصة الوطنية للعقارات. 
    استخدم المعلومات التالية للإجابة (تشمل دليل المنصة ومحتوى الملفات المرفوعة):
    
    [دليل المنصة]:
    {manual_text}
    
    [محتوى الملفات والتقارير]:
    {docs_text}
    
    تعليمات:
    - إذا كانت الإجابة من ملف معين، اذكر اسم الملف في ردك.
    - إذا لم تجد الإجابة، رد بـ NOT_FOUND."""

    messages = [{"role": "system", "content": system_prompt}] + chat_context

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0,
            stream=True  
        )
        
        full_response = ""
        for chunk in response:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                yield content  
        if "NOT_FOUND" in full_response:
            crud.add_unanswered(db, question)
        
        crud.save_message(db, conv.id, "assistant", full_response)
        
    except Exception as e:
        yield "حدث خطأ تقني."
    
def generate_chat_title(first_question: str):
    prompt = f"""قم بصياغة عنوان قصير جداً (3-5 كلمات) باللغة العربية يلخص هذا السؤال العقاري:
    "{first_question}"
    رد بالعنوان فقط بدون مقدمات ولا علامات تنصيص."""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except:
        return first_question[:40] 