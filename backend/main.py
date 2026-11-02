from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
import bcrypt

from database import engine, SessionLocal
import models

app = FastAPI()

models.Base.metadata.create_all(bind=engine)


# Har request ke liye database session kholta hai, kaam ke baad band karta hai
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class UserRegister(BaseModel):
    name: str
    email: str
    password: str


@app.get("/")
def home():
    return {"message": "Hello, backend is running!"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/register", status_code=201)
def register(user: UserRegister, db: Session = Depends(get_db)):
    # 1. Check karo ki email pehle se to nahi hai
    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # 2. Password ko hash karo
    hashed = bcrypt.hashpw(user.password.encode("utf-8"), bcrypt.gensalt())

    # 3. Naya user banao aur database mein save karo
    new_user = models.User(
        name=user.name,
        email=user.email,
        password_hash=hashed.decode("utf-8"),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 4. Response (password kabhi wapas nahi bhejte)
    return {
        "message": "User registered successfully",
        "id": new_user.id,
        "name": new_user.name,
        "email": new_user.email,
        "role": new_user.role,
    }