from functools import wraps
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from ..extensions import db, emit_event
from ..models import User, Category, Product, Order, OrderItem, Room, RoomBooking, RoomBlock, RestaurantTable, AuditLog, InventoryMovement, Notification, OrderStatusHistory, BusinessProfile
from ..uploads import save_image, delete_image, ImageUploadError

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
ORDER_STATES = {"pending", "accepted", "preparing", "ready", "served", "completed", "cancelled"}
# A served order is a completed sale even before the status is changed to completed.
SALES_STATUSES = ("served", "completed")

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

def report_snapshot():
    """Return live sales totals and served-product aggregates.

    Served orders count as sales immediately so the dashboard and reports
    update as soon as service marks an order as served.
    """
    status_filter = Order.status.in_(SALES_STATUSES)
    total_cents, order_count = db.session.query(
        func.coalesce(func.sum(Order.total_cents), 0),
        func.count(Order.id),
    ).filter(status_filter).one()
    items_served, items_value_cents = db.session.query(
        func.coalesce(func.sum(OrderItem.quantity), 0),
        func.coalesce(func.sum(OrderItem.line_total_cents), 0),
    ).join(Order).filter(status_filter).one()
    product_rows = db.session.query(
        OrderItem.product_name_snapshot,
        func.sum(OrderItem.quantity),
        func.sum(OrderItem.line_total_cents),
    ).join(Order).filter(status_filter).group_by(OrderItem.product_name_snapshot).order_by(
        func.sum(OrderItem.line_total_cents).desc(), OrderItem.product_name_snapshot.asc()
    ).all()
    by_status = db.session.query(Order.status, func.count(Order.id)).group_by(Order.status).order_by(Order.status).all()

    today_start = datetime.combine(datetime.utcnow().date(), datetime.min.time())
    today_total_cents, today_order_count = db.session.query(
        func.coalesce(func.sum(Order.total_cents), 0),
        func.count(Order.id),
    ).filter(status_filter, Order.created_at >= today_start).one()
    today_items_served = db.session.query(
        func.coalesce(func.sum(OrderItem.quantity), 0)
    ).join(Order).filter(status_filter, Order.created_at >= today_start).scalar()

    return {
        "total_cents": int(total_cents),
        "order_count": int(order_count),
        "items_served": int(items_served),
        "items_value_cents": int(items_value_cents),
        "products": [
            {"name": name, "quantity": int(quantity), "total_cents": int(value)}
            for name, quantity, value in product_rows
        ],
        "by_status": [(status, int(count)) for status, count in by_status],
        "today": {
            "total_cents": int(today_total_cents),
            "order_count": int(today_order_count),
            "items_served": int(today_items_served),
        },
    }

@admin_bp.get("/dashboard")
@roles_required("admin", "supervisor")
def dashboard():
    today = datetime.utcnow().date()
    start = datetime.combine(today, datetime.min.time())
    orders_today = Order.query.filter(Order.created_at >= start, Order.status != "cancelled").all()
    sales = sum(o.total_cents for o in orders_today if o.status in SALES_STATUSES)
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
        image_path = None
        try:
            name = request.form.get("name", "").strip()
            category_id = int(request.form.get("category_id", ""))
            price = int(round(float(request.form.get("price", "0")) * 100))
            stock = int(request.form.get("stock_quantity", "0"))
            reorder = int(request.form.get("reorder_level", "5"))
            category = db.session.get(Category, category_id)
            if not name or not category or price < 0 or stock < 0 or reorder < 0:
                raise ValueError()
            image_path = save_image(request.files.get("image"), "products")
            p = Product(category_id=category_id, name=name, description=request.form.get("description", "").strip(),
                        price_cents=price, cost_cents=0, stock_quantity=stock, reorder_level=reorder,
                        image_path=image_path)
            db.session.add(p); db.session.flush()
            audit("product_created", "product", p.id, name)
            if stock:
                db.session.add(InventoryMovement(product_id=p.id, quantity_change=stock, reason="Initial stock", user_id=current_user.id))
            db.session.commit()
            flash("Product added.", "success")
            return redirect(url_for("admin.products"))
        except ImageUploadError as exc:
            db.session.rollback()
            delete_image(image_path)
            flash(str(exc), "danger")
        except (ValueError, TypeError):
            db.session.rollback()
            delete_image(image_path)
            flash("Check the product fields and enter valid non-negative numbers.", "danger")
    return render_template("admin/products.html", products=Product.query.order_by(Product.name).all(), categories=categories)

