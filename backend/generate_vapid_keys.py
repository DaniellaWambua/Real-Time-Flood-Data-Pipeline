"""
Makes the key pair Web Push needs (notify.py), once per deployment. Prints three lines to add to
backend/.env; the private key must stay secret, the public one is handed to browsers.
Run from the backend/ directory: python generate_vapid_keys.py
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

key = ec.generate_private_key(ec.SECP256R1())
private = key.private_numbers().private_value.to_bytes(32, "big")
public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


print(f"VAPID_PUBLIC_KEY={b64(public)}")
print(f"VAPID_PRIVATE_KEY={b64(private)}")
print("VAPID_SUBJECT=mailto:you@example.org   # an address the push services can contact")
