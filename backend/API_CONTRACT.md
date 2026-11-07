# API Contract (Contract 2): Backend for Frontend

Project: Hybrid QML Platform for Fetal Health
Owner: Member 4 (Backend). Reader: Member 5 (Frontend).
Version: 1.2 (draft). Added patient history, expiring image links, admin activate/deactivate.

Base URL (local): `http://127.0.0.1:8000`
Live, testable docs (Swagger): `http://127.0.0.1:8000/docs`

---

## 1. General Rules

| Topic | Rule |
|---|---|
| Data format | JSON, except login (form) and image upload (multipart) |
| Auth | Send `Authorization: Bearer <access_token>` on every protected endpoint |
| Token expiry | 30 minutes. After that the backend returns `401`; the user must log in again |
| Roles | `patient`, `doctor`, `admin` (role is inside the token; a new token is needed if the role changes) |
| Error format | `{ "detail": "message" }` |
| Validation error | `422` with a `detail` list; each item has `loc` (which field) and `msg` |
| Rate limits | `POST /login`: 5 per minute. `POST /register`: 10 per minute. Over the limit gives `429` |
| CORS | Only addresses listed in the backend `ALLOWED_ORIGINS` setting can call the API |

### Status codes used

| Code | Meaning here |
|---|---|
| 200 / 201 | OK / created |
| 400 | Bad request (empty file, corrupt image, email already registered, no image uploaded yet) |
| 401 | Not logged in, wrong password, or token expired |
| 403 | Logged in, but role is not allowed (or the account is deactivated, at login) |
| 404 | Not found, or belongs to another patient (the backend does not reveal which) |
| 413 | Image larger than 10 MB |
| 415 | Image is not JPEG or PNG |
| 422 | Request body or field is invalid |
| 429 | Too many requests |
| 503 | AI service is down or too slow |

---

## 2. Endpoints at a Glance

| Method | URL | Who | Purpose |
|---|---|---|---|
| GET | `/health` | Anyone | Is the backend alive? |
| POST | `/register` | Anyone | Create a patient account |
| POST | `/login` | Anyone | Get an access token |
| GET | `/me` | Any logged-in user | Who am I? |
| POST | `/assessments` | Logged-in user | Start a new screening |
| GET | `/assessments` | Logged-in user | My screenings (own only), with latest result and image ids |
| GET | `/assessments/{id}` | Owner of the assessment | One of my screenings in detail (all predictions, probabilities, doctor comments) |
| POST | `/assessments/{id}/image` | Owner of the assessment | Upload an ultrasound image |
| POST | `/assessments/{id}/predict` | Owner of the assessment | Run the AI on the latest image |
| GET | `/images/{image_id}` | Owner, doctor, admin | Download an image (needs the Authorization header) |
| POST | `/images/{image_id}/link` | Owner, doctor, admin | Get a temporary image link (5 minutes) |
| GET | `/image-links/{token}` | Anyone with the link | Open the image from a temporary link (no header needed) |
| GET | `/doctor/assessments` | Doctor, admin | All patients' screenings |
| GET | `/doctor/assessments/{id}` | Doctor, admin | One screening in detail |
| POST | `/doctor/predictions/{prediction_id}/review` | Doctor, admin | Add a review comment |
| GET | `/admin/users` | Admin | List all users |
| PUT | `/admin/users/{user_id}/active` | Admin | Activate or deactivate a user |
| GET | `/admin/audit-logs` | Admin | Latest 100 audit entries |

---

## 3. Endpoint Details

### 3.1 Auth

#### POST `/register`
Creates a **patient** account. Doctor and admin accounts cannot be created here.

Request (JSON):
```json
{ "name": "Riya", "email": "riya@gmail.com", "password": "mypassword123" }
```
Rules: name 1 to 100 characters, valid email format, password 8 to 72 characters.

Response `201`:
```json
{ "message": "User registered successfully", "id": 1, "name": "Riya", "email": "riya@gmail.com", "role": "patient" }
```
Errors: `400` email already registered, `422` invalid field, `429` too many requests.

#### POST `/login`
**Important:** this is **form data**, not JSON, and the email goes in a field called `username`.

Request: `Content-Type: application/x-www-form-urlencoded`
```
username=riya@gmail.com&password=mypassword123
```
Response `200`:
```json
{ "access_token": "<long token>", "token_type": "bearer" }
```
Errors: `401` invalid email or password, `403` account is deactivated, `429` too many attempts.

#### GET `/me`  (auth)
Response `200`:
```json
{ "id": 1, "name": "Riya", "email": "riya@gmail.com", "role": "patient" }
```
Use this after login to know the role and decide which screens to show.

---

### 3.2 Patient flow (auth)

#### POST `/assessments`
No body. Response `201`:
```json
{ "id": 3, "status": "pending", "created_at": "2026-11-03T06:21:41.240998" }
```

#### GET `/assessments`
Only the logged-in user's own assessments. Use this for the history list. Response `200`:
```json
[
  {
    "id": 3,
    "status": "completed",
    "created_at": "2026-11-03T06:21:41.240998",
    "predicted_class": "Brain",
    "image_ids": [5]
  },
  {
    "id": 4,
    "status": "pending",
    "created_at": "2026-11-04T09:10:00.000000",
    "predicted_class": null,
    "image_ids": []
  }
]
```
`status` is `pending` until a prediction is run, then `completed`.
`predicted_class` is the latest prediction, or `null` if none yet.
`image_ids` is empty until an image is uploaded.

