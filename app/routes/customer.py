import csv
import io
from datetime import datetime

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
from sqlalchemy import or_

import qrcode
import qrcode.constants

from app.extensions import db
from app.models import Customer, PointTransaction, WalletCard
from app.loyalty import (
    load_config,
    get_config_tracks,
    get_track_points_value,
    get_track_status,
    get_all_track_status,
    get_available_rewards,
    get_combined_status_message,
    format_phone_number,
    get_phone_number_extension,
    normalize_french_phone,
)

customer_bp = Blueprint("customer", __name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_config():
    return load_config(current_app.config["LOYALTY_CONFIG_PATH"])


def _update_wallet_passes(customer: Customer, config: dict) -> None:
    """Best-effort push of updated points to registered wallet passes."""
    from app.wallet import get_google_wallet_service

    has_google = any(c.wallet_type == "google" for c in customer.wallet_cards)
    if not has_google:
        return

    gw = get_google_wallet_service()
    if not gw:
        return

    tracks = get_config_tracks(config)
    primary_track = tracks[0]
    primary_pts = get_track_points_value(customer, primary_track["id"])
    primary_label = primary_track.get("action_unit", "point").capitalize()

    secondary_pts = None
    secondary_label = None
    if len(tracks) > 1:
        sec_track = tracks[1]
        secondary_pts = get_track_points_value(customer, sec_track["id"])
        secondary_label = sec_track.get("action_unit", "point").capitalize()

    gw.update_loyalty_object(
        customer_id=customer.id,
        points=primary_pts,
        status_message=get_combined_status_message(config, customer),
        points_label=primary_label,
        secondary_points=secondary_pts,
        secondary_label=secondary_label,
    )


def _track_status_payload(config: dict, customer: Customer) -> dict:
    """Build the track_status dict returned in JSON responses."""
    result = {}
    for track in get_config_tracks(config):
        tid = track["id"]
        pts = get_track_points_value(customer, tid)
        ts = get_track_status(config, tid, pts)
        remaining = max(0, ts["points_required"] - pts) if ts["points_required"] else 0
        result[tid] = {
            "track_name": track.get("name", tid),
            "action_unit": track.get("action_unit", "point"),
            "points": pts,
            "status_message": ts["message"],
            "progress_pct": ts["progress_pct"],
            "points_required": ts["points_required"],
            "remaining": remaining,
        }
    return result


# ── routes ────────────────────────────────────────────────────────────────────

@customer_bp.route("/")
@login_required
def list_customers():
    customers = Customer.query.order_by(Customer.created_at.desc()).all()
    config = _get_config()
    phone_extension = get_phone_number_extension(config)
    formatted_phone_numbers = {
        customer.id: format_phone_number(customer.phone_number, config)
        for customer in customers
    }
    phone_search_values = {
        customer.id: " ".join(filter(None, [
            customer.phone_number,
            "0" + customer.phone_number[len(phone_extension):]
            if customer.phone_number and customer.phone_number.startswith(phone_extension)
            else None,
        ]))
        for customer in customers
    }
    return render_template(
        "dashboard.html",
        customers=customers,
        config=config,
        formatted_phone_numbers=formatted_phone_numbers,
        phone_search_values=phone_search_values,
    )


@customer_bp.route("/export.csv")
@login_required
def export_customers():
    customers = Customer.query.order_by(Customer.created_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "first_name", "last_name", "email", "phone_number", "points", "registered_at"
    ])
    for customer in customers:
        writer.writerow([
            customer.id,
            customer.first_name or "",
            customer.last_name or "",
            customer.email or "",
            customer.phone_number or "",
            customer.points,
            customer.created_at.isoformat(),
        ])

    csv_bytes = io.BytesIO(("\ufeff" + output.getvalue()).encode("utf-8"))
    filename = f"customers-{datetime.now().strftime('%Y-%m-%d')}.csv"
    return send_file(
        csv_bytes,
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=filename,
    )


@customer_bp.route("/scan")
@login_required
def scan():
    config = _get_config()
    return render_template("scan.html", config=config)


