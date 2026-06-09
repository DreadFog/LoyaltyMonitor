from flask import Blueprint, jsonify, send_file, current_app
from flask_login import login_required

from app.extensions import db
from app.models import Customer, WalletCard
from app.loyalty import (
    load_config,
    get_config_tracks,
    get_track_points_value,
    get_combined_status_message,
    get_status_message,
)

wallet_bp = Blueprint("wallet", __name__)


def _get_config():
    return load_config(current_app.config["LOYALTY_CONFIG_PATH"])


def _register_card(customer_id: str, wallet_type: str) -> None:
    if not WalletCard.query.filter_by(
        customer_id=customer_id, wallet_type=wallet_type
    ).first():
        db.session.add(WalletCard(customer_id=customer_id, wallet_type=wallet_type))
        db.session.commit()


@wallet_bp.route("/google/<customer_id>")
@login_required
def google_wallet(customer_id: str):
    customer = db.get_or_404(Customer, customer_id)
    config = _get_config()

    from app.wallet import get_google_wallet_service

    gw = get_google_wallet_service()
    if not gw:
        return jsonify(
            {
                "error": (
                    "Google Wallet is not configured. "
                    "Set GOOGLE_WALLET_ISSUER_ID and GOOGLE_SERVICE_ACCOUNT_FILE."
                )
            }
        ), 503

    try:
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

        status_message = get_combined_status_message(config, customer)
        gw.ensure_loyalty_class(
            program_name=config.get("program_name", "Loyalty Program"),
            issuer_name=config.get("organization_name", "LoyaltyMonitor"),
        )
        gw.create_or_update_loyalty_object(
            customer_id=customer.id,
            customer_name=customer.display_name,
            points=primary_pts,
            points_label=primary_label,
            secondary_points=secondary_pts,
            secondary_label=secondary_label,
            status_message=status_message,
        )
        save_link = gw.generate_save_link(customer_id=customer.id)
        _register_card(customer_id, "google")
        return jsonify({"save_link": save_link})
    except Exception as exc:
        current_app.logger.error("Google Wallet error for %s: %s", customer_id, exc)
        return jsonify({"error": str(exc)}), 500


@wallet_bp.route("/apple/<customer_id>")
@login_required
def apple_wallet(customer_id: str):
    customer = db.get_or_404(Customer, customer_id)
    config = _get_config()

    from app.wallet import get_apple_wallet_service

    aw = get_apple_wallet_service()
    if not aw:
        return jsonify(
            {
                "error": (
                    "Apple Wallet is not configured. "
                    "Set APPLE_PASS_TYPE_ID, APPLE_TEAM_ID, and certificate paths."
                )
            }
        ), 503

    try:
        pass_buf = aw.create_pass(
            customer_id=customer.id,
            customer_name=customer.display_name,
            points=customer.points,
            status_message=get_status_message(config, customer.points),
            program_name=config.get("program_name", "Loyalty Program"),
            organization_name=config.get("organization_name", "LoyaltyMonitor"),
        )
        _register_card(customer_id, "apple")
        return send_file(
            pass_buf,
            mimetype="application/vnd.apple.pkpass",
            as_attachment=True,
            download_name=f"loyalty_{customer_id[:8]}.pkpass",
        )
    except Exception as exc:
        current_app.logger.error("Apple Wallet error for %s: %s", customer_id, exc)
        return jsonify({"error": str(exc)}), 500


@wallet_bp.route("/samsung/<customer_id>")
@login_required
def samsung_wallet(customer_id: str):
    customer = db.get_or_404(Customer, customer_id)
    config = _get_config()

    from app.wallet import get_samsung_wallet_service

    sw = get_samsung_wallet_service()
    if not sw:
        return jsonify(
            {
                "error": (
                    "Samsung Wallet is not configured. "
                    "Set SAMSUNG_SERVICE_ID, SAMSUNG_API_KEY, and SAMSUNG_CARD_TYPE_ID."
                )
            }
        ), 503

    try:
        result = sw.create_or_update_card(
            customer_id=customer.id,
            customer_name=customer.display_name,
            points=customer.points,
            status_message=get_status_message(config, customer.points),
            program_name=config.get("program_name", "Loyalty Program"),
        )
        _register_card(customer_id, "samsung")
        return jsonify(result)
    except Exception as exc:
        current_app.logger.error("Samsung Wallet error for %s: %s", customer_id, exc)
        return jsonify({"error": str(exc)}), 500
