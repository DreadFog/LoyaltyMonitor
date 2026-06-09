#!/bin/sh
set -e

echo "==> LoyaltyMonitor starting..."

# Wait for PostgreSQL if DATABASE_URL points to postgres
if echo "${DATABASE_URL:-}" | grep -q "postgresql"; then
    echo "==> Waiting for PostgreSQL..."
    python - << 'PYEOF'
import time, os, sys
try:
    import psycopg2
    db_url = os.environ["DATABASE_URL"]
    for i in range(30):
        try:
            conn = psycopg2.connect(db_url)
            conn.close()
            print("==> PostgreSQL is ready!")
            break
        except Exception as e:
            if i == 29:
                print(f"ERROR: Could not connect to PostgreSQL: {e}", file=sys.stderr)
                sys.exit(1)
            print(f"    Waiting for PostgreSQL... ({i+1}/30)")
            time.sleep(1)
except ImportError:
    print("psycopg2 not found, skipping wait")
PYEOF
fi

# Initialise the database schema and seed the admin user
echo "==> Initialising database..."
python - << 'PYEOF'
import os, sys
sys.path.insert(0, "/app")
from app import create_app
from app.extensions import db
from app.models import Admin

app = create_app()
with app.app_context():
    db.create_all()

    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_password:
        print("WARNING: ADMIN_PASSWORD is not set — defaulting to 'changeme123'", file=sys.stderr)
        admin_password = "changeme123"

    if not Admin.query.filter_by(username=admin_username).first():
        admin = Admin(username=admin_username)
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.commit()
        print(f"==> Admin user '{admin_username}' created.")
    else:
        print(f"==> Admin user '{admin_username}' already exists.")

print("==> Database ready.")
PYEOF

echo "==> Starting Gunicorn..."
exec gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 2 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile - \
    "app:create_app()"
