from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from datetime import date
import os

# ---------------- APP ----------------
app = Flask(__name__)

# ---------------- PATHS / DBS ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DBS = {
    "LD": "data_LD.db",
    "DL": "data_DL.db",
}


def get_selected_business():
    """Lexon biznesin nga query param: ?b=LD ose ?b=DL (default LD)."""
    b = (request.args.get("b") or "LD").upper().strip()
    return b if b in DBS else "LD"


def normalize_business(b):
    b = (b or "LD").upper().strip()
    return b if b in DBS else "LD"


def get_conn(business="LD"):
    business = normalize_business(business)
    db_file = DBS.get(business, DBS["LD"])
    db_path = os.path.join(BASE_DIR, db_file)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Krijon tabelat në të DY databazat (LD dhe DL)."""
    for b in ["LD", "DL"]:
        with get_conn(b) as conn:
            cur = conn.cursor()

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sale_date TEXT NOT NULL,
                    client TEXT NOT NULL,
                    amount REAL NOT NULL
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    buy_date TEXT NOT NULL,
                    vendor TEXT NOT NULL,
                    amount REAL NOT NULL
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS orders_cash (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_date TEXT NOT NULL,
                    note TEXT,
                    amount REAL NOT NULL
                )
                """
            )

            conn.commit()


# E rëndësishme për Render/gunicorn: init_db duhet të ekzekutohet edhe kur file importohet.
init_db()

# ---------------- DASHBOARD ----------------
@app.route("/")
def home():
    b = get_selected_business()
    return redirect(url_for("dashboard", b=b))


@app.route("/dashboard")
def dashboard():
    b = get_selected_business()

    start = request.args.get("start", "").strip()
    end = request.args.get("end", "").strip()

    sales_where = []
    purch_where = []
    order_where = []
    params_sales = []
    params_purch = []
    params_order = []

    if start:
        sales_where.append("sale_date >= ?")
        params_sales.append(start)
        purch_where.append("buy_date >= ?")
        params_purch.append(start)
        order_where.append("order_date >= ?")
        params_order.append(start)

    if end:
        sales_where.append("sale_date <= ?")
        params_sales.append(end)
        purch_where.append("buy_date <= ?")
        params_purch.append(end)
        order_where.append("order_date <= ?")
        params_order.append(end)

    sales_where_sql = ("WHERE " + " AND ".join(sales_where)) if sales_where else ""
    purch_where_sql = ("WHERE " + " AND ".join(purch_where)) if purch_where else ""
    order_where_sql = ("WHERE " + " AND ".join(order_where)) if order_where else ""

    with get_conn(b) as conn:
        cur = conn.cursor()

        total_sales = cur.execute(
            f"SELECT COALESCE(SUM(amount),0) AS s FROM sales {sales_where_sql}",
            params_sales,
        ).fetchone()["s"]

        total_purchases = cur.execute(
            f"SELECT COALESCE(SUM(amount),0) AS p FROM purchases {purch_where_sql}",
            params_purch,
        ).fetchone()["p"]

        total_orders = cur.execute(
            f"SELECT COALESCE(SUM(amount),0) AS o FROM orders_cash {order_where_sql}",
            params_order,
        ).fetchone()["o"]

        sales_by_date = cur.execute(
            f"""SELECT sale_date AS d, COALESCE(SUM(amount),0) AS s
                FROM sales {sales_where_sql}
                GROUP BY sale_date
                ORDER BY sale_date""",
            params_sales,
        ).fetchall()

        purch_by_date = cur.execute(
            f"""SELECT buy_date AS d, COALESCE(SUM(amount),0) AS p
                FROM purchases {purch_where_sql}
                GROUP BY buy_date
                ORDER BY buy_date""",
            params_purch,
        ).fetchall()

    s_map = {r["d"]: float(r["s"]) for r in sales_by_date}
    p_map = {r["d"]: float(r["p"]) for r in purch_by_date}
    labels = sorted(set(list(s_map.keys()) + list(p_map.keys())))

    sales_series = [s_map.get(d, 0.0) for d in labels]
    purchases_series = [p_map.get(d, 0.0) for d in labels]
    profit_series = [sales_series[i] - purchases_series[i] for i in range(len(labels))]

    profit_total = float(total_sales) - float(total_purchases)

    return render_template(
        "dashboard.html",
        b=b,
        start=start,
        end=end,
        today=str(date.today()),
        total_sales=float(total_sales),
        total_purchases=float(total_purchases),
        total_orders=float(total_orders),
        profit=float(profit_total),
        labels=labels,
        sales_series=sales_series,
        purchases_series=purchases_series,
        profit_series=profit_series,
    )