@customer_bp.route("/search")
@login_required
def search_customers():
    query = request.args.get("q", "").strip()
    if len(query) < 3:
        return jsonify({"customers": []})

    config = _get_config()
    phone_digits = "".join(character for character in query if character.isdigit())
    if phone_digits.startswith("0"):
        extension_digits = get_phone_number_extension(config).lstrip("+")
        phone_digits = extension_digits + phone_digits[1:]

    filters = [
        Customer.first_name.ilike(f"%{query}%"),
        Customer.last_name.ilike(f"%{query}%"),
        Customer.email.ilike(f"%{query}%"),
    ]
    if phone_digits:
        filters.append(Customer.phone_number.like(f"%{phone_digits}%"))

    customers = (
        Customer.query.filter(or_(*filters))
        .order_by(Customer.last_name, Customer.first_name, Customer.created_at.desc())
        .limit(10)
        .all()
    )
    return jsonify({
        "customers": [
            {
                "id": customer.id,
                "name": customer.display_name,
                "email": customer.email or "",
                "phone_number": format_phone_number(customer.phone_number, config),
                "url": url_for("customer.customer_detail", customer_id=customer.id),
            }
            for customer in customers
        ]
    })


@customer_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_customer():
    config = _get_config()
    if request.method == "POST":
        email = request.form.get("email", "").strip() or None
        first_name = request.form.get("first_name", "").strip() or None
        last_name = request.form.get("last_name", "").strip() or None
        try:
            phone_number = normalize_french_phone(
                request.form.get("phone_number", ""), config
            )
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("new_customer.html", config=config)

        if email:
            if Customer.query.filter_by(email=email).first():
                flash("A customer with this email already exists.", "danger")
                return render_template("new_customer.html", config=config)

        customer = Customer(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
        )
        db.session.add(customer)
        db.session.commit()

        flash(f"Customer registered! ID: {customer.id}", "success")
        return redirect(url_for("customer.customer_detail", customer_id=customer.id))

    return render_template("new_customer.html", config=config)


@customer_bp.route("/<customer_id>")
@login_required
def customer_detail(customer_id: str):
    customer = db.get_or_404(Customer, customer_id)
    config = _get_config()

    config_tracks = get_config_tracks(config)
    is_multi_track = len(config_tracks) > 1
    track_status = get_all_track_status(config, customer)
    available_rewards = get_available_rewards(config, customer)

    transactions = (
        PointTransaction.query.filter_by(customer_id=customer_id)
        .order_by(PointTransaction.created_at.desc())
        .limit(10)
        .all()
    )

    wallet_types = {c.wallet_type for c in customer.wallet_cards}

    return render_template(
        "customer_detail.html",
        customer=customer,
        config=config,
        config_tracks=config_tracks,
        is_multi_track=is_multi_track,
        track_status=track_status,
        available_rewards=available_rewards,
        transactions=transactions,
        wallet_types=wallet_types,
        formatted_phone_number=format_phone_number(customer.phone_number, config),
    )


