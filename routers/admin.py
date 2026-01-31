import os
import shutil
import uuid
from fastapi import APIRouter, Depends, Form, HTTPException, Query, File, UploadFile
from sqlalchemy.orm import Session
from database import get_db
from models import Conversation, DocumentKnowledge, SiteKnowledge, UnansweredQuestion
import schemas
import services
import vector_service
from fastapi import BackgroundTasks 

router = APIRouter(prefix="/admin", tags=["Admin Knowledge"])

@router.get("/knowledge/")
def list_knowledge(
    q: str = Query(None), 
    page: int = Query(1, ge=1), 
    limit: int = Query(20, ge=1), 
    db: Session = Depends(get_db)
):
    query = db.query(SiteKnowledge)
    if q:
        query = query.filter(
            (SiteKnowledge.section_name.ilike(f"%{q}%")) | 
            (SiteKnowledge.content.ilike(f"%{q}%"))
        )
    
    offset = (page - 1) * limit
    total = query.count()
    items = query.offset(offset).limit(limit).all()
    return {"total": total, "page": page, "limit": limit, "items": items}

#----------------------------------------------------------------------------

@router.post("/knowledge/", response_model=schemas.KnowledgeOut)
def add_knowledge(data: schemas.KnowledgeCreate, db: Session = Depends(get_db)):
    item = SiteKnowledge(section_name=data.section_name, content=data.content)
    db.add(item)
    db.commit()
    db.refresh(item)
    try:
        vector_service.add_to_vector_db(
            text=data.content,
            metadata={"section_name": data.section_name, "id": item.id},
            collection_type="site"
        )
    except:
        pass 
    return item

#----------------------------------------------------------------------------

@router.get("/unanswered/")
def list_unanswered(page: int = Query(1, ge=1), limit: int = Query(20, ge=1), db: Session = Depends(get_db)):
    offset = (page - 1) * limit
    total = db.query(UnansweredQuestion).count()
    items = db.query(UnansweredQuestion).offset(offset).limit(limit).all()
    return {"total": total, "page": page, "limit": limit, "items": items}

#----------------------------------------------------------------------------

@router.delete("/unanswered/{qid}")
def delete_unanswered(qid: int, db: Session = Depends(get_db)):
    item = db.query(UnansweredQuestion).filter(UnansweredQuestion.id == qid).first()
    if not item: raise HTTPException(status_code=404)
    db.delete(item)
    db.commit()
    return {"status": "deleted"}

#----------------------------------------------------------------------------

@router.post("/knowledge/resolve-unanswered/{qid}")
async def resolve_unanswered(qid: int, data: schemas.KnowledgeCreate, db: Session = Depends(get_db)):
    un_item = db.query(UnansweredQuestion).filter(UnansweredQuestion.id == qid).first()
    if not un_item: raise HTTPException(status_code=404)
    new_k = SiteKnowledge(section_name=data.section_name, content=data.content)
    db.add(new_k)
    db.delete(un_item)
    db.commit()
    return {"status": "resolved"}

#----------------------------------------------------------------------------

# @router.post("/upload-document/")
# async def upload_document(
#     background_tasks: BackgroundTasks,
#     file: UploadFile = File(...), 
#     conversation_id: Union[int, str, None] = Form(None), 
#     db: Session = Depends(get_db)
# ):
#     actual_id = None
#     if conversation_id not in [None, "null", "0", 0, ""]:
#         try:
#             actual_id = int(conversation_id)
#         except: actual_id = None

#     allowed_extensions = ('.pdf', '.docx', '.jpg', '.jpeg', '.png')
#     if not file.filename.lower().endswith(allowed_extensions):
#         raise HTTPException(status_code=400, detail="نوع الملف غير مدعوم.")

#     if not actual_id:
#         new_conv = Conversation(title=f"محادثة ملف: {file.filename}")
#         db.add(new_conv)
#         db.commit()
#         db.refresh(new_conv)
#         actual_id = new_conv.id