# ---------------- SALES ----------------
@app.route("/sales", methods=["GET", "POST"])
def sales():
    b = get_selected_business()

    # POST: shto shitje
    if request.method == "POST":
        sale_date = (request.form.get("sale_date") or str(date.today())).strip()
        client = (request.form.get("client") or "").strip()
        amount = float(request.form.get("amount") or 0)

        with get_conn(b) as conn:
            conn.execute(
                "INSERT INTO sales (sale_date, client, amount) VALUES (?, ?, ?)",
                (sale_date, client, amount),
            )
            conn.commit()

        return redirect(url_for("sales", b=b))

    # GET: filtro (mbështet edhe parametrat e vjetër from/to)
    date_from = (request.args.get("nga") or request.args.get("from") or "").strip()
    date_to = (request.args.get("deri") or request.args.get("to") or "").strip()
    client_q = (request.args.get("client") or "").strip()

    where = []
    params = []

    if date_from:
        where.append("sale_date >= ?")
        params.append(date_from)

    if date_to:
        where.append("sale_date <= ?")
        params.append(date_to)

    if client_q:
        where.append("LOWER(client) LIKE ?")
        params.append(f"%{client_q.lower()}%")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with get_conn(b) as conn:
        rows = conn.execute(
            f"""SELECT id, sale_date, client, amount
                 FROM sales
                 {where_sql}
                 ORDER BY sale_date DESC, id DESC""",
            params,
        ).fetchall()

        total = conn.execute(
            f"SELECT COALESCE(SUM(amount), 0) FROM sales {where_sql}",
            params,
        ).fetchone()[0]

        clients = conn.execute(
            "SELECT DISTINCT client FROM sales WHERE client IS NOT NULL AND TRIM(client)<>'' ORDER BY client"
        ).fetchall()

    return render_template(
        "sales.html",
        b=b,
        rows=rows,
        total=float(total),
        nga=date_from,
        deri=date_to,
        client_filter=client_q,
        clients=[c["client"] for c in clients],
        today=str(date.today()),
    )


@app.route("/sales/edit/<int:id>", methods=["GET", "POST"])
def edit_sale(id):
    b = get_selected_business()

    with get_conn(b) as conn:
        cur = conn.cursor()

        if request.method == "POST":
            sale_date = request.form.get("sale_date") or str(date.today())
            client = request.form.get("client") or ""
            amount = float(request.form.get("amount") or 0)

            cur.execute(
                "UPDATE sales SET sale_date=?, client=?, amount=? WHERE id=?",
                (sale_date, client, amount, id),
            )
            conn.commit()
            return redirect(url_for("sales", b=b))

        row = cur.execute("SELECT * FROM sales WHERE id=?", (id,)).fetchone()

    if not row:
        return "Nuk u gjet kjo shitje!", 404

    return render_template("sales_edit.html", r=row, b=b)


@app.route("/sales/delete/<int:id>", methods=["POST"])
def delete_sale(id):
    b = normalize_business(request.form.get("b"))
    with get_conn(b) as conn:
        conn.execute("DELETE FROM sales WHERE id=?", (id,))
        conn.commit()
    return redirect(url_for("sales", b=b))


@app.route("/sales/delete_selected", methods=["POST"])
def delete_selected_sales():
    b = normalize_business(request.form.get("b"))
    ids = request.form.getlist("delete_ids")

    if ids:
        with get_conn(b) as conn:
            conn.executemany("DELETE FROM sales WHERE id=?", [(int(i),) for i in ids])
            conn.commit()

    return redirect(url_for("sales", b=b))


