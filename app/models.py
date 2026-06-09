import uuid
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db, login_manager


class Admin(UserMixin, db.Model):
    """Authenticated shop owner / operator."""

    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    # UI preference: 'mobile' or 'desktop'
    display_mode = db.Column(db.String(10), nullable=False, default="desktop")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(Admin, int(user_id))


class Customer(db.Model):
    """Loyalty programme participant."""

    __tablename__ = "customers"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email = db.Column(db.String(120), unique=True, nullable=True)
    first_name = db.Column(db.String(64), nullable=True)
    last_name = db.Column(db.String(64), nullable=True)
    points = db.Column(db.Integer, nullable=False, default=0)
    # Per-track balances: {"medium": 5, "large": 3}
    # For single-track configs this is {} and `points` is used directly.
    track_points = db.Column(db.JSON, nullable=True, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    wallet_cards = db.relationship(
        "WalletCard",
        backref="customer",
        lazy=True,
        cascade="all, delete-orphan",
    )
    transactions = db.relationship(
        "PointTransaction",
        backref="customer",
        lazy=True,
        cascade="all, delete-orphan",
    )

    @property
    def display_name(self) -> str:
        parts = [self.first_name or "", self.last_name or ""]
        name = " ".join(p for p in parts if p).strip()
        return name if name else f"Customer #{self.id[:8]}"


class WalletCard(db.Model):
    """A digital wallet pass linked to a customer."""

    __tablename__ = "wallet_cards"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    customer_id = db.Column(
        db.String(36), db.ForeignKey("customers.id"), nullable=False
    )
    # 'google' | 'apple' | 'samsung'
    wallet_type = db.Column(db.String(20), nullable=False)
    # Provider-side pass ID (for push updates)
    pass_id = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("customer_id", "wallet_type", name="uq_customer_wallet"),
    )


class PointTransaction(db.Model):
    """Immutable audit record for every points change."""

    __tablename__ = "point_transactions"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(
        db.String(36), db.ForeignKey("customers.id"), nullable=False
    )
    action_id = db.Column(db.String(64), nullable=False)
    action_name = db.Column(db.String(128), nullable=False)
    points_delta = db.Column(db.Integer, nullable=False)
    track_id = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
