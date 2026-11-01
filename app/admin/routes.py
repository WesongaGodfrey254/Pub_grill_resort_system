from functools import wraps
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import func
from ..extensions import db, socketio
from ..models import User, Category, Product, Order, OrderItem, Room, RoomBooking, RoomBlock, RestaurantTable, AuditLog, InventoryMovement, Notification, OrderStatusHistory

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
ORDER_STATES = {"pending", "accepted", "preparing", "ready", "served", "completed", "cancelled"}

def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator

def audit(action, entity_type=None, entity_id=None, details=None):
    db.session.add(AuditLog(user_id=current_user.id, action=action, entity_type=entity_type, entity_id=str(entity_id) if entity_id is not None else None, details=details))

@admin_bp.get("/dashboard")
@roles_required("admin", "supervisor")
def dashboard():
    today = datetime.utcnow().date()
    start = datetime.combine(today, datetime.min.time())
    orders_today = Order.query.filter(Order.created_at >= start, Order.status != "cancelled").all()
    sales = sum(o.total_cents for o in orders_today if o.status == "completed")
    return render_template("admin/dashboard.html",
        sales=sales, orders_today=len(orders_today),
        pending=Order.query.filter_by(status="pending").count(),
        customers=User.query.filter_by(role="customer").count(),
        employees=User.query.filter(User.role.notin_(["customer", "admin"])).count(),
        rooms=Room.query.count(),
        occupied=RoomBooking.query.filter(RoomBooking.status == "checked_in", RoomBooking.check_out_at > datetime.utcnow()).count(),
        available=sum(1 for r in Room.query.all() if room_available_now(r)),
        low_stock=Product.query.filter(Product.stock_quantity <= Product.reorder_level, Product.is_available.is_(True)).count(),
        recent_orders=Order.query.order_by(Order.created_at.desc()).limit(10).all(),
        recent_bookings=RoomBooking.query.order_by(RoomBooking.created_at.desc()).limit(8).all())

def room_available_now(room):
    now = datetime.utcnow()
    if room.status == "maintenance":
        return False
    booking = RoomBooking.query.filter(
        RoomBooking.room_id == room.id,
        RoomBooking.status.in_(["confirmed", "checked_in"]),
        RoomBooking.check_in_at < now,
        RoomBooking.check_out_at > now
    ).first()
    block = RoomBlock.query.filter_by(room_id=room.id, is_active=True).filter(
        RoomBlock.starts_at < now, RoomBlock.ends_at > now).first()
    return booking is None and block is None

@admin_bp.get("/operations")
@login_required
def operations():
    if current_user.role not in {"admin", "supervisor", "chef", "bartender", "waiter", "cashier", "receptionist", "storekeeper"}:
        abort(403)
    if current_user.role in {"admin", "supervisor"}:
        return redirect(url_for("admin.dashboard"))
    orders = Order.query.filter(Order.status.in_(["pending", "accepted", "preparing", "ready"])).order_by(Order.created_at.asc()).all()
    bookings = RoomBooking.query.filter(RoomBooking.status.in_(["confirmed", "checked_in"])).order_by(RoomBooking.check_in_at.asc()).limit(30).all()
    return render_template("admin/operations.html", orders=orders, bookings=bookings)

@admin_bp.route("/products", methods=["GET", "POST"])
@roles_required("admin")
def products():
    categories = Category.query.order_by(Category.name).all()
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            category_id = int(request.form.get("category_id", ""))
            price = int(round(float(request.form.get("price", "0")) * 100))
            stock = int(request.form.get("stock_quantity", "0"))
            reorder = int(request.form.get("reorder_level", "5"))
            category = db.session.get(Category, category_id)
            if not name or not category or price < 0 or stock < 0 or reorder < 0:
                raise ValueError()
            p = Product(category_id=category_id, name=name, description=request.form.get("description", "").strip(),
                        price_cents=price, cost_cents=0, stock_quantity=stock, reorder_level=reorder)
            db.session.add(p); db.session.flush()
            audit("product_created", "product", p.id, name)
            if stock:
                db.session.add(InventoryMovement(product_id=p.id, quantity_change=stock, reason="Initial stock", user_id=current_user.id))
            db.session.commit()
            flash("Product added.", "success")
            return redirect(url_for("admin.products"))
        except (ValueError, TypeError):
            db.session.rollback()
            flash("Check the product fields and enter valid non-negative numbers.", "danger")
    return render_template("admin/products.html", products=Product.query.order_by(Product.name).all(), categories=categories)

