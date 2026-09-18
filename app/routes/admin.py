from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.loyalty import load_config
from app.models import Admin
from app.permissions import admin_required

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/settings")
@login_required
@admin_required
def settings():
    config = None
    try:
        config = load_config(current_app.config["LOYALTY_CONFIG_PATH"])
    except Exception as exc:
        flash(f"Could not load loyalty configuration: {exc}", "warning")
    staff_members = Admin.query.order_by(Admin.role, Admin.username).all()
    return render_template(
        "admin_settings.html", config=config, staff_members=staff_members
    )


@admin_bp.route("/operators", methods=["POST"])
@login_required
@admin_required
def create_operator():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "operator")

    if not username:
        flash("Username is required.", "danger")
    elif len(password) < 8:
        flash("Password must be at least 8 characters.", "danger")
    elif role not in {"admin", "operator"}:
        flash("Invalid role.", "danger")
    elif Admin.query.filter_by(username=username).first():
        flash("That username is already in use.", "danger")
    else:
        operator = Admin(username=username, role=role)
        operator.set_password(password)
        db.session.add(operator)
        db.session.commit()
        flash(f"{role.capitalize()} '{username}' created.", "success")

    return redirect(url_for("admin.settings"))


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
