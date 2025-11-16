from sqlalchemy import create_engine, Column, Integer, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")  

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

#Table of unanswered questions
class FAQ(Base):
    __tablename__ = "faqs"
    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)

# Table of New Unanswered Questions
class UnansweredQuestion(Base):
    __tablename__ = "unanswered"
    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, nullable=False)

# Create tables if they do not exist
Base.metadata.create_all(bind=engine)
