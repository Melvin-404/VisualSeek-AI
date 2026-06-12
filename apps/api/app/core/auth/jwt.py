import time
import urllib.request
import json
import logging
from typing import Dict, Any, Optional
from jose import jwt, jwk
from jose.exceptions import JWTError, JWKError
from app.core.config import settings

logger = logging.getLogger("visionquery.auth")

class JWKSKeyManager:
    """Manages Keycloak JWKS public keys with in-memory caching."""
    def __init__(self):
        self.jwks: Optional[Dict[str, Any]] = None
        self.last_fetched: float = 0.0
        self.cache_ttl: float = 3600.0  # 1 hour

    def fetch_jwks(self) -> Dict[str, Any]:
        now = time.time()
        if self.jwks and (now - self.last_fetched) < self.cache_ttl:
            return self.jwks

        jwks_url = f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/certs"
        try:
            logger.info("Fetching JWKS from Keycloak: %s", jwks_url)
            with urllib.request.urlopen(jwks_url, timeout=5) as response:
                self.jwks = json.loads(response.read().decode("utf-8"))
                self.last_fetched = now
                return self.jwks
        except Exception as e:
            logger.error("Failed to fetch JWKS from Keycloak: %s", str(e))
            if self.jwks:
                logger.warning("Using expired cached JWKS due to fetch failure.")
                return self.jwks
            raise JWTError("Could not retrieve JWKS keys from provider") from e

    def get_public_key(self, kid: str) -> Any:
        jwks = self.fetch_jwks()
        for key_data in jwks.get("keys", []):
            if key_data.get("kid") == kid:
                return jwk.construct(key_data)
        raise JWKError(f"Public key for kid '{kid}' not found in JWKS")

jwks_manager = JWKSKeyManager()

def decode_and_verify_token(token: str) -> Dict[str, Any]:
    """Decodes a JWT and verifies its signature using RS256 (Keycloak) or HS256 (local).
    
    Args:
        token: JWT string to verify.
        
    Returns:
        dict: The decoded token payload.
        
    Raises:
        JWTError: If signature verification or decoding fails.
    """
    try:
        # Get token header to inspect algorithm and kid
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")
        
        if alg == "RS256":
            kid = header.get("kid")
            if not kid:
                raise JWTError("RS256 token is missing 'kid' header parameter")
            public_key = jwks_manager.get_public_key(kid)
            # jose requires the jwk construct key or dict
            payload = jwt.decode(
                token,
                public_key.to_pem().decode("utf-8"),
                algorithms=["RS256"],
                audience=settings.KEYCLOAK_CLIENT_ID,
                options={"verify_aud": True}
            )
            return payload
        elif alg == "HS256":
            # Fallback/local token verification
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=["HS256"]
            )
            return payload
        else:
            raise JWTError(f"Unsupported algorithm '{alg}'")
    except (JWTError, JWKError) as e:
        logger.warning("Token verification failed: %s", str(e))
        raise JWTError("Signature verification failed or token is invalid") from e
