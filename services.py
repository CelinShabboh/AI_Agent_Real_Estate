import base64
import os
import json
import pandas as pd  
import docx
import pdfplumber
from openai import OpenAI
from pptx import Presentation
from sqlalchemy.orm import Session
from io import BytesIO
import crud
import vector_service

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def classify_intent(user_text):
    prompt = f"""تصنف رسالة المستخدم لـ 'greeting' أو 'technical' أو 'out_of_scope'.
    - 'greeting': سلام أو ترحيب.
    - 'technical': سؤال عن العقارات، المنصة، الملفات المرفوعة، بنود العقود، أو الإجراءات القانونية العقارية.
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
    try:
        with pdfplumber.open(BytesIO(file_content)) as pdf:
            return "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
    except Exception as e:
        print(f"Error PDF: {e}")
        return ""

def extract_text_general(content: bytes, filename: str):
    filename = filename.lower()
    try:
        if filename.endswith('.pdf'):
            return extract_text_from_pdf(content)
        elif filename.endswith('.docx'):
            doc = docx.Document(BytesIO(content))
            return "\n".join([p.text for p in doc.paragraphs])
        elif filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(BytesIO(content))
            return "بيانات الجدول المستخرجة:\n" + df.to_string()
        elif filename.endswith('.pptx'):
            prs = Presentation(BytesIO(content))
            return "\n".join([shape.text for slide in prs.slides for shape in slide.shapes if hasattr(shape, "text")])
    except Exception as e:
        print(f"Extraction Error for {filename}: {e}")
    return ""

async def extract_text_from_image(image_bytes: bytes):
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    try:
        response = client.chat.completions.create( 
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "انسخ النص من الصورة حرفياً."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ],
                }
            ],
            temperature=0
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error: {e}")
        return ""

def get_ai_answer(db: Session, question: str, conv):
    manual_text = vector_service.search_vector_db(question, collection_type="site")
    
    from database import DocumentKnowledge
    db_docs = db.query(DocumentKnowledge).filter(DocumentKnowledge.conversation_id == conv.id).all()
    docs_text = "\n".join([f"محتوى ملف {d.file_name}:\n{d.content}" for d in db_docs])

    history = crud.get_chat_history(db, conv.id, limit=5)
    chat_context = [{"role": m.role, "content": m.text} for m in reversed(history)]

    system_prompt = f"""أنت المساعد الذكي للمنصة الوطنية للعقارات. 
استخدم المعلومات التالية للإجابة بدقة:

[معلومات من دليل المنصة]:
{manual_text}

[نصوص من الصور والمستندات المرفوعة في هذه المحادثة]:
{docs_text if docs_text else "لا توجد مستندات مرفوعة."}

تعليمات صارمة:
- إذا سأل المستخدم عن تفاصيل في العقد أو الصورة، استخرج الإجابة من [نصوص من الصور والمستندات المرفوعة].
- إذا لم تجد المعلومة في النصوص أعلاه، ابحث في [معلومات من دليل المنصة].
- إذا لم تجدها نهائياً، قل NOT_FOUND."""

    messages = [{"role": "system", "content": system_prompt}] + chat_context
    messages.append({"role": "user", "content": question})

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=messages,
            temperature=0,
            stream=True  
        )
        
        full_response = ""
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                yield content 

        if "NOT_FOUND" in full_response:
            crud.add_unanswered(db, question)
            yield "\n\n(ملاحظة: عذراً، لم أجد هذه التفاصيل، يرجى التواصل مع الدعم)."
        else:
            crud.save_message(db, conv.id, "assistant", full_response)
        
    except Exception as e:
        print(f"Error in AI Response: {e}")
        yield "عذراً، حدث خطأ أثناء الاتصال بالذكاء الاصطناعي."

def generate_chat_title(first_question: str):
    prompt = f"صغ عنواناً جذاباً وقصيراً جداً (3 كلمات) لهذا السؤال: {first_question}"
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20
        )
        return response.choices[0].message.content.strip()
    except:
        return first_question[:30]