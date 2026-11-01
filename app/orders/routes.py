from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from ..extensions import db, socketio
from ..models import Category, Product, Order, OrderItem, OrderStatusHistory, Notification, AuditLog, InventoryMovement, RestaurantTable

orders_bp = Blueprint("orders", __name__)

@orders_bp.get("/menu")
def menu():
    categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
    category_id = request.args.get("category", type=int)
    query = Product.query.filter_by(is_available=True)
    if category_id:
        query = query.filter_by(category_id=category_id)
    products = query.order_by(Product.name).all()
    return render_template("customer/menu.html", categories=categories, products=products, selected_category=category_id)

@orders_bp.get("/cart")
@login_required
def cart():
    return render_template("customer/cart.html")

@orders_bp.post("/orders")
@login_required
def create_order():
    payload = request.get_json(silent=True) if request.is_json else request.form
    raw_items = payload.get("items") if hasattr(payload, "get") else None
    if isinstance(raw_items, str):
        import json
        try: raw_items = json.loads(raw_items)
        except ValueError: raw_items = None
    if not isinstance(raw_items, list) or not raw_items:
        flash("Your cart is empty.", "danger")
        return redirect(url_for("orders.menu"))
    quantities = {}
    for item in raw_items:
        try:
            pid, qty = int(item.get("product_id")), int(item.get("quantity"))
        except (TypeError, ValueError, AttributeError):
            return jsonify(error="Invalid cart item."), 400
        if qty < 1 or qty > 50:
            return jsonify(error="Quantity must be between 1 and 50."), 400
        quantities[pid] = quantities.get(pid, 0) + qty
    products = Product.query.filter(Product.id.in_(quantities.keys()), Product.is_available.is_(True)).all()
    if len(products) != len(quantities):
        return jsonify(error="One or more products are unavailable."), 409
    subtotal = 0
    for p in products:
        if p.stock_quantity < quantities[p.id]:
            return jsonify(error=f"Insufficient stock for {p.name}."), 409
        subtotal += p.price_cents * quantities[p.id]
    order = Order(order_number=f"ORD-{datetime.utcnow():%y%m%d%H%M%S}-{current_user.id}", customer_id=current_user.id,
                  order_type=(payload.get("order_type", "takeaway") if hasattr(payload, "get") else "takeaway"),
                  status="pending", subtotal_cents=subtotal, total_cents=subtotal,
                  special_instructions=(payload.get("special_instructions", "") if hasattr(payload, "get") else ""))
    if order.order_type not in {"dine_in", "takeaway", "delivery"}:
        return jsonify(error="Invalid order type."), 400
    try:
        db.session.add(order); db.session.flush()
        for p in products:
            qty = quantities[p.id]
            # Deduct stock within the same transaction as the order.
            p.stock_quantity -= qty
            db.session.add(InventoryMovement(product_id=p.id, quantity_change=-qty,
                                             reason=f"Stock deducted for {order.order_number}",
                                             user_id=current_user.id))
            order.items.append(OrderItem(product_id=p.id, product_name_snapshot=p.name, quantity=qty,
                                          unit_price_cents=p.price_cents, line_total_cents=p.price_cents * qty))
        order.status_history.append(OrderStatusHistory(status="pending", changed_by=current_user.id))
        db.session.add(Notification(user_id=current_user.id, title="Order received", message=f"Order {order.order_number} was received."))
        db.session.add(AuditLog(user_id=current_user.id, action="order_created", entity_type="order", entity_id=str(order.id)))
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app = __import__("flask").current_app
        current_app.logger.exception("Order creation failed")
        return jsonify(error="The order could not be saved. Please try again."), 500
    data = {"id": order.id, "order_number": order.order_number, "customer": current_user.full_name,
            "status": order.status, "total": order.total_cents / 100,
            "items": [{"name": i.product_name_snapshot, "quantity": i.quantity} for i in order.items]}
    socketio.emit("order_created", data, to="staff")
    if request.is_json:
        return jsonify(message="Order placed successfully.", order=data), 201
    flash(f"Order {order.order_number} placed successfully.", "success")
    return redirect(url_for("orders.my_orders"))

@orders_bp.get("/my-orders")
@login_required
def my_orders():
    orders = Order.query.filter_by(customer_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template("customer/orders.html", orders=orders)

@orders_bp.get("/api/my-orders")
@login_required
def my_orders_api():
    orders = Order.query.filter_by(customer_id=current_user.id).order_by(Order.created_at.desc()).limit(50).all()
    return jsonify([{"id": o.id, "order_number": o.order_number, "status": o.status, "total": o.total_cents / 100,
                     "items": [{"name": i.product_name_snapshot, "quantity": i.quantity} for i in o.items]} for o in orders])

@orders_bp.get("/api/admin/orders")
@login_required
def admin_orders_api():
    if current_user.role not in {"admin", "supervisor", "chef", "bartender", "waiter", "cashier"}:
        abort(403)
    orders = Order.query.order_by(Order.created_at.desc()).limit(100).all()
    return jsonify([{"id": o.id, "order_number": o.order_number, "customer": o.customer.full_name,
                     "status": o.status, "total": o.total_cents / 100,
                     "items": [{"name": i.product_name_snapshot, "quantity": i.quantity} for i in o.items]} for o in orders])