@admin_bp.post("/products/<int:product_id>/update")
@roles_required("admin")
def update_product(product_id):
    p = db.get_or_404(Product, product_id)
    try:
        p.name = request.form.get("name", p.name).strip()
        p.price_cents = int(round(float(request.form.get("price", p.price_cents / 100)) * 100))
        p.stock_quantity = int(request.form.get("stock_quantity", p.stock_quantity))
        p.is_available = request.form.get("is_available") == "on"
        if p.price_cents < 0 or p.stock_quantity < 0 or not p.name:
            raise ValueError()
        audit("product_updated", "product", p.id, p.name)
        db.session.commit()
        flash("Product updated.", "success")
    except (ValueError, TypeError):
        db.session.rollback(); flash("Invalid product values.", "danger")
    return redirect(url_for("admin.products"))

@admin_bp.route("/categories", methods=["GET", "POST"])
@roles_required("admin")
def categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name and not Category.query.filter(func.lower(Category.name) == name.lower()).first():
            db.session.add(Category(name=name, description=request.form.get("description", "").strip()))
            audit("category_created", "category", name)
            db.session.commit(); flash("Category added.", "success")
        else:
            flash("Enter a unique category name.", "danger")
        return redirect(url_for("admin.categories"))
    return render_template("admin/categories.html", categories=Category.query.order_by(Category.name).all())

@admin_bp.route("/employees", methods=["GET", "POST"])
@roles_required("admin")
def employees():
    allowed = {"supervisor", "cashier", "waiter", "chef", "bartender", "storekeeper", "receptionist"}
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", "")
        password = request.form.get("password", "")
        if not name or not email or role not in allowed or len(password) < 12 or User.query.filter_by(email=email).first():
            flash("Check fields: unique email, valid role and password of at least 12 characters.", "danger")
        else:
            user = User(full_name=name, email=email, role=role)
            user.set_password(password)
            db.session.add(user); db.session.flush()
            audit("employee_created", "user", user.id, role)
            db.session.commit(); flash("Employee account created.", "success")
            return redirect(url_for("admin.employees"))
    return render_template("admin/employees.html", employees=User.query.filter(User.role != "customer").order_by(User.full_name).all(), roles=sorted(allowed))