@admin_bp.post("/products/<int:product_id>/update")
@roles_required("admin")
def update_product(product_id):
    p = db.get_or_404(Product, product_id)
    new_image = None
    old_image = p.image_path
    try:
        p.name = request.form.get("name", p.name).strip()
        p.price_cents = int(round(float(request.form.get("price", p.price_cents / 100)) * 100))
        p.stock_quantity = int(request.form.get("stock_quantity", p.stock_quantity))
        p.is_available = request.form.get("is_available") == "on"
        if p.price_cents < 0 or p.stock_quantity < 0 or not p.name:
            raise ValueError()
        new_image = save_image(request.files.get("image"), "products")
        if new_image:
            p.image_path = new_image
        audit("product_updated", "product", p.id, p.name)
        db.session.commit()
        if new_image:
            delete_image(old_image)
            db.session.commit()
        flash("Product updated.", "success")
    except ImageUploadError as exc:
        db.session.rollback()
        delete_image(new_image)
        flash(str(exc), "danger")
    except (ValueError, TypeError):
        db.session.rollback()
        delete_image(new_image)
        flash("Invalid product values.", "danger")
    return redirect(url_for("admin.products"))

@admin_bp.route("/business-profile", methods=["GET", "POST"])
@roles_required("admin")
def business_profile():
    profile = db.session.get(BusinessProfile, 1)
    if profile is None:
        profile = BusinessProfile(id=1, name=current_app.config["BUSINESS_NAME"])
        db.session.add(profile)
        db.session.commit()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        remove_logo = request.form.get("remove_logo") == "on"
        new_logo = None
        old_logo = profile.logo_path
        try:
            if not name:
                raise ValueError("Enter the business name.")
            if len(name) > 120:
                raise ValueError("Business name must be 120 characters or fewer.")
            new_logo = save_image(request.files.get("logo"), "business")
            profile.name = name
            if new_logo:
                profile.logo_path = new_logo
            elif remove_logo:
                profile.logo_path = None
            audit("business_profile_updated", "business_profile", profile.id, name)
            db.session.commit()
            if new_logo or remove_logo:
                delete_image(old_logo)
                db.session.commit()
            flash("Business profile updated.", "success")
            return redirect(url_for("admin.business_profile"))
        except ImageUploadError as exc:
            db.session.rollback()
            delete_image(new_logo)
            flash(str(exc), "danger")
        except ValueError as exc:
            db.session.rollback()
            delete_image(new_logo)
            flash(str(exc), "danger")
    return render_template("admin/business_profile.html", profile=profile)

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
    emit_event("order_status_changed", {"order_id": order.id, "order_number": order.order_number, "status": status},
                  to=f"user:{order.customer_id}")
    emit_event("order_updated", {"order_id": order.id, "order_number": order.order_number, "status": status},
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
    emit_event("room_availability_changed", {"room_id": room.id, "status": status})
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
    snapshot = report_snapshot()
    orders = Order.query.filter(Order.status.in_(SALES_STATUSES)).order_by(Order.created_at.desc()).limit(100).all()
    return render_template("admin/reports.html", orders=orders, total=snapshot["total_cents"],
                           order_count=snapshot["order_count"], items_served=snapshot["items_served"],
                           products=snapshot["products"], by_status=snapshot["by_status"])

@admin_bp.get("/reports/live")
@roles_required("admin", "supervisor")
def reports_live():
    snapshot = report_snapshot()
    orders = Order.query.filter(Order.status.in_(SALES_STATUSES)).order_by(Order.created_at.desc()).limit(100).all()
    response = jsonify({
        "currency": current_app.config["CURRENCY"],
        "all_time": {
            "total_cents": snapshot["total_cents"],
            "order_count": snapshot["order_count"],
            "items_served": snapshot["items_served"],
            "items_value_cents": snapshot["items_value_cents"],
        },
        "today": snapshot["today"],
        "by_status": [{"status": status, "count": count} for status, count in snapshot["by_status"]],
        "products": snapshot["products"],
        "orders": [{
            "order_number": order.order_number,
            "customer": order.customer.full_name,
            "date": order.created_at.strftime("%d %b %Y %H:%M"),
            "status": order.status,
            "total_cents": order.total_cents,
            "items": [{"name": item.product_name_snapshot, "quantity": item.quantity} for item in order.items],
        } for order in orders],
    })
    response.headers["Cache-Control"] = "no-store"
    return response
