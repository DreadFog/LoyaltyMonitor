"""Apple Wallet (.pkpass) integration.

Required environment variables
--------------------------------
APPLE_PASS_TYPE_ID   — e.g. pass.com.yourcompany.loyalty
APPLE_TEAM_ID        — 10-character Apple Developer Team ID
APPLE_CERT_PEM       — Path to (or PEM content of) your Pass Type certificate
APPLE_KEY_PEM        — Path to (or PEM content of) the corresponding private key
APPLE_WWDR_PEM       — Path to (or PEM content of) the Apple WWDR intermediate cert
                       Download from https://www.apple.com/certificateauthority/

Setup steps
-----------
1. Enrol in the Apple Developer Program.
2. In the Certificates section, create a Pass Type ID and generate a certificate.
3. Export the .p12 file and convert:
       openssl pkcs12 -in cert.p12 -nokeys -clcerts -out apple-cert.pem
       openssl pkcs12 -in cert.p12 -nocerts -nodes  -out apple-key.pem
4. Download the WWDR G4 certificate from Apple and convert if needed:
       openssl x509 -inform DER -in AppleWWDRCAG4.cer -out apple-wwdr.pem
5. Set the env vars to the file paths.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization.pkcs7 import (
    PKCS7Options,
    PKCS7SignatureBuilder,
)


class AppleWalletService:
    def __init__(
        self,
        pass_type_id: str,
        team_id: str,
        cert_pem: str,
        key_pem: str,
        wwdr_pem: str,
    ) -> None:
        self.pass_type_id = pass_type_id
        self.team_id = team_id
        self._cert_pem = cert_pem
        self._key_pem = key_pem
        self._wwdr_pem = wwdr_pem

    # ── public API ────────────────────────────────────────────────────────────

    def create_pass(
        self,
        customer_id: str,
        customer_name: str,
        points: int,
        status_message: str,
        program_name: str,
        organization_name: str,
    ) -> io.BytesIO:
        """Build and return an in-memory .pkpass ZIP buffer."""
        pass_dict = {
            "formatVersion": 1,
            "passTypeIdentifier": self.pass_type_id,
            "serialNumber": customer_id,
            "teamIdentifier": self.team_id,
            "organizationName": organization_name,
            "description": program_name,
            "storeCard": {
                "primaryFields": [
                    {"key": "points", "label": "Points", "value": points}
                ],
                "secondaryFields": [
                    {"key": "status", "label": "Status", "value": status_message}
                ],
                "auxiliaryFields": [
                    {"key": "member", "label": "Member", "value": customer_name}
                ],
                "backFields": [
                    {"key": "customer_id", "label": "Customer ID", "value": customer_id}
                ],
            },
            "barcode": {
                "message": customer_id,
                "format": "PKBarcodeFormatQR",
                "messageEncoding": "iso-8859-1",
                "altText": customer_id[:8],
            },
            "foregroundColor": "rgb(255, 255, 255)",
            "backgroundColor": "rgb(22, 40, 130)",
            "labelColor": "rgb(200, 210, 255)",
        }

        pass_json: bytes = json.dumps(pass_dict, ensure_ascii=False).encode("utf-8")

        manifest = {"pass.json": hashlib.sha1(pass_json).hexdigest()}
        manifest_json: bytes = json.dumps(manifest).encode("utf-8")

        signature: bytes = self._sign(manifest_json)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("pass.json", pass_json)
            zf.writestr("manifest.json", manifest_json)
            zf.writestr("signature", signature)
        buf.seek(0)
        return buf

    # ── internal ──────────────────────────────────────────────────────────────

    def _sign(self, data: bytes) -> bytes:
        """Return a DER-encoded detached PKCS#7 / CMS signature."""
        _enc = lambda s: s.encode("utf-8") if isinstance(s, str) else s

        cert = x509.load_pem_x509_certificate(_enc(self._cert_pem))
        key = serialization.load_pem_private_key(_enc(self._key_pem), password=None)
        wwdr = x509.load_pem_x509_certificate(_enc(self._wwdr_pem))

        return (
            PKCS7SignatureBuilder()
            .set_data(data)
            .add_signer(cert, key, hashes.SHA256())
            .add_certificate(wwdr)
            .sign(serialization.Encoding.DER, [PKCS7Options.DetachedSignature])
        )
