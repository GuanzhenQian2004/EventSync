import os
from flask import Flask, jsonify, Response, render_template, request, redirect, url_for, session, flash
import pymysql

app = Flask(__name__, template_folder="templates")

# Simple dev secret so session/flash works
app.secret_key = "dev"

def get_db_connection():
    """
    Local dev: connect to 127.0.0.1:3306 (via Cloud SQL Proxy)
    Cloud Run: connect via Unix socket /cloudsql/INSTANCE_CONNECTION_NAME
    """
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASS"]
    db = os.environ["DB_NAME"]

    instance = os.getenv("INSTANCE_CONNECTION_NAME")
    running_on_cloud_run = os.getenv("K_SERVICE") is not None

    if running_on_cloud_run and instance:
        # Cloud Run via Unix socket
        conn = pymysql.connect(
            user=user, password=password, database=db,
            unix_socket=f"/cloudsql/{instance}",
            charset="utf8mb4", cursorclass=pymysql.cursors.Cursor
        )
    else:
        # Local via proxy on localhost:3306
        host = os.getenv("DB_HOST", "127.0.0.1")
        port = int(os.getenv("DB_PORT", "3306"))
        conn = pymysql.connect(
            host=host, port=port, user=user, password=password, database=db,
            charset="utf8mb4", cursorclass=pymysql.cursors.Cursor
        )
    return conn

# ---------- Pages ----------

@app.get("/")
def home():
    # NEW: fetch event_name, org_name for homepage
    events = []
    err = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT event_name, org_name FROM event NATURAL JOIN host ORDER BY event_name")
            events = cur.fetchall()  # list of tuples: (event_name, org_name)
    except Exception as e:
        err = str(e)
    finally:
        try:
            conn.close()
        except:
            pass

    return render_template("home.html", events=events, err=err)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    # POST
    email = (request.form.get("user_email") or "").strip().lower()
    if not email:
        flash("Email is required.")
        return redirect(url_for("login"))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_email, name FROM users WHERE user_email=%s", (email,))
            row = cur.fetchone()
    finally:
        conn.close()

    if row:
        # NOTE: with Cursor (tuples), row[0]=user_email, row[1]=name
        session["user_email"] = row[0]
        session["name"] = row[1]
        flash("Logged in.")
        return redirect(url_for("profile"))
    else:
        flash("No account for that email. Please sign up.")
        return redirect(url_for("signup"))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")
    # POST
    email = (request.form.get("user_email") or "").strip().lower()
    name = (request.form.get("name") or "").strip()
    if not email or not name:
        flash("Email and name are required.")
        return redirect(url_for("signup"))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (user_email, name) VALUES (%s, %s)",
                 (email, name),
            )   
        conn.commit() # need conn.commit so the new user saves. 
        flash("Account created. You are now logged in.")
        session["user_email"] = email
        session["name"] = name
        return redirect(url_for("profile"))
    except pymysql.err.IntegrityError:
        conn.rollback() #keeps connnection clean after an error.
        flash("That email already exists. Try logging in.")
        return redirect(url_for("login"))
    finally:
        conn.close()

@app.get("/profile")
def profile():
    email = session.get("user_email")
    if not email:
        flash("Please log in.")
        return redirect(url_for("login"))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_email, name FROM users WHERE user_email=%s", (email,))
            row = cur.fetchone()
    finally:
        conn.close()

    # row is a tuple with (user_email, name) or None
    user = None
    if row:
        user = type("U", (), {"user_email": row[0], "name": row[1]})

    return render_template("profile.html", user=user)

@app.get("/logout")
def logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("home"))

# ---------- Existing debug endpoint ----------

@app.get("/table")
def tables():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema=%s ORDER BY table_name",
                (os.environ["DB_NAME"],)
            )
            rows = [t[0] for t in cur.fetchall()]
        conn.close()
        return jsonify({"schema": os.environ["DB_NAME"], "tables": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=True)
