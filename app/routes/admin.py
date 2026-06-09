from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.loyalty import load_config

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/settings")
@login_required
def settings():
    config = None
    try:
        config = load_config(current_app.config["LOYALTY_CONFIG_PATH"])
    except Exception as exc:
        flash(f"Could not load loyalty configuration: {exc}", "warning")
    return render_template("admin_settings.html", config=config)


@admin_bp.route("/toggle-display", methods=["POST"])
@login_required
def toggle_display():
    current_user.display_mode = (
        "mobile" if current_user.display_mode == "desktop" else "desktop"
    )
    db.session.commit()
    return jsonify({"display_mode": current_user.display_mode, "success": True})


@admin_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not current_user.check_password(current_password):
        flash("Current password is incorrect.", "danger")
        return redirect(url_for("admin.settings"))

    if len(new_password) < 8:
        flash("New password must be at least 8 characters.", "danger")
        return redirect(url_for("admin.settings"))

    if new_password != confirm_password:
        flash("Passwords do not match.", "danger")
        return redirect(url_for("admin.settings"))

    current_user.set_password(new_password)
    db.session.commit()
    flash("Password changed successfully.", "success")
    return redirect(url_for("admin.settings"))
