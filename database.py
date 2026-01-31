from sqlalchemy import create_engine, Column, Integer, Text, String, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

is_local = "localhost" in DATABASE_URL or "127.0.0.1" in DATABASE_URL

if is_local:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"sslmode": "require"},
        pool_pre_ping=True,
        pool_recycle=300,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()