import os
from flask import Flask, jsonify, Response, render_template, request, redirect, url_for, session, flash
from functools import wraps
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


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user_email"):
            flash("Please log in.")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper

@app.route("/events/new", methods=["GET", "POST"])
@login_required
def create_events():
    #load organizations and venues for the form w dropdowns
    organizations, venues, load_err = [], [], None
    try: 
        conn = get_db_connection()
        with conn.cursor() as cur: 
            cur.execute("SELECT org_name FROM organization ORDER BY org_name")
            orgs = [row[0] for row in cur.fetchall()]
            cur.execute("""
                SELECT v.vid, CONCAT(v.street, ', ', v.city, ' ', z.state, ' ', v.zip) AS vlabel
                FROM venue v
                JOIN zip_codes z ON z.zip = v.zip
                ORDER BY v.city, v.street
            """)
            venues = cur.fetchall() #list[(vid,label)]
    except Exception as e: 
            load_err = str(e)
    finally: 
            try: conn.close()
            except: pass
        
    if request.method == "GET":
            return render_template("event_new.html", organizations=orgs, venues=venues, err=load_err)
        
    # POST: validate inputs
    event_name = (request.form.get("event_name") or "").strip()
    org_name = (request.form.get("org_name") or "").strip()
    vid = request.form.get("vid")
    room_number = request.form.get("room_number") or None
    date_str = (request.form.get("date") or "").strip()
    start_str = (request.form.get("start_time") or "").strip()
    end_str = (request.form.get("end_time") or "").strip()
    price_str = (request.form.get("price") or "0").strip()
    description = (request.form.get("description") or "").strip()

    # Basic required fields
    if not (event_name and org_name and vid and date_str and start_str and end_str):
        flash("Please fill all required fields.")
        return redirect(url_for("create_event"))

  # Price check 
    try:
        price = float(price_str)
        if price < 0:
            raise ValueError()
    except ValueError:
        flash("Price must be a non-negative number.")
        return redirect(url_for("create_event"))

    #Insert event, then host, link to organization
    conn.get_db_connection()
    try: 
        with conn.cursor() as cur: 
        #Comfirm foreign keys exist
            cur.execute("SELECT 1 FROM venue WHERE vid=%s", (vid,))
            if not cur.fetchone():
                flash("Selected venue does not exist.")
                conn.close()
                return redirect(url_for("create_event"))

            cur.execute("SELECT 1 FROM organization WHERE org_name=%s", (org_name,))
            if not cur.fetchone():
                flash("Selected organization does not exist.")
                conn.close()
                return redirect(url_for("create_event"))

        # Insert into event (AUTO_INCREMENT path)
            cur.execute("""
            INSERT INTO event (vid, room_number, date, start_time, end_time, description, price, event_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, 
            (vid, room_number, date, start_time, end_time, description, price, event_name)
            )
            eid = cur.lastrowid  

            # Link event to org in host
            cur.execute("INSERT INTO host (eid, org_name) VALUES (%s, %s)", (eid, org_name))

        conn.commit()
        flash("Event created!")
        return redirect(url_for("home"))
    except Exception as e:
        conn.rollback()
        flash(f"Could not create event: {e}")
        return redirect(url_for("create_event"))
    finally:
        conn.close()

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
