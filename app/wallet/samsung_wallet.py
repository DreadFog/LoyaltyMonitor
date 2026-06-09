"""Samsung Wallet integration.

Required environment variables
--------------------------------
SAMSUNG_SERVICE_ID    — Service ID issued by Samsung Wallet Partner Portal
SAMSUNG_API_KEY       — API key from the Samsung Wallet Partner Portal
SAMSUNG_CARD_TYPE_ID  — Card type ID created in the Partner Portal

Setup steps
-----------
1. Apply for the Samsung Wallet Partner Programme at
   https://developer.samsung.com/wallet
2. Create a Loyalty Card type in the Partner Portal and note its Card Type ID.
3. Generate API credentials (Service ID + API Key).
4. Set the three env vars above.

API reference: https://developer.samsung.com/wallet/api-reference

Note: Samsung Wallet requires partner approval before cards can be issued to
real devices. The implementation below follows the documented REST API contract.
"""

from __future__ import annotations

import time

import jwt as pyjwt
import requests

_API_BASE = "https://walletpartner.samsung.com/v1"


class SamsungWalletService:
    def __init__(self, service_id: str, api_key: str, card_type_id: str) -> None:
        self.service_id = service_id
        self.api_key = api_key
        self.card_type_id = card_type_id

    # ── internal ──────────────────────────────────────────────────────────────

    def _make_token(self) -> str:
        """Build a short-lived JWT for API authentication."""
        payload = {
            "iss": self.service_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
        }
        return pyjwt.encode(payload, self.api_key, algorithm="HS256")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._make_token()}",
            "Content-Type": "application/json",
            "serviceId": self.service_id,
        }

    # ── public API ────────────────────────────────────────────────────────────

    def create_or_update_card(
        self,
        customer_id: str,
        customer_name: str,
        points: int,
        status_message: str,
        program_name: str,
    ) -> dict:
        """Create or update a Samsung Wallet loyalty card instance.

        Returns a dict containing ``add_link`` which the customer can open to
        add the card to Samsung Wallet.
        """
        card_body = {
            "cardTypeId": self.card_type_id,
            "cardId": customer_id,
            "attributes": [
                {"name": "memberName", "value": customer_name},
                {"name": "points", "value": str(points)},
                {"name": "status", "value": status_message},
                {"name": "programName", "value": program_name},
            ],
            "barcode": {
                "type": "QR_CODE",
                "value": customer_id,
            },
        }

        # Try to update first; fall back to create
        update_url = f"{_API_BASE}/cards/{self.card_type_id}/{customer_id}"
        resp = requests.put(update_url, json=card_body, headers=self._headers(), timeout=15)

        if resp.status_code == 404:
            create_url = f"{_API_BASE}/cards"
            resp = requests.post(create_url, json=card_body, headers=self._headers(), timeout=15)

        resp.raise_for_status()
        data: dict = resp.json()

        # Samsung Wallet deep link for adding the card
        add_link = data.get(
            "addLink",
            f"samsungpay://wallet/add?cardId={customer_id}&cardTypeId={self.card_type_id}",
        )
        return {"success": True, "add_link": add_link, "card_id": customer_id}
