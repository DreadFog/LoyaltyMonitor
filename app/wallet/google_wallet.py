"""Google Wallet Loyalty Pass integration.

Required environment variables
--------------------------------
GOOGLE_WALLET_ISSUER_ID         — Your Wallet Issuer ID from the Google Pay & Wallet Console
GOOGLE_WALLET_CLASS_SUFFIX      — Arbitrary suffix for the loyalty class (e.g. "loyalty_card")
GOOGLE_SERVICE_ACCOUNT_FILE     — Path to the service account JSON key file

Setup steps
-----------
1. Go to https://pay.google.com/business/console and create an Issuer account.
2. Enable the Google Wallet API in Google Cloud Console.
3. Create a service account, grant it the "Google Wallet Object Issuer" role,
   and download the JSON key.
4. Set the three env vars above.
5. On first use, call create_loyalty_class() once to register the programme with Google.
"""

from __future__ import annotations

import json
import time
from typing import Any

import jwt as pyjwt
import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

_SCOPES = ["https://www.googleapis.com/auth/wallet_object.issuer"]
_API = "https://walletobjects.googleapis.com/walletobjects/v1"


class GoogleWalletService:
    def __init__(self, issuer_id: str, class_suffix: str, sa_file: str) -> None:
        self.issuer_id = issuer_id
        self.class_id = f"{issuer_id}.{class_suffix}"
        self._sa_file = sa_file

        with open(sa_file, "r", encoding="utf-8") as fh:
            self._sa_data: dict[str, Any] = json.load(fh)

        self._credentials = service_account.Credentials.from_service_account_file(
            sa_file, scopes=_SCOPES
        )

    # ── internal ──────────────────────────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        self._credentials.refresh(Request())
        return {
            "Authorization": f"Bearer {self._credentials.token}",
            "Content-Type": "application/json",
        }

    def _api_get(self, path: str) -> requests.Response:
        return requests.get(f"{_API}/{path}", headers=self._auth_headers(), timeout=15)

    def _api_post(self, path: str, body: dict[str, Any]) -> requests.Response:
        return requests.post(
            f"{_API}/{path}",
            json=body,
            headers=self._auth_headers(),
            timeout=15,
        )

    def _api_patch(self, path: str, body: dict[str, Any]) -> requests.Response:
        return requests.patch(
            f"{_API}/{path}",
            json=body,
            headers=self._auth_headers(),
            timeout=15,
        )

    def _object_id(self, customer_id: str) -> str:
        # Object IDs may not contain hyphens in some regions — use underscores
        return f"{self.class_id}.{customer_id.replace('-', '_')}"

    def _loyalty_object_body(
        self,
        customer_id: str,
        customer_name: str,
        points: int,
        status_message: str,
        points_label: str = "Points",
        secondary_points: int | None = None,
        secondary_label: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "id": self._object_id(customer_id),
            "classId": self.class_id,
            "accountId": customer_id,
            "accountName": customer_name,
            "state": "ACTIVE",
            "loyaltyPoints": {
                "balance": {"string": str(points)},
                "label": points_label,
            },
            "textModulesData": [
                {"id": "status", "header": "Status", "body": status_message}
            ],
            "barcode": {
                "type": "QR_CODE",
                "value": customer_id,
                "alternateText": customer_id[:8],
            },
        }
        if secondary_points is not None and secondary_label:
            body["secondaryLoyaltyPoints"] = {
                "balance": {"string": str(secondary_points)},
                "label": secondary_label,
            }
        return body

    # ── public API ────────────────────────────────────────────────────────────

    def create_loyalty_class(self, program_name: str, issuer_name: str) -> dict:
        """Register the loyalty programme class with Google (run once)."""
        body = {
            "id": self.class_id,
            "issuerName": issuer_name,
            "programName": program_name,
            "reviewStatus": "UNDER_REVIEW",
        }
        resp = self._api_post("loyaltyClass", body)
        return resp.json()

    def ensure_loyalty_class(self, program_name: str, issuer_name: str) -> dict:
        """Ensure the loyalty class exists and return its payload."""
        resp = self._api_get(f"loyaltyClass/{self.class_id}")
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code not in (404,):
            resp.raise_for_status()

        body = {
            "id": self.class_id,
            "issuerName": issuer_name,
            "programName": program_name,
            "reviewStatus": "UNDER_REVIEW",
        }
        create_resp = self._api_post("loyaltyClass", body)
        # 409 = class already exists (race condition or created elsewhere)
        if create_resp.status_code in (200, 201, 409):
            check = self._api_get(f"loyaltyClass/{self.class_id}")
            check.raise_for_status()
            return check.json()
        create_resp.raise_for_status()
        return create_resp.json()

    def create_or_update_loyalty_object(
        self,
        customer_id: str,
        customer_name: str,
        points: int,
        status_message: str,
        points_label: str = "Points",
        secondary_points: int | None = None,
        secondary_label: str | None = None,
    ) -> dict:
        """Create the loyalty object if missing, otherwise patch it."""
        object_id = self._object_id(customer_id)
        obj = self._loyalty_object_body(
            customer_id, customer_name, points, status_message,
            points_label, secondary_points, secondary_label,
        )

        get_resp = self._api_get(f"loyaltyObject/{object_id}")
        if get_resp.status_code == 404:
            create_resp = self._api_post("loyaltyObject", obj)
            if create_resp.status_code in (200, 201, 409):
                return {"id": object_id, "created": create_resp.status_code in (200, 201)}
            create_resp.raise_for_status()
            return create_resp.json()
        if get_resp.status_code != 200:
            get_resp.raise_for_status()

        patch: dict[str, Any] = {
            "accountName": customer_name,
            "state": "ACTIVE",
            "loyaltyPoints": {"balance": {"string": str(points)}, "label": points_label},
            "textModulesData": [
                {"id": "status", "header": "Status", "body": status_message}
            ],
        }
        if secondary_points is not None and secondary_label:
            patch["secondaryLoyaltyPoints"] = {
                "balance": {"string": str(secondary_points)},
                "label": secondary_label,
            }
        patch_resp = self._api_patch(f"loyaltyObject/{object_id}", patch)
        patch_resp.raise_for_status()
        return patch_resp.json()

    def generate_save_link(
        self,
        customer_id: str,
    ) -> str:
        """Return a short save URL (thin JWT) for an existing loyalty object."""
        object_id = self._object_id(customer_id)
        claims = {
            "iss": self._sa_data["client_email"],
            "aud": "google",
            "origins": [],
            "typ": "savetowallet",
            "payload": {"loyaltyObjects": [{"id": object_id}]},
            "iat": int(time.time()),
        }
        token = pyjwt.encode(claims, self._sa_data["private_key"], algorithm="RS256")
        if len(token) > 1800:
            raise ValueError(
                "Generated Google Wallet JWT exceeds 1800 characters; check claims/origins."
            )
        return f"https://pay.google.com/gp/v/save/{token}"

    def update_loyalty_object(
        self,
        customer_id: str,
        points: int,
        status_message: str,
        points_label: str = "Points",
        secondary_points: int | None = None,
        secondary_label: str | None = None,
    ) -> dict:
        """PATCH an existing loyalty object to reflect new points/status."""
        object_id = self._object_id(customer_id)
        patch: dict[str, Any] = {
            "loyaltyPoints": {"balance": {"string": str(points)}, "label": points_label},
            "textModulesData": [
                {"id": "status", "header": "Status", "body": status_message}
            ],
        }
        if secondary_points is not None and secondary_label:
            patch["secondaryLoyaltyPoints"] = {
                "balance": {"string": str(secondary_points)},
                "label": secondary_label,
            }
        resp = self._api_patch(f"loyaltyObject/{object_id}", patch)
        if resp.status_code == 404:
            raise ValueError(
                "Google loyalty object not found. Generate the Google pass once before updates."
            )
        resp.raise_for_status()
        return resp.json()
