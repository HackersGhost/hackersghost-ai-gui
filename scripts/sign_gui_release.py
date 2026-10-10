"""Publisher-only offline signing helper. Does not upload or generate signing keys."""

import argparse
import base64
import getpass
import hashlib
import json
from pathlib import Path
import sys
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hackersghost_ai.core.update_service import (
    PACKAGE_LIMIT, PRODUCT, PUBLIC_KEY, Release, validate_package, verify_manifest, version_tuple,
)


def signed_manifest(package, version, private_key, days=30):
    version_tuple(version)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("An Ed25519 signing key is required.")
    if private_key.public_key().public_bytes_raw().hex() != PUBLIC_KEY:
        raise ValueError("This key does not match the trusted publisher key in the GUI.")
    if not 1 <= days <= 30:
        raise ValueError("Expiry must be between 1 and 30 days.")
    release = Release(version, hashlib.sha256(package).hexdigest(), int(time.time()) + days * 86400, b"")
    validate_package(package, release)
    payload = json.dumps({
        "schema": 1, "product": PRODUCT, "version": version, "url": release.url,
        "sha256": release.sha256, "expires": release.expires,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    envelope = json.dumps({"payload": base64.b64encode(payload).decode("ascii"),
                           "signature": base64.b64encode(private_key.sign(payload)).decode("ascii")}).encode("utf-8")
    verify_manifest(envelope, PUBLIC_KEY)
    return envelope


def main():
    parser = argparse.ArgumentParser(description="Sign a GUI release with the existing offline publisher key")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    with args.private_key.open("rb") as handle:
        raw = handle.read(65537)
    if len(raw) > 65536:
        raise ValueError("Unsupported key file size.")
    if raw.startswith(b"-----BEGIN"):
        password = getpass.getpass("Signing key password: ").encode() if b"ENCRYPTED" in raw else None
        key = serialization.load_pem_private_key(raw, password=password)
    else:
        key_bytes = bytes.fromhex(raw.decode("ascii").strip()) if len(raw.strip()) == 64 else raw
        key = Ed25519PrivateKey.from_private_bytes(key_bytes)
    with args.archive.open("rb") as handle:
        package = handle.read(PACKAGE_LIMIT + 1)
    envelope = signed_manifest(package, args.version, key, args.days)
    with args.output.open("xb") as handle:
        handle.write(envelope)
    print("Signed GUI manifest created. No files were uploaded.")


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt):
        print("Signing stopped. Check the key, archive, version, expiry and output path. Existing output is never overwritten.", file=sys.stderr)
        sys.exit(1)
