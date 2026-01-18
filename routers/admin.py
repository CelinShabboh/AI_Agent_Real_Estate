from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
import schemas, crud
from database import DocumentKnowledge, get_db, SiteKnowledge, UnansweredQuestion
from fastapi import File, UploadFile
import services

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

@router.post("/knowledge/", response_model=schemas.KnowledgeOut)
def add_knowledge(data: schemas.KnowledgeCreate, db: Session = Depends(get_db)):
    item = SiteKnowledge(section_name=data.section_name, content=data.content)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item

@router.get("/knowledge/")
def list_knowledge(page: int = Query(1, ge=1), limit: int = Query(20, ge=1), db: Session = Depends(get_db)):
    offset = (page - 1) * limit
    total = db.query(SiteKnowledge).count()
    items = db.query(SiteKnowledge).offset(offset).limit(limit).all()
    return {"total": total, "page": page, "limit": limit, "items": items}

@router.get("/unanswered/")
def list_unanswered(page: int = Query(1, ge=1), limit: int = Query(20, ge=1), db: Session = Depends(get_db)):
    offset = (page - 1) * limit
    total = db.query(UnansweredQuestion).count()
    items = db.query(UnansweredQuestion).offset(offset).limit(limit).all()
    return {"total": total, "page": page, "limit": limit, "items": items}


@router.delete("/unanswered/{qid}")
def delete_unanswered(qid: int, db: Session = Depends(get_db)):
    item = db.query(UnansweredQuestion).filter(UnansweredQuestion.id == qid).first()
    if not item: raise HTTPException(status_code=404)
    db.delete(item)
    db.commit()
    return {"status": "deleted"}


@router.post("/knowledge/resolve-unanswered/{qid}")
async def resolve_unanswered(qid: int, data: schemas.KnowledgeCreate, db: Session = Depends(get_db)):
    un_item = db.query(UnansweredQuestion).filter(UnansweredQuestion.id == qid).first()
    if not un_item: raise HTTPException(status_code=404)
    new_k = SiteKnowledge(section_name=data.section_name, content=data.content)
    db.add(new_k)
    db.delete(un_item)
    db.commit()
    return {"status": "resolved"}


@router.post("/upload-document/")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="فقط ملفات PDF مدعومة حالياً.")
    
    content = await file.read()
    text_content = services.extract_text_from_pdf(content)
    
    if not text_content.strip():
        raise HTTPException(status_code=400, detail="لم نتمكن من استخراج نص من الملف.")
    
    db_doc = DocumentKnowledge(file_name=file.filename, content=text_content)
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    
    return {"message": f"تم رفع ومعالجة الملف {file.filename} بنجاح."}


@router.get("/documents/")
def list_documents(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    offset = (page - 1) * limit
    total = db.query(DocumentKnowledge).count()
    items = db.query(DocumentKnowledge).order_by(DocumentKnowledge.created_at.desc()).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": items
    }


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(DocumentKnowledge).filter(DocumentKnowledge.id == doc_id).first()
    if not doc: raise HTTPException(status_code=404)
    db.delete(doc)
    db.commit()
    return {"status": "تم حذف الملف من قاعدة المعرفة."}