#     upload_dir = "static/uploads"
#     os.makedirs(upload_dir, exist_ok=True)
#     file_path = os.path.join(upload_dir, file.filename)
    
#     with open(file_path, "wb") as buffer:
#         shutil.copyfileobj(file.file, buffer)

#     web_friendly_path = file_path.replace(os.sep, '/')

#     db_doc = DocumentKnowledge(
#         file_name=file.filename, 
#         file_path=web_friendly_path,
#         content="جاري استخراج النص...", 
#         conversation_id=actual_id
#     )
#     db.add(db_doc)
#     db.commit()
#     db.refresh(db_doc)

#     background_tasks.add_task(services.process_file_task, db_doc.id, file_path, file.filename, actual_id)

#     return {
#         "status": "success",
#         "document_id": db_doc.id,
#         "conversation_id": actual_id,
#         "file_url": f"http://127.0.0.1:8000/{file_path.replace(os.sep, '/')}"
#     }

@router.post("/conversations/documents")
async def upload_chat_document(
    file: UploadFile = File(...),
    conversation_id: int = Form(None),  # اختياري
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    actual_conv_id = conversation_id

    # إذا ما أعطى المستخدم conv_id أو صفر → أنشئ محادثة جديدة
    if not actual_conv_id or actual_conv_id in [0, "0", "null", None]:
        new_conv = Conversation(title=f"محادثة ملف: {file.filename}")
        db.add(new_conv)
        db.commit()
        db.refresh(new_conv)
        actual_conv_id = new_conv.id

    # تحقق من وجود المحادثة
    conv = db.query(Conversation).filter(Conversation.id == actual_conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    allowed = ('.pdf', '.docx', '.jpg', '.jpeg', '.png')
    if not file.filename.lower().endswith(allowed):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    upload_dir = "static/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    safe_name = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(upload_dir, safe_name)

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    doc = DocumentKnowledge(
        conversation_id=actual_conv_id,
        file_name=file.filename,
        file_path=file_path.replace(os.sep, "/"),
        content="PROCESSING"
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(
        services.process_file_task,
        doc.id,
        file_path,
        file.filename,
        actual_conv_id
    )

    return {
        "id": doc.id,
        "type": "file",
        "file_name": doc.file_name,
        "file_url": f"/{doc.file_path}",
        "status": "processing",
        "conversation_id": actual_conv_id
    }


#----------------------------------------------------------------------------

@router.get("/conversations/{conv_id}/documents")
def list_conversation_documents(
    conv_id: int, 
    page: int = Query(1, ge=1), 
    limit: int = Query(20, ge=1), 
    db: Session = Depends(get_db)
):
    offset = (page - 1) * limit
    items = db.query(DocumentKnowledge).filter(
        DocumentKnowledge.conversation_id == conv_id
    ).order_by(DocumentKnowledge.created_at.desc()).offset(offset).limit(limit).all()
    
    for item in items:
        if item.file_path:
            item.file_url = f"http://127.0.0.1:8000/{item.file_path.replace(os.sep, '/')}"

    total = db.query(DocumentKnowledge).filter(
        DocumentKnowledge.conversation_id == conv_id
    ).count()

    return {
        "conversation_id": conv_id,
        "total": total,
        "page": page,
        "limit": limit,
        "items": items
    }

#----------------------------------------------------------------------------

@router.delete("/conversations/{conv_id}/delete")
def delete_conv(conv_id: int, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="المحادثة غير موجودة")

    for doc in conv.documents:
        if doc.file_path and os.path.exists(doc.file_path):
            try:
                os.remove(doc.file_path) 
            except Exception as e:
                print(f"فشل حذف الملف {doc.file_path}: {e}")

    db.delete(conv)
    db.commit()
    
    return {"status": "deleted", "message": "تم حذف المحادثة وكل ملفاتها وصورها بنجاح"}