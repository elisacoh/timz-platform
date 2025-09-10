# timz_app/dependencies/firebase.py
from fastapi import HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from timz_app.core.config import settings


def verify_firebase_id_token_or_401(id_token_str: str) -> dict:
    project_id = settings.FIREBASE_PROJECT_ID
    if not project_id:
        raise HTTPException(status_code=500, detail="FIREBASE_PROJECT_ID missing")
    try:
        claims = google_id_token.verify_firebase_token(
            id_token_str.strip(),
            google_requests.Request(),
            audience=project_id,
        )
    except ValueError as e:
        # <- ici tu verras “Token expired”, “Wrong reserved ‘aud’”, “Not a Firebase token”, etc.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Firebase ID token: {e}",
        )
    if not claims or claims.get("aud") != project_id:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid Firebase audience; aud={claims.get('aud')}, expected={project_id}",
        )
    return claims
