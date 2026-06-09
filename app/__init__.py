import os

from flask import Flask

from app.extensions import db, login_manager, csrf


def create_app() -> Flask:
    app = Flask(__name__)

    # ── Core settings ──────────────────────────────────────────────────────────
    app.config["SECRET_KEY"] = os.environ.get(
        "SECRET_KEY", "dev-secret-key-CHANGE-IN-PRODUCTION"
    )
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///loyalty.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["WTF_CSRF_TIME_LIMIT"] = None  # sessions don't expire mid-shift

    # ── Loyalty config ─────────────────────────────────────────────────────────
    app.config["LOYALTY_CONFIG_PATH"] = os.environ.get(
        "LOYALTY_CONFIG_PATH", "config/pizzeria.json"
    )
    app.config["APP_BASE_URL"] = os.environ.get("APP_BASE_URL", "http://localhost:5000")

    # ── Google Wallet ──────────────────────────────────────────────────────────
    app.config["GOOGLE_WALLET_ISSUER_ID"] = os.environ.get(
        "GOOGLE_WALLET_ISSUER_ID", ""
    )
    app.config["GOOGLE_WALLET_CLASS_SUFFIX"] = os.environ.get(
        "GOOGLE_WALLET_CLASS_SUFFIX", "loyalty_card"
    )
    app.config["GOOGLE_SERVICE_ACCOUNT_FILE"] = os.environ.get(
        "GOOGLE_SERVICE_ACCOUNT_FILE", ""
    )

    # ── Apple Wallet ───────────────────────────────────────────────────────────
    app.config["APPLE_PASS_TYPE_ID"] = os.environ.get("APPLE_PASS_TYPE_ID", "")
    app.config["APPLE_TEAM_ID"] = os.environ.get("APPLE_TEAM_ID", "")
    app.config["APPLE_CERT_PEM"] = os.environ.get("APPLE_CERT_PEM", "")
    app.config["APPLE_KEY_PEM"] = os.environ.get("APPLE_KEY_PEM", "")
    app.config["APPLE_WWDR_PEM"] = os.environ.get("APPLE_WWDR_PEM", "")

    # ── Samsung Wallet ─────────────────────────────────────────────────────────
    app.config["SAMSUNG_SERVICE_ID"] = os.environ.get("SAMSUNG_SERVICE_ID", "")
    app.config["SAMSUNG_API_KEY"] = os.environ.get("SAMSUNG_API_KEY", "")
    app.config["SAMSUNG_CARD_TYPE_ID"] = os.environ.get("SAMSUNG_CARD_TYPE_ID", "")

    # ── Extensions ─────────────────────────────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    # ── Blueprints ─────────────────────────────────────────────────────────────
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.customer import customer_bp
    from app.routes.wallet import wallet_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(customer_bp, url_prefix="/customers")
    app.register_blueprint(wallet_bp, url_prefix="/wallet")

    return app