#### GET `/assessments/{id}`
One of the logged-in user's own assessments, in detail. Use this for the history detail screen. Response `200`:
```json
{
  "id": 3,
  "status": "completed",
  "created_at": "2026-11-03T06:21:41.240998",
  "image_ids": [5],
  "predictions": [
    {
      "id": 7,
      "predicted_class": "Brain",
      "probabilities": { "Brain": 0.82, "Abdomen": 0.05, "Femur": 0.03, "Thorax": 0.04, "Cervix": 0.02, "Other": 0.04 },
      "model_version": "mock-service-v1",
      "disclaimer": "Screening support only, not a diagnosis.",
      "reviews": [ { "comment": "Plane looks correct.", "created_at": "2026-11-05T10:00:00" } ]
    }
  ]
}
```
`reviews` holds the doctor comments (the doctor's id is not shown to patients).
Errors: `404` not found, or belongs to another patient.
Use each id in `image_ids` with `GET /images/{image_id}`.

#### POST `/assessments/{id}/image`
Request: `multipart/form-data` with one field named `file`.

Rules: JPEG or PNG only, maximum 10 MB, must be a real image. The backend strips metadata (EXIF) and stores the file privately.

Response `201`:
```json
{
  "id": 5,
  "assessment_id": 1,
  "size_bytes": 464293,
  "content_type": "image/jpeg",
  "sha256": "0f9d68ca..."
}
```
Errors: `400` empty or corrupt file, `404` assessment not found (or not yours), `413` too large, `415` wrong format.

Keep the returned `id`: it is the `image_id` for `GET /images/{image_id}`.

#### POST `/assessments/{id}/predict`
No body. Uses the latest image of that assessment. May take a few seconds (the backend retries the AI service up to 3 times).

Response `201`:
```json
{
  "id": 7,
  "assessment_id": 1,
  "predicted_class": "Brain",
  "probabilities": { "Brain": 0.82, "Abdomen": 0.05, "Femur": 0.03, "Thorax": 0.04, "Cervix": 0.02, "Other": 0.04 },
  "model_version": "mock-service-v1",
  "disclaimer": "Screening support only, not a diagnosis."
}
```
Errors: `400` no image uploaded yet, `404` assessment not found, `503` AI service unavailable.

Show the `disclaimer` and `model_version` in the UI.

#### GET `/images/{image_id}`  (auth)
Returns the image file (`image/jpeg` or `image/png`).
A patient can only get their own images. Doctor and admin can get any. Others get `404`.

**Note for frontend:** a plain `<img src="/images/5">` will not work here because this endpoint needs the `Authorization` header. Use the temporary link endpoint below instead (simplest), or fetch with the header and use `URL.createObjectURL(blob)`.

#### POST `/images/{image_id}/link`  (auth)
Creates a temporary link for one image. The same permission rules apply (a patient can only create links for their own images).

Response `200`:
```json
{ "url": "/image-links/eyJhbGciOi...", "expires_in_seconds": 300 }
```
Errors: `404` image not found (or not yours).

#### GET `/image-links/{token}`  (no auth header needed)
Open `BASE_URL + url` directly in `<img src>`. Works for 5 minutes, then returns `401 Link expired or invalid`. Ask for a new link when it expires.
Anyone who has the link can open the image until it expires, so do not share or store these links.

---

### 3.3 Doctor (auth, role `doctor` or `admin`)

#### GET `/doctor/assessments`
```json
[ { "id": 1, "patient_id": 2, "patient_name": "Aman", "status": "completed", "created_at": "2026-11-03T06:19:29.546498" } ]
```

#### GET `/doctor/assessments/{id}`
```json
{
  "id": 1,
  "patient_name": "Aman",
  "status": "completed",
  "image_ids": [5],
  "predictions": [
    {
      "id": 7,
      "predicted_class": "Brain",
      "probabilities": { "Brain": 0.82, "Abdomen": 0.05, "Femur": 0.03, "Thorax": 0.04, "Cervix": 0.02, "Other": 0.04 },
      "model_version": "mock-service-v1",
      "reviews": [ { "doctor_id": 4, "comment": "Plane looks correct.", "created_at": "2026-11-05T10:00:00" } ]
    }
  ]
}
```
Use each id in `image_ids` with `GET /images/{image_id}`. Error: `404` not found, `403` not a doctor.

#### POST `/doctor/predictions/{prediction_id}/review`
Request:
```json
{ "comment": "Plane looks correct, image quality is good." }
```
Response `201`:
```json
{ "id": 1, "prediction_id": 7, "comment": "Plane looks correct, image quality is good." }
```

---

### 3.4 Admin (auth, role `admin`)

#### GET `/admin/users`
```json
[ { "id": 1, "name": "Riya", "email": "riya@gmail.com", "role": "admin", "is_active": true } ]
```

#### PUT `/admin/users/{user_id}/active`
Request:
```json
{ "is_active": false }
```
Response `200`:
```json
{ "id": 3, "email": "sara@gmail.com", "is_active": false }
```
A deactivated user cannot log in, and their existing token stops working immediately.
Errors: `400` admin tried to change their own status, `404` user not found, `403` not an admin.

#### GET `/admin/audit-logs`
Latest 100 entries, newest first.
```json
[ { "id": 3, "user_id": 1, "action": "login_success", "detail": null, "created_at": "2026-11-06T18:42:16.480658" } ]
```
Actions recorded: `login_success`, `login_failed`, `login_blocked_inactive`, `image_uploaded`, `image_viewed`, `image_link_created`, `image_viewed_via_link`, `prediction_run`, `review_added`, `user_activated`, `user_deactivated`.

---

## 4. Not Available Yet (planned)

| Item | Status |
|---|---|
| Heatmap image (`heatmap_base64`) | Waiting for the real AI service (Member 3). The field is `null` in the mock |
| Sign in with Google (Firebase) | Parked, pending answers from Member 5 |
| Password change, forgot password | Not planned yet |

Any change to this contract will be announced before it is made.