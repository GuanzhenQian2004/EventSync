import os
from flask import Flask, jsonify, Response
import pymysql

app = Flask(__name__)

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
        # Use the Cloud SQL connector socket on Cloud Run
        # host is a Unix socket path; no port
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

@app.get("/")
def home():
    return Response("Hello from Cloud Run + MySQL! (Fixed text)", mimetype="text/plain")

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
