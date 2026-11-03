from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone

from database import engine, SessionLocal
import models

app = FastAPI()

models.Base.metadata.create_all(bind=engine)

SECRET_KEY = "change-this-to-a-long-random-secret"
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 30
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


# Har request ke liye database session kholta hai, kaam ke baad band karta hai
def get_db():
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_role(*allowed_roles: str):
    def checker(current_user: models.User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Not enough permissions")
        return current_user
    return checker


class UserRegister(BaseModel):
    name: str
    email: str
    password: str

class UserLogin(BaseModel):
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

@app.post("/login")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    db_user = db.query(models.User).filter(models.User.email == form.username).first()

    if not db_user or not bcrypt.checkpw(
        form.password.encode("utf-8"), db_user.password_hash.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    expire = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    token = jwt.encode(
        {"sub": db_user.email, "role": db_user.role, "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    return {"access_token": token, "token_type": "bearer"}

@app.get("/me")
def read_me(current_user: models.User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
    }


@app.get("/admin/users")
def list_users(
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_role("admin")),
):
    users = db.query(models.User).all()
    return [
        {"id": u.id, "name": u.name, "email": u.email, "role": u.role}
        for u in users
    ]

@app.post("/assessments", status_code=201)
def create_assessment(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    assessment = models.Assessment(user_id=current_user.id)
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return {
        "id": assessment.id,
        "status": assessment.status,
        "created_at": assessment.created_at,
    }


@app.get("/assessments")
def my_assessments(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    items = (
        db.query(models.Assessment)
        .filter(models.Assessment.user_id == current_user.id)
        .all()
    )
    return [
        {"id": a.id, "status": a.status, "created_at": a.created_at}
        for a in items
    ]