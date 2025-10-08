from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "canteen_secret_key"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "canteen.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ---------------- Models ----------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="user")  # 'user' or 'admin'

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, nullable=False)
    available = db.Column(db.Boolean, default=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    pickup_time = db.Column(db.String(30), nullable=False)   # "12:30 PM"
    status = db.Column(db.String(30), default="Pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ------------- DB init and sample data -------------
def init_db():
    db.create_all()
    # create default admin if missing
    admin = User.query.filter_by(role="admin").first()
    if not admin:
        admin_user = User(
            username="canteen_admin",
            password_hash=generate_password_hash("admin123"),
            role="admin"
        )
        db.session.add(admin_user)
    # sample menu items if none exist
    if MenuItem.query.count() == 0:
        sample = [
            ("Chicken Biryani", 120.0, True),
            ("Veg Biryani", 100.0, True),
            ("Samosa", 15.0, True),
            ("Egg Manchuria", 80.0, True),
            ("Chicken Manchuria", 100.0, True),
            ("Idli", 30.0, True),
            ("Dosa", 40.0, True),
            ("Poori", 35.0, True)
        ]
        for n, p, av in sample:
            db.session.add(MenuItem(name=n, price=p, available=av))
    db.session.commit()

# ------------- Helpers -------------
def is_logged_in():
    return 'username' in session

def is_admin():
    return session.get('role') == 'admin'

# ------------- Routes -------------
@app.route('/')
def root():
    if is_logged_in():
        if is_admin():
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))

# ---------- Auth ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        uname = request.form['username'].strip()
        pwd = request.form['password']
        if not uname or not pwd:
            flash("Please provide valid username and password", "danger")
            return redirect(url_for('register'))
        if User.query.filter_by(username=uname).first():
            flash("Username already exists", "danger")
            return redirect(url_for('register'))
        user = User(username=uname, password_hash=generate_password_hash(pwd), role='user')
        db.session.add(user)
        db.session.commit()
        flash("Registered! Please login.", "success")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        uname = request.form['username'].strip()
        pwd = request.form['password']
        # admin shortcut: there is an admin user in DB, but we check DB normally
        user = User.query.filter_by(username=uname).first()
        if user and check_password_hash(user.password_hash, pwd):
            session['username'] = user.username
            session['role'] = user.role
            flash("Login successful", "success")
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('student_dashboard'))
        flash("Invalid credentials", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ---------- Student ----------
@app.route('/student/dashboard')
def student_dashboard():
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    return render_template('student_dashboard.html')

@app.route('/menu')
def menu():
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    items = MenuItem.query.order_by(MenuItem.name).all()
    return render_template('menu.html', items=items)

@app.route('/order/<int:item_id>', methods=['GET', 'POST'])
def order_form(item_id):
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    item = MenuItem.query.get_or_404(item_id)
    if request.method == 'POST':
        time_val = request.form.get('order_time', '').strip()
        ampm = request.form.get('order_ampm', '').strip()
        if not time_val or ampm not in ['AM', 'PM']:
            flash("Please enter valid time and AM/PM", "danger")
            return redirect(url_for('order_form', item_id=item_id))
        pickup = f"{time_val} {ampm}"
        new_order = Order(
            username=session['username'],
            item_name=item.name,
            total_price=item.price,
            pickup_time=pickup,
            status="Pending"
        )
        db.session.add(new_order)
        db.session.commit()
        return redirect(url_for('order_receipt', order_id=new_order.id))
    return render_template('order.html', item=item)

@app.route('/order/receipt/<int:order_id>')
def order_receipt(order_id):
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    order = Order.query.get_or_404(order_id)
    # only allow owner or the user who placed
    if not is_admin() and order.username != session['username']:
        flash("Not authorized", "danger")
        return redirect(url_for('student_dashboard'))
    return render_template('order_receipt.html', order=order)

# ---------- Admin ----------
@app.route('/admin/dashboard')
def admin_dashboard():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    return render_template('admin_dashboard.html')

@app.route('/admin/menu', methods=['GET', 'POST'])
def admin_menu():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        price = request.form.get('price', '').strip()
        if not name or not price:
            flash("Provide name and price", "danger")
            return redirect(url_for('admin_menu'))
        try:
            price_val = float(price)
        except:
            flash("Price must be a number", "danger")
            return redirect(url_for('admin_menu'))
        item = MenuItem(name=name, price=price_val, available=True)
        db.session.add(item)
        db.session.commit()
        flash("Item added", "success")
        return redirect(url_for('admin_menu'))
    items = MenuItem.query.order_by(MenuItem.name).all()
    return render_template('admin_menu.html', items=items)

@app.route('/admin/menu/toggle/<int:item_id>')
def admin_toggle_menu(item_id):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    it = MenuItem.query.get_or_404(item_id)
    it.available = not it.available
    db.session.commit()
    return redirect(url_for('admin_menu'))

@app.route('/admin/orders', methods=['GET', 'POST'])
def admin_orders():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    if request.method == 'POST':
        oid = request.form.get('order_id')
        new_status = request.form.get('status')
        if oid and new_status:
            o = Order.query.get(int(oid))
            if o:
                o.status = new_status
                db.session.commit()
                flash("Order status updated", "success")
        return redirect(url_for('admin_orders'))
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template('admin_orders.html', orders=orders)

# ---------- JSON APIs for polling ----------
@app.route('/api/orders')  # user-specific
def api_orders():
    if not is_logged_in() or is_admin():
        return jsonify({"error": "Not authorized"}), 403
    orders = Order.query.filter_by(username=session['username']).order_by(Order.created_at.desc()).all()
    out = []
    for o in orders:
        out.append({
            "id": o.id,
            "item_name": o.item_name,
            "total_price": o.total_price,
            "pickup_time": o.pickup_time,
            "status": o.status,
            "created_at": o.created_at.isoformat()
        })
    return jsonify(out)

@app.route('/api/admin/orders')  # admin view
def api_admin_orders():
    if not is_logged_in() or not is_admin():
        return jsonify({"error": "Not authorized"}), 403
    orders = Order.query.order_by(Order.created_at.desc()).all()
    out = []
    for o in orders:
        out.append({
            "id": o.id,
            "username": o.username,
            "item_name": o.item_name,
            "total_price": o.total_price,
            "pickup_time": o.pickup_time,
            "status": o.status,
            "created_at": o.created_at.isoformat()
        })
    return jsonify(out)

# ---------- Utility: create DB and run ----------
if __name__ == '__main__':
    with app.app_context():
        init_db()
    
    # Get port from environment variable (required by Render)
    port = int(os.environ.get("PORT", 5000))
    
    # Bind to 0.0.0.0 for Render
    app.run(host="0.0.0.0", port=port)


