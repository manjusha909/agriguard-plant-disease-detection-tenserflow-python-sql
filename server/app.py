from flask import Flask, render_template, request, redirect, session, url_for
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing import image
from werkzeug.utils import secure_filename
import numpy as np
import json
import os
import mysql.connector

app = Flask(__name__)
app.secret_key = "manjusha_secret"

# ------------------------------ DATABASE ------------------------------
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="123456",
    database="agriguard"
)
cursor = db.cursor()

# ------------------------------ MODEL ------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "../model/plant_model.h5")
CLASS_JSON_PATH = os.path.join(BASE_DIR, "../model/class_indices.json")

model = load_model(MODEL_PATH)
with open(CLASS_JSON_PATH, "r") as f:
    class_indices = json.load(f)
    class_indices = {v: k for k, v in class_indices.items()}

def predict_disease(img_path, threshold=0.80):
    img = image.load_img(img_path, target_size=(128, 128))
    img_array = np.array(img) / 255.0
    img_array = np.expand_dims(img_array, axis=0)
    prediction = model.predict(img_array)
    max_prob = np.max(prediction)

    if max_prob < threshold:
        return "Not a leaf image"

    predicted_index = np.argmax(prediction)
    return class_indices[predicted_index]

# ------------------------------ REGISTER ------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"].strip()

        cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
        if cursor.fetchone():
            error = "Email already registered"
        else:
            cursor.execute(
                "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                (name, email, password)
            )
            db.commit()
            return redirect("/login")

    return render_template("register.html", error=error)

# ------------------------------ LOGIN ------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"].strip()

        # User login
        cursor.execute("SELECT id, password FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        if user and user[1].strip() == password:
            session["user_id"] = user[0]
            return redirect("/")

        # Admin login
        cursor.execute("SELECT id, password FROM admin WHERE email=%s", (email,))
        admin = cursor.fetchone()
        if admin and admin[1].strip() == password:
            session["admin_id"] = admin[0]
            return redirect("/admin/dashboard")

        error = "Invalid email or password"

    return render_template("login.html", error=error)

# ------------------------------ HOME / PREDICTION ------------------------------
@app.route("/", methods=["GET", "POST"])
def home():
    if "user_id" not in session:
        return redirect("/login")

    prediction = None
    image_path = None

    if request.method == "POST":
        file = request.files["image"]
        if file:
            upload_folder = os.path.join(BASE_DIR, "static/uploads/")
            os.makedirs(upload_folder, exist_ok=True)

            filename = secure_filename(file.filename)
            img_path = os.path.join(upload_folder, filename)
            file.save(img_path)

            prediction = predict_disease(img_path)
            image_path = os.path.relpath(img_path, BASE_DIR).replace("\\", "/")

            cursor.execute(
                "INSERT INTO predictions (user_id, image_path, result) VALUES (%s, %s, %s)",
                (session["user_id"], image_path, prediction)
            )
            db.commit()

    return render_template("index.html", prediction=prediction, image_path=image_path)

# ------------------------------ LOGOUT ------------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ------------------------------ ADMIN DASHBOARD ------------------------------
@app.route("/admin/dashboard")
def admin_dashboard():
    if "admin_id" not in session:
        return redirect("/login")

    # Users
    cursor.execute("SELECT id, username, email FROM users")
    users = cursor.fetchall()

    # Predictions
    cursor.execute("""
        SELECT predictions.id, users.username, predictions.image_path, predictions.result
        FROM predictions
        JOIN users ON predictions.user_id = users.id
    """)
    predictions = cursor.fetchall()

    return render_template("admin_dashboard.html", users=users, predictions=predictions)

# ------------------------------ ADMIN DELETE ------------------------------
@app.route("/admin/delete_user/<int:user_id>")
def delete_user(user_id):
    if "admin_id" not in session:
        return redirect("/login")
    cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
    db.commit()
    return redirect("/admin/dashboard")

@app.route("/admin/delete_prediction/<int:pred_id>")
def delete_prediction(pred_id):
    if "admin_id" not in session:
        return redirect("/login")
    cursor.execute("DELETE FROM predictions WHERE id=%s", (pred_id,))
    db.commit()
    return redirect("/admin/dashboard")

# ------------------------------ ADMIN LOGOUT ------------------------------
@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_id", None)
    return redirect("/login")

if __name__ == "__main__":
    app.run(debug=True)
