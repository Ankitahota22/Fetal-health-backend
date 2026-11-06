import os
from dotenv import load_dotenv
import time
import httpx
import json
from fastapi.responses import FileResponse
import io
import hashlib
import uuid
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
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

load_dotenv(Path(__file__).parent / ".env")

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY missing in .env file")
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 30
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

UPLOAD_DIR = Path(__file__).parent / "uploads_data"
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_FORMATS = {"JPEG": "jpg", "PNG": "png"}


AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://127.0.0.1:8001")


MAX_RETRIES = 3


def call_ai_service(image_bytes: bytes, filename: str, content_type: str) -> dict:
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = httpx.post(
                f"{AI_SERVICE_URL}/predict",
                files={"file": (filename, image_bytes, content_type)},
                timeout=10.0,
            )
            # 4xx = hamari galti (galat image), retry ka fayda nahi
            if 400 <= response.status_code < 500:
                raise HTTPException(
                    status_code=400, detail="AI service rejected the image"
                )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            last_error = e
            if attempt < MAX_RETRIES:
                time.sleep(attempt)  # 1 sec, phir 2 sec rukna
    raise last_error

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

@app.post("/assessments/{assessment_id}/image", status_code=201)
def upload_image(
    assessment_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 1. Assessment hai aur isi user ka hai?
    assessment = (
        db.query(models.Assessment)
        .filter(
            models.Assessment.id == assessment_id,
            models.Assessment.user_id == current_user.id,
        )
        .first()
    )
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # 2. File padho (size limit ke saath)
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    # 3. Pillow se check: kya yeh sach mein image hai?
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()  # corrupt file pakadta hai
        img = Image.open(io.BytesIO(data))  # verify ke baad dobara kholna padta hai
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Invalid or corrupt image")

    # 4. Sirf JPEG / PNG
    fmt = img.format
    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(
            status_code=415, detail="Only JPEG and PNG images are allowed"
        )

    # 5. Metadata hatao: sirf pixels ko naye image mein copy karo
    clean = Image.new(img.mode, img.size)
    clean.putdata(list(img.getdata()))
    buffer = io.BytesIO()
    clean.save(buffer, format=fmt)
    clean_bytes = buffer.getvalue()

    # 6. Hash, random naam, save
    sha256 = hashlib.sha256(clean_bytes).hexdigest()
    stored_name = f"{uuid.uuid4().hex}.{ALLOWED_FORMATS[fmt]}"
    (UPLOAD_DIR / stored_name).write_bytes(clean_bytes)

    # 7. Database record
    asset = models.ImageAsset(
        assessment_id=assessment.id,
        stored_name=stored_name,
        size_bytes=len(clean_bytes),
        content_type=f"image/{ALLOWED_FORMATS[fmt]}".replace("jpg", "jpeg"),
        sha256=sha256,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    return {
        "id": asset.id,
        "assessment_id": asset.assessment_id,
        "size_bytes": asset.size_bytes,
        "content_type": asset.content_type,
        "sha256": asset.sha256,
    }

@app.get("/images/{image_id}")
def get_image(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 1. Image record dhundho
    asset = db.query(models.ImageAsset).filter(models.ImageAsset.id == image_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Image not found")

    # 2. Permission check
    if current_user.role not in ("doctor", "admin"):
        assessment = (
            db.query(models.Assessment)
            .filter(
                models.Assessment.id == asset.assessment_id,
                models.Assessment.user_id == current_user.id,
            )
            .first()
        )
        if not assessment:
            raise HTTPException(status_code=404, detail="Image not found")

    # 3. File disk par hai?
    file_path = UPLOAD_DIR / asset.stored_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image file missing")

    # 4. Image bhejo
    return FileResponse(file_path, media_type=asset.content_type or "image/jpeg")

@app.post("/assessments/{assessment_id}/predict", status_code=201)
def run_prediction(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 1. Assessment isi user ki hai?
    assessment = (
        db.query(models.Assessment)
        .filter(
            models.Assessment.id == assessment_id,
            models.Assessment.user_id == current_user.id,
        )
        .first()
    )
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # 2. Is assessment ki image hai?
    asset = (
        db.query(models.ImageAsset)
        .filter(models.ImageAsset.assessment_id == assessment.id)
        .order_by(models.ImageAsset.id.desc())
        .first()
    )
    if not asset:
        raise HTTPException(status_code=400, detail="Upload an image first")

    # 3. Image padho aur AI ko bhejo (abhi mock)
    image_bytes = (UPLOAD_DIR / asset.stored_name).read_bytes()
    try:
        result = call_ai_service(
            image_bytes, asset.stored_name, asset.content_type or "image/jpeg"
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="AI service unavailable")

    # 4. Result save karo
    prediction = models.Prediction(
        assessment_id=assessment.id,
        predicted_class=result["predicted_class"],
        probabilities=json.dumps(result["probabilities"]),
        model_version=result["model_version"],
    )
    db.add(prediction)
    assessment.status = "completed"
    db.commit()
    db.refresh(prediction)

    return {
        "id": prediction.id,
        "assessment_id": prediction.assessment_id,
        "predicted_class": prediction.predicted_class,
        "probabilities": result["probabilities"],
        "model_version": prediction.model_version,
        "disclaimer": "Screening support only, not a diagnosis.",
    }

class ReviewIn(BaseModel):
    comment: str


@app.get("/doctor/assessments")
def doctor_list_assessments(
    db: Session = Depends(get_db),
    doctor: models.User = Depends(require_role("doctor", "admin")),
):
    items = db.query(models.Assessment).all()
    return [
        {
            "id": a.id,
            "patient_id": a.user_id,
            "patient_name": a.owner.name,
            "status": a.status,
            "created_at": a.created_at,
        }
        for a in items
    ]


@app.get("/doctor/assessments/{assessment_id}")
def doctor_assessment_detail(
    assessment_id: int,
    db: Session = Depends(get_db),
    doctor: models.User = Depends(require_role("doctor", "admin")),
):
    a = db.query(models.Assessment).filter(models.Assessment.id == assessment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assessment not found")

    images = db.query(models.ImageAsset).filter(models.ImageAsset.assessment_id == a.id).all()
    preds = db.query(models.Prediction).filter(models.Prediction.assessment_id == a.id).all()

    result = []
    for p in preds:
        reviews = (
            db.query(models.DoctorReview)
            .filter(models.DoctorReview.prediction_id == p.id)
            .all()
        )
        result.append(
            {
                "id": p.id,
                "predicted_class": p.predicted_class,
                "probabilities": json.loads(p.probabilities),
                "model_version": p.model_version,
                "reviews": [
                    {"doctor_id": r.doctor_id, "comment": r.comment, "created_at": r.created_at}
                    for r in reviews
                ],
            }
        )

    return {
        "id": a.id,
        "patient_name": a.owner.name,
        "status": a.status,
        "image_ids": [i.id for i in images],
        "predictions": result,
    }


@app.post("/doctor/predictions/{prediction_id}/review", status_code=201)
def add_review(
    prediction_id: int,
    body: ReviewIn,
    db: Session = Depends(get_db),
    doctor: models.User = Depends(require_role("doctor", "admin")),
):
    pred = db.query(models.Prediction).filter(models.Prediction.id == prediction_id).first()
    if not pred:
        raise HTTPException(status_code=404, detail="Prediction not found")

    review = models.DoctorReview(
        prediction_id=pred.id, doctor_id=doctor.id, comment=body.comment
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return {"id": review.id, "prediction_id": review.prediction_id, "comment": review.comment}

