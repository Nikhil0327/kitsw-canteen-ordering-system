from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import json, random, string
from datetime import datetime, date, time, timedelta

app = Flask(__name__)
app.secret_key = "canteen_secret_key_final"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///canteen.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ---------------- Models ----------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="user")  # "user" or "owner"

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(80), nullable=True)
    available = db.Column(db.Boolean, default=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    items_json = db.Column(db.String(2000), nullable=False)  # JSON array of {id,name,qty,price}
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="Pending")
    token = db.Column(db.String(12), nullable=False)
    payment_method = db.Column(db.String(30), nullable=False)
    payment_status = db.Column(db.String(30), default="Not Paid")
    pickup_time = db.Column(db.String(20), nullable=True)   # e.g. "12:45 PM"
    pickup_dt = db.Column(db.String(50), nullable=True)     # ISO datetime string (for sorting)
    created_at = db.Column(db.String(50), default=lambda: datetime.utcnow().isoformat())

# ---------------- Helpers ----------------
def generate_token(k=6):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=k))

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'username' not in session:
            flash("Please login to continue", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

def parse_time_am_pm(hm_str, ampm):
    """hm_str: 'HH:MM' (24-hour style from input), but user input will be 12-hour pick; ampm either 'AM' or 'PM'"""
    # hm_str is 'HH:MM' e.g. '12:30'
    hh, mm = [int(x) for x in hm_str.split(":")]
    if ampm.upper() == "PM" and hh != 12:
        hh = (hh % 12) + 12
    if ampm.upper() == "AM" and hh == 12:
        hh = 0
    return time(hour=hh, minute=mm)

# ---------------- Initialize DB & default owner & sample menu ----------------
with app.app_context():
    db.create_all()

    # Ensure exactly one owner exists (fixed owner)
    owner = User.query.filter_by(role="owner").first()
    if not owner:
        owner = User(username="canteen_admin", password_hash=generate_password_hash("admin123"), role="owner")
        db.session.add(owner)
        db.session.commit()
    else:
        # Remove any extra owners if present (enforce single owner)
        others = User.query.filter(User.role == "owner", User.id != owner.id).all()
        for o in others:
            db.session.delete(o)
        db.session.commit()

    # Add sample items if none
    if MenuItem.query.count() == 0:
        samples = [
            MenuItem(name="Veg Biryani", price=60, category="Main"),
            MenuItem(name="Chicken Biryani", price=90, category="Main"),
            MenuItem(name="Egg Manchuria", price=50, category="Snacks"),
            MenuItem(name="Chicken Manchuria", price=70, category="Snacks"),
            MenuItem(name="Samosa", price=15, category="Snacks"),
            MenuItem(name="Idli", price=25, category="Tiffins"),
            MenuItem(name="Dosa", price=30, category="Tiffins"),
            MenuItem(name="Upma", price=20, category="Tiffins"),
        ]
        db.session.bulk_save_objects(samples)
        db.session.commit()

# ---------------- Routes: Auth ----------------
@app.route("/")
def index():
    # Landing suggests login first
    return render_template("index.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username")
        pw = request.form.get("password")
        user = User.query.filter_by(username=u).first()
        if user and check_password_hash(user.password_hash, pw):
            session['username'] = user.username
            session['role'] = user.role
            flash("Logged in successfully", "success")
            if user.role == "owner":
                return redirect(url_for("owner_dashboard"))
            return redirect(url_for("menu"))
        flash("Invalid credentials", "danger")
    return render_template("login.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        u = request.form.get("username").strip()
        pw = request.form.get("password")
        if not u or not pw:
            flash("Enter username & password", "danger")
            return render_template("register.html")

        # Prevent registering reserved owner username
        if u == "canteen_admin":
            flash("This username is reserved", "danger")
            return render_template("register.html")

        if User.query.filter_by(username=u).first():
            flash("Username already exists", "danger")
            return render_template("register.html")

        new_user = User(username=u, password_hash=generate_password_hash(pw), role="user")
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful. Please login.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("index"))

# ---------------- Menu & Cart (login required) ----------------
@app.route("/menu")
@login_required
def menu():
    items = MenuItem.query.order_by(MenuItem.category, MenuItem.name).all()
    return render_template("menu.html", items=items)

@app.route("/add_to_cart", methods=["POST"])
@login_required
def add_to_cart():
    item_id = request.form.get("item_id")
    qty = int(request.form.get("quantity", 1))
    item = MenuItem.query.get(item_id)
    if not item or not item.available:
        flash("Item not available", "danger")
        return redirect(url_for("menu"))
    cart = session.get("cart", {})
    key = str(item_id)
    cart[key] = cart.get(key, 0) + qty
    session['cart'] = cart
    flash(f"Added {qty} × {item.name} to cart", "success")
    return redirect(url_for("menu"))

@app.route("/cart")
@login_required
def cart_view():
    cart = session.get("cart", {})
    items = []
    total = 0.0
    for key, qty in cart.items():
        it = MenuItem.query.get(int(key))
        if it:
            subtotal = round(it.price * qty, 2)
            items.append({"id": it.id, "name": it.name, "qty": qty, "price": it.price, "subtotal": subtotal})
            total += subtotal
    return render_template("cart.html", items=items, total=round(total,2))

@app.route("/cart/remove/<int:item_id>")
@login_required
def cart_remove(item_id):
    cart = session.get("cart", {})
    key = str(item_id)
    if key in cart:
        cart.pop(key)
    session['cart'] = cart
    flash("Removed from cart", "info")
    return redirect(url_for("cart_view"))

# ---------------- Checkout & Dummy Payment (pickup time selection implemented) ----------------
@app.route("/checkout", methods=["GET","POST"])
@login_required
def checkout():
    cart = session.get("cart", {})
    if not cart:
        flash("Cart empty", "danger")
        return redirect(url_for("menu"))

    items = []
    total = 0.0
    for k, qty in cart.items():
        it = MenuItem.query.get(int(k))
        if it:
            items.append({"id": it.id, "name": it.name, "qty": qty, "price": it.price})
            total += it.price * qty
    total = round(total,2)

    if request.method == "POST":
        payment_method = request.form.get("payment_method", "Cash")
        # pickup time inputs
        order_time = request.form.get("order_time")   # "HH:MM" from <input type="time"> but we'll use 12-hour input on UI
        order_ampm = request.form.get("order_ampm")   # "AM" or "PM"
        # to keep consistent, in our UI we'll send e.g. "12:30" and "PM"
        # build pickup_dt (ISO)
        try:
            if order_time and order_ampm:
                picked_time = parse_time_am_pm(order_time, order_ampm)  # returns time object
                today = date.today()
                pickup_dt = datetime.combine(today, picked_time)
                now = datetime.now()
                # if pickup time already passed today, schedule for next day
                if pickup_dt < now:
                    pickup_dt = pickup_dt + timedelta(days=1)
                pickup_time_str = f"{picked_time.strftime('%I:%M')} {order_ampm.upper()}"
                pickup_dt_iso = pickup_dt.isoformat()
            else:
                pickup_time_str = None
                pickup_dt_iso = None
        except Exception:
            pickup_time_str = None
            pickup_dt_iso = None

        username = session.get("username")
        if payment_method == "Online":
            # create pending payment session that holds items, total and pickup info
            session['pending_payment'] = {
                "username": username,
                "payment_method": "Online",
                "items": items,
                "total": total,
                "pickup_time_str": pickup_time_str,
                "pickup_dt_iso": pickup_dt_iso
            }
            return redirect(url_for("dummy_payment"))
        # Cash: create order directly
        token = generate_token(6)
        order = Order(username=username,
                      items_json=json.dumps(items),
                      total_price=total,
                      status="Pending",
                      token=token,
                      payment_method="Cash",
                      payment_status="Not Paid",
                      pickup_time=pickup_time_str,
                      pickup_dt=pickup_dt_iso)
        db.session.add(order)
        db.session.commit()
        session.pop("cart", None)
        flash("Order placed (Cash). Token generated.", "success")
        return redirect(url_for("order_confirmation", order_id=order.id))

    # GET
    return render_template("checkout.html", items=items, total=total)

@app.route("/payment/dummy", methods=["GET","POST"])
@login_required
def dummy_payment():
    pending = session.get("pending_payment")
    if not pending:
        flash("No pending payment", "danger")
        return redirect(url_for("menu"))

    items = pending.get("items", [])
    total = pending.get("total", 0.0)
    pickup_time_str = pending.get("pickup_time_str")
    pickup_dt_iso = pending.get("pickup_dt_iso")

    if request.method == "POST":
        username = session.get("username")
        token = generate_token(6)
        order = Order(username=username,
                      items_json=json.dumps(items),
                      total_price=total,
                      status="Pending",
                      token=token,
                      payment_method="Online",
                      payment_status="Paid",
                      pickup_time=pickup_time_str,
                      pickup_dt=pickup_dt_iso)
        db.session.add(order)
        db.session.commit()
        session.pop("cart", None)
        session.pop("pending_payment", None)
        flash("Payment completed (simulated) and order placed", "success")
        return redirect(url_for("order_confirmation", order_id=order.id))

    # dummy upi & qr
    dummy_upi = "canteen@upi"
    dummy_qr = f"upi://pay?pa={dummy_upi}&pn=CampusCanteen&am={total}"
    return render_template("dummy_payment.html", items=items, total=total, upi_id=dummy_upi, upi_qr=dummy_qr, pickup_time=pickup_time_str)

@app.route("/order/confirmation/<int:order_id>")
@login_required
def order_confirmation(order_id):
    o = Order.query.get_or_404(order_id)
    try:
        items = json.loads(o.items_json)
    except Exception:
        items = []
    return render_template("order_confirmation.html", order=o, items=items)

# ---------------- User Orders ----------------
@app.route("/user/orders")
@login_required
def user_orders_page():
    username = session.get("username")
    orders = Order.query.filter_by(username=username).order_by(Order.id.desc()).all()
    parsed = []
    for o in orders:
        try:
            items = json.loads(o.items_json)
        except Exception:
            items = []
        parsed.append({
            "id": o.id,
            "token": o.token,
            "items_list": items,
            "total_price": o.total_price,
            "status": o.status,
            "payment_method": o.payment_method,
            "payment_status": o.payment_status,
            "pickup_time": o.pickup_time,
            "pickup_dt": o.pickup_dt,
            "created_at": o.created_at
        })
    return render_template("user_orders.html", orders=parsed)

@app.route("/user/order/received/<int:order_id>", methods=["POST"])
@login_required
def user_mark_received(order_id):
    username = session.get("username")
    o = Order.query.get(order_id)
    if not o or o.username != username:
        flash("Order not found or not yours", "danger")
        return redirect(url_for("user_orders_page"))
    if o.status != "Ready":
        flash("Order not ready yet", "danger")
        return redirect(url_for("user_orders_page"))
    db.session.delete(o)
    db.session.commit()
    flash("Order received and removed", "success")
    return redirect(url_for("user_orders_page"))

# ---------------- Owner routes (only one owner in DB) ----------------
@app.route("/owner/dashboard")
@login_required
def owner_dashboard():
    if session.get("role") != "owner":
        flash("Owner access required", "danger")
        return redirect(url_for("login"))
    statuses = ["Pending","Preparing","Ready","Completed","Received"]
    counts = {s: Order.query.filter_by(status=s).count() for s in ["Pending","Preparing","Ready","Completed"]}
    total = Order.query.count()
    return render_template("owner_dashboard.html", counts=counts, total=total)

@app.route("/owner/menu", methods=["GET","POST"])
@login_required
def owner_menu():
    if session.get("role") != "owner":
        flash("Owner access required", "danger")
        return redirect(url_for("login"))
    if request.method == "POST":
        name = request.form.get("name")
        try:
            price = float(request.form.get("price") or 0)
        except:
            price = 0.0
        category = request.form.get("category") or "General"
        item = MenuItem(name=name, price=price, category=category)
        db.session.add(item)
        db.session.commit()
        flash("Menu item added", "success")
        return redirect(url_for("owner_menu"))
    items = MenuItem.query.order_by(MenuItem.category, MenuItem.name).all()
    return render_template("owner_menu.html", items=items)

@app.route("/owner/menu/toggle/<int:item_id>")
@login_required
def owner_toggle(item_id):
    if session.get("role") != "owner":
        flash("Owner access required", "danger")
        return redirect(url_for("login"))
    it = MenuItem.query.get_or_404(item_id)
    it.available = not it.available
    db.session.commit()
    flash("Toggled availability", "info")
    return redirect(url_for("owner_menu"))

@app.route("/owner/orders", methods=["GET","POST"])
@login_required
def owner_orders():
    if session.get("role") != "owner":
        flash("Owner access required", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        order_id = int(request.form.get("order_id"))
        action = request.form.get("action")
        if action == "update":
            new_status = request.form.get("status")
            o = Order.query.get(order_id)
            if o:
                o.status = new_status
                db.session.commit()
                flash(f"Order #{order_id} set to {new_status}", "success")
        elif action == "received":
            o = Order.query.get(order_id)
            if o:
                db.session.delete(o)
                db.session.commit()
                flash(f"Order #{order_id} marked Received and removed", "success")
        elif action == "delete":
            o = Order.query.get(order_id)
            if o:
                db.session.delete(o)
                db.session.commit()
                flash(f"Order #{order_id} deleted", "info")
        return redirect(url_for("owner_orders", status=request.args.get("status","")))

    status_filter = request.args.get("status", None)
    if status_filter:
        orders_q = Order.query.filter_by(status=status_filter).order_by(Order.id.desc()).all()
    else:
        orders_q = Order.query.order_by(Order.id.desc()).all()

    parsed = []
    for o in orders_q:
        try:
            items = json.loads(o.items_json)
        except Exception:
            items = []
        parsed.append({
            "id": o.id,
            "username": o.username,
            "token": o.token,
            "items_list": items,
            "total_price": o.total_price,
            "status": o.status,
            "payment_method": o.payment_method,
            "payment_status": o.payment_status,
            "pickup_time": o.pickup_time,
            "pickup_dt": o.pickup_dt,
            "created_at": o.created_at
        })

    # Sort by pickup_dt (nearest first) when pickup_dt available; fallback to created_at desc
    def sort_key(o):
        try:
            if o.get("pickup_dt"):
                return datetime.fromisoformat(o["pickup_dt"])
        except Exception:
            pass
        # fallback: put later created_at later
        try:
            return datetime.fromisoformat(o["created_at"])
        except:
            return datetime.max

    parsed_sorted = sorted(parsed, key=sort_key)
    return render_template("owner_orders.html", orders=parsed_sorted, status_filter=status_filter)

import os

if __name__ == "__main__":
    # Get port from Render or default to 5000 locally
    port = int(os.environ.get("PORT", 5000))
    
    # Run Flask app accessible externally
    app.run(host="0.0.0.0", port=port)


