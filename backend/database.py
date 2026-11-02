from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Database ki file ka address (backend folder mein app.db banegi)
DATABASE_URL = "sqlite:///./app.db"

# Engine = database se connection
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

# Session = database se baat karne ka ek "chat window"
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Base = saari tables ki "parent class"
Base = declarative_base()