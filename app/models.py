from datetime import datetime, timezone
from decimal import Decimal
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db, login_manager

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(40))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="customer", index=True)
    is_active_account = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    orders = db.relationship("Order", backref="customer", lazy=True)
    bookings = db.relationship("RoomBooking", backref="customer", lazy=True)

    @property
    def is_active(self):
        return self.is_active_account

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None

class BusinessProfile(db.Model):
    """Single-row settings record for the business name and logo."""
    id = db.Column(db.Integer, primary_key=True, default=1)
    name = db.Column(db.String(120), nullable=False)
    logo_path = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

class UploadedFile(db.Model):
    """Image bytes stored in PostgreSQL because serverless disks are ephemeral."""
    id = db.Column(db.Integer, primary_key=True)
    folder = db.Column(db.String(40), nullable=False, index=True)
    filename = db.Column(db.String(80), unique=True, nullable=False, index=True)
    mimetype = db.Column(db.String(60), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    @property
    def path(self):
        return f"uploads/{self.folder}/{self.filename}"

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    products = db.relationship("Product", backref="category", lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    price_cents = db.Column(db.Integer, nullable=False)
    cost_cents = db.Column(db.Integer, default=0, nullable=False)
    stock_quantity = db.Column(db.Integer, default=0, nullable=False)
    reorder_level = db.Column(db.Integer, default=5, nullable=False)
    image_path = db.Column(db.String(255))
    is_available = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

class RestaurantTable(db.Model):
    __tablename__ = "restaurant_table"
    id = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.String(20), unique=True, nullable=False)
    capacity = db.Column(db.Integer, default=4, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    table_id = db.Column(db.Integer, db.ForeignKey("restaurant_table.id"))
    order_type = db.Column(db.String(20), default="takeaway", nullable=False)
    status = db.Column(db.String(30), default="pending", nullable=False, index=True)
    subtotal_cents = db.Column(db.Integer, nullable=False)
    discount_cents = db.Column(db.Integer, default=0, nullable=False)
    tax_cents = db.Column(db.Integer, default=0, nullable=False)
    total_cents = db.Column(db.Integer, nullable=False)
    special_instructions = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan", lazy=True)
    status_history = db.relationship("OrderStatusHistory", backref="order", cascade="all, delete-orphan", lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    product_name_snapshot = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price_cents = db.Column(db.Integer, nullable=False)
    line_total_cents = db.Column(db.Integer, nullable=False)

class OrderStatusHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    status = db.Column(db.String(30), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    changed_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    note = db.Column(db.String(255))

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(20), unique=True, nullable=False)
    room_type = db.Column(db.String(60), default="Standard", nullable=False)
    description = db.Column(db.Text)
    hourly_rate_cents = db.Column(db.Integer, nullable=False)
    daily_rate_cents = db.Column(db.Integer, nullable=False)
    weekly_rate_cents = db.Column(db.Integer, nullable=False)
    capacity = db.Column(db.Integer, default=2, nullable=False)
    status = db.Column(db.String(30), default="available", nullable=False, index=True)
    image_path = db.Column(db.String(255))

class RoomBooking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_reference = db.Column(db.String(30), unique=True, nullable=False, index=True)
    room_id = db.Column(db.Integer, db.ForeignKey("room.id"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    check_in_at = db.Column(db.DateTime, nullable=False, index=True)
    check_out_at = db.Column(db.DateTime, nullable=False, index=True)
    booking_unit = db.Column(db.String(10), nullable=False)
    total_cents = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), default="confirmed", nullable=False, index=True)
    payment_status = db.Column(db.String(30), default="unpaid", nullable=False)
    actual_check_in_at = db.Column(db.DateTime)
    actual_check_out_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    room = db.relationship("Room", backref=db.backref("bookings", lazy=True))

class RoomBlock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("room.id"), nullable=False, index=True)
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_reference = db.Column(db.String(80), unique=True, nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"))
    booking_id = db.Column(db.Integer, db.ForeignKey("room_booking.id"))
    amount_cents = db.Column(db.Integer, nullable=False)
    payment_method = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(30), default="pending", nullable=False)
    provider_reference = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

class InventoryMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    quantity_change = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

class Discount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    percent_off = db.Column(db.Integer, default=0, nullable=False)
    amount_off_cents = db.Column(db.Integer, default=0, nullable=False)
    starts_at = db.Column(db.DateTime)
    ends_at = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    action = db.Column(db.String(120), nullable=False)
    entity_type = db.Column(db.String(80))
    entity_id = db.Column(db.String(80))
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