# ---------------- PURCHASES ----------------
@app.route("/purchases", methods=["GET", "POST"])
def purchases():
    b = get_selected_business()

    # POST: shto blerje
    if request.method == "POST":
        buy_date = request.form.get("buy_date") or str(date.today())
        vendor = (request.form.get("vendor") or "").strip()
        amount = float(request.form.get("amount") or 0)

        with get_conn(b) as conn:
            conn.execute(
                "INSERT INTO purchases (buy_date, vendor, amount) VALUES (?, ?, ?)",
                (buy_date, vendor, amount),
            )
            conn.commit()

        return redirect(url_for("purchases", b=b))

    # GET: filtro
    nga = (request.args.get("nga") or "").strip()
    deri = (request.args.get("deri") or "").strip()
    vendor_q = (request.args.get("vendor") or "").strip()

    where = []
    params = []

    if nga:
        where.append("buy_date >= ?")
        params.append(nga)
    if deri:
        where.append("buy_date <= ?")
        params.append(deri)
    if vendor_q:
        where.append("LOWER(vendor) LIKE ?")
        params.append(f"%{vendor_q.lower()}%")

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    with get_conn(b) as conn:
        cur = conn.cursor()

        rows = cur.execute(
            f"SELECT * FROM purchases{where_sql} ORDER BY buy_date DESC, id DESC",
            params,
        ).fetchall()

        total = cur.execute(
            f"SELECT COALESCE(SUM(amount),0) AS t FROM purchases{where_sql}",
            params,
        ).fetchone()["t"]

        vendors = cur.execute(
            "SELECT DISTINCT vendor FROM purchases ORDER BY vendor"
        ).fetchall()

    return render_template(
        "purchases.html",
        rows=rows,
        b=b,
        today=str(date.today()),
        total=float(total),
        nga=nga,
        deri=deri,
        vendor_filter=vendor_q,
        vendors=[v["vendor"] for v in vendors],
    )


@app.route("/purchases/delete/<int:id>", methods=["POST"])
def delete_purchase(id):
    b = normalize_business(request.form.get("b"))
    with get_conn(b) as conn:
        conn.execute("DELETE FROM purchases WHERE id=?", (id,))
        conn.commit()
    return redirect(url_for("purchases", b=b))


@app.route("/purchases/edit/<int:id>", methods=["GET", "POST"])
def edit_purchase(id):
    b = get_selected_business()

    with get_conn(b) as conn:
        cur = conn.cursor()

        if request.method == "POST":
            buy_date = request.form.get("buy_date") or str(date.today())
            vendor = (request.form.get("vendor") or "").strip()
            amount = float(request.form.get("amount") or 0)

            cur.execute(
                "UPDATE purchases SET buy_date=?, vendor=?, amount=? WHERE id=?",
                (buy_date, vendor, amount, id),
            )
            conn.commit()
            return redirect(url_for("purchases", b=b))

        row = cur.execute("SELECT * FROM purchases WHERE id=?", (id,)).fetchone()

    if not row:
        return "Nuk u gjet kjo blerje!", 404

    return render_template("edit_purchase.html", row=row, purchase=row, b=b, today=str(date.today()))


# ---------------- ORDERS CASH (Porosi-Kesh) ----------------
@app.route("/orders_cash", methods=["GET", "POST"])
def orders_cash():
    b = get_selected_business()

    with get_conn(b) as conn:
        cur = conn.cursor()

        if request.method == "POST":
            order_date = request.form.get("order_date") or str(date.today())
            note = request.form.get("note", "")
            amount = float(request.form.get("amount") or 0)

            cur.execute(
                "INSERT INTO orders_cash (order_date, note, amount) VALUES (?, ?, ?)",
                (order_date, note, amount),
            )
            conn.commit()
            return redirect(url_for("orders_cash", b=b))

        rows = cur.execute("SELECT * FROM orders_cash ORDER BY order_date DESC, id DESC").fetchall()
        total = cur.execute("SELECT COALESCE(SUM(amount),0) AS t FROM orders_cash").fetchone()["t"]

    return render_template(
        "orders_cash.html", rows=rows, b=b, today=str(date.today()), total=float(total)
    )


@app.route("/orders_cash/delete/<int:id>", methods=["POST"])
def delete_order_cash(id):
    b = normalize_business(request.form.get("b"))
    with get_conn(b) as conn:
        conn.execute("DELETE FROM orders_cash WHERE id=?", (id,))
        conn.commit()
    return redirect(url_for("orders_cash", b=b))


