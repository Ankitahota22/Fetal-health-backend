from database import SessionLocal
import models

EMAIL = "riya@gmail.com"  # jis user ko admin banana hai

db = SessionLocal()
user = db.query(models.User).filter(models.User.email == EMAIL).first()

if user:
    user.role = "admin"
    db.commit()
    print(f"{user.email} is now admin")
else:
    print("User not found")

db.close()