@customer_bp.route("/<customer_id>/edit", methods=["GET", "POST"])
@login_required
def edit_customer(customer_id: str):
    customer = db.get_or_404(Customer, customer_id)
    config = _get_config()

    if request.method == "POST":
        email = request.form.get("email", "").strip() or None
        first_name = request.form.get("first_name", "").strip() or None
        last_name = request.form.get("last_name", "").strip() or None
        try:
            phone_number = normalize_french_phone(
                request.form.get("phone_number", ""), config
            )
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template(
                "edit_customer.html", customer=customer, config=config
            )

        if email and Customer.query.filter(
            Customer.email == email,
            Customer.id != customer.id,
        ).first():
            flash("A customer with this email already exists.", "danger")
            return render_template(
                "edit_customer.html", customer=customer, config=config
            )

        customer.email = email
        customer.first_name = first_name
        customer.last_name = last_name
        customer.phone_number = phone_number
        db.session.commit()

        flash("Customer details updated.", "success")
        return redirect(url_for("customer.customer_detail", customer_id=customer.id))

    return render_template(
        "edit_customer.html",
        customer=customer,
        config=config,
        formatted_phone_number=format_phone_number(customer.phone_number, config),
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

    track_id = action.get("track_id", "default")
    points_delta = action["points"] * delta

    # Work with a copy so SQLAlchemy detects the change
    tp = dict(customer.track_points or {})

    # Migrate legacy single-track customers
    if not tp and customer.points > 0:
        tp["default"] = customer.points

    current = tp.get(track_id, 0)
    new_val = current + points_delta
    if new_val < 0:
        return jsonify({"error": "Cannot subtract below 0", "track_points": tp}), 400

    tp[track_id] = new_val
    customer.track_points = tp
    customer.points = sum(tp.values())

    db.session.add(
        PointTransaction(
            customer_id=customer_id,
            action_id=action_id,
            action_name=action["name"],
            points_delta=points_delta,
            track_id=track_id,
        )
    )
    db.session.commit()

    try:
        _update_wallet_passes(customer, config)
    except Exception as exc:
        current_app.logger.warning("Wallet update failed: %s", exc)

    return jsonify({
        "success": True,
        "track_id": track_id,
        "points_delta": points_delta,
        "total_points": customer.points,
        "track_status": _track_status_payload(config, customer),
        "available_rewards": get_available_rewards(config, customer),
    })


@customer_bp.route("/<customer_id>/scan-credit", methods=["POST"])
@login_required
def scan_credit(customer_id: str):
    """Apply a batch of preselected action quantities right after scan."""
    customer = db.get_or_404(Customer, customer_id)
    config = _get_config()

    data = request.get_json(silent=True) or {}
    actions_qty = data.get("actions", {})
    if not isinstance(actions_qty, dict) or not actions_qty:
        return jsonify({"error": "No actions selected"}), 400

    actions_map = {a["id"]: a for a in config.get("actions", [])}

    tp = dict(customer.track_points or {})
    if not tp and customer.points > 0:
        tp["default"] = customer.points

    applied = []
    for action_id, qty_raw in actions_qty.items():
        action = actions_map.get(action_id)
        if not action:
            return jsonify({"error": f"Unknown action: {action_id}"}), 400

        try:
            qty = int(qty_raw)
        except (TypeError, ValueError):
            return jsonify({"error": f"Invalid quantity for {action_id}"}), 400

        if qty < 0:
            return jsonify({"error": f"Quantity cannot be negative for {action_id}"}), 400
        if qty == 0:
            continue

        track_id = action.get("track_id", "default")
        points_delta = action["points"] * qty
        tp[track_id] = tp.get(track_id, 0) + points_delta

        db.session.add(
            PointTransaction(
                customer_id=customer_id,
                action_id=action_id,
                action_name=f"{action['name']} x{qty}",
                points_delta=points_delta,
                track_id=track_id,
            )
        )
        applied.append({
            "action_id": action_id,
            "action_name": action["name"],
            "quantity": qty,
            "points_delta": points_delta,
            "track_id": track_id,
        })

    if not applied:
        return jsonify({"error": "No positive quantities selected"}), 400

    customer.track_points = tp
    customer.points = sum(tp.values())
    db.session.commit()

    try:
        _update_wallet_passes(customer, config)
    except Exception as exc:
        current_app.logger.warning("Wallet update failed: %s", exc)

    track_status = _track_status_payload(config, customer)
    remaining_by_track = {
        tid: {
            "track_name": info["track_name"],
            "action_unit": info["action_unit"],
            "remaining": info["remaining"],
        }
        for tid, info in track_status.items()
    }

    return jsonify({
        "success": True,
        "customer_id": customer.id,
        "customer_name": customer.display_name,
        "applied": applied,
        "total_points": customer.points,
        "track_status": track_status,
        "remaining_by_track": remaining_by_track,
        "available_rewards": get_available_rewards(config, customer),
    })


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

    track_id = reward.get("track_id", "default")

    tp = dict(customer.track_points or {})
    if not tp and customer.points > 0:
        tp["default"] = customer.points

    current = tp.get(track_id, 0)
    if current < reward["points_required"]:
        return jsonify({"error": "Insufficient points"}), 400

    tp[track_id] = current - reward["points_required"]
    customer.track_points = tp
    customer.points = sum(tp.values())

    db.session.add(
        PointTransaction(
            customer_id=customer_id,
            action_id=f"cashout_{reward_id}",
            action_name=f"Reward: {reward['name']}",
            points_delta=-reward["points_required"],
            track_id=track_id,
        )
    )
    db.session.commit()

    try:
        _update_wallet_passes(customer, config)
    except Exception as exc:
        current_app.logger.warning("Wallet update failed: %s", exc)

    return jsonify({
        "success": True,
        "total_points": customer.points,
        "track_status": _track_status_payload(config, customer),
        "available_rewards": get_available_rewards(config, customer),
        "message": f'Reward "{reward["name"]}" redeemed successfully!',
    })


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
