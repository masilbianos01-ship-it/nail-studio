from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import datetime
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-me"

DB_PATH = os.path.join(os.path.dirname(__file__), "salon.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            allergies TEXT,
            notes TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            visit_date TEXT NOT NULL,
            service TEXT NOT NULL,
            color_design TEXT,
            price REAL,
            notes TEXT,
            FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE
        );
        """
    )
    conn.commit()
    conn.close()


# ---------- Αρχική / Λίστα πελατών ----------

@app.route("/")
def index():
    query = request.args.get("q", "").strip()
    conn = get_db()
    if query:
        clients = conn.execute(
            """SELECT * FROM clients
               WHERE full_name LIKE ? OR phone LIKE ? OR email LIKE ?
               ORDER BY full_name COLLATE NOCASE""",
            (f"%{query}%", f"%{query}%", f"%{query}%"),
        ).fetchall()
    else:
        clients = conn.execute(
            "SELECT * FROM clients ORDER BY full_name COLLATE NOCASE"
        ).fetchall()

    # Τελευταία επίσκεψη ανά πελάτη για γρήγορη προβολή στη λίστα
    clients_with_last_visit = []
    for c in clients:
        last_visit = conn.execute(
            "SELECT visit_date, service FROM visits WHERE client_id = ? ORDER BY visit_date DESC LIMIT 1",
            (c["id"],),
        ).fetchone()
        clients_with_last_visit.append({"client": c, "last_visit": last_visit})

    conn.close()
    return render_template(
        "index.html", clients=clients_with_last_visit, query=query
    )


# ---------- Προσθήκη πελάτη ----------

@app.route("/clients/new", methods=["GET", "POST"])
def new_client():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        if not full_name:
            flash("Το ονοματεπώνυμο είναι υποχρεωτικό.", "error")
            return render_template("client_form.html", client=request.form)

        conn = get_db()
        conn.execute(
            """INSERT INTO clients (full_name, phone, email, allergies, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                full_name,
                request.form.get("phone", "").strip(),
                request.form.get("email", "").strip(),
                request.form.get("allergies", "").strip(),
                request.form.get("notes", "").strip(),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        conn.close()
        flash(f"Ο/Η πελάτης {full_name} προστέθηκε.", "success")
        return redirect(url_for("index"))

    return render_template("client_form.html", client=None)


# ---------- Επεξεργασία πελάτη ----------

@app.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
def edit_client(client_id):
    conn = get_db()
    client = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if client is None:
        conn.close()
        flash("Ο πελάτης δεν βρέθηκε.", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        if not full_name:
            flash("Το ονοματεπώνυμο είναι υποχρεωτικό.", "error")
            conn.close()
            return render_template("client_form.html", client=client)

        conn.execute(
            """UPDATE clients SET full_name=?, phone=?, email=?, allergies=?, notes=?
               WHERE id=?""",
            (
                full_name,
                request.form.get("phone", "").strip(),
                request.form.get("email", "").strip(),
                request.form.get("allergies", "").strip(),
                request.form.get("notes", "").strip(),
                client_id,
            ),
        )
        conn.commit()
        conn.close()
        flash("Τα στοιχεία ενημερώθηκαν.", "success")
        return redirect(url_for("client_detail", client_id=client_id))

    conn.close()
    return render_template("client_form.html", client=client)


# ---------- Διαγραφή πελάτη ----------

@app.route("/clients/<int:client_id>/delete", methods=["POST"])
def delete_client(client_id):
    conn = get_db()
    conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    conn.commit()
    conn.close()
    flash("Ο πελάτης διαγράφηκε.", "success")
    return redirect(url_for("index"))


# ---------- Προφίλ πελάτη + ιστορικό επισκέψεων ----------

@app.route("/clients/<int:client_id>")
def client_detail(client_id):
    conn = get_db()
    client = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if client is None:
        conn.close()
        flash("Ο πελάτης δεν βρέθηκε.", "error")
        return redirect(url_for("index"))

    visits = conn.execute(
        "SELECT * FROM visits WHERE client_id = ? ORDER BY visit_date DESC",
        (client_id,),
    ).fetchall()
    conn.close()
    return render_template("client_detail.html", client=client, visits=visits)


# ---------- Προσθήκη επίσκεψης ----------

@app.route("/clients/<int:client_id>/visits/new", methods=["GET", "POST"])
def new_visit(client_id):
    conn = get_db()
    client = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if client is None:
        conn.close()
        flash("Ο πελάτης δεν βρέθηκε.", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        visit_date = request.form.get("visit_date", "").strip()
        service = request.form.get("service", "").strip()
        if not visit_date or not service:
            flash("Ημερομηνία και υπηρεσία είναι υποχρεωτικά.", "error")
            conn.close()
            return render_template("visit_form.html", client=client, visit=None)

        price_raw = request.form.get("price", "").strip()
        price = float(price_raw) if price_raw else None

        conn.execute(
            """INSERT INTO visits (client_id, visit_date, service, color_design, price, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                client_id,
                visit_date,
                service,
                request.form.get("color_design", "").strip(),
                price,
                request.form.get("notes", "").strip(),
            ),
        )
        conn.commit()
        conn.close()
        flash("Η επίσκεψη καταχωρήθηκε.", "success")
        return redirect(url_for("client_detail", client_id=client_id))

    conn.close()
    return render_template("visit_form.html", client=client, visit=None)


# ---------- Επεξεργασία επίσκεψης ----------

@app.route("/visits/<int:visit_id>/edit", methods=["GET", "POST"])
def edit_visit(visit_id):
    conn = get_db()
    visit = conn.execute("SELECT * FROM visits WHERE id = ?", (visit_id,)).fetchone()
    if visit is None:
        conn.close()
        flash("Η επίσκεψη δεν βρέθηκε.", "error")
        return redirect(url_for("index"))

    client = conn.execute(
        "SELECT * FROM clients WHERE id = ?", (visit["client_id"],)
    ).fetchone()

    if request.method == "POST":
        visit_date = request.form.get("visit_date", "").strip()
        service = request.form.get("service", "").strip()
        if not visit_date or not service:
            flash("Ημερομηνία και υπηρεσία είναι υποχρεωτικά.", "error")
            conn.close()
            return render_template("visit_form.html", client=client, visit=visit)

        price_raw = request.form.get("price", "").strip()
        price = float(price_raw) if price_raw else None

        conn.execute(
            """UPDATE visits SET visit_date=?, service=?, color_design=?, price=?, notes=?
               WHERE id=?""",
            (
                visit_date,
                service,
                request.form.get("color_design", "").strip(),
                price,
                request.form.get("notes", "").strip(),
                visit_id,
            ),
        )
        conn.commit()
        conn.close()
        flash("Η επίσκεψη ενημερώθηκε.", "success")
        return redirect(url_for("client_detail", client_id=client["id"]))

    conn.close()
    return render_template("visit_form.html", client=client, visit=visit)


# ---------- Διαγραφή επίσκεψης ----------

@app.route("/visits/<int:visit_id>/delete", methods=["POST"])
def delete_visit(visit_id):
    conn = get_db()
    visit = conn.execute("SELECT client_id FROM visits WHERE id = ?", (visit_id,)).fetchone()
    client_id = visit["client_id"] if visit else None
    conn.execute("DELETE FROM visits WHERE id = ?", (visit_id,))
    conn.commit()
    conn.close()
    flash("Η επίσκεψη διαγράφηκε.", "success")
    if client_id:
        return redirect(url_for("client_detail", client_id=client_id))
    return redirect(url_for("index"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