@admin_bp.post("/employees/<int:user_id>/toggle")
@roles_required("admin")
def toggle_employee(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id or user.role == "admin":
        flash("You cannot deactivate your own account or another administrator here.", "danger")
    else:
        user.is_active_account = not user.is_active_account
        audit("employee_status_changed", "user", user.id, str(user.is_active_account))
        db.session.commit(); flash("Employee status updated.", "success")
    return redirect(url_for("admin.employees"))

@admin_bp.get("/orders")
@login_required
def orders():
    if current_user.role not in {"admin", "supervisor", "cashier", "waiter", "chef", "bartender"}: abort(403)
    return render_template("admin/orders.html", orders=Order.query.order_by(Order.created_at.desc()).limit(200).all(), states=sorted(ORDER_STATES))

@admin_bp.post("/orders/<int:order_id>/status")
@login_required
def update_order_status(order_id):
    if current_user.role not in {"admin", "supervisor", "cashier", "waiter", "chef", "bartender"}: abort(403)
    order = db.get_or_404(Order, order_id)
    status = request.form.get("status", "")
    if status not in ORDER_STATES:
        abort(400)
    if order.status in {"completed", "cancelled"} and status != order.status:
        flash("Finalized orders cannot be reopened here.", "danger")
        return redirect(url_for("admin.orders"))
    previous_status = order.status
    if status == "cancelled" and previous_status != "cancelled":
        # Return stock when an order is cancelled; the reversal is auditable.
        for item in order.items:
            product = db.session.get(Product, item.product_id)
            if product:
                product.stock_quantity += item.quantity
                db.session.add(InventoryMovement(product_id=product.id, quantity_change=item.quantity,
                    reason=f"Stock returned for cancelled order {order.order_number}", user_id=current_user.id))
    order.status = status
    order.status_history.append(OrderStatusHistory(status=status, changed_by=current_user.id))
    audit("order_status_changed", "order", order.id, status)
    db.session.commit()
    socketio.emit("order_status_changed", {"order_id": order.id, "order_number": order.order_number, "status": status},
                  to=f"user:{order.customer_id}")
    socketio.emit("order_updated", {"order_id": order.id, "order_number": order.order_number, "status": status},
                  to="staff")
    flash("Order status updated.", "success")
    return redirect(request.referrer or url_for("admin.orders"))

@admin_bp.route("/rooms", methods=["GET", "POST"])
@roles_required("admin")
def rooms():
    if request.method == "POST":
        try:
            number = request.form.get("room_number", "").strip()
            room_type = request.form.get("room_type", "Standard").strip()
            hourly = int(round(float(request.form.get("hourly_rate", "0")) * 100))
            daily = int(round(float(request.form.get("daily_rate", "0")) * 100))
            weekly = int(round(float(request.form.get("weekly_rate", "0")) * 100))
            capacity = int(request.form.get("capacity", "2"))
            if not number or min(hourly, daily, weekly) < 0 or capacity < 1 or Room.query.filter_by(room_number=number).first():
                raise ValueError()
            room = Room(room_number=number, room_type=room_type, description=request.form.get("description", ""),
                        hourly_rate_cents=hourly, daily_rate_cents=daily, weekly_rate_cents=weekly, capacity=capacity)
            db.session.add(room); db.session.flush()
            audit("room_created", "room", room.id, number)
            db.session.commit(); flash("Room added.", "success")
        except (ValueError, TypeError):
            db.session.rollback(); flash("Check room number, unique room number, rates and capacity.", "danger")
        return redirect(url_for("admin.rooms"))
    rooms_list = Room.query.order_by(Room.room_number).all()
    from ..models import RoomBlock
    blocks = RoomBlock.query.order_by(RoomBlock.starts_at.desc()).limit(30).all()
    return render_template("admin/rooms.html", rooms=rooms_list, bookings=RoomBooking.query.order_by(RoomBooking.check_in_at.desc()).limit(100).all(), blocks=blocks)

@admin_bp.post("/rooms/<int:room_id>/status")
@roles_required("admin")
def room_status(room_id):
    room = db.get_or_404(Room, room_id)
    status = request.form.get("status")
    if status not in {"available", "maintenance"}:
        abort(400)
    room.status = status
    audit("room_status_changed", "room", room.id, status)
    db.session.commit()
    socketio.emit("room_availability_changed", {"room_id": room.id, "status": status})
    flash("Room status updated.", "success")
    return redirect(url_for("admin.rooms"))

@admin_bp.post("/rooms/<int:room_id>/block")
@roles_required("admin")
def block_room(room_id=None):
    from ..models import RoomBlock
    room_id = room_id or request.form.get("room_id", type=int)
    room = db.get_or_404(Room, room_id)
    try:
        start = datetime.fromisoformat(request.form.get("starts_at", ""))
        end = datetime.fromisoformat(request.form.get("ends_at", ""))
        reason = request.form.get("reason", "").strip()
        if end <= start or not reason:
            raise ValueError()
        db.session.add(RoomBlock(room_id=room.id, starts_at=start, ends_at=end, reason=reason))
        audit("room_block_created", "room", room.id, reason)
        db.session.commit(); flash("Room availability block created.", "success")
    except ValueError:
        db.session.rollback(); flash("Enter valid start/end times and a reason.", "danger")
    return redirect(url_for("admin.rooms"))

@admin_bp.get("/customers")
@roles_required("admin", "supervisor")
def customers():
    return render_template("admin/customers.html", customers=User.query.filter_by(role="customer").order_by(User.created_at.desc()).all())

@admin_bp.get("/reports")
@roles_required("admin", "supervisor")
def reports():
    orders = Order.query.filter(Order.status == "completed").order_by(Order.created_at.desc()).all()
    by_status = db.session.query(Order.status, func.count(Order.id)).group_by(Order.status).all()
    total = sum(o.total_cents for o in orders)
    return render_template("admin/reports.html", orders=orders, total=total, by_status=by_status)
