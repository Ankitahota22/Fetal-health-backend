from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


@app.get("/")
def home():
    return {"message": "Hello, backend is running!"}


@app.get("/health")
def health():
    return {"status": "ok"}

class UserRegister(BaseModel):
    name: str
    email: str
    password: str


@app.post("/register")
def register(user: UserRegister):
    return {
        "message": "User registered successfully",
        "name": user.name,
        "email": user.email,
    }