@app.route("/orders_cash/edit/<int:id>", methods=["GET", "POST"])
def edit_order_cash(id):
    b = get_selected_business()

    with get_conn(b) as conn:
        cur = conn.cursor()

        if request.method == "POST":
            order_date = request.form.get("order_date") or str(date.today())
            note = request.form.get("note", "")
            amount = float(request.form.get("amount") or 0)

            cur.execute(
                """
                UPDATE orders_cash
                SET order_date=?, note=?, amount=?
                WHERE id=?
                """,
                (order_date, note, amount, id),
            )
            conn.commit()
            return redirect(url_for("orders_cash", b=b))

        row = cur.execute("SELECT * FROM orders_cash WHERE id=?", (id,)).fetchone()

    return render_template("edit_order_cash.html", row=row, b=b)


# ---------------- LIBRA (Raporte me periudhe) ----------------
@app.route("/liber/bleje")
def liber_bleje():
    b = get_selected_business()
    start = request.args.get("start", "").strip()
    end = request.args.get("end", "").strip()

    where = []
    params = []
    if start:
        where.append("buy_date >= ?")
        params.append(start)
    if end:
        where.append("buy_date <= ?")
        params.append(end)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with get_conn(b) as conn:
        cur = conn.cursor()
        rows = cur.execute(
            f"SELECT buy_date, vendor, amount FROM purchases {where_sql} ORDER BY buy_date ASC, id ASC",
            params,
        ).fetchall()

        total = cur.execute(
            f"SELECT COALESCE(SUM(amount),0) AS t FROM purchases {where_sql}",
            params,
        ).fetchone()["t"]

        total_all = cur.execute("SELECT COALESCE(SUM(amount),0) AS t FROM purchases").fetchone()["t"]

    return render_template(
        "liber_bleje.html",
        b=b,
        start=start,
        end=end,
        rows=rows,
        total=float(total),
        total_all=float(total_all),
    )


@app.route("/liber/shitje")
def liber_shitje():
    b = get_selected_business()
    start = request.args.get("start", "").strip()
    end = request.args.get("end", "").strip()

    where = []
    params = []
    if start:
        where.append("sale_date >= ?")
        params.append(start)
    if end:
        where.append("sale_date <= ?")
        params.append(end)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with get_conn(b) as conn:
        cur = conn.cursor()
        rows = cur.execute(
            f"SELECT sale_date, client, amount FROM sales {where_sql} ORDER BY sale_date ASC, id ASC",
            params,
        ).fetchall()

        total = cur.execute(
            f"SELECT COALESCE(SUM(amount),0) AS t FROM sales {where_sql}",
            params,
        ).fetchone()["t"]

        total_all = cur.execute("SELECT COALESCE(SUM(amount),0) AS t FROM sales").fetchone()["t"]

    return render_template(
        "liber_shitje.html",
        b=b,
        start=start,
        end=end,
        rows=rows,
        total=float(total),
        total_all=float(total_all),
    )


@app.route("/liber/porosi")
def liber_porosi():
    # Raport për Porosi-Kesh (orders_cash)
    b = get_selected_business()
    start = request.args.get("start", "").strip()
    end = request.args.get("end", "").strip()

    where = []
    params = []
    if start:
        where.append("order_date >= ?")
        params.append(start)
    if end:
        where.append("order_date <= ?")
        params.append(end)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with get_conn(b) as conn:
        cur = conn.cursor()

        rows = cur.execute(
            f"SELECT order_date, note, amount FROM orders_cash {where_sql} ORDER BY order_date ASC, id ASC",
            params,
        ).fetchall()

        total = cur.execute(
            f"SELECT COALESCE(SUM(amount),0) AS t FROM orders_cash {where_sql}",
            params,
        ).fetchone()["t"]

        total_all = cur.execute(
            "SELECT COALESCE(SUM(amount),0) AS t FROM orders_cash"
        ).fetchone()["t"]

    return render_template(
        "liber_porosi.html",
        b=b,
        start=start,
        end=end,
        rows=rows,
        total=float(total),
        total_all=float(total_all),
    )


if __name__ == "__main__":
    # Lokal
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


