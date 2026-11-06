from fastapi import FastAPI, UploadFile, File, HTTPException

app = FastAPI(title="Mock AI Service")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict")
def predict(file: UploadFile = File(...)):
    data = file.file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty image")

    # Yeh nakli result hai. Real service mein yahan model chalega.
    return {
        "predicted_class": "Brain",
        "probabilities": {
            "Brain": 0.82,
            "Abdomen": 0.05,
            "Femur": 0.03,
            "Thorax": 0.04,
            "Cervix": 0.02,
            "Other": 0.04,
        },
        "model_version": "mock-service-v1",
        "heatmap_base64": None,
    }