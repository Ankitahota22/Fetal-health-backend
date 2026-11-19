# FetalScan Assist: Hybrid Quantum Machine Learning Platform for Fetal Ultrasound Screening Support

A web application that lets patients upload a fetal ultrasound image and receive an AI-assisted category result, and lets doctors review the images, results and heatmaps and record whether they agree.

> **This is a research prototype and screening-support tool. It does not diagnose and does not assess the health of a pregnancy.** The categories are experimental, data-derived groups and are not clinical thresholds. Use anonymised or public dataset images only.

## What is in this repository

| Folder | Content | Owner |
|---|---|---|
| [`backend/`](backend/) | FastAPI application backend: authentication, roles, secure image upload and storage, assessments, predictions, doctor reviews, admin tools, audit log, tests | Member 4 |
| [`ai-service/`](ai-service/) | Hybrid classical-quantum model service (PyTorch and PennyLane) with `/predict`, `/health`, `/model-info` and optional saliency heatmap | Member 3 |
| [`mock_ai_service/`](mock_ai_service/) | Small fake AI service with the same response shape, used for development | Member 4 |

The React frontend (Member 5) is developed separately. It talks only to the backend, using the API described in [`backend/API_CONTRACT.md`](backend/API_CONTRACT.md).

## How the parts fit together

```
Frontend (React)  -->  Backend (FastAPI)  -->  AI service (HybridNet)
                         |        |
                    SQLite DB   Private image storage
```

1. A patient creates an assessment and uploads an ultrasound image (JPEG or PNG, up to 10 MB).
2. The backend validates the image, removes its metadata, stores it privately and records a hash.
3. The backend sends the image to the AI service (10-second timeout, up to 3 attempts; 30 seconds when a heatmap is requested) and saves the result.
4. The patient sees the category, class scores, model version and an optional heatmap. A doctor can review the result.

## The model

The AI service classifies fetal head ultrasound images into three experimental head-circumference categories, **Small, Medium and Large**, using a hybrid network: a classical branch (51 features) combined with a 4-qubit quantum circuit simulated with PennyLane. The heatmap is a gradient-based saliency map. It shows input sensitivity and is not proof of a finding. The quantum circuit runs on a simulator; no quantum advantage is claimed.

## Backend highlights

- 23 REST endpoints with automatic Swagger documentation at `/docs`
- Passwords hashed with bcrypt; JWT access tokens (30 minutes)
- Three roles (patient, doctor, admin) with ownership checks on patient data
- Images: format and content checks, size limit, metadata removal, random file names, SHA-256 hash, private storage, 5-minute signed links for images and heatmaps
- Audit log, rate limiting on login and registration, input validation, CORS
- Alembic migrations; 33 automated tests (pytest) using a temporary database and a fake AI service

Details: [`backend/README.md`](backend/README.md), [`backend/API_CONTRACT.md`](backend/API_CONTRACT.md) and [`backend/SECURITY_NOTES.md`](backend/SECURITY_NOTES.md).

## Quick start

You need Python 3.12 and Git. The backend and the AI service use **separate virtual environments** (the AI service needs torch and PennyLane).

**Backend (port 8000)**

```
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env         # then put a real SECRET_KEY in .env
alembic upgrade head
uvicorn main:app --reload
```

Open http://127.0.0.1:8000/docs

**AI service (port 8001)**

```
cd ai-service
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn api:app --port 8001
```
Open http://127.0.0.1:8001/docs

It can take up to two minutes to start while the model loads. For quick development without the real model, run `mock_ai_service` instead (see `backend/README.md`).

**Tests**

```
cd backend
pip install pytest
pytest -v
```

## Current status and limitations

- The backend and the AI service were connected and checked manually on a local machine. The automated backend tests use a fake AI service.
- The complete frontend to backend to AI workflow, the heatmap display in the frontend and the combined docker-compose setup are still to be tested.
- Dockerfiles are written but not yet verified together. PostgreSQL, HTTPS and encryption at rest are planned for deployment, not implemented.
- The hybrid model has not yet been evaluated on a held-out test set, and its scores are not clinically calibrated probabilities. It does not check whether an uploaded image is really an ultrasound.
- Pixel size is not known for user uploads, so the model uses the training median. Categories are therefore approximate.
- Sign in with Google (Firebase) is planned, not implemented.

## Team

| Name | Role |
|---|---|
| Nutan Choudhury | Member 1: data engineering and classical ML |
| Anaya Mund | Member 2: quantum computing and QML |
| Ashreeta Das | Member 3: hybrid AI and model serving |
| Ankita Hota | Member 4: application backend and security |
| Prerana Mishra | Member 5: frontend, UX and DevOps |

Mentor: Dr. Dillip Ranjan Nayak

## Data credit

The model was trained on the HC18 fetal head ultrasound dataset (CC BY 4.0). Please credit the dataset authors as listed on the application's Dataset credits page.