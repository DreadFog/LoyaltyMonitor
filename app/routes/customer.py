import io

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    jsonify,
    send_file,
    current_app,
)
from flask_login import login_required

import qrcode
import qrcode.constants

from app.extensions import db
from app.models import Customer, PointTransaction, WalletCard
from app.loyalty import load_config, get_status_message, get_progress_pct

customer_bp = Blueprint("customer", __name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_config():
    return load_config(current_app.config["LOYALTY_CONFIG_PATH"])


def _update_wallet_passes(customer: Customer, config: dict) -> None:
    """Best-effort push of updated points to registered wallet passes."""
    from app.wallet import get_google_wallet_service

    status_msg = get_status_message(config, customer.points)
    has_google = any(c.wallet_type == "google" for c in customer.wallet_cards)

    if has_google:
        rewards = config.get("rewards", [])
        points_label = rewards[0].get("action_unit", "Points").capitalize() if rewards else "Points"
        gw = get_google_wallet_service()
        if gw:
            gw.update_loyalty_object(
                customer_id=customer.id,
                points=customer.points,
                status_message=status_msg,
                points_label=points_label,
            )


# ── routes ────────────────────────────────────────────────────────────────────

@customer_bp.route("/")
@login_required
def list_customers():
    customers = Customer.query.order_by(Customer.created_at.desc()).all()
    config = _get_config()
    return render_template("dashboard.html", customers=customers, config=config)


@customer_bp.route("/scan")
@login_required
def scan():
    config = _get_config()
    return render_template("scan.html", config=config)


@customer_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_customer():
    if request.method == "POST":
        email = request.form.get("email", "").strip() or None
        first_name = request.form.get("first_name", "").strip() or None
        last_name = request.form.get("last_name", "").strip() or None

        if email:
            if Customer.query.filter_by(email=email).first():
                flash("A customer with this email already exists.", "danger")
                return render_template("new_customer.html")

        customer = Customer(email=email, first_name=first_name, last_name=last_name)
        db.session.add(customer)
        db.session.commit()

        flash(f"Customer registered! ID: {customer.id}", "success")
        return redirect(url_for("customer.customer_detail", customer_id=customer.id))

    return render_template("new_customer.html")


@customer_bp.route("/<customer_id>")
@login_required
def customer_detail(customer_id: str):
    customer = db.get_or_404(Customer, customer_id)
    config = _get_config()

    status_message = get_status_message(config, customer.points)
    progress_pct = get_progress_pct(config, customer.points)

    transactions = (
        PointTransaction.query.filter_by(customer_id=customer_id)
        .order_by(PointTransaction.created_at.desc())
        .limit(10)
        .all()
    )

    available_rewards = [
        r for r in config.get("rewards", []) if customer.points >= r["points_required"]
    ]

    wallet_types = {c.wallet_type for c in customer.wallet_cards}
    max_points = (
        config["rewards"][0]["points_required"] if config.get("rewards") else 10
    )

    return render_template(
        "customer_detail.html",
        customer=customer,
        config=config,
        status_message=status_message,
        progress_pct=progress_pct,
        transactions=transactions,
        available_rewards=available_rewards,
        wallet_types=wallet_types,
        max_points=max_points,
    )


@customer_bp.route("/<customer_id>/add-points", methods=["POST"])
@login_required
def add_points(customer_id: str):
    customer = db.get_or_404(Customer, customer_id)
    config = _get_config()

    data = request.get_json(silent=True) or {}
    action_id = data.get("action_id")
    delta = data.get("delta", 1)

    if delta not in (1, -1):
        return jsonify({"error": "delta must be 1 or -1"}), 400

    action = next((a for a in config.get("actions", []) if a["id"] == action_id), None)
    if not action:
        return jsonify({"error": "Unknown action"}), 400

    points_delta = action["points"] * delta
    new_points = customer.points + points_delta
    if new_points < 0:
        return jsonify({"error": "Cannot subtract below 0 points", "points": customer.points}), 400

    customer.points = new_points
    db.session.add(
        PointTransaction(
            customer_id=customer_id,
            action_id=action_id,
            action_name=action["name"],
            points_delta=points_delta,
        )
    )
    db.session.commit()

    try:
        _update_wallet_passes(customer, config)
    except Exception as exc:
        current_app.logger.warning("Wallet update failed: %s", exc)

    available_rewards = [
        r for r in config.get("rewards", []) if customer.points >= r["points_required"]
    ]

    return jsonify(
        {
            "success": True,
            "points": customer.points,
            "points_delta": points_delta,
            "status_message": get_status_message(config, customer.points),
            "progress_pct": get_progress_pct(config, customer.points),
            "available_rewards": available_rewards,
        }
    )


@customer_bp.route("/<customer_id>/cashout", methods=["POST"])
@login_required
def cashout(customer_id: str):
    customer = db.get_or_404(Customer, customer_id)
    config = _get_config()

    data = request.get_json(silent=True) or {}
    reward_id = data.get("reward_id")

    reward = next((r for r in config.get("rewards", []) if r["id"] == reward_id), None)
    if not reward:
        return jsonify({"error": "Unknown reward"}), 400

    if customer.points < reward["points_required"]:
        return jsonify({"error": "Insufficient points"}), 400

    customer.points -= reward["points_required"]
    db.session.add(
        PointTransaction(
            customer_id=customer_id,
            action_id=f"cashout_{reward_id}",
            action_name=f"Reward: {reward['name']}",
            points_delta=-reward["points_required"],
        )
    )
    db.session.commit()

    try:
        _update_wallet_passes(customer, config)
    except Exception as exc:
        current_app.logger.warning("Wallet update failed: %s", exc)

    return jsonify(
        {
            "success": True,
            "points": customer.points,
            "status_message": get_status_message(config, customer.points),
            "progress_pct": get_progress_pct(config, customer.points),
            "message": f'Reward "{reward["name"]}" redeemed successfully!',
        }
    )


@customer_bp.route("/<customer_id>/delete", methods=["POST"])
@login_required
def delete_customer(customer_id: str):
    customer = db.get_or_404(Customer, customer_id)
    customer_name = customer.display_name

    db.session.delete(customer)
    db.session.commit()

    flash(f'Customer "{customer_name}" has been deleted.', "success")
    return redirect(url_for("customer.list_customers"))


@customer_bp.route("/<customer_id>/qr")
@login_required
def customer_qr(customer_id: str):
    customer = db.get_or_404(Customer, customer_id)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(customer.id)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")
