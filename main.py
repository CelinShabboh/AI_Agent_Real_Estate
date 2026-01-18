from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import chat, admin

app = FastAPI(title="Real Estate Assistant API v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(admin.router)

@app.get("/")
def health_check():
    return {"status": "GPT Agent is running"}