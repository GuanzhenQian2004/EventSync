import os
import re
from flask import Flask, jsonify, Response, render_template, request, redirect, url_for, session, flash
from functools import wraps
import pymysql
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, template_folder="templates")

# Simple dev secret so session/flash works
app.secret_key = "dev"

# Simple email regex (not perfect, but good enough for most cases)
EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email or ""))


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
    # fetch eid, event_name, org_name for homepage
    events = []
    err = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT e.eid, e.event_name, h.org_name
                FROM event e
                JOIN host h ON h.eid = e.eid
                ORDER BY e.event_name
            """)
            events = cur.fetchall()  # list of tuples: (eid, event_name, org_name)
    except Exception as e:
        err = str(e)
    finally:
        try:
            conn.close()
        except:
            pass

    return render_template("home.html", events=events, err=err)


@app.get("/events/<int:eid>")
def event_detail(eid):
    conn = get_db_connection()
    event = None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    e.eid,
                    e.event_name,
                    e.date,
                    e.start_time,
                    e.end_time,
                    e.description,
                    e.price,
                    e.room_number,
                    v.street,
                    v.city,
                    v.zip,
                    z.state,
                    o.org_name,
                    e.created_by,
                    u.name AS creator_name
                FROM event e
                JOIN host h ON h.eid = e.eid
                JOIN organization o ON o.org_name = h.org_name
                JOIN venue v ON v.vid = e.vid
                JOIN zip_codes z ON z.zip = v.zip
                LEFT JOIN users u ON u.user_email = e.created_by
                WHERE e.eid = %s
            """, (eid,))
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        flash("Event not found.")
        return redirect(url_for("home"))

    # unpack row into a dict for easier use in the template
    event = {
        "eid": row[0],
        "event_name": row[1],
        "date": row[2],
        "start_time": row[3],
        "end_time": row[4],
        "description": row[5],
        "price": row[6],
        "room_number": row[7],
        "street": row[8],
        "city": row[9],
        "zip": row[10],
        "state": row[11],
        "org_name": row[12],
        "created_by": row[13],
        "creator_name": row[14],
    }

    return render_template("event_detail.html", event=event)



@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    # POST
    email = (request.form.get("user_email") or "").strip().lower()
    password = (request.form.get("password") or "").strip()

    if not email or not password:
        flash("Email and password are required.")
        return redirect(url_for("login"))

    if not is_valid_email(email):
        flash("Please enter a valid email address.")
        return redirect(url_for("login"))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Fetch stored password hash
            cur.execute(
                "SELECT user_email, name, password_hash FROM users WHERE user_email=%s",
                (email,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    # row: (user_email, name, password_hash)
    if not row or not check_password_hash(row[2], password):
        # Don't reveal which one was wrong
        flash("Invalid email or password.")
        return redirect(url_for("login"))

    session["user_email"] = row[0]
    session["name"] = row[1]
    flash("Logged in.")
    return redirect(url_for("profile"))


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
    # load organizations and venues for the form w dropdowns
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
            venues = cur.fetchall()  # list[(vid,label)]
    except Exception as e: 
        load_err = str(e)
    finally: 
        try:
            conn.close()
        except:
            pass
        
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

    # who is creating this event
    created_by = session.get("user_email")  # login_required should guarantee this

    # Basic required fields
    if not (event_name and org_name and vid and date_str and start_str and end_str):
        flash("Please fill all required fields.")
        return redirect(url_for("create_events"))

    # Price check 
    try:
        price = float(price_str)
        if price < 0:
            raise ValueError()
    except ValueError:
        flash("Price must be a non-negative number.")
        return redirect(url_for("create_events"))

    # Insert event, then host, link to organization
    conn = get_db_connection()
    try: 
        with conn.cursor() as cur: 
            # Confirm foreign keys exist
            cur.execute("SELECT 1 FROM venue WHERE vid=%s", (vid,))
            if not cur.fetchone():
                flash("Selected venue does not exist.")
                conn.close()
                return redirect(url_for("create_events"))

            cur.execute("SELECT 1 FROM organization WHERE org_name=%s", (org_name,))
            if not cur.fetchone():
                flash("Selected organization does not exist.")
                conn.close()
                return redirect(url_for("create_events"))

            # 🔹 Insert into event with created_by
            cur.execute("""
                INSERT INTO event (
                    vid, room_number, date, start_time, end_time,
                    description, price, event_name, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, 
            (vid, room_number, date_str, start_str, end_str,
             description, price, event_name, created_by)
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
        return redirect(url_for("create_events"))
    finally:
        conn.close()

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")

    # POST
    email = (request.form.get("user_email") or "").strip().lower()
    name = (request.form.get("name") or "").strip()
    password = (request.form.get("password") or "").strip()

    if not email or not name or not password:
        flash("Email, name, and password are required.")
        return redirect(url_for("signup"))

    if not is_valid_email(email):
        flash("Please enter a valid email address.")
        return redirect(url_for("signup"))

    # Optional: basic password length check
    if len(password) < 8:
        flash("Password must be at least 8 characters long.")
        return redirect(url_for("signup"))

    pwd_hash = generate_password_hash(password)

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (user_email, name, password_hash) VALUES (%s, %s, %s)",
                 (email, name, pwd_hash),
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
@login_required
def profile():
    email = session.get("user_email")
    if not email:
        flash("Please log in.")
        return redirect(url_for("login"))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Fetch user info
            cur.execute(
                "SELECT user_email, name FROM users WHERE user_email=%s",
                (email,),
            )
            row = cur.fetchone()

            # Fetch events created by this user
            cur.execute("""
                SELECT
                    e.eid,
                    e.event_name,
                    e.date,
                    e.start_time,
                    o.org_name
                FROM event e
                JOIN host h ON h.eid = e.eid
                JOIN organization o ON o.org_name = h.org_name
                WHERE e.created_by = %s
                ORDER BY e.date, e.start_time, e.event_name
            """, (email,))
            events_created = cur.fetchall()  # list of (eid, event_name, date, start_time, org_name)
    finally:
        conn.close()

    user = None
    if row:
        user = type("U", (), {"user_email": row[0], "name": row[1]})

    return render_template("profile.html", user=user, events_created=events_created)

@app.post("/events/<int:eid>/delete")
@login_required
def delete_event(eid):
    email = session.get("user_email")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Check the event exists and is owned by this user
            cur.execute("SELECT created_by FROM event WHERE eid=%s", (eid,))
            row = cur.fetchone()

            if not row:
                flash("Event not found.")
                return redirect(url_for("profile"))

            if row[0] != email:
                flash("You are not allowed to delete this event.")
                return redirect(url_for("profile"))

            # First delete from host, then from event (if FK is not ON DELETE CASCADE)
            cur.execute("DELETE FROM host WHERE eid=%s", (eid,))
            cur.execute("DELETE FROM event WHERE eid=%s", (eid,))

        conn.commit()
        flash("Event deleted.")
    except Exception as e:
        conn.rollback()
        flash(f"Could not delete event: {e}")
    finally:
        conn.close()

    return redirect(url_for("profile"))



@app.get("/logout")
def logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=True)
