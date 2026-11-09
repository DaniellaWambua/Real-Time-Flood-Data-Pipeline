"""Test-only settings, so the suite runs without a real backend/.env."""
import os

for name, value in {
    "DB_PASSWORD": "test-db-password",
    "SECRET_KEY": "test-secret-key",
    "INTERNAL_API_TOKEN": "test-internal-token",
}.items():
    os.environ.setdefault(name, value)
