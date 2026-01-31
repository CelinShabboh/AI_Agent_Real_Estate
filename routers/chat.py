from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from models import Conversation
import schemas
import crud, services
from database import get_db
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/chat", tags=["Chat & Conversations"])

@router.post("/ask/")
async def ask_real_estate_agent(q: schemas.Question, db: Session = Depends(get_db)):
    conv = crud.get_or_create_conversation(db, q.question, q.conversation_id)
    
    crud.save_message(db, conv.id, "user", q.question)

    return StreamingResponse(
        services.get_ai_answer(db, q.question, conv),
        media_type="text/event-stream", 
        headers={
            "X-Conversation-Id": str(conv.id),
            "Access-Control-Expose-Headers": "X-Conversation-Id",
            "X-Accel-Buffering": "no",  
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

#----------------------------------------------------------------------------

@router.get("/conversations/")
def list_conversations(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    offset = (page - 1) * limit
    total = db.query(Conversation).count()
    items = db.query(Conversation).order_by(Conversation.updated_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "page": page, "limit": limit, "items": items}

#----------------------------------------------------------------------------

@router.get("/conversations/{conv_id}/messages")
def get_messages(conv_id: int, cursor: int = Query(None), limit: int = 30, db: Session = Depends(get_db)):
    from database import Message
    query = db.query(Message).filter(Message.conversation_id == conv_id)
    if cursor: query = query.filter(Message.id < cursor)
    
    messages = query.order_by(Message.id.desc()).limit(limit).all()
    next_cursor = messages[-1].id if messages else None
    
    return {
        "items": list(reversed(messages)), 
        "next_cursor": next_cursor,
        "limit": limit
    }

#----------------------------------------------------------------------------

@router.patch("/conversations/{conv_id}/rename")
def rename_conv(conv_id: int, data: schemas.ConversationRename, db: Session = Depends(get_db)):
    success = crud.rename_conversation(db, conv_id, data.title) 
    if not success: raise HTTPException(status_code=404)
    return {"status": "updated"}

#----------------------------------------------------------------------------

# @router.delete("/conversations/{conv_id}/delete")
# def delete_conv(conv_id: int, db: Session = Depends(get_db)):
#     success = crud.delete_conversation(db, conv_id) 
#     if not success: raise HTTPException(status_code=404)
#     return {"status": "deleted"}

#----------------------------------------------------------------------------

@router.patch("/messages/{message_id}/edit")
async def edit_message(message_id: int, data: schemas.MessageUpdate, db: Session = Depends(get_db)):
    updated_msg = crud.update_message_text(db, message_id, data.text)
    if not updated_msg:
        raise HTTPException(status_code=404, detail="الرسالة غير موجودة")
    
    if updated_msg.role == "user":
        db.query(crud.Message).filter(
            crud.Message.conversation_id == updated_msg.conversation_id,
            crud.Message.id > message_id
        ).delete()
        db.commit()

        conv = db.query(crud.Conversation).filter(crud.Conversation.id == updated_msg.conversation_id).first()

        return StreamingResponse(
    services.get_ai_answer(db, data.text, conv),
    media_type="text/plain",
    headers={
        "X-Conversation-Id": str(conv.id),
        "Access-Control-Expose-Headers": "X-Conversation-Id"
    }
)
    
    return {"status": "success", "updated_text": updated_msg.text}