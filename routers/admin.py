from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Query, File, UploadFile
from sqlalchemy.orm import Session
import schemas
from database import Conversation, DocumentKnowledge, get_db, SiteKnowledge, UnansweredQuestion
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

@router.post("/upload-document/")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    conversation_id: Optional[int] = Form(None), 
    db: Session = Depends(get_db)
):
    allowed_extensions = ('.pdf', '.docx', '.jpg', '.jpeg', '.png')
    if not file.filename.lower().endswith(allowed_extensions):
        raise HTTPException(status_code=400, detail="نوع الملف غير مدعوم.")

    if not conversation_id:
        new_conv = Conversation(title=f"محادثة ملف: {file.filename}")
        db.add(new_conv)
        db.commit()
        db.refresh(new_conv)
        conversation_id = new_conv.id

    db_doc = DocumentKnowledge(
        file_name=file.filename, 
        content="جاري استخراج النص في الخلفية...", 
        conversation_id=conversation_id
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)

    content = await file.read()
    background_tasks.add_task(process_file_task, db_doc.id, content, file.filename, conversation_id)

    return {
        "status": "success",
        "message": "بدأ رفع ومعالجة الملف في الخلفية، يمكنك متابعة المحادثة.",
        "document_id": db_doc.id,
        "conversation_id": conversation_id
    }

#----------------------------------------------------------------------------

async def process_file_task(doc_id: int, content: bytes, filename: str, conv_id: int):
    from database import SessionLocal 
    db = SessionLocal()
    try:
        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            text = await services.extract_text_from_image(content)
        else:
            text = services.extract_text_general(content, filename)
        
        if text:
            doc = db.query(DocumentKnowledge).filter(DocumentKnowledge.id == doc_id).first()
            if doc:
                doc.content = text
                db.commit()
                vector_service.add_to_vector_db(text, {"file_name": filename}, "docs")
    finally:
        db.close()
    
#----------------------------------------------------------------------------

@router.get("/documents/")
def list_documents(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    offset = (page - 1) * limit
    total = db.query(DocumentKnowledge).count()
    items = db.query(DocumentKnowledge).order_by(DocumentKnowledge.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "page": page, "limit": limit, "items": items}

#----------------------------------------------------------------------------

@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(DocumentKnowledge).filter(DocumentKnowledge.id == doc_id).first()
    if not doc: raise HTTPException(status_code=404)
    db.delete(doc)
    db.commit()
    return {"status": "تم حذف الملف."}