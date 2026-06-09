"""Wallet service factories — return None when credentials are absent."""

from __future__ import annotations

import os

from flask import current_app


def get_google_wallet_service():
    issuer_id = current_app.config.get("GOOGLE_WALLET_ISSUER_ID", "")
    class_suffix = current_app.config.get("GOOGLE_WALLET_CLASS_SUFFIX", "loyalty_card")
    sa_file = current_app.config.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")

    if not issuer_id or not sa_file:
        return None

    try:
        from app.wallet.google_wallet import GoogleWalletService
        return GoogleWalletService(issuer_id, class_suffix, sa_file)
    except Exception as exc:
        current_app.logger.warning("Google Wallet init failed: %s", exc)
        return None


def get_apple_wallet_service():
    pass_type_id = current_app.config.get("APPLE_PASS_TYPE_ID", "")
    team_id = current_app.config.get("APPLE_TEAM_ID", "")
    cert_pem = current_app.config.get("APPLE_CERT_PEM", "")
    key_pem = current_app.config.get("APPLE_KEY_PEM", "")
    wwdr_pem = current_app.config.get("APPLE_WWDR_PEM", "")

    if not (pass_type_id and team_id):
        return None

    # Accept either a file path or PEM content directly
    def _resolve(val: str) -> str:
        if val and os.path.isfile(val):
            with open(val, "r", encoding="utf-8") as fh:
                return fh.read()
        return val

    cert_pem = _resolve(cert_pem)
    key_pem = _resolve(key_pem)
    wwdr_pem = _resolve(wwdr_pem)

    if not (cert_pem and key_pem and wwdr_pem):
        return None

    try:
        from app.wallet.apple_wallet import AppleWalletService
        return AppleWalletService(pass_type_id, team_id, cert_pem, key_pem, wwdr_pem)
    except Exception as exc:
        current_app.logger.warning("Apple Wallet init failed: %s", exc)
        return None


def get_samsung_wallet_service():
    service_id = current_app.config.get("SAMSUNG_SERVICE_ID", "")
    api_key = current_app.config.get("SAMSUNG_API_KEY", "")
    card_type_id = current_app.config.get("SAMSUNG_CARD_TYPE_ID", "")

    if not (service_id and api_key):
        return None

    try:
        from app.wallet.samsung_wallet import SamsungWalletService
        return SamsungWalletService(service_id, api_key, card_type_id)
    except Exception as exc:
        current_app.logger.warning("Samsung Wallet init failed: %s", exc)
        return None
