# LoyaltyMonitor

A Dockerized web application for managing digital loyalty cards for small shops (pizzerias, cafés, etc.).

## Features

- **Owner dashboard** — register customers, scan their QR code, add/subtract points per action, and cash out rewards.
- **Configurable loyalty rules** — all actions and rewards are defined in a single JSON file; no code changes needed.
- **Three digital wallets** — Google Wallet, Apple Wallet (.pkpass), and Samsung Wallet. Each card shows the live points balance and a human-readable status (e.g. *"3 pizza(s) left!"*).
- **Mobile / Desktop UI mode** — the admin can toggle between compact desktop and touch-friendly mobile layouts with one click.
- **Secure by default** — CSRF protection, bcrypt password hashing, session authentication via Flask-Login.

---

## Quick Start

```bash
# 1. Copy and edit the environment file
cp .env.example .env
# Edit .env: set SECRET_KEY, ADMIN_PASSWORD, and any wallet credentials

# 2. Build and run
docker compose up --build
```

Open **http://localhost:5000** and log in with the credentials from `.env`.

---

## Loyalty Configuration

Edit `config/pizzeria.json` (or point `LOYALTY_CONFIG_PATH` to another file):

```jsonc
{
  "program_name": "Pizzeria Loyalty",
   "phone_number_default_extension": "+33",
   "phone_number_group_size": 2,
  "actions": [
    { "id": "medium_pizza", "name": "Medium Pizza", "points": 1, "icon": "🍕" }
  ],
  "rewards": [
    {
      "id": "free_pizza",
      "name": "Free Pizza",
      "points_required": 10,
      "status_template": "{remaining} pizza(s) left!"
    }
  ]
}
```

`{remaining}` in `status_template` is replaced with `points_required − current_points`.
`phone_number_default_extension` is added when a phone number is entered without an international prefix.
`phone_number_group_size` controls how customer phone digits are grouped for display and defaults to `2`.

---

## Wallet Setup

### Google Wallet
1. Create an Issuer account at [pay.google.com/business/console](https://pay.google.com/business/console).
2. Enable the **Google Wallet API** in Google Cloud Console.
3. Create a service account, grant it the *Google Wallet Object Issuer* role, and download the JSON key.
4. Set in `.env`:
   ```
   GOOGLE_WALLET_ISSUER_ID=3388000000012345678
   GOOGLE_WALLET_CLASS_SUFFIX=loyalty_card
   GOOGLE_SERVICE_ACCOUNT_FILE=/app/wallet_data/google-service-account.json
   ```
5. Place the JSON key in `wallet_data/` (bind-mounted into the container).
6. On first use, call `GoogleWalletService.create_loyalty_class()` once (can be done from a Flask shell).

### Apple Wallet
1. Enrol in the **Apple Developer Program**.
2. Create a *Pass Type ID* (`pass.com.yourcompany.loyalty`).
3. Generate a pass certificate, export as `.p12`, and convert:
   ```bash
   openssl pkcs12 -in cert.p12 -nokeys -clcerts -out wallet_data/apple-cert.pem
   openssl pkcs12 -in cert.p12 -nocerts -nodes  -out wallet_data/apple-key.pem
   ```
4. Download the [WWDR G4 certificate](https://www.apple.com/certificateauthority/) and convert to PEM.
5. Set in `.env`:
   ```
   APPLE_PASS_TYPE_ID=pass.com.yourcompany.loyalty
   APPLE_TEAM_ID=ABCDE12345
   APPLE_CERT_PEM=/app/wallet_data/apple-cert.pem
   APPLE_KEY_PEM=/app/wallet_data/apple-key.pem
   APPLE_WWDR_PEM=/app/wallet_data/apple-wwdr.pem
   ```

### Samsung Wallet
1. Apply for the [Samsung Wallet Partner Programme](https://developer.samsung.com/wallet).
2. Create a loyalty card type in the Partner Portal.
3. Set in `.env`:
   ```
   SAMSUNG_SERVICE_ID=your-service-id
   SAMSUNG_API_KEY=your-api-key
   SAMSUNG_CARD_TYPE_ID=your-card-type-id
   ```

Wallet providers are **optional** — the app runs normally without any credentials; the wallet buttons simply report that the provider is not configured.

---

## Owner Workflow

1. **Register** — go to *Register* and optionally enter name / email.  
   The app generates a unique UUID and QR code for the customer.
2. **Show card** — on the customer detail page, tap *Add to [Wallet]* so the customer can save their card.
3. **Next visit** — tap *Scan*, point the camera at the customer's wallet card QR code.  
   The customer detail page opens automatically.
4. **Add points** — tap **+** next to each purchased item; tap **−** to undo.
5. **Cash out** — when the customer has enough points the *Cash Out* button appears. Tap it to redeem.

---

## Project Structure

```
LoyaltyMonitor/
├── app/
│   ├── __init__.py          # Flask application factory
│   ├── extensions.py        # SQLAlchemy, LoginManager, CSRF
│   ├── models.py            # Admin, Customer, WalletCard, PointTransaction
│   ├── loyalty.py           # Config loader + status-message helpers
│   ├── routes/
│   │   ├── auth.py          # /login, /logout
│   │   ├── admin.py         # /admin/settings, toggle-display, change-password
│   │   ├── customer.py      # /customers/, /customers/<id>, add-points, cashout, qr
│   │   └── wallet.py        # /wallet/google|apple|samsung/<customer_id>
│   ├── wallet/
│   │   ├── google_wallet.py
│   │   ├── apple_wallet.py
│   │   └── samsung_wallet.py
│   ├── templates/
│   └── static/
├── config/
│   └── pizzeria.json        # Loyalty configuration (swap for your own)
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh
├── requirements.txt
└── .env.example
```
