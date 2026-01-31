from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import models
from routers import chat, admin
from database import engine

app = FastAPI(title="Real Estate Assistant API v2")

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
    expose_headers=["x-conversation-id"], 
)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://syrianlistings.com:5174"], 
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

app.include_router(chat.router)
app.include_router(admin.router)

@app.get("/")
def health_check():
    return {"status": "GPT Agent is running"}

models.Base.metadata.create_all(bind=engine)