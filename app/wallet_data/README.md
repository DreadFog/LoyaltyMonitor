# Wallet Credentials Setup

This directory holds sensitive wallet provider credentials. Files here are **NOT committed to Git** (see .gitignore).

## Google Wallet

### Setup Steps

1. **Create a Google Cloud Project**
   - Go to [console.cloud.google.com](https://console.cloud.google.com)
   - Create a new project (e.g., "LoyaltyMonitor")

2. **Enable the Google Wallet API**
   - In the Cloud Console, search for "Google Wallet API"
   - Enable it for your project

3. **Create an Issuer Account**
   - Go to [pay.google.com/business/console](https://pay.google.com/business/console)
   - Sign in with your Google account
   - Click "Get Started" and create an Issuer account
   - Note your **Issuer ID** (10–19 digits) — add to `.env` as `GOOGLE_WALLET_ISSUER_ID`

4. **Create a Service Account**
   - Back in the Cloud Console, go to **IAM & Admin → Service Accounts**
   - Click "Create Service Account"
   - Name: e.g., `google-wallet-issuer`
   - Click "Create and Continue"
   - Grant the role: **Cloud Wallet Partner** or look for **Google Wallet Object Issuer** if available
   - Click "Continue" then "Done"

5. **Create and Download the JSON Key**
   - On the Service Account page, go to **Keys** tab
   - Click "Add Key" → "Create new key"
   - Choose **JSON**
   - Save the file locally as `google-service-account.json`
   - **Keep this file safe — it's your private key!**

6. **Share with Google Wallet**
   - Copy the `client_email` from the JSON file
   - In the Google Wallet console, go to **Issuers** → **Users**
   - Invite the service account email with role **Editor** or higher

7. **Place the File**
   - Copy your `google-service-account.json` to this directory:
     ```bash
     cp ~/Downloads/google-service-account.json app/wallet_data/
     ```
   - Update `.env`:
     ```
     GOOGLE_WALLET_ISSUER_ID=1234567890123456789
     GOOGLE_SERVICE_ACCOUNT_FILE=/app/wallet_data/google-service-account.json
     GOOGLE_WALLET_CLASS_SUFFIX=loyalty_card
     ```

8. **Create the Loyalty Class** (one-time)
   - On first deployment, run:
     ```bash
   docker exec loyaltymonitor-web flask shell
     >>> from app import create_app
     >>> from app.wallet import get_google_wallet_service
     >>> app = create_app()
     >>> with app.app_context():
     ...     gw = get_google_wallet_service()
     ...     gw.create_loyalty_class("Pizzeria Loyalty", "Pizzeria Roma")
     ```
   - Or use the Python REPL to call `GoogleWalletService.create_loyalty_class()`

---

## Apple Wallet

### Setup Steps

1. **Enrol in Apple Developer Program** (requires paid membership)
   - Visit [developer.apple.com](https://developer.apple.com)

2. **Create a Pass Type ID**
   - Go to **Certificates, Identifiers & Profiles** → **Identifiers**
   - Click "+" and select "Pass Type IDs"
   - Register (e.g., `pass.com.yourcompany.loyalty`)
   - Note this ID as `APPLE_PASS_TYPE_ID` in `.env`

3. **Create a Pass Certificate**
   - In **Certificates**, click "+" → "Pass Type ID Certificate"
   - Follow the CSR process (you'll upload a certificate signing request)
   - Download the `.cer` file

4. **Convert Certificate to PEM**
   ```bash
   # Convert .cer to .pem
   openssl x509 -inform DER -in YourPassCertificate.cer -out apple-cert.pem

   # You'll also need the private key from your CSR:
   # If you created a .p12 file instead:
   openssl pkcs12 -in cert.p12 -nokeys -clcerts -out apple-cert.pem
   openssl pkcs12 -in cert.p12 -nocerts -nodes -out apple-key.pem
   ```

5. **Download WWDR Certificate**
   - Go to [apple.com/certificateauthority](https://www.apple.com/certificateauthority)
   - Download "AppleWWDRCAG4.cer" (G4 is current)
   - Convert:
     ```bash
     openssl x509 -inform DER -in AppleWWDRCAG4.cer -out apple-wwdr.pem
     ```

6. **Place Files**
   ```bash
   cp apple-cert.pem apple-key.pem apple-wwdr.pem app/wallet_data/
   ```

7. **Update `.env`**
   ```
   APPLE_PASS_TYPE_ID=pass.com.yourcompany.loyalty
   APPLE_TEAM_ID=ABCDE12345
   APPLE_CERT_PEM=/app/wallet_data/apple-cert.pem
   APPLE_KEY_PEM=/app/wallet_data/apple-key.pem
   APPLE_WWDR_PEM=/app/wallet_data/apple-wwdr.pem
   ```

---

## Samsung Wallet

### Setup Steps

1. **Apply for Partner Program**
   - Visit [developer.samsung.com/wallet](https://developer.samsung.com/wallet)
   - Apply for the Loyalty Partner Programme
   - Wait for approval (typically 1–2 weeks)

2. **Create a Loyalty Card Type**
   - In the Partner Portal, create a new loyalty card type
   - Note the **Card Type ID**

3. **Generate API Credentials**
   - In Partner Portal → **API Keys**
   - Generate **Service ID** and **API Key**

4. **Update `.env`**
   ```
   SAMSUNG_SERVICE_ID=your-service-id
   SAMSUNG_API_KEY=your-api-key
   SAMSUNG_CARD_TYPE_ID=your-card-type-id
   ```

---

## Notes

- **All wallet credentials are optional.** The app runs fine without any of them.
- If a wallet provider is not configured, the corresponding buttons on the customer detail page will show a "not configured" message.
- **Never commit these files to Git** — they're in `.gitignore` for security.
- For Docker, mount `wallet_data` as a volume to persist credentials across container restarts.
