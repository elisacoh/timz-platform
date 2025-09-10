from uuid import uuid4

import jwt
import pytest

from timz_app.core.jwt import create_access_token, verify_access_token


def test_access_happy():
    """Sign + verify OK"""
    user_id = str(uuid4())
    roles = ["client", "pro"]

    token = create_access_token(sub=user_id, roles=roles, ttl_minutes=2)
    payload = verify_access_token(token)

    assert payload["sub"] == user_id
    # order not guaranteed
    assert set(payload["roles"]) == set(roles)
    assert payload["typ"] == "access"
    assert isinstance(payload["iat"], int)
    assert isinstance(payload["exp"], int)


def test_access_expired():
    """Token déjà expiré -> ExpiredSignatureError"""
    token = create_access_token(sub="u-expired", roles=[], ttl_minutes=-1)

    with pytest.raises(jwt.ExpiredSignatureError):
        verify_access_token(token)


def test_access_tampered_signature():
    """Token modifié (signature corrompue) -> InvalidSignatureError/InvalidTokenError"""
    token = create_access_token(sub="u", roles=[])
    parts = token.split(".")
    assert len(parts) == 3

    header, payload, signature = parts
    # flip la 1ère lettre de la signature tout en gardant un base64url valide
    new_first = "A" if signature[0] != "A" else "B"
    bad_sig = new_first + signature[1:]
    tampered = ".".join([header, payload, bad_sig])

    with pytest.raises((jwt.InvalidSignatureError, jwt.InvalidTokenError)):
        verify_access_token(tampered)
