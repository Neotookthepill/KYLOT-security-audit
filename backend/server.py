from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import io
import csv
import uuid
import logging
import secrets
import asyncio
from datetime import datetime, timezone, timedelta, date
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

import bcrypt
import hmac as _hmac
import hashlib
import httpx
import stripe
import re
import ipaddress
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse
import jwt
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Query, BackgroundTasks, Header, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
import base64
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator
from zoneinfo import ZoneInfo


# ---------------- Setup ----------------

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

_RUNTIME_ENV = (os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "development").lower()
_IS_PRODUCTION = _RUNTIME_ENV in ("production", "prod")
_DOCS_REQUESTED = (os.environ.get("EXPOSE_API_DOCS") or ("false" if _IS_PRODUCTION else "true")).lower() in ("1", "true", "yes")
_DOCS_ENABLED = _DOCS_REQUESTED and not _IS_PRODUCTION
app = FastAPI(
    title="Pylot API",
    docs_url="/docs" if _DOCS_ENABLED else None,
    redoc_url="/redoc" if _DOCS_ENABLED else None,
    openapi_url="/openapi.json" if _DOCS_ENABLED else None,
)
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("pylot")


def _cors_origins() -> List[str]:
    """Return explicit browser origins; production fails closed by default."""
    environment = (os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "development").lower()
    raw = (os.environ.get("CORS_ORIGINS") or "").strip()
    if raw == "*":
        if environment in ("production", "prod"):
            raise RuntimeError("CORS_ORIGINS='*' est interdit en production")
        raw = "http://localhost:3000,http://127.0.0.1:3000"
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    # Always include the FRONTEND_URL (from env) if not present
    fu = (os.environ.get("FRONTEND_URL") or "").strip().rstrip("/")
    if fu and fu not in origins:
        origins.append(fu)
    if environment not in ("production", "prod"):
        for loc in ("http://localhost:3000", "http://127.0.0.1:3000"):
            if loc not in origins:
                origins.append(loc)
    return origins


# ---------------- Utils ----------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validated_month(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
        raise HTTPException(status_code=400, detail="Mois invalide (YYYY-MM)")
    try:
        datetime.strptime(value, "%Y-%m")
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Mois invalide (YYYY-MM)")
    return value


MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
MAX_UPLOAD_FILES = int(os.environ.get("MAX_UPLOAD_FILES", "5"))
MAX_PDF_PAGES = int(os.environ.get("MAX_PDF_PAGES", "10"))
MAX_REQUEST_BYTES = int(os.environ.get("MAX_REQUEST_BYTES", str(20 * 1024 * 1024)))
MAX_INLINE_IMAGE_BYTES = int(os.environ.get("MAX_INLINE_IMAGE_BYTES", str(4 * 1024 * 1024)))
MAX_PHOTOS_PER_ENTITY = int(os.environ.get("MAX_PHOTOS_PER_ENTITY", "20"))
MAX_IMPORT_ROWS = int(os.environ.get("MAX_IMPORT_ROWS", "5000"))
MAX_IMPORT_COLUMNS = int(os.environ.get("MAX_IMPORT_COLUMNS", "100"))
MAX_IMPORT_CELL_CHARS = int(os.environ.get("MAX_IMPORT_CELL_CHARS", "10000"))
IMPORT_BATCH_TTL_MINUTES = int(os.environ.get("IMPORT_BATCH_TTL_MINUTES", "30"))


def _external_ai_enabled() -> bool:
    default = "false" if _IS_PRODUCTION else "true"
    return (os.environ.get("ALLOW_EXTERNAL_AI") or default).strip().lower() in ("1", "true", "yes")


def _require_external_ai_enabled() -> None:
    """Fail closed before customer text or files can be sent to an external AI provider."""
    if not _external_ai_enabled():
        raise HTTPException(status_code=503, detail="Fonctions IA externes désactivées par la configuration de sécurité")


_DATA_IMAGE_RE = re.compile(
    r"^data:image/(jpeg|jpg|png|webp);base64,([A-Za-z0-9+/=\r\n]+)$",
    re.IGNORECASE,
)


def _validated_photo_source(value: Any) -> str:
    """Accept only bounded HTTPS images or bounded, well-formed image data URIs."""
    if not isinstance(value, str):
        raise HTTPException(status_code=422, detail="Photo invalide")
    source = value.strip()
    if source.startswith("https://"):
        if len(source) > 2048:
            raise HTTPException(status_code=413, detail="URL de photo trop longue")
        parsed = urlparse(source)
        if not parsed.hostname or parsed.username or parsed.password:
            raise HTTPException(status_code=422, detail="URL de photo invalide")
        allowed_hosts = {
            host.strip().lower() for host in (os.environ.get("PHOTO_ALLOWED_HOSTS") or "").split(",") if host.strip()
        }
        if (parsed.hostname or "").lower() not in allowed_hosts:
            raise HTTPException(status_code=422, detail="Hôte de photo non autorisé")
        return source
    match = _DATA_IMAGE_RE.fullmatch(source)
    if not match:
        raise HTTPException(status_code=422, detail="Format de photo non autorisé")
    try:
        decoded = base64.b64decode(match.group(2), validate=True)
    except Exception:
        raise HTTPException(status_code=422, detail="Photo base64 invalide")
    if not decoded:
        raise HTTPException(status_code=422, detail="Photo vide")
    if len(decoded) > MAX_INLINE_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Photo trop volumineuse (max {MAX_INLINE_IMAGE_BYTES // (1024 * 1024)} Mo)",
        )
    declared = match.group(1).lower()
    actual = (
        "png" if decoded.startswith(b"\x89PNG\r\n\x1a\n")
        else "jpeg" if decoded.startswith(b"\xff\xd8\xff")
        else "webp" if len(decoded) >= 12 and decoded.startswith(b"RIFF") and decoded[8:12] == b"WEBP"
        else None
    )
    if not actual or (declared in ("jpeg", "jpg") and actual != "jpeg") or (declared not in ("jpeg", "jpg") and actual != declared):
        raise HTTPException(status_code=422, detail="Le contenu de la photo ne correspond pas au format déclaré")
    return source


def _validated_photo_entries(photos: Any, *, max_count: Optional[int] = None) -> List[Union[str, dict]]:
    """Validate persisted photo sources and discard attacker-controlled metadata keys."""
    if photos is None:
        return []
    if not isinstance(photos, list):
        raise HTTPException(status_code=422, detail="Liste de photos invalide")
    limit = max_count if max_count is not None else MAX_PHOTOS_PER_ENTITY
    if len(photos) > limit:
        raise HTTPException(status_code=413, detail=f"Trop de photos (max {limit})")
    safe: List[Union[str, dict]] = []
    allowed_metadata = {
        "taken_at", "created_at", "added_by", "added_by_id", "by_completion",
        "lat", "lng", "accuracy", "latitude", "longitude", "gps", "day",
    }
    for photo in photos:
        raw_source = photo if isinstance(photo, str) else (photo.get("src") if isinstance(photo, dict) else None)
        source = _validated_photo_source(raw_source)
        if isinstance(photo, dict):
            clean = {k: v for k, v in photo.items() if k in allowed_metadata}
            for key, low, high in (
                ("lat", -90, 90), ("latitude", -90, 90),
                ("lng", -180, 180), ("longitude", -180, 180),
                ("accuracy", 0, 100_000),
            ):
                if key in clean and (not isinstance(clean[key], (int, float)) or not low <= clean[key] <= high):
                    clean.pop(key, None)
            if "gps" in clean:
                gps = clean["gps"]
                if not isinstance(gps, dict):
                    clean.pop("gps", None)
                else:
                    clean["gps"] = {
                        k: v for k, v in gps.items()
                        if k in {"lat", "lng", "accuracy"} and isinstance(v, (int, float))
                    }
            for key in ("taken_at", "created_at", "added_by", "added_by_id", "day"):
                if key in clean and not isinstance(clean[key], str):
                    clean.pop(key, None)
                elif key in clean:
                    clean[key] = clean[key][:200]
            if "by_completion" in clean:
                clean["by_completion"] = bool(clean["by_completion"])
            clean["src"] = source
            safe.append(clean)
        else:
            safe.append(source)
    return safe


async def _read_upload_limited(file: UploadFile) -> bytes:
    """Read at most the configured upload limit plus one sentinel byte."""
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Fichier trop volumineux (max {MAX_UPLOAD_BYTES // (1024 * 1024)} Mo)")
    if not raw:
        raise HTTPException(status_code=400, detail="Fichier vide")
    return raw


def _safe_frontend_url(requested: str, *, keep_path: bool = False) -> str:
    """Validate Stripe return URLs against server-controlled origins."""
    environment = (os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "development").lower()
    configured = (os.environ.get("FRONTEND_URL") or "").strip().rstrip("/")
    extra = [x.strip().rstrip("/") for x in (os.environ.get("STRIPE_RETURN_ORIGINS") or "").split(",") if x.strip()]
    allowed = set(extra)
    if configured:
        allowed.add(configured)
    if environment not in ("production", "prod"):
        allowed.update({"http://localhost:3000", "http://127.0.0.1:3000"})

    parsed = urlparse((requested or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="URL de retour invalide")
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if origin not in allowed:
        raise HTTPException(status_code=400, detail="Origine de retour non autorisée")
    if keep_path:
        path = parsed.path if parsed.path.startswith("/") else "/"
        return f"{origin}{path}"
    return origin

def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode("utf-8"), h.encode("utf-8"))
    except Exception:
        return False

# Used when an email does not exist so the login path still performs one
# bcrypt verification and does not expose account existence through timing.
_DUMMY_PASSWORD_HASH = hash_password("kylot-dummy-password-never-used-for-login")

def create_access_token(user_id: str, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id, "email": email, "type": "access",
        # iat is used server-side to invalidate all tokens issued before a logout
        # (compared against users.token_epoch).
        "iat": int(now.timestamp()),
        "iat_ms": int(now.timestamp() * 1000),
        "exp": now + timedelta(minutes=60 * 12),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def set_auth_cookie(response: Response, access: str):
    environment = (os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "development").lower()
    secure = (os.environ.get("COOKIE_SECURE") or ("true" if environment in ("production", "prod") else "false")).lower() in ("1", "true", "yes")
    samesite = (os.environ.get("COOKIE_SAMESITE") or "lax").lower()
    if samesite not in ("lax", "strict", "none"):
        raise RuntimeError("COOKIE_SAMESITE doit être lax, strict ou none")
    if samesite == "none" and not secure:
        raise RuntimeError("COOKIE_SAMESITE=none exige COOKIE_SECURE=true")
    if environment in ("production", "prod") and samesite == "none":
        raise RuntimeError("COOKIE_SAMESITE=none est interdit sans protection CSRF dédiée")
    response.set_cookie("access_token", access, httponly=True, secure=secure, samesite=samesite, max_age=60*60*12, path="/")


def _auth_response(user: dict, token: str) -> dict:
    """Return the browser-safe login payload; token JSON is legacy opt-in only."""
    payload = {"user": public_user(user)}
    environment = (os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "development").lower()
    legacy_enabled = (os.environ.get("ALLOW_TOKEN_RESPONSE") or "false").strip().lower() in ("1", "true", "yes")
    if legacy_enabled and environment not in ("production", "prod"):
        payload["token"] = token
    return payload

async def _apply_overtime_eligibility_gate(u: dict) -> None:
    """iter94/121/126 : verrouille strictement l'accès aux heures sup pour un technicien.
    Un technicien n'a `overtime.declare/view/edit` que si son team_member (match
    par name OU email dans la même société) porte `overtime_enabled = True`.
    iter121 : matching insensible à la casse ET aux accents ("Sébastien" ↔ "Sebastien").
    iter126 : matching insensible aussi aux différences de nom court/long — l'utilisateur
    `users.name = "Sébastien Vasseur"` matche `team_members.name = "Sébastien"` (et vice-versa)
    via comparaison sur le prénom OU sur inclusion mot-à-mot.
    Sinon les permissions overtime sont neutralisées → le menu disparaît côté
    frontend (Layout) ET tous les endpoints /api/overtime* renvoient 403.
    """
    if not u or u.get("role") != "technicien":
        return
    import unicodedata as _ud
    def _norm(s):
        s = (s or "").strip()
        if not s:
            return ""
        return _ud.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower()
    def _tokens(s):
        return [t for t in _norm(s).split() if t]
    company = u.get("company_id") or DEFAULT_COMPANY_ID
    my_name_n = _norm(u.get("name"))
    my_tokens = _tokens(u.get("name"))
    my_first = my_tokens[0] if my_tokens else ""
    my_email = (u.get("email") or "").strip().lower()
    eligible = False
    if my_name_n or my_email:
        # iter121 : on charge TOUS les techniciens de la société puis on compare
        # côté Python après normalisation (évite les caprices d'accents Mongo).
        techs = await db.team_members.find(
            {"company_id": company, "type": "technicien"},
            {"_id": 0, "name": 1, "email": 1, "overtime_enabled": 1},
        ).to_list(500)
        for t in techs:
            t_name_n = _norm(t.get("name"))
            t_tokens = _tokens(t.get("name"))
            t_first = t_tokens[0] if t_tokens else ""
            t_email = (t.get("email") or "").strip().lower()
            # iter126 : 4 stratégies de match — full string, prénom identique, tokens inclus, email.
            match_full = my_name_n and t_name_n and my_name_n == t_name_n
            match_email = my_email and t_email and t_email == my_email
            if match_full or match_email:
                if t.get("overtime_enabled"):
                    eligible = True
                break
    if not eligible:
        perms = dict(u.get("permissions") or {})
        ot = dict(perms.get("overtime") or {})
        ot.update({"declare": False, "view": "none", "edit": False})
        perms["overtime"] = ot
        u["permissions"] = perms


# iter198 — Cache in-memory du dernier reconcile par company_id (rate-limit 1h).
_AUTH_ME_RECONCILE_CACHE: dict = {}


def public_user(u: dict) -> dict:
    # iter48: fusionne les permissions par défaut du rôle avec celles sauvegardées.
    # Cela garantit que les nouvelles ressources (ex: photos) apparaissent
    # dans /auth/me pour les utilisateurs créés avant leur ajout.
    saved = u.get("permissions") or {}
    defaults = get_default_permissions(u.get("role", ""))
    merged = {**defaults, **{k: v for k, v in saved.items() if v is not None}}
    for res, actions in defaults.items():
        if isinstance(actions, dict) and isinstance(merged.get(res), dict):
            merged[res] = {**actions, **{k: v for k, v in merged[res].items() if v is not None}}
    return {
        "id": u["id"],
        "email": u["email"],
        "name": u.get("name", ""),
        "role": u.get("role", "commercial"),
        "is_active": u.get("is_active", True),
        "company_id": u.get("company_id") or DEFAULT_COMPANY_ID,
        "permissions": merged,
        # iter183 — Onboarding « première utilisation » persisté server-side.
        # Empêche la boîte de dialogue de se rouvrir à chaque reconnexion / autre navigateur.
        "onboarding_done": bool(u.get("onboarding_done")),
    }


async def get_current_user(request: Request) -> dict:
    cookie_token = request.cookies.get("access_token")
    token = cookie_token
    if cookie_token and request.method.upper() not in ("GET", "HEAD", "OPTIONS"):
        origin = (request.headers.get("origin") or "").strip().rstrip("/")
        fetch_site = (request.headers.get("sec-fetch-site") or "").strip().lower()
        allowed_origins = {value.rstrip("/") for value in _cors_origins()}
        # Modern browsers send Origin and/or Fetch Metadata on unsafe requests.
        # Reject a present untrusted origin (including an untrusted same-site
        # subdomain) and explicit cross-site navigation. Older clients without
        # either signal still rely on the production SameSite=Lax cookie.
        if (origin and origin not in allowed_origins) or fetch_site == "cross-site":
            raise HTTPException(status_code=403, detail="Origine de requête refusée")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Non authentifié")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Type de token invalide")
        # B105 exclusion: zero means "omit this field" in a MongoDB projection.
        u = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})  # nosec B105
        if not u:
            raise HTTPException(status_code=401, detail="Utilisateur introuvable")
        if u.get("is_active", True) is False:
            raise HTTPException(status_code=401, detail="Compte désactivé")
        # Server-side session invalidation: any token issued before the user's last logout
        # (or forced logout by admin) is rejected. token_epoch is a unix timestamp bumped
        # by /auth/logout and by admin actions that must revoke sessions.
        token_epoch = int(u.get("token_epoch") or 0)
        token_iat = int(payload.get("iat") or 0)
        if token_epoch and token_iat < token_epoch:
            raise HTTPException(status_code=401, detail="Session révoquée")
        token_epoch_ms = int(u.get("token_epoch_ms") or 0)
        token_iat_ms = int(payload.get("iat_ms") or 0)
        if token_epoch_ms and token_iat_ms < token_epoch_ms:
            raise HTTPException(status_code=401, detail="Session révoquée")
        # Ensure legacy users have company_id and permissions filled in
        u.setdefault("company_id", DEFAULT_COMPANY_ID)
        if not u.get("permissions"):
            u["permissions"] = get_default_permissions(u.get("role", ""))
        # Enforce role-critical rules (iter21): sales/commissions for commercial/responsable
        # are non-negotiable regardless of stale DB permissions.
        _role = u.get("role")
        if _role in ("commercial", "responsable"):
            _perms = dict(u.get("permissions") or {})
            if _role == "commercial":
                _sales = dict(_perms.get("sales") or {})
                _sales.update({"create": False, "edit": False, "delete": False})
                _perms["sales"] = _sales
                _comm = dict(_perms.get("commissions") or {})
                _comm.update({"edit": False})
                _perms["commissions"] = _comm
            else:  # responsable
                _sales = dict(_perms.get("sales") or {})
                _sales.update({"view": "all", "create": True, "edit": True, "delete": True})
                _perms["sales"] = _sales
                _comm = dict(_perms.get("commissions") or {})
                _comm.update({"view": "all", "edit": True})
                _perms["commissions"] = _comm
            u["permissions"] = _perms
        # iter94 : verrou éligibilité heures sup (technicien uniquement)
        await _apply_overtime_eligibility_gate(u)
        # iter161 : gate abonnement — un compte SUSPENDED n'a plus accès aux endpoints
        # métier mais l'auth, la lecture de son propre statut d'abonnement et le
        # parcours de régularisation restent ouverts. AUCUNE donnée n'est supprimée
        # côté serveur : la suspension n'est qu'un flag `subscription_status`.
        if u.get("subscription_status") == "suspended" and u.get("role") != "super_admin":
            p = request.url.path or ""
            _billing_ok = (
                p.startswith("/api/auth/")
                or p.startswith("/api/payments/")
                or p.startswith("/api/stripe/")
                or p in ("/api/subscription/me", "/api/company/me", "/api/version")
            )
            if not _billing_ok:
                raise HTTPException(status_code=402, detail="Abonnement suspendu — régularisez votre paiement pour retrouver l'accès. Aucune donnée n'a été supprimée.")
        # Super-admin restricted to their own scope of endpoints (auth + superadmin + company/me)
        if u.get("role") == "super_admin":
            p = request.url.path or ""
            allowed_prefixes = ("/api/auth/", "/api/superadmin/")
            allowed_exact = ("/api/company/me",)
            if not (p in allowed_exact or any(p.startswith(a) for a in allowed_prefixes)):
                raise HTTPException(status_code=403, detail="Super-admin : utilisez les endpoints /api/superadmin/*")
        return u
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expirée")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalide")


def require_role(user: dict, *allowed_roles: str):
    if user.get("role") not in allowed_roles and user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Accès refusé")

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    require_role(user, "admin")
    return user

async def require_super_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Réservé au super-admin")
    return user

async def require_sales_access(user: dict = Depends(get_current_user)) -> dict:
    # admin + commercial + responsable + comptable + super-admin can access sales/clients/dashboard
    require_role(user, "admin", "commercial", "responsable", "comptable")
    return user


# ---------------- Multi-tenant + Permissions ----------------

DEFAULT_COMPANY_ID = "default"

DEFAULT_PERMISSIONS = {
    "admin": {
        "sales": {"view": "all", "create": True, "edit": True, "delete": True},
        "clients": {"view": "all", "create": True, "edit": True, "delete": True},
        "projects": {"view": "all", "create": True, "edit": True, "delete": True},
        "planning": {"view": "all", "edit": "all"},
        "commissions": {"view": "all", "edit": True},
        "overtime": {"declare": True, "view": "all", "edit": True, "validate": True},
        "reports": {"view": True},
        "users": {"manage": True},
        "settings": {"modify": True},
        "financial": {"view": True},
        "photos": {"view": True, "add": True},
        # iter68 : Stock — admin voit et modifie tout.
        "stock": {"view": True, "edit": True, "view_own": True, "view_others": True, "view_company": True},
    },
    "responsable": {
        # Responsable = manager. Full sales + commissions rights.
        "sales": {"view": "all", "create": True, "edit": True, "delete": True},
        "clients": {"view": "all", "create": True, "edit": True, "delete": False},
        "projects": {"view": "all", "create": True, "edit": True, "delete": False},
        "planning": {"view": "all", "edit": "all"},
        "commissions": {"view": "all", "edit": True},
        "overtime": {"declare": False, "view": "all", "edit": True, "validate": True},
        "reports": {"view": True},
        "users": {"manage": False},
        "settings": {"modify": False},
        "financial": {"view": False},
        "photos": {"view": True, "add": True},
        "stock": {"view": True, "edit": True, "view_own": True, "view_others": True, "view_company": True},
    },
    "commercial": {
        # Commercial = READ-ONLY on sales and commissions. Cannot create/edit/delete sales,
        # cannot change rates, cannot toggle "payé".
        "sales": {"view": "own", "create": False, "edit": False, "delete": False},
        "clients": {"view": "own", "create": True, "edit": True, "delete": False},
        "projects": {"view": "own", "create": False, "edit": False, "delete": False},
        "planning": {"view": "own", "edit": "none"},
        "commissions": {"view": "own", "edit": False},
        "overtime": {"declare": False, "view": "none", "edit": False, "validate": False},
        "reports": {"view": False},
        "users": {"manage": False},
        "settings": {"modify": False},
        "financial": {"view": False},
        "photos": {"view": True, "add": False},
        # iter68 : Stock — un commercial n'a AUCUN accès au stock par défaut.
        "stock": {"view": False, "edit": False, "view_own": False, "view_others": False, "view_company": False},
    },
    "technicien": {
        "sales": {"view": "none", "create": False, "edit": False, "delete": False},
        "clients": {"view": "none", "create": False, "edit": False, "delete": False},
        "projects": {"view": "own", "create": False, "edit": True, "delete": False},
        "planning": {"view": "own", "edit": "own"},
        "commissions": {"view": "none", "edit": False},
        "overtime": {"declare": True, "view": "own", "edit": True, "validate": False},
        "reports": {"view": False},
        "users": {"manage": False},
        "settings": {"modify": False},
        "financial": {"view": False},
        "photos": {"view": True, "add": True},
        # iter68 : Stock — technicien voit son stock + celui des autres + société par défaut.
        # Aucune modification par défaut. L'admin peut ajuster individuellement chaque bool.
        "stock": {"view": True, "edit": False, "view_own": True, "view_others": True, "view_company": True},
    },
    # iter85 : Sous-traitant — accès strictement limité à Chantiers + Planning (comme technicien mais sans stock ni heures sup).
    "sous_traitant": {
        "sales": {"view": "none", "create": False, "edit": False, "delete": False},
        "clients": {"view": "none", "create": False, "edit": False, "delete": False},
        "projects": {"view": "own", "create": False, "edit": True, "delete": False},
        "planning": {"view": "own", "edit": "own"},
        "commissions": {"view": "none", "edit": False},
        "overtime": {"declare": False, "view": "none", "edit": False, "validate": False},
        "reports": {"view": False},
        "users": {"manage": False},
        "settings": {"modify": False},
        "financial": {"view": False},
        "photos": {"view": True, "add": True},
        "stock": {"view": False, "edit": False, "view_own": False, "view_others": False, "view_company": False},
    },
    "comptable": {
        "sales": {"view": "all", "create": False, "edit": False, "delete": False},
        "clients": {"view": "all", "create": False, "edit": False, "delete": False},
        "projects": {"view": "all", "create": False, "edit": False, "delete": False},
        "planning": {"view": "all", "edit": "none"},
        "commissions": {"view": "all", "edit": True},
        "overtime": {"declare": False, "view": "all", "edit": False, "validate": False},
        "reports": {"view": True},
        "users": {"manage": False},
        "settings": {"modify": False},
        "financial": {"view": True},
        "photos": {"view": True, "add": False},
        "stock": {"view": True, "edit": False, "view_own": True, "view_others": True, "view_company": True},
    },
    # Prospecteur : accès uniquement à sa page Prospecteur (lecture seule)
    "prospecteur": {
        "sales": {"view": "none", "create": False, "edit": False, "delete": False},
        "clients": {"view": "none", "create": False, "edit": False, "delete": False},
        "projects": {"view": "none", "create": False, "edit": False, "delete": False},
        "planning": {"view": "none", "edit": "none"},
        "commissions": {"view": "none", "edit": False},
        "overtime": {"declare": False, "view": "none", "edit": False, "validate": False},
        "reports": {"view": False},
        "users": {"manage": False},
        "settings": {"modify": False},
        "financial": {"view": False},
        "photos": {"view": False, "add": False},
        "stock": {"view": False, "edit": False, "view_own": False, "view_others": False, "view_company": False},
    },
}
DEFAULT_PERMISSIONS["responsable_prospecteur"] = __import__("copy").deepcopy(DEFAULT_PERMISSIONS["prospecteur"])


def get_default_permissions(role: str) -> dict:
    import copy as _copy
    return _copy.deepcopy(DEFAULT_PERMISSIONS.get(role, DEFAULT_PERMISSIONS["technicien"]))


def is_super_admin(user: dict) -> bool:
    return (user or {}).get("role") == "super_admin"


def company_id_of(user: dict) -> str:
    return (user or {}).get("company_id") or DEFAULT_COMPANY_ID


def cq(user: dict, extra: Optional[dict] = None) -> dict:
    """Return a Mongo query dict scoped to the user's company. Super-admins are unscoped."""
    q = dict(extra or {})
    if not is_super_admin(user):
        q["company_id"] = company_id_of(user)
    return q


def with_company(doc: dict, user: dict) -> dict:
    d = dict(doc)
    d["company_id"] = company_id_of(user)
    return d


def _perm(user: dict, resource: str, action: str):
    perms = (user or {}).get("permissions") or {}
    # iter48: fallback per-resource sur DEFAULT_PERMISSIONS quand la clé manque
    # dans les permissions sauvegardées (utilisateurs créés avant ajout d'une nouvelle ressource).
    if resource not in perms:
        defaults = get_default_permissions(user.get("role", "") if user else "")
        return (defaults.get(resource) or {}).get(action)
    return (perms.get(resource) or {}).get(action)


_SCOPE_ORDER = {"none": 0, "own": 1, "team": 2, "all": 3}


def has_perm(user: dict, resource: str, action: str, min_scope: str = "own") -> bool:
    if is_super_admin(user):
        return True
    v = _perm(user, resource, action)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return _SCOPE_ORDER.get(v, 0) >= _SCOPE_ORDER.get(min_scope, 1)
    return False


def check_perm(user: dict, resource: str, action: str, min_scope: str = "own"):
    if not has_perm(user, resource, action, min_scope):
        raise HTTPException(status_code=403, detail="Accès refusé (permission manquante)")


def perm_scope(user: dict, resource: str, action: str) -> str:
    if is_super_admin(user):
        return "all"
    v = _perm(user, resource, action)
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return "all" if v else "none"
    return "none"


async def _commercial_client_ids(user: dict) -> List[str]:
    """For a commercial with 'own' scope: list of client_ids linked to their own sales.
    iter98 : utilise le filtre canonique `_own_sales_filter` (basé sur commercial_user_id +
    fallback nom insensible casse/accent + slot 2), au lieu du match strict qui manquait des ventes."""
    q = {"company_id": company_id_of(user)}
    q.update(_own_sales_filter(user))
    sales = await db.sales.find(q, {"_id": 0, "client_id": 1}).to_list(20000)
    return list({s["client_id"] for s in sales if s.get("client_id")})


PROSPECT_ROLES = ("prospecteur", "responsable_prospecteur")


def _is_prospect_role(user: dict) -> bool:
    return (user or {}).get("role") in PROSPECT_ROLES


def _prospect_sales_filter(user: dict) -> dict:
    if user.get("role") == "prospecteur":
        return {"prospecteur_id": user["id"]}
    return {"prospecteur_id": {"$nin": [None, ""]}}


async def _prospect_ids(user: dict):
    """(sale_ids, client_ids) des ventes liées à un prospecteur — périmètre des rôles prospection."""
    sales = await db.sales.find(cq(user, _prospect_sales_filter(user)), {"_id": 0, "id": 1, "client_id": 1}).to_list(20000)
    return [s["id"] for s in sales], list({s["client_id"] for s in sales if s.get("client_id")})


async def _own_sale_ids(user: dict) -> List[str]:
    """iter98 : idem, filtre canonique."""
    q = {"company_id": company_id_of(user)}
    q.update(_own_sales_filter(user))
    sales = await db.sales.find(q, {"_id": 0, "id": 1}).to_list(20000)
    return [s["id"] for s in sales]


async def _scoped_client_query(user: dict, client_id: str) -> dict:
    """Return a tenant- and ownership-scoped query for a client mutation.

    Listing and mutation must share the same ownership rules.  A user with an
    ``own`` scope may only mutate clients linked to one of their sales or
    clients they created themselves.  Broader scopes remain company-scoped.
    """
    q = cq(user, {"id": client_id})
    if perm_scope(user, "clients", "view") == "own":
        own_ids = await _commercial_client_ids(user)
        q["$or"] = [
            {"id": {"$in": own_ids}},
            {"created_by": user["id"]},
        ]
    return q


def _scoped_prospect_query(user: dict, prospect_id: str) -> dict:
    """Return a tenant- and ownership-scoped query for a prospect mutation."""
    q = cq(user, {"id": prospect_id})
    if perm_scope(user, "clients", "view") == "own":
        q["assigned_to"] = user.get("name") or "__none__"
    return q


# ---------------- Models ----------------

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=72)
    name: str = Field(min_length=1, max_length=120)

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)

class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: Optional[str] = Field(default="", max_length=40)
    email: Optional[str] = Field(default="", max_length=320)
    address: Optional[str] = Field(default="", max_length=500)
    postal_code: Optional[str] = Field(default="", max_length=20)
    city: Optional[str] = Field(default="", max_length=120)
    notes: Optional[str] = Field(default="", max_length=5000)

class PrestationLine(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(default=1, ge=1, le=10)


class SaleIn(BaseModel):
    client_id: Optional[str] = Field(default=None, max_length=128)
    client: Optional[ClientIn] = None
    bdc: Optional[str] = Field(default="", max_length=120)
    service: str = Field(min_length=1, max_length=500, description="Prestation requise")
    prestations: Optional[List[PrestationLine]] = Field(default=None, max_length=100)
    amount: float = Field(default=0, ge=0, le=10_000_000, description="Montant HT (€)")
    payment_method: Optional[str] = Field(default="", max_length=80)
    payment_installments: Optional[int] = Field(default=1, ge=1, le=120)
    financement_amount: Optional[float] = Field(default=None, ge=0, le=10_000_000, description="Part financée (€) si payment_method=financement")
    comptant_installments: Optional[int] = Field(default=1, ge=1, le=12, description="Nombre d'échéances pour la part comptant")
    commission_rate: Optional[float] = Field(default=0.0, ge=0, le=1)
    commission_rate_2: Optional[float] = Field(default=None, ge=0, le=1)  # DE only: independent rate for commercial_2
    # iter27: commission mode per sale. `fixed` (default) keeps `commission_rate` as-is.
    # `evolutive_ca` uses the company threshold rule. `evolutive_discount` uses the company's discount tiers.
    commission_type: Optional[Literal["fixed", "evolutive_ca", "evolutive_discount"]] = "fixed"
    commission_type_2: Optional[Literal["fixed", "evolutive_ca", "evolutive_discount"]] = None
    discount_percent: Optional[float] = Field(default=None, ge=0, le=100)  # only used when commission_type == "evolutive_discount"
    # iter130 : paramètres per-vente du palier evolutive_ca (renseignés côté frontend).
    # Sans ces champs, Pydantic strippait silencieusement les valeurs → reconcile inopérant.
    evolutive_ca_threshold: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    evolutive_rate_below: Optional[float] = Field(default=None, ge=0, le=1)
    evolutive_rate_above: Optional[float] = Field(default=None, ge=0, le=1)
    commercial: Optional[str] = Field(default="", max_length=120)
    commercial_2: Optional[str] = Field(default="", max_length=120)  # 2nd commercial for DE sales
    is_de: Optional[bool] = False                  # marks a "vente en DE"
    commercial_share: Optional[float] = Field(default=0.5, ge=0, le=1)  # DEPRECATED (iter22): CA is always 50/50 for DE.
    source: Optional[str] = Field(default="", max_length=80)  # R1 | Assist | CQ | CA
    commission_paid: Optional[bool] = False
    commission_month: Optional[str] = Field(default="", pattern=r"^(|\d{4}-\d{2})$")  # YYYY-MM
    sale_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")
    desired_intervention_date: Optional[str] = Field(default=None, pattern=r"^(\d{4}-\d{2}-\d{2}|attente_financement|attente_14j)$")
    status: str = Field(default="commercial_cheque", max_length=80)
    notes: Optional[str] = Field(default="", max_length=5000)
    prospecteur_id: Optional[str] = Field(default="", max_length=128)
    prospecteur_commission: Optional[float] = Field(default=None, ge=0, le=1_000_000)

    @field_validator("sale_date")
    @classmethod
    def validate_sale_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value

    @field_validator("desired_intervention_date")
    @classmethod
    def validate_desired_intervention_date(cls, value: Optional[str]) -> Optional[str]:
        if value and value not in ("attente_financement", "attente_14j"):
            date.fromisoformat(value)
        return value

    @field_validator("commission_month")
    @classmethod
    def validate_commission_month(cls, value: Optional[str]) -> Optional[str]:
        if value:
            datetime.strptime(value, "%Y-%m")
        return value

    @model_validator(mode="after")
    def validate_financing_split(self):
        if self.financement_amount is not None and self.financement_amount > self.amount:
            raise ValueError("La part financée ne peut pas dépasser le montant total")
        return self

class SaleUpdate(BaseModel):
    bdc: Optional[str] = Field(default=None, max_length=120)
    service: Optional[str] = Field(default=None, max_length=500)
    prestations: Optional[List[PrestationLine]] = Field(default=None, max_length=100)
    amount: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    payment_method: Optional[str] = Field(default=None, max_length=80)
    payment_installments: Optional[int] = Field(default=None, ge=1, le=120)
    financement_amount: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    comptant_installments: Optional[int] = Field(default=None, ge=1, le=12)
    commission_rate: Optional[float] = Field(default=None, ge=0, le=1)
    commission_rate_2: Optional[float] = Field(default=None, ge=0, le=1)
    commission_type: Optional[Literal["fixed", "evolutive_ca", "evolutive_discount"]] = None
    commission_type_2: Optional[Literal["fixed", "evolutive_ca", "evolutive_discount"]] = None
    discount_percent: Optional[float] = Field(default=None, ge=0, le=100)
    # iter130 : paramètres per-vente du palier evolutive_ca (modifiables via l'édition).
    evolutive_ca_threshold: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    evolutive_rate_below: Optional[float] = Field(default=None, ge=0, le=1)
    evolutive_rate_above: Optional[float] = Field(default=None, ge=0, le=1)
    commercial: Optional[str] = Field(default=None, max_length=120)
    commercial_2: Optional[str] = Field(default=None, max_length=120)
    is_de: Optional[bool] = None
    commercial_share: Optional[float] = Field(default=None, ge=0, le=1)  # DEPRECATED — ignored server-side (CA always 50/50)
    source: Optional[str] = Field(default=None, max_length=80)
    commission_paid: Optional[bool] = None
    commission_month: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    sale_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    desired_intervention_date: Optional[str] = Field(default=None, pattern=r"^(\d{4}-\d{2}-\d{2}|attente_financement|attente_14j)$")
    status: Optional[str] = Field(default=None, max_length=80)
    notes: Optional[str] = Field(default=None, max_length=5000)
    prospecteur_id: Optional[str] = Field(default=None, max_length=128)
    prospecteur_commission: Optional[float] = Field(default=None, ge=0, le=1_000_000)

    @field_validator("sale_date")
    @classmethod
    def validate_sale_date(cls, value: Optional[str]) -> Optional[str]:
        if value:
            date.fromisoformat(value)
        return value

    @field_validator("desired_intervention_date")
    @classmethod
    def validate_desired_intervention_date(cls, value: Optional[str]) -> Optional[str]:
        if value and value not in ("attente_financement", "attente_14j"):
            date.fromisoformat(value)
        return value

    @field_validator("commission_month")
    @classmethod
    def validate_commission_month(cls, value: Optional[str]) -> Optional[str]:
        if value:
            datetime.strptime(value, "%Y-%m")
        return value

    @model_validator(mode="after")
    def validate_financing_split(self):
        if self.amount is not None and self.financement_amount is not None and self.financement_amount > self.amount:
            raise ValueError("La part financée ne peut pas dépasser le montant total")
        return self

class ProjectUpdate(BaseModel):
    status: Optional[Literal["a_planifier", "en_cours", "termine", "encaisse"]] = None
    scheduled_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    assigned_to: Optional[List[Annotated[str, Field(max_length=120)]]] = Field(default=None, max_length=100)
    priority: Optional[str] = Field(default=None, max_length=40)
    notes: Optional[str] = Field(default=None, max_length=5000)
    duration_days: Optional[int] = Field(default=None, ge=1, le=365)
    photos: Optional[List[Union[str, dict]]] = Field(default=None, max_length=MAX_PHOTOS_PER_ENTITY)

    @field_validator("scheduled_date")
    @classmethod
    def validate_scheduled_date(cls, value: Optional[str]) -> Optional[str]:
        if value:
            date.fromisoformat(value)
        return value
    # iter211 : exclusions ciblées par journée sur un chantier multi-jours.
    # Format : { "YYYY-MM-DD": ["nom1", "nom2"] } — noms retirés UNIQUEMENT ce jour.
    day_exclusions: Optional[Dict[str, List[Annotated[str, Field(max_length=120)]]]] = Field(default=None, max_length=366)
    # iter213 : jours supplémentaires NON consécutifs (ex : chantier lundi + mercredi + vendredi).
    # Format : ["YYYY-MM-DD", ...] — chaque date s'ajoute en plus des `duration_days` jours consécutifs.
    extra_dates: Optional[List[Annotated[str, Field(max_length=10)]]] = Field(default=None, max_length=366)

    @field_validator("extra_dates")
    @classmethod
    def validate_extra_dates(cls, values: Optional[List[str]]) -> Optional[List[str]]:
        for value in values or []:
            date.fromisoformat(value)
        return values

    @field_validator("day_exclusions")
    @classmethod
    def validate_day_exclusions(cls, values: Optional[Dict[str, List[str]]]) -> Optional[Dict[str, List[str]]]:
        for day, names in (values or {}).items():
            date.fromisoformat(day)
            if len(names) > 100:
                raise ValueError("Trop de personnes exclues pour une journée")
        return values


class ClientsBulkIn(BaseModel):
    text: Optional[str] = Field(default=None, max_length=1_000_000)
    clients: Optional[List[ClientIn]] = Field(default=None, max_length=5000)


class MonthlyReportIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")

    @field_validator("month")
    @classmethod
    def validate_monthly_report_month(cls, value: str) -> str:
        datetime.strptime(value, "%Y-%m")
        return value


# ---------------- Auth Endpoints ----------------

@api_router.post("/auth/register")
async def register(data: RegisterIn, response: Response):
    # Production accounts must be created through an authenticated admin flow.
    # Public registration is an explicit, development-only opt-in so an
    # unauthenticated visitor can never join DEFAULT_COMPANY_ID by accident.
    environment = (os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "development").lower()
    registration_enabled = (os.environ.get("ALLOW_PUBLIC_REGISTRATION") or "false").strip().lower() in ("1", "true", "yes")
    if not registration_enabled or environment in ("production", "prod"):
        raise HTTPException(status_code=403, detail="Inscription publique désactivée — demandez une invitation à un administrateur")
    email = data.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
    uid = str(uuid.uuid4())
    doc = {
        "id": uid, "email": email, "name": data.name,
        "password_hash": hash_password(data.password),
        "role": "commercial",
        "company_id": DEFAULT_COMPANY_ID,
        "permissions": get_default_permissions("commercial"),
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    token = create_access_token(uid, email)
    set_auth_cookie(response, token)
    return _auth_response(doc, token)

# ---------------- Anti brute-force login ----------------
_LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
_LOGIN_WINDOW_MIN = int(os.environ.get("LOGIN_WINDOW_MIN", "15"))
_LOGIN_LOCKOUT_MIN = int(os.environ.get("LOGIN_LOCKOUT_MIN", "15"))
_LOGIN_SOURCE_MAX_ATTEMPTS = int(os.environ.get("LOGIN_SOURCE_MAX_ATTEMPTS", "30"))


def _login_key(email: str) -> str:
    """Return a non-reversible database key without storing the account email."""
    return _hmac.new(
        JWT_SECRET.encode("utf-8"),
        (email or "").strip().lower().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _as_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def _check_login_lock(email: str):
    key = _login_key(email)
    rec = await db.login_attempts.find_one({"_id": key})
    if not rec:
        return
    now = datetime.now(timezone.utc)
    lu = _as_utc(rec.get("locked_until"))
    if lu and now < lu:
        remaining = int((lu - now).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"Trop d'échecs de connexion. Réessayez dans {max(1, remaining // 60)} minute(s).",
            headers={"Retry-After": str(remaining)},
        )
    # Reset window if too old
    first = _as_utc(rec.get("first"))
    if first and (now - first) > timedelta(minutes=_LOGIN_WINDOW_MIN):
        await db.login_attempts.delete_one({"_id": key})


async def _register_login_failure(email: str):
    key = _login_key(email)
    now = datetime.now(timezone.utc)
    update = {
        "$inc": {"count": 1},
        "$setOnInsert": {"first": now},
        "$set": {"expires_at": now + timedelta(minutes=_LOGIN_WINDOW_MIN + _LOGIN_LOCKOUT_MIN)},
    }
    try:
        rec = await db.login_attempts.find_one_and_update(
            {"_id": key}, update, upsert=True, return_document=ReturnDocument.AFTER
        )
    except DuplicateKeyError:
        rec = await db.login_attempts.find_one_and_update(
            {"_id": key}, update, return_document=ReturnDocument.AFTER
        )
    if rec and int(rec.get("count") or 0) >= _LOGIN_MAX_ATTEMPTS:
        await db.login_attempts.update_one(
            {"_id": key},
            {"$set": {
                "locked_until": now + timedelta(minutes=_LOGIN_LOCKOUT_MIN),
                "expires_at": now + timedelta(minutes=_LOGIN_LOCKOUT_MIN + 1),
            }},
        )


async def _reset_login_attempts(email: str):
    await db.login_attempts.delete_one({"_id": _login_key(email)})


def _login_source(request: Request) -> str:
    """Use the direct peer unless proxy headers were explicitly trusted."""
    source_ip = request.client.host if request.client else "unknown"
    trust_proxy = (os.environ.get("TRUST_PROXY_HEADERS") or "false").strip().lower() in ("1", "true", "yes")
    if trust_proxy:
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
        if forwarded:
            try:
                source_ip = str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass
    return _hmac.new(
        JWT_SECRET.encode("utf-8"), f"login-source:{source_ip}".encode("utf-8"), hashlib.sha256,
    ).hexdigest()


async def _check_login_source(request: Request):
    rec = await db.login_source_attempts.find_one({"_id": _login_source(request)})
    if rec and int(rec.get("count") or 0) >= _LOGIN_SOURCE_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Trop de tentatives de connexion. Réessayez plus tard.")


async def _register_login_source_failure(request: Request):
    now = datetime.now(timezone.utc)
    await db.login_source_attempts.update_one(
        {"_id": _login_source(request)},
        {
            "$inc": {"count": 1},
            "$setOnInsert": {"first": now},
            "$set": {"expires_at": now + timedelta(minutes=_LOGIN_WINDOW_MIN)},
        },
        upsert=True,
    )


async def _reset_login_source(request: Request):
    await db.login_source_attempts.delete_one({"_id": _login_source(request)})


@api_router.post("/auth/login")
async def login(data: LoginIn, response: Response, request: Request):
    email = (data.email or "").lower().strip()
    # Refuse a source already throttled before paying the cost of bcrypt. The
    # old order still performed an expensive hash on every blocked request.
    await _check_login_source(request)
    u = await db.users.find_one({"email": email})
    password_valid = verify_password(data.password, (u or {}).get("password_hash") or _DUMMY_PASSWORD_HASH)
    if not password_valid:
        await _check_login_lock(email)
        await _register_login_failure(email)
        await _register_login_source_failure(request)
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    if u.get("is_active", True) is False:
        await _register_login_source_failure(request)
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    await _reset_login_attempts(email)
    await _reset_login_source(request)
    token = create_access_token(u["id"], email)
    # iter94 : appliquer le verrou éligibilité heures sup avant sérialisation
    u.setdefault("company_id", DEFAULT_COMPANY_ID)
    if not u.get("permissions"):
        u["permissions"] = get_default_permissions(u.get("role", ""))
    await _apply_overtime_eligibility_gate(u)
    set_auth_cookie(response, token)
    return _auth_response(u, token)

@api_router.post("/auth/logout")
async def logout(response: Response, request: Request):
    # Best-effort: identify the user and bump their token_epoch so every previously
    # issued access token is rejected by /api/auth/me and any protected endpoint.
    # We do NOT raise if the token is missing/invalid — logout is idempotent.
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            uid = payload.get("sub")
            if uid:
                # Add 1s so a token minted in the same second is also invalidated.
                new_epoch = int(datetime.now(timezone.utc).timestamp()) + 1
                new_epoch_ms = int(datetime.now(timezone.utc).timestamp() * 1000) + 1
                await db.users.update_one({"id": uid}, {"$set": {"token_epoch": new_epoch, "token_epoch_ms": new_epoch_ms}})
        except jwt.PyJWTError:
            pass
    response.delete_cookie("access_token", path="/")
    # Clear the unused legacy cookie left by versions prior to the security pass.
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}

@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    # iter198 — Sanity reconcile ventes ↔ commerciaux au premier /auth/me du jour.
    # Rattache automatiquement les ventes créées sous « Théo » (prénom court)
    # à Théo Dudal via user_id, sans que l'admin doive cliquer sur un bouton.
    # Rate-limit : max une fois par heure par company_id pour éviter le coût sur les gros clients.
    try:
        cid = company_id_of(user)
        _last_key = f"__last_reconcile__{cid}"
        now_ts = datetime.now(timezone.utc).timestamp()
        last = _AUTH_ME_RECONCILE_CACHE.get(_last_key, 0)
        if now_ts - last > 3600:
            _AUTH_ME_RECONCILE_CACHE[_last_key] = now_ts
            asyncio.create_task(_reconcile_sales_commercials(cid))
    except Exception:
        logger.exception("Échec du rapprochement périodique des commerciaux")
    return public_user(user)


@api_router.post("/me/onboarding-complete")
async def mark_onboarding_complete(user: dict = Depends(get_current_user)):
    """iter183 — Marque l'onboarding « première utilisation » comme terminé côté serveur.
    Idempotent : le flag reste true à vie sur le document `users`.
    L'assistant d'accueil n'apparaîtra plus jamais pour cet utilisateur, même sur
    un autre navigateur ou après clear cache."""
    await db.users.update_one({"id": user["id"]}, {"$set": {"onboarding_done": True, "onboarding_done_at": now_iso()}})
    return {"ok": True, "onboarding_done": True}


# ---------------- Clients ----------------

async def find_or_create_client(client_id: Optional[str], client: Optional[ClientIn], user: dict) -> dict:
    if client_id:
        c = await db.clients.find_one(cq(user, {"id": client_id}), {"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail="Client introuvable")
        return c
    if not client:
        raise HTTPException(status_code=400, detail="Client requis")
    # Dedup by name+phone (within company)
    q = cq(user, {"name": client.name})
    if client.phone:
        q["phone"] = client.phone
    existing = await db.clients.find_one(q, {"_id": 0})
    if existing:
        return existing
    c = with_company({"id": str(uuid.uuid4()), "created_at": now_iso(), "created_by": user["id"], **client.model_dump()}, user)
    await db.clients.insert_one(c.copy())
    return c

@api_router.get("/search")
async def global_search(
    q: str = Query("", max_length=200),
    limit: int = Query(8, ge=1, le=20),
    user: dict = Depends(get_current_user),
):
    """iter169 : recherche globale multi-collections, permission-aware et strictement
    multi-tenant. Retourne des catégories (clients, sales, projects, users, reinterventions).
    Chaque catégorie applique le même filtrage que ses listings dédiés (`cq` + perm_scope
    + `_own_sales_filter` + `assigned_to` pour techs)."""
    q = (q or "").strip()
    if len(q) < 2:
        return {"query": q, "categories": {}}
    import re as _re
    pat = _re.escape(q)
    rx = {"$regex": pat, "$options": "i"}
    role = user.get("role")
    company = company_id_of(user)
    out = {"clients": [], "sales": [], "projects": [], "users": [], "reinterventions": []}
    lim = max(1, min(int(limit or 8), 20))

    # --- CLIENTS ---
    clients_scope = perm_scope(user, "clients", "view")
    if clients_scope != "none":
        c_or = [{f: rx} for f in ("name", "phone", "email", "address", "postal_code", "city")]
        c_q = cq(user, {"$or": c_or})
        if clients_scope == "own":
            ids = await _commercial_client_ids(user)
            c_q["id"] = {"$in": ids}
        docs = await db.clients.find(c_q, {"_id": 0, "id": 1, "name": 1, "city": 1, "phone": 1, "postal_code": 1}).limit(lim).to_list(lim)
        out["clients"] = docs

    # --- SALES ---
    sales_scope = perm_scope(user, "sales", "view")
    if sales_scope != "none":
        s_or = [{f: rx} for f in ("client_name", "service", "commercial", "bdc", "postal_code")]
        s_q = cq(user, {"$or": s_or})
        if sales_scope == "own":
            s_q.update(_own_sales_filter(user))
        docs = await db.sales.find(s_q, {"_id": 0, "id": 1, "client_name": 1, "service": 1, "amount": 1, "status": 1, "sale_date": 1, "commercial": 1}).sort("sale_date", -1).limit(lim).to_list(lim)
        out["sales"] = docs

    # --- PROJECTS (chantiers) ---
    projects_scope = perm_scope(user, "projects", "view")
    if projects_scope != "none":
        p_or = [{f: rx} for f in ("client_name", "service", "city", "address", "postal_code")]
        p_or.append({"assigned_to": rx})
        p_q = cq(user, {"$or": p_or, "cancelled": {"$ne": True}})
        if role in ("technicien", "sous_traitant"):
            my_name = user.get("name") or ""
            my_toks = [t for t in _re.split(r"[\s_\-\.]+", my_name.lower()) if t]
            p_q["assigned_to"] = {"$in": [my_name] + my_toks} if my_toks else my_name
        elif projects_scope == "own":
            p_q["$and"] = [{"$or": p_q.pop("$or")}, {"$or": [
                {"client_id": {"$in": await _commercial_client_ids(user)}},
                {"sale_id": {"$in": await _own_sale_ids(user)}},
            ]}]
        docs = await db.projects.find(p_q, {"_id": 0, "id": 1, "client_name": 1, "service": 1, "status": 1, "scheduled_date": 1, "assigned_to": 1, "city": 1}).sort("scheduled_date", -1).limit(lim).to_list(lim)
        out["projects"] = docs

    # --- REINTERVENTIONS ---
    planning_scope = perm_scope(user, "planning", "view")
    if planning_scope != "none" and role != "commercial":
        r_or = [{f: rx} for f in ("client_name", "reason", "assigned_to")]
        r_q = cq(user, {"$or": r_or})
        if role in ("technicien", "sous_traitant") or planning_scope == "own":
            r_q["$and"] = [{"$or": r_q.pop("$or")}, {"assigned_to": {
                "$regex": _re.escape(user.get("name") or "__none__"), "$options": "i",
            }}]
        out["reinterventions"] = await db.reinterventions.find(r_q, {"_id": 0, "id": 1, "client_name": 1, "reason": 1, "scheduled_date": 1, "assigned_to": 1}).sort("scheduled_date", -1).limit(lim).to_list(lim)

    # --- USERS (équipe) — admin/responsable seulement ---
    if has_perm(user, "users", "manage"):
        u_or = [{f: rx} for f in ("name", "email")]
        u_q = cq(user, {"$or": u_or})
        docs = await db.users.find(u_q, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}).limit(lim).to_list(lim)
        out["users"] = docs

    total = sum(len(v) for v in out.values())
    return {"query": q, "total": total, "categories": out}
    # iter142 : auto-heal — rétro-catégorise les clients dépourvus de catégorie
    # à partir de leur vente la plus récente (idempotent, ne touche jamais un
    # client déjà catégorisé). Rend l'auto-tri opérationnel sur les données existantes.
    try:
        await _backfill_client_categories_for_company(company_id_of(user))
    except Exception as _e:
        logger.warning(f"backfill client categories failed: {_e}")
    scope = perm_scope(user, "clients", "view")
    if scope == "all":
        q = cq(user)
    else:
        ids = await _commercial_client_ids(user)
        q = cq(user, {"id": {"$in": ids}})
    docs = await db.clients.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return docs


# ============================================================================
# iter133 — Catégories clients (Réinter / Litiges / Impayés / Archivés / …)
# ============================================================================
DEFAULT_CLIENT_CATEGORIES = [
    {"key": "en_cours", "label": "En cours", "color": "indigo", "order": 1, "sub_statuses": []},
    {"key": "reinter", "label": "Réinter", "color": "sky", "order": 2, "sub_statuses": [
        {"key": "a_programmer", "label": "À programmer"}, {"key": "programme", "label": "Programmé"},
        {"key": "attente", "label": "En attente"}, {"key": "intervention_faite", "label": "Intervention faite"},
        {"key": "clos", "label": "Clos"},
    ]},
    {"key": "litiges", "label": "Litiges", "color": "orange", "order": 3, "sub_statuses": [
        {"key": "reclamation", "label": "Réclamation"}, {"key": "mise_en_demeure", "label": "Mise en demeure"},
        {"key": "mediation", "label": "Médiation"}, {"key": "judiciaire", "label": "Avocat / Judiciaire"}, {"key": "resolu", "label": "Résolu"},
    ]},
    {"key": "impayes", "label": "Impayés", "color": "red", "order": 4, "sub_statuses": [
        {"key": "relance", "label": "Relance"}, {"key": "mise_en_demeure", "label": "Mise en demeure"},
        {"key": "echeancier", "label": "Échéancier"}, {"key": "contentieux", "label": "Contentieux"}, {"key": "paye", "label": "Payé"},
    ]},
    {"key": "annules", "label": "Annulés", "color": "red", "order": 5, "sub_statuses": []},
    {"key": "archives", "label": "Archivés", "color": "slate", "order": 6, "sub_statuses": []},
]


# iter137 : mapping automatique statut de vente → catégorie client par défaut.
# Le client peut toujours override manuellement via la fiche client.
SALE_STATUS_TO_CLIENT_CATEGORY = {
    "attente_prog": "en_cours", "attente_fi": "en_cours",
    "virement_en_cours": "en_cours", "commercial_cheque": "en_cours",
    "en_cours": "en_cours", "chantier_fini": "en_cours",
    "litige": "litiges", "annule": "annules",
    "argent_recupere": "archives", "virement_recu": "archives",
}


async def _auto_assign_client_category_from_sale(user: dict, sale: dict):
    """iter137 : quand une vente est créée/modifiée, catégorise le client automatiquement
    selon le statut. Ne modifie PAS les catégories déjà positionnées manuellement (dédupe par key).
    L'utilisateur peut toujours override via PUT /api/clients/{id}/category."""
    try:
        cid = sale.get("client_id")
        st = sale.get("status") or ""
        cat_key = SALE_STATUS_TO_CLIENT_CATEGORY.get(st)
        if not (cid and cat_key):
            return
        client = await db.clients.find_one(cq(user, {"id": cid}), {"_id": 0})
        if not client:
            return
        categories = list(client.get("categories") or [])
        # Retire les autres catégories système auto-assignables (pour refléter le nouveau statut)
        auto_keys = set(SALE_STATUS_TO_CLIENT_CATEGORY.values())
        categories = [c for c in categories if c.get("category_key") not in auto_keys]
        categories.append({
            "category_key": cat_key, "sub_status_key": None,
            "updated_at": now_iso(), "updated_by": user.get("id"),
            "updated_by_name": user.get("name") or "", "_auto": True,
        })
        await db.clients.update_one(cq(user, {"id": cid}), {"$set": {"categories": categories, "updated_at": now_iso()}})
    except Exception as _e:
        logger.warning(f"auto client category assign failed: {_e}")


# iter142 : cache in-memory par company_id → timestamp du dernier backfill, pour
# éviter de recalculer à chaque GET /clients tout en gardant l'auto-heal réactif
# quand de nouvelles ventes/clients arrivent (TTL 60s).
_BACKFILL_LAST_RUN: dict = {}
_BACKFILL_TTL_SEC = 60


async def _backfill_client_categories_for_company(company_id: str) -> int:
    """Rétro-catégorise les clients d'une company qui n'ont pas encore de catégorie,
    à partir de leur vente la plus récente (statut → mapping SALE_STATUS_TO_CLIENT_CATEGORY).
    Idempotent : ne touche jamais un client déjà catégorisé. Renvoie le nombre de clients màj.
    """
    import time as _time
    now_ts = _time.time()
    last = _BACKFILL_LAST_RUN.get(company_id, 0)
    if now_ts - last < _BACKFILL_TTL_SEC:
        return 0
    _BACKFILL_LAST_RUN[company_id] = now_ts

    clients = await db.clients.find(
        {"company_id": company_id, "$or": [
            {"categories": {"$exists": False}},
            {"categories": []},
            {"categories": None},
        ]},
        {"_id": 0, "id": 1},
    ).to_list(5000)
    if not clients:
        return 0
    client_ids = [c["id"] for c in clients]
    sales = await db.sales.find(
        {"company_id": company_id, "client_id": {"$in": client_ids}},
        {"_id": 0, "id": 1, "client_id": 1, "status": 1, "sale_date": 1, "created_at": 1},
    ).sort([("sale_date", -1), ("created_at", -1)]).to_list(20000)
    latest_by_client: dict = {}
    for s in sales:
        cid = s.get("client_id")
        if cid and cid not in latest_by_client:
            latest_by_client[cid] = s
    updated = 0
    now = now_iso()
    for cid, sale in latest_by_client.items():
        cat_key = SALE_STATUS_TO_CLIENT_CATEGORY.get(sale.get("status") or "")
        if not cat_key:
            continue
        entry = {
            "category_key": cat_key,
            "sub_status_key": None,
            "updated_at": now,
            "_auto": True,
        }
        r = await db.clients.update_one(
            {"company_id": company_id, "id": cid, "$or": [
                {"categories": {"$exists": False}},
                {"categories": []},
                {"categories": None},
            ]},
            {"$set": {"categories": [entry], "updated_at": now}},
        )
        if r.modified_count:
            updated += 1
    if updated:
        logger.info(f"iter142 backfill client categories: {updated} client(s) auto-catégorisé(s) pour company={company_id}")
    return updated


@api_router.post("/clients/backfill-categories")
async def backfill_client_categories(user: dict = Depends(require_admin)):
    """iter142 : endpoint admin pour forcer une re-catégorisation immédiate (contourne le TTL)."""
    _BACKFILL_LAST_RUN.pop(company_id_of(user), None)
    n = await _backfill_client_categories_for_company(company_id_of(user))
    return {"updated_count": n}


class ClientSubStatusIn(BaseModel):
    key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=60)


class ClientCategoryIn(BaseModel):
    key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=60)
    color: Optional[str] = Field(default="slate", max_length=20)
    order: Optional[int] = 0
    sub_statuses: Optional[List[ClientSubStatusIn]] = Field(default_factory=list, max_length=100)

    @field_validator("color")
    @classmethod
    def validate_client_category_color(cls, value: Optional[str]) -> Optional[str]:
        if value not in ALLOWED_STATUS_COLORS:
            raise ValueError("Couleur non autorisée")
        return value


class ClientCategoryPayload(BaseModel):
    categories: List[ClientCategoryIn] = Field(max_length=100)


class ClientCategoryAssign(BaseModel):
    category_key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    sub_status_key: Optional[str] = Field(default=None, max_length=40, pattern=r"^[a-z0-9_]+$")
    action: Optional[Literal["set", "remove"]] = "set"


async def _resolve_client_categories(company_id: str) -> List[dict]:
    s = await db.settings.find_one({"company_id": company_id, "kind": "global"}, {"_id": 0}) or {}
    raw = s.get("client_categories")
    if isinstance(raw, list) and raw:
        return sorted(raw, key=lambda x: x.get("order", 999))
    return list(DEFAULT_CLIENT_CATEGORIES)


@api_router.get("/client-categories")
async def get_client_categories(user: dict = Depends(get_current_user)):
    check_perm(user, "clients", "view", "own")
    return await _resolve_client_categories(company_id_of(user))


@api_router.put("/client-categories")
async def put_client_categories(payload: ClientCategoryPayload, user: dict = Depends(get_current_user)):
    check_perm(user, "settings", "modify")
    cid = company_id_of(user)
    data = [c.model_dump() for c in payload.categories]
    keys = [c["key"] for c in data]
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=400, detail="Clés de catégorie en doublon")
    await db.settings.update_one(
        {"company_id": cid, "kind": "global"},
        {"$set": {"client_categories": data, "kind": "global", "company_id": cid}},
        upsert=True,
    )
    await log_audit(user, "update", "client_categories", cid, after={"count": len(data)})
    return await _resolve_client_categories(cid)


@api_router.put("/clients/{cid}/category")
async def assign_client_category(cid: str, data: ClientCategoryAssign, user: dict = Depends(get_current_user)):
    check_perm(user, "clients", "edit")
    client_q = await _scoped_client_query(user, cid)
    client = await db.clients.find_one(client_q, {"_id": 0})
    if not client:
        raise HTTPException(status_code=404, detail="Client introuvable")
    categories = list(client.get("categories") or [])
    now = now_iso()
    if data.action == "remove":
        categories = [c for c in categories if c.get("category_key") != data.category_key]
    else:
        # set : remplace ou ajoute cette catégorie (dédupe par category_key)
        categories = [c for c in categories if c.get("category_key") != data.category_key]
        categories.append({
            "category_key": data.category_key,
            "sub_status_key": data.sub_status_key,
            "updated_at": now,
            "updated_by": user["id"],
            "updated_by_name": user.get("name") or user.get("email") or "",
        })
    history = list(client.get("category_history") or [])
    history.append({
        "ts": now, "user_id": user["id"], "user_name": user.get("name") or "",
        "action": data.action, "category_key": data.category_key, "sub_status_key": data.sub_status_key,
    })
    if len(history) > 100:
        history = history[-100:]
    await db.clients.update_one(
        client_q,
        {"$set": {"categories": categories, "category_history": history, "updated_at": now}},
    )
    await log_audit(user, "assign_category", "client", cid, after={"category_key": data.category_key, "sub_status_key": data.sub_status_key, "action": data.action})
    return await db.clients.find_one(client_q, {"_id": 0})


@api_router.get("/clients")
async def list_clients(user: dict = Depends(get_current_user)):
    """iter180 — Restauration après régression iter169 (Cmd+K global search) : cet endpoint
    avait été retiré par erreur. Retourne la liste des clients de la société avec scope
    RBAC (`own` pour un commercial = uniquement clients rattachés à ses propres ventes)."""
    check_perm(user, "clients", "view", "own")
    q = cq(user)
    if perm_scope(user, "clients", "view") == "own":
        ids = await _commercial_client_ids(user)
        q["id"] = {"$in": ids}
    if _is_prospect_role(user):
        q["id"] = {"$in": (await _prospect_ids(user))[1]}
    docs = await db.clients.find(q, {"_id": 0}).sort("created_at", -1).to_list(20000)
    return docs


_GEO_SEM = asyncio.Semaphore(8)


async def _geocode_fr(client_http, addr: str):
    async with _GEO_SEM:
        try:
            r = await client_http.get("https://api-adresse.data.gouv.fr/search/", params={"q": addr, "limit": 1}, timeout=8)
            feats = (r.json() or {}).get("features") or []
            if feats:
                lng, lat = feats[0]["geometry"]["coordinates"]
                return lat, lng
        except Exception:
            logger.warning("Échec du géocodage externe", exc_info=True)
    return None


@api_router.get("/clients/map")
async def clients_map(user: dict = Depends(get_current_user)):
    check_perm(user, "clients", "view", "own")
    q = cq(user)
    if perm_scope(user, "clients", "view") == "own":
        q["id"] = {"$in": await _commercial_client_ids(user)}
    if _is_prospect_role(user):
        q["id"] = {"$in": (await _prospect_ids(user))[1]}
    proj = {"_id": 0, "id": 1, "name": 1, "phone": 1, "address": 1, "postal_code": 1, "city": 1, "categories": 1, "geo_lat": 1, "geo_lng": 1, "geo_key": 1}
    docs = await db.clients.find(q, proj).to_list(20000)
    todo = []
    for d in docs:
        key = " ".join(x.strip() for x in (d.get("address") or "", d.get("postal_code") or "", d.get("city") or "") if x and x.strip())
        d["_key"] = key
        if key and d.get("geo_key") != key:
            todo.append(d)
    todo = todo[:300]
    environment = (os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "development").lower()
    geocoding_enabled = (os.environ.get("ALLOW_EXTERNAL_GEOCODING") or ("false" if environment in ("production", "prod") else "true")).strip().lower() in ("1", "true", "yes")
    if todo and geocoding_enabled:
        async with httpx.AsyncClient() as hc:
            results = await asyncio.gather(*[_geocode_fr(hc, d["_key"]) for d in todo])
        for d, res in zip(todo, results):
            lat, lng = res if res else (None, None)
            d["geo_lat"], d["geo_lng"], d["geo_key"] = lat, lng, d["_key"]
            await db.clients.update_one(cq(user, {"id": d["id"]}), {"$set": {"geo_lat": lat, "geo_lng": lng, "geo_key": d["_key"]}})
    pending = sum(1 for d in docs if d["_key"] and d.get("geo_key") != d["_key"])
    out = []
    for d in docs:
        d.pop("_key", None); d.pop("geo_key", None)
        out.append(d)
    return {"clients": out, "pending": pending, "external_geocoding_enabled": geocoding_enabled}

@api_router.post("/clients")
async def create_client(data: ClientIn, user: dict = Depends(get_current_user)):
    check_perm(user, "clients", "create")
    c = with_company({"id": str(uuid.uuid4()), "created_at": now_iso(), "created_by": user["id"], **data.model_dump()}, user)
    await db.clients.insert_one(c.copy())
    await log_audit(user, "create", "client", c["id"], after=c)
    return c

@api_router.put("/clients/{cid}")
async def update_client(cid: str, data: ClientIn, user: dict = Depends(get_current_user)):
    check_perm(user, "clients", "edit")
    client_q = await _scoped_client_query(user, cid)
    before = await db.clients.find_one(client_q, {"_id": 0})
    r = await db.clients.update_one(client_q, {"$set": data.model_dump()})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Client introuvable")
    after = await db.clients.find_one(client_q, {"_id": 0})
    await log_audit(user, "update", "client", cid, before=before, after=after)
    return after

@api_router.delete("/clients/{cid}")
async def delete_client(cid: str, user: dict = Depends(get_current_user)):
    check_perm(user, "clients", "delete")
    client_q = await _scoped_client_query(user, cid)
    before = await db.clients.find_one(client_q, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Client introuvable")
    dependencies = {
        "ventes": await db.sales.count_documents(cq(user, {"client_id": cid})),
        "chantiers": await db.projects.count_documents(cq(user, {"client_id": cid})),
        "notes": await db.client_notes.count_documents(cq(user, {"client_id": cid})),
    }
    if any(dependencies.values()):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "client_has_history",
                "message": "Ce client possède un historique. Archivez-le au lieu de le supprimer.",
                "dependencies": dependencies,
            },
        )
    r = await db.clients.delete_one(client_q)
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Client introuvable")
    await log_audit(user, "delete", "client", cid, before=before)
    return {"ok": True}


class ClientNoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@api_router.get("/clients/{cid}/notes")
async def list_client_notes(cid: str, user: dict = Depends(get_current_user)):
    check_perm(user, "clients", "view", "own")
    client_q = await _scoped_client_query(user, cid)
    if not await db.clients.find_one(client_q, {"_id": 1}):
        raise HTTPException(status_code=404, detail="Client introuvable")
    return await db.client_notes.find(cq(user, {"client_id": cid}), {"_id": 0}).sort("created_at", -1).to_list(500)


@api_router.post("/clients/{cid}/notes")
async def add_client_note(cid: str, data: ClientNoteIn, user: dict = Depends(get_current_user)):
    check_perm(user, "clients", "edit", "own")
    client_q = await _scoped_client_query(user, cid)
    if not await db.clients.find_one(client_q, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Client introuvable")
    note = with_company({"id": str(uuid.uuid4()), "client_id": cid, "text": data.text.strip(),
                         "author_id": user["id"], "author_name": user.get("name", ""), "created_at": now_iso()}, user)
    await db.client_notes.insert_one(note.copy())
    note.pop("_id", None)
    return note


@api_router.delete("/client-notes/{nid}")
async def delete_client_note(nid: str, user: dict = Depends(get_current_user)):
    check_perm(user, "clients", "edit", "own")
    q = cq(user, {"id": nid})
    if user.get("role") not in ("admin", "responsable"):
        q["author_id"] = user["id"]
    note = await db.client_notes.find_one(q, {"_id": 0, "client_id": 1})
    if not note:
        raise HTTPException(status_code=404, detail="Note introuvable")
    client_q = await _scoped_client_query(user, note.get("client_id") or "")
    if not await db.clients.find_one(client_q, {"_id": 1}):
        raise HTTPException(status_code=404, detail="Note introuvable")
    r = await db.client_notes.delete_one(q)
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Note introuvable")
    return {"ok": True}


def _parse_bulk_clients_text(raw: str) -> List[dict]:
    """Parse a pasted text into a list of client dicts.
    Detects the separator (\t, ;, or ,) per line. Columns expected in order:
    name, phone, email, address, postal_code, city, notes
    Only 'name' is mandatory. Blank lines and header lines are skipped.
    """
    if not raw:
        return []
    rows: List[dict] = []
    HEADERS = {"nom", "prenom", "prénom", "name", "nom / prenom", "nom / prénom", "client"}
    for line in raw.replace("\r", "").split("\n"):
        line = line.strip()
        if not line:
            continue
        # Detect separator
        if "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
        elif ";" in line:
            parts = [p.strip() for p in line.split(";")]
        elif "," in line and line.count(",") >= 2:
            parts = [p.strip() for p in line.split(",")]
        else:
            parts = [line]
        # Skip header
        if parts and parts[0].lower() in HEADERS:
            continue
        while len(parts) < 7:
            parts.append("")
        name, phone, email, address, postal_code, city, notes = parts[:7]
        if not name:
            continue
        rows.append({
            "name": name,
            "phone": phone,
            "email": email,
            "address": address,
            "postal_code": postal_code,
            "city": city,
            "notes": notes,
        })
    return rows


@api_router.post("/clients/bulk")
async def create_clients_bulk(data: ClientsBulkIn, user: dict = Depends(get_current_user)):
    """Accept either 'text' (paste) or 'clients' (list). Dedup by name+phone."""
    check_perm(user, "clients", "create")
    entries: List[dict] = []
    if data.clients:
        for c in data.clients:
            d = c.model_dump()
            if d.get("name"):
                entries.append(d)
    if data.text:
        entries.extend(_parse_bulk_clients_text(data.text))
    if not entries:
        raise HTTPException(status_code=400, detail="Aucun client à importer")

    created: List[dict] = []
    skipped: List[dict] = []
    for e in entries:
        q = cq(user, {"name": e["name"]})
        if e.get("phone"):
            q["phone"] = e["phone"]
        existing = await db.clients.find_one(q, {"_id": 0})
        if existing:
            skipped.append({"name": e["name"], "reason": "déjà présent"})
            continue
        doc = with_company({"id": str(uuid.uuid4()), "created_at": now_iso(), "created_by": user["id"], **e}, user)
        await db.clients.insert_one(doc.copy())
        created.append(doc)
    return {"created_count": len(created), "skipped_count": len(skipped), "created": created, "skipped": skipped}


# ---------------- Clients File Import (CSV / XLSX) ----------------
# iter138 : Import fichier avec wizard côté frontend.
# STRICT : ne touche QUE la collection `clients`. N'écrit AUCUNE vente / projet / facture.

CLIENT_IMPORT_FIELDS = [
    {"key": "name", "label": "Nom complet (une seule colonne)", "required": False},
    {"key": "first_name", "label": "Prénom", "required": False},
    {"key": "last_name", "label": "Nom", "required": False},
    {"key": "phone", "label": "Téléphone", "required": False},
    {"key": "email", "label": "Email", "required": False},
    {"key": "address", "label": "Adresse", "required": False},
    {"key": "postal_code", "label": "Code postal", "required": False},
    {"key": "city", "label": "Ville", "required": False},
    {"key": "notes", "label": "Notes", "required": False},
]

# Heuristiques d'auto-mapping des colonnes courantes → champ QYLOT
_IMPORT_AUTOMAP = {
    "name": ["nom prenom", "prenom nom", "nom / prenom", "nom / prénom", "nom complet", "client", "name", "fullname", "full name"],
    "first_name": ["prenom", "prénom", "prénom du contact", "prenom du contact", "firstname", "first name", "first_name", "given name"],
    "last_name": ["nom", "nom du contact", "nom de famille", "lastname", "last name", "last_name", "family name", "surname"],
    "phone": ["telephone", "téléphone", "tel", "tél", "portable", "mobile", "phone", "gsm", "numero", "numéro", "téléphone portable", "telephone portable", "téléphone fixe", "telephone fixe"],
    "email": ["email", "e-mail", "mail", "courriel", "adresse mail"],
    "address": ["adresse", "adresse postale", "rue", "address", "street"],
    "postal_code": ["cp", "code postal", "codepostal", "postal_code", "postal code", "zip", "zipcode", "zip code"],
    "city": ["ville", "commune", "city", "town", "localite", "localité"],
    "notes": ["note", "notes", "remarque", "remarques", "commentaire", "commentaires", "commentaire du contact", "observation", "observations"],
}


def _norm_header(s: str) -> str:
    import unicodedata as _ud
    s = _ud.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return " ".join(s.lower().strip().split())


def _auto_map_headers(headers: List[str]) -> dict:
    mapping: dict = {}
    used_field: set = set()
    for i, h in enumerate(headers):
        nh = _norm_header(h)
        if not nh:
            continue
        for field, aliases in _IMPORT_AUTOMAP.items():
            if field in used_field:
                continue
            if nh in aliases or any(nh == a or nh.startswith(a + " ") for a in aliases):
                mapping[str(i)] = field
                used_field.add(field)
                break
    return mapping


def _read_csv_bytes(raw: bytes) -> List[List[str]]:
    # Détecte encoding et séparateur
    text = None
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise HTTPException(status_code=400, detail="Impossible de lire l'encodage du fichier")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        delim = dialect.delimiter
    except Exception:
        # Fallback : détection par comptage
        counts = {d: sample.count(d) for d in [";", ",", "\t", "|"]}
        delim = max(counts, key=counts.get) if any(counts.values()) else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows: List[List[str]] = []
    for row_number, row in enumerate(reader, start=1):
        if row_number > MAX_IMPORT_ROWS + 1:  # header + bounded data rows
            raise HTTPException(status_code=413, detail=f"Import limité à {MAX_IMPORT_ROWS} lignes")
        if len(row) > MAX_IMPORT_COLUMNS:
            raise HTTPException(status_code=413, detail=f"Import limité à {MAX_IMPORT_COLUMNS} colonnes")
        if any(len(cell or "") > MAX_IMPORT_CELL_CHARS for cell in row):
            raise HTTPException(status_code=413, detail=f"Cellule trop longue (max {MAX_IMPORT_CELL_CHARS} caractères)")
        rows.append(row)
    return rows


def _read_xlsx_bytes(raw: bytes) -> List[List[str]]:
    try:
        import openpyxl  # type: ignore
    except ImportError:
        raise HTTPException(status_code=500, detail="Support Excel indisponible (openpyxl manquant)")
    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception:
        logger.exception("Invalid Excel import")
        raise HTTPException(status_code=400, detail="Fichier Excel invalide")
    ws = wb.active
    if ws.max_row > MAX_IMPORT_ROWS + 1:
        wb.close()
        raise HTTPException(status_code=413, detail=f"Import limité à {MAX_IMPORT_ROWS} lignes")
    if ws.max_column > MAX_IMPORT_COLUMNS:
        wb.close()
        raise HTTPException(status_code=413, detail=f"Import limité à {MAX_IMPORT_COLUMNS} colonnes")
    rows: List[List[str]] = []
    for row_number, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if row_number > MAX_IMPORT_ROWS + 1:
            wb.close()
            raise HTTPException(status_code=413, detail=f"Import limité à {MAX_IMPORT_ROWS} lignes")
        values = ["" if v is None else str(v) for v in row]
        if len(values) > MAX_IMPORT_COLUMNS:
            wb.close()
            raise HTTPException(status_code=413, detail=f"Import limité à {MAX_IMPORT_COLUMNS} colonnes")
        if any(len(cell) > MAX_IMPORT_CELL_CHARS for cell in values):
            wb.close()
            raise HTTPException(status_code=413, detail=f"Cellule trop longue (max {MAX_IMPORT_CELL_CHARS} caractères)")
        rows.append(values)
    wb.close()
    return rows


@api_router.post("/clients/import/parse")
async def parse_import_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Étape 1 : parse le fichier (CSV/XLSX) et renvoie les en-têtes + un aperçu.
    Ne crée AUCUN client. Retourne aussi une proposition d'auto-mapping.
    """
    check_perm(user, "clients", "create")
    raw = await _read_upload_limited(file)
    fname = (file.filename or "").lower()
    if fname.endswith(".xlsx") or fname.endswith(".xlsm"):
        rows = _read_xlsx_bytes(raw)
    elif fname.endswith(".csv") or fname.endswith(".tsv") or fname.endswith(".txt"):
        rows = _read_csv_bytes(raw)
    else:
        # Tentative CSV par défaut
        rows = _read_csv_bytes(raw)
    # Filtre les lignes totalement vides
    rows = [r for r in rows if any((c or "").strip() for c in r)]
    if not rows:
        raise HTTPException(status_code=400, detail="Fichier vide")
    headers = [(h or "").strip() for h in rows[0]]
    data_rows = rows[1:]
    # Uniformise le nombre de colonnes
    ncols = len(headers)
    normalized = [[(r[i] if i < len(r) else "") for i in range(ncols)] for r in data_rows]
    preview = normalized[:20]
    import_id = str(uuid.uuid4())
    await db.client_import_batches.insert_one(with_company({
        "id": import_id,
        "user_id": user["id"],
        "rows": normalized,
        "created_at": now_iso(),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=IMPORT_BATCH_TTL_MINUTES),
    }, user))
    return {
        "import_id": import_id,
        "headers": headers,
        "row_count": len(normalized),
        "preview": preview,
        "auto_mapping": _auto_map_headers(headers),
        "fields": CLIENT_IMPORT_FIELDS,
    }


ImportCell = Annotated[str, Field(max_length=MAX_IMPORT_CELL_CHARS)]


class ClientImportExecuteIn(BaseModel):
    # mapping : {column_index_str: field_key}. Colonnes non mappées = ignorées.
    mapping: Dict[str, str] = Field(max_length=MAX_IMPORT_COLUMNS)
    # `import_id` is the normal browser flow. Bounded rows remain accepted for
    # backwards-compatible API clients and controlled migrations.
    import_id: Optional[str] = Field(default=None, min_length=36, max_length=36)
    rows: List[List[ImportCell]] = Field(default_factory=list, max_length=MAX_IMPORT_ROWS)
    # Stratégie de dédoublonnage par téléphone/email :
    #   "ignore" (défaut) — saute les doublons
    #   "update"          — met à jour la fiche existante
    #   "create"          — crée quand même une nouvelle fiche
    duplicate_strategy: Optional[Literal["ignore", "update", "create"]] = "ignore"
    # iter146 : catégorie à assigner aux clients nouvellement créés (ex. "archives").
    # Ignorée pour les fiches mises à jour ou ignorées (doublons).
    assign_category: Optional[str] = Field(default=None, max_length=40, pattern=r"^[a-z0-9_]+$")

    @model_validator(mode="after")
    def validate_import_shape(self):
        if not self.import_id and not self.rows:
            raise ValueError("import_id ou lignes d'import requis")
        if any(len(row) > MAX_IMPORT_COLUMNS for row in self.rows):
            raise ValueError(f"Import limité à {MAX_IMPORT_COLUMNS} colonnes")
        return self


@api_router.post("/clients/import/execute")
async def execute_import_file(data: ClientImportExecuteIn, user: dict = Depends(get_current_user)):
    """Étape 2 : crée / met à jour les clients selon le mapping validé par l'utilisateur.
    STRICT : n'écrit QUE dans la collection `clients`. Aucun projet / vente / facture.
    """
    check_perm(user, "clients", "create")
    rows = data.rows
    batch = None
    if data.import_id:
        batch = await db.client_import_batches.find_one(cq(user, {
            "id": data.import_id,
            "user_id": user["id"],
            "expires_at": {"$gt": datetime.now(timezone.utc)},
        }), {"_id": 0})
        if not batch:
            raise HTTPException(status_code=404, detail="Import expiré ou introuvable")
        rows = batch.get("rows") or []
    if not rows:
        raise HTTPException(status_code=400, detail="Aucune ligne à importer")
    mapping = data.mapping or {}
    if not mapping:
        raise HTTPException(status_code=400, detail="Aucune colonne mappée")
    # Inversion : field_key -> column_index
    field_to_col: dict = {}
    for col_idx, field_key in mapping.items():
        if field_key and field_key in {f["key"] for f in CLIENT_IMPORT_FIELDS}:
            try:
                field_to_col[field_key] = int(col_idx)
            except (TypeError, ValueError):
                continue
    if "name" not in field_to_col and "first_name" not in field_to_col and "last_name" not in field_to_col:
        raise HTTPException(status_code=400, detail="Vous devez mapper au moins « Prénom », « Nom » ou « Nom complet »")

    strategy = data.duplicate_strategy or "ignore"
    company_id = company_id_of(user)

    created: List[dict] = []
    updated: List[dict] = []
    skipped: List[dict] = []
    errors: List[dict] = []

    def _cell(row: List[str], key: str) -> str:
        idx = field_to_col.get(key)
        if idx is None or idx >= len(row):
            return ""
        return (row[idx] or "").strip()

    for i, row in enumerate(rows):
        try:
            # iter148 : reconstitue le nom depuis 1 à 3 colonnes possibles :
            #   - `name` (colonne unique déjà « Prénom Nom »)
            #   - `first_name` + `last_name` (colonnes séparées, concaténées « Prénom Nom »)
            name_full = _cell(row, "name")
            if not name_full:
                first = _cell(row, "first_name")
                last = _cell(row, "last_name")
                name = " ".join([p for p in (first, last) if p]).strip()
            else:
                name = name_full
            if not name:
                skipped.append({"line": i + 1, "name": "", "reason": "nom manquant"})
                continue
            phone = _cell(row, "phone")
            email = _cell(row, "email").lower()
            payload = {
                "name": name,
                "phone": phone,
                "email": email,
                "address": _cell(row, "address"),
                "postal_code": _cell(row, "postal_code"),
                "city": _cell(row, "city"),
                "notes": _cell(row, "notes"),
            }
            # Détection doublon : phone OU email (dans la company)
            existing = None
            if phone or email:
                or_terms = []
                if phone:
                    or_terms.append({"phone": phone})
                if email:
                    or_terms.append({"email": email})
                if or_terms:
                    existing = await db.clients.find_one(
                        {"company_id": company_id, "$or": or_terms}, {"_id": 0}
                    )
            if existing:
                if strategy == "ignore":
                    skipped.append({"line": i + 1, "name": name, "reason": "doublon (téléphone/email)", "existing_id": existing.get("id")})
                    continue
                if strategy == "update":
                    # On ne remplace que les champs non vides pour ne pas écraser des données
                    upd = {k: v for k, v in payload.items() if v}
                    if upd:
                        await db.clients.update_one(
                            {"company_id": company_id, "id": existing["id"]},
                            {"$set": upd},
                        )
                    merged = {**existing, **upd}
                    updated.append(merged)
                    continue
                # strategy == "create" : on tombe dans le bloc création ci-dessous
            doc = with_company(
                {"id": str(uuid.uuid4()), "created_at": now_iso(), "created_by": user["id"], **payload},
                user,
            )
            # iter146 : catégorie assignée à l'import (généralement "archives") — pré-remplie
            # sur les nouvelles fiches uniquement. La rétro-catégorisation iter142 ne touchera
            # pas ces clients puisqu'ils auront déjà une categorie.
            if data.assign_category:
                doc["categories"] = [{
                    "category_key": data.assign_category,
                    "sub_status_key": None,
                    "updated_at": now_iso(),
                    "_auto": True,
                    "_import": True,
                }]
            await db.clients.insert_one(doc.copy())
            created.append(doc)
        except Exception as e:  # noqa: BLE001
            errors.append({"line": i + 1, "error": str(e)})

    result = {
        "created_count": len(created),
        "updated_count": len(updated),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }
    await log_audit(
        user, "import", "clients", data.import_id or "direct",
        after={
            "created_count": len(created), "updated_count": len(updated),
            "skipped_count": len(skipped), "error_count": len(errors),
            "duplicate_strategy": strategy,
        },
    )
    if batch:
        await db.client_import_batches.delete_one(cq(user, {"id": data.import_id, "user_id": user["id"]}))
    return result


# ---------------- Client Import PDF (extraction IA) ----------------
# iter143 : Import un devis PDF (ou une image) → extrait uniquement les infos client
# (nom, prénom, téléphone, email, adresse, code postal, ville, date du devis).
# STRICT : n'écrit QUE dans la collection `clients`. Aucun sale/project créé.

_CLIENT_PDF_EXTRACT_SYSTEM = """Tu es un extracteur strict d'informations CLIENT depuis un devis / bon de commande.
Ta seule mission : identifier les coordonnées du client destinataire du document et la date du devis.
Tu ignores absolument tout le reste (produits, prestations, montants, conditions générales, logo, coordonnées du vendeur).

RÈGLE ABSOLUE : tu recopies LITTÉRALEMENT ce qui est ÉCRIT sur le document.
Tu ne devines, ne complètes, ne corriges, n'infères RIEN. Si tu hésites → chaîne vide.

Renvoie STRICTEMENT ce JSON, sans texte autour, sans commentaire, sans balises markdown :

{
  "name": "Nom et prénom du client (ex: 'Dupont Jean' ou 'Jean Dupont' — préserve l'ordre et la casse du document)",
  "phone": "Téléphone du client (recopie EXACTE avec espaces/points/+ tels qu'écrits, sinon '')",
  "email": "Email du client si présent, sinon ''",
  "address": "Numéro + rue UNIQUEMENT (SANS le CP ni la ville), recopie mot-à-mot, sinon ''",
  "postal_code": "Code postal (5 chiffres pour la France, sinon '')",
  "city": "Ville seule (sans CP), recopie EXACTE (respecte majuscules/tirets), sinon ''",
  "devis_date": "Date du devis au format YYYY-MM-DD si trouvée, sinon ''",
  "confidence": "high | medium | low"
}

Règles strictes :
- RECOPIE MOT POUR MOT. Ne reformule pas. Ne corrige pas les fautes. Ne complète pas les abréviations ("St" reste "St").
- N'invente RIEN. Si une information n'est pas 100% certaine, renvoie une chaîne vide. PLUTÔT VIDE QUE FAUX.
- Le client est le destinataire du devis (« Client », « À l'attention de », « Facturer à », « Livré à ») — JAMAIS l'entreprise émettrice (en-tête/pied avec SIRET, IBAN, logo).
- Pour un nom en majuscules type « MARTIN Jean », renvoie « MARTIN Jean » tel quel.
- Convertis les dates FR (JJ/MM/AAAA, « 15 mars 2026 ») vers YYYY-MM-DD. En cas d'ambiguïté → ''.
- Ne remplis JAMAIS les champs produits, prestations, montants — ils sont hors périmètre.
"""


class ClientPdfCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: Optional[str] = Field(default="", max_length=40)
    email: Optional[str] = Field(default="", max_length=320)
    address: Optional[str] = Field(default="", max_length=500)
    postal_code: Optional[str] = Field(default="", max_length=20)
    city: Optional[str] = Field(default="", max_length=120)
    notes: Optional[str] = Field(default="", max_length=5000)
    devis_date: Optional[str] = Field(default="", pattern=r"^(|\d{4}-\d{2}-\d{2})$")
    duplicate_strategy: Optional[Literal["ignore", "update", "create"]] = "ignore"
    # iter146 : catégorie à assigner à la fiche créée (ex. "archives").
    assign_category: Optional[str] = Field(default=None, max_length=40, pattern=r"^[a-z0-9_]+$")

    @field_validator("devis_date")
    @classmethod
    def validate_pdf_quote_date(cls, value: Optional[str]) -> Optional[str]:
        if value:
            date.fromisoformat(value)
        return value


@api_router.post("/clients/import/pdf/parse")
async def parse_client_pdf(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Étape 1 : extrait les infos client d'un devis PDF (ou image) via GPT-4o-mini vision.
    Renvoie la fiche pré-remplie + un signalement de doublon éventuel. Ne crée AUCUN client.
    """
    check_perm(user, "clients", "create")
    _require_external_ai_enabled()
    raw = await _read_upload_limited(file)

    mime = (file.content_type or "").lower()
    fname = (file.filename or "").lower()
    images_b64: List[str] = []
    if mime == "application/pdf" or fname.endswith(".pdf"):
        try:
            import fitz  # pymupdf
            doc = fitz.open(stream=raw, filetype="pdf")
            if doc.page_count > MAX_PDF_PAGES:
                doc.close()
                raise HTTPException(status_code=413, detail=f"PDF trop long (max {MAX_PDF_PAGES} pages)")
            # Limite : 3 premières pages suffisent pour l'en-tête client
            for i, page in enumerate(doc):
                if i >= 3:
                    break
                # iter203 : DPI 240 pour OCR plus fiable sur scans/photocopies.
                pix = page.get_pixmap(dpi=240)
                images_b64.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))
            doc.close()
        except HTTPException:
            raise
        except Exception:
            logger.exception("Unreadable client import PDF")
            raise HTTPException(status_code=400, detail="PDF illisible")
    elif mime.startswith("image/") or fname.endswith((".png", ".jpg", ".jpeg", ".webp", ".heic")):
        images_b64.append(base64.b64encode(raw).decode("utf-8"))
    else:
        raise HTTPException(status_code=400, detail="Format non supporté (PDF ou image)")

    if not images_b64:
        raise HTTPException(status_code=400, detail="Aucune page à analyser")

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        # iter203 : GPT-4o (pas -mini) pour extraction fiable depuis photo/scan.
        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"client-pdf-{user['id']}-{uuid.uuid4().hex[:8]}",
            system_message=_CLIENT_PDF_EXTRACT_SYSTEM,
        ).with_model("openai", "gpt-4o")
        reply = await chat.send_message(UserMessage(
            text=f"Extrais UNIQUEMENT les infos client de ce devis ({len(images_b64)} page(s)). RECOPIE MOT POUR MOT : nom, prénom, adresse, code postal, ville, numéro, date. Renvoie le JSON strict.",
            file_contents=[ImageContent(b) for b in images_b64],
        ))
    except Exception:
        logger.exception("Client PDF extraction error")
        raise HTTPException(status_code=502, detail="Analyse IA temporairement indisponible")

    import json as _json
    txt = (reply or "").strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]
        txt = txt.strip()
    try:
        parsed = _json.loads(txt)
    except Exception:
        i, j = txt.find("{"), txt.rfind("}")
        if i >= 0 and j > i:
            try:
                parsed = _json.loads(txt[i:j + 1])
            except Exception:
                raise HTTPException(status_code=422, detail="Réponse IA non JSON")
        else:
            raise HTTPException(status_code=422, detail="Réponse IA non JSON")

    def _s(v: Any) -> str:
        return (str(v).strip() if v is not None else "")

    client_data = {
        "name": _s(parsed.get("name")),
        "phone": _s(parsed.get("phone")),
        "email": _s(parsed.get("email")).lower(),
        "address": _s(parsed.get("address")),
        "postal_code": _s(parsed.get("postal_code")),
        "city": _s(parsed.get("city")),
        "devis_date": _s(parsed.get("devis_date")),
        "confidence": _s(parsed.get("confidence")) or "medium",
    }

    # Détection doublon (téléphone / email) dans la company
    duplicate = None
    or_terms = []
    if client_data["phone"]:
        or_terms.append({"phone": client_data["phone"]})
    if client_data["email"]:
        or_terms.append({"email": client_data["email"]})
    if or_terms:
        existing = await db.clients.find_one(
            {"company_id": company_id_of(user), "$or": or_terms},
            {"_id": 0, "id": 1, "name": 1, "phone": 1, "email": 1, "city": 1},
        )
        if existing:
            duplicate = existing

    return {"client": client_data, "duplicate": duplicate, "pages_analyzed": len(images_b64)}


@api_router.post("/clients/import/pdf/create")
async def create_client_from_pdf(data: ClientPdfCreateIn, user: dict = Depends(get_current_user)):
    """Étape 2 : crée / met à jour la fiche client validée par l'utilisateur.
    STRICT : ne touche QUE la collection `clients`.
    La date du devis est ajoutée en tête des notes pour traçabilité (pas de nouveau champ).
    """
    check_perm(user, "clients", "create")
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom requis")
    company_id = company_id_of(user)
    # Notes = "Devis du <date>\n<notes optionnelles>"
    notes_parts = []
    if data.devis_date:
        notes_parts.append(f"Devis du {data.devis_date}")
    if data.notes:
        notes_parts.append(data.notes.strip())
    notes_str = "\n".join(notes_parts)

    payload = {
        "name": name,
        "phone": (data.phone or "").strip(),
        "email": (data.email or "").strip().lower(),
        "address": (data.address or "").strip(),
        "postal_code": (data.postal_code or "").strip(),
        "city": (data.city or "").strip(),
        "notes": notes_str,
    }

    # Détection doublon
    existing = None
    or_terms = []
    if payload["phone"]:
        or_terms.append({"phone": payload["phone"]})
    if payload["email"]:
        or_terms.append({"email": payload["email"]})
    if or_terms:
        existing = await db.clients.find_one(
            {"company_id": company_id, "$or": or_terms}, {"_id": 0}
        )

    strategy = data.duplicate_strategy or "ignore"
    if existing:
        if strategy == "ignore":
            return {"action": "skipped", "reason": "doublon (téléphone/email)", "existing": existing}
        if strategy == "update":
            upd = {k: v for k, v in payload.items() if v}
            if upd:
                await db.clients.update_one(
                    {"company_id": company_id, "id": existing["id"]},
                    {"$set": upd},
                )
            merged = {**existing, **upd}
            return {"action": "updated", "client": merged}
        # "create" → tombe dans le bloc création
    doc = with_company(
        {"id": str(uuid.uuid4()), "created_at": now_iso(), "created_by": user["id"], **payload},
        user,
    )
    # iter146 : catégorie optionnelle assignée à l'import (ex. "archives")
    if data.assign_category:
        doc["categories"] = [{
            "category_key": data.assign_category,
            "sub_status_key": None,
            "updated_at": now_iso(),
            "_auto": True,
            "_import": True,
        }]
    await db.clients.insert_one(doc.copy())
    return {"action": "created", "client": doc}


# ---------------- Sales + Auto Project ----------------

def _norm_name(s: str) -> str:
    """Case-insensitive + whitespace-tolerant + accent-insensitive name key."""
    import unicodedata as _ud
    s = _ud.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def _own_sales_filter(user: dict) -> dict:
    """
    Build the "own" scope filter for sales.
    iter122 : match STRICT sur commercial_user_id / commercial_2_user_id (source de vérité).
    iter198 : fallback élargi au PRÉNOM (accent-insensible) quand `commercial_user_id`
    est vide — permet à Théo Dudal de voir les ventes créées avec `commercial="Théo"`
    même si `_reconcile_sales_commercials` n'a pas encore tourné.
    """
    import re as _re
    name = (user or {}).get("name") or ""
    uid = (user or {}).get("id") or "__none__"
    ors: List[dict] = [
        {"commercial_user_id": uid},
        {"commercial_2_user_id": uid},
    ]
    key = _norm_name(name)
    if key:
        # Nom complet exact (case-insensitive) — sécurité rétro-compat
        pattern_full = _re.compile(rf"^\s*{_re.escape(name.strip())}\s*$", _re.IGNORECASE)
        ors.append({"$and": [{"commercial_user_id": {"$in": [None, ""]}}, {"commercial": {"$regex": pattern_full}}]})
        ors.append({"$and": [{"commercial_2_user_id": {"$in": [None, ""]}}, {"commercial_2": {"$regex": pattern_full}}]})
    return {"$or": ors}


def _levenshtein(a: str, b: str) -> int:
    """Distance de Levenshtein simple (courts prénoms, O(n·m) suffisant)."""
    if a == b:
        return 0
    if not a: return len(b)
    if not b: return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (0 if ca == cb else 1))
        prev = curr
    return prev[-1]


async def _resolve_commercial_user_id(user: dict, commercial_name: str) -> Optional[str]:
    """
    Trouve l'utilisateur commercial dont le nom matche `commercial_name`.
    Stratégie (iter43 → iter194) :
      1) match exact sur clé normalisée (case/accent/espace-insensitive)
      2) match sur PRÉNOM (premier token) — accepté uniquement si UNIQUE
      Ambigu ou aucun → None (jamais rattaché au hasard)

    iter194 — Suppression du fuzzy Levenshtein ≤ 1 sur le prénom.
    Il provoquait des attributions silencieuses ENTRE prénoms distincts d'1 lettre
    (ex : « Kelian » → « Kilian Blanc », « Théo » → « Léo »). L'utilisateur doit
    choisir explicitement via l'écran « Ventes non associées » quand la
    correspondance est ambiguë.
    """
    if not commercial_name:
        return None
    key = _norm_name(commercial_name)
    if not key:
        return None
    users = await db.users.find(
        {"company_id": company_id_of(user), "role": {"$in": ["commercial", "responsable", "admin"]}},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(500)
    # Pass 1 : exact normalized
    for u in users:
        if _norm_name(u.get("name") or "") == key:
            return u.get("id")
    # Pass 2 : first-name only (UNIQUE)
    first_token = key.split(" ", 1)[0]
    if not first_token:
        return None
    exact_first = [u for u in users if (_norm_name(u.get("name") or "").split(" ", 1)[0] == first_token)]
    if len(exact_first) == 1:
        return exact_first[0].get("id")
    return None


@api_router.get("/sales")
async def list_sales(user: dict = Depends(get_current_user)):
    check_perm(user, "sales", "view", "own")
    scope = perm_scope(user, "sales", "view")
    q = cq(user)
    if scope == "own":
        q.update(_own_sales_filter(user))
    if _is_prospect_role(user):
        q.update(_prospect_sales_filter(user))
    sales = await db.sales.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
    # enrich with client name
    ids = list({s["client_id"] for s in sales})
    clients = await db.clients.find(cq(user, {"id": {"$in": ids}}), {"_id": 0}).to_list(5000)
    cmap = {c["id"]: c for c in clients}
    for s in sales:
        c = cmap.get(s["client_id"], {})
        s["client_name"] = c.get("name", "")
        s["client_phone"] = c.get("phone", "")
        s["client_address"] = c.get("address", "")
        s["client_postal_code"] = c.get("postal_code", "")
        s["client_city"] = c.get("city", "")
        s.setdefault("commercial", "")
        s.setdefault("source", "")
        s.setdefault("payment_installments", 1)
        s.setdefault("commission_rate", 0.10)
        s.setdefault("commission_paid", False)
        s.setdefault("commission_month", "")
    return sales

@api_router.get("/sales/commercial-month-ca")
async def sales_commercial_month_ca(
    commercial_user_id: Optional[str] = Query(None),
    commercial_name: Optional[str] = Query(None),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    exclude_sale_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """iter113 : renvoie le CA cumulé d'un commercial pour un mois donné (source de vérité
    pour la preview 'Taux appliqué' du type de commission 'Évolutive selon CA').
    `exclude_sale_id` permet d'exclure la vente en cours d'édition pour projeter le CA cible.
    Accepte soit `commercial_user_id`, soit `commercial_name` (résolu côté serveur)."""
    check_perm(user, "sales", "view", "own")
    month = _validated_month(month)
    cuid = commercial_user_id
    if not cuid and commercial_name:
        cuid = await _resolve_commercial_user_id(user, commercial_name)
    if not cuid:
        return {"commercial_user_id": None, "month": month, "total_ca": 0.0}
    q = {
        "company_id": company_id_of(user),
        "sale_date": {"$regex": f"^{month}"},
        "$or": [
            {"commercial_user_id": cuid},
            {"commercial_2_user_id": cuid},
        ],
    }
    if exclude_sale_id:
        q["id"] = {"$ne": exclude_sale_id}
    sales = await db.sales.find(q, {"_id": 0}).to_list(5000)
    total = 0.0
    for s in sales:
        if (s.get("status") or "") in ("annule", "litige"):
            continue
        amt = float(s.get("amount") or 0)
        is_de = bool(s.get("is_de")) and bool((s.get("commercial_2") or "").strip())
        if is_de:
            if s.get("commercial_user_id") == cuid:
                total += amt * 0.5
            if s.get("commercial_2_user_id") == cuid:
                total += amt * 0.5
        else:
            if s.get("commercial_user_id") == cuid:
                total += amt
    return {"commercial_user_id": cuid, "month": month, "total_ca": round(total, 2)}


async def _require_active_sale_status(user: dict, status: str) -> None:
    settings = await db.settings.find_one(
        {"company_id": company_id_of(user), "kind": "global"},
        {"_id": 0, "sale_statuses": 1},
    ) or {}
    allowed = {item["value"] for item in _resolve_statuses(settings) if item.get("active", True)}
    if status not in allowed:
        raise HTTPException(status_code=422, detail="Statut de vente inconnu ou désactivé")


@api_router.post("/sales")
async def create_sale(data: SaleIn, user: dict = Depends(get_current_user)):
    check_perm(user, "sales", "create")
    await _require_active_sale_status(user, data.status)
    c = await find_or_create_client(data.client_id, data.client, user)
    sid = str(uuid.uuid4())
    # Normalize prestations (products with quantity 1..10). Fallback: infer from service string.
    prestas = [{"name": (p.name or "").strip(), "quantity": max(1, min(10, int(p.quantity or 1)))}
               for p in (data.prestations or []) if (p.name or "").strip()]
    sale = with_company({
        "id": sid,
        "client_id": c["id"],
        "bdc": data.bdc or "",
        "service": data.service,
        "prestations": prestas,
        "amount": float(data.amount or 0),
        "payment_method": data.payment_method or "cheque",
        "payment_installments": int(data.payment_installments or 1),
        "financement_amount": float(data.financement_amount) if data.financement_amount is not None else None,
        "comptant_installments": int(data.comptant_installments or 1),
        "commission_rate": float(data.commission_rate if data.commission_rate is not None else 0.0),
        # DE only: independent rate for the 2nd commercial. Defaults to 0 (must be set explicitly by admin/responsable).
        "commission_rate_2": (float(data.commission_rate_2) if (getattr(data, "is_de", False) and data.commission_rate_2 is not None)
                              else (0.0 if getattr(data, "is_de", False) else None)),
        # iter27: per-sale commission mode. Default "fixed" — no automatic threshold logic.
        "commission_type": (getattr(data, "commission_type", None) or "fixed"),
        "commission_type_2": (getattr(data, "commission_type_2", None) if getattr(data, "is_de", False) else None),
        "discount_percent": (float(getattr(data, "discount_percent", None)) if getattr(data, "discount_percent", None) is not None else None),
        # iter130 : persistance des paramètres du palier evolutive_ca — indispensable pour
        # que le reconcile puisse recalculer commission_rate à chaque mutation.
        "evolutive_ca_threshold": (float(getattr(data, "evolutive_ca_threshold", None)) if getattr(data, "evolutive_ca_threshold", None) is not None else None),
        "evolutive_rate_below": (float(getattr(data, "evolutive_rate_below", None)) if getattr(data, "evolutive_rate_below", None) is not None else None),
        "evolutive_rate_above": (float(getattr(data, "evolutive_rate_above", None)) if getattr(data, "evolutive_rate_above", None) is not None else None),
        "commercial": data.commercial or "",
        "commercial_2": (data.commercial_2 or "") if getattr(data, "is_de", False) else "",
        "commercial_user_id": (await _resolve_commercial_user_id(user, data.commercial)) if data.commercial else None,
        "commercial_2_user_id": (await _resolve_commercial_user_id(user, data.commercial_2)) if (getattr(data, "is_de", False) and data.commercial_2) else None,
        # iter42: flag les ventes dont un slot commercial n'a pas pu être résolu (pour revue admin)
        "commercial_unmatched": bool((data.commercial and not _is_direction(data.commercial) and not (await _resolve_commercial_user_id(user, data.commercial))) or (getattr(data, "is_de", False) and data.commercial_2 and not _is_direction(data.commercial_2) and not (await _resolve_commercial_user_id(user, data.commercial_2)))),
        "is_de": bool(getattr(data, "is_de", False)),
        # commercial_share is DEPRECATED. CA is always split 50/50 for DE sales.
        "commercial_share": 0.5,
        "source": data.source or "",
        "commission_paid": bool(data.commission_paid or False),
        "commission_month": data.commission_month or ((data.sale_date or "")[:7]) or datetime.now(timezone.utc).strftime("%Y-%m"),
        "sale_date": data.sale_date,
        "desired_intervention_date": data.desired_intervention_date,
        "status": data.status,
        "notes": data.notes or "",
        **(await _prospecteur_fields(user, data.prospecteur_id, data.prospecteur_commission)),
        "created_by": user["id"],
        "created_at": now_iso(),
    }, user)
    await db.sales.insert_one(sale.copy())
    await log_audit(user, "create", "sale", sid, after=sale)
    # iter137 : catégorise le client automatiquement selon le statut de vente
    await _auto_assign_client_category_from_sale(user, sale)
    # iter113/123 : recalcule les taux evolutive_ca pour le(s) commercial(aux) impacté(s)
    # (mois issu de `sale_date` — cohérent avec la page Ventes)
    try:
        _sm = (sale.get("sale_date") or "")[:7]
        await _reconcile_after_sale_mutation(
            company_id_of(user),
            [
                (sale.get("commercial_user_id"), _sm),
                (sale.get("commercial_2_user_id"), _sm),
            ],
        )
    except Exception as _e:
        logger.warning(f"reconcile evolutive_ca on create_sale failed: {_e}")
    # iter93 : check bonuses (async, best-effort)
    try:
        await _check_and_award_bonuses(user, [sale.get("commercial"), sale.get("commercial_2")])
    except Exception as _e:
        logger.warning(f"bonus check on create_sale failed: {_e}")
    # Auto-create project unless the sale is cancelled or in litigation
    if sale["status"] not in ("annule", "litige"):
        proj = with_company({
            "id": str(uuid.uuid4()),
            "sale_id": sid,
            "client_id": c["id"],
            "service": data.service,
            "prestations": prestas,
            "status": ("en_cours" if data.desired_intervention_date else "a_planifier"),
            "priority": "moyenne",
            "scheduled_date": data.desired_intervention_date,
            "assigned_to": [],
            "duration_days": 1,
            "notes": "",
            "photos": [],
            "created_at": now_iso(),
        }, user)
        await db.projects.insert_one(proj.copy())
    sale["client_name"] = c.get("name", "")
    # Optional in-app notification for admins
    await emit_notification(
        company_id_of(user), "new_sales",
        title="Nouvelle vente",
        message=f"{user.get('name') or 'Un commercial'} a enregistré une vente de {sale['amount']:.0f} € — {c.get('name','')}",
        link_url="/ventes", roles=["admin"], exclude_user_id=user["id"],
    )
    return sale

@api_router.put("/sales/{sid}")
async def update_sale(sid: str, data: SaleUpdate, user: dict = Depends(get_current_user)):
    check_perm(user, "sales", "edit")
    # Commercial "own" scope can only update their own sales (including DE second-commercial slot)
    scope = perm_scope(user, "sales", "view")
    q = cq(user, {"id": sid})
    if scope == "own":
        q.update(_own_sales_filter(user))
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if "status" in updates:
        await _require_active_sale_status(user, updates["status"])
    # iter41: auto-link commercial name → user id on update
    if "commercial" in updates:
        updates["commercial_user_id"] = await _resolve_commercial_user_id(user, updates["commercial"])
    if "commercial_2" in updates:
        updates["commercial_2_user_id"] = await _resolve_commercial_user_id(user, updates["commercial_2"])
    if user.get("role") not in PROSPECT_COMM_ROLES:
        updates.pop("prospecteur_commission", None)
    if "prospecteur_id" in updates:
        _pf = await _prospecteur_fields(user, updates.pop("prospecteur_id"), updates.pop("prospecteur_commission", None))
        if _pf["prospecteur_id"] and user.get("role") in PROSPECT_COMM_ROLES and data.prospecteur_commission is None:
            _pf.pop("prospecteur_commission")
        elif _pf["prospecteur_id"] and user.get("role") not in PROSPECT_COMM_ROLES:
            _pf.pop("prospecteur_commission")
        updates.update(_pf)
    # iter99 : quand `sale_date` change, resync automatiquement `commission_month` sur le
    # nouveau mois. Garantit que toutes les pages (Commissions, Rapport, Dashboard) restent
    # cohérentes après changement de date de vente.
    if "sale_date" in updates and updates["sale_date"] and not updates.get("commission_month"):
        updates["commission_month"] = (updates["sale_date"] or "")[:7]
    # Normalize prestations list on update (products with quantity 1..10)
    if "prestations" in updates and isinstance(updates["prestations"], list):
        updates["prestations"] = [
            {"name": (p.get("name") or "").strip(), "quantity": max(1, min(10, int(p.get("quantity") or 1)))}
            for p in updates["prestations"] if (p.get("name") or "").strip()
        ]
    # iter38: fetch previous state BEFORE updating (for cancellation transition)
    exists = await db.sales.find_one(q, {"_id": 0})
    if not exists:
        raise HTTPException(status_code=404, detail="Vente introuvable")
    r = await db.sales.update_one(q, {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vente introuvable")
    sale = await db.sales.find_one(cq(user, {"id": sid}), {"_id": 0})
    # Sync prestations & service to any linked project so techs always see current products/qty
    sync_fields = {}
    if "prestations" in updates:
        sync_fields["prestations"] = updates["prestations"]
    if "service" in updates:
        sync_fields["service"] = updates["service"]
    if sync_fields:
        await db.projects.update_many(cq(user, {"sale_id": sid}), {"$set": sync_fields})

    # iter38/119/158 : cancellation workflow + auto-transition PROG.
    # - Statut vente vers `hides_from_projects` → soft-delete chantiers liés.
    # - Statut vente `attente_prog` (label "PROG") → le chantier "À planifier" bascule
    #   automatiquement en "En cours" (colonne renommée "PROG" côté UI). Demande Msg 350.
    if "status" in updates:
        prev_status = (exists.get("status") if exists else None)
        new_status = updates["status"]
        try:
            hiding_set = await _get_hiding_status_values(user)
        except Exception:
            hiding_set = {"annule", "litige"}
        was_hidden = prev_status in hiding_set
        is_hidden = new_status in hiding_set
        if is_hidden and not was_hidden:
            await db.projects.update_many(
                cq(user, {"sale_id": sid}),
                {"$set": {"cancelled": True, "cancelled_at": now_iso(), "cancelled_by": user.get("id")}},
            )
            await log_audit(user, "cancel", "sale", sid, after={"cancelled_projects": True, "trigger_status": new_status})
        elif was_hidden and not is_hidden:
            # iter52 : vente réactivée → réactiver le chantier soft-deleted (préserve
            # photos / notes / affectations). Si aucun chantier annulé n'existe, en créer un neuf.
            reactivated = await db.projects.update_many(
                cq(user, {"sale_id": sid, "cancelled": True}),
                {"$set": {"cancelled": False}, "$unset": {"cancelled_at": "", "cancelled_by": ""}},
            )
            await log_audit(user, "reactivate", "sale", sid, after={"projects_reactivated": reactivated.modified_count})
        # iter164 : suppression de l'auto-transition attente_prog → en_cours.
        # Le chantier reste dans « À planifier » tant qu'un utilisateur ne le
        # déplace pas manuellement. Seul le passage `chantier_fini` fait
        # avancer le chantier (voir _sync_project_status ailleurs).
    # If sale still active and no project exists, create one
    if sale and sale.get("status") not in ("annule", "litige"):
        existing = await db.projects.find_one(cq(user, {"sale_id": sid, "cancelled": {"$ne": True}}))
        if not existing:
            proj = with_company({
                "id": str(uuid.uuid4()), "sale_id": sid, "client_id": sale["client_id"],
                "service": sale["service"], "status": ("en_cours" if sale.get("desired_intervention_date") else "a_planifier"), "priority": "moyenne",
                "scheduled_date": sale.get("desired_intervention_date"), "assigned_to": [],
                "duration_days": 1, "notes": "", "photos": [], "created_at": now_iso(),
            }, user)
            await db.projects.insert_one(proj.copy())
    # iter93 : re-check bonuses if the sale still counts (best-effort)
    try:
        if sale and sale.get("status") not in ("annule", "litige"):
            await _check_and_award_bonuses(user, [sale.get("commercial"), sale.get("commercial_2")])
    except Exception as _e:
        logger.warning(f"bonus check on update_sale failed: {_e}")
    # iter137 : catégorise le client automatiquement selon le nouveau statut de vente
    if sale:
        await _auto_assign_client_category_from_sale(user, sale)
    # iter113 : recalcule les taux evolutive_ca pour l'ancien ET le nouveau (commercial_user_id, mois)
    try:
        cid = company_id_of(user)
        tuples = [
            (exists.get("commercial_user_id"), (exists.get("sale_date") or "")[:7]),
            (exists.get("commercial_2_user_id"), (exists.get("sale_date") or "")[:7]),
        ]
        if sale:
            tuples += [
                (sale.get("commercial_user_id"), (sale.get("sale_date") or "")[:7]),
                (sale.get("commercial_2_user_id"), (sale.get("sale_date") or "")[:7]),
            ]
        await _reconcile_after_sale_mutation(cid, tuples)
        # Re-fetch sale to return the up-to-date rates
        sale = await db.sales.find_one(cq(user, {"id": sid}), {"_id": 0}) or sale
    except Exception as _e:
        logger.warning(f"reconcile evolutive_ca on update_sale failed: {_e}")
    return sale


@api_router.post("/sales/check-attente-14j")
async def check_attente_14j(user: dict = Depends(get_current_user)):
    """iter162 / iter166 : idempotent — parcourt les ventes marquées
    `desired_intervention_date=attente_14j` et, pour chacune arrivée à J+14,
    émet une notification cloche (admin/responsable + commerciaux concernés).
    Le statut de la vente n'est PAS modifié automatiquement (choix utilisateur
    iter166 : "Ne modifie pas le statut de la vente")."""
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    from datetime import date as _date
    today = _date.today()
    q = cq(user, {"desired_intervention_date": "attente_14j"})
    sales = await db.sales.find(q, {"_id": 0}).to_list(2000)
    notified = 0
    for s in sales:
        # iter185 : la fenêtre 14 j ne s'applique qu'aux ventes encore « En attente prog ».
        # Dès que le statut a basculé (En attente FI, Chèque récupéré, Annulé, Virement reçu,
        # Non finançable…), on ne notifie plus le Jour J — la vente est déjà sortie du flux.
        if s.get("status") != "attente_prog":
            continue
        try:
            sd = _date.fromisoformat((s.get("sale_date") or "")[:10])
        except Exception:
            logger.debug("Date de vente historique invalide ignorée dans le rappel 14 jours")
            continue
        days_elapsed = (today - sd).days
        if days_elapsed < 14:
            continue
        if s.get("attente_14j_notified_at"):
            continue
        client = await db.clients.find_one(cq(user, {"id": s.get("client_id")}), {"_id": 0}) or {}
        title = f"Délai 14 jours écoulé — {client.get('name') or 'Client'}"
        message = f"La vente de {client.get('name') or 'ce client'} arrive à Jour J (attente 14 jours dépassée)."
        await emit_notification(
            company_id_of(user), "new_sales",
            title=title, message=message, link_url="/ventes",
            roles=["admin", "responsable"],
        )
        commercial_ids = [x for x in [s.get("commercial_user_id"), s.get("commercial_2_user_id")] if x]
        if commercial_ids:
            await emit_notification_to_users(
                company_id_of(user), commercial_ids,
                title=title, message=message, link_url="/ventes",
                category="attente_14j",
            )
        await db.sales.update_one(cq(user, {"id": s["id"]}), {"$set": {"attente_14j_notified_at": now_iso()}})
        notified += 1
    return {"scanned": len(sales), "notified": notified}


@api_router.delete("/sales/{sid}")
async def delete_sale(sid: str, user: dict = Depends(get_current_user)):
    check_perm(user, "sales", "delete")
    q = cq(user, {"id": sid})
    if perm_scope(user, "sales", "view") == "own":
        q.update(_own_sales_filter(user))
    before = await db.sales.find_one(q, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Vente introuvable")
    linked_projects = await db.projects.count_documents(cq(user, {"sale_id": sid}))
    if linked_projects:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "sale_has_projects",
                "message": "Cette vente possède un chantier. Archivez ou annulez la vente au lieu de la supprimer.",
                "project_count": linked_projects,
            },
        )
    r = await db.sales.delete_one(q)
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Vente introuvable")
    await log_audit(user, "delete", "sale", sid, before=before)
    # iter113/123 : recalcule les taux evolutive_ca pour le(s) commercial(aux) impacté(s)
    try:
        if before:
            _sm = (before.get("sale_date") or "")[:7]
            await _reconcile_after_sale_mutation(
                company_id_of(user),
                [
                    (before.get("commercial_user_id"), _sm),
                    (before.get("commercial_2_user_id"), _sm),
                ],
            )
    except Exception as _e:
        logger.warning(f"reconcile evolutive_ca on delete_sale failed: {_e}")
    return {"ok": True}


# ---------------- Projects (Chantiers) ----------------

async def _fetch_projects_list(user: dict, include_deleted: str, *, perm_resource: str = "projects", keep_closed: bool = False) -> list:
    """iter209 — logique partagée entre `/api/projects` (Chantiers, gated par
    `projects.view`) et `/api/planning/projects` (Planning, gated par
    `planning.view`). Le `perm_resource` détermine UNIQUEMENT le scope
    (own/team/all) — la permission a déjà été checkée par l'endpoint appelant.
    Ainsi, retirer `projects.view` n'assèche PAS le Planning : les deux vues
    sont désormais indépendantes.
    iter215 — `keep_closed=True` (utilisé par Planning) conserve TOUS les chantiers
    quel que soit le statut de la vente sauf `annule`. Le Kanban Chantiers (`keep_closed=False`)
    garde son ancien comportement : masque `argent_recupere`, `annule`, `litige`."""
    scope = perm_scope(user, perm_resource, "view")
    q = cq(user)
    # iter38/87: soft-delete flag `cancelled=True`. Par défaut masqué. `?include_deleted=only` → uniquement supprimés. `=1` → mix.
    if include_deleted == "only":
        q["cancelled"] = True
    elif include_deleted != "1":
        q["cancelled"] = {"$ne": True}
    # iter46/215 : masque les chantiers dont la vente est fermée.
    #   Kanban Chantiers : masque argent_recupere / annule / litige (comportement historique)
    #   Planning        : masque UNIQUEMENT annule (à la demande de l'utilisateur — un chantier
    #                     reste visible sur le calendrier peu importe son statut sauf s'il est annulé)
    closed_sale_statuses = ["annule"] if keep_closed else ["argent_recupere", "annule", "litige"]
    closed_sales = await db.sales.find(
        {**cq(user), "status": {"$in": closed_sale_statuses}},
        {"_id": 0, "id": 1},
    ).to_list(10000)
    closed_ids = [s["id"] for s in closed_sales]
    if closed_ids:
        existing_ne = q.get("sale_id")
        if isinstance(existing_ne, dict) and "$in" in existing_ne:
            # commercial scope: intersect
            q["sale_id"] = {"$in": [s for s in existing_ne["$in"] if s not in closed_ids]}
        elif "sale_id" not in q:
            q["sale_id"] = {"$nin": closed_ids}
    # iter44: un commercial ne voit que les chantiers issus de ses ventes (commercial ou commercial_2).
    if (user or {}).get("role") == "commercial":
        own_sale_filter = _own_sales_filter(user)
        # Récupérer les sale_id des ventes qui appartiennent au commercial
        own_sales = await db.sales.find(
            {**cq(user), **own_sale_filter},
            {"_id": 0, "id": 1},
        ).to_list(5000)
        own_sale_ids = [s["id"] for s in own_sales if s["id"] not in closed_ids]
        q["sale_id"] = {"$in": own_sale_ids} if own_sale_ids else {"$in": ["__none__"]}
    if _is_prospect_role(user):
        p_sale_ids = [i for i in (await _prospect_ids(user))[0] if i not in closed_ids]
        q["sale_id"] = {"$in": p_sale_ids or ["__none__"]}

    if user.get("role") in ("technicien", "sous_traitant"):
        # Robust matching: gather every candidate name for THIS technician,
        # then filter projects whose `assigned_to` (string or array) contains
        # any of them, case- and accent-insensitive.
        import unicodedata
        def _norm(s: str) -> str:
            s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
            return " ".join(s.lower().split())

        candidates = set()
        uname = (user.get("name") or "").strip()
        if uname:
            candidates.add(uname)
        email = (user.get("email") or "").strip()
        if email:
            local = email.split("@")[0]
            if local:
                candidates.add(local)
            # team_members linked by email
            tms_by_email = await db.team_members.find(
                cq(user, {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}),
                {"_id": 0, "name": 1},
            ).to_list(50)
            for t in tms_by_email:
                if t.get("name"): candidates.add(t["name"])
        # team_members linked by name (fuzzy: same normalised name) — techniciens ET sous-traitants
        if uname:
            tms_by_name = await db.team_members.find(
                cq(user, {"type": {"$in": ["technicien", "sous_traitant"]}}),
                {"_id": 0, "name": 1},
            ).to_list(500)
            uname_norm = _norm(uname)
            for t in tms_by_name:
                tn = t.get("name") or ""
                if _norm(tn) == uname_norm or uname_norm in _norm(tn) or _norm(tn) in uname_norm:
                    if tn: candidates.add(tn)

        norm_cands = {_norm(c) for c in candidates if c}
        if not norm_cands:
            return []

        # Load projects for this company (no assigned_to prefilter — do it in Python)
        all_projs = await db.projects.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
        projects = []
        for p in all_projs:
            at = p.get("assigned_to")
            names = at if isinstance(at, list) else ([at] if at else [])
            names_norm = {_norm(n) for n in names if n}
            if names_norm & norm_cands:
                projects.append(p)
    else:
        if scope == "own" and not _is_prospect_role(user):
            # Commercial-scope: projects tied to their own clients OR own sales
            client_ids = await _commercial_client_ids(user)
            sale_ids = await _own_sale_ids(user)
            q["$or"] = [
                {"client_id": {"$in": client_ids}},
                {"sale_id": {"$in": sale_ids}},
            ]
        projects = await db.projects.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)

    ids = list({p["client_id"] for p in projects})
    clients = await db.clients.find(cq(user, {"id": {"$in": ids}}), {"_id": 0}).to_list(5000)
    cmap = {c["id"]: c for c in clients}
    # Enrich with commercial(s) + prestations from the source sale (DE-aware)
    sale_ids = list({p.get("sale_id") for p in projects if p.get("sale_id")})
    sales_map = {}
    if sale_ids:
        srows = await db.sales.find(cq(user, {"id": {"$in": sale_ids}}), {"_id": 0, "id": 1, "commercial": 1, "commercial_2": 1, "is_de": 1, "prestations": 1, "status": 1, "desired_intervention_date": 1}).to_list(len(sale_ids))
        sales_map = {s["id"]: s for s in srows}
    # iter106 : n'affiche PAS les chantiers orphelins (sale_id pointant vers une vente supprimée
    # ou vers un client absent). Un chantier sans vente ni client visible = résidu → masqué.
    projects = [p for p in projects if (p.get("sale_id") in sales_map) and (p.get("client_id") in cmap)]
    for p in projects:
        c = cmap.get(p["client_id"], {})
        p["client_name"] = c.get("name", "")
        p["client_phone"] = c.get("phone", "")
        p["client_address"] = c.get("address", "")
        p["client_postal_code"] = c.get("postal_code", "")
        p["client_city"] = c.get("city", "")
        s = sales_map.get(p.get("sale_id")) or {}
        p["commercial"] = s.get("commercial", "")
        p["commercial_2"] = s.get("commercial_2", "") if s.get("is_de") else ""
        p["is_de"] = bool(s.get("is_de")) and bool((s.get("commercial_2") or "").strip())
        # iter197 — Expose le statut de la vente pour que le Kanban puisse afficher
        # « En attente acceptation financement » quand la vente est en `attente_fi`,
        # même si une date programmée réelle a été renseignée entre-temps.
        p["sale_status"] = s.get("status") or ""
        # Always prefer the sale's current prestations (single source of truth) so techs see live qty
        if not p.get("prestations") and s.get("prestations"):
            p["prestations"] = s.get("prestations") or []
    # iter220 — Performance : les listes Chantiers / Planning n'ont PAS besoin du
    # contenu binaire des photos (base64 data-URI). On remplace la liste des photos
    # par le nombre + les métadonnées légères (taken_at, gps, by_completion). Résultat :
    # le payload passe de plusieurs Mo à ~quelques Ko, l'app ne saute plus en page de
    # login lors du chargement du Planning. Les photos complètes sont récupérées à la
    # demande via `GET /api/projects/{pid}` (ouverture de la fiche chantier).
    for p in projects:
        raw_photos = p.get("photos") or []
        slim = []
        for ph in raw_photos:
            if isinstance(ph, dict):
                slim.append({k: v for k, v in ph.items() if k != "src"})
            else:
                slim.append({})  # strip raw string
        p["photo_count"] = len(raw_photos)
        p["photos"] = slim
    return projects


@api_router.get("/projects")
async def list_projects(
    user: dict = Depends(get_current_user),
    include_deleted: str = Query(default="", pattern=r"^(only|1)?$"),
):
    check_perm(user, "projects", "view", "own")
    return await _fetch_projects_list(user, include_deleted, perm_resource="projects")


@api_router.get("/planning/projects")
async def list_planning_projects(
    user: dict = Depends(get_current_user),
    include_deleted: str = Query(default="", pattern=r"^(only|1)?$"),
):
    """iter209 — même charge que `/projects` mais gated par `planning.view`.
    Permet à un technicien à qui l'admin a retiré `projects.view` de conserver
    son Planning intact (les deux permissions sont indépendantes).
    iter215 — `keep_closed=True` : un chantier reste visible sur le calendrier peu
    importe son statut ou celui de la vente, sauf annulation (`sale.status='annule'`)."""
    if _is_prospect_role(user):
        rows = await _fetch_projects_list(user, "", perm_resource="planning", keep_closed=True)
        keep = ("id", "client_id", "client_name", "client_address", "client_postal_code", "client_city", "status", "sale_status",
                "scheduled_date", "scheduled_dates", "extra_dates", "duration_days", "end_date", "days_done", "day_exclusions", "cancelled")
        return [{k: p.get(k) for k in keep if k in p} | {"service": ""} for p in rows]
    check_perm(user, "planning", "view", "own")
    return await _fetch_projects_list(user, include_deleted, perm_resource="planning", keep_closed=True)


@api_router.get("/projects/{pid}")
async def get_project_full(pid: str, user: dict = Depends(get_current_user)):
    """iter220 — fiche chantier complète (avec photos pleines) utilisée par
    `ProjectDialog` à l'ouverture. Séparé de la liste pour alléger le payload des
    pages Chantiers / Planning."""
    # Autorisation : projects.view OU planning.view (les 2 pages ouvrent la même fiche)
    try:
        check_perm(user, "projects", "view", "own")
        scope_resource = "projects"
    except HTTPException:
        check_perm(user, "planning", "view", "own")
        scope_resource = "planning"
    p = await db.projects.find_one(cq(user, {"id": pid}), {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    await _ensure_project_scope(user, p, scope_resource)
    # Enrichit client/sale metadata (comme _fetch_projects_list) sans slim des photos
    c = await db.clients.find_one(cq(user, {"id": p.get("client_id")}), {"_id": 0}) or {}
    s = await db.sales.find_one(cq(user, {"id": p.get("sale_id")}), {"_id": 0}) or {}
    p["client_name"] = c.get("name", "")
    p["client_phone"] = c.get("phone", "")
    p["client_address"] = c.get("address", "")
    p["client_postal_code"] = c.get("postal_code", "")
    p["client_city"] = c.get("city", "")
    p["commercial"] = s.get("commercial", "")
    p["commercial_2"] = s.get("commercial_2", "") if s.get("is_de") else ""
    p["is_de"] = bool(s.get("is_de")) and bool((s.get("commercial_2") or "").strip())
    p["sale_status"] = s.get("status") or ""
    if not p.get("prestations") and s.get("prestations"):
        p["prestations"] = s.get("prestations") or []
    return p


async def _ensure_project_scope(user: dict, project: dict, resource: str = "projects") -> None:
    """Apply row-level project visibility after the tenant-level lookup."""
    if user.get("role") in ("technicien", "sous_traitant"):
        if not await _resolve_matched_assigned_names(user, project):
            raise HTTPException(status_code=404, detail="Chantier introuvable")
        return
    if _is_prospect_role(user):
        sale_ids, _ = await _prospect_ids(user)
        if project.get("sale_id") not in sale_ids:
            raise HTTPException(status_code=404, detail="Chantier introuvable")
        return
    if perm_scope(user, resource, "view") == "own":
        client_ids = await _commercial_client_ids(user)
        sale_ids = await _own_sale_ids(user)
        if project.get("client_id") not in client_ids and project.get("sale_id") not in sale_ids:
            raise HTTPException(status_code=404, detail="Chantier introuvable")


@api_router.put("/projects/{pid}")
async def update_project(pid: str, data: ProjectUpdate, user: dict = Depends(get_current_user)):
    check_perm(user, "projects", "edit")
    # iter206 : charge d'abord par (company_id, id), puis vérifie le scope par
    # matching FUZZY (accent-insensible, tokens partagés) au lieu d'un regex strict.
    # Fixe le bug : « Sébastien » ne pouvait ni ajouter de photo ni valider un
    # chantier terminé quand son user.name divergeait légèrement de l'assigné
    # (accent manquant, nom complet vs prénom, casse…).
    exists = await db.projects.find_one(cq(user, {"id": pid}), {"_id": 0})
    if not exists:
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    await _ensure_project_scope(user, exists)
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    # iter154 : dès qu'une date de programmation est renseignée sur un chantier « À planifier »,
    # il passe automatiquement en « En cours ». L'admin peut toujours forcer un statut explicite
    # dans le même PUT (updates["status"] est prioritaire).
    if (
        "scheduled_date" in updates
        and updates.get("scheduled_date")
        and "status" not in updates
        and (exists.get("status") == "a_planifier")
    ):
        updates["status"] = "en_cours"
    _will_start = updates.get("status") == "en_cours" and exists.get("status") != "en_cours"
    # iter48: RBAC + traçabilité photos.
    # Si la clé "photos" est envoyée, on compare avec l'existant :
    #   - un ajout de photo nécessite has_perm(user, "photos", "add")
    #   - toute nouvelle photo est enrichie de {added_by, added_by_id, created_at} si absent
    #   - la view des photos suit has_perm(user, "photos", "view") (défaut True)
    if "photos" in updates:
        new_list = updates["photos"] or []
        old_list = exists.get("photos") or []
        if len(new_list) > MAX_PHOTOS_PER_ENTITY:
            raise HTTPException(status_code=413, detail=f"Trop de photos (max {MAX_PHOTOS_PER_ENTITY})")
        # Normalise l'ancien en dicts pour comparer facilement
        def _src(p):
            if isinstance(p, str): return p
            if isinstance(p, dict): return p.get("src") or p.get("url") or ""
            return ""
        old_srcs = {_src(p) for p in old_list if _src(p)}
        added = [p for p in new_list if _src(p) and _src(p) not in old_srcs]
        if added and not has_perm(user, "photos", "add"):
            raise HTTPException(status_code=403, detail="Vous n'avez pas la permission d'ajouter des photos à ce chantier.")
        validated_added = _validated_photo_entries(added, max_count=MAX_PHOTOS_PER_ENTITY)
        validated_by_src = {_src(p): p for p in validated_added}
        # Enrichit chaque nouvelle photo avec la traçabilité (sans écraser si déjà présent)
        now = now_iso()
        uname = user.get("name") or user.get("email") or "?"
        uid = user.get("id")
        enriched = []
        for p in new_list:
            src = _src(p)
            if not src:
                continue
            if src in old_srcs:
                # Photo existante : conserve son objet tel quel
                # (retrouve l'ancien pour préserver les métadonnées)
                match = next((o for o in old_list if _src(o) == src), p)
                enriched.append(match if isinstance(match, dict) else {"src": src})
            else:
                safe_photo = validated_by_src.get(src)
                base = dict(safe_photo) if isinstance(safe_photo, dict) else {"src": src}
                base.setdefault("src", src)
                base.setdefault("added_by", uname)
                base.setdefault("added_by_id", uid)
                base.setdefault("created_at", now)
                enriched.append(base)
        updates["photos"] = enriched
    # Techniciens cannot re-assign a chantier to someone else
    if user.get("role") in ("technicien", "sous_traitant"):
        updates.pop("assigned_to", None)
    if "assigned_to" in updates and isinstance(updates["assigned_to"], list):
        clean = []
        for n in updates["assigned_to"]:
            if isinstance(n, list):
                clean.extend([x for x in n if isinstance(x, str) and x.strip()])
            elif isinstance(n, str) and n.strip():
                clean.append(n)
        seen = set()
        updates["assigned_to"] = [x for x in clean if not (x in seen or seen.add(x))]
    await db.projects.update_one(cq(user, {"id": pid}), {"$set": updates})
    updated = await db.projects.find_one(cq(user, {"id": pid}), {"_id": 0})
    # iter176 : journalise les changements de statut chantier + réassignations pour
    # l'historique B2B (jamais éditable côté user, gate admin sur GET /api/audit).
    _before_status = (updates or {}).get("status")
    if _before_status is not None or "assigned_to" in (updates or {}) or "scheduled_date" in (updates or {}):
        await log_audit(
            user, "update", "project", pid,
            after={k: updates.get(k) for k in ("status", "assigned_to", "scheduled_date") if k in updates},
        )
    # iter159 : email au(x) technicien(s)/sous-traitant(s) quand le chantier passe en "En cours"
    if _will_start and updated:
        await _notify_project(user, updated, "started")
    return updated

@api_router.delete("/projects/{pid}")
async def delete_project(pid: str, user: dict = Depends(get_current_user)):
    check_perm(user, "projects", "delete")
    before = await db.projects.find_one(cq(user, {"id": pid}), {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    await _ensure_project_scope(user, before)
    # iter87 : soft-delete → conserve les données pour restauration ultérieure.
    await db.projects.update_one(
        cq(user, {"id": pid}),
        {"$set": {"cancelled": True, "deleted_at": now_iso(), "deleted_by": user["id"]}},
    )
    await log_audit(user, "delete", "project", pid, before=before)
    return {"ok": True}


@api_router.post("/projects/{pid}/restore")
async def restore_project(pid: str, user: dict = Depends(get_current_user)):
    check_perm(user, "projects", "edit")
    before = await db.projects.find_one(cq(user, {"id": pid, "cancelled": True}), {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Chantier supprimé introuvable")
    await _ensure_project_scope(user, before)
    r = await db.projects.update_one(
        cq(user, {"id": pid, "cancelled": True}),
        {"$set": {"cancelled": False}, "$unset": {"deleted_at": "", "deleted_by": ""}},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Chantier supprimé introuvable")
    await log_audit(user, "restore", "project", pid)
    return {"ok": True}


# iter159 : Confirmation d'un chantier (bouton "Confirmer" dans la fiche).
# Bascule project.confirmed = true/false et envoie un email aux assignés si activation.
@api_router.post("/projects/{pid}/confirm")
async def confirm_project(pid: str, user: dict = Depends(get_current_user)):
    check_perm(user, "projects", "edit")
    proj = await db.projects.find_one(cq(user, {"id": pid}), {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    await _ensure_project_scope(user, proj)
    is_confirmed = bool(proj.get("confirmed"))
    new_val = not is_confirmed
    now = now_iso()
    upd = {"confirmed": new_val, "confirmed_at": now if new_val else None, "confirmed_by": (user.get("name") or user.get("email") or "?") if new_val else None}
    await db.projects.update_one(cq(user, {"id": pid}), {"$set": upd})
    updated = await db.projects.find_one(cq(user, {"id": pid}), {"_id": 0})
    if new_val and updated:
        await _notify_project(user, updated, "confirmed")
    return updated


# ---------------- Per-technician chantier notes (iter23) ----------------

class ProjectNoteIn(BaseModel):
    note: str = Field(default="", max_length=4000)

def _can_read_all_notes(user: dict) -> bool:
    role = user.get("role")
    return role in ("admin", "responsable", "super_admin")

def _fuzzy_name_match(user_name: str, candidate: str) -> bool:
    """Legacy names only authorize when the complete normalized names match."""
    a, b = _norm_name(user_name), _norm_name(candidate)
    return bool(a and b and a == b)

async def _resolve_matched_assigned_names(user: dict, proj: dict) -> set:
    """Retourne l'ensemble (lc) des noms d'assignés au chantier qui correspondent
    à l'utilisateur courant (par name fuzzy OU par email → team_members)."""
    my_name = user.get("name") or ""
    my_email = (user.get("email") or "").strip().lower()
    assigned = proj.get("assigned_to") or []
    if isinstance(assigned, str): assigned = [assigned]
    matched_lc = set()
    for a in assigned:
        if isinstance(a, str) and _fuzzy_name_match(my_name, a):
            matched_lc.add(_norm_name(a))
    # Fallback via team_members email → name
    if my_email:
        tms = await db.team_members.find(cq(user, {"email": my_email}), {"_id": 0, "name": 1}).to_list(50)
        for tm in tms:
            nm = tm.get("name") or ""
            if not nm: continue
            for a in assigned:
                if isinstance(a, str) and _fuzzy_name_match(nm, a):
                    matched_lc.add(_norm_name(a))
    return matched_lc

@api_router.get("/projects/{pid}/notes")
async def list_project_notes(pid: str, user: dict = Depends(get_current_user)):
    """Return per-technician notes. Techniciens only see their own note.
    Admin / Responsable see every note tied to the chantier.

    iter155 : matching robuste (insensible aux accents/casse + partage de prénom)
    entre user.name et team_member.name pour éviter les notes invisibles quand
    les orthographes divergent légèrement (ex: "Thanh" vs "Thanh Nguyen")."""
    try:
        check_perm(user, "projects", "view", "own")
        scope_resource = "projects"
    except HTTPException:
        check_perm(user, "planning", "view", "own")
        scope_resource = "planning"
    proj = await db.projects.find_one(cq(user, {"id": pid}), {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    await _ensure_project_scope(user, proj, scope_resource)
    q = cq(user, {"project_id": pid})
    if not _can_read_all_notes(user):
        matched_lc = await _resolve_matched_assigned_names(user, proj)
        if not matched_lc:
            return []
        q["technician_name_lc"] = {"$in": list(matched_lc)}
    docs = await db.project_notes.find(q, {"_id": 0}).sort("technician_name_lc", 1).to_list(200)
    return docs

@api_router.put("/projects/{pid}/notes/{technician_name}")
async def upsert_project_note(pid: str, technician_name: str, data: ProjectNoteIn, user: dict = Depends(get_current_user)):
    """Create or update a note for one technician of the chantier.
    - Admin/Responsable: can write for any assigned technician.
    - Technicien: can only write their own note.
    """
    tname = (technician_name or "").strip()
    if not tname:
        raise HTTPException(status_code=400, detail="Nom du technicien requis")
    proj = await db.projects.find_one(cq(user, {"id": pid}), {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    await _ensure_project_scope(user, proj)
    # Permission check
    role = user.get("role")
    if role not in ("admin", "responsable", "super_admin"):
        # technicien : only own note — matching robuste (accents/prénom/tokens/prefix)
        if not _fuzzy_name_match(user.get("name") or "", tname):
            raise HTTPException(status_code=403, detail="Accès refusé")
    # The technician must be assigned to the chantier
    assigned = proj.get("assigned_to") or []
    if isinstance(assigned, str):
        assigned = [assigned]
    assigned_lc = { _norm_name(x) for x in assigned if isinstance(x, str) }
    if _norm_name(tname) not in assigned_lc:
        raise HTTPException(status_code=400, detail="Ce technicien n'est pas assigné au chantier")
    now = now_iso()
    tname_lc = _norm_name(tname)
    existing = await db.project_notes.find_one(cq(user, {"project_id": pid, "technician_name_lc": tname_lc}), {"_id": 0})
    if existing:
        await db.project_notes.update_one(
            cq(user, {"project_id": pid, "technician_name_lc": tname_lc}),
            {"$set": {"note": data.note or "", "updated_at": now, "updated_by": user["id"]}},
        )
    else:
        doc = with_company({
            "id": str(uuid.uuid4()),
            "project_id": pid,
            "technician_name": tname,
            "technician_name_lc": tname_lc,
            "note": data.note or "",
            "created_by": user["id"],
            "created_at": now,
            "updated_at": now,
            "updated_by": user["id"],
        }, user)
        await db.project_notes.insert_one(doc)
    return await db.project_notes.find_one(cq(user, {"project_id": pid, "technician_name_lc": tname_lc}), {"_id": 0})

@api_router.delete("/projects/{pid}/notes/{technician_name}")
async def delete_project_note(pid: str, technician_name: str, user: dict = Depends(get_current_user)):
    role = user.get("role")
    if role not in ("admin", "responsable", "super_admin"):
        raise HTTPException(status_code=403, detail="Accès refusé")
    proj = await db.projects.find_one(cq(user, {"id": pid}), {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    await _ensure_project_scope(user, proj)
    tname_lc = _norm_name(technician_name)
    r = await db.project_notes.delete_one(cq(user, {"project_id": pid, "technician_name_lc": tname_lc}))
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Note introuvable")
    return {"ok": True}


# ---------------- AI corrections memory (iter25) ----------------
# Per-company memory of AI mistakes that got corrected by admin/responsable.
# Used as hints in the AI prompt to progressively improve field extraction.
# Isolation: strictly scoped by company_id. No cross-tenant reads.

class AICorrectionIn(BaseModel):
    field: str = Field(max_length=64)
    ai_value: Optional[str] = Field(default="", max_length=500)
    corrected_value: str = Field(max_length=500)
    context: Optional[dict] = None

def _is_manager(u: dict) -> bool:
    return u.get("role") in ("admin", "responsable", "super_admin")

@api_router.post("/ai/corrections")
async def log_ai_correction(data: AICorrectionIn, user: dict = Depends(get_current_user)):
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    doc = with_company({
        "id": str(uuid.uuid4()),
        "field": data.field,
        "ai_value": (data.ai_value or "").strip(),
        "corrected_value": (data.corrected_value or "").strip(),
        "context": data.context or {},
        "created_by": user["id"],
        "created_at": now_iso(),
    }, user)
    if doc["corrected_value"]:
        await db.ai_corrections.insert_one(doc)
    return {"ok": True}

@api_router.get("/ai/corrections")
async def list_ai_corrections(user: dict = Depends(get_current_user)):
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    rows = await db.ai_corrections.find(cq(user), {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows

@api_router.delete("/ai/corrections/{cid}")
async def delete_ai_correction(cid: str, user: dict = Depends(get_current_user)):
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    r = await db.ai_corrections.delete_one(cq(user, {"id": cid}))
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Correction introuvable")
    return {"ok": True}


async def _company_ai_learnings_hint(user: dict, limit: int = 30) -> str:
    """Build a small text block with recent corrections for THIS company only.
    Injected into the AI prompt as hints — never shared across tenants."""
    try:
        rows = await db.ai_corrections.find(cq(user), {"_id": 0, "field": 1, "ai_value": 1, "corrected_value": 1}).sort("created_at", -1).to_list(limit)
    except Exception:
        return ""
    if not rows:
        return ""
    by_field = {}
    for r in rows:
        f = r.get("field") or ""
        if not f: continue
        pair = (r.get("ai_value") or "").strip()[:80], (r.get("corrected_value") or "").strip()[:80]
        if pair[1]:
            by_field.setdefault(f, []).append(pair)
    if not by_field:
        return ""
    lines = ["Corrections apprises pour cette société (source de vérité prioritaire) :"]
    for f, pairs in list(by_field.items())[:8]:
        seen = set()
        uniq = []
        for a, c in pairs:
            k = (a.lower(), c.lower())
            if k in seen: continue
            seen.add(k); uniq.append((a, c))
            if len(uniq) >= 5: break
        pretty = ", ".join([f'"{a or "∅"}" → "{c}"' for a, c in uniq])
        lines.append(f"- Champ {f} : {pretty}")
    return "\n".join(lines)


# ---------------- IA — Mémoire persistante multi-tenant (iter56) ----------------
# Collection `ai_memories` : chaque doc {id, company_id, user_id, scope, content, tags, created_at, updated_at}
#   scope = "user"   → mémoire personnelle (visible uniquement pour user_id + company_id)
#   scope = "company"→ mémoire société (visible pour tous les utilisateurs de la company)
# ISOLATION STRICTE : toute lecture/écriture passe par cq(user) → filtre company_id, jamais accès inter-sociétés.
# Toute lecture user filtre en plus user_id == user["id"].

class AIMemoryIn(BaseModel):
    scope: Literal["user", "company"] = "user"
    content: str = Field(min_length=2, max_length=1000)
    tags: Optional[List[Annotated[str, Field(max_length=50)]]] = Field(default=None, max_length=8)

class AIMemoryPatch(BaseModel):
    content: Optional[str] = Field(default=None, max_length=1000)
    tags: Optional[List[Annotated[str, Field(max_length=50)]]] = Field(default=None, max_length=8)
    scope: Optional[Literal["user", "company"]] = None


def _mem_scope_filter(user: dict, scope: Optional[str] = None) -> dict:
    """Retourne le filtre qui garantit qu'un utilisateur ne peut lire que
    sa propre mémoire (scope=user + user_id==self) ou celle de sa société
    (scope=company). JAMAIS croiser company_id."""
    base = cq(user)
    if scope == "user":
        return {**base, "scope": "user", "user_id": user["id"]}
    if scope == "company":
        return {**base, "scope": "company"}
    # défaut : both — mais toujours strict user_id sur scope=user
    return {**base, "$or": [
        {"scope": "user", "user_id": user["id"]},
        {"scope": "company"},
    ]}


@api_router.get("/ai/memory")
async def list_ai_memory(scope: Optional[str] = Query(None, pattern="^(user|company)$"), user: dict = Depends(get_current_user)):
    q = _mem_scope_filter(user, scope)
    rows = await db.ai_memories.find(q, {"_id": 0}).sort("updated_at", -1).to_list(500)
    return rows


@api_router.post("/ai/memory")
async def create_ai_memory(data: AIMemoryIn, user: dict = Depends(get_current_user)):
    # RBAC : scope=company réservé à admin/responsable (règles société)
    if data.scope == "company" and not _is_manager(user):
        raise HTTPException(status_code=403, detail="Seul un admin/responsable peut créer une mémoire société")
    doc = with_company({
        "id": str(uuid.uuid4()),
        "user_id": user["id"] if data.scope == "user" else None,
        "created_by": user["id"],
        "created_by_name": user.get("name") or user.get("email") or "?",
        "scope": data.scope,
        "content": data.content.strip(),
        "tags": [(t or "").strip().lower() for t in (data.tags or []) if (t or "").strip()][:8],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }, user)
    await db.ai_memories.insert_one(doc.copy())
    await log_audit(user, "create", "ai_memory", doc["id"], after={"scope": data.scope, "content": data.content[:120]})
    return doc


@api_router.patch("/ai/memory/{mid}")
async def update_ai_memory(mid: str, data: AIMemoryPatch, user: dict = Depends(get_current_user)):
    existing = await db.ai_memories.find_one(cq(user, {"id": mid}), {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Mémoire introuvable")
    # Un user ne peut modifier une mémoire user que si c'est la sienne
    if existing.get("scope") == "user" and existing.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Cette mémoire ne vous appartient pas")
    if existing.get("scope") == "company" and not _is_manager(user):
        raise HTTPException(status_code=403, detail="Seul un admin/responsable peut modifier la mémoire société")
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    target_scope = updates.get("scope", existing.get("scope"))
    if target_scope == "company" and not _is_manager(user):
        raise HTTPException(status_code=403, detail="Seul un admin/responsable peut publier une mémoire société")
    if "scope" in updates:
        # Ownership follows the target scope; never keep a user owner on a
        # company-wide rule or create an ownerless personal memory.
        updates["user_id"] = None if target_scope == "company" else user["id"]
    if "tags" in updates:
        updates["tags"] = [(t or "").strip().lower() for t in updates["tags"] if (t or "").strip()][:8]
    updates["updated_at"] = now_iso()
    await db.ai_memories.update_one(cq(user, {"id": mid}), {"$set": updates})
    await log_audit(user, "update", "ai_memory", mid, after=updates)
    return await db.ai_memories.find_one(cq(user, {"id": mid}), {"_id": 0})


@api_router.delete("/ai/memory/{mid}")
async def delete_ai_memory(mid: str, user: dict = Depends(get_current_user)):
    existing = await db.ai_memories.find_one(cq(user, {"id": mid}), {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Mémoire introuvable")
    if existing.get("scope") == "user" and existing.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Cette mémoire ne vous appartient pas")
    if existing.get("scope") == "company" and not _is_manager(user):
        raise HTTPException(status_code=403, detail="Seul un admin/responsable peut supprimer la mémoire société")
    await db.ai_memories.delete_one(cq(user, {"id": mid}))
    await log_audit(user, "delete", "ai_memory", mid, before=existing)
    return {"ok": True}


async def _ai_memories_hint(user: dict, limit: int = 20) -> str:
    """iter56 : construit un extrait texte des mémoires (user + company) à injecter
    dans le system prompt de l'IA. STRICTEMENT scopé à user.company_id + user.id."""
    try:
        q = _mem_scope_filter(user)
        rows = await db.ai_memories.find(q, {"_id": 0, "scope": 1, "content": 1}).sort("updated_at", -1).to_list(limit)
    except Exception:
        return ""
    if not rows:
        return ""
    perso = [r["content"] for r in rows if r.get("scope") == "user"][:12]
    societe = [r["content"] for r in rows if r.get("scope") == "company"][:12]
    parts: list = []
    if societe:
        parts.append("Règles / mémoire de cette société (à respecter systématiquement) :")
        parts += [f"- {c}" for c in societe]
    if perso:
        parts.append("Préférences personnelles de cet utilisateur :")
        parts += [f"- {c}" for c in perso]
    return "\n".join(parts)


# Détecte les commandes utilisateur "Retiens ça / Souviens-toi / Oublie ça"
_MEM_SAVE_PATTERNS = [
    r"(?i)^\s*(?:retiens|souviens\s*-?\s*toi|note|memorise|mémorise)(?:\s*(?:que|ceci|ça|ca|cela))?\s*[:\-\s]+(.{4,600})$",
    r"(?i)^\s*(?:règle|regle|préférence|preference)\s*(?:société|societe)?\s*[:\-]\s*(.{4,600})$",
]
_MEM_FORGET_PATTERNS = [
    r"(?i)^\s*(?:oublie|efface|supprime)\s*(?:que|ça|ca|cela|cette\s+info(?:rmation)?)?\s*[:\-]?\s*(.{2,300})$",
]


async def _handle_memory_command(user: dict, message: str) -> Optional[str]:
    """Retourne une confirmation textuelle si la commande a été traitée, sinon None.
    Toutes les opérations sont scopées company_id + user_id."""
    m = (message or "").strip()
    if not m:
        return None
    for pat in _MEM_SAVE_PATTERNS:
        mo = re.match(pat, m)
        if mo:
            content = mo.group(1).strip().rstrip(".")
            if len(content) < 4:
                return None
            is_company = bool(re.search(r"(?i)^\s*(?:règle|regle|préférence|preference)\s*(?:société|societe)", m))
            scope = "company" if (is_company and _is_manager(user)) else "user"
            doc = with_company({
                "id": str(uuid.uuid4()),
                "user_id": user["id"] if scope == "user" else None,
                "created_by": user["id"],
                "created_by_name": user.get("name") or user.get("email") or "?",
                "scope": scope,
                "content": content,
                "tags": ["chat"],
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }, user)
            await db.ai_memories.insert_one(doc.copy())
            await log_audit(user, "auto_remember", "ai_memory", doc["id"], after={"scope": scope, "content": content[:120]})
            return f"🧠 Mémorisé ({'société' if scope == 'company' else 'perso'}) : « {content} »"
    for pat in _MEM_FORGET_PATTERNS:
        mo = re.match(pat, m)
        if mo:
            needle = mo.group(1).strip().rstrip(".")
            if len(needle) < 2:
                return None
            # Recherche fuzzy dans les mémoires de l'utilisateur uniquement (jamais society sauf manager)
            q = _mem_scope_filter(user)
            rows = await db.ai_memories.find(q, {"_id": 0, "id": 1, "content": 1, "scope": 1, "user_id": 1}).to_list(500)
            target = None
            n_norm = needle.lower()
            for r in rows:
                c = (r.get("content") or "").lower()
                if n_norm in c or c in n_norm:
                    if r.get("scope") == "company" and not _is_manager(user):
                        continue
                    if r.get("scope") == "user" and r.get("user_id") != user["id"]:
                        continue
                    target = r; break
            if target:
                await db.ai_memories.delete_one(cq(user, {"id": target["id"]}))
                await log_audit(user, "auto_forget", "ai_memory", target["id"], before=target)
                return f"🗑️ Oublié : « {target['content']} »"
            return f"Je n'ai rien trouvé de correspondant à « {needle} » dans ta mémoire."
    return None


# ---------------- Dashboard ----------------

# iter150 : helper robuste pour retrouver le team_member "commercial" correspondant à l'user.
# Match par name exact → email → normalisé (accent+case-insensible). Utilisé par les endpoints
# qui appliquent des flags par-commercial (see_company_*) pour éviter les fuites en cas de
# désynchronisation orthographique entre users.name et team_members.name.
async def _find_commercial_team_member(user: dict) -> Optional[dict]:
    if not user:
        return None
    my_name = (user.get("name") or "").strip()
    my_email = (user.get("email") or "").strip().lower()
    q_base = cq(user, {"type": "commercial"})
    if my_name:
        tm = await db.team_members.find_one({**q_base, "name": my_name}, {"_id": 0})
        if tm:
            return tm
    if my_email:
        tm = await db.team_members.find_one({**q_base, "email": my_email}, {"_id": 0})
        if tm:
            return tm
    if my_name:
        import unicodedata as _ud
        def _norm(s: str) -> str:
            return _ud.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()
        target = _norm(my_name)
        async for cand in db.team_members.find(q_base, {"_id": 0}):
            if _norm(cand.get("name") or "") == target:
                return cand
    return None


@api_router.get("/dashboard/company-comparison")
async def dashboard_company_comparison(
    period: str = Query("month", pattern="^(month|prev|next|year)$"),
    user: dict = Depends(get_current_user),
):
    """iter53 : renvoie les totaux SOCIÉTÉ (ignore le scope 'own') pour affichage secondaire
    à côté des chiffres personnels du commercial. Read-only et jamais nominatif."""
    check_perm(user, "sales", "view", "own")
    from calendar import monthrange
    tz = ZoneInfo("Europe/Paris")
    today = datetime.now(tz).date()
    y, m = today.year, today.month
    if period == "prev":
        first = date(y, m, 1) - timedelta(days=1)
        py, pm = first.year, first.month
        start = date(py, pm, 1); end = date(py, pm, monthrange(py, pm)[1])
    elif period == "next":
        last_day = date(y, m, monthrange(y, m)[1])
        first_next = last_day + timedelta(days=1)
        ny, nm = first_next.year, first_next.month
        start = date(ny, nm, 1); end = date(ny, nm, monthrange(ny, nm)[1])
    elif period == "year":
        start = date(y, 1, 1); end = date(y, 12, 31)
    else:
        start = date(y, m, 1); end = date(y, m, monthrange(y, m)[1])

    q = {"company_id": company_id_of(user), "sale_date": {"$gte": start.isoformat(), "$lte": end.isoformat()}}
    sales = await db.sales.find(q, {"_id": 0, "amount": 1, "status": 1}).to_list(20000)
    ca = 0.0; count = 0
    for s in sales:
        if s.get("status") in ("annule", "litige"):
            continue
        ca += float(s.get("amount") or 0); count += 1
    settings = await db.settings.find_one({"company_id": company_id_of(user), "kind": "global"}, {"_id": 0}) or {}
    obj = float(settings.get("objectif_ca") or 0)
    progress = round((ca / obj) * 100, 1) if obj > 0 else None

    # iter68/150 : appliquer les flags de visibilité société individuels si le viewer est un commercial
    # Défaut = True pour chaque flag (les 3 permissions sont ON par défaut).
    # iter150 : lookup robuste — match exact sur name, sinon normalisé (accent/case-insensible),
    # sinon fallback sur email. Fixe le bug où un nom légèrement différent (case, accents)
    # entre users.name et team_members.name renvoyait toujours "défaut True" (data leak).
    can_ca, can_obj, can_prog = True, True, True
    if (user or {}).get("role") == "commercial":
        tm = await _find_commercial_team_member(user)
        if tm:
            can_ca = bool(tm.get("see_company_ca", True))
            can_obj = bool(tm.get("see_company_objectif", True))
            can_prog = bool(tm.get("see_company_progress", True))
    return {
        "ca_total": round(ca, 2) if can_ca else None,
        "objectif": obj if can_obj else None,
        "progress": progress if can_prog else None,
        "count": count,
        "can_view_ca": can_ca,
        "can_view_objectif": can_obj,
        "can_view_progress": can_prog,
        "period": period,
    }


def _add_ranking_share(by_com, s, amt):
    # Vente DE : CA partagé 50/50 entre commercial et commercial_2
    n1 = (s.get("commercial") or "").strip()
    n2 = (s.get("commercial_2") or "").strip() if s.get("is_de") else ""
    parts = [(n1, 0.5), (n2, 0.5)] if (n2 and n2 != n1) else [(n1, 1.0)]
    for n, share in parts:
        if n:
            b_ = by_com.setdefault(n, {"commercial": n, "ca": 0.0, "count": 0})
            b_["ca"] += amt * share; b_["count"] += 1


@api_router.get("/dashboard/executive")
async def dashboard_executive(period: str = Query("month", pattern="^(month|prev|next|year)$"), user: dict = Depends(get_current_user)):
    check_perm(user, "sales", "view", "own")
    sales_scope = perm_scope(user, "sales", "view")
    projects_scope = perm_scope(user, "projects", "view")
    comm_scope = perm_scope(user, "commissions", "view")
    can_financial = has_perm(user, "financial", "view")
    from calendar import monthrange
    tz = ZoneInfo("Europe/Paris")
    today = datetime.now(tz).date()
    y, m = today.year, today.month
    if period == "prev":
        first = date(y, m, 1) - timedelta(days=1)
        py, pm = first.year, first.month
        start = date(py, pm, 1); end = date(py, pm, monthrange(py, pm)[1])
    elif period == "next":
        last_day = date(y, m, monthrange(y, m)[1])
        first_next = last_day + timedelta(days=1)
        ny, nm = first_next.year, first_next.month
        start = date(ny, nm, 1); end = date(ny, nm, monthrange(ny, nm)[1])
    elif period == "year":
        start = date(y, 1, 1); end = date(y, 12, 31)
    else:
        start = date(y, m, 1); end = date(y, m, monthrange(y, m)[1])
    prev_first = date(start.year, start.month, 1) - timedelta(days=1)
    prev_start = date(prev_first.year, prev_first.month, 1)
    prev_end = date(prev_first.year, prev_first.month, monthrange(prev_first.year, prev_first.month)[1])

    async def _agg(a, b):
        q = cq(user, {"sale_date": {"$gte": a.isoformat(), "$lte": b.isoformat()}})
        if sales_scope == "own":
            # iter60 : utilise le filtre canonique (commercial_user_id + fuzzy nom + slot 2)
            # au lieu du match strict qui manquait les ventes bind ou avec accent/casse différent
            q.update(_own_sales_filter(user))
        if _is_prospect_role(user):
            q.update(_prospect_sales_filter(user))
        sales = await db.sales.find(q, {"_id": 0}).to_list(20000)
        ca = 0.0; count = 0; comm = 0.0; by_com = {}
        for s in sales:
            if s.get("status") in ("annule", "litige"):
                continue
            amt = float(s.get("amount") or 0); rate = float(s.get("commission_rate") if s.get("commission_rate") is not None else 0)
            ca += amt; count += 1; comm += amt * rate
            _add_ranking_share(by_com, s, amt)
        return {"ca": ca, "count": count, "commission_total": comm, "by_com": by_com}

    cur = await _agg(start, end)
    prev = await _agg(prev_start, prev_end)

    # iter67 : pour un commercial (scope 'own'), on veut afficher tout le classement société
    # → on ré-agrège les ventes SANS filtre 'own' pour le classement uniquement.
    ranking_by_com = cur["by_com"]
    if sales_scope == "own":
        all_q = cq(user, {"sale_date": {"$gte": start.isoformat(), "$lte": end.isoformat()}})
        all_sales_period = await db.sales.find(all_q, {"_id": 0, "amount": 1, "commercial": 1, "commercial_2": 1, "is_de": 1, "status": 1}).to_list(20000)
        ranking_by_com = {}
        for s in all_sales_period:
            if s.get("status") in ("annule", "litige"):
                continue
            _add_ranking_share(ranking_by_com, s, float(s.get("amount") or 0))
    def _delta(cv, pv):
        if not pv or pv < 1000:
            return None
        return round(((cv - pv) / pv) * 100, 1)

    def _delta_count(cv, pv):
        if not pv or pv < 3:
            return None
        return round(((cv - pv) / pv) * 100, 1)

    team = await db.team_members.find(cq(user, {"type": "commercial"}), {"_id": 0}).to_list(500)
    tmap = {t["name"]: float(t.get("objectif") or 0) for t in team}
    # iter199 — Fallback prénom accent-insensible : Théo Dudal / Anaïs Tran (users
    # sans team_member.objectif direct mais présents dans un team_member "Théo" / "Anaïs").
    tmap_first = {}
    for t in team:
        first = _norm_name(t.get("name") or "").split(" ", 1)[0]
        if first and (t.get("objectif") or 0) > 0:
            tmap_first.setdefault(first, float(t["objectif"]))
    # iter61 : map name → hidden_from_ranking (visibilité publique)
    hidden_map = {t["name"]: bool(t.get("hidden_from_ranking")) for t in team}
    # iter73 : map name → team_member_id + can_view_others_ranking (pour admin inline toggle + enforcement)
    tm_id_map = {t["name"]: t.get("id") for t in team}
    can_others_map = {t["name"]: bool(t.get("can_view_others_ranking", True)) for t in team}
    ranking = sorted(ranking_by_com.values(), key=lambda r: r["ca"], reverse=True)
    for r in ranking:
        obj = tmap.get(r["commercial"], 0)
        if not obj:
            first = _norm_name(r["commercial"]).split(" ", 1)[0]
            obj = tmap_first.get(first, 0)
        r["objectif"] = obj
        r["progress"] = round((r["ca"] / obj) * 100, 1) if obj > 0 else 0
        r["hidden_from_ranking"] = hidden_map.get(r["commercial"], False)
        r["team_member_id"] = tm_id_map.get(r["commercial"])
        r["can_view_others_ranking"] = can_others_map.get(r["commercial"], True)
    # iter67 : un commercial voit désormais TOUT le classement société (comme les admins), pas uniquement sa propre ligne.
    # Confidentialité : on masque l'objectif/la progression des AUTRES commerciaux au viewer commercial (garde seulement les siens).
    # iter67 : un commercial voit désormais TOUT le classement société (comme les admins), pas uniquement sa propre ligne.
    # iter73 : sauf si son flag can_view_others_ranking est False → restreint alors à sa propre ligne.
    # iter151v3 : couplage — si le viewer commercial est lui-même retiré du classement
    #   (hidden_from_ranking=true), il ne doit PAS voir le CA des autres commerciaux.
    #   Il apparaît alors seul (première position toute seule). Symétrie parfaite avec la
    #   règle "on ne voit pas ceux qui sont cachés" côté sortie.
    if sales_scope == "own":
        my = (user.get("name") or "").lower()
        # Cherche le viewer commercial dans team_members (name insensible à la casse)
        viewer_can_view_others = True
        viewer_is_hidden = False
        for t in team:
            if (t.get("name") or "").lower() == my:
                viewer_can_view_others = bool(t.get("can_view_others_ranking", True))
                viewer_is_hidden = bool(t.get("hidden_from_ranking"))
                break
        if (not viewer_can_view_others) or viewer_is_hidden:
            ranking = [r for r in ranking if (r.get("commercial") or "").lower() == my]
        else:
            for r in ranking:
                if (r.get("commercial") or "").lower() != my:
                    r["objectif"] = 0
                    r["progress"] = None
    # iter61 : pour les non-admins (hors soi-même), masquer les commerciaux hidden_from_ranking
    if not _is_manager(user):
        my_name_lc = (user.get("name") or "").lower()
        ranking = [r for r in ranking if not r.get("hidden_from_ranking") or (r.get("commercial") or "").lower() == my_name_lc]

    settings = await db.settings.find_one({"company_id": company_id_of(user), "kind": "global"}, {"_id": 0}) or {}
    monthly_objectif = float(settings.get("objectif_ca") or 100000)
    # iter74/78 : source unique = team_members.objectif défini par l'admin.
    # Match robuste en 3 étapes pour éviter les "Non défini" quand user.name ≠ team_member.name :
    #   1) match exact normalisé (accents/casse) — cas "Thomas" == "Thomas"
    #   2) match par premier token (prénom) — cas "Kilian Blanc" (user) ↔ "Kilian" (team_member)
    #   3) match par email exact si présent des 2 côtés
    if sales_scope == "own":
        my_key = _norm_name(user.get("name") or "")
        my_first = my_key.split(" ", 1)[0] if my_key else ""
        my_email = (user.get("email") or "").lower()
        personal_obj = 0.0
        # Passe 1 : exact
        for t in team:
            if _norm_name(t.get("name") or "") == my_key and my_key:
                personal_obj = float(t.get("objectif") or 0)
                break
        # Passe 2 : premier token
        if personal_obj == 0.0 and my_first:
            for t in team:
                tkey = _norm_name(t.get("name") or "")
                if tkey and (tkey == my_first or tkey.split(" ", 1)[0] == my_first):
                    personal_obj = float(t.get("objectif") or 0)
                    break
        # Passe 3 : email
        if personal_obj == 0.0 and my_email:
            for t in team:
                if (t.get("email") or "").lower() == my_email:
                    personal_obj = float(t.get("objectif") or 0)
                    break
        monthly_objectif = personal_obj  # 0 → "Non défini" côté frontend

    # Projects counts respect the projects scope
    proj_q = cq(user)
    if projects_scope == "own":
        client_ids = await _commercial_client_ids(user)
        sale_ids = await _own_sale_ids(user)
        proj_q["$or"] = [
            {"client_id": {"$in": client_ids}},
            {"sale_id": {"$in": sale_ids}},
        ]
    # iter173 : exclure les chantiers annulés (cancelled=True) des KPI, cohérence
    # avec la vue Kanban qui filtre déjà `cancelled: {$ne: True}`.
    _proj_active = {**proj_q, "cancelled": {"$ne": True}}
    to_schedule = await db.projects.count_documents({**_proj_active, "status": "a_planifier"})
    in_progress = await db.projects.count_documents({**_proj_active, "status": "en_cours"})
    completed = await db.projects.count_documents({**_proj_active, "status": "termine"})

    # --- Activité chantiers : aujourd'hui + semaine en cours (lundi -> dimanche) ---
    # Filter: projects with a real scheduled_date (YYYY-MM-DD), status != termine, and whose
    # source sale is not annule/litige. HT counted once per project (even if multiple techs).
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)             # Sunday
    act_q = {**proj_q, "status": {"$ne": "termine"},
             "scheduled_date": {"$regex": r"^\d{4}-\d{2}-\d{2}$"}}
    act_projects = await db.projects.find(act_q, {"_id": 0, "id": 1, "sale_id": 1, "scheduled_date": 1, "duration_days": 1}).to_list(5000)
    sale_ids_act = list({p.get("sale_id") for p in act_projects if p.get("sale_id")})
    sale_amounts: dict = {}
    if sale_ids_act:
        srows = await db.sales.find(
            cq(user, {"id": {"$in": sale_ids_act}}),
            {"_id": 0, "id": 1, "amount": 1, "status": 1},
        ).to_list(len(sale_ids_act))
        for s in srows:
            if s.get("status") not in ("annule", "litige"):
                sale_amounts[s["id"]] = float(s.get("amount") or 0)

    HOURS_PER_DAY = 8
    today_count = 0; today_hours = 0.0; today_ca = 0.0
    week_count = 0;  week_hours = 0.0;  week_ca = 0.0
    for p in act_projects:
        try:
            ps = datetime.fromisoformat(p["scheduled_date"]).date()
        except Exception:
            logger.debug("Date de chantier historique invalide ignorée dans les statistiques")
            continue
        dur = max(1, int(p.get("duration_days") or 1))
        pe = ps + timedelta(days=dur - 1)
        amt = sale_amounts.get(p.get("sale_id"), 0.0)
        if amt == 0.0 and p.get("sale_id"):
            # Sale annulée/litige → exclure ce chantier
            continue
        # Today overlap: 1 day if today ∈ [ps, pe] else 0
        if ps <= today <= pe:
            today_count += 1
            today_hours += HOURS_PER_DAY
            today_ca += amt
        # Week overlap: number of days in the intersection with [week_start, week_end]
        ov_start = max(ps, week_start); ov_end = min(pe, week_end)
        if ov_start <= ov_end:
            week_count += 1
            week_hours += (ov_end - ov_start).days * HOURS_PER_DAY + HOURS_PER_DAY
            week_ca += amt

    activity = {
        "today": {"count": today_count, "hours": round(today_hours, 1), "ca": round(today_ca, 2)},
        "week": {
            "count": week_count, "hours": round(week_hours, 1), "ca": round(week_ca, 2),
            "start": week_start.isoformat(), "end": week_end.isoformat(),
        },
    }

    # Commissions to validate — scoped by commissions.view perm
    unpaid = []
    comm_val = 0.0
    if comm_scope != "none":
        # iter99 : source unique = sale_date (règle identique sur toutes les pages : Dashboard, Ventes, Commissions, Rapport)
        cq_ = cq(user, {"commission_paid": {"$ne": True}, "status": {"$nin": ["annule", "litige", "non_financable"]}})
        if comm_scope == "own":
            cq_.update(_own_sales_filter(user))
        if period != "year":
            cq_["sale_date"] = {"$gte": start.isoformat(), "$lte": end.isoformat()}
        else:
            cq_["sale_date"] = {"$regex": f"^{start.year}"}
        unpaid = await db.sales.find(cq_, {"_id": 0, "amount": 1, "commission_rate": 1, "commission_rate_2": 1, "is_de": 1, "commercial_2": 1, "commercial": 1, "commercial_user_id": 1, "commercial_2_user_id": 1}).to_list(5000)
        def _commission_for(s):
            amt = float(s.get("amount") or 0)
            r1 = float(s.get("commission_rate") if s.get("commission_rate") is not None else 0)
            is_de = bool(s.get("is_de")) and bool((s.get("commercial_2") or "").strip())
            if not is_de:
                return amt * r1
            r2 = float(s.get("commission_rate_2") if s.get("commission_rate_2") is not None else r1)
            # iter98 : pour un commercial en scope 'own', ne compter QUE la part qui lui revient
            if comm_scope == "own":
                uid = user.get("id")
                uname_norm = _norm_name(user.get("name") or "")
                mine_slot1 = (s.get("commercial_user_id") == uid) or (_norm_name(s.get("commercial") or "") == uname_norm)
                mine_slot2 = (s.get("commercial_2_user_id") == uid) or (_norm_name(s.get("commercial_2") or "") == uname_norm)
                total = 0.0
                if mine_slot1: total += amt * 0.5 * r1
                if mine_slot2: total += amt * 0.5 * r2
                return total
            return amt * 0.5 * r1 + amt * 0.5 * r2
        comm_val = sum(_commission_for(s) for s in unpaid)

    date_prefix = f"^{start.strftime('%Y-%m')}" if period != "year" else f"^{start.year}"
    ot_scope = perm_scope(user, "overtime", "view")
    pending_ot: List[dict] = []
    if ot_scope != "none":
        ot_q = cq(user, {"status": {"$ne": "approved"}, "date": {"$regex": date_prefix}})
        if ot_scope == "own":
            ot_q["technician_name"] = user.get("name") or "__none__"
        pending_ot = await db.overtime.find(ot_q, {"_id": 0, "hours": 1}).to_list(5000)
    ot_h = round(sum(float(e.get("hours") or 0) for e in pending_ot), 2)

    alerts = []
    if to_schedule > 0 and has_perm(user, "projects", "view", "own"):
        alerts.append({"key": "to_schedule", "label": f"{to_schedule} chantier{'s' if to_schedule > 1 else ''} à planifier", "count": to_schedule, "href": "/chantiers"})
    if len(pending_ot) > 0 and has_perm(user, "overtime", "validate"):
        alerts.append({"key": "overtime", "label": f"{ot_h}h sup à valider ({len(pending_ot)} saisie{'s' if len(pending_ot) > 1 else ''})", "count": len(pending_ot), "href": "/heures-sup"})
    if len(unpaid) > 0 and has_perm(user, "commissions", "edit"):
        alerts.append({"key": "commissions", "label": f"{len(unpaid)} commission{'s' if len(unpaid) > 1 else ''} à valider", "count": len(unpaid), "href": "/commissions"})

    recent_q = cq(user)
    if sales_scope == "own":
        # iter60 : même logique que _agg — cohérence CA / recent_sales garantie
        recent_q.update(_own_sales_filter(user))
    # iter122 : les ventes annulées / en litige ne figurent PAS dans "Ventes récentes"
    # (widget destiné aux ventes actives récentes ; les annulées restent visibles dans
    # la page Ventes filtrée). Cohérent avec le CA affiché "hors annulé & litige".
    recent_q["status"] = {"$nin": ["annule", "litige"]}
    recent = await db.sales.find(recent_q, {"_id": 0}).sort("created_at", -1).to_list(6)
    # Enrich with client_name
    if recent:
        client_ids = list({s.get("client_id") for s in recent if s.get("client_id")})
        clients_map = {c["id"]: c for c in await db.clients.find(cq(user, {"id": {"$in": client_ids}}), {"_id": 0}).to_list(200)}
        for s in recent:
            s["client_name"] = (clients_map.get(s.get("client_id")) or {}).get("name", "")

    # Clients count: respect clients scope
    clients_scope = perm_scope(user, "clients", "view")
    if clients_scope == "all":
        clients_count = await db.clients.count_documents(cq(user))
    elif clients_scope == "own":
        # iter98 : compter uniquement les clients qui existent réellement (exclut les orphelins
        # dont la vente référence un client_id supprimé) — cohérence avec la page /clients.
        ids = await _commercial_client_ids(user)
        if ids:
            clients_count = await db.clients.count_documents(cq(user, {"id": {"$in": ids}}))
        else:
            clients_count = 0
    else:
        clients_count = 0

    payload = {
        "period": period,
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "ca": {"total": cur["ca"], "objectif": monthly_objectif, "progress": round((cur["ca"] / monthly_objectif) * 100, 1) if monthly_objectif > 0 else 0, "delta_pct": _delta(cur["ca"], prev["ca"])},
        "sales": {"count": cur["count"], "delta_pct": _delta_count(cur["count"], prev["count"])},
        "clients_count": clients_count,
        "projects": {"to_schedule": to_schedule, "in_progress": in_progress, "completed": completed},
        "activity": activity,
        "ranking": ranking[:10],
        "commissions": {"total": round(cur["commission_total"], 2) if can_financial or comm_scope != "none" else 0, "to_validate_count": len(unpaid), "to_validate_amount": round(comm_val, 2)},
        "overtime": {"pending_hours": ot_h, "pending_count": len(pending_ot)},
        "alerts": alerts,
        "recent_sales": recent,
    }
    return payload



@api_router.get("/dashboard/activity")
async def dashboard_activity(
    day: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    week: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user: dict = Depends(get_current_user),
):
    """Activité chantiers pour un jour + une semaine spécifiques (navigation libre).

    Utilise scheduled_date (string YYYY-MM-DD) — aucune conversion UTC.
    Exclut les ventes annulée/litige/argent_recupere et les chantiers terminés/cancelled.
    """
    check_perm(user, "sales", "view", "own")
    projects_scope = perm_scope(user, "projects", "view")
    tz = ZoneInfo("Europe/Paris")
    today = datetime.now(tz).date()
    HOURS_PER_DAY = 8

    try:
        d = date.fromisoformat(day) if day else today
    except Exception:
        d = today
    try:
        w_ref = date.fromisoformat(week) if week else today
    except Exception:
        w_ref = today
    w_start = w_ref - timedelta(days=w_ref.weekday())
    w_end = w_start + timedelta(days=6)

    proj_q = cq(user)
    if projects_scope == "own":
        client_ids = await _commercial_client_ids(user)
        sale_ids = await _own_sale_ids(user)
        proj_q["$or"] = [
            {"client_id": {"$in": client_ids}},
            {"sale_id": {"$in": sale_ids}},
        ]
    # iter107 : on ne filtre plus par status ≠ termine ici — on veut aussi les chantiers finis
    # pour les compter séparément dans done_count/done_ca à côté des chantiers prévus.
    proj_q["scheduled_date"] = {"$regex": r"^\d{4}-\d{2}-\d{2}$"}
    proj_q["cancelled"] = {"$ne": True}

    # Ventes fermées / annulées / litige → chantiers exclus
    closed_statuses = ["argent_recupere", "annule", "litige"]
    closed_rows = await db.sales.find(
        {**cq(user), "status": {"$in": closed_statuses}},
        {"_id": 0, "id": 1},
    ).to_list(20000)
    closed_ids = {s["id"] for s in closed_rows}

    projects = await db.projects.find(proj_q, {"_id": 0}).to_list(5000)
    projects = [p for p in projects if not p.get("sale_id") or p.get("sale_id") not in closed_ids]

    s_ids = list({p.get("sale_id") for p in projects if p.get("sale_id")})
    sales_map: dict = {}
    if s_ids:
        rows = await db.sales.find(cq(user, {"id": {"$in": s_ids}}), {"_id": 0}).to_list(len(s_ids))
        sales_map = {r["id"]: r for r in rows}
    c_ids = list({p.get("client_id") for p in projects if p.get("client_id")})
    clients_map: dict = {}
    if c_ids:
        rows = await db.clients.find(cq(user, {"id": {"$in": c_ids}}), {"_id": 0}).to_list(len(c_ids))
        clients_map = {r["id"]: r for r in rows}

    def build_entry(p):
        s = sales_map.get(p.get("sale_id")) or {}
        c = clients_map.get(p.get("client_id")) or {}
        amt = float(s.get("amount") or 0)
        techs = p.get("assigned_to") or []
        if isinstance(techs, str):
            techs = [techs] if techs else []
        return {
            "id": p["id"],
            "sale_id": p.get("sale_id"),
            "client_name": p.get("client_name") or c.get("name") or "—",
            "client_phone": c.get("phone") or p.get("client_phone") or "",
            "service": p.get("service") or s.get("service") or "",
            "commercial": s.get("commercial") or p.get("commercial") or "",
            "commercial_2": (s.get("commercial_2") if s.get("is_de") else None),
            "techniciens": techs,
            "amount": amt,
            "scheduled_date": p.get("scheduled_date"),
            "duration_days": max(1, int(p.get("duration_days") or 1)),
            "priority": p.get("priority"),
            "status": p.get("status"),
        }

    def overlaps(p, start_d, end_d):
        try:
            ps = date.fromisoformat(p["scheduled_date"])
        except Exception:
            return False
        dur = max(1, int(p.get("duration_days") or 1))
        pe = ps + timedelta(days=dur - 1)
        return not (pe < start_d or ps > end_d)

    day_entries = [build_entry(p) for p in projects if overlaps(p, d, d)]
    week_entries = [build_entry(p) for p in projects if overlaps(p, w_start, w_end)]

    def summarize(entries, start_d, end_d):
        # iter111 : le physique du chantier est fait dès `termine` (= À encaisser).
        #   - "fini" (vert)  = status in {termine, encaisse}
        #   - "prévu" (noir) = tout le reste (a_planifier, en_cours, …)
        # Hours uniquement sur les prévus (les finis n'occupent plus de créneau à venir).
        upcoming = [e for e in entries if e.get("status") not in ("termine", "encaisse")]
        done = [e for e in entries if e.get("status") in ("termine", "encaisse")]
        ca = sum(e["amount"] for e in upcoming)
        done_ca = sum(e["amount"] for e in done)
        hours = 0
        for e in upcoming:
            try:
                ps = date.fromisoformat(e["scheduled_date"])
            except Exception:
                logger.debug("Date de chantier invalide ignorée dans le calcul de charge")
                continue
            pe = ps + timedelta(days=max(1, e["duration_days"]) - 1)
            ov_s = max(ps, start_d); ov_e = min(pe, end_d)
            if ov_s <= ov_e:
                hours += ((ov_e - ov_s).days + 1) * HOURS_PER_DAY
        return {"count": len(upcoming), "ca": round(ca, 2), "hours": hours,
                "done_count": len(done), "done_ca": round(done_ca, 2)}

    return {
        "today": today.isoformat(),
        "day": {
            "date": d.isoformat(),
            **summarize(day_entries, d, d),
            "projects": sorted(day_entries, key=lambda x: (x["scheduled_date"], x["client_name"])),
        },
        "week": {
            "start": w_start.isoformat(),
            "end": w_end.isoformat(),
            **summarize(week_entries, w_start, w_end),
            "projects": sorted(week_entries, key=lambda x: (x["scheduled_date"], x["client_name"])),
        },
    }


@api_router.get("/dashboard/stats")
async def dashboard_stats(user: dict = Depends(get_current_user)):
    check_perm(user, "sales", "view", "own")
    q = cq(user)
    if perm_scope(user, "sales", "view") == "own":
        # iter98 : filtre canonique (commercial_user_id + fallback nom) au lieu du match strict
        q.update(_own_sales_filter(user))
    if _is_prospect_role(user):
        q.update(_prospect_sales_filter(user))
    sales = await db.sales.find(q, {"_id": 0}).to_list(10000)
    # Projects scope
    proj_q = cq(user)
    if _is_prospect_role(user):
        proj_q["sale_id"] = {"$in": (await _prospect_ids(user))[0]}
    if perm_scope(user, "projects", "view") == "own":
        client_ids = await _commercial_client_ids(user)
        sale_ids = await _own_sale_ids(user)
        proj_q["$or"] = [
            {"client_id": {"$in": client_ids}},
            {"sale_id": {"$in": sale_ids}},
        ]
    projects = await db.projects.find(proj_q, {"_id": 0}).to_list(10000)
    # Clients count scope
    cscope = perm_scope(user, "clients", "view")
    if cscope == "all":
        clients_count = await db.clients.count_documents(cq(user))
    elif cscope == "own":
        # iter98 : ne compter que les clients existants (exclut les orphelins) — cohérence avec /clients
        ids = await _commercial_client_ids(user)
        if ids:
            clients_count = await db.clients.count_documents(cq(user, {"id": {"$in": ids}}))
        else:
            clients_count = 0
    else:
        clients_count = 0
    if _is_prospect_role(user):
        clients_count = len((await _prospect_ids(user))[1])
    active_sales = [s for s in sales if s.get("status") not in ("annule", "litige")]
    total_ca = sum(float(s.get("amount", 0)) for s in active_sales)
    return {
        "sales_count": len(sales),
        "signed_count": len(active_sales),
        "ca_total": total_ca,
        "clients_count": clients_count,
        "to_schedule": len([p for p in projects if p.get("status") == "a_planifier" and not p.get("cancelled")]),
        "in_progress": len([p for p in projects if p.get("status") == "en_cours" and not p.get("cancelled")]),
        "completed": len([p for p in projects if p.get("status") == "termine" and not p.get("cancelled")]),
    }


# ---------------- Commissions ----------------

async def require_commission_access(user: dict = Depends(get_current_user)) -> dict:
    require_role(user, "admin", "comptable")
    return user


# ---------------- AI Assistant ----------------

AI_RATE_LIMIT_PER_MINUTE = int(os.environ.get("AI_RATE_LIMIT_PER_MINUTE", "20"))
AI_DAILY_REQUEST_QUOTA = int(os.environ.get("AI_DAILY_REQUEST_QUOTA", "200"))


async def _enforce_ai_rate_limit(user: dict, cost_units: int = 1):
    """Distributed per-user rate limit and daily quota, shared by all workers."""
    now = datetime.now(timezone.utc)
    company = company_id_of(user)
    user_id = user.get("id") or "unknown"
    windows = (
        (f"minute:{company}:{user_id}:{now.strftime('%Y%m%d%H%M')}", AI_RATE_LIMIT_PER_MINUTE,
         now.replace(second=0, microsecond=0) + timedelta(minutes=2)),
        (f"day:{company}:{user_id}:{now.strftime('%Y%m%d')}", AI_DAILY_REQUEST_QUOTA,
         now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=2)),
    )
    for key, quota, expires_at in windows:
        rec = await db.ai_rate_limits.find_one_and_update(
            {"_id": key},
            {
                "$inc": {"count": max(1, int(cost_units))},
                "$setOnInsert": {"company_id": company, "user_id": user_id, "created_at": now},
                "$set": {"expires_at": expires_at},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if int((rec or {}).get("count") or 0) > quota:
            raise HTTPException(status_code=429, detail="Quota IA atteint. Réessayez plus tard.")

class AIChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=16_000)

_APP_CONTEXT = """Tu es l'assistant intelligent de KEYLOT, une application française de gestion pour la vente à domicile et la planification de chantiers.

RÈGLE ABSOLUE DE CONFIDENTIALITÉ (iter64) :
- Si l'utilisateur qui te parle a le rôle "commercial", tu ne dois JAMAIS révéler les taux de commission disponibles dans la société, les taux appliqués aux autres commerciaux, ni les paliers/règles internes de calcul. Tu peux uniquement parler du taux appliqué à ses propres ventes.
- Si un commercial demande "quels sont les autres taux ?" ou "combien touche tel autre commercial ?", réponds poliment que ces informations sont confidentielles et réservées à l'administrateur.
- Pour un admin/responsable, aucune restriction de ce type.
""" + """

Modules principaux:
- Ventes : créer/modifier des ventes (Date, BDC, client, produits, montant HT, règlement Chèque/Virement/CB/Financement/Acompte, commission 10/13/20/25/30%, commercial, source R1/Assist/CQ/CA, statut En cours/Commercial a le chèque/Chèque récupéré/Chantier fini/Litige/Annulé).
- Chantiers : Kanban 3 colonnes (À planifier / En cours / Terminé), drag & drop, photos, assignation à un technicien.
- Planning : calendrier mensuel des chantiers, clic pour éditer.
- Commissions : par mois avec onglets (ce mois, mois prochain, +N mois), bouton "Payé", filtre par commercial.
- Clients : répertoire, clic pour voir l'historique des ventes.
- Utilisateurs & Équipe : admin ajoute des commerciaux (avec objectif €) et techniciens.
- Paramètres (admin) : logo, nom société, couleurs, police, objectif global.

Rôles : admin (tout), commercial (ventes/clients/chantiers/planning), technicien (ses chantiers uniquement), comptable (commissions uniquement).

Réponds toujours en français, sois concis (max 4-6 phrases), pratique, avec des étapes numérotées quand pertinent."""

async def _save_recent_ai_context(user: dict, text: str, meta: dict = None):
    """iter128 : trace un extrait de la Q/R ou de l'analyse de document dans un cache
    per-user (company_id conservé pour audit). Sert de mémoire courte inter-messages."""
    if not text:
        return
    try:
        doc = {
            "user_id": user.get("id"),
            "company_id": company_id_of(user),
            "ts": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=30),
            "text": text[:5000],
            "meta": meta or {},
        }
        await db.ai_recent_context.insert_one(doc)
        # Cap à 10 entrées les plus récentes par user
        scope = {"user_id": user.get("id"), "company_id": company_id_of(user)}
        keep = await db.ai_recent_context.find(scope).sort("ts", -1).to_list(50)
        stale = keep[10:]
        if stale:
            await db.ai_recent_context.delete_many({**scope, "_id": {"$in": [d["_id"] for d in stale]}})
    except Exception:
        logger.warning("Impossible d'enregistrer le contexte IA récent", exc_info=True)


async def _load_recent_ai_context(user: dict, max_items: int = 5, max_age_min: int = 30) -> str:
    """iter128 : renvoie un préambule système avec les dernières analyses/Q&R du user."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_min)
        docs = await db.ai_recent_context.find(
            {"user_id": user.get("id"), "company_id": company_id_of(user), "ts": {"$gte": cutoff}},
        ).sort("ts", -1).to_list(max_items)
    except Exception:
        return ""
    if not docs:
        return ""
    lines = ["\n\n### CONTEXTE RÉCENT DE LA CONVERSATION (documents analysés + Q&R des 30 dernières minutes)"]
    for i, d in enumerate(reversed(docs), 1):
        lines.append(f"\n--- Entrée {i} ---\n{d.get('text', '')}")
    lines.append("\n\nQuand l'utilisateur fait référence à « les devis / documents / photos que je viens d'envoyer », utilise ces entrées comme source. Ne redemande pas d'envoyer les fichiers s'ils sont déjà dans le contexte ci-dessus. Calcule / réponds directement.")
    return "\n".join(lines)


class KiksActIn(BaseModel):
    message: str = Field(min_length=1, max_length=16_000)
    page: Optional[str] = Field(default=None, max_length=120)
    page_entity_id: Optional[str] = Field(default=None, max_length=128)


@api_router.post("/kiks/act")
async def kiks_act(data: KiksActIn, user: dict = Depends(get_current_user)):
    """iter171 — KIK'S opérationnel : parse une demande en langage naturel via LLM,
    exécute immédiatement les actions read-only (search_client, list_projects_by_status,
    list_reinterventions_date, search_sale) avec cq(user)+perm_scope, et retourne un
    résumé + pending_id pour les actions write (create_client) qui nécessitent une
    confirmation via `POST /api/kiks/confirm/{pending_id}`.
    Toute exécution passe par les mêmes règles de sécurité que les endpoints dédiés."""
    _require_external_ai_enabled()
    await _enforce_ai_rate_limit(user)
    msg = (data.message or "").strip()
    if len(msg) < 3:
        return {"kind": "answer", "text": "Que puis-je faire pour vous ?"}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception:
        return {"kind": "answer", "text": "Assistant temporairement indisponible."}
    sys = (
        "Tu es l'assistant opérationnel de QYLOT. À partir de la demande de l'utilisateur, "
        "renvoie UNIQUEMENT un JSON strict au format :\n"
        "{\"action\": <str>, \"params\": {...}}\n"
        "Actions disponibles :\n"
        "- search_client (params: query)\n"
        "- list_projects_by_status (params: status ∈ [a_planifier, en_cours, termine])\n"
        "- list_reinterventions_date (params: date ISO YYYY-MM-DD | 'today' | 'tomorrow')\n"
        "- search_sale (params: query)\n"
        "- create_client (params: name, city?, phone?, email?)\n"
        "- unknown (params: {})\n"
        "Réponds uniquement en JSON, jamais de texte hors JSON."
    )
    try:
        chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=f"kiks-{user['id']}", system_message=sys).with_model("openai", "gpt-4o-mini")
        raw = await chat.send_message(UserMessage(text=msg))
    except Exception as e:
        logger.warning(f"kiks_act LLM error: {e}")
        return {"kind": "answer", "text": "Je n'ai pas compris. Reformulez ?"}
    import re as _re, json as _json
    m = _re.search(r"\{[\s\S]*\}", raw or "")
    if not m:
        return {"kind": "answer", "text": raw or "Aucune action détectée."}
    try:
        plan = _json.loads(m.group(0))
    except Exception:
        return {"kind": "answer", "text": raw}
    act = (plan.get("action") or "unknown").lower()
    p = plan.get("params") or {}
    from datetime import date as _date, timedelta as _td

    if act == "search_client":
        qtxt = (p.get("query") or "").strip()
        if not qtxt: return {"kind": "answer", "text": "Quel client cherchez-vous ?"}
        rx = {"$regex": _re.escape(qtxt), "$options": "i"}
        q = cq(user, {"$or": [{"name": rx}, {"phone": rx}, {"email": rx}, {"city": rx}]})
        if perm_scope(user, "clients", "view") == "own":
            ids = await _commercial_client_ids(user)
            q["id"] = {"$in": ids}
        docs = await db.clients.find(q, {"_id": 0, "id": 1, "name": 1, "city": 1, "phone": 1}).limit(8).to_list(8)
        return {"kind": "result", "text": f"{len(docs)} client(s) trouvé(s).", "results": {"clients": docs}}

    if act == "list_projects_by_status":
        status = (p.get("status") or "a_planifier").lower()
        if status not in ("a_planifier", "en_cours", "termine"):
            status = "a_planifier"
        q = cq(user, {"status": status, "cancelled": {"$ne": True}})
        if user.get("role") in ("technicien", "sous_traitant"):
            q["assigned_to"] = {"$regex": _re.escape(user.get("name") or ""), "$options": "i"}
        docs = await db.projects.find(q, {"_id": 0, "id": 1, "client_name": 1, "scheduled_date": 1, "assigned_to": 1, "city": 1}).sort("scheduled_date", 1).limit(20).to_list(20)
        label = {"a_planifier": "À planifier", "en_cours": "PROG", "termine": "À encaisser"}[status]
        return {"kind": "result", "text": f"{len(docs)} chantier(s) « {label} »", "results": {"projects": docs}}

    if act == "list_reinterventions_date":
        d = (p.get("date") or "today").lower()
        if d == "today": d_iso = _date.today().isoformat()
        elif d == "tomorrow": d_iso = (_date.today() + _td(days=1)).isoformat()
        else:
            try: d_iso = _date.fromisoformat(d[:10]).isoformat()
            except Exception: d_iso = _date.today().isoformat()
        q = cq(user, {"scheduled_date": d_iso})
        if user.get("role") in ("technicien", "sous_traitant"):
            q["assigned_to"] = {"$regex": _re.escape(user.get("name") or ""), "$options": "i"}
        docs = await db.reinterventions.find(q, {"_id": 0, "id": 1, "client_name": 1, "reason": 1, "assigned_to": 1}).limit(20).to_list(20)
        return {"kind": "result", "text": f"{len(docs)} intervention(s) le {d_iso}", "results": {"reinterventions": docs}}

    if act == "search_sale":
        qtxt = (p.get("query") or "").strip()
        rx = {"$regex": _re.escape(qtxt), "$options": "i"}
        q = cq(user, {"$or": [{"client_name": rx}, {"service": rx}, {"bdc": rx}, {"commercial": rx}]})
        if perm_scope(user, "sales", "view") == "own":
            q.update(_own_sales_filter(user))
        docs = await db.sales.find(q, {"_id": 0, "id": 1, "client_name": 1, "service": 1, "amount": 1, "status": 1, "sale_date": 1, "commercial": 1}).sort("sale_date", -1).limit(10).to_list(10)
        return {"kind": "result", "text": f"{len(docs)} vente(s) trouvée(s).", "results": {"sales": docs}}

    if act == "create_client":
        if not has_perm(user, "clients", "create"):
            return {"kind": "answer", "text": "Vous n'avez pas la permission de créer un client."}
        name = (p.get("name") or "").strip()
        if not name:
            return {"kind": "answer", "text": "Quel est le nom du client à créer ?"}
        payload = {"name": name, "city": p.get("city") or "", "phone": p.get("phone") or "", "email": p.get("email") or ""}
        pending_id = str(uuid.uuid4())
        await db.kiks_pending.insert_one({
            "id": pending_id, "user_id": user["id"], "company_id": company_id_of(user),
            "action": "create_client", "params": payload, "created_at": now_iso(),
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
        })
        summary = f"Créer le client « {name} »" + (f" à {payload['city']}" if payload["city"] else "") + (f" (tél {payload['phone']})" if payload["phone"] else "")
        return {"kind": "confirm", "pending_id": pending_id, "summary": summary + ". Confirmer ?", "action": "create_client"}

    return {"kind": "answer", "text": "Je n'ai pas encore appris cette action. Reformulez ou faites-le manuellement."}


@api_router.post("/kiks/confirm/{pending_id}")
async def kiks_confirm(pending_id: str, user: dict = Depends(get_current_user)):
    """iter171 — Exécute une action en attente créée par /api/kiks/act. Vérifie
    l'ownership (user_id + company_id) et les permissions du role au moment de
    l'exécution (fail-closed)."""
    pend = await db.kiks_pending.find_one_and_delete({
        "id": pending_id,
        "user_id": user["id"],
        "company_id": company_id_of(user),
        "expires_at": {"$gt": datetime.now(timezone.utc)},
    }, {"_id": 0})
    if not pend:
        raise HTTPException(status_code=404, detail="Action introuvable ou déjà exécutée")
    act = pend.get("action")
    p = pend.get("params") or {}
    if act == "create_client":
        check_perm(user, "clients", "create")
        cli = ClientIn(**p)
        doc = with_company(cli.model_dump(), user)
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = now_iso()
        await db.clients.insert_one(doc)
        return {"kind": "done", "text": f"Client « {p.get('name')} » créé ✅", "result": {"id": doc["id"]}}
    raise HTTPException(status_code=400, detail="Action non supportée")


@api_router.post("/ai/chat")
async def ai_chat(data: AIChatIn, user: dict = Depends(get_current_user)):
    _require_external_ai_enabled()
    await _enforce_ai_rate_limit(user)
    # iter56 : détecte "Retiens ça / Oublie ça" avant même d'appeler le LLM
    mem_reply = await _handle_memory_command(user, data.message)
    if mem_reply:
        return {"reply": mem_reply, "memory_action": True}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        # iter56 : injection des mémoires user + company (isolation stricte company_id)
        mem_hint = await _ai_memories_hint(user)
        # iter128 : injection du contexte récent (docs/devis analysés < 30 min) — permet
        # à KIK'S de répondre aux follow-up "les devis que je t'ai envoyés" sans re-upload.
        recent_ctx = await _load_recent_ai_context(user)
        sys_msg = _APP_CONTEXT + ("\n\n" + mem_hint if mem_hint else "") + recent_ctx
        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"user-{user['id']}",
            system_message=sys_msg,
        ).with_model("openai", "gpt-4o-mini")
        reply = await chat.send_message(UserMessage(text=data.message))
        # iter128 : trace la Q/R dans le cache pour continuer la conversation ensuite
        await _save_recent_ai_context(user, f"[Chat]\nQ: {data.message[:500]}\nR: {(reply or '')[:1500]}", {"kind": "chat"})
        return {"reply": reply}
    except Exception:
        logger.exception("AI chat error")
        raise HTTPException(status_code=502, detail="Service IA temporairement indisponible")


@api_router.post("/ai/chat-multipart")
async def ai_chat_multipart(
    message: str = "",
    files: List[UploadFile] = File(default=[]),
    user: dict = Depends(get_current_user),
):
    """Multimodal chat: text + optional images/PDFs. If files are attached AND the
    message asks to fill a sale/devis, we ALSO return a structured devis extraction
    (`devis` field) so the frontend can prefill the NewSaleSheet."""
    _require_external_ai_enabled()
    if not message and not files:
        raise HTTPException(status_code=400, detail="Message ou fichier requis")
    if len(files or []) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=413, detail=f"Trop de fichiers (max {MAX_UPLOAD_FILES})")
    if len(message or "") > 16_000:
        raise HTTPException(status_code=413, detail="Message trop long")
    await _enforce_ai_rate_limit(user, cost_units=max(1, 1 + len(files or [])))

    # iter56 : commande mémoire prioritaire (uniquement si pas de fichier)
    if not files and message:
        mem_reply = await _handle_memory_command(user, message)
        if mem_reply:
            return {"reply": mem_reply, "attached": 0, "memory_action": True}

    images_b64: List[str] = []
    for f in files or []:
        raw = await _read_upload_limited(f)
        mime = (f.content_type or "").lower()
        name = (f.filename or "").lower()
        if mime == "application/pdf" or name.endswith(".pdf"):
            try:
                import fitz
                doc = fitz.open(stream=raw, filetype="pdf")
                if doc.page_count > MAX_PDF_PAGES:
                    doc.close()
                    raise HTTPException(status_code=413, detail=f"PDF trop long (max {MAX_PDF_PAGES} pages)")
                for page in doc:
                    pix = page.get_pixmap(dpi=180)
                    images_b64.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))
                doc.close()
            except HTTPException:
                raise
            except Exception:
                logger.exception("Unreadable AI chat PDF")
                raise HTTPException(status_code=400, detail="PDF illisible")
        elif mime.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".webp", ".heic")):
            images_b64.append(base64.b64encode(raw).decode("utf-8"))

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        # iter56 : mémoires user+company injectées en plus du contexte app (strict company_id)
        mem_hint = await _ai_memories_hint(user)
        # iter128 : contexte récent (docs analysés < 30 min) — mémoire courte inter-messages
        recent_ctx = await _load_recent_ai_context(user)
        sys_msg = _APP_CONTEXT + ("\n\n" + mem_hint if mem_hint else "") + recent_ctx
        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"user-{user['id']}",
            system_message=sys_msg,
        ).with_model("openai", "gpt-4o-mini")
        user_msg = UserMessage(
            text=message or "Décris ce document.",
            file_contents=[ImageContent(b) for b in images_b64] if images_b64 else None,
        )
        reply = await chat.send_message(user_msg)
        # iter128 : trace l'analyse du/des document(s) pour que les follow-up puissent y référer
        if images_b64:
            try:
                await _save_recent_ai_context(
                    user,
                    f"[Analyse {len(images_b64)} document(s)]\nQuestion : {message or 'Décrire'}\nAnalyse : {(reply or '')[:2500]}",
                    {"kind": "multipart", "attached": len(images_b64)},
                )
            except Exception:
                logger.warning("Impossible d'enregistrer le contexte IA multimodal", exc_info=True)
    except Exception:
        logger.exception("AI multimodal error")
        raise HTTPException(status_code=502, detail="Service IA temporairement indisponible")

    out = {"reply": reply, "attached": len(images_b64)}

    # If we have files AND the user's intent looks like a devis/sale creation → run the strict extractor too
    if images_b64:
        m = (message or "").lower().strip()
        action_kw = ["cr\u00e9e", "cree", "cr\u00e9er", "creer", "ajoute", "ajouter",
                      "enregistre", "enregistrer", "pr\u00e9pare", "prepare", "pr\u00e9parer",
                      "remplis", "remplir", "fais-moi", "fais moi", "fiche de vente", "cr\u00e9e la vente",
                      "cree la vente", "ajoute cette vente", "enregistre ce devis", "fiche"]
        question_kw = ["quel", "quelle", "combien", "qui ", "quand", "r\u00e9sume", "resume", "?"]
        is_action = any(k in m for k in action_kw)
        is_question = any(k in m for k in question_kw)
        wants_sale = (is_action and not is_question) or (not message and images_b64)
        if wants_sale:
            try:
                # Inject per-company learnings as prompt hint (iter25) — isolated by company_id
                hint = await _company_ai_learnings_hint(user)
                sys_msg = _DEVIS_SYSTEM + ("\n\n" + hint if hint else "")
                # iter203 : GPT-4o (pas -mini) pour l'extraction de vente depuis photo/devis.
                extractor = LlmChat(
                    api_key=os.environ["EMERGENT_LLM_KEY"],
                    session_id=f"devis-multi-{user['id']}-{uuid.uuid4().hex[:6]}",
                    system_message=sys_msg,
                ).with_model("openai", "gpt-4o")
                raw = await extractor.send_message(UserMessage(
                    text=f"Analyse ce devis ({len(images_b64)} page(s)) et renvoie le JSON strict. RECOPIE MOT POUR MOT : nom, prénom, adresse, code postal, ville, numéro de devis, date.",
                    file_contents=[ImageContent(b) for b in images_b64],
                ))
                import json as _json
                txt = (raw or "").strip()
                if txt.startswith("```"):
                    txt = txt.strip("`")
                    if txt.lower().startswith("json"): txt = txt[4:]
                    txt = txt.strip()
                i, j = txt.find("{"), txt.rfind("}")
                extracted = None
                if i >= 0 and j > i:
                    try:
                        extracted = _json.loads(txt[i:j+1])
                    except Exception:
                        extracted = None
                if isinstance(extracted, dict):
                    warns = list(extracted.get("warnings") or [])
                    warns.extend(_consistency_checks(extracted))
                    commercials = await _list_commercials_names(user)
                    matched = _fuzzy_match_commercial(extracted.get("commercial") or "", commercials)
                    cmatch = await _find_matching_client(user, extracted)
                    out["devis"] = {
                        "data": extracted,
                        "commercial_matched": matched,
                        "client_match": cmatch,
                        "warnings": warns,
                        "pages": len(images_b64),
                    }
                    # Build an executable preview for create_sale
                    prenom = (extracted.get("client_prenom") or "").strip()
                    nom = (extracted.get("client_nom") or "").strip()
                    client_full = (f"{prenom} {nom}".strip()) if prenom else nom
                    amount = _parse_num(extracted.get("total_ht")) or 0
                    prestations = extracted.get("prestations") or []
                    service_lines = []
                    for p in prestations:
                        d_ = (p.get("designation") or "").strip()
                        if not d_:
                            continue
                        # iter26: only the product NAME goes into `service`. The amount is
                        # kept separately in `total_ht` / `amount` — never appended here.
                        service_lines.append(f"• {d_}")
                    service_text = "\n".join(service_lines)
                    sale_data = {
                        "client_name": (cmatch or {}).get("name") or client_full or None,
                        "client_id": (cmatch or {}).get("id"),
                        "commercial": matched,
                        "amount": amount,
                        "service": service_text,
                        "bdc": extracted.get("numero_devis"),
                        "sale_date": extracted.get("date_vente"),
                        # Spread client fields flat so /ai/action/execute picks them up when creating a new client
                        "client_phone": extracted.get("client_telephone") if not cmatch else None,
                        "client_address": extracted.get("client_adresse") if not cmatch else None,
                        "client_postal_code": extracted.get("client_code_postal") if not cmatch else None,
                        "client_city": extracted.get("client_ville") if not cmatch else None,
                        "prestations_count": len([p for p in prestations if p.get("designation")]),
                        "total_ht": _parse_num(extracted.get("total_ht")),
                    }
                    # Commercial n'est PAS bloquant — utilisateur peut créer la vente sans, à compléter plus tard.
                    missing = [k for k in ("client_name", "amount") if not sale_data.get(k)]
                    if not sale_data.get("commercial"):
                        missing.append("commercial")  # signalé mais non bloquant côté UI
                    summary_bits = []
                    if sale_data["prestations_count"]:
                        summary_bits.append(f"{sale_data['prestations_count']} prestation{'s' if sale_data['prestations_count'] > 1 else ''}")
                    if amount:
                        summary_bits.append(f"{amount:.0f} € HT")
                    preview = {
                        "intent": "create_sale",
                        "data": sale_data,
                        "missing": missing,
                        "summary": " · ".join(summary_bits) if summary_bits else "Devis analysé",
                        "confidence": "high" if not missing else "medium",
                        "warnings": warns,
                    }
                    out["preview"] = preview
                    # Short assistant reply, replacing the long verbose one
                    out["reply"] = f"Vente préparée ✅ — {preview['summary']}"
            except Exception:
                logger.exception("Devis auto-extract during chat failed (non-fatal)")

    return out


# ---------------- AI Actions (create sale / client from natural language) ----------------

class AIActionIn(BaseModel):
    message: str = Field(min_length=1, max_length=16_000)

class AIActionExecuteIn(BaseModel):
    intent: Literal["create_sale", "create_client", "update_sale_status"]
    data: dict = Field(max_length=50)


async def _list_commercials_names(user: dict) -> List[str]:
    docs = await db.team_members.find(cq(user, {"type": "commercial"}), {"_id": 0, "name": 1}).to_list(500)
    return [d["name"] for d in docs]


def _match_commercial(name: str, options: List[str]) -> Optional[str]:
    if not name:
        return None
    needle = name.strip().lower()
    for n in options:
        if n.lower() == needle:
            return n
    for n in options:
        if needle in n.lower() or n.lower().startswith(needle):
            return n
    return None


_ACTION_SYSTEM = """Tu es l'assistant KEYLOT en MODE ACTION. L'utilisateur veut créer ou mettre à jour rapidement des données via une phrase en français.

Analyse sa demande et renvoie UNIQUEMENT un JSON strict (sans commentaire, sans texte autour).

Intents supportés:
- "create_sale" : créer une vente. Champs data possibles:
   client_name (string, obligatoire), commercial (string, doit correspondre à un nom fourni), amount (number, en €),
   commission_rate (number entre 0 et 0.30 — accepte "0%", "10%", "13%", "15%", "20%", "25%", "30%"),
   source (string parmi ["R1","Assist","CQ","CA","TAP","Sous-traitance"]), payment_method (string parmi ["cheque","virement","cb","financement","acompte"]),
   payment_installments (number, défaut 1), service (string, description produit/prestation), notes (string).
- "create_client" : créer un client. Champs data possibles: name, phone, email, address, postal_code, city, notes.
- "update_sale_status" : changer le statut d'une vente existante. Champs data possibles:
   client_name (string) OU bdc (string), status (string parmi ["en_cours","commercial_cheque","argent_recupere","chantier_fini","litige","annule"]).
   Mapping FR→statut : "chantier fini/terminé"→"chantier_fini", "chèque récupéré/argent récupéré"→"argent_recupere",
   "commercial a le chèque"→"commercial_cheque", "en cours"→"en_cours", "litige/problème"→"litige", "annulé/annulée"→"annule".
- "unknown" : demande non actionnable ou trop ambigüe.

Consignes:
- Le champ commercial DOIT correspondre à un nom de la liste "COMMERCIAUX_DISPONIBLES" (renvoie le nom exact tel qu'écrit dans la liste, sensible aux accents). Si tu ne trouves pas, laisse "" et ajoute "commercial" dans "missing".
- commission_rate en décimal (ex: 20% → 0.20, 0% → 0).
- Si un champ obligatoire manque (client_name pour vente, name pour client, status pour update), mets-le dans "missing".
- Renvoie confidence "high" | "medium" | "low".

Format de sortie EXACT (JSON pur):
{"intent": "...", "confidence": "...", "data": {...}, "missing": [...], "summary": "phrase courte en français décrivant l'action"}
"""


async def _resolve_sale_for_status(data: dict, user: dict) -> Optional[dict]:
    """Try bdc exact -> bdc-as-client-name -> client_name regex. Fills data['client_name'] with the canonical value when found."""
    sale = None
    bdc = (data.get("bdc") or "").strip()
    name = (data.get("client_name") or "").strip()
    if bdc:
        sale = await db.sales.find_one(cq(user, {"bdc": bdc}), {"_id": 0})
    if not sale and bdc:
        client = await db.clients.find_one(cq(user, {"name": {"$regex": f"^{re.escape(bdc)}", "$options": "i"}}), {"_id": 0})
        if client:
            sale = await db.sales.find_one(cq(user, {"client_id": client["id"]}), {"_id": 0}, sort=[("created_at", -1)])
            if sale:
                data["client_name"] = client.get("name") or bdc
    if not sale and name:
        client = await db.clients.find_one(cq(user, {"name": {"$regex": f"^{re.escape(name)}", "$options": "i"}}), {"_id": 0})
        if client:
            sale = await db.sales.find_one(cq(user, {"client_id": client["id"]}), {"_id": 0}, sort=[("created_at", -1)])
            if sale:
                data["client_name"] = client.get("name") or name
    return sale



@api_router.post("/ai/action")
async def ai_action(payload: AIActionIn, user: dict = Depends(require_sales_access)):
    """Parse a natural-language message into a structured action preview (no execution)."""
    _require_external_ai_enabled()
    await _enforce_ai_rate_limit(user)
    import json as _json
    commercials = await _list_commercials_names(user)
    system = _ACTION_SYSTEM + "\n\nCOMMERCIAUX_DISPONIBLES = " + _json.dumps(commercials, ensure_ascii=False)
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"action-{user['id']}-{uuid.uuid4().hex[:8]}",
            system_message=system,
        ).with_model("openai", "gpt-4o-mini")
        raw = await chat.send_message(UserMessage(text=payload.message))
    except Exception:
        logger.exception("AI action LLM error")
        raise HTTPException(status_code=502, detail="Service IA temporairement indisponible")

    # Extract JSON from raw (LLM sometimes wraps in ```json)
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        parsed = _json.loads(text)
    except Exception:
        # last resort: try to slice { ... }
        s = text.find("{"); e = text.rfind("}")
        if s >= 0 and e > s:
            try:
                parsed = _json.loads(text[s:e+1])
            except Exception:
                raise HTTPException(status_code=422, detail="Réponse IA non JSON")
        else:
            raise HTTPException(status_code=422, detail="Réponse IA non JSON")

    intent = parsed.get("intent") or "unknown"
    data = parsed.get("data") or {}
    missing = parsed.get("missing") or []

    if intent == "create_sale":
        # Normalize commercial to an exact team name
        if data.get("commercial"):
            matched = _match_commercial(data["commercial"], commercials)
            if matched:
                data["commercial"] = matched
            else:
                data["commercial"] = ""
                if "commercial" not in missing:
                    missing.append("commercial")
        # Coerce numbers
        try:
            if data.get("amount") is not None:
                data["amount"] = float(data["amount"])
        except Exception:
            data["amount"] = 0
        if data.get("commission_rate") is None:
            data["commission_rate"] = 0.0
        # Defaults
        data.setdefault("source", "")
        data.setdefault("payment_method", "cheque")
        data.setdefault("payment_installments", 1)
        data.setdefault("service", "")
        data.setdefault("notes", "")
        # Only keep truly required fields in "missing"
        required = {"client_name"}
        missing = [m for m in missing if m in required or m == "commercial"]
        if not data.get("client_name") and "client_name" not in missing:
            missing.append("client_name")

    if intent == "create_client":
        required = {"name"}
        missing = [m for m in missing if m in required]
        if not data.get("name") and "name" not in missing:
            missing.append("name")

    if intent == "update_sale_status":
        valid_statuses = {"en_cours", "commercial_cheque", "argent_recupere", "chantier_fini", "litige", "annule"}
        st = (data.get("status") or "").strip()
        if st and st not in valid_statuses:
            data["status"] = ""
        sale = await _resolve_sale_for_status(data, user)
        if sale:
            data["resolved_sale_id"] = sale["id"]
            data["current_status"] = sale.get("status")
            data["resolved_amount"] = sale.get("amount")
        else:
            if "sale_not_found" not in missing:
                missing.append("sale_not_found")
        required = {"status"}
        missing = [m for m in missing if m in required or m == "sale_not_found"]
        if not data.get("status") and "status" not in missing:
            missing.append("status")

    return {
        "intent": intent,
        "confidence": parsed.get("confidence") or "low",
        "summary": parsed.get("summary") or "",
        "data": data,
        "missing": missing,
    }


@api_router.post("/ai/action/execute")
async def ai_action_execute(payload: AIActionExecuteIn, user: dict = Depends(require_sales_access)):
    """Execute a previously previewed AI action."""
    intent = payload.intent
    d = payload.data or {}

    # Enforce role-based restrictions on the AI's ability to CREATE / MODIFY sales.
    # A commercial user must not be able to bypass the UI by calling this endpoint.
    if intent == "create_sale":
        check_perm(user, "sales", "create")
    if intent == "update_sale_status":
        check_perm(user, "sales", "edit")
    if intent == "create_client":
        check_perm(user, "clients", "create")

    if intent == "create_client":
        name = (d.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Nom client requis")
        client_in = ClientIn(
            name=name,
            phone=d.get("phone") or "",
            email=d.get("email") or "",
            address=d.get("address") or "",
            postal_code=d.get("postal_code") or "",
            city=d.get("city") or "",
            notes=d.get("notes") or "",
        )
        return await create_client(client_in, user)  # type: ignore

    if intent == "create_sale":
        client_name = (d.get("client_name") or "").strip()
        if not client_name:
            raise HTTPException(status_code=400, detail="Nom client requis")
        # Find or create the client by name
        existing = await db.clients.find_one(cq(user, {"name": client_name}), {"_id": 0})
        if existing:
            client_id = existing["id"]
            client_obj = None
        else:
            client_id = None
            client_obj = ClientIn(
                name=client_name,
                phone=d.get("client_phone") or "",
                email=d.get("client_email") or "",
                address=d.get("client_address") or "",
                postal_code=d.get("client_postal_code") or "",
                city=d.get("client_city") or "",
                notes="",
            )
        sale_date = d.get("sale_date") or datetime.now(timezone.utc).date().isoformat()
        from pydantic import ValidationError as _ValErr
        try:
            sale_in = SaleIn(
                client_id=client_id,
                client=client_obj,
                bdc=d.get("bdc") or "",
                service=(d.get("service") or "").strip() or "Prestation",
                amount=float(d.get("amount") or 0),
                payment_method=d.get("payment_method") or "cheque",
                payment_installments=int(d.get("payment_installments") or 1),
                commission_rate=float(d.get("commission_rate") if d.get("commission_rate") is not None else 0.0),
                commercial=d.get("commercial") or "",
                source=d.get("source") or "",
                commission_paid=False,
                commission_month=datetime.now(timezone.utc).strftime("%Y-%m"),
                sale_date=sale_date,
                desired_intervention_date=None,
                status=d.get("status") or "commercial_cheque",
                notes=d.get("notes") or "",
            )
        except _ValErr as e:
            first = e.errors()[0] if e.errors() else {}
            msg = first.get("msg") or "Payload invalide"
            loc = ".".join(str(x) for x in (first.get("loc") or []))
            raise HTTPException(status_code=400, detail=f"Vente invalide ({loc}): {msg}")
        return await create_sale(sale_in, user)  # type: ignore

    if intent == "update_sale_status":
        sale_id = d.get("resolved_sale_id")
        if not sale_id:
            sale = await _resolve_sale_for_status(dict(d), user)
            if sale:
                sale_id = sale["id"]
        if not sale_id:
            raise HTTPException(status_code=404, detail="Vente introuvable")
        status = (d.get("status") or "").strip()
        valid = {"en_cours", "commercial_cheque", "argent_recupere", "chantier_fini", "litige", "annule"}
        if status not in valid:
            raise HTTPException(status_code=400, detail=f"Statut invalide: {status}")
        upd = SaleUpdate(status=status)
        return await update_sale(sale_id, upd, user)  # type: ignore

    raise HTTPException(status_code=400, detail=f"Intent non supporté: {intent}")


# ---------------- AI Devis analyzer (OCR + structured extraction) ----------------

_DEVIS_SYSTEM = """Tu es un extracteur strict de devis / bons de commande pour QYLOT.

RÈGLE ABSOLUE : tu recopies LITTÉRALEMENT ce qui est ÉCRIT sur le document.
Tu ne devines, ne complètes, ne corriges, n'infères RIEN. Si tu hésites → `null` + warning.

Retourne UNIQUEMENT un JSON valide (aucun texte autour, pas de ``` fence) suivant EXACTEMENT ce schéma :

{
  "numero_devis": string|null,             // recopie EXACTE (ex "DV-2024-0157", "N°2024/034"). Jamais confondu avec le téléphone.
  "date_vente": string|null,               // format YYYY-MM-DD. En France DD/MM/YYYY → convertir (12/03/2024 → 2024-03-12).
  "commercial": string|null,               // Nom du commercial VENDEUR uniquement (généralement bas de page "Commercial:" ou "Vendeur:")
  "client_nom": string|null,               // NOM DE FAMILLE du client destinataire, écrit tel quel (majuscules incluses si présentes)
  "client_prenom": string|null,            // PRÉNOM du client destinataire, écrit tel quel
  "client_telephone": string|null,         // Recopie EXACTE (garde les espaces/points si présents, ex "06 12 34 56 78")
  "client_adresse": string|null,           // Rue et n° UNIQUEMENT (jamais le CP ni la ville dans ce champ). Recopie mot-à-mot.
  "client_code_postal": string|null,       // 5 chiffres exacts (France) ou tel qu'écrit
  "client_ville": string|null,             // Recopie EXACTE (respecte majuscules/tirets, ex "SAINT-JEAN-DE-LUZ")
  "client_pays": string|null,
  "prestations": [
    { "designation": string, "description": string|null, "prix_unitaire_ht": number|null,
      "quantite": number|null, "remise": number|null, "montant_ht": number|null }
  ],
  "total_ht": number|null,
  "taux_tva": number|null,                 // en % (ex 10.0) — informatif uniquement
  "warnings": [ string ]                   // liste courte des champs incertains ("date ambigüe", "adresse partiellement lisible"...)
}

RÈGLES CRITIQUES (à respecter sans exception) :
1. RECOPIE MOT POUR MOT. Ne reformule pas. Ne corrige pas les fautes. Ne complète pas les abréviations ("St" reste "St", pas "Saint").
2. CLIENT ≠ ENTREPRISE ÉMETTRICE. L'émetteur est en en-tête / pied avec SIRET, logo, IBAN. Le client est sous "Client :", "À l'attention de", "Facturé à", "Livré à" ou dans un encart séparé.
3. Ne confonds JAMAIS numéro de devis et téléphone.
4. Ne confonds JAMAIS prix unitaire, montant ligne et total HT.
5. Chaque prestation DOIT être une ligne distincte. Ne fusionne jamais 2 prestations.
6. Analyse TOUTES les pages avant de répondre. La signature/total est souvent en dernière page.
7. Nombres : décimales avec un point (5040.00), sans symbole ni espace. "5 040,50 €" → 5040.50.
8. Si une info n'est pas 100% lisible ou ambiguë → `null` + entrée dans "warnings". PLUTÔT NULL QUE FAUX.
9. Ne renvoie AUCUN total_ttc ni montant_tva — QYLOT ne stocke que le HT.
10. Ne renvoie AUCUN texte hors JSON."""


def _parse_num(x):
    try:
        if x is None: return None
        return float(x)
    except Exception:
        return None


def _fuzzy_match_commercial(name: str, options: List[str]) -> Optional[str]:
    if not name or not options:
        return None
    import unicodedata
    def norm(s):
        s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
        return " ".join(s.replace(",", " ").split())
    n = norm(name)
    if not n:
        return None
    parts = set(n.split())
    best, best_score = None, 0.0
    for opt in options:
        o = norm(opt)
        oparts = set(o.split())
        if o == n or parts == oparts:
            return opt
        # partial: intersection ratio
        inter = len(parts & oparts)
        score = inter / max(1, len(parts | oparts))
        # substring match
        if n in o or o in n:
            score = max(score, 0.9)
        if score > best_score:
            best_score, best = score, opt
    return best if best_score >= 0.5 else None


def _consistency_checks(d: dict) -> List[str]:
    warns = []
    # Line-level
    for i, p in enumerate(d.get("prestations") or []):
        pu = _parse_num(p.get("prix_unitaire_ht"))
        qt = _parse_num(p.get("quantite")) or 1
        rm = _parse_num(p.get("remise")) or 0
        mt = _parse_num(p.get("montant_ht"))
        if pu is not None and mt is not None:
            expected = round(pu * qt - rm, 2)
            if abs(expected - mt) > max(0.5, mt * 0.02):
                warns.append(f"Ligne {i+1} : {pu}×{qt}-{rm}={expected} ≠ {mt}")
    # Sum lines vs total_ht
    lines = [_parse_num(p.get("montant_ht")) for p in (d.get("prestations") or [])]
    lines = [x for x in lines if x is not None]
    total_ht = _parse_num(d.get("total_ht"))
    if lines and total_ht is not None:
        s = round(sum(lines), 2)
        if abs(s - total_ht) > max(1.0, total_ht * 0.02):
            warns.append(f"Somme des lignes ({s}) ≠ total HT ({total_ht})")
    # TVA / TTC — plus utilisés : QYLOT ne conserve que le HT.
    # (checks retirés volontairement)
    return warns


async def _find_matching_client(user: dict, extracted: dict) -> Optional[dict]:
    """Look for an existing client that matches the extracted info (phone → name+city)."""
    phone = (extracted.get("client_telephone") or "").strip()
    if phone:
        digits = "".join(ch for ch in phone if ch.isdigit())[-9:]
        if len(digits) >= 8:
            regex = ".*".join(digits)
            c = await db.clients.find_one(cq(user, {"phone": {"$regex": regex}}), {"_id": 0})
            if c:
                return c
    nom = (extracted.get("client_nom") or "").strip()
    prenom = (extracted.get("client_prenom") or "").strip()
    full = f"{prenom} {nom}".strip() if prenom else nom
    if full:
        import re as _re
        pat = _re.escape(full)
        c = await db.clients.find_one(cq(user, {"name": {"$regex": pat, "$options": "i"}}), {"_id": 0})
        if c:
            return c
    return None


@api_router.post("/ai/analyze-devis")
async def ai_analyze_devis(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Read a devis (image or PDF, multi-page supported) and return a structured, pre-filled sale."""
    check_perm(user, "sales", "create")
    _require_external_ai_enabled()
    await _enforce_ai_rate_limit(user, cost_units=3)
    raw = await _read_upload_limited(file)
    mime = (file.content_type or "").lower()
    filename = (file.filename or "").lower()

    images_b64: List[str] = []   # list of PNG base64 (no data: prefix)
    if mime == "application/pdf" or filename.endswith(".pdf"):
        try:
            import fitz  # pymupdf
            doc = fitz.open(stream=raw, filetype="pdf")
            if doc.page_count > MAX_PDF_PAGES:
                doc.close()
                raise HTTPException(status_code=413, detail=f"PDF trop long (max {MAX_PDF_PAGES} pages)")
            for page in doc:
                # iter203 : DPI 240 (au lieu de 180) → OCR nettement plus fiable
                # sur les documents scannés / photocopiés (adresses, n° devis, chiffres).
                pix = page.get_pixmap(dpi=240)
                images_b64.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))
            doc.close()
        except HTTPException:
            raise
        except Exception:
            logger.exception("Unreadable quote PDF")
            raise HTTPException(status_code=400, detail="PDF illisible")
    elif mime.startswith("image/") or filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".heic")):
        images_b64.append(base64.b64encode(raw).decode("utf-8"))
    else:
        raise HTTPException(status_code=400, detail="Format non supporté (PDF ou image uniquement)")

    if not images_b64:
        raise HTTPException(status_code=400, detail="Aucune page à analyser")

    # iter203 : GPT-4o (vision complète, pas -mini) — beaucoup plus fiable pour recopier
    # exactement noms, adresses, n° de devis, dates depuis une photo/scan.
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        # Inject per-company learnings as prompt hint (iter25)
        hint = await _company_ai_learnings_hint(user)
        sys_msg = _DEVIS_SYSTEM + ("\n\n" + hint if hint else "")
        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"devis-{user['id']}-{uuid.uuid4().hex[:8]}",
            system_message=sys_msg,
        ).with_model("openai", "gpt-4o")
        prompt = f"Analyse ce devis ({len(images_b64)} page{'s' if len(images_b64) > 1 else ''}) et renvoie le JSON strict décrit dans les instructions. RECOPIE MOT POUR MOT : nom, prénom, adresse, code postal, ville, numéro de devis, date."
        reply = await chat.send_message(UserMessage(
            text=prompt,
            file_contents=[ImageContent(b) for b in images_b64],
        ))
    except Exception:
        logger.exception("Devis vision error")
        raise HTTPException(status_code=502, detail="Analyse IA temporairement indisponible")

    # Parse JSON (strip possible fences)
    import json as _json
    txt = (reply or "").strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]
        txt = txt.strip()
    try:
        extracted = _json.loads(txt)
    except Exception:
        # Salvage: find first { .. last }
        i, j = txt.find("{"), txt.rfind("}")
        if i >= 0 and j > i:
            try:
                extracted = _json.loads(txt[i:j+1])
            except Exception:
                logger.exception("AI quote returned invalid JSON")
                raise HTTPException(status_code=502, detail="Réponse IA invalide")
        else:
            raise HTTPException(status_code=502, detail="Sortie IA non JSON")

    if not isinstance(extracted, dict):
        raise HTTPException(status_code=502, detail="Sortie IA invalide")

    warnings_out = list(extracted.get("warnings") or [])
    warnings_out.extend(_consistency_checks(extracted))

    # Fuzzy-match commercial to an existing team member
    commercials = await _list_commercials_names(user)
    commercial_matched = _fuzzy_match_commercial(extracted.get("commercial") or "", commercials)
    if extracted.get("commercial") and not commercial_matched:
        warnings_out.append("Commercial non reconnu — à vérifier")

    # Client match
    client_match = await _find_matching_client(user, extracted)

    return {
        "ok": True,
        "pages": len(images_b64),
        "data": extracted,
        "commercial_matched": commercial_matched,
        "client_match": client_match,
        "warnings": warnings_out,
    }


# ---------------- Team members (commerciaux / techniciens) ----------------

class TeamMemberIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: Literal["commercial", "technicien", "sous_traitant", "prospecteur", "responsable_prospecteur"]
    objectif: Optional[float] = Field(default=0, ge=0, le=1_000_000_000, allow_inf_nan=False)
    email: Optional[str] = Field(default="", max_length=320)
    # iter189 — Bypass explicite de la garde anti-doublon quand l'admin confirme
    # sciemment de créer un nouveau membre malgré un utilisateur au prénom similaire.
    confirm_new: Optional[bool] = False

class TeamMemberUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    objectif: Optional[float] = Field(default=None, ge=0, le=1_000_000_000, allow_inf_nan=False)
    email: Optional[str] = Field(default=None, max_length=320)
    # iter61 : visibilité du commercial dans le classement public
    hidden_from_ranking: Optional[bool] = None
    # iter62 : autorisation individuelle aux heures supplémentaires (technicien)
    overtime_enabled: Optional[bool] = None
    # iter116 : seuil d'alerte heures sup personnalisé (override du seuil global de la société)
    overtime_alert_threshold: Optional[float] = Field(default=None, ge=0, le=500)
    # iter68 : visibilité société pour un commercial (par défaut True côté serveur)
    see_company_ca: Optional[bool] = None
    see_company_objectif: Optional[bool] = None
    see_company_progress: Optional[bool] = None
    # iter73 : autorise ce commercial à consulter le classement des autres (défaut True)
    can_view_others_ranking: Optional[bool] = None

@api_router.get("/team")
async def list_team(
    type: Optional[Literal["commercial", "technicien", "sous_traitant", "prospecteur", "responsable_prospecteur"]] = None,
    user: dict = Depends(get_current_user),
):
    q = cq(user)
    if type:
        q["type"] = type
    # iter95 : un commercial n'a aucun accès à la liste des techniciens/sous-traitants.
    if user.get("role") == "commercial" and (type in ("technicien", "sous_traitant") or type is None):
        if type in ("technicien", "sous_traitant"):
            return []
        # type is None : filtrer côté serveur, ne renvoyer que les commerciaux
        q["type"] = "commercial"
    docs = await db.team_members.find(q, {"_id": 0}).sort("name", 1).to_list(500)
    limited_profile = user.get("role") in ("technicien", "sous_traitant", "prospecteur", "responsable_prospecteur")
    for d in docs:
        if limited_profile:
            d.pop("objectif", None)
            d.pop("email", None)
        else:
            d.setdefault("objectif", 0)
            d.setdefault("email", "")
    return docs

@api_router.post("/team")
async def create_team_member(data: TeamMemberIn, user: dict = Depends(require_admin)):
    if data.type not in ("commercial", "technicien", "sous_traitant"):
        raise HTTPException(status_code=400, detail="Type invalide")
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom requis")
    existing = await db.team_members.find_one(cq(user, {"name": name, "type": data.type}))
    if existing:
        raise HTTPException(status_code=400, detail="Déjà existant")
    # iter195 — Pas de blocage « doublon » : si un utilisateur existe déjà avec le même
    # prénom normalisé ou le même email, on RÉCUPÈRE simplement son nom/email canonique
    # et on lie le team_member au user via `user_id`. Pas de 409, pas de dialogue.
    # (Un team_member est un "slot" pour objectif/visibilité/heures sup — pas un account.)
    import unicodedata as _ud
    def _norm(s: str) -> str:
        s = _ud.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
        return " ".join(s.lower().split())
    first = _norm(name).split(" ", 1)[0]
    email_in = (data.email or "").strip().lower()
    linked_user = None
    if data.type in ("technicien", "sous_traitant", "commercial"):
        target_role = {"technicien": "technicien", "sous_traitant": "sous_traitant", "commercial": "commercial"}[data.type]
        # 1) match par email (fort)
        if email_in:
            linked_user = await db.users.find_one(cq(user, {"role": target_role, "email": email_in}), {"_id": 0, "id": 1, "name": 1, "email": 1})
        # 2) match par prénom unique (couvre le cas « Kelyan » vs « Kelyan Richard »)
        if not linked_user and first:
            matches = []
            async for u in db.users.find(cq(user, {"role": target_role}), {"_id": 0, "id": 1, "name": 1, "email": 1}):
                if _norm(u.get("name") or "").split(" ", 1)[0] == first:
                    matches.append(u)
            if len(matches) == 1:
                linked_user = matches[0]
    canonical_name = (linked_user or {}).get("name") or name
    canonical_email = (linked_user or {}).get("email") or email_in
    # Évite un doublon strict si le team_member existe déjà pour ce nom canonique
    existing_canon = await db.team_members.find_one(cq(user, {"name": canonical_name, "type": data.type}), {"_id": 0})
    if existing_canon:
        return existing_canon  # idempotent — pas d'erreur
    doc = with_company({
        "id": str(uuid.uuid4()),
        "name": canonical_name,
        "type": data.type,
        "objectif": float(data.objectif or 0),
        "email": canonical_email,
        "user_id": (linked_user or {}).get("id"),  # lien fort → RBAC & ventes
        "created_at": now_iso(),
    }, user)
    await db.team_members.insert_one(doc.copy())
    await log_audit(user, "create", "team_member", doc["id"], after=doc)
    # Rattachement AUTOMATIQUE des ventes historiques dont le nom correspond
    if data.type in ("commercial", "responsable", "admin"):
        try:
            await _reconcile_sales_commercials(company_id_of(user))
        except Exception as _e:
            logger.warning(f"auto-reconcile after create_team_member failed: {_e}")
    return doc

@api_router.put("/team/{tid}")
async def update_team_member(tid: str, data: TeamMemberUpdate, user: dict = Depends(require_admin)):
    current = await db.team_members.find_one(cq(user, {"id": tid}), {"_id": 0})
    if not current:
        raise HTTPException(status_code=404, detail="Membre introuvable")
    updates = {}
    new_name = None
    if data.name is not None:
        new_name = data.name.strip()
        updates["name"] = new_name
    if data.objectif is not None:
        updates["objectif"] = float(data.objectif)
    if data.email is not None:
        updates["email"] = data.email.strip().lower()
    # iter61 : toggle visibilité classement (admin uniquement)
    if getattr(data, "hidden_from_ranking", None) is not None:
        updates["hidden_from_ranking"] = bool(data.hidden_from_ranking)
    # iter62 : autorisation heures sup (technicien)
    if getattr(data, "overtime_enabled", None) is not None:
        updates["overtime_enabled"] = bool(data.overtime_enabled)
    # iter116 : seuil d'alerte heures sup personnalisé (None => reset au global)
    if hasattr(data, "overtime_alert_threshold"):
        val = getattr(data, "overtime_alert_threshold", None)
        if val is None:
            updates["overtime_alert_threshold"] = None
        else:
            updates["overtime_alert_threshold"] = float(val)
    # iter68 : visibilité société (par commercial)
    for f in ("see_company_ca", "see_company_objectif", "see_company_progress", "can_view_others_ranking"):
        val = getattr(data, f, None)
        if val is not None:
            updates[f] = bool(val)
    if not updates:
        raise HTTPException(status_code=400, detail="Aucun champ à mettre à jour")
    await db.team_members.update_one(cq(user, {"id": tid}), {"$set": updates})
    # Cascade rename in projects.assigned_to when a technicien is renamed
    if new_name and new_name != current.get("name") and current.get("type") == "technicien":
        old = current["name"]
        cursor = db.projects.find(cq(user, {"assigned_to": old}), {"_id": 1, "assigned_to": 1})
        async for doc in cursor:
            new_list = [new_name if n == old else n for n in (doc.get("assigned_to") or [])]
            await db.projects.update_one({"_id": doc["_id"]}, {"$set": {"assigned_to": new_list}})
    # Auto-sync company total objectif from all commerciaux
    if data.objectif is not None or (current.get("type") == "commercial" and new_name):
        commerciaux = await db.team_members.find(cq(user, {"type": "commercial"}), {"_id": 0, "objectif": 1}).to_list(500)
        total = sum(float(t.get("objectif") or 0) for t in commerciaux)
        cid = company_id_of(user)
        await db.settings.update_one(
            {"company_id": cid, "kind": "global"},
            {"$set": {"objectif_ca": total, "kind": "global", "company_id": cid}},
            upsert=True,
        )
    after = await db.team_members.find_one(cq(user, {"id": tid}), {"_id": 0})
    await log_audit(user, "update", "team_member", tid, before=current, after=after)
    return after

@api_router.delete("/team/{tid}")
async def delete_team_member(tid: str, user: dict = Depends(require_admin)):
    doc = await db.team_members.find_one(cq(user, {"id": tid}), {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Membre introuvable")
    await db.team_members.delete_one(cq(user, {"id": tid}))
    # Cascade: pull the technicien's name from any project's assigned_to list
    if doc and doc.get("type") == "technicien":
        await db.projects.update_many(cq(user, {"assigned_to": doc["name"]}), {"$pull": {"assigned_to": doc["name"]}})
    await log_audit(user, "delete", "team_member", tid, before=doc)
    return {"ok": True}


async def _compute_monthly_report(prefix: str, user: dict) -> dict:
    """Shared logic used by both JSON endpoint and PDF endpoint."""
    sales = await db.sales.find(cq(user, {"sale_date": {"$regex": f"^{prefix}"}}), {"_id": 0}).to_list(10000)
    team = await db.team_members.find(cq(user, {"type": "commercial"}), {"_id": 0}).to_list(500)
    names = [t["name"] for t in team]
    for s in sales:
        n = (s.get("commercial") or "").strip()
        if n and n not in names:
            names.append(n)

    def key(n):
        return (n or "").strip().lower()

    per_commercial = {}
    for n in names:
        per_commercial[key(n)] = {
            "commercial": n,
            "sales_count": 0,
            "active_count": 0,
            "cancelled_count": 0,
            "litige_count": 0,
            "ca_total": 0.0,
            "commission_total": 0.0,
            "sources": {"R1": 0, "Assist": 0, "CQ": 0, "CA": 0, "TAP": 0, "Sous-traitance": 0},
        }

    for s in sales:
        # DE sales (iter22): CA is ALWAYS split 50/50 across commercial + commercial_2.
        # Each commercial has an INDEPENDENT commission rate (commission_rate for the primary,
        # commission_rate_2 for the secondary, defaulting to the primary rate for legacy sales).
        is_de = bool(s.get("is_de")) and bool((s.get("commercial_2") or "").strip())
        primary = (s.get("commercial") or "").strip()
        secondary = (s.get("commercial_2") or "").strip() if is_de else ""
        rate_1 = float(s.get("commission_rate") if s.get("commission_rate") is not None else 0)
        rate_2 = float(s.get("commission_rate_2") if s.get("commission_rate_2") is not None else rate_1)
        involved = []  # list of (name, ca_share, commission_rate)
        if is_de and secondary and secondary != primary:
            if primary: involved.append((primary, 0.5, rate_1))
            involved.append((secondary, 0.5, rate_2))
        else:
            if primary: involved.append((primary, 1.0, rate_1))
        if not involved:
            continue
        status = s.get("status", "")
        amount = float(s.get("amount") or 0)
        for (n, ca_share, comm_rate) in involved:
            k = key(n)
            if k not in per_commercial:
                per_commercial[k] = {
                    "commercial": n, "sales_count": 0, "active_count": 0, "cancelled_count": 0,
                    "litige_count": 0, "ca_total": 0.0, "commission_total": 0.0,
                    "sources": {"R1": 0, "Assist": 0, "CQ": 0, "CA": 0, "TAP": 0, "Sous-traitance": 0},
                }
            b = per_commercial[k]
            b["sales_count"] += 1
            if status == "annule":
                b["cancelled_count"] += 1
            elif status == "litige":
                b["litige_count"] += 1
            else:
                b["active_count"] += 1
                b["ca_total"] += amount * ca_share
                b["commission_total"] += amount * ca_share * comm_rate
            src = s.get("source") or ""
            if src in b["sources"]:
                b["sources"][src] += 1

    rows = sorted(per_commercial.values(), key=lambda r: r["ca_total"], reverse=True)
    totals = {
        "sales_count": sum(r["sales_count"] for r in rows),
        "active_count": sum(r["active_count"] for r in rows),
        "cancelled_count": sum(r["cancelled_count"] for r in rows),
        "litige_count": sum(r["litige_count"] for r in rows),
        "ca_total": sum(r["ca_total"] for r in rows),
        "commission_total": sum(r["commission_total"] for r in rows),
        "sources": {
            "R1": sum(r["sources"]["R1"] for r in rows),
            "Assist": sum(r["sources"]["Assist"] for r in rows),
            "CQ": sum(r["sources"]["CQ"] for r in rows),
            "CA": sum(r["sources"]["CA"] for r in rows),
            "TAP": sum(r["sources"].get("TAP", 0) for r in rows),
            "Sous-traitance": sum(r["sources"].get("Sous-traitance", 0) for r in rows),
        },
    }
    return {"month": prefix, "rows": rows, "totals": totals}


@api_router.get("/reports/monthly")
async def monthly_report(month: str = Query(..., pattern=r"^\d{4}-\d{2}$"), user: dict = Depends(get_current_user)):
    check_perm(user, "reports", "view")
    return await _compute_monthly_report(_validated_month(month), user)


@api_router.get("/dashboard/annual")
async def dashboard_annual(year: int = Query(..., ge=2000, le=2100), user: dict = Depends(get_current_user)):
    """iter93 : suivi progression annuel — CA par commercial × mois vs objectif.
    iter193 — Filtre `own` basé sur commercial_user_id (aligné à Sales/Commissions).
    Renvoie systématiquement une ligne par commercial (team_member ou user) même si
    aucun CA sur l'année, pour que chaque personne (ex : Théo) ait son graphique.
    """
    check_perm(user, "sales", "view", "own")
    start = f"{year}-01-01"; end = f"{year}-12-31"
    q = cq(user, {"sale_date": {"$gte": start, "$lte": end}, "status": {"$nin": ["annule", "litige"]}})
    scope = perm_scope(user, "sales", "view")
    if scope == "own":
        q.update(_own_sales_filter(user))
    if _is_prospect_role(user):
        q.update(_prospect_sales_filter(user))
    sales = await db.sales.find(q, {"_id": 0, "amount": 1, "sale_date": 1, "commercial": 1, "commercial_2": 1, "commercial_user_id": 1, "commercial_2_user_id": 1, "is_de": 1}).to_list(20000)
    # Résolution id → nom canonique (nom du user si connu, sinon le champ texte du sale)
    all_uids = list({s.get(k) for s in sales for k in ("commercial_user_id", "commercial_2_user_id") if s.get(k)})
    users_by_id = {}
    if all_uids:
        async for u in db.users.find(cq(user, {"id": {"$in": all_uids}}), {"_id": 0, "id": 1, "name": 1}):
            users_by_id[u["id"]] = u.get("name") or ""

    from collections import defaultdict
    bucket = defaultdict(lambda: [0.0] * 12)
    company_total = [0.0] * 12

    def _slot_name(sale, id_slot, name_slot):
        uid = sale.get(id_slot)
        if uid and users_by_id.get(uid):
            return users_by_id[uid]
        return sale.get(name_slot) or ""

    for s in sales:
        d = (s.get("sale_date") or "")
        try:
            m = int(d[5:7])
        except Exception:
            logger.debug("Mois de vente historique invalide ignoré dans les statistiques")
            continue
        if m < 1 or m > 12:
            continue
        amt = float(s.get("amount") or 0)
        n1 = _slot_name(s, "commercial_user_id", "commercial")
        n2 = _slot_name(s, "commercial_2_user_id", "commercial_2")
        is_de = bool(s.get("is_de")) and bool((n2 or "").strip())
        if is_de:
            share = amt * 0.5
            if n1: bucket[n1][m - 1] += share
            if n2: bucket[n2][m - 1] += share
        elif n1:
            bucket[n1][m - 1] += amt
        company_total[m - 1] += amt

    team = await db.team_members.find(cq(user, {"type": "commercial"}), {"_id": 0, "name": 1, "objectif": 1}).to_list(500)
    obj_map = {(t.get("name") or ""): float(t.get("objectif") or 0) for t in team}

    # iter196 — Confidentialité : un commercial (scope "own") ne voit QUE SA propre ligne.
    # `known_names` doit donc être restreint à son propre nom (et à ceux issus du bucket
    # calculé sur SES ventes). En scope "team"/"all" (admin/responsable), on ajoute tous
    # les commerciaux connus + users role commercial/responsable pour donner un graphique
    # à chacun, même sans CA.
    known_names = set(bucket.keys())
    if scope == "own":
        my_name = (user.get("name") or "").strip()
        if my_name:
            known_names.add(my_name)
    else:
        known_names |= set(obj_map.keys())
        async for u in db.users.find(cq(user, {"role": {"$in": ["commercial", "responsable"]}}), {"_id": 0, "name": 1}):
            nm = u.get("name") or ""
            if nm: known_names.add(nm)
    # Dédoublonnage : un prénom seul (« Thomas ») fusionne dans le nom complet unique (« Thomas Delporte »)
    import unicodedata as _ud
    def _nk(x):
        return " ".join(_ud.normalize("NFKD", x or "").encode("ascii", "ignore").decode().lower().split())
    for name in list(known_names):
        nk = _nk(name)
        if not nk or " " in nk:
            continue
        fulls = [o for o in known_names if o != name and " " in _nk(o) and _nk(o).split(" ", 1)[0] == nk]
        if len(fulls) == 1:
            full = fulls[0]
            if name in bucket:
                merged = bucket[full]
                for i, v in enumerate(bucket.pop(name)):
                    merged[i] += v
            if not obj_map.get(full) and obj_map.get(name):
                obj_map[full] = obj_map[name]
            known_names.discard(name)
    result_rows = []
    for name in known_names:
        if not name:
            continue
        monthly = bucket.get(name, [0.0] * 12)
        total = round(sum(monthly), 2)
        obj_month = obj_map.get(name, 0.0)
        # Fallback : match par prénom normalisé (ex : « Théo » vs « Théo Dudal »)
        if not obj_month:
            key = _norm_name(name).split(" ", 1)[0]
            if key:
                for tn, tv in obj_map.items():
                    if _norm_name(tn).split(" ", 1)[0] == key:
                        obj_month = tv; break
        obj_annual = round(obj_month * 12, 2)
        result_rows.append({
            "commercial": name,
            "monthly": [round(v, 2) for v in monthly],
            "total": total,
            "objectif_monthly": obj_month,
            "objectif_annual": obj_annual,
            "progress_pct": round((total / obj_annual * 100) if obj_annual > 0 else 0, 1),
        })
    result_rows.sort(key=lambda r: -r["total"])
    settings = await db.settings.find_one({"company_id": company_id_of(user), "kind": "global"}, {"_id": 0}) or {}
    company_obj_monthly = float(settings.get("objectif_ca") or sum(obj_map.values()) or 0)
    return {
        "year": year,
        "rows": result_rows,
        "company_total_monthly": [round(v, 2) for v in company_total],
        "company_total": round(sum(company_total), 2),
        "company_objectif_annual": round(company_obj_monthly * 12, 2),
    }


@api_router.get("/commissions.pdf")
async def commissions_pdf(month: str = Query(..., pattern=r"^\d{4}-\d{2}$"), user: dict = Depends(get_current_user)):
    """iter93 : récap PDF des commissions du mois + primes atteintes."""
    month = _validated_month(month)
    check_perm(user, "commissions", "view", "own")

    # Load commissions rows for the month (same shape as /commissions)
    rows = await list_commissions(user=user)
    # iter105 : la page Commissions filtre par `commission_month` (mois de paiement de la commission).
    # Permet de reporter une vente d'août au mois de paiement septembre. Dashboard/Rapport gardent sale_date.
    # iter205 : `non_financable` exclu au même titre que `annule`/`litige` (pas de paiement possible).
    month_rows = [r for r in rows if ((r.get("commission_month") or (r.get("sale_date") or "")[:7]) == month[:7]) and r.get("status") not in ("annule", "litige", "non_financable")]
    month_rows.sort(key=lambda r: (r.get("sale_date") or "", r.get("commercial") or ""))
    # Load bonus awards reached this month
    awards = await db.bonus_awards.find(cq(user, {"period_key": {"$in": [month[:7], month[:4]]}}), {"_id": 0}).to_list(500)
    awards.sort(key=lambda a: (a.get("commercial") or "", a.get("bonus_name") or ""))

    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    import io as _io

    buf = _io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=13*mm, rightMargin=13*mm, topMargin=15*mm, bottomMargin=15*mm, title=f"Commissions {month}")
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Title"], fontSize=20, textColor=colors.HexColor("#0f172a"), spaceAfter=4)
    sub_style = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#64748b"), spaceAfter=14)
    section_style = ParagraphStyle("Section", parent=styles["Heading2"], fontSize=13, textColor=colors.HexColor("#0f172a"), spaceBefore=10, spaceAfter=6)

    months_fr = ["Janvier","Février","Mars","Avril","Mai","Juin","Juillet","Août","Septembre","Octobre","Novembre","Décembre"]
    y_, m_ = month.split("-")
    label = f"{months_fr[int(m_)-1]} {y_}"

    story = []
    story.append(Paragraph(f"Récap commissions — {label}", title_style))
    story.append(Paragraph(f"{EMAIL_FROM_NAME} · Généré le {datetime.now(ZoneInfo('Europe/Paris')).strftime('%d/%m/%Y à %H:%M')}", sub_style))

    def eur(n):
        return f"{int(round(float(n or 0))):,} €".replace(",", " ")

    total_amount = sum(float(r.get("amount") or 0) for r in month_rows)
    total_commission = sum(float(r.get("commission_amount") or 0) for r in month_rows)
    total_paid = sum(float(r.get("commission_amount") or 0) for r in month_rows if r.get("commission_paid"))
    total_to_pay = total_commission - total_paid

    kpi_data = [
        ["Commissions", "Reste à payer", "Déjà payé", "CA HT"],
        [eur(total_commission), eur(total_to_pay), eur(total_paid), eur(total_amount)],
    ]
    kpi = Table(kpi_data, colWidths=[45*mm, 45*mm, 45*mm, 45*mm])
    kpi.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,0), colors.HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0,0),(-1,0), colors.HexColor("#64748b")),
        ("FONTSIZE", (0,0),(-1,0), 8),
        ("FONTSIZE", (0,1),(-1,1), 15),
        ("FONTNAME", (0,1),(-1,1), "Helvetica-Bold"),
        ("ALIGN", (0,0),(-1,-1), "CENTER"),
        ("BOTTOMPADDING", (0,0),(-1,0), 6),
        ("TOPPADDING", (0,1),(-1,1), 8),
        ("BOTTOMPADDING", (0,1),(-1,1), 8),
        ("BOX", (0,0),(-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0,0),(-1,-1), 0.25, colors.HexColor("#e2e8f0")),
    ]))
    story.append(kpi)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Détail des commissions", section_style))
    header = ["Date", "BDC", "Client", "Commercial", "Montant HT", "Taux", "Commission", "Payé"]
    data = [header]
    for r in month_rows:
        data.append([
            r.get("sale_date") or "—",
            r.get("bdc") or "—",
            (r.get("client_name") or "—")[:32],
            r.get("commercial") or "—",
            eur(r.get("amount") or 0),
            f"{int(round((r.get('rate') or 0)*100))}%" if r.get("rate") is not None else "—",
            eur(r.get("commission_amount") or 0),
            "Oui" if r.get("commission_paid") else "Non",
        ])
    data.append(["", "", "", "TOTAL", eur(total_amount), "", eur(total_commission), ""])
    col_widths = [22*mm, 22*mm, 44*mm, 30*mm, 22*mm, 12*mm, 24*mm, 12*mm]
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        ("BACKGROUND", (0,0),(-1,0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0,0),(-1,0), colors.white),
        ("FONTNAME", (0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0),(-1,0), 9),
        ("FONTSIZE", (0,1),(-1,-1), 9),
        ("ALIGN", (4,0),(-1,-1), "RIGHT"),
        ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
        ("BOX", (0,0),(-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0,0),(-1,-1), 0.25, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0,-1),(-1,-1), colors.HexColor("#f1f5f9")),
        ("FONTNAME", (0,-1),(-1,-1), "Helvetica-Bold"),
    ])
    for i in range(1, len(data) - 1):
        if i % 2 == 0:
            style.add("BACKGROUND", (0,i),(-1,i), colors.HexColor("#f8fafc"))
    t.setStyle(style)
    story.append(t)

    if awards:
        story.append(Paragraph("Primes atteintes", section_style))
        ah = ["Commercial", "Palier", "Période", "CA atteint", "Prime"]
        adata = [ah]
        total_bonus = 0.0
        for a in awards:
            adata.append([
                a.get("commercial") or "—",
                a.get("bonus_name") or "—",
                a.get("period_key") or "—",
                eur(a.get("ca_reached") or 0),
                eur(a.get("amount") or 0),
            ])
            total_bonus += float(a.get("amount") or 0)
        adata.append(["", "", "", "TOTAL", eur(total_bonus)])
        at = Table(adata, colWidths=[40*mm, 45*mm, 30*mm, 35*mm, 30*mm], repeatRows=1)
        at.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0,0),(-1,0), colors.white),
            ("FONTNAME", (0,0),(-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0),(-1,0), 9),
            ("FONTSIZE", (0,1),(-1,-1), 9),
            ("ALIGN", (3,0),(-1,-1), "RIGHT"),
            ("BOX", (0,0),(-1,-1), 0.5, colors.HexColor("#e2e8f0")),
            ("INNERGRID", (0,0),(-1,-1), 0.25, colors.HexColor("#e2e8f0")),
            ("BACKGROUND", (0,-1),(-1,-1), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0,-1),(-1,-1), "Helvetica-Bold"),
        ]))
        story.append(at)

    story.append(Spacer(1, 12))
    story.append(Paragraph(f"<font color='#94a3b8' size='8'>Document confidentiel — {EMAIL_FROM_NAME}</font>", styles["Normal"]))
    doc.build(story)
    buf.seek(0)
    filename = f"commissions-{month}.pdf"
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@api_router.get("/reports/monthly.pdf")
async def monthly_report_pdf(month: str = Query(..., pattern=r"^\d{4}-\d{2}$"), user: dict = Depends(get_current_user)):
    """PDF export protected by the same centralized authentication as the API."""
    month = _validated_month(month)
    check_perm(user, "reports", "view")

    report = await _compute_monthly_report(month[:7], user)

    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    import io as _io

    buf = _io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm, title=f"Rapport {month}")
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Title"], fontSize=20, textColor=colors.HexColor("#0f172a"), spaceAfter=4)
    sub_style = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#64748b"), spaceAfter=14)
    section_style = ParagraphStyle("Section", parent=styles["Heading2"], fontSize=13, textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=6)

    months_fr = ["Janvier","Février","Mars","Avril","Mai","Juin","Juillet","Août","Septembre","Octobre","Novembre","Décembre"]
    y_, m_ = month.split("-")
    label = f"{months_fr[int(m_)-1]} {y_}"

    story = []
    story.append(Paragraph(f"Rapport mensuel — {label}", title_style))
    story.append(Paragraph(f"{EMAIL_FROM_NAME} · Généré le {datetime.now(ZoneInfo('Europe/Paris')).strftime('%d/%m/%Y à %H:%M')}", sub_style))

    tot = report["totals"]
    def eur(n):
        return f"{int(n):,} €".replace(",", " ")
    kpi_data = [
        ["Ventes actives", "Annulations", "CA du mois", "Commissions"],
        [str(tot["active_count"]), str(tot["cancelled_count"]), eur(tot['ca_total']), eur(tot['commission_total'])],
    ]
    kpi_table = Table(kpi_data, colWidths=[45*mm, 45*mm, 45*mm, 45*mm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#64748b")),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, 1), 16),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#0f172a")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 1), (-1, 1), 8),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("Détail par commercial", section_style))
    header = ["Commercial", "Ventes", "R1", "Assist", "CQ", "CA", "TAP", "Annulé", "CA €", "Commission €"]
    rows = [header]
    for r in report["rows"]:
        rows.append([
            r["commercial"], str(r["sales_count"]),
            str(r["sources"]["R1"]), str(r["sources"]["Assist"]),
            str(r["sources"]["CQ"]), str(r["sources"]["CA"]),
            str(r["sources"].get("TAP", 0)),
            str(r["cancelled_count"]),
            eur(r['ca_total']), eur(r['commission_total']),
        ])
    rows.append([
        "TOTAL", str(tot["sales_count"]),
        str(tot["sources"]["R1"]), str(tot["sources"]["Assist"]),
        str(tot["sources"]["CQ"]), str(tot["sources"]["CA"]),
        str(tot["sources"].get("TAP", 0)),
        str(tot["cancelled_count"]), eur(tot['ca_total']), eur(tot['commission_total']),
    ])
    col_widths = [30*mm, 13*mm, 11*mm, 14*mm, 11*mm, 11*mm, 11*mm, 14*mm, 22*mm, 27*mm]
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f1f5f9")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ])
    for i in range(1, len(rows) - 1):
        if i % 2 == 0:
            style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f8fafc"))
    t.setStyle(style)
    story.append(t)
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"<font color='#94a3b8' size='8'>Rapport confidentiel — {EMAIL_FROM_NAME}</font>", styles["Normal"]))

    doc.build(story)
    buf.seek(0)
    filename = f"rapport-{month}.pdf"
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})






DEFAULT_COMMISSION_CA_THRESHOLD = 30000.0
DEFAULT_COMMISSION_CA_RATE_BEFORE = 0.10
DEFAULT_COMMISSION_CA_RATE_AFTER = 0.15
DEFAULT_COMMISSION_DISCOUNT_TIERS = [
    {"max_discount": 5.0, "rate": 0.15},
    {"max_discount": 10.0, "rate": 0.10},
    {"max_discount": 20.0, "rate": 0.05},
    {"max_discount": 100.0, "rate": 0.0},
]


def _commission_config_from_settings(s: dict) -> dict:
    return {
        "ca_threshold": float(s.get("commission_ca_threshold") if s.get("commission_ca_threshold") is not None else DEFAULT_COMMISSION_CA_THRESHOLD),
        "ca_rate_before": float(s.get("commission_ca_rate_before") if s.get("commission_ca_rate_before") is not None else DEFAULT_COMMISSION_CA_RATE_BEFORE),
        "ca_rate_after": float(s.get("commission_ca_rate_after") if s.get("commission_ca_rate_after") is not None else DEFAULT_COMMISSION_CA_RATE_AFTER),
        "discount_tiers": (s.get("commission_discount_tiers") if isinstance(s.get("commission_discount_tiers"), list) else DEFAULT_COMMISSION_DISCOUNT_TIERS),
    }


def _rate_for_discount(discount_percent, tiers):
    dp = float(discount_percent or 0)
    for t in sorted(tiers or [], key=lambda x: float(x.get("max_discount") or 0)):
        if dp <= float(t.get("max_discount") or 0):
            return float(t.get("rate") or 0)
    return 0.0


def _resolve_sale_rate(sale: dict, slot: int, per_commercial_ca_evolutive: dict, cfg: dict) -> float:
    ctype = ((sale.get("commission_type_2") or sale.get("commission_type")) if slot == 2 else sale.get("commission_type")) or "fixed"
    if ctype == "fixed":
        r = sale.get("commission_rate_2") if slot == 2 else sale.get("commission_rate")
        if r is None and slot == 2:
            r = sale.get("commission_rate")
        return float(r if r is not None else 0.0)
    if ctype == "evolutive_ca":
        # iter115 : le taux évolutive_ca est reconcilié en base à chaque mutation (iter113).
        #   On lit directement `commission_rate` / `commission_rate_2` qui reflète le CA
        #   mensuel cumulé du commercial. Fallback : recalcul dynamique à partir du seuil
        #   PER-VENTE (pas de la config globale) + index cumulé mensuel.
        stored = sale.get("commission_rate_2") if slot == 2 else sale.get("commission_rate")
        if stored is not None:
            return float(stored)
        who = (sale.get("commercial_2") if slot == 2 else sale.get("commercial")) or ""
        ca = float(per_commercial_ca_evolutive.get(who.strip().lower(), 0.0))
        threshold = float(sale.get("evolutive_ca_threshold") or cfg.get("ca_threshold") or 0)
        r_below = float(sale.get("evolutive_rate_below") if sale.get("evolutive_rate_below") is not None else cfg.get("ca_rate_before") or 0)
        r_above = float(sale.get("evolutive_rate_above") if sale.get("evolutive_rate_above") is not None else cfg.get("ca_rate_after") or 0)
        return r_above if ca >= threshold else r_below
    if ctype == "evolutive_discount":
        return _rate_for_discount(sale.get("discount_percent"), cfg["discount_tiers"])
    return 0.0


async def _company_commission_config(user: dict) -> dict:
    s = await db.settings.find_one({"company_id": company_id_of(user), "kind": "global"}, {"_id": 0}) or {}
    return _commission_config_from_settings(s)


def _build_ca_evolutive_index(sales):
    """iter115 : indexe le CA MENSUEL CUMULÉ par commercial (toutes ventes actives).
    Sert de fallback quand la reconcile en base ne s'est pas encore appliquée."""
    idx = {}
    for s in sales:
        if (s.get("status") or "") in ("annule", "litige"):
            continue
        amt = float(s.get("amount") or 0)
        is_de = bool(s.get("is_de")) and bool((s.get("commercial_2") or "").strip())
        primary = (s.get("commercial") or "").strip().lower()
        secondary = (s.get("commercial_2") or "").strip().lower() if is_de else ""
        share_primary = 0.5 if is_de else 1.0
        if primary:
            idx[primary] = idx.get(primary, 0.0) + amt * share_primary
        if is_de and secondary:
            idx[secondary] = idx.get(secondary, 0.0) + amt * 0.5
    return idx


async def _commercial_month_ca(company_id: str, commercial_user_id: str, commission_month: str) -> float:
    """Somme du CA (ventes actives, hors annule/litige) d'un commercial pour un mois.
    iter123 : filtre par `sale_date` (YYYY-MM prefix) — cohérent avec la page Ventes
    "Ce mois". Le `commission_month` (paramètre) sert de mois de référence YYYY-MM.
    Applique le split 50/50 sur les ventes DE."""
    if not (company_id and commercial_user_id and commission_month):
        return 0.0
    q = {
        "company_id": company_id,
        "sale_date": {"$regex": f"^{commission_month[:7]}"},
        "$or": [
            {"commercial_user_id": commercial_user_id},
            {"commercial_2_user_id": commercial_user_id},
        ],
    }
    sales = await db.sales.find(q, {"_id": 0}).to_list(5000)
    total = 0.0
    for s in sales:
        if (s.get("status") or "") in ("annule", "litige"):
            continue
        amt = float(s.get("amount") or 0)
        is_de = bool(s.get("is_de")) and bool((s.get("commercial_2") or "").strip())
        if is_de:
            if s.get("commercial_user_id") == commercial_user_id:
                total += amt * 0.5
            if s.get("commercial_2_user_id") == commercial_user_id:
                total += amt * 0.5
        else:
            if s.get("commercial_user_id") == commercial_user_id:
                total += amt
    return round(total, 2)


async def _reconcile_evolutive_ca_rates_for(company_id: str, commercial_user_id: str, commission_month: str) -> int:
    """iter113 : recalcule et persiste `commission_rate` (et `commission_rate_2`) des ventes
    de type `evolutive_ca` du commercial pour le mois. Le taux dépend du CA CUMULÉ du mois
    (ventes actives, hors annule/litige), pas du montant de la vente individuelle.
    - CA cumulé >= evolutive_ca_threshold → evolutive_rate_above
    - sinon → evolutive_rate_below
    Retourne le nb de ventes mises à jour."""
    if not (company_id and commercial_user_id and commission_month):
        return 0
    total = await _commercial_month_ca(company_id, commercial_user_id, commission_month)
    q = {
        "company_id": company_id,
        "sale_date": {"$regex": f"^{commission_month[:7]}"},
        "$or": [
            {"commercial_user_id": commercial_user_id},
            {"commercial_2_user_id": commercial_user_id},
        ],
    }
    sales = await db.sales.find(q, {"_id": 0}).to_list(5000)
    _s = await db.settings.find_one({"company_id": company_id, "kind": "global"}, {"_id": 0}) or {}
    _cfg = {"ca_threshold": float(_s.get("commission_ca_threshold") or 30000.0),
            "ca_rate_before": float(_s["commission_ca_rate_before"]) if _s.get("commission_ca_rate_before") is not None else 0.10,
            "ca_rate_after": float(_s["commission_ca_rate_after"]) if _s.get("commission_ca_rate_after") is not None else 0.13}
    updated = 0
    for s in sales:
        updates = {}
        # Paramètres per-vente, sinon réglages société (ventes créées/modifiées sans palier)
        threshold = float(s.get("evolutive_ca_threshold") if s.get("evolutive_ca_threshold") is not None else _cfg["ca_threshold"])
        r_below = s.get("evolutive_rate_below") if s.get("evolutive_rate_below") is not None else _cfg["ca_rate_before"]
        r_above = s.get("evolutive_rate_above") if s.get("evolutive_rate_above") is not None else _cfg["ca_rate_after"]
        type_2 = s.get("commission_type_2") or s.get("commission_type") or "fixed"
        # Slot 1
        if s.get("commercial_user_id") == commercial_user_id and (s.get("commission_type") or "fixed") == "evolutive_ca":
            if r_below is not None and r_above is not None:
                new_rate = float(r_above) if total >= threshold else float(r_below)
                if abs(float(s.get("commission_rate") or 0) - new_rate) > 1e-9:
                    updates["commission_rate"] = new_rate
        # Slot 2 (DE) — hérite du type du commercial 1 si non précisé
        if s.get("is_de") and s.get("commercial_2_user_id") == commercial_user_id and type_2 == "evolutive_ca":
            if r_below is not None and r_above is not None:
                new_rate = float(r_above) if total >= threshold else float(r_below)
                if abs(float(s.get("commission_rate_2") or 0) - new_rate) > 1e-9:
                    updates["commission_rate_2"] = new_rate
        if updates:
            await db.sales.update_one({"company_id": company_id, "id": s["id"]}, {"$set": updates})
            updated += 1
    return updated


async def _reconcile_after_sale_mutation(company_id: str, tuples):
    """tuples = iterable of (commercial_user_id, commission_month). Dédupe et recalcule."""
    seen = set()
    total = 0
    for cuid, cm in tuples:
        if not cuid or not cm:
            continue
        key = (cuid, cm)
        if key in seen:
            continue
        seen.add(key)
        try:
            total += await _reconcile_evolutive_ca_rates_for(company_id, cuid, cm)
        except Exception as _e:
            logger.warning(f"reconcile evolutive_ca failed for {key}: {_e}")
    return total


@api_router.get("/commissions")
async def list_commissions(user: dict = Depends(get_current_user)):
    check_perm(user, "commissions", "view", "own")
    # iter117/123 : recalcul systématique lazy — à chaque lecture des commissions, on reconcilie
    # les taux `evolutive_ca` pour toutes les paires (commercial_user_id, sale_date YYYY-MM)
    # de la société. Idempotent, self-healing quand des ventes anciennes n'ont pas été
    # touchées par la reconcile write-time (iter113). Le mois est extrait du sale_date
    # (source de vérité — cohérent avec la page Ventes "Ce mois").
    try:
        cid = company_id_of(user)
        pairs = await db.sales.aggregate([
            {"$match": {"company_id": cid, "$or": [{"commission_type": "evolutive_ca"}, {"commission_type_2": "evolutive_ca"}]}},
            {"$project": {
                "_id": 0,
                "cm": {"$substr": ["$sale_date", 0, 7]},
                "pairs": [
                    {"cuid": "$commercial_user_id"},
                    {"cuid": "$commercial_2_user_id"},
                ],
            }},
            {"$unwind": "$pairs"},
            {"$match": {"pairs.cuid": {"$ne": None}, "cm": {"$ne": ""}}},
            {"$group": {"_id": {"cuid": "$pairs.cuid", "cm": "$cm"}}},
        ]).to_list(2000)
        tuples = [(p["_id"]["cuid"], p["_id"]["cm"]) for p in pairs]
        if tuples:
            await _reconcile_after_sale_mutation(cid, tuples)
    except Exception as _e:
        logger.warning(f"lazy reconcile evolutive_ca on list_commissions failed: {_e}")
    scope = perm_scope(user, "commissions", "view")
    q = cq(user)
    if scope == "own":
        q.update(_own_sales_filter(user))
    sales = await db.sales.find(q, {"_id": 0}).sort("sale_date", -1).to_list(5000)
    ids = list({s["client_id"] for s in sales})
    clients = await db.clients.find(cq(user, {"id": {"$in": ids}}), {"_id": 0}).to_list(5000)
    cmap = {c["id"]: c for c in clients}
    # iter27: precompute evolutive CA index and load company commission config
    cfg = await _company_commission_config(user)
    # For evolutive_ca, compute using ALL sales of the company (not filtered by own scope)
    all_sales = sales if scope != "own" else await db.sales.find(cq(user), {"_id": 0, "amount": 1, "commercial": 1, "commercial_2": 1, "is_de": 1, "commission_type": 1, "commission_type_2": 1, "status": 1}).to_list(5000)
    ca_evo_idx = _build_ca_evolutive_index(all_sales)
    out = []
    for s in sales:
        c = cmap.get(s["client_id"], {})
        amount = float(s.get("amount") or 0)
        commercial_2 = (s.get("commercial_2") or "").strip()
        is_de = bool(s.get("is_de")) and bool(commercial_2)
        # iter204 : GARDE ANTI-DOUBLON — si les 2 slots d'une vente DE désignent
        # le MÊME commercial (par user_id ou par nom normalisé accent-insensible),
        # on force is_de=False → une seule ligne, share=1.0. Fix « BDC 2204 Billot
        # apparaît 2× dans les commissions de Thomas ».
        if is_de:
            same_uid = (s.get("commercial_user_id") and
                        s.get("commercial_user_id") == s.get("commercial_2_user_id"))
            same_name = (_norm_name(s.get("commercial") or "") ==
                         _norm_name(commercial_2)) and bool(_norm_name(commercial_2))
            if same_uid or same_name:
                is_de = False
        share = 0.5 if is_de else 1.0
        rate_1 = _resolve_sale_rate(s, 1, ca_evo_idx, cfg)
        rate_2 = _resolve_sale_rate(s, 2, ca_evo_idx, cfg) if is_de else 0.0
        base = {
            "sale_id": s["id"], "sale_date": s.get("sale_date", ""), "bdc": s.get("bdc", ""),
            "client_name": c.get("name", ""), "service": s.get("service", ""),
            "source": s.get("source", ""), "amount": amount,
            "commission_paid": bool(s.get("commission_paid", False)),
            "commission_month": s.get("commission_month") or "", "status": s.get("status", ""),
            "is_de": is_de,
            "commission_type": s.get("commission_type") or "fixed",
            "commission_type_2": s.get("commission_type_2") if is_de else None,
            "discount_percent": s.get("discount_percent"),
        }
        primary_row = {
            **base, "commercial": s.get("commercial", ""), "share": share,
            "commercial_slot": 1,
            "commission_rate": rate_1,
            "ca_share": round(amount * share, 2),
            "commission_amount": round(amount * share * rate_1, 2),
        }
        secondary_row = None
        if is_de:
            secondary_row = {
                **base, "commercial": commercial_2, "share": 0.5,
                "commercial_slot": 2,
                "commission_rate": rate_2,
                "ca_share": round(amount * 0.5, 2),
                "commission_amount": round(amount * 0.5 * rate_2, 2),
            }
        if scope == "own" and is_de:
            # iter98 : match par commercial_user_id (autorité) OU nom normalisé — fini le strict `uname == s.commercial` qui manquait les DE avec accent/casse différente
            uid = user.get("id")
            uname_norm = _norm_name(user.get("name") or "")
            mine_slot1 = (s.get("commercial_user_id") == uid) or (_norm_name(s.get("commercial") or "") == uname_norm)
            mine_slot2 = (s.get("commercial_2_user_id") == uid) or (_norm_name(commercial_2) == uname_norm)
            if mine_slot1:
                out.append(primary_row)
            if mine_slot2 and secondary_row is not None:
                out.append(secondary_row)
            continue
        out.append(primary_row)
        if secondary_row is not None:
            out.append(secondary_row)
    # iter204 : dédup finale de sécurité — un même (sale_id, commercial normalisé)
    # ne peut apparaître qu'UNE fois, quoi qu'il arrive (blindage contre données
    # corrompues où commercial_1 == commercial_2 aurait échappé au filtre plus haut).
    seen = set()
    deduped = []
    for r in out:
        key = (r.get("sale_id"), _norm_name(r.get("commercial") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped


@api_router.get("/commissions/history")
async def commissions_history(user: dict = Depends(get_current_user), months: int = Query(12, ge=1, le=36)):
    """iter179 — Historique des primes/commissions gagnées : agrège par mois de paiement
    (`commission_month` ou fallback `sale_date[:7]`) et par commercial (nom).
    Renvoie total, payé, à payer + décompte de ventes. Respecte le scope (own => seulement
    ses propres commissions). Limite : `months` mois glissants (par défaut 12).
    """
    check_perm(user, "commissions", "view", "own")
    # Réutilise la même logique que list_commissions pour la cohérence des calculs
    rows = await list_commissions(user)  # type: ignore
    if not isinstance(rows, list):
        return {"months": [], "commercials": [], "matrix": {}, "totals_by_month": {}, "totals_by_commercial": {}}
    from datetime import date as _date
    _today = _date.today()
    # Construit la liste des mois cibles (du plus ancien au plus récent)
    months = max(1, min(int(months or 12), 36))
    y, m = _today.year, _today.month
    month_keys: list = []
    for i in range(months - 1, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12; yy -= 1
        month_keys.append(f"{yy:04d}-{mm:02d}")
    month_set = set(month_keys)
    # Agrégation
    matrix: dict = {}  # matrix[commercial][month] = {total, paid, to_pay, count}
    totals_by_month: dict = {mk: {"total": 0.0, "paid": 0.0, "to_pay": 0.0, "count": 0} for mk in month_keys}
    totals_by_commercial: dict = {}
    for r in rows:
        # Filtrer statuts non commissionnables (annulé / litige / non finançable) — cohérent avec la vue mensuelle
        if r.get("status") in ("annule", "litige", "non_financable"):
            continue
        cm = r.get("commission_month") or (r.get("sale_date") or "")[:7]
        if cm not in month_set:
            continue
        name = (r.get("commercial") or "").strip() or "—"
        amount = float(r.get("commission_amount") or 0)
        paid = bool(r.get("commission_paid"))
        cell = matrix.setdefault(name, {}).setdefault(cm, {"total": 0.0, "paid": 0.0, "to_pay": 0.0, "count": 0})
        cell["total"] += amount
        cell["count"] += 1
        if paid: cell["paid"] += amount
        else: cell["to_pay"] += amount
        tm = totals_by_month[cm]
        tm["total"] += amount; tm["count"] += 1
        if paid: tm["paid"] += amount
        else: tm["to_pay"] += amount
        tc = totals_by_commercial.setdefault(name, {"total": 0.0, "paid": 0.0, "to_pay": 0.0, "count": 0})
        tc["total"] += amount; tc["count"] += 1
        if paid: tc["paid"] += amount
        else: tc["to_pay"] += amount
    # Arrondi en 2 déc.
    def _r(d):
        for k in ("total", "paid", "to_pay"):
            if k in d: d[k] = round(d[k], 2)
        return d
    for name in matrix:
        for mk in matrix[name]:
            _r(matrix[name][mk])
    for mk in totals_by_month: _r(totals_by_month[mk])
    for n in totals_by_commercial: _r(totals_by_commercial[n])
    commercials = sorted(matrix.keys(), key=lambda x: (-totals_by_commercial.get(x, {}).get("total", 0), x.lower()))
    return {
        "months": month_keys,
        "commercials": commercials,
        "matrix": matrix,
        "totals_by_month": totals_by_month,
        "totals_by_commercial": totals_by_commercial,
    }


# ---------------- Settings (objectif CA) ----------------

class CommissionDiscountTierIn(BaseModel):
    max_discount: float = Field(ge=0, le=100, allow_inf_nan=False)
    rate: float = Field(ge=0, le=1, allow_inf_nan=False)


class ProspectManagerBonusIn(BaseModel):
    id: Optional[str] = Field(default=None, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    metric: Literal["ca", "sales"] = "ca"
    threshold: float = Field(ge=0, le=1_000_000_000, allow_inf_nan=False)
    amount: float = Field(ge=0, le=1_000_000, allow_inf_nan=False)


class SettingsIn(BaseModel):
    objectif_ca: Optional[float] = Field(default=None, ge=0, le=1_000_000_000, allow_inf_nan=False)
    # iter132 : objectif annuel avec override manuel (null => fallback objectif_ca * 12)
    objectif_ca_year: Optional[float] = Field(default=None, ge=0, le=1_000_000_000)
    theme_primary: Optional[str] = Field(default=None, max_length=32)
    theme_accent: Optional[str] = Field(default=None, max_length=32)
    font_family: Optional[str] = Field(default=None, max_length=120)
    logo: Optional[str] = Field(default=None, max_length=6_000_000)  # validated image data URI or approved HTTPS URL
    app_name: Optional[str] = Field(default=None, max_length=120)
    overtime_alert_threshold: Optional[float] = Field(default=None, ge=0, le=500)
    overtime_eligible: Optional[List[Annotated[str, Field(max_length=120)]]] = Field(default=None, max_length=500)  # curated list of names allowed in the overtime module
    notifications: Optional[Dict[str, bool]] = Field(default=None, max_length=20)
    commission_rates: Optional[List[float]] = Field(default=None, max_length=100)  # available commission rates for future sales
    dashboard_widgets: Optional[Dict[str, bool]] = Field(default=None, max_length=20)
    sale_status_order: Optional[List[Annotated[str, Field(max_length=40)]]] = Field(default=None, max_length=100)  # per-company display order for sale statuses
    # iter27 — commission configuration (evolutive rules)
    commission_ca_threshold: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    commission_ca_rate_before: Optional[float] = Field(default=None, ge=0, le=1)
    commission_ca_rate_after: Optional[float] = Field(default=None, ge=0, le=1)
    commission_discount_tiers: Optional[List[CommissionDiscountTierIn]] = Field(default=None, max_length=100)
    # iter28 — bonuses dashboard visibility toggle
    show_bonuses_on_dashboard: Optional[bool] = None
    prospect_smic_threshold: Optional[int] = Field(default=None, ge=1, le=100)
    prospect_smic_amount: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    prospect_mgr_goal_sales: Optional[int] = Field(default=None, ge=1, le=1000)
    prospect_mgr_rate_below: Optional[float] = Field(default=None, ge=0, le=100)
    prospect_mgr_rate_above: Optional[float] = Field(default=None, ge=0, le=100)
    prospect_mgr_base_amount: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    prospect_mgr_bonuses: Optional[List[ProspectManagerBonusIn]] = Field(default=None, max_length=100)

    @field_validator("notifications")
    @classmethod
    def validate_notification_keys(cls, value: Optional[Dict[str, bool]]) -> Optional[Dict[str, bool]]:
        allowed = {"new_sales", "objectives", "planning", "overtime", "project_alerts", "events", "chantier_started", "chantier_confirmed", "chantier_terminated"}
        if value is not None and not set(value).issubset(allowed):
            raise ValueError("Catégorie de notification inconnue")
        return value

    @field_validator("dashboard_widgets")
    @classmethod
    def validate_dashboard_widget_keys(cls, value: Optional[Dict[str, bool]]) -> Optional[Dict[str, bool]]:
        allowed = {"ca_hero", "stats", "alerts", "commissions", "overtime", "events", "ranking", "recent_sales"}
        if value is not None and not set(value).issubset(allowed):
            raise ValueError("Widget de tableau de bord inconnu")
        return value

DEFAULT_COMMISSION_RATES = [0, 0.10, 0.13, 0.15, 0.20, 0.25, 0.30]


# ---------------- Bonuses / Primes (iter28) ----------------
# Fully optional bonus system. Multiple bonuses per company, each with its own
# CA threshold, amount, active flag and list of concerned commerciaux (["*"] = all).

class BonusIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    ca_threshold: float = Field(ge=0, le=10_000_000)
    amount: float = Field(ge=0, le=1_000_000)
    period: Optional[Literal["month", "quarter", "year", "all"]] = "month"
    commerciaux: List[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=500)  # empty or ["*"] = all
    active: Optional[bool] = True
    notify_near: Optional[bool] = False
    notify_reached: Optional[bool] = False
    near_threshold_pct: Optional[float] = Field(default=90.0, ge=0, le=100)

class BonusUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    ca_threshold: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    amount: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    period: Optional[Literal["month", "quarter", "year", "all"]] = None
    commerciaux: Optional[List[Annotated[str, Field(max_length=120)]]] = Field(default=None, max_length=500)
    active: Optional[bool] = None
    notify_near: Optional[bool] = None
    notify_reached: Optional[bool] = None
    near_threshold_pct: Optional[float] = Field(default=None, ge=0, le=100)


def _period_range(period: str):
    """Return (start_iso, end_iso) date bounds for a bonus period. `all` returns None,None."""
    today = date.today()
    if period == "month":
        start = today.replace(day=1)
        end = today
    elif period == "quarter":
        qm = ((today.month - 1) // 3) * 3 + 1
        start = today.replace(month=qm, day=1)
        end = today
    elif period == "year":
        start = today.replace(month=1, day=1)
        end = today
    else:
        return None, None
    return start.isoformat(), end.isoformat()


def _period_key(period: str) -> str:
    """iter93 : clé unique pour idempotence bonus_awards."""
    today = date.today()
    if period == "month":
        return today.strftime("%Y-%m")
    if period == "quarter":
        return f"{today.year}-Q{((today.month - 1) // 3) + 1}"
    if period == "year":
        return f"{today.year}"
    return "all"


async def _check_and_award_bonuses(user: dict, commercial_names):
    """iter93 : vérifie si une prime est nouvellement franchie pour un ou plusieurs commerciaux
    et notifie chacun via bonus_awards (idempotent par bonus × commercial × période)."""
    names = [n for n in (commercial_names or []) if n]
    if not names:
        return
    company = company_id_of(user)
    bonuses = await db.bonuses.find(cq(user, {"active": True}), {"_id": 0}).to_list(500)
    for b in bonuses:
        cs = b.get("commerciaux") or []
        included_all = "*" in cs or not cs
        period = b.get("period") or "month"
        pkey = _period_key(period)
        threshold = float(b.get("ca_threshold") or 0)
        amount = float(b.get("amount") or 0)
        for name in names:
            if not included_all and name not in cs:
                continue
            key_q = {"company_id": company, "bonus_id": b["id"], "commercial": name, "period_key": pkey}
            existing = await db.bonus_awards.find_one(key_q, {"_id": 0})
            if existing:
                continue
            ca = await _ca_for_commercial(user, name, period)
            if ca >= threshold and threshold > 0:
                await db.bonus_awards.insert_one({
                    **key_q, "id": str(uuid.uuid4()),
                    "bonus_name": b.get("name", ""),
                    "ca_reached": round(ca, 2),
                    "amount": amount,
                    "reached_at": now_iso(),
                })
                if b.get("notify_reached", True):
                    u = await db.users.find_one(cq(user, {"role": "commercial", "name": name}), {"_id": 0, "id": 1})
                    if u and u.get("id"):
                        await emit_notification_to_users(
                            company, [u["id"]],
                            title=f"Palier atteint : {b.get('name', 'Prime')}",
                            message=f"Bravo ! Vous avez franchi {int(threshold)} € de CA — Prime de {int(amount)} € débloquée.",
                            link_url="/commissions", category="events",
                        )


async def _ca_for_commercial(user: dict, name: str, period: str) -> float:
    """Sum CA (including 50% share for DE) for `name` over the given period, excluding cancel/litige.
    iter98 : matche par commercial_user_id (autorité) OU nom normalisé (insensible casse/accent),
    sur les 2 slots commercial et commercial_2. Résout `name` en uid en début d'exécution."""
    resolved_uid = await _resolve_commercial_user_id(user, name)
    key = _norm_name(name)
    q = cq(user)
    start, end = _period_range(period)
    if start and end:
        q["sale_date"] = {"$gte": start, "$lte": end}
    q["status"] = {"$nin": ["annule", "litige"]}
    or_clauses: List[dict] = []
    if resolved_uid:
        or_clauses.append({"commercial_user_id": resolved_uid})
        or_clauses.append({"commercial_2_user_id": resolved_uid})
    # regex fallback
    import re as _re
    if name:
        pat = _re.compile(rf"^\s*{_re.escape(name.strip())}\s*$", _re.IGNORECASE)
        or_clauses.append({"commercial": {"$regex": pat}})
        or_clauses.append({"commercial_2": {"$regex": pat}})
    if not or_clauses:
        return 0.0
    q["$or"] = or_clauses
    total = 0.0
    async for s in db.sales.find(q, {"_id": 0, "amount": 1, "commercial": 1, "commercial_2": 1, "commercial_user_id": 1, "commercial_2_user_id": 1, "is_de": 1}):
        amt = float(s.get("amount") or 0)
        is_de = bool(s.get("is_de")) and bool((s.get("commercial_2") or "").strip())
        mine_slot1 = (resolved_uid and s.get("commercial_user_id") == resolved_uid) or (_norm_name(s.get("commercial") or "") == key)
        mine_slot2 = (resolved_uid and s.get("commercial_2_user_id") == resolved_uid) or (_norm_name(s.get("commercial_2") or "") == key)
        if is_de and (mine_slot1 or mine_slot2):
            total += amt * 0.5 * ((1 if mine_slot1 else 0) + (1 if mine_slot2 else 0))
        elif mine_slot1:
            total += amt
    return total


@api_router.get("/bonuses")
async def list_bonuses(user: dict = Depends(get_current_user)):
    if user.get("role") not in ("commercial", "admin", "responsable", "comptable"):
        return []
    if user.get("role") == "commercial":
        # commercial can only see bonuses that apply to them (progress endpoint filters too)
        rows = await db.bonuses.find(cq(user), {"_id": 0}).sort("ca_threshold", 1).to_list(500)
        me = user.get("name") or ""
        return [b for b in rows if b.get("active") and (not b.get("commerciaux") or "*" in b["commerciaux"] or me in b["commerciaux"])]
    return await db.bonuses.find(cq(user), {"_id": 0}).sort("ca_threshold", 1).to_list(500)


@api_router.post("/bonuses")
async def create_bonus(data: BonusIn, user: dict = Depends(get_current_user)):
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    doc = with_company({
        "id": str(uuid.uuid4()),
        "name": data.name.strip(),
        "ca_threshold": float(data.ca_threshold),
        "amount": float(data.amount),
        "period": data.period or "month",
        "commerciaux": list(data.commerciaux or []),
        "active": bool(data.active if data.active is not None else True),
        "notify_near": bool(data.notify_near or False),
        "notify_reached": bool(data.notify_reached or False),
        "near_threshold_pct": float(data.near_threshold_pct if data.near_threshold_pct is not None else 90.0),
        "created_by": user["id"],
        "created_at": now_iso(),
    }, user)
    await db.bonuses.insert_one(doc.copy())
    await log_audit(user, "create", "bonus", doc["id"], after=doc)
    return doc


@api_router.put("/bonuses/{bid}")
async def update_bonus(bid: str, data: BonusUpdate, user: dict = Depends(get_current_user)):
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Aucun champ")
    before = await db.bonuses.find_one(cq(user, {"id": bid}), {"_id": 0})
    r = await db.bonuses.update_one(cq(user, {"id": bid}), {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Prime introuvable")
    after = await db.bonuses.find_one(cq(user, {"id": bid}), {"_id": 0})
    await log_audit(user, "update", "bonus", bid, before=before, after=after)
    return after


@api_router.delete("/bonuses/{bid}")
async def delete_bonus(bid: str, user: dict = Depends(get_current_user)):
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    before = await db.bonuses.find_one(cq(user, {"id": bid}), {"_id": 0})
    r = await db.bonuses.delete_one(cq(user, {"id": bid}))
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Prime introuvable")
    # Awards (history) preserved on purpose — never deleted.
    await log_audit(user, "delete", "bonus", bid, before=before)
    return {"ok": True}


@api_router.get("/bonuses/progress")
async def bonuses_progress(user: dict = Depends(get_current_user)):
    """Return {bonus_id, commercial, ca_current, ca_threshold, amount, progress_pct, reached, near, remaining}
    entries. For a commercial user, only their own rows are returned."""
    bonuses = await db.bonuses.find(cq(user, {"active": True}), {"_id": 0}).to_list(500)
    # Collect all commerciaux referenced (either explicitly, or via "*" -> use team_members)
    all_commerciaux = set()
    for b in bonuses:
        cs = b.get("commerciaux") or []
        if "*" in cs or not cs:
            team = await db.team_members.find(cq(user, {"type": "commercial"}), {"_id": 0, "name": 1}).to_list(500)
            all_commerciaux.update(t["name"] for t in team if t.get("name"))
        else:
            all_commerciaux.update(cs)
    # Restrict for commercial role
    if user.get("role") == "commercial":
        me = user.get("name") or ""
        all_commerciaux = {me} if me in all_commerciaux else set()
    out = []
    # Cache CA per (name, period) to avoid duplicate queries
    ca_cache: dict = {}
    for b in bonuses:
        cs = b.get("commerciaux") or []
        included_all = "*" in cs or not cs
        threshold = float(b.get("ca_threshold") or 0)
        amount = float(b.get("amount") or 0)
        period = b.get("period") or "month"
        near_pct = float(b.get("near_threshold_pct") or 90.0)
        for name in all_commerciaux:
            if not included_all and name not in cs:
                continue
            key = (name, period)
            if key not in ca_cache:
                ca_cache[key] = await _ca_for_commercial(user, name, period)
            ca = ca_cache[key]
            progress = (ca / threshold * 100.0) if threshold > 0 else 100.0
            reached = ca >= threshold
            remaining = max(0.0, threshold - ca)
            out.append({
                "bonus_id": b["id"], "bonus_name": b.get("name", ""),
                "commercial": name, "period": period,
                "ca_threshold": threshold, "amount": amount,
                "ca_current": round(ca, 2), "remaining": round(remaining, 2),
                "progress_pct": round(min(progress, 999.9), 1),
                "reached": reached, "near": (not reached) and progress >= near_pct,
            })
    return out


@api_router.get("/bonuses/awards")
async def list_bonus_awards(user: dict = Depends(get_current_user)):
    """History of bonuses reached. Techniciens/commerciaux only see their own.
    iter98 : match par commercial_user_id + fallback nom normalisé pour être robuste
    aux différences d'accent/casse."""
    q = cq(user)
    if user.get("role") == "commercial":
        import re as _re
        me = (user.get("name") or "").strip()
        uid = user.get("id") or "__none__"
        ors: List[dict] = [{"commercial_user_id": uid}]
        if me:
            pat = _re.compile(rf"^\s*{_re.escape(me)}\s*$", _re.IGNORECASE)
            ors.append({"commercial": {"$regex": pat}})
        q["$or"] = ors
    return await db.bonus_awards.find(q, {"_id": 0}).sort("reached_at", -1).to_list(500)


# ---------------- Technician chantier bonuses (iter29) ----------------
# One-off financial bonus attached to (project, technician). Independent of overtime hours.
# Storage: `project_bonuses` = {id, company_id, project_id, technician_name, technician_name_lc,
#                               amount, note, project_date, created_by, created_at, updated_at}
# The project_date field is a snapshot used by monthly aggregations even after the project is
# deleted (history preservation).

class ProjectBonusIn(BaseModel):
    technician_name: str = Field(min_length=1, max_length=120)
    amount: float = Field(ge=0, le=100000)
    note: Optional[str] = Field(default="", max_length=500)

class ProjectBonusUpdate(BaseModel):
    amount: Optional[float] = Field(default=None, ge=0, le=100000)
    note: Optional[str] = Field(default=None, max_length=500)


def _project_date_snapshot(proj: dict) -> str:
    return (proj.get("scheduled_date") or proj.get("sale_date") or now_iso())[:10]


@api_router.get("/projects/{pid}/bonuses")
async def list_project_bonuses(pid: str, user: dict = Depends(get_current_user)):
    proj = await db.projects.find_one(cq(user, {"id": pid}), {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    await _ensure_project_scope(user, proj)
    q = cq(user, {"project_id": pid})
    if user.get("role") in ("technicien", "sous_traitant"):
        q["technician_name_lc"] = _norm_name(user.get("name") or "")
    return await db.project_bonuses.find(q, {"_id": 0}).sort("technician_name_lc", 1).to_list(200)


@api_router.post("/projects/{pid}/bonuses")
async def create_project_bonus(pid: str, data: ProjectBonusIn, user: dict = Depends(get_current_user)):
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    proj = await db.projects.find_one(cq(user, {"id": pid}), {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    await _ensure_project_scope(user, proj)
    assigned = proj.get("assigned_to") or []
    if isinstance(assigned, str):
        assigned = [assigned]
    if _norm_name(data.technician_name) not in {_norm_name(x) for x in assigned if isinstance(x, str)}:
        raise HTTPException(status_code=400, detail="Ce technicien n'est pas assigné au chantier")
    # Idempotent per (project, technician) — one bonus row per pair. Update if exists.
    tname_lc = _norm_name(data.technician_name)
    existing = await db.project_bonuses.find_one(cq(user, {"project_id": pid, "technician_name_lc": tname_lc}), {"_id": 0})
    now = now_iso()
    if existing:
        await db.project_bonuses.update_one(
            cq(user, {"id": existing["id"]}),
            {"$set": {"amount": float(data.amount), "note": data.note or "",
                      "project_date": _project_date_snapshot(proj), "updated_at": now, "updated_by": user["id"]}},
        )
        return await db.project_bonuses.find_one(cq(user, {"id": existing["id"]}), {"_id": 0})
    doc = with_company({
        "id": str(uuid.uuid4()),
        "project_id": pid,
        "project_name": proj.get("client_name") or "",
        "technician_name": data.technician_name.strip(),
        "technician_name_lc": tname_lc,
        "amount": float(data.amount),
        "note": (data.note or "").strip(),
        "project_date": _project_date_snapshot(proj),
        "created_by": user["id"],
        "created_at": now,
        "updated_at": now,
    }, user)
    await db.project_bonuses.insert_one(doc.copy())
    return doc


@api_router.put("/project-bonuses/{bid}")
async def update_project_bonus(bid: str, data: ProjectBonusUpdate, user: dict = Depends(get_current_user)):
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Aucun champ")
    updates["updated_at"] = now_iso()
    r = await db.project_bonuses.update_one(cq(user, {"id": bid}), {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Bonus introuvable")
    return await db.project_bonuses.find_one(cq(user, {"id": bid}), {"_id": 0})


@api_router.delete("/project-bonuses/{bid}")
async def delete_project_bonus(bid: str, user: dict = Depends(get_current_user)):
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    r = await db.project_bonuses.delete_one(cq(user, {"id": bid}))
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Bonus introuvable")
    return {"ok": True}


@api_router.get("/project-bonuses/monthly")
async def project_bonuses_monthly(month: str = Query(default="", pattern=r"^(|\d{4}-\d{2})$"), user: dict = Depends(get_current_user)):
    """Aggregate bonuses per technician for one YYYY-MM. Techniciens only see their own row.
    Response: [{technician_name, month, total_amount, items:[{project_id, project_name, amount, note, date}]}].
    """
    if not month:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
    month = _validated_month(month)
    prefix = month + "-"
    q = cq(user, {"project_date": {"$regex": f"^{prefix}"}})
    if user.get("role") in ("technicien", "sous_traitant"):
        q["technician_name_lc"] = _norm_name(user.get("name") or "")
    rows = await db.project_bonuses.find(q, {"_id": 0}).sort("project_date", 1).to_list(2000)
    by_tech: dict = {}
    for r in rows:
        k = r.get("technician_name_lc") or ""
        if k not in by_tech:
            by_tech[k] = {
                "technician_name": r.get("technician_name") or "",
                "month": month,
                "total_amount": 0.0,
                "items": [],
            }
        by_tech[k]["total_amount"] += float(r.get("amount") or 0)
        by_tech[k]["items"].append({
            "bonus_id": r.get("id"),
            "project_id": r.get("project_id") or "",
            "project_name": r.get("project_name") or "",
            "amount": float(r.get("amount") or 0),
            "note": r.get("note") or "",
            "date": r.get("project_date") or "",
        })
    out = list(by_tech.values())
    out.sort(key=lambda x: x["technician_name"].lower())
    for x in out:
        x["total_amount"] = round(x["total_amount"], 2)
    return out



@api_router.get("/settings")
async def get_settings(user: dict = Depends(get_current_user)):
    cid = company_id_of(user)
    s = await db.settings.find_one({"company_id": cid, "kind": "global"}, {"_id": 0})
    if not s:
        s = {"id": f"global-{cid}", "kind": "global", "company_id": cid, "objectif_ca": 100000.0}
        await db.settings.insert_one(s.copy())
    prefs = s.get("notifications") or {}
    rates = s.get("commission_rates") or DEFAULT_COMMISSION_RATES
    overtime_eligible = s.get("overtime_eligible")
    widgets = s.get("dashboard_widgets") or {}
    default_widgets = {
        "ca_hero": True, "stats": True, "alerts": True, "commissions": True,
        "overtime": True, "events": True, "ranking": True, "recent_sales": True,
    }
    can_view_commission_config = (user or {}).get("role") in ("admin", "responsable", "comptable")
    # iter64 : les commerciaux ne doivent PAS voir les taux disponibles / seuils / paliers
    # de la société. Seul le taux appliqué à LEUR vente est visible via list_commissions.
    _all_rates = sorted({round(float(r), 4) for r in rates if 0 <= float(r) <= 1})
    return {
        "objectif_ca": s.get("objectif_ca", 100000.0),
        "objectif_ca_year": s.get("objectif_ca_year"),  # iter132 : null si non défini → frontend fallback ×12
        "theme_primary": s.get("theme_primary", "#0f172a"),
        "theme_accent": s.get("theme_accent", "#6366f1"),
        "font_family": s.get("font_family", "Inter"),
        "logo": s.get("logo", ""),
        "app_name": s.get("app_name", "KEYLOT"),
        "overtime_alert_threshold": s.get("overtime_alert_threshold", 30.0),
        "overtime_eligible": list(overtime_eligible) if isinstance(overtime_eligible, list) else None,
        "notifications": {k: bool(prefs.get(k, False)) for k in NOTIFICATION_CATEGORIES},
        "commission_rates": _all_rates if can_view_commission_config else [],
        "dashboard_widgets": {k: bool(widgets.get(k, default_widgets[k])) for k in default_widgets},
        "sale_status_order": list(s.get("sale_status_order")) if isinstance(s.get("sale_status_order"), list) else None,
        # iter27 — commission config exposed to the UI (masqué aux commerciaux depuis iter64)
        "commission_ca_threshold": float(s.get("commission_ca_threshold") if s.get("commission_ca_threshold") is not None else DEFAULT_COMMISSION_CA_THRESHOLD) if can_view_commission_config else 0,
        "commission_ca_rate_before": float(s.get("commission_ca_rate_before") if s.get("commission_ca_rate_before") is not None else DEFAULT_COMMISSION_CA_RATE_BEFORE) if can_view_commission_config else 0,
        "commission_ca_rate_after": float(s.get("commission_ca_rate_after") if s.get("commission_ca_rate_after") is not None else DEFAULT_COMMISSION_CA_RATE_AFTER) if can_view_commission_config else 0,
        "commission_discount_tiers": (list(s.get("commission_discount_tiers")) if isinstance(s.get("commission_discount_tiers"), list) else DEFAULT_COMMISSION_DISCOUNT_TIERS) if can_view_commission_config else [],
        "show_bonuses_on_dashboard": bool(s.get("show_bonuses_on_dashboard") or False),
        "prospect_smic_threshold": int(s.get("prospect_smic_threshold") or 3),
        "prospect_smic_amount": float(s.get("prospect_smic_amount") if s.get("prospect_smic_amount") is not None else 1867.0),
        "prospect_mgr_goal_sales": int(s.get("prospect_mgr_goal_sales") or 12),
        "prospect_mgr_rate_below": float(s.get("prospect_mgr_rate_below") if s.get("prospect_mgr_rate_below") is not None else 1.0),
        "prospect_mgr_rate_above": float(s.get("prospect_mgr_rate_above") if s.get("prospect_mgr_rate_above") is not None else 2.0),
        "prospect_mgr_base_amount": float(s.get("prospect_mgr_base_amount") if s.get("prospect_mgr_base_amount") is not None else 2329.97),
        "prospect_mgr_bonuses": s.get("prospect_mgr_bonuses") or [],
    }

@api_router.put("/settings")
async def update_settings(data: SettingsIn, user: dict = Depends(get_current_user)):
    check_perm(user, "settings", "modify")
    cid = company_id_of(user)
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Aucun champ")
    if updates.get("logo"):
        updates["logo"] = _validated_photo_source(updates["logo"])
    updates["kind"] = "global"
    updates["company_id"] = cid
    before = await db.settings.find_one({"company_id": cid, "kind": "global"}, {"_id": 0})
    await db.settings.update_one({"company_id": cid, "kind": "global"}, {"$set": updates}, upsert=True)
    after = await get_settings(user)
    await log_audit(user, "update", "settings", cid, before=before, after=after)
    return after


# ---------------- Users (admin) ----------------

class UserCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=72)
    name: str = Field(min_length=1, max_length=120)
    role: Literal["admin", "commercial", "technicien", "comptable", "responsable", "sous_traitant", "prospecteur", "responsable_prospecteur"] = "commercial"

class UserUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    role: Optional[Literal["admin", "commercial", "technicien", "comptable", "responsable", "sous_traitant", "prospecteur", "responsable_prospecteur"]] = None
    password: Optional[str] = Field(default=None, min_length=12, max_length=72)
    is_active: Optional[bool] = None

@api_router.get("/users")
async def list_users(user: dict = Depends(require_admin)):
    users = await db.users.find(cq(user), {"_id": 0, "password_hash": 0}).to_list(1000)  # nosec B105
    for u in users:
        if not u.get("permissions"):
            u["permissions"] = get_default_permissions(u.get("role", ""))
    return users

@api_router.post("/users")
async def create_user(data: UserCreateIn, user: dict = Depends(require_admin)):
    # Enforce plan user limit (per company)
    admin = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0}) or {}  # nosec B105
    plan = admin.get("subscription_plan")
    limit = PLAN_USER_LIMITS.get(plan) if plan else None
    if limit is not None:
        current = await db.users.count_documents(cq(user))
        if current >= limit:
            raise HTTPException(status_code=402, detail=f"Limite du plan atteinte ({current}/{limit} utilisateurs). Passez à un forfait supérieur pour ajouter plus d'utilisateurs.")
    if data.role not in ("admin", "commercial", "technicien", "comptable", "responsable", "sous_traitant", "prospecteur", "responsable_prospecteur"):
        raise HTTPException(status_code=400, detail="Rôle invalide")
    email = data.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
    uid = str(uuid.uuid4())
    doc = with_company({
        "id": uid, "email": email, "name": data.name,
        "password_hash": hash_password(data.password),
        "role": data.role,
        "is_active": True,
        "permissions": get_default_permissions(data.role),
        "created_at": now_iso(),
    }, user)
    await db.users.insert_one(doc)
    # iter176 : journalise la création utilisateur (RGPD/audit B2B).
    await log_audit(user, "create", "user", doc["id"], after={"email": doc.get("email"), "name": doc.get("name"), "role": doc.get("role")})
    # iter102 : synchro automatique de team_members selon le rôle (source unique = users.role)
    try:
        await _sync_user_team_membership(user, doc)
    except Exception as _e:
        logger.warning(f"team sync after create_user failed: {_e}")
    # iter100 : rattachement AUTOMATIQUE des ventes historiques dont le nom correspond à ce nouveau user (commercial/responsable/admin)
    if data.role in ("commercial", "responsable", "admin"):
        try:
            await _reconcile_sales_commercials(company_id_of(user))
        except Exception as _e:
            logger.warning(f"auto-reconcile after create_user failed: {_e}")
    return public_user(doc)

@api_router.put("/users/{uid}")
async def update_user(uid: str, data: UserUpdateIn, user: dict = Depends(require_admin)):
    before = await db.users.find_one(cq(user, {"id": uid}), {"_id": 0, "password_hash": 0})  # nosec B105
    if not before:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    updates = {}
    if data.name is not None:
        updates["name"] = data.name
    if data.role is not None:
        if data.role not in ("admin", "commercial", "technicien", "comptable", "responsable", "sous_traitant", "prospecteur", "responsable_prospecteur"):
            raise HTTPException(status_code=400, detail="Rôle invalide")
        updates["role"] = data.role
        # Reset permissions to role defaults when role changes (admin can then customize)
        updates["permissions"] = get_default_permissions(data.role)
    if data.password:
        updates["password_hash"] = hash_password(data.password)
        updates["token_epoch_ms"] = int(datetime.now(timezone.utc).timestamp() * 1000) + 1
    if data.is_active is not None:
        if uid == user["id"] and not data.is_active:
            raise HTTPException(status_code=400, detail="Vous ne pouvez pas désactiver votre propre compte")
        updates["is_active"] = data.is_active
        # Any activation state change revokes all existing sessions.
        updates["token_epoch_ms"] = int(datetime.now(timezone.utc).timestamp() * 1000) + 1
    if not updates:
        raise HTTPException(status_code=400, detail="Aucun champ à mettre à jour")
    r = await db.users.update_one(cq(user, {"id": uid}), {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    u = await db.users.find_one(cq(user, {"id": uid}), {"_id": 0, "password_hash": 0})  # nosec B105
    # iter102 : synchro team_members à chaque changement de rôle/nom (dédoublonne + résidu ancien type supprimé)
    if ("name" in updates) or ("role" in updates):
        try:
            await _sync_user_team_membership(user, u)
        except Exception as _e:
            logger.warning(f"team sync after update_user failed: {_e}")
    # iter100 : rattachement AUTOMATIQUE quand le nom OU le rôle change vers commercial/responsable/admin
    if ("name" in updates) or (updates.get("role") in ("commercial", "responsable", "admin")):
        try:
            await _reconcile_sales_commercials(company_id_of(user))
        except Exception as _e:
            logger.warning(f"auto-reconcile after update_user failed: {_e}")
    await log_audit(
        user, "update", "user", uid, before=before, after=u,
        extra={"password_changed": bool(data.password)},
    )
    return public_user(u)

@api_router.delete("/users/{uid}")
async def delete_user(uid: str, user: dict = Depends(require_admin)):
    if uid == user["id"]:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte")
    before = await db.users.find_one(cq(user, {"id": uid}), {"_id": 0, "password_hash": 0})  # nosec B105
    r = await db.users.delete_one(cq(user, {"id": uid}))
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    # iter102 : supprime aussi les entrées team_members liées (aucun résidu)
    if before:
        try:
            await _sync_user_team_membership(user, {**before, "role": None})
        except Exception as _e:
            logger.warning(f"team sync after delete_user failed: {_e}")
    await log_audit(user, "delete", "user", uid, before=before)
    return {"ok": True}


class UserPermissionsIn(BaseModel):
    permissions: dict = Field(max_length=50)

    @field_validator("permissions")
    @classmethod
    def validate_permissions_shape(cls, permissions: dict) -> dict:
        schema = DEFAULT_PERMISSIONS["admin"]
        for resource, actions in permissions.items():
            if resource not in schema or not isinstance(actions, dict):
                raise ValueError(f"Ressource de permission invalide : {resource}")
            if len(actions) > len(schema[resource]):
                raise ValueError(f"Trop d'actions pour la ressource : {resource}")
            for action, value in actions.items():
                if action not in schema[resource]:
                    raise ValueError(f"Action de permission invalide : {resource}.{action}")
                expected = schema[resource][action]
                if isinstance(expected, str):
                    if value not in ("none", "own", "all"):
                        raise ValueError(f"Portée invalide : {resource}.{action}")
                elif not isinstance(value, bool):
                    raise ValueError(f"Valeur booléenne requise : {resource}.{action}")
        return permissions


@api_router.get("/users/{uid}/permissions")
async def get_user_permissions(uid: str, user: dict = Depends(require_admin)):
    u = await db.users.find_one(cq(user, {"id": uid}), {"_id": 0, "password_hash": 0})  # nosec B105
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return {"id": u["id"], "role": u.get("role"), "permissions": u.get("permissions") or get_default_permissions(u.get("role", ""))}


@api_router.put("/users/{uid}/permissions")
async def update_user_permissions(uid: str, data: UserPermissionsIn, user: dict = Depends(require_admin)):
    if not isinstance(data.permissions, dict):
        raise HTTPException(status_code=400, detail="permissions doit être un objet")
    before = await db.users.find_one(cq(user, {"id": uid}), {"_id": 0, "permissions": 1})
    r = await db.users.update_one(cq(user, {"id": uid}), {"$set": {"permissions": data.permissions}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    u = await db.users.find_one(cq(user, {"id": uid}), {"_id": 0, "password_hash": 0})  # nosec B105
    await log_audit(user, "update", "permissions", uid, before=(before or {}).get("permissions"), after=data.permissions)
    return {"id": u["id"], "role": u.get("role"), "permissions": u.get("permissions")}


@api_router.get("/roles/defaults")
async def get_role_defaults(user: dict = Depends(require_admin)):
    return DEFAULT_PERMISSIONS


# ---------------- Export ----------------

def _csv_safe_cell(value: Any) -> Any:
    """Neutralize spreadsheet formulas while preserving ordinary CSV values."""
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _csv_line(values: List[Any]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, delimiter=";").writerow([_csv_safe_cell(v) for v in values])
    return buffer.getvalue()

@api_router.get("/export/sales.csv")
async def export_sales(user: dict = Depends(get_current_user)):
    # iter155b : export CSV réservé aux admins/super_admins uniquement.
    if user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Réservé à l'administrateur")
    q = cq(user)
    if perm_scope(user, "sales", "view") == "own":
        # iter98 : filtre canonique
        q.update(_own_sales_filter(user))
    async def generate_sales_csv():
        yield _csv_line(["Date", "BDC", "Nom / Prénom", "Téléphone", "Adresse", "Code postal", "Ville", "Produits", "Montant HT", "Règlement", "Fois", "Commission %", "Commission €", "Commercial", "Statut", "Date intervention souhaitée", "Notes"])
        async for s in db.sales.find(q, {"_id": 0}).sort("sale_date", -1):
            c = await db.clients.find_one(cq(user, {"id": s.get("client_id")}), {"_id": 0}) or {}
            rate = float(s.get("commission_rate") if s.get("commission_rate") is not None else 0.10)
            yield _csv_line([s.get("sale_date",""), s.get("bdc",""), c.get("name",""), c.get("phone",""), c.get("address",""), c.get("postal_code",""), c.get("city",""), s.get("service",""), s.get("amount",0), s.get("payment_method",""), s.get("payment_installments",1), f"{int(rate*100)}%", round(float(s.get("amount",0))*rate,2), s.get("commercial",""), s.get("status",""), s.get("desired_intervention_date",""), s.get("notes","")])
    return StreamingResponse(generate_sales_csv(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=ventes.csv"})

@api_router.get("/export/projects.csv")
async def export_projects(user: dict = Depends(get_current_user)):
    # iter155b : export CSV réservé aux admins/super_admins uniquement.
    if user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Réservé à l'administrateur")
    q = cq(user)
    if perm_scope(user, "projects", "view") == "own" and user.get("role") != "technicien":
        client_ids = await _commercial_client_ids(user)
        sale_ids = await _own_sale_ids(user)
        q["$or"] = [
            {"client_id": {"$in": client_ids}},
            {"sale_id": {"$in": sale_ids}},
        ]
    elif user.get("role") in ("technicien", "sous_traitant"):
        name = user.get("name") or ""
        q["assigned_to"] = {"$regex": f"^{re.escape(name)}$", "$options": "i"} if name else "__none__"
    async def generate_projects_csv():
        yield _csv_line(["Client", "Téléphone", "Adresse", "Prestation", "Statut", "Date planifiée", "Assigné à", "Priorité", "Durée (jours)", "Notes"])
        async for p in db.projects.find(q, {"_id": 0}):
            c = await db.clients.find_one(cq(user, {"id": p.get("client_id")}), {"_id": 0}) or {}
            assigned = p.get("assigned_to", "")
            if isinstance(assigned, list):
                assigned = ", ".join(assigned)
            yield _csv_line([c.get("name",""), c.get("phone",""), c.get("address",""), p.get("service",""), p.get("status",""), p.get("scheduled_date",""), assigned, p.get("priority",""), p.get("duration_days",1), p.get("notes","")])
    return StreamingResponse(generate_projects_csv(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=chantiers.csv"})


# ---------------- Email (Emergent managed proxy) ----------------

EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "KEYLOT")

_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors, self.dangerous_attrs = set(), [], [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        self.dangerous_attrs += [k for k, _ in attrs if k.lower().startswith("on")]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    forbidden_tags = {"form", "input", "textarea", "select", "script", "style", "iframe", "object", "embed", "svg", "meta", "link", "img"}
    if scan.tags & forbidden_tags:
        raise ValueError("Forbidden active, tracking or form content in email (G2)")
    if scan.dangerous_attrs:
        raise ValueError("Event-handler attributes are forbidden in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} ≠ real link host {real!r} (G3)")


async def send_email(*, to: str, subject: str, html: str) -> Optional[str]:
    subject = " ".join((subject or "").splitlines()).strip()[:200]
    _assert_safe_email(subject, html)
    if not EMAIL_KEY:
        logger.warning("EMERGENT_EMAIL_KEY missing; skipping send")
        return None
    payload = {"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME}
    try:
        async with httpx.AsyncClient(timeout=30) as client_h:
            resp = await client_h.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": EMAIL_KEY},
                json=payload,
            )
        resp.raise_for_status()
        return resp.json().get("id")
    except httpx.HTTPStatusError as e:
        logger.error(f"Email send failed: {e.response.status_code} {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Email send error: {e}")
        return None


# ---------------- Cron: Rappel J-1 des chantiers ----------------

WEBHOOK_CRON_SECRET = os.environ.get("WEBHOOK_CRON_SECRET", "")


def _paris_tomorrow_iso() -> str:
    tz = ZoneInfo("Europe/Paris")
    tomorrow = datetime.now(tz).date() + timedelta(days=1)
    return tomorrow.isoformat()


def _fmt_fr_date(iso_date: str) -> str:
    try:
        y, m, d = iso_date.split("-")
        months = ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"]
        return f"{int(d)} {months[int(m)-1]} {y}"
    except Exception:
        return iso_date


async def _build_reminder_digest(target_date: str, company_id: Optional[str] = None) -> List[dict]:
    """Return enriched list of chantiers scheduled for target_date (multi-day aware).
    A project spans [scheduled_date, scheduled_date + duration_days - 1]."""
    proj_q = {"scheduled_date": {"$ne": None, "$exists": True}, "status": {"$ne": "termine"}}
    if company_id:
        proj_q["company_id"] = company_id
    projects = await db.projects.find(proj_q, {"_id": 0}).to_list(5000)
    target = datetime.fromisoformat(target_date).date()
    items: List[dict] = []
    for p in projects:
        try:
            start = datetime.fromisoformat(p["scheduled_date"]).date()
        except Exception:
            logger.debug("Date de chantier historique invalide ignorée dans le planning")
            continue
        dur = max(1, int(p.get("duration_days") or 1))
        end = start + timedelta(days=dur - 1)
        if start <= target <= end:
            items.append(p)
    if not items:
        return []
    # Enrich with client & sale (commercial)
    client_ids = list({p["client_id"] for p in items})
    sale_ids = list({p.get("sale_id") for p in items if p.get("sale_id")})
    c_q = {"id": {"$in": client_ids}}
    s_q = {"id": {"$in": sale_ids}}
    if company_id:
        c_q["company_id"] = company_id
        s_q["company_id"] = company_id
    clients = await db.clients.find(c_q, {"_id": 0}).to_list(5000)
    cmap = {c["id"]: c for c in clients}
    sales = await db.sales.find(s_q, {"_id": 0}).to_list(5000)
    smap = {s["id"]: s for s in sales}
    enriched = []
    for p in items:
        c = cmap.get(p["client_id"], {})
        s = smap.get(p.get("sale_id"), {})
        assigned = p.get("assigned_to") or []
        if isinstance(assigned, str):
            assigned = [assigned] if assigned else []
        # flatten defensively
        flat = []
        for x in assigned:
            if isinstance(x, list):
                flat.extend([y for y in x if isinstance(y, str)])
            elif isinstance(x, str):
                flat.append(x)
        enriched.append({
            "company_id": p.get("company_id") or DEFAULT_COMPANY_ID,
            "client_name": c.get("name", "—"),
            "client_phone": c.get("phone", ""),
            "client_address": " ".join(filter(None, [c.get("address",""), c.get("postal_code",""), c.get("city","")])),
            "service": p.get("service", ""),
            "commercial": (s.get("commercial") or "").strip(),
            "technicians": flat,
            "duration_days": int(p.get("duration_days") or 1),
            "scheduled_date": p["scheduled_date"],
        })
    return enriched


def _digest_html_row(it: dict) -> str:
    techs = ", ".join(it["technicians"]) if it["technicians"] else "<em>non assigné</em>"
    dur = f"{it['duration_days']} jours" if it["duration_days"] > 1 else "1 jour"
    comm = it["commercial"]
    comm_html = f'<div>👔 {escape(comm)}</div>' if comm else ""
    return (
        f'<tr>'
        f'<td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">'
        f'<div style="font-weight:600;color:#0f172a">{escape(it["client_name"])}</div>'
        f'<div style="font-size:12px;color:#64748b">{escape(it["service"])}</div>'
        f'<div style="font-size:12px;color:#64748b">{escape(it["client_address"])}</div>'
        f'</td>'
        f'<td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:#334155;font-size:13px">'
        f'<div>👷 {techs}</div>'
        f'<div>⏱ {dur}</div>'
        f'{comm_html}'
        f'</td>'
        f'</tr>'
    )


def _wrap_digest(target_date: str, intro: str, rows_html: str) -> str:
    date_fr = _fmt_fr_date(target_date)
    return (
        f'<table role="presentation" width="100%" style="background:#f9fafb;padding:24px 0;font-family:Arial,sans-serif">'
        f'<tr><td align="center">'
        f'<table role="presentation" width="600" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.06)">'
        f'<tr><td style="background:#0f172a;color:#ffffff;padding:20px 24px">'
        f'<div style="font-size:12px;letter-spacing:2px;color:#94a3b8;text-transform:uppercase">Rappel chantier</div>'
        f'<div style="font-size:22px;font-weight:700;margin-top:4px">Chantiers de demain · {escape(date_fr)}</div>'
        f'</td></tr>'
        f'<tr><td style="padding:20px 24px;color:#334155;font-size:14px;line-height:1.5">{intro}</td></tr>'
        f'<tr><td style="padding:0 24px 20px">'
        f'<table role="presentation" width="100%" style="border-collapse:collapse;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden">'
        f'<thead><tr style="background:#f1f5f9"><th align="left" style="padding:10px 12px;font-size:11px;color:#64748b;letter-spacing:1px;text-transform:uppercase">Client</th><th align="left" style="padding:10px 12px;font-size:11px;color:#64748b;letter-spacing:1px;text-transform:uppercase">Équipe</th></tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>'
        f'</td></tr>'
        f'<tr><td style="padding:16px 24px;background:#f9fafb;color:#94a3b8;font-size:11px;text-align:center">'
        f'Envoyé par {escape(EMAIL_FROM_NAME)} · Rappel automatique 20h la veille'
        f'</td></tr>'
        f'</table></td></tr></table>'
    )


async def _run_reminders(target_date: str) -> dict:
    # Build each digest independently so even colliding legacy IDs cannot join
    # a project to a client or sale from another tenant.
    company_ids = {
        cid for cid in await db.projects.distinct("company_id")
        if isinstance(cid, str) and cid
    } or {DEFAULT_COMPANY_ID}
    items: List[dict] = []
    for company_id in company_ids:
        items.extend(await _build_reminder_digest(target_date, company_id))
    if not items:
        logger.info(f"Rappel J-1 ({target_date}) : aucun chantier")
        return {"target_date": target_date, "sent": 0, "recipients": [], "chantiers": 0}

    by_company: dict = {}
    for it in items:
        by_company.setdefault(it["company_id"], []).append(it)

    sent = 0
    recipients: List[str] = []
    failed: List[dict] = []

    for company_id, company_items in by_company.items():
        # Every lookup is tenant-scoped so equal names in two companies cannot cross.
        users = await db.users.find(
            {"company_id": company_id, "role": {"$in": ["commercial", "admin"]}},
            {"_id": 0, "password_hash": 0},  # nosec B105
        ).to_list(500)
        team_comms = await db.team_members.find(
            {"company_id": company_id, "type": "commercial"}, {"_id": 0}
        ).to_list(500)
        tmap = {(t.get("name") or "").strip().lower(): t for t in team_comms}

        def find_user_email(commercial_name: str) -> Optional[str]:
            if not commercial_name:
                return None
            needle = commercial_name.strip().lower()
            member = tmap.get(needle)
            if member and member.get("email"):
                return member["email"]
            for candidate in users:
                uname = (candidate.get("name") or "").lower()
                if uname == needle or needle in uname or uname.split(" ")[0] == needle:
                    return candidate.get("email")
            return None

        groups: dict = {}
        for item in company_items:
            groups.setdefault(item["commercial"] or "__none", []).append(item)

        for commercial, commercial_items in groups.items():
            if commercial == "__none":
                continue
            email = find_user_email(commercial)
            if not email:
                failed.append({"company_id": company_id, "commercial": commercial, "reason": "no_user_email_match"})
                continue
            rows = "".join(_digest_html_row(item) for item in commercial_items)
            intro = f"Bonjour <strong>{escape(commercial)}</strong>, voici tes chantiers de demain :"
            html = _wrap_digest(target_date, intro, rows)
            subject = f"[KEYLOT] Rappel · {len(commercial_items)} chantier{'s' if len(commercial_items)>1 else ''} demain"
            msg_id = await send_email(to=email, subject=subject, html=html)
            if msg_id:
                sent += 1
                recipients.append(email)
            else:
                failed.append({"company_id": company_id, "commercial": commercial, "email": email, "reason": "send_failed"})

        admin_emails = list(dict.fromkeys(
            (candidate.get("email") or "").lower()
            for candidate in users
            if candidate.get("role") == "admin" and candidate.get("email")
        ))
        rows = "".join(_digest_html_row(item) for item in company_items)
        intro = f"Récapitulatif de tous les chantiers programmés pour demain ({len(company_items)} au total) :"
        html = _wrap_digest(target_date, intro, rows)
        subject = f"[KEYLOT] Récap admin · {len(company_items)} chantier{'s' if len(company_items)>1 else ''} demain"
        for admin_email in admin_emails:
            msg_id = await send_email(to=admin_email, subject=subject, html=html)
            if msg_id:
                sent += 1
                recipients.append(admin_email)
            else:
                failed.append({"company_id": company_id, "commercial": "__admin__", "email": admin_email, "reason": "send_failed"})

    logger.info(f"Rappel J-1 ({target_date}) : {sent} email(s) envoyé(s), {len(items)} chantier(s), {len(failed)} échec(s)")
    return {"target_date": target_date, "sent": sent, "recipients": recipients, "chantiers": len(items), "companies": len(by_company), "failed": failed}


class CronReminderIn(BaseModel):
    event: Optional[str] = Field(default=None, max_length=120)
    schedule_id: Optional[str] = Field(default=None, max_length=200)
    run_id: Optional[str] = Field(default=None, max_length=200)
    dispatch_time: Optional[str] = Field(default=None, max_length=80)
    job_id: Optional[str] = Field(default=None, max_length=200)
    data: Optional[dict] = Field(default=None, max_length=50)


@api_router.post("/cron/rappel-chantiers-j1")
async def cron_rappel_chantiers_j1(
    body: CronReminderIn,
    background: BackgroundTasks,
    authorization: Optional[str] = Header(None),
    x_webhook_id: Optional[str] = Header(None),
):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization[7:]
    if not WEBHOOK_CRON_SECRET or not _hmac.compare_digest(token, WEBHOOK_CRON_SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized")

    run_id = x_webhook_id or body.run_id or ""
    # Idempotency: skip if we already processed this run
    if run_id:
        existing = await db.cron_runs.find_one({"run_id": run_id, "name": "rappel-chantiers-j1"})
        if existing:
            return {"accepted": True, "duplicate": True, "run_id": run_id}
        await db.cron_runs.insert_one({"run_id": run_id, "name": "rappel-chantiers-j1", "at": now_iso()})

    target = _paris_tomorrow_iso()
    background.add_task(_run_reminders_task, target)
    return {"accepted": True, "target_date": target, "run_id": run_id}


async def _run_reminders_task(target_date: str):
    try:
        await _run_reminders(target_date)
    except Exception:
        logger.exception("Rappel J-1 background task failed")


@api_router.post("/cron/rappel-chantiers-j1/test")
async def cron_rappel_test(
    user: dict = Depends(require_admin),
    target_date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
):
    """Admin-only manual trigger for testing the reminder job."""
    td = target_date or _paris_tomorrow_iso()
    date.fromisoformat(td)
    result = await _run_reminders(td)
    return result


# ---------------- Cron: Bilan mensuel automatique (1er du mois 9h Paris) ----------------

async def _run_monthly_digest_email() -> dict:
    """Compute the report for the PREVIOUS month and email it to each company's admin (multi-tenant)."""
    tz = ZoneInfo("Europe/Paris")
    today = datetime.now(tz).date()
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    prev_month = last_prev.strftime("%Y-%m")

    months_fr = ["Janvier","Février","Mars","Avril","Mai","Juin","Juillet","Août","Septembre","Octobre","Novembre","Décembre"]
    y_, m_ = prev_month.split("-")
    label = f"{months_fr[int(m_)-1]} {y_}"

    def eur(n: float) -> str:
        return f"{int(n):,} €".replace(",", " ")

    sent_total = 0
    # Iterate every admin of every company and send them their own scoped report
    admins = await db.users.find({"role": "admin"}, {"_id": 0, "id": 1, "email": 1, "company_id": 1, "name": 1, "role": 1}).to_list(2000)
    for admin in admins:
        if not admin.get("email") or not admin.get("company_id"):
            continue
        try:
            report = await _compute_monthly_report(prev_month, admin)
            tot = report["totals"]
            kpi_row = (
                f'<tr>'
                f'<td style="padding:12px;text-align:center;border-right:1px solid #e5e7eb"><div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px">Ventes actives</div><div style="font-size:22px;font-weight:700;color:#0f172a;margin-top:2px">{tot["active_count"]}</div></td>'
                f'<td style="padding:12px;text-align:center;border-right:1px solid #e5e7eb"><div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px">Annulations</div><div style="font-size:22px;font-weight:700;color:#b91c1c;margin-top:2px">{tot["cancelled_count"]}</div></td>'
                f'<td style="padding:12px;text-align:center;border-right:1px solid #e5e7eb"><div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px">CA du mois</div><div style="font-size:22px;font-weight:700;color:#0f172a;margin-top:2px">{escape(eur(tot["ca_total"]))}</div></td>'
                f'<td style="padding:12px;text-align:center"><div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px">Commissions</div><div style="font-size:22px;font-weight:700;color:#047857;margin-top:2px">{escape(eur(tot["commission_total"]))}</div></td>'
                f'</tr>'
            )
            rows_html = ""
            for r in report["rows"]:
                rows_html += (
                    f'<tr>'
                    f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;font-weight:600">{escape(r["commercial"])}</td>'
                    f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:right">{r["sales_count"]}</td>'
                    f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:right">{r["sources"]["R1"]}</td>'
                    f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:right">{r["sources"]["Assist"]}</td>'
                    f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:right">{r["sources"]["CQ"]}</td>'
                    f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:right">{r["sources"]["CA"]}</td>'
                    f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:right;color:{"#b91c1c" if r["cancelled_count"] else "#94a3b8"}">{r["cancelled_count"] or "—"}</td>'
                    f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:right;font-weight:600">{escape(eur(r["ca_total"]))}</td>'
                    f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:right;font-weight:600;color:#047857">{escape(eur(r["commission_total"]))}</td>'
                    f'</tr>'
                )
            frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
            app_link = f'<a href="{frontend_url}/rapport" style="color:#0f172a">Ouvrir dans KEYLOT</a>' if frontend_url else ""
            html = (
                f'<table role="presentation" width="100%" style="background:#f9fafb;padding:24px 0;font-family:Arial,sans-serif">'
                f'<tr><td align="center"><table role="presentation" width="720" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.06)">'
                f'<tr><td style="background:#0f172a;color:#ffffff;padding:20px 24px">'
                f'<div style="font-size:11px;letter-spacing:2px;color:#94a3b8;text-transform:uppercase">Bilan mensuel automatique</div>'
                f'<div style="font-size:22px;font-weight:700;margin-top:4px">Rapport {escape(label)}</div></td></tr>'
                f'<tr><td style="padding:16px 24px 8px;color:#334155;font-size:14px">Voici le récap du mois écoulé.</td></tr>'
                f'<tr><td style="padding:0 24px 20px"><table role="presentation" width="100%" style="border:1px solid #e5e7eb;border-radius:8px;border-collapse:separate;border-spacing:0;background:#f8fafc">{kpi_row}</table></td></tr>'
                f'<tr><td style="padding:0 24px 24px">'
                f'<table role="presentation" width="100%" style="border-collapse:collapse;border:1px solid #e5e7eb">'
                f'<thead><tr style="background:#0f172a;color:#ffffff">'
                f'<th align="left" style="padding:10px;font-size:11px;text-transform:uppercase;letter-spacing:1px">Commercial</th>'
                f'<th align="right" style="padding:10px;font-size:11px;text-transform:uppercase;letter-spacing:1px">Ventes</th>'
                f'<th align="right" style="padding:10px;font-size:11px;text-transform:uppercase;letter-spacing:1px">R1</th>'
                f'<th align="right" style="padding:10px;font-size:11px;text-transform:uppercase;letter-spacing:1px">Assist</th>'
                f'<th align="right" style="padding:10px;font-size:11px;text-transform:uppercase;letter-spacing:1px">CQ</th>'
                f'<th align="right" style="padding:10px;font-size:11px;text-transform:uppercase;letter-spacing:1px">CA</th>'
                f'<th align="right" style="padding:10px;font-size:11px;text-transform:uppercase;letter-spacing:1px">Annulé</th>'
                f'<th align="right" style="padding:10px;font-size:11px;text-transform:uppercase;letter-spacing:1px">CA €</th>'
                f'<th align="right" style="padding:10px;font-size:11px;text-transform:uppercase;letter-spacing:1px">Commission €</th>'
                f'</tr></thead><tbody>{rows_html}</tbody></table></td></tr>'
                f'<tr><td style="padding:0 24px 24px;color:#64748b;font-size:12px">{app_link} · Version PDF disponible dans l\'app.</td></tr>'
                f'<tr><td style="padding:16px 24px;background:#f9fafb;color:#94a3b8;font-size:11px;text-align:center">Envoyé par {escape(EMAIL_FROM_NAME)} · Bilan mensuel automatique le 1er du mois à 9h</td></tr>'
                f'</table></td></tr></table>'
            )
            subject = f"[KEYLOT] Bilan mensuel — {label}"
            msg_id = await send_email(to=admin["email"], subject=subject, html=html)
            if msg_id:
                sent_total += 1
        except Exception as e:
            logger.warning(f"monthly digest for {admin.get('email')} failed: {e}")
    return {"month": prev_month, "sent": sent_total, "companies": len(admins)}


@api_router.post("/cron/bilan-mensuel")
async def cron_bilan_mensuel(
    body: CronReminderIn,
    background: BackgroundTasks,
    authorization: Optional[str] = Header(None),
    x_webhook_id: Optional[str] = Header(None),
):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization[7:]
    if not WEBHOOK_CRON_SECRET or not _hmac.compare_digest(token, WEBHOOK_CRON_SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized")
    run_id = x_webhook_id or body.run_id or ""
    if run_id:
        existing = await db.cron_runs.find_one({"run_id": run_id, "name": "bilan-mensuel"})
        if existing:
            return {"accepted": True, "duplicate": True, "run_id": run_id}
        await db.cron_runs.insert_one({"run_id": run_id, "name": "bilan-mensuel", "at": now_iso()})

    async def _task():
        try:
            await _run_monthly_digest_email()
        except Exception:
            logger.exception("Bilan mensuel task failed")

    background.add_task(_task)
    return {"accepted": True, "run_id": run_id}


@api_router.post("/cron/bilan-mensuel/test")
async def cron_bilan_test(user: dict = Depends(require_admin)):
    return await _run_monthly_digest_email()


# ---------------- Stripe subscriptions ----------------

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

PLAN_USER_LIMITS = {
    # iter168 : grille tarifaire simplifiée (v2) — 100 % des fonctionnalités partout,
    # seul le nombre d'utilisateurs actifs varie. Au-delà de 15 : Entreprise + 10 €/u.
    "keylot_essentiel_monthly": 3,     # 39 € HT
    "keylot_equipe_monthly": 8,        # 69 € HT
    "keylot_entreprise_monthly": None, # 99 € HT + 10 €/u au-delà de 15
    # Rétro-compatibilité anciens plans
    "keylot_small_monthly": 3,
    "keylot_medium_monthly": 8,
    "keylot_large_monthly": None,
}

PLAN_PRICING = {
    "keylot_essentiel_monthly": {"price": 39, "label": "Essentiel", "max_users": 3},
    "keylot_equipe_monthly": {"price": 69, "label": "Équipe", "max_users": 8},
    "keylot_entreprise_monthly": {"price": 99, "label": "Entreprise", "max_users": None, "extra_price_per_user": 10, "extra_threshold": 15},
}

# Rétro-compatibilité — les anciens lookup_keys pointent vers les nouveaux labels.
_LEGACY_PLAN_MAP = {
    "keylot_small_monthly": "keylot_essentiel_monthly",
    "keylot_medium_monthly": "keylot_equipe_monthly",
    "keylot_large_monthly": "keylot_entreprise_monthly",
}


def _resolve_plan(lookup_key: Optional[str]) -> Optional[str]:
    if not lookup_key:
        return None
    return _LEGACY_PLAN_MAP.get(lookup_key, lookup_key)


def _suggested_plan(active_users: int) -> str:
    """Renvoie le lookup_key du plan correspondant à un nombre d'utilisateurs actifs (iter168)."""
    if active_users <= 3:
        return "keylot_essentiel_monthly"
    if active_users <= 8:
        return "keylot_equipe_monthly"
    return "keylot_entreprise_monthly"


def _compute_price(plan: str, active_users: int) -> dict:
    """iter168 : Entreprise = 99 € base + 10 €/u au-delà de 15 utilisateurs."""
    p = _resolve_plan(plan)
    info = PLAN_PRICING.get(p) or PLAN_PRICING["keylot_essentiel_monthly"]
    base = info["price"]
    extra_users = 0
    extra_price = 0
    if p == "keylot_entreprise_monthly":
        threshold = info.get("extra_threshold", 15)
        per_user = info.get("extra_price_per_user", 10)
        if active_users > threshold:
            extra_users = active_users - threshold
            extra_price = extra_users * per_user
    return {
        "plan": p,
        "label": info["label"],
        "base_price": base,
        "extra_users": extra_users,
        "extra_price": extra_price,
        "total_price": base + extra_price,
        "max_users": info.get("max_users"),
    }
TRIAL_DAYS = 14


class CheckoutRequest(BaseModel):
    lookup_key: str = Field(min_length=1, max_length=120)
    origin_url: str = Field(min_length=1, max_length=2048)


@api_router.post("/payments/checkout")
async def create_checkout(req: CheckoutRequest, user: dict = Depends(require_admin)):
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe non configuré")
    if req.lookup_key not in PLAN_USER_LIMITS:
        raise HTTPException(status_code=400, detail="Plan non autorisé")
    prices = stripe.Price.list(lookup_keys=[req.lookup_key], active=True, limit=1).data
    if not prices:
        raise HTTPException(status_code=400, detail=f"Plan introuvable : {req.lookup_key}")
    price = prices[0]
    return_origin = _safe_frontend_url(req.origin_url)
    # Give a 14-day trial the first time an admin subscribes (or if their last sub is not currently active/trial)
    give_trial = True
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0}) or {}
    if u.get("subscription_status") in ("active", "trialing"):
        give_trial = False
    kwargs = dict(
        line_items=[{"price": price.id, "quantity": 1}],
        mode="subscription" if price.recurring else "payment",
        success_url=f"{return_origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{return_origin}/payment/cancel",
        metadata={
            "user_id": user["id"],
            "company_id": company_id_of(user),
            "user_email": user["email"],
            "lookup_key": req.lookup_key,
        },
    )
    if price.recurring and give_trial:
        kwargs["subscription_data"] = {
            "trial_period_days": TRIAL_DAYS,
            "metadata": {"user_id": user["id"], "company_id": company_id_of(user), "lookup_key": req.lookup_key},
        }
    try:
        session = stripe.checkout.Session.create(**kwargs, managed_payments={"enabled": True})
    except stripe.error.InvalidRequestError as e:
        msg = (getattr(e, "user_message", "") or str(e)).lower()
        if "managed payments" in msg or "ineligible" in msg:
            session = stripe.checkout.Session.create(
                **kwargs, automatic_tax={"enabled": True}, billing_address_collection="required",
            )
        else:
            logger.exception("Stripe checkout rejected")
            raise HTTPException(status_code=502, detail="Paiement temporairement indisponible")

    await db.payment_transactions.insert_one({
        "session_id": session.id,
        "user_id": user["id"],
        "company_id": company_id_of(user),
        "user_email": user["email"],
        "lookup_key": req.lookup_key,
        "amount": (price.unit_amount or 0),
        "currency": price.currency,
        "status": "initiated",
        "payment_status": "pending",
        "trial_days": TRIAL_DAYS if give_trial else 0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })
    return {"checkout_url": session.url, "session_id": session.id, "trial_days": TRIAL_DAYS if give_trial else 0}


@api_router.get("/payments/status/{session_id}")
async def get_payment_status(session_id: str, user: dict = Depends(get_current_user)):
    # iter161 : durcissement — le paiement doit appartenir à l'utilisateur qui le poll.
    record = await db.payment_transactions.find_one({"session_id": session_id, "user_id": user["id"]}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Session introuvable")
    if record.get("payment_status") != "paid":
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            subscription_status = None
            if s.subscription:
                try:
                    subscription_status = stripe.Subscription.retrieve(s.subscription).status
                except stripe.error.StripeError:
                    subscription_status = None
            entitled = s.payment_status == "paid" or subscription_status in ("active", "trialing")
            if entitled:
                await db.payment_transactions.update_one(
                    {"session_id": session_id, "user_id": user["id"], "company_id": company_id_of(user)},
                    {"$set": {
                        "status": "completed", "payment_status": s.payment_status,
                        "subscription_status": subscription_status,
                        "stripe_subscription_id": s.subscription,
                        "stripe_payment_intent_id": s.payment_intent,
                        "updated_at": now_iso(),
                    }},
                )
                # Mark user as subscribed
                # The local transaction is the source of truth. Stripe metadata
                # is useful for support/debugging, but must never select a user.
                uid = record.get("user_id")
                lookup = record.get("lookup_key")
                if uid:
                    await db.users.update_one({"id": uid, "company_id": company_id_of(user)}, {"$set": {
                        "stripe_subscription_id": s.subscription,
                        "subscription_plan": lookup,
                        "subscription_status": subscription_status or "active",
                        "subscription_updated_at": now_iso(),
                    }})
                record = await db.payment_transactions.find_one(
                    {"session_id": session_id, "user_id": user["id"], "company_id": company_id_of(user)},
                    {"_id": 0},
                )
        except stripe.error.StripeError:
            pass
    return {
        "session_id": record["session_id"],
        "status": record["status"],
        "payment_status": record["payment_status"],
        "entitled": record.get("payment_status") == "paid" or record.get("subscription_status") in ("active", "trialing"),
        "lookup_key": record.get("lookup_key"),
    }


async def _set_subscription_status(subscription_id: str, status: str) -> None:
    """Update the owning user via the tenant-scoped payment transaction."""
    transaction = await db.payment_transactions.find_one(
        {"stripe_subscription_id": subscription_id},
        {"_id": 0, "user_id": 1, "company_id": 1},
    )
    if not transaction or not transaction.get("user_id"):
        logger.warning("Stripe subscription has no matching payment transaction")
        return
    user_query = {"id": transaction["user_id"]}
    if transaction.get("company_id"):
        user_query["company_id"] = transaction["company_id"]
    await db.users.update_one(user_query, {"$set": {
        "stripe_subscription_id": subscription_id,
        "subscription_status": status,
        "subscription_updated_at": now_iso(),
    }})


async def _set_payment_intent_status(payment_intent_id: str, payment_status: str, *, suspend: bool) -> None:
    """Apply a refund/dispute only to the locally recorded payment owner."""
    transaction = await db.payment_transactions.find_one(
        {"stripe_payment_intent_id": payment_intent_id},
        {"_id": 0, "session_id": 1, "user_id": 1, "company_id": 1},
    )
    if not transaction or not transaction.get("user_id") or not transaction.get("company_id"):
        logger.warning("Stripe payment intent has no matching payment transaction")
        return
    query = {
        "stripe_payment_intent_id": payment_intent_id,
        "user_id": transaction["user_id"],
        "company_id": transaction["company_id"],
    }
    await db.payment_transactions.update_one(query, {"$set": {
        "status": payment_status,
        "payment_status": payment_status,
        "updated_at": now_iso(),
    }})
    if suspend:
        await db.users.update_one(
            {"id": transaction["user_id"], "company_id": transaction["company_id"]},
            {"$set": {"subscription_status": "suspended", "subscription_updated_at": now_iso()}},
        )


async def _apply_checkout_session_state(obj: dict, *, force_payment_status: Optional[str] = None) -> None:
    """Apply a Stripe checkout only when it matches a session created by this application."""
    session_id = obj.get("id") or ""
    transaction = await db.payment_transactions.find_one(
        {"session_id": session_id},
        {"_id": 0, "user_id": 1, "company_id": 1, "lookup_key": 1, "stripe_subscription_id": 1},
    )
    if not transaction or not transaction.get("user_id") or not transaction.get("company_id"):
        raise RuntimeError("Stripe checkout has no matching local transaction")

    payment_status = force_payment_status or obj.get("payment_status") or "unpaid"
    subscription_id = obj.get("subscription") or transaction.get("stripe_subscription_id")
    subscription_status = None
    if subscription_id:
        try:
            subscription_status = stripe.Subscription.retrieve(subscription_id).status
        except stripe.error.StripeError:
            # A paid session is already sufficient. Trial/no-payment sessions
            # require the subscription status as proof and must be retried.
            if payment_status != "paid":
                raise
    entitled = payment_status == "paid" or subscription_status in ("active", "trialing")
    await db.payment_transactions.update_one(
        {"session_id": session_id, "user_id": transaction["user_id"], "company_id": transaction["company_id"]},
        {"$set": {
            "status": "completed" if entitled else "pending",
            "payment_status": payment_status,
            "subscription_status": subscription_status,
            "stripe_subscription_id": subscription_id,
            "stripe_payment_intent_id": obj.get("payment_intent"),
            "updated_at": now_iso(),
        }},
    )
    if not entitled:
        return
    await db.users.update_one(
        {"id": transaction["user_id"], "company_id": transaction["company_id"]},
        {"$set": {
            "stripe_subscription_id": subscription_id,
            "subscription_plan": transaction.get("lookup_key"),
            "subscription_status": subscription_status or "active",
            "subscription_updated_at": now_iso(),
        }},
    )


async def _process_stripe_event(event: dict) -> None:
    obj = event["data"]["object"]
    event_type = event["type"]
    if event_type == "checkout.session.completed":
        await _apply_checkout_session_state(obj)
    elif event_type == "checkout.session.async_payment_succeeded":
        await _apply_checkout_session_state(obj, force_payment_status="paid")
    elif event_type == "checkout.session.async_payment_failed":
        transaction = await db.payment_transactions.find_one(
            {"session_id": obj.get("id")}, {"_id": 0, "user_id": 1, "company_id": 1}
        )
        if not transaction or not transaction.get("user_id") or not transaction.get("company_id"):
            raise RuntimeError("Stripe checkout has no matching local transaction")
        await db.payment_transactions.update_one(
            {"session_id": obj["id"], "user_id": transaction["user_id"], "company_id": transaction["company_id"]},
            {"$set": {"status": "failed", "payment_status": "failed", "updated_at": now_iso()}},
        )
        await db.users.update_one(
            {"id": transaction["user_id"], "company_id": transaction["company_id"]},
            {"$set": {"subscription_status": "past_due", "subscription_updated_at": now_iso()}},
        )
    elif event_type in ("invoice.payment_failed", "invoice.marked_uncollectible"):
        subscription_id = (obj or {}).get("subscription")
        if subscription_id:
            await _set_subscription_status(subscription_id, "suspended")
    elif event_type == "invoice.payment_succeeded":
        subscription_id = (obj or {}).get("subscription")
        if subscription_id:
            await _set_subscription_status(subscription_id, "active")
    elif event_type == "customer.subscription.deleted":
        await _set_subscription_status(obj["id"], "suspended")
    elif event_type == "customer.subscription.updated":
        stripe_status = (obj or {}).get("status") or ""
        local_status = stripe_status if stripe_status in ("active", "trialing") else "suspended"
        if (obj or {}).get("id"):
            await _set_subscription_status(obj["id"], local_status)
    elif event_type == "checkout.session.expired":
        transaction = await db.payment_transactions.find_one(
            {"session_id": obj.get("id")}, {"_id": 0, "user_id": 1, "company_id": 1}
        )
        if transaction and transaction.get("user_id") and transaction.get("company_id"):
            await db.payment_transactions.update_one(
                {"session_id": obj.get("id"), "user_id": transaction["user_id"], "company_id": transaction["company_id"]},
                {"$set": {"status": "expired", "payment_status": "unpaid", "updated_at": now_iso()}},
            )
    elif event_type == "charge.refunded":
        payment_intent_id = (obj or {}).get("payment_intent")
        if payment_intent_id:
            # Stripe's `refunded` flag is true only when the charge is fully refunded.
            await _set_payment_intent_status(
                payment_intent_id,
                "refunded" if (obj or {}).get("refunded") else "partially_refunded",
                suspend=bool((obj or {}).get("refunded")),
            )
    elif event_type == "charge.dispute.created":
        payment_intent_id = (obj or {}).get("payment_intent")
        if payment_intent_id:
            await _set_payment_intent_status(payment_intent_id, "disputed", suspend=True)


@api_router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > 1024 * 1024:
        raise HTTPException(status_code=413, detail="Payload Stripe trop volumineux")
    payload = await request.body()
    if len(payload) > 1024 * 1024:
        raise HTTPException(status_code=413, detail="Payload Stripe trop volumineux")
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except (stripe.error.SignatureVerificationError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid signature")
    ev_id = event.get("id") or ""
    if not ev_id:
        raise HTTPException(status_code=400, detail="Missing event id")
    try:
        await db.stripe_events.insert_one({
            "event_id": ev_id,
            "type": event.get("type"),
            "status": "processing",
            "received_at": datetime.now(timezone.utc),
            "processing_started_at": datetime.now(timezone.utc),
        })
    except DuplicateKeyError:
        existing = await db.stripe_events.find_one(
            {"event_id": ev_id}, {"_id": 0, "status": 1, "processing_started_at": 1}
        ) or {}
        # Legacy rows without a status were created by the old implementation
        # after signature verification and are treated as already processed.
        if existing.get("status") in (None, "processed"):
            return {"status": "ok", "duplicate": True}
        if existing.get("status") == "processing":
            started_at = existing.get("processing_started_at")
            if isinstance(started_at, datetime) and started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            stale = isinstance(started_at, datetime) and started_at < datetime.now(timezone.utc) - timedelta(minutes=5)
            if not stale:
                raise HTTPException(status_code=409, detail="Event already processing")
        claim = await db.stripe_events.update_one(
            {"event_id": ev_id, "status": {"$in": ["failed", "processing"]}},
            {"$set": {
                "status": "processing",
                "retry_at": datetime.now(timezone.utc),
                "processing_started_at": datetime.now(timezone.utc),
            }, "$unset": {"error_type": ""}},
        )
        if claim.modified_count != 1:
            raise HTTPException(status_code=409, detail="Event already claimed")
    except Exception:
        logger.exception("Stripe idempotency store unavailable")
        raise HTTPException(status_code=503, detail="Webhook temporarily unavailable")

    try:
        await _process_stripe_event(event)
    except Exception as exc:
        try:
            await db.stripe_events.update_one(
                {"event_id": ev_id, "status": "processing"},
                {"$set": {"status": "failed", "failed_at": now_iso(), "error_type": type(exc).__name__}},
            )
        except Exception:
            logger.exception("Unable to mark Stripe event as failed")
        raise

    await db.stripe_events.update_one(
        {"event_id": ev_id, "status": "processing"},
        {"$set": {"status": "processed", "processed_at": now_iso()}},
    )
    return {"status": "ok"}


@api_router.get("/subscription/me")
async def my_subscription(user: dict = Depends(get_current_user)):
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})  # nosec B105
    plan = _resolve_plan(u.get("subscription_plan"))
    status = u.get("subscription_status")
    # iter167 : count uniquement les utilisateurs de la société (fix cross-tenant leak).
    active_users = await db.users.count_documents({"company_id": company_id_of(user)})
    limit = PLAN_USER_LIMITS.get(plan) if plan else None
    # Prix computed selon la grille iter167 (avec extras Entreprise au-delà de 20)
    pricing = _compute_price(plan or "keylot_essentiel_monthly", active_users)
    suggested = _suggested_plan(active_users)
    # Retrieve Stripe subscription details (period, trial) if we have one
    period_start = None
    period_end = None
    trial_end = None
    cancel_at_period_end = False
    txn = await db.payment_transactions.find_one(
        {"user_id": user["id"], "company_id": company_id_of(user), "status": "completed"},
        {"_id": 0}, sort=[("updated_at", -1)],
    )
    if txn and txn.get("stripe_subscription_id") and stripe.api_key:
        try:
            sub = stripe.Subscription.retrieve(txn["stripe_subscription_id"])
            period_start = datetime.fromtimestamp(sub.current_period_start, tz=timezone.utc).isoformat() if sub.get("current_period_start") else None
            period_end = datetime.fromtimestamp(sub.current_period_end, tz=timezone.utc).isoformat() if sub.get("current_period_end") else None
            if sub.get("trial_end"):
                trial_end = datetime.fromtimestamp(sub.trial_end, tz=timezone.utc).isoformat()
            cancel_at_period_end = bool(sub.get("cancel_at_period_end"))
            status = sub.get("status") or status
        except stripe.error.StripeError:
            pass
    return {
        "plan": plan,
        "status": status,
        "updated_at": u.get("subscription_updated_at"),
        "active_users": active_users,
        "user_limit": limit,
        "period_start": period_start,
        "period_end": period_end,
        "trial_end": trial_end,
        "cancel_at_period_end": cancel_at_period_end,
        # iter167
        "pricing": pricing,
        "suggested_plan": suggested,
        "suggested_matches_current": (suggested == plan) if plan else False,
    }


@api_router.get("/subscription/catalog")
async def subscription_catalog(user: dict = Depends(get_current_user)):
    """iter167 : catalogue tarifaire officiel — utilisé par le front pour l'affichage
    et par les tests. Toutes les formules incluent 100 % des fonctionnalités."""
    return {
        "trial_days": TRIAL_DAYS,
        "plans": [
            {"key": "essentiel", "lookup_key": "keylot_essentiel_monthly", "label": "Essentiel", "price": 39, "max_users": 3, "range_label": "1 à 3 utilisateurs"},
            {"key": "equipe", "lookup_key": "keylot_equipe_monthly", "label": "Équipe", "price": 69, "max_users": 8, "range_label": "4 à 8 utilisateurs", "popular": True},
            {"key": "entreprise", "lookup_key": "keylot_entreprise_monthly", "label": "Entreprise", "price": 99, "max_users": None, "range_label": "9 à 15 utilisateurs (puis +10 € HT / mois par utilisateur supplémentaire)", "extra_price_per_user": 10, "extra_threshold": 15},
        ],
        "notice": "Toutes les fonctionnalités QYLOT sont incluses dans chaque formule. Votre abonnement évolue simplement avec la taille de votre équipe.",
    }


# ---------------- Overtime tracking (heures sup techniciens) ----------------

class OvertimeIn(BaseModel):
    technician_name: str = Field(min_length=1, max_length=120)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    hours: float = Field(ge=0, le=24)

    @field_validator("date")
    @classmethod
    def validate_overtime_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value


def _validate_iso_date(s: str) -> None:
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date invalide (YYYY-MM-DD)")


@api_router.get("/overtime")
async def list_overtime(month: str = Query(..., pattern=r"^\d{4}-\d{2}$"), user: dict = Depends(get_current_user)):
    check_perm(user, "overtime", "view", "own")
    prefix = _validated_month(month)
    scope = perm_scope(user, "overtime", "view")
    q = cq(user, {"date": {"$regex": f"^{prefix}"}})
    if scope == "own" and user.get("role") == "technicien":
        q["technician_name"] = user.get("name") or "__none__"
    entries = await db.overtime.find(q, {"_id": 0}).to_list(5000)

    # Threshold + curated eligibility list from settings
    s = await db.settings.find_one({"company_id": company_id_of(user), "kind": "global"}, {"_id": 0}) or {}
    threshold = float(s.get("overtime_alert_threshold", 30) or 0)
    eligible_raw = s.get("overtime_eligible")
    eligibility = [str(n).strip() for n in eligible_raw if str(n).strip()] if isinstance(eligible_raw, list) else None

    # iter62 : privilégie l'autorisation individuelle sur team_members.overtime_enabled
    # (rétro-compat : sinon on retombe sur la liste curated puis sur tous les techniciens)
    techs_all = await db.team_members.find(cq(user, {"type": "technicien"}), {"_id": 0}).sort("name", 1).to_list(500)
    enabled_names = [t["name"] for t in techs_all if t.get("overtime_enabled")]
    if enabled_names:
        tech_names = list(dict.fromkeys(enabled_names))
    elif eligibility is not None and eligibility:
        # Legacy : liste curated dans settings
        tech_names = list(dict.fromkeys(eligibility))
    else:
        # Défaut : rétro-compat historique, tous les techniciens
        tech_names = [t["name"] for t in techs_all]

    # iter189 — Dédup Sébastien vs Sebastien Hurtel : quand un team_member (ex : "Sébastien",
    # sans compte) et un user (ex : "Sebastien Hurtel", role=technicien) existent en
    # parallèle avec le même prénom normalisé, on n'affiche QUE le user (nom canonique).
    # Les saisies portées par l'ancien nom sont réattribuées au nom canonique pour que le
    # cumul soit correct dans le tableau et l'historique.
    tech_users = await db.users.find(
        cq(user, {"role": {"$in": ["technicien", "sous_traitant"]}}),
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(500)
    _first = lambda s: (_norm_name(s or "").split(" ", 1) or [""])[0]
    users_by_first = {}
    for u in tech_users:
        f = _first(u.get("name") or "")
        if f:
            users_by_first.setdefault(f, u["name"])  # premier gagnant (nom canonique)
    _canon_map: dict = {}  # ancien_nom → nom canonique
    dedup: list = []
    for nm in tech_names:
        canon = users_by_first.get(_first(nm), nm)
        if canon not in dedup:
            dedup.append(canon)
        if canon != nm:
            _canon_map[nm] = canon
    tech_names = dedup

    if scope == "own" and user.get("role") == "technicien":
        me = (user.get("name") or "").strip()
        # iter91 : la ligne du technicien connecté doit TOUJOURS apparaître dès qu'il a
        # accès à la rubrique heures sup, même s'il n'est pas dans team_members / pas
        # marqué overtime_enabled et même sans aucune saisie sur le mois en cours.
        tech_names = [me] if me else []

    # Always include names that already have entries in this month so historical data isn't hidden
    for e in entries:
        if e.get("technician_name") and e["technician_name"] not in tech_names:
            tech_names.append(e["technician_name"])
    # iter189 — Applique la carte de canonicalisation (Sébastien → Sebastien Hurtel)
    # aux entrées elles-mêmes pour que le cumul retombe sur le bon nom affiché.
    if _canon_map:
        for e in entries:
            nm = e.get("technician_name") or ""
            if nm in _canon_map:
                e["technician_name"] = _canon_map[nm]

    # iter116 : seuil par technicien (override) — indexé par name
    per_tech_threshold = {}
    for t in techs_all:
        v = t.get("overtime_alert_threshold")
        if v is not None:
            try:
                per_tech_threshold[t["name"]] = float(v)
            except Exception:
                logger.warning("Seuil d'heures supplémentaires invalide ignoré")

    approved_totals = {n: 0.0 for n in tech_names}
    pending_totals = {n: 0.0 for n in tech_names}
    refused_totals = {n: 0.0 for n in tech_names}
    for e in entries:
        n = e["technician_name"]
        h = float(e.get("hours") or 0)
        st = e.get("status")
        if st == "approved":
            approved_totals[n] = approved_totals.get(n, 0) + h
        elif st == "refused":
            refused_totals[n] = refused_totals.get(n, 0) + h
        else:
            pending_totals[n] = pending_totals.get(n, 0) + h
    # Countable hours (approved + pending) — refused entries do not count in monthly totals or threshold
    rows = []
    for n in tech_names:
        # iter116 : threshold effectif = override tech OU fallback global
        th = per_tech_threshold.get(n, threshold)
        total_countable = approved_totals.get(n, 0) + pending_totals.get(n, 0)
        rows.append({
            "technician_name": n,
            "approved_hours": round(approved_totals.get(n, 0), 2),
            "pending_hours": round(pending_totals.get(n, 0), 2),
            "refused_hours": round(refused_totals.get(n, 0), 2),
            "total_hours": round(total_countable, 2),
            "threshold": th,
            "over_threshold": th > 0 and total_countable >= th,
        })
    rows.sort(key=lambda r: (not r["over_threshold"], -r["total_hours"], r["technician_name"]))
    return {
        "month": prefix,
        "entries": entries,
        "rows": rows,
        "grand_total": round(sum(approved_totals.values()) + sum(pending_totals.values()), 2),
        "threshold": threshold,
    }


@api_router.post("/overtime")
async def upsert_overtime(data: OvertimeIn, user: dict = Depends(get_current_user)):
    check_perm(user, "overtime", "declare")
    name = data.technician_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Technicien requis")
    # A technician can only declare/edit their own overtime
    if user.get("role") == "technicien" and name != (user.get("name") or ""):
        raise HTTPException(status_code=403, detail="Vous ne pouvez déclarer que vos propres heures")
    _validate_iso_date(data.date)
    hours = float(data.hours or 0)
    q = cq(user, {"technician_name": name, "date": data.date})
    if hours <= 0:
        await db.overtime.delete_many(q)
        return {"deleted": True, "technician_name": name, "date": data.date, "hours": 0}
    existing = await db.overtime.find_one(q, {"_id": 0})
    if existing:
        # editing a validated entry sends it back to pending, unless admin/responsable edits it
        privileged = user.get("role") in ("admin", "responsable") or has_perm(user, "overtime", "validate")
        prev_status = existing.get("status", "pending")
        # iter92 : quand un technicien re-saisit une entrée refusée, on la remet en attente
        # et on efface le motif — l'admin doit revalider.
        if not privileged or prev_status == "refused":
            new_status = "pending"
        else:
            new_status = prev_status
        updates = {"hours": hours, "status": new_status, "updated_at": now_iso(), "updated_by": user["id"]}
        if new_status != "refused":
            updates["refused_reason"] = None
            updates["refused_at"] = None
            updates["refused_by"] = None
        await db.overtime.update_one(q, {"$set": updates})
        return {**existing, **updates}
    doc = with_company({
        "id": str(uuid.uuid4()),
        "technician_name": name,
        "date": data.date,
        "hours": hours,
        "status": "pending",
        "created_at": now_iso(),
        "created_by": user["id"],
    }, user)
    await db.overtime.insert_one(doc.copy())
    await log_audit(user, "create", "overtime", doc["id"], after=doc)
    await emit_notification(
        company_id_of(user), "overtime",
        title="Heures sup à valider",
        message=f"{name} a déclaré {hours}h le {data.date}",
        link_url="/heures-sup", roles=["admin", "responsable"], exclude_user_id=user["id"],
    )
    return doc


async def _notify_tech_of_status(user: dict, entry: dict, action: str, reason: Optional[str] = None):
    """iter92 : notifier le technicien concerné quand son entrée est validée / refusée."""
    if not entry or not entry.get("technician_name"):
        return
    tech = await db.users.find_one(
        cq(user, {"role": "technicien", "name": entry["technician_name"]}),
        {"_id": 0, "id": 1},
    )
    if not tech or not tech.get("id"):
        return
    hours = entry.get("hours") or 0
    date = entry.get("date") or ""
    if action == "approved":
        title = "Heures sup validées"
        message = f"{hours}h du {date} validées"
    else:
        title = "Heures sup refusées"
        message = f"{hours}h du {date} refusées" + (f" — {reason}" if reason else "")
    await emit_notification_to_users(
        company_id_of(user), [tech["id"]],
        title=title, message=message,
        link_url="/heures-sup", category="overtime",
    )


@api_router.put("/overtime/{oid}/validate")
async def validate_overtime(oid: str, user: dict = Depends(get_current_user)):
    check_perm(user, "overtime", "validate")
    r = await db.overtime.update_one(
        cq(user, {"id": oid}),
        {"$set": {
            "status": "approved",
            "validated_at": now_iso(), "validated_by": user["id"],
            "refused_reason": None, "refused_at": None, "refused_by": None,
        }},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Entrée introuvable")
    entry = await db.overtime.find_one(cq(user, {"id": oid}), {"_id": 0})
    await _notify_tech_of_status(user, entry, "approved")
    return entry


class OvertimeRefuseIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


@api_router.post("/overtime/{oid}/refuse")
async def refuse_overtime(oid: str, payload: OvertimeRefuseIn, user: dict = Depends(get_current_user)):
    """iter92 : refus explicite avec motif — l'entrée reste visible côté tech."""
    check_perm(user, "overtime", "validate")
    reason = (payload.reason or "").strip() or None
    r = await db.overtime.update_one(
        cq(user, {"id": oid}),
        {"$set": {
            "status": "refused",
            "refused_reason": reason,
            "refused_at": now_iso(), "refused_by": user["id"],
            "validated_at": None, "validated_by": None,
        }},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Entrée introuvable")
    entry = await db.overtime.find_one(cq(user, {"id": oid}), {"_id": 0})
    await _notify_tech_of_status(user, entry, "refused", reason)
    return entry


@api_router.put("/overtime/{oid}/reject")
async def reject_overtime(oid: str, user: dict = Depends(get_current_user)):
    """Legacy — rétro-compat : renvoie l'entrée en attente (undo d'une validation)."""
    check_perm(user, "overtime", "validate")
    r = await db.overtime.update_one(
        cq(user, {"id": oid}),
        {"$set": {"status": "pending", "validated_at": None, "validated_by": None}},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Entrée introuvable")
    return await db.overtime.find_one(cq(user, {"id": oid}), {"_id": 0})


@api_router.get("/overtime/history")
async def overtime_history(months: int = Query(6, ge=1, le=24), user: dict = Depends(get_current_user)):
    """iter92 : récapitulatif par mois sur les N derniers mois pour le technicien connecté (ou tous si admin)."""
    check_perm(user, "overtime", "view", "own")
    # Compute the list of last N months (YYYY-MM), most recent first
    today = datetime.now(timezone.utc)
    year, month = today.year, today.month
    month_list = []
    for _ in range(months):
        month_list.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    prefix_regex = "|".join(m for m in month_list)
    q = cq(user, {"date": {"$regex": f"^({prefix_regex})"}})
    scope = perm_scope(user, "overtime", "view")
    if scope == "own" and user.get("role") == "technicien":
        q["technician_name"] = user.get("name") or "__none__"
    entries = await db.overtime.find(q, {"_id": 0}).to_list(10000)
    # Aggregate per (technician, month)
    buckets: dict = {}
    for e in entries:
        m = (e.get("date") or "")[:7]
        n = e.get("technician_name") or ""
        key = (n, m)
        b = buckets.setdefault(key, {"approved": 0.0, "pending": 0.0, "refused": 0.0})
        h = float(e.get("hours") or 0)
        st = e.get("status")
        if st == "approved":
            b["approved"] += h
        elif st == "refused":
            b["refused"] += h
        else:
            b["pending"] += h
    # Build response oriented by month (per current tech only when scope=own)
    result_months = []
    for m in month_list:
        rows_for_month = []
        for (n, mm), b in buckets.items():
            if mm != m:
                continue
            rows_for_month.append({
                "technician_name": n,
                "approved_hours": round(b["approved"], 2),
                "pending_hours": round(b["pending"], 2),
                "refused_hours": round(b["refused"], 2),
                "total_hours": round(b["approved"] + b["pending"], 2),
            })
        result_months.append({"month": m, "rows": rows_for_month})
    return {"months": result_months}


class OvertimeValidateTechIn(BaseModel):
    technician_name: str = Field(min_length=1, max_length=120)
    month: str = Field(pattern=r"^\d{4}-\d{2}$")

    @field_validator("month")
    @classmethod
    def validate_overtime_month(cls, value: str) -> str:
        datetime.strptime(value, "%Y-%m")
        return value


@api_router.post("/overtime/validate-tech")
async def validate_all_pending_for_tech(payload: OvertimeValidateTechIn, user: dict = Depends(get_current_user)):
    """Validate all pending entries for a given technician + month."""
    check_perm(user, "overtime", "validate")
    name = payload.technician_name.strip()
    month = payload.month
    # Validate month range
    try:
        y, m = month.split("-")
        yy = int(y); mm = int(m)
        if not (1 <= mm <= 12) or yy < 2000 or yy > 2100:
            raise ValueError()
    except ValueError:
        raise HTTPException(status_code=400, detail="Mois invalide (YYYY-MM)")
    r = await db.overtime.update_many(
        cq(user, {"technician_name": name, "date": {"$regex": f"^{month}"}, "status": {"$ne": "approved"}}),
        {"$set": {"status": "approved", "validated_at": now_iso(), "validated_by": user["id"]}},
    )
    return {"validated": r.modified_count, "technician_name": name, "month": month}


class PortalRequest(BaseModel):
    return_url: str = Field(min_length=1, max_length=2048)


@api_router.post("/payments/portal")
async def create_billing_portal(req: PortalRequest, user: dict = Depends(require_admin)):
    """Open the Stripe billing portal for the current admin's Stripe customer."""
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe non configuré")
    # Find the latest paid transaction for this user to get the customer id
    txn = await db.payment_transactions.find_one(
        {"user_id": user["id"], "company_id": company_id_of(user), "status": "completed"},
        {"_id": 0},
        sort=[("updated_at", -1)],
    )
    customer_id = None
    if txn and txn.get("stripe_subscription_id"):
        try:
            sub = stripe.Subscription.retrieve(txn["stripe_subscription_id"])
            customer_id = sub.customer
        except stripe.error.StripeError:
            pass
    if not customer_id:
        # Fallback: retrieve via checkout session
        if txn:
            try:
                s = stripe.checkout.Session.retrieve(txn["session_id"])
                customer_id = s.customer
            except stripe.error.StripeError:
                pass
    if not customer_id:
        raise HTTPException(status_code=400, detail="Aucun abonnement Stripe trouvé pour cet utilisateur")
    try:
        safe_return_url = _safe_frontend_url(req.return_url, keep_path=True)
        portal = stripe.billing_portal.Session.create(customer=customer_id, return_url=safe_return_url)
    except stripe.error.StripeError:
        logger.exception("Stripe billing portal error")
        raise HTTPException(status_code=502, detail="Portail de paiement temporairement indisponible")
    return {"portal_url": portal.url}


# ---------------- Super-admin (companies management) ----------------

class CompanyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    admin_email: Optional[EmailStr] = None
    admin_password: Optional[str] = Field(default=None, min_length=12, max_length=72)
    admin_name: Optional[str] = Field(default=None, max_length=120)


TENANT_COLLECTIONS = (
    "users", "clients", "client_notes", "prospects", "sales", "projects", "project_notes",
    "team_members", "overtime", "settings", "payment_transactions",
    "notifications", "audit_log", "events", "absences", "off_days",
    "reinterventions", "bonus_awards", "bonuses", "project_bonuses",
    "ai_memories", "ai_corrections", "ai_recent_context", "kiks_pending", "ai_rate_limits",
    "stock", "stock_movements", "user_prefs", "client_import_batches",
)


@api_router.get("/superadmin/companies")
async def list_companies(user: dict = Depends(require_super_admin)):
    docs = await db.companies.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    for d in docs:
        d["user_count"] = await db.users.count_documents({"company_id": d["id"]})
        d["sales_count"] = await db.sales.count_documents({"company_id": d["id"]})
    return docs


@api_router.post("/superadmin/companies")
async def create_company(data: CompanyIn, user: dict = Depends(require_super_admin)):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom d'entreprise requis")
    if bool(data.admin_email) != bool(data.admin_password):
        raise HTTPException(status_code=400, detail="Email et mot de passe administrateur requis ensemble")
    if data.admin_password and len(data.admin_password) < 16:
        raise HTTPException(status_code=400, detail="Le mot de passe administrateur doit contenir au moins 16 caractères")
    email = data.admin_email.lower() if data.admin_email else None
    if email and await db.users.find_one({"email": email}, {"_id": 1}):
        raise HTTPException(status_code=400, detail="Email admin déjà utilisé")
    cid = str(uuid.uuid4())
    doc = {
        "id": cid, "name": name,
        "created_at": now_iso(),
        "created_by": user["id"],
    }
    await db.companies.insert_one(doc.copy())
    admin_user = None
    if data.admin_email and data.admin_password:
        uid = str(uuid.uuid4())
        admin_doc = {
            "id": uid, "email": email,
            "name": (data.admin_name or name).strip(),
            "password_hash": hash_password(data.admin_password),
            "role": "admin",
            "company_id": cid,
            "permissions": get_default_permissions("admin"),
            "created_at": now_iso(),
        }
        try:
            await db.users.insert_one(admin_doc)
        except Exception:
            # Compensate only the company created by this request; never leave an
            # unusable tenant behind when the paired admin creation fails.
            await db.companies.delete_one({"id": cid, "created_by": user["id"]})
            raise
        admin_user = public_user(admin_doc)
    return {"company": doc, "admin": admin_user}


@api_router.delete("/superadmin/companies/{cid}")
async def delete_company(cid: str, user: dict = Depends(require_super_admin)):
    if cid == DEFAULT_COMPANY_ID:
        raise HTTPException(status_code=400, detail="Impossible de supprimer l'entreprise par défaut")
    company = await db.companies.find_one({"id": cid}, {"_id": 0, "id": 1, "name": 1})
    if not company:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")
    deleted_counts = {}
    # Delete children first and the company record last. If a child deletion
    # fails, the tenant remains visible and the operation can safely be retried.
    for coll in TENANT_COLLECTIONS:
        result = await db[coll].delete_many({"company_id": cid})
        deleted_counts[coll] = int(result.deleted_count or 0)
    result = await db.companies.delete_one({"id": cid})
    if result.deleted_count != 1:
        raise HTTPException(status_code=500, detail="Suppression de l'entreprise incomplète")
    await db.company_deletion_log.insert_one({
        "company_id": cid,
        "company_name": company.get("name"),
        "deleted_counts": deleted_counts,
        "deleted_by": user.get("id"),
        "deleted_at": datetime.now(timezone.utc),
    })
    return {"ok": True, "company_id": cid, "deleted_counts": deleted_counts}


@api_router.get("/company/me")
async def my_company(user: dict = Depends(get_current_user)):
    if is_super_admin(user):
        return {"id": None, "name": "Super-admin", "role": "super_admin"}
    cid = company_id_of(user)
    doc = await db.companies.find_one({"id": cid}, {"_id": 0})
    if not doc:
        doc = {"id": cid, "name": os.environ.get("EMAIL_FROM_NAME", "KEYLOT"), "created_at": now_iso()}
    doc["user_count"] = await db.users.count_documents({"company_id": cid})
    return doc


# ---------------- Notifications & Audit log ----------------

NOTIFICATION_CATEGORIES = ["new_sales", "objectives", "planning", "overtime", "project_alerts", "events", "chantier_started", "chantier_confirmed", "chantier_terminated"]


async def _send_email(to: str, subject: str, html: str) -> Optional[str]:
    """Compatibility wrapper using the single hardened email implementation."""
    return await send_email(to=to, subject=subject, html=html)


def _project_email_html(kind: str, project: dict, client: dict) -> tuple:
    """Renvoie (subject, html) selon kind : 'started', 'confirmed', 'terminated'."""
    cname = escape(client.get("name") or project.get("client_name") or "?")
    addr = escape(client.get("address") or "")
    cp = escape(client.get("postal_code") or "")
    city = escape(client.get("city") or "")
    phone = escape(client.get("phone") or "")
    date = escape(project.get("scheduled_date") or "")
    service = escape(project.get("service") or "")
    titles = {"started": "Nouveau chantier programmé", "confirmed": "Chantier confirmé", "terminated": "Chantier terminé — prêt à encaisser"}
    subject = f"{titles.get(kind, 'Chantier')} — {cname}"
    body = (
        f'<table role="presentation" width="100%" style="font-family:Arial,sans-serif;background:#f8fafc;padding:24px">'
        f'<tr><td><div style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;padding:28px">'
        f'<h2 style="margin:0 0 12px 0;color:#0f172a">{escape(titles.get(kind, "Chantier"))}</h2>'
        f'<p style="margin:0 0 16px;color:#475569">Détails du chantier :</p>'
        f'<table cellpadding="6" style="width:100%;font-size:14px;color:#0f172a">'
        f'<tr><td style="color:#64748b;width:120px">Client</td><td><strong>{cname}</strong></td></tr>'
        f'{f"<tr><td style=color:#64748b>Adresse</td><td>{addr} · {cp} {city}</td></tr>" if (addr or city) else ""}'
        f'{f"<tr><td style=color:#64748b>Téléphone</td><td>{phone}</td></tr>" if phone else ""}'
        f'{f"<tr><td style=color:#64748b>Date</td><td>{date}</td></tr>" if date else ""}'
        f'{f"<tr><td style=color:#64748b>Prestation</td><td>{service}</td></tr>" if service else ""}'
        f'</table>'
        f'<p style="margin-top:20px;font-size:12px;color:#94a3b8">Envoyé par QYLOT. Ne répondez pas à cet email — connectez-vous à l\'application pour toute action.</p>'
        f'</div></td></tr></table>'
    )
    return subject, body


def _completion_commercial_email_html(*, client_name: str, address: str, completed_by: str,
                                      completed_at: str, note: str, photo_count: int) -> str:
    """Build the completion email with every business value encoded as text."""
    safe_client = escape(client_name or "Client")
    safe_address = escape(address or "—")
    safe_actor = escape(completed_by or "?")
    safe_at = escape(completed_at or "")
    safe_note = escape(note or "")
    note_line = (
        f"<p style='background:#f8fafc;padding:12px;border-left:3px solid #6366f1'>"
        f"<strong>Note du technicien :</strong> {safe_note}</p>"
        if safe_note else ""
    )
    photo_line = f"<p>📸 <strong>{int(photo_count)} photo(s)</strong> ajoutée(s) au chantier.</p>" if photo_count else ""
    return f"""
    <div style='font-family:system-ui,-apple-system,sans-serif;max-width:560px;color:#0f172a'>
      <h2 style='margin:0 0 8px 0'>Chantier terminé — {safe_client}</h2>
      <p><strong>{safe_actor}</strong> vient de terminer le chantier.</p>
      <ul style='line-height:1.7'>
        <li><strong>Client :</strong> {safe_client}</li>
        <li><strong>Adresse :</strong> {safe_address}</li>
        <li><strong>Date de fin :</strong> {safe_at}</li>
        <li><strong>Technicien :</strong> {safe_actor}</li>
      </ul>
      {note_line}
      {photo_line}
      <p style='margin-top:20px'>À toi de jouer : passe la vente en <em>Chèque récupéré</em> une fois le chèque en main.</p>
    </div>
    """


async def _emails_for_team_names(user: dict, names: list) -> list:
    """Résout les emails des techniciens/sous-traitants à partir de leurs noms."""
    if not names:
        return []
    emails = []
    for n in names:
        if not n:
            continue
        # team_members.email first, then users.email as fallback
        tm = await db.team_members.find_one(cq(user, {"name": n}), {"_id": 0, "email": 1}) or {}
        em = (tm.get("email") or "").strip()
        if not em:
            u = await db.users.find_one({"company_id": company_id_of(user), "name": n}, {"_id": 0, "email": 1}) or {}
            em = (u.get("email") or "").strip()
        if em and "@" in em:
            emails.append(em)
    return list(dict.fromkeys(emails))


async def _notify_project(user: dict, project: dict, kind: str):
    """Envoi asynchrone d'un email de chantier. kind: 'started'/'confirmed'/'terminated'.
    Vérifie la préférence société avant envoi. Silencieux si désactivé.
    iter166 : pour `confirmed`, émet aussi une notification cloche aux techniciens
    assignés (en plus de l'email) — bypass des prefs de catégorie individuelles.
    """
    try:
        cat_map = {"started": "chantier_started", "confirmed": "chantier_confirmed", "terminated": "chantier_terminated"}
        cat = cat_map.get(kind)
        if not cat:
            return
        if not await _notif_enabled(company_id_of(user), cat):
            return
        client = await db.clients.find_one(cq(user, {"id": project.get("client_id")}), {"_id": 0}) or {}
        subject, html = _project_email_html(kind, project, client)
        if kind in ("started", "confirmed"):
            assigned = project.get("assigned_to") or []
            if isinstance(assigned, str):
                assigned = [assigned]
            recipients = await _emails_for_team_names(user, assigned)
            # iter166 : notif cloche pour "confirmed" — retrouve les user_ids par email
            if kind == "confirmed" and recipients:
                target_uids = []
                for em in recipients:
                    u = await db.users.find_one({"company_id": company_id_of(user), "email": em}, {"_id": 0, "id": 1}) or {}
                    if u.get("id"):
                        target_uids.append(u["id"])
                if target_uids:
                    cname = client.get("name") or "Client"
                    await emit_notification_to_users(
                        company_id_of(user), target_uids,
                        title=f"Chantier confirmé — {cname}",
                        message=f"Le chantier de {cname} vient d'être confirmé par l'équipe.",
                        link_url="/chantiers",
                        category="chantier_confirmed",
                    )
        else:
            recipients = []
            # iter212 : ajout des admins (+ responsables) dans la liste des destinataires
            # de l'email « chantier terminé ». Le commercial était déjà couvert par
            # l'appel direct dans complete_project ligne ~9500 — on évite donc les
            # doublons en n'ajoutant ici QUE les admins/responsables.
            seen = set()
            async for u in db.users.find(
                {"company_id": company_id_of(user), "role": {"$in": ["admin", "responsable"]}},
                {"_id": 0, "email": 1},
            ):
                em = (u.get("email") or "").strip()
                if em and "@" in em and em not in seen:
                    seen.add(em)
                    recipients.append(em)
        for to in recipients:
            await _send_email(to, subject, html)
    except Exception as _e:
        logger.warning(f"notify_project {kind} failed: {_e}")


async def _notif_enabled(company_id: str, category: str) -> bool:
    s = await db.settings.find_one({"company_id": company_id, "kind": "global"}, {"_id": 0, "notifications": 1}) or {}
    prefs = (s.get("notifications") or {})
    return bool(prefs.get(category, False))


async def emit_notification(company_id: str, category: str, *, title: str, message: str, link_url: str = "", roles: Optional[List[str]] = None, exclude_user_id: Optional[str] = None):
    """Insert one notification per user matching the given roles. No-op if the category is disabled."""
    if not company_id:
        return 0
    if not await _notif_enabled(company_id, category):
        return 0
    q = {"company_id": company_id}
    if roles:
        q["role"] = {"$in": list(roles)}
    users = await db.users.find(q, {"_id": 0, "id": 1}).to_list(500)
    docs = []
    now = now_iso()
    for u in users:
        if exclude_user_id and u["id"] == exclude_user_id:
            continue
        docs.append({
            "id": str(uuid.uuid4()), "company_id": company_id, "user_id": u["id"],
            "category": category, "title": title, "message": message,
            "link_url": link_url, "is_read": False, "created_at": now,
        })
    if docs:
        await db.notifications.insert_many(docs)
    return len(docs)


async def emit_notification_to_users(company_id: str, user_ids: List[str], *, title: str, message: str, link_url: str = "", category: str = "events"):
    """Insert a notification for an explicit list of users, bypassing category prefs."""
    if not company_id or not user_ids:
        return 0
    docs = []
    now = now_iso()
    for uid in user_ids:
        docs.append({
            "id": str(uuid.uuid4()), "company_id": company_id, "user_id": uid,
            "category": category, "title": title, "message": message,
            "link_url": link_url, "is_read": False, "created_at": now,
        })
    if docs:
        await db.notifications.insert_many(docs)
    return len(docs)


@api_router.get("/notifications")
async def list_notifications(user: dict = Depends(get_current_user), only_unread: bool = False):
    q = cq(user, {"user_id": user["id"]})
    if only_unread:
        q["is_read"] = False
    items = await db.notifications.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    unread = await db.notifications.count_documents(cq(user, {"user_id": user["id"], "is_read": False}))
    return {"items": items, "unread": unread}


@api_router.put("/notifications/{nid}/read")
async def mark_notif_read(nid: str, user: dict = Depends(get_current_user)):
    r = await db.notifications.update_one(cq(user, {"id": nid, "user_id": user["id"]}), {"$set": {"is_read": True}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification introuvable")
    return {"ok": True}


@api_router.post("/notifications/read-all")
async def mark_all_notif_read(user: dict = Depends(get_current_user)):
    r = await db.notifications.update_many(cq(user, {"user_id": user["id"], "is_read": False}), {"$set": {"is_read": True}})
    return {"marked": r.modified_count}


@api_router.delete("/notifications/{nid}")
async def delete_notification(nid: str, user: dict = Depends(get_current_user)):
    r = await db.notifications.delete_one(cq(user, {"id": nid, "user_id": user["id"]}))
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Notification introuvable")
    return {"ok": True}


async def log_audit(user: dict, action: str, resource: str, resource_id: str, *,
                    before: Optional[dict] = None, after: Optional[dict] = None,
                    extra: Optional[dict] = None):
    """Record a sensitive action in the audit_log collection (best-effort)."""
    try:
        doc = {
            "id": str(uuid.uuid4()),
            "company_id": company_id_of(user),
            "user_id": user.get("id"),
            "user_name": user.get("name") or user.get("email") or "?",
            "user_role": user.get("role") or "",
            "action": action,          # create | update | delete
            "resource": resource,      # sale | client | project | user | overtime | commission | permissions
            "resource_id": resource_id,
            "before": before,
            "after": after,
            "extra": extra or {},
            "at": now_iso(),
        }
        await db.audit_log.insert_one(doc)
    except Exception as e:
        logger.warning(f"audit log failed: {e}")


@api_router.get("/audit")
async def list_audit(
    user: dict = Depends(require_admin),
    user_id: Optional[str] = Query(None, max_length=128),
    resource: Optional[str] = Query(None, max_length=80),
    action: Optional[str] = Query(None, max_length=80),
    from_date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    limit: int = Query(500, ge=1, le=2000),
):
    if from_date:
        date.fromisoformat(from_date)
    if to_date:
        date.fromisoformat(to_date)
    q = cq(user)
    if user_id:
        q["user_id"] = user_id
    if resource:
        q["resource"] = resource
    if action:
        q["action"] = action
    if from_date or to_date:
        q["at"] = {}
        if from_date:
            q["at"]["$gte"] = from_date
        if to_date:
            q["at"]["$lte"] = to_date + "T23:59:59Z" if len(to_date) == 10 else to_date
    docs = await db.audit_log.find(q, {"_id": 0}).sort("at", -1).to_list(limit)
    return docs


# ---------------- Startup ----------------

async def seed_admin():
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    admin_password = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": admin_email})
    if existing:
        if existing.get("role") != "admin" or (existing.get("company_id") or DEFAULT_COMPANY_ID) != DEFAULT_COMPANY_ID:
            logger.critical("ADMIN_EMAIL belongs to a non-admin or another tenant; no privilege change was made")
        return
    existing_admin = await db.users.find_one({"company_id": DEFAULT_COMPANY_ID, "role": "admin"}, {"_id": 1})
    if existing_admin:
        logger.warning("Default company already has an admin; ADMIN_EMAIL change will not create another privileged account")
        return
    await db.users.insert_one({
        "id": str(uuid.uuid4()), "email": admin_email, "name": "Kilian Blanc",
        "password_hash": hash_password(admin_password), "role": "admin",
        "company_id": DEFAULT_COMPANY_ID,
        "permissions": get_default_permissions("admin"),
        "created_at": now_iso(),
    })
    logger.info(f"Admin créé: {admin_email}")
    # iter191 — Le mot de passe défini via l'UI (page Utilisateurs > icône clé) est la
    # SOURCE DE VÉRITÉ. La seed NE réécrit JAMAIS le password_hash d'un admin existant,
    # même si `ADMIN_PASSWORD` diverge, sinon chaque restart / redéploiement réinitialiserait
    # le mot de passe choisi par l'admin (bug signalé Msg 431).


async def seed_default_company():
    """Ensure the default company exists (used as fallback for legacy data)."""
    existing = await db.companies.find_one({"id": DEFAULT_COMPANY_ID})
    if not existing:
        await db.companies.insert_one({
            "id": DEFAULT_COMPANY_ID,
            "name": os.environ.get("EMAIL_FROM_NAME", "KEYLOT"),
            "created_at": now_iso(),
            "created_by": "system",
        })
        logger.info("Entreprise par défaut créée")


async def seed_super_admin():
    """Ensure a super-admin user exists (creates companies + their first admin)."""
    email = (os.environ.get("SUPER_ADMIN_EMAIL") or "").lower().strip()
    password = os.environ.get("SUPER_ADMIN_PASSWORD") or ""
    if not email or not password:
        return
    existing = await db.users.find_one({"email": email})
    if existing:
        if existing.get("role") != "super_admin":
            logger.critical("SUPER_ADMIN_EMAIL belongs to a non-super-admin; no privilege escalation was performed")
        return
    existing_super_admin = await db.users.find_one({"role": "super_admin"}, {"_id": 1})
    if existing_super_admin:
        logger.warning("A super-admin already exists; environment changes will not create another privileged account")
        return
    await db.users.insert_one({
        "id": str(uuid.uuid4()), "email": email, "name": "Super Admin",
        "password_hash": hash_password(password), "role": "super_admin",
        "company_id": None,
        "permissions": {},
        "created_at": now_iso(),
    })
    logger.info(f"Super-admin créé: {email}")

async def migrate_multi_tenant():
    """Backfill company_id on all legacy documents and permissions on users."""
    collections = ["users", "clients", "sales", "projects", "team_members", "overtime", "payment_transactions"]
    for coll in collections:
        await db[coll].update_many({"company_id": {"$exists": False}}, {"$set": {"company_id": DEFAULT_COMPANY_ID}})
    # Users legacy without company_id (except super_admin which has null)
    await db.users.update_many({"company_id": None, "role": {"$ne": "super_admin"}}, {"$set": {"company_id": DEFAULT_COMPANY_ID}})
    # Backfill permissions per role
    cursor = db.users.find({"$or": [{"permissions": {"$exists": False}}, {"permissions": None}, {"permissions": {}}]}, {"_id": 1, "role": 1})
    async for u in cursor:
        role = u.get("role") or "commercial"
        if role == "super_admin":
            continue
        await db.users.update_one({"_id": u["_id"]}, {"$set": {"permissions": get_default_permissions(role)}})
    # Migrate global settings: old id=global doc -> per-company kind=global doc.
    # IDEMPOTENT: only copies the legacy document into a per-company shape if it hasn't been
    # migrated yet. We deliberately DO NOT delete the legacy doc — it never interferes because
    # every application query is scoped by company_id / kind, and keeping it prevents any risk
    # of destructive behaviour across restarts / redeployments.
    old_global = await db.settings.find_one({"id": "global"}, {"_id": 0})
    if old_global:
        existing = await db.settings.find_one({"company_id": DEFAULT_COMPANY_ID, "kind": "global"})
        if not existing:
            migrated = {**old_global, "id": f"global-{DEFAULT_COMPANY_ID}", "kind": "global", "company_id": DEFAULT_COMPANY_ID}
            try:
                await db.settings.insert_one(migrated)
            except Exception as e:
                logger.warning(f"Legacy settings migration skipped: {e}")
    logger.info("Migration multi-tenant OK")


async def _sync_user_team_membership(user: dict, u: dict) -> None:
    """iter102 : synchronise `team_members` avec le rôle du user (source unique = users.role).
    - supprime toute entrée team_members précédente rattachée au user (par email OU par name normalisé)
    - si role == commercial → upsert {type: 'commercial', name, email}
    - si role == technicien → upsert {type: 'technicien', name, email, overtime_enabled: preserved OR False}
    - sinon (sous_traitant, admin, responsable, comptable) → aucune entrée team_members (lecture directe users)
    Idempotent, best-effort.
    """
    if not u or not u.get("id"):
        return
    company = u.get("company_id") or company_id_of(user)
    email = (u.get("email") or "").strip().lower()
    name = (u.get("name") or "").strip()
    name_norm = _norm_name(name)
    role = u.get("role")
    # 1) Récupère les entrées existantes rattachées à ce user (email ou name)
    or_clauses = []
    if email:
        or_clauses.append({"email": email})
    if name:
        or_clauses.append({"name": name})
    existing = []
    if or_clauses:
        existing = await db.team_members.find({"company_id": company, "$or": or_clauses}, {"_id": 0}).to_list(50)
    target_type = "commercial" if role == "commercial" else ("technicien" if role == "technicien" else None)
    # 2) Si le rôle ne correspond à aucun bloc → supprime toutes les entrées liées, aucun résidu
    if not target_type:
        for e in existing:
            await db.team_members.delete_one({"id": e["id"], "company_id": company})
        return
    # 3) Cherche une entrée déjà au bon type → on la conserve et met à jour name/email
    kept = next((e for e in existing if e.get("type") == target_type), None)
    if kept:
        upd = {}
        if name and kept.get("name") != name:
            upd["name"] = name
        if email and (kept.get("email") or "") != email:
            upd["email"] = email
        if upd:
            await db.team_members.update_one({"id": kept["id"], "company_id": company}, {"$set": upd})
        # supprime les résidus d'un autre type
        for e in existing:
            if e["id"] != kept["id"]:
                await db.team_members.delete_one({"id": e["id"], "company_id": company})
        return
    # 4) Pas d'entrée du bon type → supprime les résidus + crée une nouvelle
    for e in existing:
        await db.team_members.delete_one({"id": e["id"], "company_id": company})
    new_doc = with_company({
        "id": str(uuid.uuid4()),
        "name": name or email or "(sans nom)",
        "type": target_type,
        "email": email or None,
        "objectif": 0.0,
        "created_at": now_iso(),
    }, {"company_id": company})
    if target_type == "technicien":
        new_doc["overtime_enabled"] = False
    await db.team_members.insert_one(new_doc)


async def _reconcile_sales_commercials(company_id: Optional[str] = None):
    """
    iter41/42/98: Réconcilie chaque vente avec un user commercial. Stratégie :
      • exact (norm key) → attache commercial_user_id + rename canonique
      • prénom unique → attache
      • ambigu OU aucun → flag `commercial_unmatched: True` pour revue admin (jamais rattaché "au hasard")
    Idempotent. Retourne un rapport {fixed, linked, flagged, cleared, unmatched_ids} pour l'endpoint admin.
    """
    import re as _re
    if company_id:
        company_ids = {company_id}
    else:
        try:
            companies = await db.companies.find({}, {"_id": 0, "id": 1}).to_list(500)
        except Exception:
            companies = []
        company_ids = {c["id"] for c in companies if c.get("id")} | {DEFAULT_COMPANY_ID}
    fixed = 0
    linked = 0
    flagged = 0
    cleared = 0
    unmatched_samples: List[dict] = []
    for cid in company_ids:
        users = await db.users.find(
            {"company_id": cid, "role": {"$in": ["commercial", "responsable", "admin"]}},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(500)
        if not users:
            continue
        by_full = {}
        by_first = {}
        for u in users:
            k = _norm_name(u.get("name") or "")
            if not k:
                continue
            by_full.setdefault(k, u)
            first = k.split(" ", 1)[0]
            by_first.setdefault(first, []).append(u)

        async for s in db.sales.find({"company_id": cid}, {"_id": 0, "id": 1, "commercial": 1, "commercial_2": 1, "commercial_user_id": 1, "commercial_2_user_id": 1, "commercial_unmatched": 1}):
            updates = {}
            unmatched_slots = []
            for slot, id_slot in (("commercial", "commercial_user_id"), ("commercial_2", "commercial_2_user_id")):
                nm = (s.get(slot) or "").strip()
                if not nm:
                    continue
                current_uid = s.get(id_slot)
                k = _norm_name(nm)
                # iter194 — Vérifie que le binding EXISTANT est cohérent. Si le nom du sale
                # ne matche PAS strictement (exact ou 1er token unique) le nom canonique du
                # user bound, on DÉLIE (bug historique du fuzzy Levenshtein qui a rattaché
                # « Kelian » à « Kilian Blanc »).
                if current_uid:
                    bound = next((u for u in users if u.get("id") == current_uid), None)
                    if bound:
                        bk = _norm_name(bound.get("name") or "")
                        first_sale = k.split(" ", 1)[0]
                        first_bound = bk.split(" ", 1)[0]
                        exact_first_cands = [u for u in users if _norm_name(u.get("name") or "").split(" ", 1)[0] == first_sale]
                        strict_ok = (k == bk) or (first_sale == first_bound and len(exact_first_cands) == 1)
                        if not strict_ok:
                            updates[id_slot] = None
                            cleared += 1
                            current_uid = None
                    else:
                        # user bound n'existe plus → nettoie
                        updates[id_slot] = None
                        current_uid = None
                if current_uid:
                    continue
                # (Re)tentative de matching STRICT — plus de fuzzy Levenshtein
                matched = by_full.get(k)
                if not matched:
                    first = k.split(" ", 1)[0]
                    cands = by_first.get(first, [])
                    if len(cands) == 1:
                        matched = cands[0]
                if matched:
                    canon = matched.get("name") or nm
                    if nm != canon:
                        updates[slot] = canon
                        fixed += 1
                    updates[id_slot] = matched["id"]
                    linked += 1
                elif not _is_direction(nm):
                    unmatched_slots.append({"slot": slot, "name": nm})
            if unmatched_slots:
                updates["commercial_unmatched"] = True
                flagged += 1
                if len(unmatched_samples) < 20:
                    unmatched_samples.append({"sale_id": s["id"], "company_id": cid, "unmatched": unmatched_slots})
            elif s.get("commercial_unmatched"):
                updates["commercial_unmatched"] = False
                cleared += 1
            if updates:
                await db.sales.update_one({"id": s["id"], "company_id": cid}, {"$set": updates})
    logger.info(f"Reconcile sales commercials: {fixed} names normalized, {linked} user IDs linked, {flagged} flagged unmatched, {cleared} cleared")
    return {"names_normalized": fixed, "user_ids_linked": linked, "flagged_unmatched": flagged, "cleared": cleared, "unmatched_samples": unmatched_samples}


@api_router.post("/admin/reconcile-commercials")
async def admin_reconcile_commercials(user: dict = Depends(get_current_user)):
    """iter98 : recalcule commercial_user_id sur toutes les ventes existantes.
    Idempotent. Retourne le rapport détaillé (dont un extrait des ventes non résolvables)."""
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Réservé aux admins/responsables")
    return await _reconcile_sales_commercials(company_id_of(user))


async def _reconcile_cancelled_projects():
    """
    iter46: Backfill — pour toutes les ventes historiquement `annule`/`litige`, s'assure
    que les projets liés portent bien `cancelled: True` (soft-delete). Idempotent.
    """
    n = 0
    async for s in db.sales.find({"status": {"$in": ["annule", "litige"]}}, {"_id": 0, "id": 1, "company_id": 1}):
        r = await db.projects.update_many(
            {"sale_id": s["id"], "company_id": s.get("company_id"), "cancelled": {"$ne": True}},
            {"$set": {"cancelled": True, "cancelled_at": now_iso(), "cancelled_reason": "auto_reconcile"}},
        )
        n += r.modified_count
    if n:
        logger.info(f"Reconcile cancelled projects: {n} projects soft-deleted (ventes annulées/litige)")


async def seed_demo_data():
    if await db.clients.count_documents({}) > 0:
        return
    demo_clients = [
        {"id": str(uuid.uuid4()), "company_id": DEFAULT_COMPANY_ID, "name": "Martin Dupont", "phone": "06 12 34 56 78", "email": "m.dupont@example.com", "address": "12 rue de la Paix", "postal_code": "69003", "city": "Lyon", "notes": "Recommandé par voisin", "created_at": now_iso()},
        {"id": str(uuid.uuid4()), "company_id": DEFAULT_COMPANY_ID, "name": "Sophie Bernard", "phone": "06 98 76 54 32", "email": "sophie.b@example.com", "address": "45 avenue des Fleurs", "postal_code": "69100", "city": "Villeurbanne", "notes": "", "created_at": now_iso()},
        {"id": str(uuid.uuid4()), "company_id": DEFAULT_COMPANY_ID, "name": "Jean-Marc Rousseau", "phone": "07 11 22 33 44", "email": "", "address": "8 chemin du Lac", "postal_code": "69130", "city": "Écully", "notes": "Bâtiment ancien", "created_at": now_iso()},
    ]
    await db.clients.insert_many([c.copy() for c in demo_clients])
    today = datetime.now(timezone.utc)
    demo_sales = [
        {"id": str(uuid.uuid4()), "company_id": DEFAULT_COMPANY_ID, "client_id": demo_clients[0]["id"], "bdc": "BDC-2026-001", "service": "Installation panneaux solaires 6 kWc", "amount": 9800, "payment_method": "financement", "commission_rate": 0.20, "sale_date": (today - timedelta(days=3)).date().isoformat(), "desired_intervention_date": (today + timedelta(days=14)).date().isoformat(), "status": "commercial_cheque", "notes": "Acompte reçu", "created_by": "system", "created_at": now_iso()},
        {"id": str(uuid.uuid4()), "company_id": DEFAULT_COMPANY_ID, "client_id": demo_clients[1]["id"], "bdc": "BDC-2026-002", "service": "Isolation combles perdus 80 m²", "amount": 3400, "payment_method": "comptant", "commission_rate": 0.13, "sale_date": (today - timedelta(days=1)).date().isoformat(), "desired_intervention_date": (today + timedelta(days=7)).date().isoformat(), "status": "argent_recupere", "notes": "", "created_by": "system", "created_at": now_iso()},
        {"id": str(uuid.uuid4()), "company_id": DEFAULT_COMPANY_ID, "client_id": demo_clients[2]["id"], "bdc": "BDC-2026-003", "service": "Pompe à chaleur air/eau + ballon", "amount": 12500, "payment_method": "acompte", "commission_rate": 0.25, "sale_date": today.date().isoformat(), "desired_intervention_date": None, "status": "commercial_cheque", "notes": "En attente devis final", "created_by": "system", "created_at": now_iso()},
    ]
    await db.sales.insert_many([s.copy() for s in demo_sales])
    demo_projects = [
        {"id": str(uuid.uuid4()), "company_id": DEFAULT_COMPANY_ID, "sale_id": demo_sales[0]["id"], "client_id": demo_clients[0]["id"], "service": demo_sales[0]["service"], "status": "a_planifier", "priority": "haute", "scheduled_date": demo_sales[0]["desired_intervention_date"], "assigned_to": "Équipe A", "duration_days": 2, "notes": "", "created_at": now_iso()},
        {"id": str(uuid.uuid4()), "company_id": DEFAULT_COMPANY_ID, "sale_id": demo_sales[1]["id"], "client_id": demo_clients[1]["id"], "service": demo_sales[1]["service"], "status": "en_cours", "priority": "moyenne", "scheduled_date": demo_sales[1]["desired_intervention_date"], "assigned_to": "Équipe B", "duration_days": 1, "notes": "", "created_at": now_iso()},
    ]
    await db.projects.insert_many([p.copy() for p in demo_projects])
    logger.info("Données de démonstration créées")

async def migrate_sales_statuses():
    """Migrate old sale statuses to new ones and ensure commission_rate exists."""
    mapping = {"signee": "commercial_cheque", "en_attente": "commercial_cheque", "annulee": "annule"}
    for old, new in mapping.items():
        await db.sales.update_many({"status": old}, {"$set": {"status": new}})
    await db.sales.update_many({"commission_rate": {"$exists": False}}, {"$set": {"commission_rate": 0.10}})


async def migrate_projects_assigned_to():
    """Ensure `assigned_to` is a flat list of strings on all project documents (legacy: string, or nested arrays)."""
    cursor = db.projects.find({}, {"_id": 1, "assigned_to": 1})
    async for doc in cursor:
        val = doc.get("assigned_to")
        if val is None:
            await db.projects.update_one({"_id": doc["_id"]}, {"$set": {"assigned_to": []}})
            continue
        if isinstance(val, str):
            new_val = [val] if val else []
        elif isinstance(val, list):
            flat = []
            for x in val:
                if isinstance(x, list):
                    flat.extend([y for y in x if isinstance(y, str) and y.strip()])
                elif isinstance(x, str) and x.strip():
                    flat.append(x)
            # Dedup preserving order
            seen = set()
            new_val = [n for n in flat if not (n in seen or seen.add(n))]
        else:
            new_val = []
        if new_val != val:
            await db.projects.update_one({"_id": doc["_id"]}, {"$set": {"assigned_to": new_val}})
    await db.projects.update_many({"duration_days": {"$exists": False}}, {"$set": {"duration_days": 1}})

async def seed_team_members():
    if await db.team_members.count_documents({}) > 0:
        return
    commerciaux = ["Thomas", "Nolan", "Kelian", "Theo", "Anaïs", "Lucelia", "Ludo", "Guillaume", "Kilian"]
    techniciens = ["Yann", "Sébastien", "Ludo", "Evan", "Guillaume"]
    docs = []
    for n in commerciaux:
        docs.append({"id": str(uuid.uuid4()), "company_id": DEFAULT_COMPANY_ID, "name": n, "type": "commercial", "created_at": now_iso()})
    for n in techniciens:
        docs.append({"id": str(uuid.uuid4()), "company_id": DEFAULT_COMPANY_ID, "name": n, "type": "technicien", "created_at": now_iso()})
    await db.team_members.insert_many(docs)
    logger.info("Équipe initiale créée (commerciaux + techniciens)")

    await db.settings.update_one(
        {"kind": "global", "company_id": DEFAULT_COMPANY_ID, "app_name": {"$in": ["PYLOT", "Chantier Pro"]}},
        {"$set": {"app_name": "KEYLOT"}}
    )

@app.on_event("startup")
async def on_startup():
    # iter165 : garde-fou persistance — on relève les volumes des collections
    # critiques AVANT toute migration/seed pour tracer que rien n'est effacé au
    # démarrage. Aucune ligne de code du startup ne doit faire de DROP/wipe.
    _preserve_before = {}
    for _c in ("users", "companies", "clients", "sales", "projects", "project_notes",
               "settings", "team_members", "notifications", "audit_log",
               "documents", "overtime", "absences", "events", "reinterventions",
               "bonus_awards", "project_bonuses", "ai_memories", "payment_transactions"):
        try:
            _preserve_before[_c] = await db[_c].estimated_document_count()
        except Exception:
            _preserve_before[_c] = -1
    logger.info(f"[persistence] Volumes AVANT migrations : {_preserve_before}")
    await db.users.create_index("email", unique=True)
    await db.clients.create_index("name")
    await db.sales.create_index("client_id")
    await db.projects.create_index("sale_id")
    await db.sales.create_index([("company_id", 1), ("id", 1)], unique=True)
    await db.projects.create_index([("company_id", 1), ("id", 1)], unique=True)
    # A product is unique inside a company. Besides preventing duplicate rows,
    # this closes the race where two workers create the same normalized product.
    await db.stock.create_index(
        [("company_id", 1), ("product_key", 1)],
        unique=True,
        partialFilterExpression={"product_key": {"$type": "string"}},
    )
    await db.project_notes.create_index([("company_id", 1), ("project_id", 1), ("technician_name_lc", 1)])
    await db.project_bonuses.create_index([("company_id", 1), ("project_id", 1), ("technician_name_lc", 1)])
    await db.payment_transactions.create_index([("company_id", 1), ("session_id", 1)])
    await db.cron_runs.create_index([("name", 1), ("run_id", 1)], unique=True)
    await db.companies.create_index("id", unique=True)
    await db.stripe_events.create_index("event_id", unique=True)
    await db.ai_recent_context.create_index("expires_at", expireAfterSeconds=0)
    await db.kiks_pending.create_index("expires_at", expireAfterSeconds=0)
    await db.login_attempts.create_index("expires_at", expireAfterSeconds=0)
    await db.login_source_attempts.create_index("expires_at", expireAfterSeconds=0)
    await db.client_import_batches.create_index("expires_at", expireAfterSeconds=0)
    await db.ai_rate_limits.create_index("expires_at", expireAfterSeconds=0)
    for collection_name in TENANT_COLLECTIONS:
        await db[collection_name].create_index("company_id")
    await seed_default_company()
    await seed_admin()
    await seed_super_admin()
    environment = (os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "development").lower()
    allow_demo = (os.environ.get("ALLOW_DEMO_DATA") or "false").strip().lower() in ("1", "true", "yes")
    if allow_demo and environment not in ("production", "prod"):
        await seed_demo_data()
        await seed_team_members()
    default_run_migrations = environment not in ("production", "prod")
    run_startup_migrations = (
        os.environ.get("RUN_STARTUP_MIGRATIONS")
        or ("true" if default_run_migrations else "false")
    ).strip().lower() in ("1", "true", "yes")
    if environment in ("production", "prod") and run_startup_migrations:
        raise RuntimeError("RUN_STARTUP_MIGRATIONS est interdit en production; utilisez la commande de migration explicite")
    if run_startup_migrations:
        await migrate_sales_statuses()
        await migrate_projects_assigned_to()
        await migrate_multi_tenant()
        await _reconcile_sales_commercials()
        await _reconcile_cancelled_projects()
    else:
        logger.info("Startup data migrations disabled; use `python -m backend.migrate --apply` during deployment")
    # iter165 : garde-fou — vérifier que les collections n'ont PAS perdu de doc.
    # Les migrations doivent être additives uniquement. Si une collection critique
    # a moins de docs qu'avant, on log CRITICAL sans bloquer (pour ne pas casser
    # un démarrage en env de test où la DB peut être vide). L'ops peut alerter
    # sur ce log via prometheus/grafana.
    for _c, _n_before in _preserve_before.items():
        try:
            _n_after = await db[_c].estimated_document_count()
        except Exception:
            _n_after = -1
        if _n_before > 0 and _n_after < _n_before:
            logger.critical(
                f"[persistence] ⚠️ REGRESSION de volume sur `{_c}` : {_n_before} → {_n_after}. "
                "Un correctif est requis avant toute nouvelle mise à jour."
            )
        elif _n_before >= 0:
            logger.info(f"[persistence] {_c}: {_n_before} → {_n_after} (OK)")
    # Detect orphan projects but never delete business data during application startup.
    try:
        all_sale_ids = {s["id"] async for s in db.sales.find({}, {"_id": 0, "id": 1})}
        orphans = []
        async for p in db.projects.find({"sale_id": {"$exists": True, "$ne": None}}, {"_id": 0, "id": 1, "sale_id": 1}):
            if p.get("sale_id") and p["sale_id"] not in all_sale_ids:
                orphans.append(p["id"])
        if orphans:
            logger.warning(f"[persistence] {len(orphans)} chantier(s) orphelin(s) détecté(s); aucune suppression automatique")
    except Exception as _e:
        logger.warning(f"orphan projects cleanup failed: {_e}")

@app.on_event("shutdown")
async def on_shutdown():
    client.close()


# ---------------- Prospects (leads with source tracking) ----------------

PROSPECT_SOURCES = ["manuel", "site_web", "scan_maison", "partenaire", "publicite", "autre"]
PROSPECT_STATUSES = ["nouveau", "contacte", "converti", "perdu"]


class ProspectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: Optional[str] = Field(default="", max_length=40)
    email: Optional[str] = Field(default="", max_length=320)
    address: Optional[str] = Field(default="", max_length=500)
    postal_code: Optional[str] = Field(default="", max_length=20)
    city: Optional[str] = Field(default="", max_length=120)
    notes: Optional[str] = Field(default="", max_length=5000)
    source: str = Field(default="manuel", max_length=40)
    status: str = Field(default="nouveau", max_length=40)
    assigned_to: Optional[str] = Field(default="", max_length=120)  # commercial name


class ProspectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=40)
    email: Optional[str] = Field(default=None, max_length=320)
    address: Optional[str] = Field(default=None, max_length=500)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    city: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=5000)
    source: Optional[str] = Field(default=None, max_length=40)
    status: Optional[str] = Field(default=None, max_length=40)
    assigned_to: Optional[str] = Field(default=None, max_length=120)


def _validate_prospect_enums(source: Optional[str], status: Optional[str]):
    if source is not None and source not in PROSPECT_SOURCES:
        raise HTTPException(status_code=400, detail=f"Source invalide. Valeurs: {', '.join(PROSPECT_SOURCES)}")
    if status is not None and status not in PROSPECT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Statut invalide. Valeurs: {', '.join(PROSPECT_STATUSES)}")


@api_router.get("/prospects")
async def list_prospects(
    user: dict = Depends(get_current_user),
    source: Optional[str] = Query(None, max_length=40),
    status: Optional[str] = Query(None, max_length=40),
):
    # Prospects visibility uses the same rules as clients
    check_perm(user, "clients", "view", "own")
    _validate_prospect_enums(source, status)
    scope = perm_scope(user, "clients", "view")
    q = cq(user)
    if scope == "own":
        q["assigned_to"] = user.get("name") or "__none__"
    if source:
        q["source"] = source
    if status:
        q["status"] = status
    docs = await db.prospects.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return docs


@api_router.post("/prospects")
async def create_prospect(data: ProspectIn, user: dict = Depends(get_current_user)):
    check_perm(user, "clients", "create")
    _validate_prospect_enums(data.source, data.status)
    payload = data.model_dump()
    if perm_scope(user, "clients", "view") == "own":
        payload["assigned_to"] = user.get("name") or ""
    doc = with_company({
        "id": str(uuid.uuid4()),
        "created_at": now_iso(),
        "created_by": user["id"],
        **payload,
    }, user)
    await db.prospects.insert_one(doc.copy())
    await log_audit(user, "create", "prospect", doc["id"], after=doc)
    return doc


@api_router.put("/prospects/{pid}")
async def update_prospect(pid: str, data: ProspectUpdate, user: dict = Depends(get_current_user)):
    check_perm(user, "clients", "edit")
    _validate_prospect_enums(data.source, data.status)
    prospect_q = _scoped_prospect_query(user, pid)
    before = await db.prospects.find_one(prospect_q, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Prospect introuvable")
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if perm_scope(user, "clients", "view") == "own" and "assigned_to" in updates:
        updates["assigned_to"] = user.get("name") or ""
    if not updates:
        raise HTTPException(status_code=400, detail="Aucun champ à mettre à jour")
    await db.prospects.update_one(prospect_q, {"$set": updates})
    after = await db.prospects.find_one(prospect_q, {"_id": 0})
    await log_audit(user, "update", "prospect", pid, before=before, after=after)
    return after


@api_router.delete("/prospects/{pid}")
async def delete_prospect(pid: str, user: dict = Depends(get_current_user)):
    check_perm(user, "clients", "delete")
    prospect_q = _scoped_prospect_query(user, pid)
    before = await db.prospects.find_one(prospect_q, {"_id": 0})
    r = await db.prospects.delete_one(prospect_q)
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Prospect introuvable")
    await log_audit(user, "delete", "prospect", pid, before=before)
    return {"ok": True}


@api_router.post("/prospects/{pid}/convert")
async def convert_prospect_to_client(pid: str, user: dict = Depends(get_current_user)):
    """Convert a prospect into a full client (keeps a reference)."""
    check_perm(user, "clients", "create")
    prospect_q = _scoped_prospect_query(user, pid)
    p = await db.prospects.find_one(prospect_q, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Prospect introuvable")
    if p.get("status") == "converti" and p.get("converted_client_id"):
        c = await db.clients.find_one(cq(user, {"id": p["converted_client_id"]}), {"_id": 0})
        if c:
            return c
    cid = str(uuid.uuid4())
    client_doc = with_company({
        "id": cid,
        "name": p.get("name", ""),
        "phone": p.get("phone", ""),
        "email": p.get("email", ""),
        "address": p.get("address", ""),
        "postal_code": p.get("postal_code", ""),
        "city": p.get("city", ""),
        "notes": p.get("notes", ""),
        "prospect_source": p.get("source"),  # keep provenance
        "prospect_id": pid,
        "created_at": now_iso(),
        "created_by": user["id"],
    }, user)
    await db.clients.insert_one(client_doc.copy())
    await db.prospects.update_one(prospect_q, {"$set": {"status": "converti", "converted_client_id": cid, "converted_at": now_iso()}})
    await log_audit(user, "update", "prospect", pid, extra={"converted_to_client": cid})
    await log_audit(user, "create", "client", cid, after=client_doc, extra={"from_prospect": pid})
    return client_doc


@api_router.get("/prospects/meta/sources")
async def prospect_sources_meta(user: dict = Depends(get_current_user)):
    return {"sources": PROSPECT_SOURCES, "statuses": PROSPECT_STATUSES}

# ---------------- Absences (planning) ----------------

class AbsenceIn(BaseModel):
    person_name: str = Field(min_length=1, max_length=120)
    person_type: str = Field(pattern=r"^(technicien|commercial)$")
    date_from: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_to: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    reason: Optional[str] = Field(default="", max_length=500)
    # iter51 : absence partielle (RDV médical, matin/après-midi…)
    all_day: Optional[bool] = True
    start_time: Optional[str] = Field(default=None, pattern=r"^(\d{2}:\d{2})?$")
    end_time: Optional[str] = Field(default=None, pattern=r"^(\d{2}:\d{2})?$")
    note: Optional[str] = Field(default="", max_length=2000)

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_absence_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_absence_time(cls, value: Optional[str]) -> Optional[str]:
        if value:
            datetime.strptime(value, "%H:%M")
        return value

    @model_validator(mode="after")
    def validate_absence_range(self):
        if self.date_to < self.date_from:
            raise ValueError("date_to doit être ≥ date_from")
        if self.all_day is False:
            if self.date_from != self.date_to:
                raise ValueError("Une absence partielle doit être sur une seule journée")
            if not self.start_time or not self.end_time:
                raise ValueError("Heure de début et de fin requises pour une absence partielle")
            if self.end_time <= self.start_time:
                raise ValueError("L'heure de fin doit être postérieure à l'heure de début")
        return self


@api_router.get("/absences")
async def list_absences(user: dict = Depends(get_current_user), month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$")):
    # iter159 : les absences ne sont visibles qu'aux admins/responsables/super_admins.
    # Les commerciaux, techniciens et sous-traitants ne voient jamais qu'un collègue
    # est absent (privacy). Demande utilisateur Msg 351.
    if user.get("role") not in ("admin", "responsable", "super_admin"):
        return []
    q = cq(user)
    if month:
        month = _validated_month(month)
        # Any absence overlapping the given month
        prefix = month[:7]
        q["$or"] = [
            {"date_from": {"$regex": f"^{prefix}"}},
            {"date_to": {"$regex": f"^{prefix}"}},
        ]
    docs = await db.absences.find(q, {"_id": 0}).sort("date_from", -1).to_list(2000)
    return docs


@api_router.post("/absences")
async def create_absence(data: AbsenceIn, user: dict = Depends(get_current_user)):
    check_perm(user, "planning", "edit", "team")
    if data.date_to < data.date_from:
        raise HTTPException(status_code=400, detail="date_to doit être ≥ date_from")
    # iter51 : validation partielle
    all_day = bool(data.all_day) if data.all_day is not None else True
    st = (data.start_time or "").strip() or None
    et = (data.end_time or "").strip() or None
    if not all_day:
        if data.date_from != data.date_to:
            raise HTTPException(status_code=400, detail="Une absence partielle doit être sur une seule journée")
        if not st or not et:
            raise HTTPException(status_code=400, detail="Heure de début et de fin requises pour une absence partielle")
        if et <= st:
            raise HTTPException(status_code=400, detail="L'heure de fin doit être postérieure à l'heure de début")
    else:
        st = None; et = None
    doc = with_company({
        "id": str(uuid.uuid4()),
        "person_name": data.person_name.strip(),
        "person_type": data.person_type,
        "date_from": data.date_from,
        "date_to": data.date_to,
        "reason": (data.reason or "").strip(),
        "all_day": all_day,
        "start_time": st,
        "end_time": et,
        "note": (data.note or "").strip(),
        "created_at": now_iso(),
        "created_by": user["id"],
    }, user)
    await db.absences.insert_one(doc.copy())
    await log_audit(user, "create", "absence", doc["id"], after=doc)
    return doc


@api_router.delete("/absences/{aid}")
async def delete_absence(aid: str, user: dict = Depends(get_current_user)):
    check_perm(user, "planning", "edit", "team")
    before = await db.absences.find_one(cq(user, {"id": aid}), {"_id": 0})
    r = await db.absences.delete_one(cq(user, {"id": aid}))
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Absence introuvable")
    await log_audit(user, "delete", "absence", aid, before=before)
    return {"ok": True}


# ---------------- Réinterventions (SAV / passages complémentaires) ----------------

class ReinterventionIn(BaseModel):
    client_id: str = Field(min_length=1, max_length=128)
    technician_name: Optional[str] = Field(default="", max_length=120)
    scheduled_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    scheduled_time: Optional[str] = Field(default="", max_length=5)  # HH:MM
    note: Optional[str] = Field(default="", max_length=5000)
    status: Optional[Literal["a_faire", "terminee"]] = "a_faire"
    # iter179 : photos jointes (avant/après intervention). Base64 data URI, plafonné côté frontend.
    photos: Optional[List[str]] = Field(default=None, max_length=MAX_PHOTOS_PER_ENTITY)

    @field_validator("scheduled_date")
    @classmethod
    def validate_reintervention_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value

    @field_validator("scheduled_time")
    @classmethod
    def validate_reintervention_time(cls, value: Optional[str]) -> Optional[str]:
        if value:
            datetime.strptime(value, "%H:%M")
        return value


class ReinterventionUpdate(BaseModel):
    technician_name: Optional[str] = Field(default=None, max_length=120)
    scheduled_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    scheduled_time: Optional[str] = Field(default=None, max_length=5)
    note: Optional[str] = Field(default=None, max_length=5000)
    status: Optional[Literal["a_faire", "terminee"]] = None
    photos: Optional[List[str]] = Field(default=None, max_length=MAX_PHOTOS_PER_ENTITY)

    @field_validator("scheduled_date")
    @classmethod
    def validate_reintervention_date(cls, value: Optional[str]) -> Optional[str]:
        if value:
            date.fromisoformat(value)
        return value

    @field_validator("scheduled_time")
    @classmethod
    def validate_reintervention_time(cls, value: Optional[str]) -> Optional[str]:
        if value:
            datetime.strptime(value, "%H:%M")
        return value


@api_router.get("/reinterventions")
async def list_reinterventions(user: dict = Depends(get_current_user), client_id: Optional[str] = Query(None, max_length=128), month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$")):
    q = cq(user)
    if client_id:
        q["client_id"] = client_id
    if month:
        q["scheduled_date"] = {"$regex": f"^{_validated_month(month)}"}
    docs = await db.reinterventions.find(q, {"_id": 0}).sort("scheduled_date", 1).to_list(2000)
    # iter193 — Filtrage par rôle :
    # - Technicien / Sous-traitant : uniquement leurs propres réinterventions (par technician_name)
    # - Commercial / Comptable : réinterventions liées à leurs propres clients uniquement
    #   (ex : réinter chez le client de Kilian → visible par Kilian, mais PAS par Théo)
    # - Admin / Responsable / Super-admin : voient tout (aggrégation planning globale)
    role = user.get("role") or ""
    if role in ("technicien", "sous_traitant"):
        import unicodedata
        def _n(s): return " ".join(unicodedata.normalize("NFKD", s or "").encode("ascii","ignore").decode().lower().split())
        me = _n(user.get("name") or "")
        docs = [d for d in docs if _n(d.get("technician_name") or "") == me]
    elif role in ("commercial", "comptable"):
        # On isole les réinterventions dont les clients appartiennent aux propres ventes du user.
        # (les commerciaux n'ont pas à voir les SAV des chantiers d'autres commerciaux)
        my_client_ids = await _commercial_client_ids(user) if role == "commercial" else []
        my_set = set(my_client_ids)
        docs = [d for d in docs if (d.get("client_id") or "") in my_set] if role == "commercial" else []
    elif role in PROSPECT_ROLES:
        p_clients = set((await _prospect_ids(user))[1])
        docs = [d for d in docs if (d.get("client_id") or "") in p_clients]
    # Enrich with client info
    if docs:
        cids = list({d["client_id"] for d in docs if d.get("client_id")})
        clients = await db.clients.find(cq(user, {"id": {"$in": cids}}), {"_id": 0}).to_list(len(cids))
        cmap = {c["id"]: c for c in clients}
        for d in docs:
            c = cmap.get(d.get("client_id")) or {}
            d["client_name"] = c.get("name", "")
            d["client_phone"] = c.get("phone", "")
            d["client_address"] = f"{c.get('address','')}{(', ' + c.get('postal_code','')) if c.get('postal_code') else ''}{(' ' + c.get('city','')) if c.get('city') else ''}".strip(", ")
    return docs


@api_router.post("/reinterventions")
async def create_reintervention(data: ReinterventionIn, user: dict = Depends(get_current_user)):
    check_perm(user, "planning", "edit", "team")
    cl = await db.clients.find_one(cq(user, {"id": data.client_id}), {"_id": 0})
    if not cl:
        raise HTTPException(status_code=404, detail="Client introuvable")
    doc = with_company({
        "id": str(uuid.uuid4()),
        "client_id": data.client_id,
        "technician_name": (data.technician_name or "").strip(),
        "scheduled_date": data.scheduled_date,
        "scheduled_time": (data.scheduled_time or "").strip(),
        "note": (data.note or "").strip(),
        "status": data.status or "a_faire",
        "photos": _validated_photo_entries(data.photos or []),
        "created_at": now_iso(),
        "created_by": user["id"],
    }, user)
    await db.reinterventions.insert_one(doc.copy())
    await log_audit(user, "create", "reintervention", doc["id"], after=doc)
    return doc


@api_router.put("/reinterventions/{rid}")
async def update_reintervention(rid: str, data: ReinterventionUpdate, user: dict = Depends(get_current_user)):
    check_perm(user, "planning", "edit", "team")
    before = await db.reinterventions.find_one(cq(user, {"id": rid}), {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Réintervention introuvable")
    patch = {k: v for k, v in data.model_dump().items() if v is not None}
    if "photos" in patch:
        patch["photos"] = _validated_photo_entries(patch["photos"])
    if patch:
        patch["updated_at"] = now_iso()
        await db.reinterventions.update_one(cq(user, {"id": rid}), {"$set": patch})
    after = await db.reinterventions.find_one(cq(user, {"id": rid}), {"_id": 0})
    await log_audit(user, "update", "reintervention", rid, before=before, after=after)
    return after


@api_router.delete("/reinterventions/{rid}")
async def delete_reintervention(rid: str, user: dict = Depends(get_current_user)):
    check_perm(user, "planning", "edit", "team")
    before = await db.reinterventions.find_one(cq(user, {"id": rid}), {"_id": 0})
    r = await db.reinterventions.delete_one(cq(user, {"id": rid}))
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Réintervention introuvable")
    await log_audit(user, "delete", "reintervention", rid, before=before)
    return {"ok": True}


# ---------------- Off-days (jours OFF / non travaillés) ----------------

class OffDayIn(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    scope: str = Field(pattern=r"^(company|person)$")
    person_names: Optional[List[Annotated[str, Field(max_length=120)]]] = Field(default=None, max_length=500)
    reason: Optional[str] = Field(default="", max_length=500)

    @field_validator("date")
    @classmethod
    def validate_off_day_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value


@api_router.get("/off-days")
async def list_off_days(user: dict = Depends(get_current_user), month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$")):
    q = cq(user)
    if month:
        q["date"] = {"$regex": f"^{_validated_month(month)}"}
    docs = await db.off_days.find(q, {"_id": 0}).sort("date", 1).to_list(2000)
    if user.get("role") in ("technicien", "sous_traitant"):
        return [{k: v for k, v in d.items() if k != "reason"} for d in docs if d.get("scope") == "company"]
    return docs


@api_router.post("/off-days")
async def create_off_day(data: OffDayIn, user: dict = Depends(get_current_user)):
    check_perm(user, "planning", "edit", "team")
    names = [n.strip() for n in (data.person_names or []) if n and str(n).strip()]
    if data.scope == "person" and not names:
        raise HTTPException(status_code=400, detail="Précisez au moins une personne pour un OFF individuel")
    # Upsert on (date, scope, names) — avoids duplicates when admin clicks twice
    existing = await db.off_days.find_one(cq(user, {"date": data.date, "scope": data.scope}), {"_id": 0})
    if existing and data.scope == "company":
        return existing
    doc = with_company({
        "id": str(uuid.uuid4()),
        "date": data.date,
        "scope": data.scope,
        "person_names": names if data.scope == "person" else [],
        "reason": (data.reason or "").strip(),
        "created_at": now_iso(),
        "created_by": user["id"],
    }, user)
    await db.off_days.insert_one(doc.copy())
    await log_audit(user, "create", "off_day", doc["id"], after=doc)
    return doc


@api_router.delete("/off-days/{oid}")
async def delete_off_day(oid: str, user: dict = Depends(get_current_user)):
    check_perm(user, "planning", "edit", "team")
    before = await db.off_days.find_one(cq(user, {"id": oid}), {"_id": 0})
    r = await db.off_days.delete_one(cq(user, {"id": oid}))
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Jour OFF introuvable")
    await log_audit(user, "delete", "off_day", oid, before=before)
    return {"ok": True}


# ---------------- Events (événements planning) ----------------

class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: Optional[str] = None      # "HH:MM"
    end_time: Optional[str] = None
    description: Optional[str] = Field(default="", max_length=5000)
    all_company: bool = False
    participants: Optional[List[str]] = Field(default=None, max_length=500)      # user ids
    show_on_dashboard: bool = False
    send_notification: bool = False

    @field_validator("date")
    @classmethod
    def validate_event_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_event_time(cls, value: Optional[str]) -> Optional[str]:
        if value:
            datetime.strptime(value, "%H:%M")
        return value

    @model_validator(mode="after")
    def validate_event_range(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("L'heure de fin doit être postérieure à l'heure de début")
        return self


class EventUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=5000)
    all_company: Optional[bool] = None
    participants: Optional[List[str]] = Field(default=None, max_length=500)
    show_on_dashboard: Optional[bool] = None
    send_notification: Optional[bool] = None

    @field_validator("date")
    @classmethod
    def validate_event_date(cls, value: Optional[str]) -> Optional[str]:
        if value:
            date.fromisoformat(value)
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_event_time(cls, value: Optional[str]) -> Optional[str]:
        if value:
            datetime.strptime(value, "%H:%M")
        return value

    @model_validator(mode="after")
    def validate_event_range(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("L'heure de fin doit être postérieure à l'heure de début")
        return self


async def _event_recipient_ids(user: dict, all_company: bool, participants: Optional[List[str]]) -> List[str]:
    if all_company:
        rows = await db.users.find(
            {"company_id": company_id_of(user)}, {"_id": 0, "id": 1}
        ).to_list(2000)
        return [r["id"] for r in rows]
    requested = list(dict.fromkeys(str(x).strip() for x in (participants or []) if str(x).strip()))
    if any(len(uid) > 128 for uid in requested):
        raise HTTPException(status_code=400, detail="Identifiant de participant invalide")
    if not requested:
        return []
    rows = await db.users.find(
        {"company_id": company_id_of(user), "id": {"$in": requested}},
        {"_id": 0, "id": 1},
    ).to_list(len(requested))
    valid = {r["id"] for r in rows}
    if len(valid) != len(requested):
        raise HTTPException(status_code=400, detail="Un ou plusieurs participants sont invalides")
    return [uid for uid in requested if uid in valid]


def _event_visible_to(u: dict, ev: dict) -> bool:
    if ev.get("all_company"):
        return True
    return u["id"] in (ev.get("participants") or [])


@api_router.get("/events")
async def list_events(user: dict = Depends(get_current_user), month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"), upcoming: bool = False):
    q = cq(user)
    if month:
        q["date"] = {"$regex": f"^{_validated_month(month)}"}
    elif upcoming:
        q["date"] = {"$gte": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    docs = await db.events.find(q, {"_id": 0}).sort("date", 1).to_list(2000)
    # Filter to events the user can see (admin/responsable always see all, others only theirs)
    if user.get("role") not in ("admin", "responsable", "super_admin"):
        docs = [d for d in docs if _event_visible_to(user, d)]
    return docs


@api_router.post("/events")
async def create_event(data: EventIn, user: dict = Depends(get_current_user)):
    check_perm(user, "planning", "edit", "team")
    recipients = await _event_recipient_ids(user, data.all_company, data.participants)
    doc = with_company({
        "id": str(uuid.uuid4()),
        "title": data.title.strip(),
        "date": data.date,
        "start_time": (data.start_time or None),
        "end_time": (data.end_time or None),
        "description": (data.description or "").strip(),
        "all_company": bool(data.all_company),
        "participants": recipients,
        "show_on_dashboard": bool(data.show_on_dashboard),
        "created_by": user["id"],
        "created_at": now_iso(),
    }, user)
    await db.events.insert_one(doc.copy())
    await log_audit(user, "create", "event", doc["id"], after=doc)
    if data.send_notification and recipients:
        when = data.date + (f" à {data.start_time}" if data.start_time else "")
        await emit_notification_to_users(
            company_id_of(user), recipients,
            title=f"Événement : {doc['title']}",
            message=when + (f" — {doc['description']}" if doc["description"] else ""),
            link_url="/planning",
        )
    return doc


@api_router.put("/events/{eid}")
async def update_event(eid: str, data: EventUpdate, user: dict = Depends(get_current_user)):
    check_perm(user, "planning", "edit", "team")
    before = await db.events.find_one(cq(user, {"id": eid}), {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Événement introuvable")
    updates = {k: v for k, v in data.model_dump().items() if v is not None and k != "send_notification"}
    # If participants list changed OR all_company toggled, recompute recipients
    if "all_company" in updates or "participants" in updates:
        all_c = updates.get("all_company", before.get("all_company", False))
        parts = updates.get("participants", before.get("participants", []))
        updates["participants"] = await _event_recipient_ids(user, all_c, parts)
    updates["updated_at"] = now_iso()
    await db.events.update_one(cq(user, {"id": eid}), {"$set": updates})
    after = await db.events.find_one(cq(user, {"id": eid}), {"_id": 0})
    await log_audit(user, "update", "event", eid, before=before, after=after)
    if data.send_notification and after:
        when = after["date"] + (f" à {after['start_time']}" if after.get("start_time") else "")
        await emit_notification_to_users(
            company_id_of(user), after.get("participants", []),
            title=f"Événement mis à jour : {after['title']}",
            message=when + (f" — {after.get('description') or ''}"),
            link_url="/planning",
        )
    return after


@api_router.delete("/events/{eid}")
async def delete_event(eid: str, user: dict = Depends(get_current_user), notify: bool = False):
    check_perm(user, "planning", "edit", "team")
    before = await db.events.find_one(cq(user, {"id": eid}), {"_id": 0})
    r = await db.events.delete_one(cq(user, {"id": eid}))
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Événement introuvable")
    await log_audit(user, "delete", "event", eid, before=before)
    if notify and before and before.get("participants"):
        await emit_notification_to_users(
            company_id_of(user), before["participants"],
            title=f"Événement annulé : {before.get('title')}",
            message=f"Prévu le {before.get('date')}",
            link_url="/planning",
        )
    return {"ok": True}


# ---------------- Stock / Inventaire (iter32) ----------------
# Company-scoped stock ledger. Auto-aggregated needs come from ACTIVE projects
# (status ∈ {a_planifier, en_cours}). Terminé/annulé excluded by design.

class StockUpsert(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    stock_disponible: Optional[int] = Field(default=None, ge=0, le=100000)
    commande_en_cours: Optional[int] = Field(default=None, ge=0, le=100000)
    # iter75 : seuil d'alerte stock bas — configurable par produit (défaut 2, désactivable via 0)
    low_stock_threshold: Optional[int] = Field(default=None, ge=0, le=100000)

class StockReceive(BaseModel):
    quantity: Optional[int] = Field(default=None, ge=1, le=100000, description="Quantité reçue; défaut = commande_en_cours")


class StockRenameIn(BaseModel):
    # iter207 : rename d'un produit du stock. Techniciens autorisés SEULEMENT
    # sur les produits qu'ils ont créés (created_by_technician + created_by == uid).
    product_name: str = Field(min_length=1, max_length=200)


class StockOverrideIn(BaseModel):
    # iter65 : override manuel d'une valeur auto-calculée (besoin / stock_previsionnel / reste_a_commander)
    field: str = Field(pattern=r"^(besoin|stock_previsionnel|reste_a_commander)$")
    value: int = Field(ge=-100000, le=100000)


def _norm_product_key(name: str) -> str:
    import unicodedata as _ud
    s = _ud.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def _stock_rbac_check(user: dict):
    """iter68 : accès au stock piloté par la permission stock.view.
    Peu importe le rôle : si stock.view est True → OK, sinon 403.
    Modification (POST/PUT/DELETE + transferts sur autres emplacements) réservée aux managers
    ou aux techniciens ayant stock.edit=True (rare)."""
    if is_super_admin(user):
        return
    if not has_perm(user, "stock", "view"):
        raise HTTPException(status_code=403, detail="Accès refusé (rubrique Stock désactivée pour ce compte)")


def _stock_is_manager(user: dict) -> bool:
    return (user or {}).get("role") in ("admin", "responsable", "super_admin")


def _stock_can_edit(user: dict) -> bool:
    """iter68 : autorise l'édition si manager OU si stock.edit=True."""
    if _stock_is_manager(user):
        return True
    return bool(has_perm(user, "stock", "edit"))


class StockHolderIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    name: Optional[str] = Field(default=None, max_length=120)
    quantity: int = Field(ge=0, le=100000)


class StockTransferIn(BaseModel):
    from_user_id: Optional[str] = Field(default=None, min_length=1, max_length=128)  # None = dépôt société
    to_user_id: Optional[str] = Field(default=None, min_length=1, max_length=128)    # None = dépôt société
    quantity: int = Field(ge=1, le=100000)


class StockAdjustIn(BaseModel):
    delta: int = Field(ge=-10_000, le=10_000)  # +N entrée, -N sortie (technicien sur son propre stock)
    project_id: Optional[str] = Field(default=None, max_length=128)
    note: Optional[str] = Field(default="", max_length=1000)


def _holders_total(holders: list) -> int:
    return sum(int(h.get("qty") or 0) for h in (holders or []))


def _holder_get(holders: list, user_id: str) -> Optional[dict]:
    for h in (holders or []):
        if h.get("user_id") == user_id:
            return h
    return None


async def _stock_compare_and_set(sid: str, user: dict, mutate, *, attempts: int = 5):
    """Retry a stock mutation when another worker changed the row meanwhile.

    Legacy rows have no `_rev`; the first successful mutation creates it. The
    revision predicate makes the read/compute/write sequence safe across
    processes without requiring a multi-document transaction.
    """
    for _ in range(attempts):
        row = await db.stock.find_one(cq(user, {"id": sid}), {"_id": 0})
        if not row:
            raise HTTPException(status_code=404, detail="Ligne stock introuvable")
        updates, context = mutate(row)
        revision = row.get("_rev")
        query = cq(user, {"id": sid})
        query["_rev"] = revision if revision is not None else {"$exists": False}
        result = await db.stock.update_one(
            query,
            {"$set": updates, "$inc": {"_rev": 1}},
        )
        if result.modified_count == 1:
            updated = await db.stock.find_one(cq(user, {"id": sid}), {"_id": 0})
            return updated, context, row
    raise HTTPException(status_code=409, detail="Stock modifié simultanément — recommencez l'opération")


def _log_movement(company_id: str, product_key: str, product_name: str,
                  actor: dict, action: str, delta: int,
                  from_user_id: Optional[str], to_user_id: Optional[str],
                  project_id: Optional[str] = None, note: str = ""):
    return {
        "id": str(uuid.uuid4()),
        "company_id": company_id,
        "product_key": product_key,
        "product_name": product_name,
        "action": action,   # in / out / transfer / set / adjust
        "delta": int(delta),
        "from_user_id": from_user_id,
        "to_user_id": to_user_id,
        "by_user_id": actor.get("id"),
        "by_user_name": actor.get("name") or actor.get("email") or "?",
        "project_id": project_id,
        "note": (note or "").strip(),
        "at": now_iso(),
    }


@api_router.get("/stock/catalog")
async def stock_catalog(user: dict = Depends(get_current_user)):
    """iter89 : liste allégée id+product_name du catalogue Stock — accessible à tout user avec stock.view.
    Utilisée par le technicien pour ajouter un produit à son stock personnel."""
    _stock_rbac_check(user)
    rows = await db.stock.find(cq(user), {"_id": 0, "id": 1, "product_name": 1}).sort("product_name", 1).to_list(2000)
    return [{"id": r.get("id"), "product_name": r.get("product_name") or ""} for r in rows if r.get("id")]


@api_router.get("/stock")
async def list_stock(
    from_date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    until: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user: dict = Depends(get_current_user),
):
    # iter68 : accès piloté par permission stock.view (indépendant des Ventes / du rôle).
    _stock_rbac_check(user)
    # 1) Aggregate needs from active projects (a_planifier, en_cours). Fallback: sales when no prestations on project yet.
    # iter58 : filtre de date sur scheduled_date (from_date <= sched <= until) — optionnel
    needs: dict = {}  # key -> {name, qty}
    proj_q = cq(user, {"status": {"$in": ["a_planifier", "en_cours"]}, "cancelled": {"$ne": True}})
    if from_date or until:
        date_q: dict = {}
        if from_date: date_q["$gte"] = from_date
        if until: date_q["$lte"] = until
        proj_q["scheduled_date"] = date_q
    async for p in db.projects.find(proj_q, {"_id": 0, "prestations": 1, "sale_id": 1}):
        prestas = p.get("prestations") or []
        if not prestas and p.get("sale_id"):
            s = await db.sales.find_one(cq(user, {"id": p["sale_id"]}), {"_id": 0, "prestations": 1, "status": 1})
            if s and s.get("status") not in ("annule", "litige"):
                prestas = s.get("prestations") or []
        for it in prestas:
            name = (it.get("name") or "").strip()
            qty = max(0, int(it.get("quantity") or 0))
            if not name or qty <= 0:
                continue
            k = _norm_product_key(name)
            if k not in needs:
                needs[k] = {"name": name, "qty": 0}
            needs[k]["qty"] += qty

    # 2) Load stock rows for this company
    rows = await db.stock.find(cq(user), {"_id": 0}).to_list(2000)
    by_key = {r.get("product_key"): r for r in rows if r.get("product_key")}

    # iter57 : "géré en stock = existe dans le catalogue Stock". On ne compte donc
    # comme besoin QUE les prestations dont le produit a été créé explicitement.
    # Les autres (sous-traitance, achat direct fournisseur, prestations pures) n'apparaissent plus.
    needs = {k: v for k, v in needs.items() if k in by_key}

    # 3) Merge: every stock row + every need key
    merged: dict = {}
    for k, r in by_key.items():
        merged[k] = {
            "id": r.get("id"),
            "product_name": r.get("product_name") or "",
            "product_key": k,
            "besoin": 0,
            "stock_disponible": int(r.get("stock_disponible") or 0),
            "commande_en_cours": int(r.get("commande_en_cours") or 0),
            # iter57 : liste des emplacements (techniciens / dépôt) qui détiennent ce produit
            "holders": list(r.get("holders") or []),
            # iter65 : overrides manuels stockés sur la ligne
            "manual_overrides": dict(r.get("manual_overrides") or {}),
            # iter75 : seuil d'alerte configurable par produit (défaut 2, 0 = alerte désactivée)
            "low_stock_threshold": int(r.get("low_stock_threshold") if r.get("low_stock_threshold") is not None else 2),
        }
    for k, n in needs.items():
        if k in merged:
            merged[k]["besoin"] = n["qty"]
            # Ensure display name reflects the latest sale wording if stock row was blank
            if not merged[k]["product_name"]:
                merged[k]["product_name"] = n["name"]
        else:
            merged[k] = {
                "id": None,
                "product_name": n["name"],
                "product_key": k,
                "besoin": n["qty"],
                "stock_disponible": 0,
                "commande_en_cours": 0,
                "holders": [],
                "manual_overrides": {},
            }

    # 4) Compute reste_a_commander + stock_previsionnel + status color for the dashboard
    # iter65 : les overrides manuels remplacent les valeurs auto-calculées (besoin / prévisionnel / à commander).
    out = []
    for k, m in merged.items():
        overrides = m.get("manual_overrides") or {}
        besoin_auto = m["besoin"]
        reste_auto = max(0, besoin_auto - m["stock_disponible"] - m["commande_en_cours"])
        prev_auto = m["stock_disponible"] + m["commande_en_cours"] - besoin_auto

        # Apply overrides
        besoin_eff = int(overrides["besoin"]["value"]) if "besoin" in overrides else besoin_auto
        prev_eff = int(overrides["stock_previsionnel"]["value"]) if "stock_previsionnel" in overrides else prev_auto
        reste_eff = int(overrides["reste_a_commander"]["value"]) if "reste_a_commander" in overrides else reste_auto

        # Status derived from effective values (respect admin overrides)
        if reste_eff > 0:
            status = "red"
        elif m["commande_en_cours"] > 0 and m["stock_disponible"] < besoin_eff:
            status = "orange"
        else:
            status = "green"

        # iter75 : alerte stock bas — seuil configurable PAR PRODUIT (défaut 2). Seuil=0 → alerte désactivée.
        threshold = int(m.get("low_stock_threshold") if m.get("low_stock_threshold") is not None else 2)
        low_stock = threshold > 0 and 0 < int(m["stock_disponible"] or 0) <= threshold

        m["besoin"] = besoin_eff
        m["besoin_auto"] = besoin_auto
        m["stock_previsionnel"] = prev_eff
        m["stock_previsionnel_auto"] = prev_auto
        m["reste_a_commander"] = reste_eff
        m["reste_a_commander_auto"] = reste_auto
        m["status"] = status
        m["low_stock"] = low_stock
        m["low_stock_threshold"] = threshold
        out.append(m)
    # Sort: to-order first (red), then partially covered (orange), then green — by descending "reste" and name.
    weight = {"red": 0, "orange": 1, "green": 2}
    out.sort(key=lambda x: (weight.get(x["status"], 3), -x["reste_a_commander"], x["product_name"].lower()))

    # iter68 : Technicien → construction d'une réponse structurée en 3 sections (mine / others / company)
    # avec respect strict des permissions stock.view_own / stock.view_others / stock.view_company.
    # Les managers (admin/responsable) reçoivent toujours la liste plate historique.
    if (user or {}).get("role") == "technicien" and not _stock_is_manager(user):
        my_id = user["id"]
        can_own = bool(has_perm(user, "stock", "view_own"))
        can_others = bool(has_perm(user, "stock", "view_others"))
        can_company = bool(has_perm(user, "stock", "view_company"))
        # id → nom des techniciens (pour libeller la section "autres")
        tech_users = await db.users.find(cq(user, {"role": "technicien"}), {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(500)
        name_by_id = {u["id"]: (u.get("name") or u.get("email") or "?") for u in tech_users}

        mine_rows: list = []
        others_map: dict = {}  # user_id → {user_id, name, rows: [{product_name, product_key, qty}]}
        company_rows: list = []

        for row in out:
            holders = row.get("holders") or []
            # iter72 : correction — le stock société (`stock_disponible`) est déjà le dépôt physique
            # POST-transfert. Les holders sont comptés séparément. Ne PAS re-soustraire les holders.
            # Source unique : la même que l'admin lit sur cette même ligne db.stock.
            company_qty = int(row.get("stock_disponible") or 0)

            # Section 1 : mon stock
            if can_own:
                mine = _holder_get(holders, my_id)
                qty_own = int(mine.get("qty") or 0) if mine else 0
                if qty_own > 0 or row.get("besoin", 0) > 0:
                    mine_rows.append({
                        "id": row.get("id"),
                        "product_name": row.get("product_name"),
                        "product_key": row.get("product_key"),
                        "qty": qty_own,
                        "besoin": row.get("besoin", 0),
                        # iter207 : flag utilisé par le front pour autoriser
                        # le renommage inline uniquement sur les produits que le
                        # technicien a lui-même créés.
                        "created_by_technician_by_me": bool(
                            row.get("created_by_technician") and row.get("created_by") == my_id
                        ),
                    })

            # Section 2 : stocks des autres techniciens
            if can_others:
                for h in holders:
                    uid = h.get("user_id")
                    if not uid or uid == my_id:
                        continue
                    qty = int(h.get("qty") or 0)
                    if qty <= 0:
                        continue
                    if uid not in others_map:
                        others_map[uid] = {
                            "user_id": uid,
                            "name": h.get("name") or name_by_id.get(uid) or "Technicien",
                            "rows": [],
                        }
                    others_map[uid]["rows"].append({
                        "product_name": row.get("product_name"),
                        "product_key": row.get("product_key"),
                        "qty": qty,
                    })

            # Section 3 : stock société — MÊMES RÉFÉRENCES et MÊMES QUANTITÉS que la vue admin.
            # iter72 : on affiche TOUS les produits du catalogue (comme l'admin), pas de filtrage 0.
            if can_company and row.get("id"):
                company_rows.append({
                    "id": row.get("id"),
                    "product_name": row.get("product_name"),
                    "product_key": row.get("product_key"),
                    "qty": company_qty,
                    "commande_en_cours": row.get("commande_en_cours", 0),
                    "besoin": row.get("besoin", 0),
                    "status": row.get("status"),
                    "low_stock": row.get("low_stock", False),  # iter75 : alerte stock bas
                })

        # Tri lisible par nom de produit
        mine_rows.sort(key=lambda x: (x.get("product_name") or "").lower())
        company_rows.sort(key=lambda x: (x.get("product_name") or "").lower())
        others = list(others_map.values())
        others.sort(key=lambda x: (x.get("name") or "").lower())
        for o in others:
            o["rows"].sort(key=lambda x: (x.get("product_name") or "").lower())

        return {
            "mode": "technicien",
            "can_view_own": can_own,
            "can_view_others": can_others,
            "can_view_company": can_company,
            "can_edit": _stock_can_edit(user),
            "sections": {
                "mine": mine_rows,
                "others": others,
                "company": company_rows,
            },
        }
    return out


@api_router.get("/stock/product/{product_key}/projects")
async def stock_product_projects(product_key: str, user: dict = Depends(get_current_user)):
    """iter49 : détail des chantiers actifs qui consomment ce produit (drill-down UI).
    Renvoie une liste avec client, commercial, techniciens, montant, date, statut, quantité."""
    _stock_rbac_check(user)
    key = _norm_product_key(product_key)
    # Chantiers actifs uniquement : a_planifier + en_cours (terminés / cancelled exclus)
    q = cq(user, {"status": {"$in": ["a_planifier", "en_cours"]}, "cancelled": {"$ne": True}})
    projects = await db.projects.find(q, {"_id": 0}).to_list(5000)
    if not projects:
        return {"product_key": key, "projects": []}

    sale_ids = list({p.get("sale_id") for p in projects if p.get("sale_id")})
    sales_map: dict = {}
    if sale_ids:
        srows = await db.sales.find(cq(user, {"id": {"$in": sale_ids}}), {"_id": 0}).to_list(len(sale_ids))
        sales_map = {r["id"]: r for r in srows}
    client_ids = list({p.get("client_id") for p in projects if p.get("client_id")})
    clients_map: dict = {}
    if client_ids:
        crows = await db.clients.find(cq(user, {"id": {"$in": client_ids}}), {"_id": 0}).to_list(len(client_ids))
        clients_map = {r["id"]: r for r in crows}

    results: list = []
    for p in projects:
        s = sales_map.get(p.get("sale_id")) or {}
        # Exclut les ventes annulées/litigieuses (protection double couche)
        if s.get("status") in ("annule", "litige", "argent_recupere"):
            continue
        prestas = p.get("prestations") or s.get("prestations") or []
        qty = 0
        for it in prestas:
            if _norm_product_key(it.get("name") or "") == key:
                qty += max(0, int(it.get("quantity") or 0))
        if qty <= 0:
            continue
        c = clients_map.get(p.get("client_id")) or {}
        techs = p.get("assigned_to") or []
        if isinstance(techs, str):
            techs = [techs] if techs else []
        results.append({
            "project_id": p["id"],
            "sale_id": p.get("sale_id"),
            "client_name": p.get("client_name") or c.get("name") or "—",
            "commercial": s.get("commercial") or p.get("commercial") or "",
            "commercial_2": s.get("commercial_2") if s.get("is_de") else None,
            "techniciens": techs,
            "service": p.get("service") or s.get("service") or "",
            "amount": float(s.get("amount") or 0),
            "scheduled_date": p.get("scheduled_date"),
            "duration_days": max(1, int(p.get("duration_days") or 1)),
            "status": p.get("status"),
            "quantity": qty,
        })
    # Chantiers non planifiés (scheduled_date=None) en fin de liste, sinon tri par date croissante
    results.sort(key=lambda r: (r["scheduled_date"] or "9999-99-99", r["client_name"]))
    total = sum(r["quantity"] for r in results)
    return {"product_key": key, "total_needed": total, "projects": results}


class TechStockCreateIn(BaseModel):
    product_name: str = Field(min_length=1, max_length=120)
    qty: int = Field(ge=1, le=100000)


@api_router.post("/stock/tech-create-and-hold")
async def tech_create_and_hold(data: TechStockCreateIn, user: dict = Depends(get_current_user)):
    """iter127 : un technicien peut créer un produit qui n'existe pas dans le catalogue
    et immédiatement l'ajouter à SON stock personnel. Si le product_key correspond à
    un produit déjà existant, on fait juste un holder-adjust (pas de doublon).
    Le stock société (dépôt) reste à 0 — l'admin peut valider ensuite si besoin."""
    if (user or {}).get("role") != "technicien":
        raise HTTPException(status_code=403, detail="Réservé technicien")
    name = data.product_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom produit requis")
    key = _norm_product_key(name)
    qty = int(data.qty)
    now = now_iso()
    existing = await db.stock.find_one(cq(user, {"product_key": key}), {"_id": 0})
    if existing:
        sid = existing["id"]
    else:
        sid = str(uuid.uuid4())
        doc = with_company({
            "id": sid,
            "product_name": name,
            "product_key": key,
            "stock_disponible": 0,
            "commande_en_cours": 0,
            "created_by": user["id"],
            "created_at": now,
            "updated_at": now,
            "created_by_technician": True,
            "_rev": 0,
        }, user)
        try:
            await db.stock.insert_one(doc.copy())
            mv = _log_movement(company_id_of(user), key, name, user, "tech_create", 0, None, None, None, "Produit créé par technicien")
            await db.stock_movements.insert_one(mv.copy())
        except DuplicateKeyError:
            # Another worker created the same normalized product between our
            # lookup and insert. Continue on that canonical row.
            existing = await db.stock.find_one(cq(user, {"product_key": key}), {"_id": 0})
            if not existing:
                raise
            sid = existing["id"]
    my_uid = user["id"]
    my_name = user.get("name") or user.get("email") or "Technicien"

    def mutate(row):
        holders = [dict(h) for h in (row.get("holders") or [])]
        for holder in holders:
            if holder.get("user_id") == my_uid:
                holder["qty"] = int(holder.get("qty") or 0) + qty
                holder["name"] = holder.get("name") or my_name
                break
        else:
            holders.append({"user_id": my_uid, "name": my_name, "qty": qty})
        return ({"holders": holders, "updated_at": now_iso(), "updated_by": my_uid}, {})

    updated, _, _ = await _stock_compare_and_set(sid, user, mutate)
    mv = _log_movement(company_id_of(user), key, name, user, "adjust", qty, None, my_uid, None, "Ajout technicien")
    await db.stock_movements.insert_one(mv.copy())
    await log_audit(user, "tech_create_and_hold", "stock", sid, after={"product_name": name, "qty": qty})
    return updated


@api_router.post("/stock")
async def upsert_stock(data: StockUpsert, user: dict = Depends(get_current_user)):
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    name = data.product_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom produit requis")
    key = _norm_product_key(name)
    existing = await db.stock.find_one(cq(user, {"product_key": key}), {"_id": 0})
    now = now_iso()
    updates = {"product_name": name, "product_key": key, "updated_at": now, "updated_by": user["id"]}
    if data.stock_disponible is not None:
        updates["stock_disponible"] = int(data.stock_disponible)
    if data.commande_en_cours is not None:
        updates["commande_en_cours"] = int(data.commande_en_cours)
    # iter75 : seuil d'alerte par produit — 0 = désactive l'alerte pour ce produit
    if getattr(data, "low_stock_threshold", None) is not None:
        updates["low_stock_threshold"] = max(0, int(data.low_stock_threshold))
    if existing:
        await db.stock.update_one(cq(user, {"id": existing["id"]}), {"$set": updates, "$inc": {"_rev": 1}})
        return await db.stock.find_one(cq(user, {"id": existing["id"]}), {"_id": 0})
    doc = with_company({
        "id": str(uuid.uuid4()),
        "product_name": name,
        "product_key": key,
        "stock_disponible": int(data.stock_disponible or 0),
        "commande_en_cours": int(data.commande_en_cours or 0),
        "created_by": user["id"],
        "created_at": now,
        "updated_at": now,
        "_rev": 0,
    }, user)
    try:
        await db.stock.insert_one(doc.copy())
    except DuplicateKeyError:
        # A concurrent request created the normalized product first. Apply this
        # request to that canonical row instead of returning a server error.
        existing = await db.stock.find_one(cq(user, {"product_key": key}), {"_id": 0})
        if not existing:
            raise
        await db.stock.update_one(
            cq(user, {"id": existing["id"]}),
            {"$set": updates, "$inc": {"_rev": 1}},
        )
        return await db.stock.find_one(cq(user, {"id": existing["id"]}), {"_id": 0})
    return doc


@api_router.put("/stock/{sid}/rename")
async def rename_stock_product(sid: str, data: StockRenameIn, user: dict = Depends(get_current_user)):
    """iter207 : renomme un produit du stock.
    Autorisation :
      - Manager (admin/responsable/super_admin) : tout produit.
      - Technicien / sous-traitant : uniquement un produit qu'il a lui-même créé
        (`created_by_technician=True` et `created_by == user.id`).
    Effet : met à jour `product_name` + `product_key`. Refuse la collision.
    """
    row = await db.stock.find_one(cq(user, {"id": sid}), {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Ligne stock introuvable")
    if not _is_manager(user):
        if user.get("role") not in ("technicien", "sous_traitant"):
            raise HTTPException(status_code=403, detail="Accès refusé")
        if not (row.get("created_by_technician") and row.get("created_by") == user.get("id")):
            raise HTTPException(status_code=403, detail="Vous ne pouvez renommer qu'un produit que vous avez créé.")
    new_name = data.product_name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Nom produit requis")
    new_key = _norm_product_key(new_name)
    dupe = await db.stock.find_one(cq(user, {"product_key": new_key, "id": {"$ne": sid}}), {"_id": 0, "id": 1})
    if dupe:
        raise HTTPException(status_code=409, detail="Un autre produit porte déjà ce nom (normalisé).")
    now = now_iso()
    try:
        await db.stock.update_one(
            cq(user, {"id": sid}),
            {"$set": {"product_name": new_name, "product_key": new_key,
                      "updated_at": now, "updated_by": user["id"]}, "$inc": {"_rev": 1}},
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Un autre produit porte déjà ce nom (normalisé).")
    try:
        mv = _log_movement(company_id_of(user), new_key, new_name, user, "rename", 0, None, None, None,
                           f"Renommage : « {row.get('product_name')} » → « {new_name} »")
        await db.stock_movements.insert_one(mv.copy())
    except Exception:
        logger.exception("Échec de la journalisation du renommage de stock")
    await log_audit(user, "stock_rename", "stock", sid,
                    before={"product_name": row.get("product_name"), "product_key": row.get("product_key")},
                    after={"product_name": new_name, "product_key": new_key})
    return await db.stock.find_one(cq(user, {"id": sid}), {"_id": 0})


@api_router.put("/stock/{sid}/override")
async def set_stock_override(sid: str, data: StockOverrideIn, user: dict = Depends(get_current_user)):
    """iter65 : pose un override manuel sur un champ auto-calculé (besoin / stock_previsionnel / reste_a_commander).
    Admin/responsable uniquement. Trace l'auteur et la date pour affichage front."""
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    def mutate(row):
        overrides = dict(row.get("manual_overrides") or {})
        overrides[data.field] = {
            "value": int(data.value),
            "updated_by": user["id"],
            "updated_by_name": user.get("name") or user.get("email") or "?",
            "updated_at": now_iso(),
        }
        return ({"manual_overrides": overrides, "updated_at": now_iso(), "updated_by": user["id"]}, {})

    updated, _, _ = await _stock_compare_and_set(sid, user, mutate)
    await log_audit(user, "stock_override_set", "stock", sid, after={"field": data.field, "value": data.value})
    return updated


@api_router.delete("/stock/{sid}/override/{field}")
async def delete_stock_override(sid: str, field: str, user: dict = Depends(get_current_user)):
    """iter65 : revient au calcul automatique en supprimant l'override sur le champ donné."""
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    if field not in ("besoin", "stock_previsionnel", "reste_a_commander"):
        raise HTTPException(status_code=400, detail="Champ non supporté")
    def mutate(row):
        overrides = dict(row.get("manual_overrides") or {})
        overrides.pop(field, None)
        return ({"manual_overrides": overrides, "updated_at": now_iso(), "updated_by": user["id"]}, {})

    updated, _, _ = await _stock_compare_and_set(sid, user, mutate)
    await log_audit(user, "stock_override_clear", "stock", sid, after={"field": field})
    return updated


@api_router.post("/stock/{sid}/receive")
async def receive_stock(sid: str, data: StockReceive, user: dict = Depends(get_current_user)):
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")

    def mutate(row):
        on_order = int(row.get("commande_en_cours") or 0)
        qty = int(data.quantity) if data.quantity is not None else on_order
        if qty <= 0:
            raise HTTPException(status_code=400, detail="Aucune quantité à réceptionner")
        qty = min(qty, on_order) if on_order > 0 else qty
        return ({
            "stock_disponible": int(row.get("stock_disponible") or 0) + qty,
            "commande_en_cours": max(0, on_order - qty),
            "updated_at": now_iso(), "updated_by": user["id"],
        }, {"qty": qty})

    updated, _, _ = await _stock_compare_and_set(sid, user, mutate)
    return updated


@api_router.delete("/stock/{sid}")
async def delete_stock(sid: str, user: dict = Depends(get_current_user)):
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    r = await db.stock.delete_one(cq(user, {"id": sid}))
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Ligne stock introuvable")
    return {"ok": True}


# ============ iter57 : Stock multi-emplacements (holders) ============

@api_router.get("/stock/{sid}/holders")
async def list_stock_holders(sid: str, user: dict = Depends(get_current_user)):
    """Renvoie la liste détaillée des détenteurs pour un produit."""
    _stock_rbac_check(user)
    row = await db.stock.find_one(cq(user, {"id": sid}), {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Ligne stock introuvable")
    holders = row.get("holders") or []
    # Si technicien non-manager : ne renvoie que ses propres détentions
    if (user or {}).get("role") == "technicien" and not _stock_is_manager(user):
        holders = [h for h in holders if h.get("user_id") == user["id"]]
    return {"product_name": row.get("product_name"), "product_key": row.get("product_key"),
            "total": _holders_total(row.get("holders") or []), "holders": holders}


@api_router.post("/stock/{sid}/holder")
async def set_stock_holder(sid: str, data: StockHolderIn, user: dict = Depends(get_current_user)):
    """Admin/responsable : attribue une quantité précise à un détenteur (remplace).
    Cette valeur devient la nouvelle qty du user_id concerné."""
    if not _stock_is_manager(user):
        raise HTTPException(status_code=403, detail="Réservé admin/responsable")
    target = await db.users.find_one(
        {"company_id": company_id_of(user), "id": data.user_id},
        {"_id": 0, "id": 1, "name": 1, "email": 1},
    )
    if not target:
        raise HTTPException(status_code=400, detail="Détenteur invalide pour cette société")
    target_name = target.get("name") or target.get("email") or "?"

    def mutate(row):
        holders = [dict(h) for h in (row.get("holders") or [])]
        prev = 0
        for h in holders:
            if h.get("user_id") == data.user_id:
                prev = int(h.get("qty") or 0)
                h["qty"] = int(data.quantity)
                h["name"] = target_name
                break
        else:
            holders.append({"user_id": data.user_id, "name": target_name, "qty": int(data.quantity)})
        holders = [h for h in holders if int(h.get("qty") or 0) > 0]
        return ({"holders": holders, "updated_at": now_iso(), "updated_by": user["id"]}, {
            "delta": int(data.quantity) - prev,
        })

    updated, context, previous = await _stock_compare_and_set(sid, user, mutate)
    mv = _log_movement(company_id_of(user), previous.get("product_key"), previous.get("product_name") or "",
                       user, "set", context["delta"], None, data.user_id, None,
                       f"Attribution → {target_name}")
    await db.stock_movements.insert_one(mv.copy())
    await log_audit(user, "stock_set_holder", "stock", sid, after={"user_id": data.user_id, "qty": data.quantity})
    return updated


@api_router.post("/stock/{sid}/transfer")
async def transfer_stock(sid: str, data: StockTransferIn, user: dict = Depends(get_current_user)):
    """Transfert entre 2 détenteurs (user_id) OU depuis/vers le dépôt société (user_id=None).
    Le stock total reste identique. Manager only pour éviter les abus.
    Un technicien peut transférer DEPUIS son propre stock UNIQUEMENT."""
    role = (user or {}).get("role")
    if not _stock_is_manager(user):
        # Technicien : seule règle autorisée = from_user_id == self
        if role != "technicien" or data.from_user_id != user["id"]:
            raise HTTPException(status_code=403, detail="Vous ne pouvez transférer que depuis votre propre stock")
    if data.from_user_id == data.to_user_id:
        raise HTTPException(status_code=400, detail="Source et destination identiques")
    referenced_ids = list(dict.fromkeys(
        uid for uid in (data.from_user_id, data.to_user_id) if uid is not None
    ))
    company_users = await db.users.find(
        {"company_id": company_id_of(user), "id": {"$in": referenced_ids}},
        {"_id": 0, "id": 1, "name": 1, "email": 1},
    ).to_list(len(referenced_ids)) if referenced_ids else []
    users_by_id = {u["id"]: u for u in company_users}
    if len(users_by_id) != len(referenced_ids):
        raise HTTPException(status_code=400, detail="Source ou destination invalide pour cette société")
    qty = int(data.quantity)

    def mutate(row):
        holders = [dict(h) for h in (row.get("holders") or [])]
        stock_dispo = int(row.get("stock_disponible") or 0)

        def find_or_add(uid: Optional[str], name_hint: Optional[str] = None):
            if uid is None:
                return None
            for holder in holders:
                if holder.get("user_id") == uid:
                    return holder
            holder = {"user_id": uid, "name": name_hint or "?", "qty": 0}
            holders.append(holder)
            return holder

        if data.from_user_id is None:
            if stock_dispo < qty:
                raise HTTPException(status_code=400, detail=f"Stock société insuffisant ({stock_dispo} dispo)")
            stock_dispo -= qty
        else:
            src = find_or_add(data.from_user_id)
            if not src or int(src.get("qty") or 0) < qty:
                available = int(src.get("qty") or 0) if src else 0
                raise HTTPException(status_code=400, detail=f"Stock détenteur insuffisant ({available} dispo)")
            src["qty"] = int(src["qty"]) - qty
        if data.to_user_id is None:
            stock_dispo += qty
        else:
            target = users_by_id[data.to_user_id]
            target_name = target.get("name") or target.get("email") or "?"
            dst = find_or_add(data.to_user_id, target_name)
            dst["name"] = target_name
            dst["qty"] = int(dst.get("qty") or 0) + qty
        return ({
            "holders": [h for h in holders if int(h.get("qty") or 0) > 0],
            "stock_disponible": stock_dispo,
            "updated_at": now_iso(), "updated_by": user["id"],
        }, {})

    updated, _, previous = await _stock_compare_and_set(sid, user, mutate)
    mv = _log_movement(company_id_of(user), previous.get("product_key"), previous.get("product_name") or "",
                       user, "transfer", qty, data.from_user_id, data.to_user_id, None,
                       f"Transfert {qty} unités")
    await db.stock_movements.insert_one(mv.copy())
    await log_audit(user, "stock_transfer", "stock", sid,
                    after={"qty": qty, "from": data.from_user_id or "depot", "to": data.to_user_id or "depot"})
    return updated


@api_router.post("/stock/{sid}/holder-adjust")
async def adjust_holder_stock(sid: str, data: StockAdjustIn, user: dict = Depends(get_current_user)):
    """Un technicien déclare une entrée (+N) ou sortie (-N) sur SON propre stock.
    Sortie : utilisée sur chantier. Entrée : réception matériel."""
    _stock_rbac_check(user)
    def mutate(row):
        holders = [dict(h) for h in (row.get("holders") or [])]
        mine = next((h for h in holders if h.get("user_id") == user["id"]), None)
        if not mine:
            mine = {"user_id": user["id"], "name": user.get("name") or "?", "qty": 0}
            holders.append(mine)
        previous_qty = int(mine.get("qty") or 0)
        new_qty = previous_qty + int(data.delta)
        if new_qty < 0:
            raise HTTPException(status_code=400, detail=f"Stock insuffisant (vous avez {previous_qty})")
        mine["qty"] = new_qty
        return ({
            "holders": [h for h in holders if int(h.get("qty") or 0) > 0],
            "updated_at": now_iso(), "updated_by": user["id"],
        }, {})

    updated, _, previous = await _stock_compare_and_set(sid, user, mutate)
    action = "in" if data.delta > 0 else "out"
    mv = _log_movement(company_id_of(user), previous.get("product_key"), previous.get("product_name") or "",
                       user, action, data.delta,
                       user["id"] if data.delta < 0 else None,
                       user["id"] if data.delta > 0 else None,
                       data.project_id, data.note or "")
    await db.stock_movements.insert_one(mv.copy())
    await log_audit(user, f"stock_{action}", "stock", sid, after={"delta": data.delta, "project_id": data.project_id})
    return updated


@api_router.get("/stock/movements")
async def list_stock_movements(product_key: Optional[str] = Query(None, max_length=120),
                                limit: int = Query(100, ge=1, le=500),
                                user: dict = Depends(get_current_user)):
    """Historique des mouvements (RBAC : technicien voit uniquement les siens)."""
    _stock_rbac_check(user)
    q = cq(user)
    if product_key:
        q["product_key"] = _norm_product_key(product_key)
    if not _stock_is_manager(user):
        # Technicien : ses propres mouvements + ceux qui l'impliquent
        q["$or"] = [{"by_user_id": user["id"]}, {"from_user_id": user["id"]}, {"to_user_id": user["id"]}]
    rows = await db.stock_movements.find(q, {"_id": 0}).sort("at", -1).to_list(limit)
    return rows


# ---------------- User dashboard preferences (iter33) ----------------
# Per-user, per-company dashboard layout (order + hidden widgets). Stored in a
# dedicated `user_prefs` collection so it never touches shared settings.
# Widget keys must match those used by Dashboard.jsx.

DASHBOARD_WIDGET_KEYS = [
    # iter86 : ordre par défaut aligné sur DEFAULT_ORDER frontend (Théo-style)
    # → tout nouveau commercial voit le même dashboard dès son 1er login, sans étape de migration.
    # iter182 : `stats` est éclaté en deux widgets indépendants (`sales_count` + `today_todos`)
    # pour permettre à l'utilisateur de placer Ventes à côté de Heures sup, avec redimensionnement libre.
    "ca_hero", "activity", "sales_count", "today_todos", "overtime", "events",
    "alerts", "commissions",
    "ranking", "recent_sales",
    # Legacy — conservé pour ne pas casser les configs déjà persistées ; migré côté frontend.
    "stats",
]

# iter182 : tailles autorisées pour chaque bloc, en colonnes sur une grille de 12.
# 4 = 1/3, 6 = 1/2, 8 = 2/3, 12 = pleine largeur.
DASHBOARD_ALLOWED_SIZES = (4, 6, 8, 12)

class DashboardConfigIn(BaseModel):
    order: Optional[List[Annotated[str, Field(max_length=40)]]] = Field(default=None, max_length=50)
    hidden: Optional[List[Annotated[str, Field(max_length=40)]]] = Field(default=None, max_length=50)
    sizes: Optional[Dict[str, int]] = Field(default=None, max_length=50)


def _sanitize_dashboard_config(cfg: dict) -> dict:
    # iter200 — On DÉDUPLIQUE strictement `order` (bug Théo : plusieurs cartes
    # « À faire aujourd'hui » à cause d'un ordre corrompu contenant des doublons).
    raw_order = cfg.get("order") or []
    seen = set()
    order = []
    for w in raw_order:
        if w in DASHBOARD_WIDGET_KEYS and w not in seen:
            seen.add(w); order.append(w)
    # Append any missing widgets at the end so newly added blocks stay visible
    for w in DASHBOARD_WIDGET_KEYS:
        if w not in seen and w != "stats":  # `stats` reste opt-in (legacy)
            seen.add(w); order.append(w)
    hidden = list({w for w in (cfg.get("hidden") or []) if w in DASHBOARD_WIDGET_KEYS})
    # iter182 — sanitize sizes
    raw_sizes = cfg.get("sizes") or {}
    sizes: dict = {}
    if isinstance(raw_sizes, dict):
        for k, v in raw_sizes.items():
            if k in DASHBOARD_WIDGET_KEYS:
                try:
                    iv = int(v)
                    if iv in DASHBOARD_ALLOWED_SIZES:
                        sizes[k] = iv
                except (TypeError, ValueError):
                    pass
    return {"order": order, "hidden": hidden, "sizes": sizes}


@api_router.get("/me/dashboard-config")
async def get_my_dashboard_config(user: dict = Depends(get_current_user)):
    row = await db.user_prefs.find_one(
        {"user_id": user["id"], "company_id": company_id_of(user), "kind": "dashboard"},
        {"_id": 0},
    )
    cfg = row or {"order": DASHBOARD_WIDGET_KEYS, "hidden": [], "sizes": {}}
    return _sanitize_dashboard_config(cfg)


@api_router.put("/me/dashboard-config")
async def put_my_dashboard_config(data: DashboardConfigIn, user: dict = Depends(get_current_user)):
    cfg = _sanitize_dashboard_config(data.model_dump())
    await db.user_prefs.update_one(
        {"user_id": user["id"], "company_id": company_id_of(user), "kind": "dashboard"},
        {"$set": {**cfg, "updated_at": now_iso()}},
        upsert=True,
    )
    return cfg


@api_router.delete("/me/dashboard-config")
async def reset_my_dashboard_config(user: dict = Depends(get_current_user)):
    """Réinitialise la mise en page du tableau de bord (ordre + visibilité + tailles) — ne touche à aucune donnée métier."""
    await db.user_prefs.delete_one(
        {"user_id": user["id"], "company_id": company_id_of(user), "kind": "dashboard"},
    )
    return {"order": [w for w in DASHBOARD_WIDGET_KEYS if w != "stats"], "hidden": [], "sizes": {}}


# ---------------- Chantier terminé workflow (iter37) ----------------
# Le technicien assigné valide "Chantier terminé" (au moins 1 photo requise).
# → project.status = "termine" + completion metadata
# → sale.status = "chantier_fini" (sauf si déjà côté commercial workflow)
# → notification in-app + email au(x) commercial(aux) liés

class ProjectCompleteIn(BaseModel):
    photos: List[Any] = Field(min_length=1, max_length=MAX_PHOTOS_PER_ENTITY, description="Au moins une photo requise")
    note: Optional[str] = Field(default="", max_length=2000)
    day: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


def _project_days(project: dict) -> List[str]:
    days = []
    sd = (project.get("scheduled_date") or "")[:10]
    try:
        start = datetime.strptime(sd, "%Y-%m-%d").date()
        for i in range(max(1, int(project.get("duration_days") or 1))):
            days.append((start + timedelta(days=i)).isoformat())
    except ValueError:
        pass
    for d in project.get("extra_dates") or []:
        if isinstance(d, str) and len(d) >= 10 and d[:10] not in days:
            days.append(d[:10])
    return sorted(days)


@api_router.post("/projects/{pid}/complete")
async def complete_project(pid: str, data: ProjectCompleteIn, user: dict = Depends(get_current_user)):
    project = await db.projects.find_one(cq(user, {"id": pid}), {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    role = (user or {}).get("role") or ""
    assigned = project.get("assigned_to") or []
    if isinstance(assigned, str):
        assigned = [assigned]
    # iter206 : matching FUZZY (accent-insensible + tokens partagés) au lieu de
    # `.strip().lower()` strict. Résout le cas où user.name = « Sébastien Martin »
    # et assigned_to = « Sébastien » (ou variantes d'accent).
    if role in ("technicien", "sous_traitant"):
        matched = await _resolve_matched_assigned_names(user, project)
        if not matched:
            raise HTTPException(status_code=403, detail="Vous n'êtes pas assigné à ce chantier")
    elif role not in ("admin", "responsable", "super_admin"):
        raise HTTPException(status_code=403, detail="Accès refusé")
    else:
        await _ensure_project_scope(user, project)

    if not data.photos:
        raise HTTPException(status_code=400, detail="Au moins une photo est requise")

    submitted_photos = _validated_photo_entries(data.photos)

    now = now_iso()
    existing_photos = list(project.get("photos") or [])
    # iter156 : dédoublonnage par `src` pour éviter les copies (le frontend envoie
    # parfois toutes les photos courantes ; sans dédup, elles étaient ajoutées à
    # la suite → doublons systématiques sur la fiche chantier).
    existing_srcs = { (p.get("src") if isinstance(p, dict) else p) for p in existing_photos if p }
    new_photos = []
    for p in submitted_photos:
        src = p if isinstance(p, str) else (p.get("src") if isinstance(p, dict) else None)
        if not src or src in existing_srcs:
            continue
        existing_srcs.add(src)
        if isinstance(p, str):
            new_photos.append({"src": p, "taken_at": now, "by_completion": True})
        else:
            new_photos.append({**p, "taken_at": p.get("taken_at") or now, "by_completion": True})
    # Pas d'erreur si aucune nouvelle photo : le technicien peut valider avec les
    # photos déjà présentes (le contrôle "au moins 1 photo" reste basé sur la totalité).
    all_photos = existing_photos + new_photos
    if not all_photos:
        raise HTTPException(status_code=400, detail="Au moins une photo est requise")

    completion = {
        "completed_at": now,
        "completed_by": user.get("name") or user.get("email") or "?",
        "completed_by_id": user.get("id"),
        "note": (data.note or "").strip(),
        "photo_count": len(new_photos),
    }
    # Chantier multi-jours : chaque journée se valide séparément ; statut global « termine » seulement quand toutes le sont
    extra_set = {}
    pdays = _project_days(project)
    today_paris = datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
    if len(pdays) == 1 and pdays[0] > today_paris:
        raise HTTPException(status_code=400, detail="Impossible de valider une intervention qui n'a pas encore eu lieu")
    if len(pdays) > 1:
        day = data.day
        if not day or day not in pdays:
            raise HTTPException(status_code=400, detail="Choisissez la journée d'intervention à valider")
        if day > today_paris:
            raise HTTPException(status_code=400, detail="Impossible de valider une intervention qui n'a pas encore eu lieu")
        days_done = dict(project.get("days_done") or {})
        days_done[day] = {**completion, "day": day}
        remaining = [d for d in pdays if d not in days_done]
        if remaining:
            await db.projects.update_one(cq(user, {"id": pid}), {"$set": {"photos": all_photos, "days_done": days_done}})
            return {"ok": True, "partial": True, "day": day, "remaining": remaining, "days_done": list(days_done.keys()), "notified": 0}
        extra_set["days_done"] = days_done
    await db.projects.update_one(
        cq(user, {"id": pid}),
        {"$set": {"status": "termine", "photos": all_photos, "completion": completion, **extra_set}},
    )
    # iter159 : email au commercial quand le chantier passe en "À encaisser" (termine)
    try:
        _p_after = await db.projects.find_one(cq(user, {"id": pid}), {"_id": 0})
        if _p_after:
            await _notify_project(user, _p_after, "terminated")
    except Exception:
        logger.exception("Échec de la notification de fin de chantier")

    sale = None
    client = {}
    commercial_users: List[dict] = []
    if project.get("sale_id"):
        sale = await db.sales.find_one(cq(user, {"id": project["sale_id"]}), {"_id": 0})
        if sale and sale.get("status") not in ("chantier_fini", "commercial_cheque", "argent_recupere", "annule"):
            await db.sales.update_one(
                cq(user, {"id": sale["id"]}),
                {"$set": {"status": "chantier_fini", "chantier_fini_at": now}},
            )
            sale["status"] = "chantier_fini"
        if sale:
            client = await db.clients.find_one(cq(user, {"id": sale.get("client_id")}), {"_id": 0}) or {}
            # iter156 : résolution robuste du commercial (fuzzy + user_id direct) pour
            # que la notif atterrisse toujours dans la cloche même quand
            # users.name ≠ sale.commercial (Anaïs vs Anaïs Blanc, etc.).
            seen_uids = set()
            uid_candidates = []
            if sale.get("commercial_user_id"): uid_candidates.append(sale["commercial_user_id"])
            if sale.get("is_de") and sale.get("commercial_2_user_id"): uid_candidates.append(sale["commercial_2_user_id"])
            for uid in uid_candidates:
                if not uid or uid in seen_uids: continue
                seen_uids.add(uid)
                cu = await db.users.find_one(cq(user, {"id": uid}), {"_id": 0})
                if cu and cu.get("id") and cu["id"] not in {c["id"] for c in commercial_users}:
                    commercial_users.append(cu)
            name_candidates = [sale.get("commercial")]
            if sale.get("is_de"): name_candidates.append(sale.get("commercial_2"))
            for cname in filter(None, name_candidates):
                # Résolution via l'helper commercial_user_id (essaie name exact puis fuzzy)
                resolved_uid = await _resolve_commercial_user_id(user, cname)
                if resolved_uid and resolved_uid not in seen_uids:
                    seen_uids.add(resolved_uid)
                    cu = await db.users.find_one(cq(user, {"id": resolved_uid}), {"_id": 0})
                    if cu and cu["id"] not in {c["id"] for c in commercial_users}:
                        commercial_users.append(cu)
                        continue
                # Fallback : scan users commerciaux et fuzzy-match sur name
                async for cu in db.users.find(cq(user, {"role": "commercial"}), {"_id": 0}):
                    if cu["id"] in {c["id"] for c in commercial_users}: continue
                    if _fuzzy_name_match(cname, cu.get("name") or ""):
                        commercial_users.append(cu)
                        seen_uids.add(cu["id"])
                        break

    await log_audit(user, "complete", "project", pid, after=completion)

    client_name = client.get("name") or project.get("client_name") or "Client"
    # iter156 : inclure la note du technicien dans le message de la cloche pour que
    # le commercial voie immédiatement ce qui a été noté (l'utilisatrice se plaignait
    # que la note du technicien restait invisible côté commercial).
    _note = (completion.get("note") or "").strip()
    _bell_msg = f"{completion['completed_by']} vient de terminer le chantier."
    if _note:
        _bell_msg = f"{_bell_msg} Note : {_note}"
    for cu in commercial_users:
        try:
            await emit_notification_to_users(
                company_id_of(user), [cu["id"]],
                title=f"Chantier terminé — {client_name}",
                message=_bell_msg,
                link_url="/ventes",
                category="chantier_done",
            )
        except Exception as _e:
            logger.warning(f"complete_project: notif failed: {_e}")
        if cu.get("email"):
            try:
                addr_parts = [client.get("address") or "", client.get("postal_code") or "", client.get("city") or ""]
                addr = " ".join([x for x in addr_parts if x]).strip() or "—"
                html = _completion_commercial_email_html(
                    client_name=client_name,
                    address=addr,
                    completed_by=completion["completed_by"],
                    completed_at=now[:16].replace("T", " à "),
                    note=completion.get("note") or "",
                    photo_count=len(new_photos),
                )
                await send_email(to=cu["email"], subject=f"Chantier terminé — {client_name}", html=html)
            except Exception as _e:
                logger.warning(f"complete_project: email failed for {cu.get('email')}: {_e}")

    return {"ok": True, "project_id": pid, "completion": completion, "notified": len(commercial_users)}


# iter42: Ventes dont le commercial n'a pas pu être matché à un compte utilisateur.
@api_router.get("/sales/unmatched-commercials")
async def list_unmatched_commercials(user: dict = Depends(get_current_user)):
    check_perm(user, "sales", "view", "all")
    rows = await db.sales.find(
        cq(user, {"commercial_unmatched": True}),
        {"_id": 0, "id": 1, "client_id": 1, "commercial": 1, "commercial_2": 1, "sale_date": 1, "amount": 1, "commercial_user_id": 1, "commercial_2_user_id": 1},
    ).sort("sale_date", -1).to_list(2000)
    # « Direction » est une attribution valide (pas de compte utilisateur requis)
    def _slot_missing(r, name_k, id_k):
        nm = (r.get(name_k) or "").strip()
        return bool(nm) and not r.get(id_k) and not _is_direction(nm)
    ok_ids = [r["id"] for r in rows if not _slot_missing(r, "commercial", "commercial_user_id") and not _slot_missing(r, "commercial_2", "commercial_2_user_id")]
    if ok_ids:
        await db.sales.update_many(cq(user, {"id": {"$in": ok_ids}}), {"$set": {"commercial_unmatched": False}})
        rows = [r for r in rows if r["id"] not in set(ok_ids)]
    client_ids = list({r["client_id"] for r in rows if r.get("client_id")})
    clients = await db.clients.find(cq(user, {"id": {"$in": client_ids}}), {"_id": 0, "id": 1, "name": 1}).to_list(len(client_ids)) if client_ids else []
    cmap = {c["id"]: c["name"] for c in clients}
    for r in rows:
        r["client_name"] = cmap.get(r.get("client_id"), "")
    return rows


def _is_direction(name) -> bool:
    import unicodedata as _ud
    import re as _re
    n = _ud.normalize("NFKD", (name or "")).encode("ascii", "ignore").decode().strip().lower()
    toks = _re.split(r"[^a-z0-9]+", n)
    return any(t in ("direction", "dir", "direct", "directeur", "directrice", "dg") for t in toks if t)


class BindCommercialIn(BaseModel):
    slot: Literal["commercial", "commercial_2"] = "commercial"
    user_id: str = Field(min_length=1, max_length=128)


@api_router.post("/sales/{sid}/bind-commercial")
async def bind_commercial(sid: str, data: BindCommercialIn, user: dict = Depends(get_current_user)):
    check_perm(user, "sales", "edit")
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Accès refusé")
    company = company_id_of(user)
    id_slot = "commercial_user_id" if data.slot == "commercial" else "commercial_2_user_id"
    if data.user_id == "__direction__":
        target = {"id": None, "name": "Direction"}
    else:
        target = await db.users.find_one({"company_id": company, "id": data.user_id}, {"_id": 0, "id": 1, "name": 1})
    if not target:
        # Peut-être un team_member.id — récupère l'email et re-cherche l'utilisateur
        tm = await db.team_members.find_one({"company_id": company, "id": data.user_id}, {"_id": 0, "email": 1, "name": 1, "user_id": 1})
        if tm:
            # 1) team_member déjà lié par `user_id`
            if tm.get("user_id"):
                target = await db.users.find_one({"company_id": company, "id": tm["user_id"]}, {"_id": 0, "id": 1, "name": 1})
            # 2) team_member avec un email → user
            if not target and (tm.get("email") or "").strip():
                email = tm["email"].strip().lower()
                target = await db.users.find_one(
                    {"company_id": company, "email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}},
                    {"_id": 0, "id": 1, "name": 1},
                )
            # 3) team_member sans compte lié → refus EXPLICITE (plus de fuzzy silencieux)
            if not target:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Le membre d'équipe « {tm.get('name') or 'ce membre'} » n'a pas encore de compte utilisateur. "
                        "Crée-lui un compte depuis Utilisateurs (rôle Commercial), puis reviens attribuer la vente."
                    ),
                )
    if not target:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable dans la société")
    updates = {data.slot: target["name"], id_slot: target["id"]}
    # Si l'autre slot est déjà lié, on peut lever le flag
    sale = await db.sales.find_one(cq(user, {"id": sid}), {"_id": 0}) or {}
    other_id_slot = "commercial_2_user_id" if data.slot == "commercial" else "commercial_user_id"
    other_name_slot = "commercial_2" if data.slot == "commercial" else "commercial"
    still_missing = bool((sale.get(other_name_slot) or "").strip()) and not sale.get(other_id_slot) and not _is_direction(sale.get(other_name_slot))
    updates["commercial_unmatched"] = still_missing
    r = await db.sales.update_one(cq(user, {"id": sid}), {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vente introuvable")
    await log_audit(user, "bind_commercial", "sale", sid, after=updates)
    return await db.sales.find_one(cq(user, {"id": sid}), {"_id": 0})


# ---------------- Sale statuses (iter40) : entièrement personnalisables par société ----------------
# Stockage dans la collection `settings` sous la clé `sale_statuses` (liste ordonnée d'objets).
# Fallback = defaults QYLOT si la société n'a rien personnalisé.

DEFAULT_SALE_STATUSES = [
    {"value": "attente_prog", "label": "En attente prog", "color": "violet", "active": True, "system": True, "hides_from_projects": False},
    {"value": "attente_fi", "label": "En attente FI", "color": "orange", "active": True, "system": True, "hides_from_projects": False},
    {"value": "en_cours", "label": "En cours", "color": "indigo", "active": True, "system": True, "hides_from_projects": False},
    {"value": "chantier_fini", "label": "Chantier fini", "color": "yellow", "active": True, "system": True, "hides_from_projects": False},
    {"value": "commercial_cheque", "label": "Commercial a le chèque", "color": "sky", "active": True, "system": True, "hides_from_projects": False},
    {"value": "argent_recupere", "label": "Chèque récupéré", "color": "emerald", "active": True, "system": True, "hides_from_projects": False},
    {"value": "litige", "label": "Litige", "color": "orange", "active": True, "system": True, "hides_from_projects": True},
    {"value": "annule", "label": "Annulé", "color": "red", "active": True, "system": True, "hides_from_projects": True},
]
ALLOWED_STATUS_COLORS = {"slate", "red", "orange", "amber", "yellow", "lime", "green", "emerald", "teal", "cyan", "sky", "blue", "indigo", "violet", "purple", "fuchsia", "pink", "rose"}


class SaleStatusItem(BaseModel):
    value: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=60)
    color: Literal["slate", "red", "orange", "amber", "yellow", "lime", "green", "emerald", "teal", "cyan", "sky", "blue", "indigo", "violet", "purple", "fuchsia", "pink", "rose"] = "slate"
    active: bool = True
    default: bool = False  # iter103 : statut par défaut à la création d'une vente
    hides_from_projects: bool = False  # iter119 : masque le chantier lié de Kanban/Planning

class SaleStatusesIn(BaseModel):
    statuses: List[SaleStatusItem] = Field(max_length=100)

class SaleStatusReassignIn(BaseModel):
    source: str = Field(min_length=1, max_length=40)
    target: str = Field(min_length=1, max_length=40)


def _resolve_statuses(s: dict) -> List[dict]:
    raw = s.get("sale_statuses")
    if not isinstance(raw, list) or not raw:
        return list(DEFAULT_SALE_STATUSES)
    seen = set()
    out = []
    system_values = {d["value"] for d in DEFAULT_SALE_STATUSES}
    system_hides = {d["value"]: d.get("hides_from_projects", False) for d in DEFAULT_SALE_STATUSES}
    for it in raw:
        if not isinstance(it, dict) or not it.get("value"):
            continue
        color = it.get("color") if it.get("color") in ALLOWED_STATUS_COLORS else "slate"
        # iter119 : fallback = valeur système par défaut si le champ n'a jamais été persisté
        hides = it.get("hides_from_projects")
        if hides is None:
            hides = system_hides.get(it["value"], False)
        out.append({
            "value": it["value"],
            "label": it.get("label") or it["value"],
            "color": color,
            "active": bool(it.get("active", True)),
            "default": bool(it.get("default", False)),
            "system": bool(it.get("system", False)) or it["value"] in system_values,
            "hides_from_projects": bool(hides),
        })
        seen.add(it["value"])
    for d in DEFAULT_SALE_STATUSES:
        if d["value"] not in seen:
            out.append({**d, "active": False, "default": False})
    return out


async def _get_hiding_status_values(user: dict) -> set:
    """iter119/155b : retourne l'ensemble des `status.value` qui doivent masquer le chantier
    lié (cancelled=True) sur Kanban/Planning. Union du toggle admin + fallback système
    (annule, litige) + heuristique valeur/label contenant `non_financ`/`annul` (couvre
    les statuts custom "Non finançable" / "Annulé" créés par l'admin sans avoir coché
    manuellement le flag `hides_from_projects`)."""
    s = await db.settings.find_one({"company_id": company_id_of(user), "kind": "global"}, {"_id": 0}) or {}
    statuses = _resolve_statuses(s)
    hiding = {st["value"] for st in statuses if st.get("hides_from_projects")} | {"annule", "litige"}
    for st in statuses:
        val = (st.get("value") or "").lower()
        lbl = (st.get("label") or "").lower()
        if ("non_financ" in val) or ("non financ" in lbl) or ("annul" in val) or ("annul" in lbl):
            hiding.add(st["value"])
    return hiding


PROSPECT_COMM_ROLES = ("admin", "responsable")
PROSPECT_VIEW_ALL_ROLES = ("admin", "responsable", "responsable_prospecteur")


async def _prospecteur_fields(user: dict, pid: Optional[str], commission: Optional[float]) -> dict:
    p = await db.users.find_one(cq(user, {"id": pid, "role": {"$in": ["prospecteur", "responsable_prospecteur"]}}), {"_id": 0, "id": 1, "name": 1}) if pid else None
    if not p:
        return {"prospecteur_id": "", "prospecteur_name": "", "prospecteur_commission": 0.0}
    allowed = user.get("role") in PROSPECT_COMM_ROLES
    return {"prospecteur_id": p["id"], "prospecteur_name": p.get("name") or "",
            "prospecteur_commission": float(commission or 0) if allowed else 0.0}


class ProspectCommissionIn(BaseModel):
    prospecteur_commission: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    prospect_commission_month: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}$")

    @field_validator("prospect_commission_month")
    @classmethod
    def validate_prospect_commission_month(cls, value: Optional[str]) -> Optional[str]:
        if value:
            datetime.strptime(value, "%Y-%m")
        return value


@api_router.get("/prospecteurs")
async def list_prospecteurs(user: dict = Depends(get_current_user)):
    return await db.users.find(cq(user, {"role": {"$in": ["prospecteur", "responsable_prospecteur"]}}), {"_id": 0, "id": 1, "name": 1, "role": 1}).sort("name", 1).to_list(500)


@api_router.get("/prospection")
async def list_prospection(
    prospecteur_id: Optional[str] = Query(None, max_length=128),
    user: dict = Depends(get_current_user),
):
    role = user.get("role")
    if role == "prospecteur":
        q = cq(user, {"prospecteur_id": user["id"]})
    elif role in PROSPECT_VIEW_ALL_ROLES:
        q = cq(user, {"prospecteur_id": prospecteur_id} if prospecteur_id else {"prospecteur_id": {"$nin": [None, ""]}})
    else:
        raise HTTPException(status_code=403, detail="Accès refusé")
    sales = await db.sales.find(q, {"_id": 0, "id": 1, "client_id": 1, "bdc": 1, "sale_date": 1, "service": 1, "status": 1, "amount": 1,
                                     "commercial": 1, "prospecteur_id": 1, "prospecteur_name": 1, "prospecteur_commission": 1, "prospect_commission_month": 1}).sort("sale_date", -1).to_list(5000)
    cids = list({s.get("client_id") for s in sales if s.get("client_id")})
    clients = {c["id"]: c async for c in db.clients.find(cq(user, {"id": {"$in": cids}}), {"_id": 0, "id": 1, "name": 1, "phone": 1, "city": 1, "postal_code": 1})}
    rows = []
    for s in sales:
        c = clients.get(s.get("client_id")) or {}
        row = {**s, "client_name": c.get("name", ""), "client_phone": c.get("phone", ""), "client_city": c.get("city", ""),
               "client_postal_code": c.get("postal_code", ""), "prospecteur_commission": float(s.get("prospecteur_commission") or 0)}
        if role == "prospecteur":
            for k in ("amount", "service", "bdc"):
                row.pop(k, None)
        rows.append(row)
    return rows


@api_router.put("/prospection/{sid}")
async def update_prospection_commission(sid: str, data: ProspectCommissionIn, user: dict = Depends(get_current_user)):
    if user.get("role") not in PROSPECT_COMM_ROLES:
        raise HTTPException(status_code=403, detail="Seuls l'admin et le responsable peuvent modifier la commission")
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    if not upd:
        raise HTTPException(status_code=400, detail="Aucun champ")
    if "prospecteur_commission" in upd:
        upd["prospecteur_commission"] = float(upd["prospecteur_commission"])
    r = await db.sales.update_one(cq(user, {"id": sid, "prospecteur_id": {"$nin": [None, ""]}}), {"$set": upd})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vente introuvable")
    return {"ok": True, **upd}


@api_router.get("/sale-statuses")
async def get_sale_statuses(user: dict = Depends(get_current_user)):
    cid = company_id_of(user)
    s = await db.settings.find_one({"company_id": cid, "kind": "global"}, {"_id": 0}) or {}
    return _resolve_statuses(s)


@api_router.get("/sale-statuses/usage")
async def get_sale_statuses_usage(user: dict = Depends(get_current_user)):
    if user.get("role") not in ("admin", "responsable", "comptable"):
        raise HTTPException(status_code=403, detail="Accès refusé")
    pipeline = [
        {"$match": cq(user)},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]
    out = {}
    async for row in db.sales.aggregate(pipeline):
        if row.get("_id"):
            out[row["_id"]] = int(row.get("n") or 0)
    return out


@api_router.put("/sale-statuses")
async def put_sale_statuses(data: SaleStatusesIn, user: dict = Depends(get_current_user)):
    check_perm(user, "settings", "modify")
    cid = company_id_of(user)
    incoming = {it.value: it for it in data.statuses}
    system_values = {d["value"] for d in DEFAULT_SALE_STATUSES}
    missing_system = [v for v in system_values if v not in incoming]
    if missing_system:
        raise HTTPException(status_code=400, detail=f"Statuts système obligatoires : {', '.join(missing_system)}. Vous pouvez les désactiver mais pas les supprimer.")
    prev = await db.settings.find_one({"company_id": cid, "kind": "global"}, {"_id": 0}) or {}
    prev_values = {s["value"] for s in _resolve_statuses(prev)}
    removed = prev_values - set(incoming.keys())
    if removed:
        cursor = db.sales.aggregate([
            {"$match": {**cq(user), "status": {"$in": list(removed)}}},
            {"$group": {"_id": "$status", "n": {"$sum": 1}}},
        ])
        used = {}
        async for r in cursor:
            if r.get("_id") and (r.get("n") or 0) > 0:
                used[r["_id"]] = int(r["n"])
        if used:
            raise HTTPException(status_code=409, detail={"message": "Certains statuts sont encore utilisés par des ventes", "used": used})
    payload = []
    default_seen = False
    for it in data.statuses:
        color = it.color if it.color in ALLOWED_STATUS_COLORS else "slate"
        is_system = it.value in system_values
        is_default = bool(it.default) and it.active and not default_seen
        if is_default:
            default_seen = True
        payload.append({"value": it.value, "label": it.label, "color": color, "active": it.active, "default": is_default, "system": is_system, "hides_from_projects": bool(getattr(it, "hides_from_projects", False))})
    await db.settings.update_one(
        {"company_id": cid, "kind": "global"},
        {"$set": {"sale_statuses": payload, "kind": "global", "company_id": cid,
                  "sale_status_order": [it.value for it in data.statuses]}},
        upsert=True,
    )
    return _resolve_statuses({"sale_statuses": payload})


@api_router.post("/sale-statuses/reassign")
async def reassign_sale_status(data: SaleStatusReassignIn, user: dict = Depends(get_current_user)):
    """iter103 : bascule TOUTES les ventes du statut `source` vers `target` puis (si `source` n'est
    pas un statut système) désactive/supprime `source` de la configuration. Utile avant suppression
    d'un statut utilisé pour ne perdre aucune donnée."""
    check_perm(user, "settings", "modify")
    if data.source == data.target:
        raise HTTPException(status_code=400, detail="Source et cible identiques")
    cid = company_id_of(user)
    s = await db.settings.find_one({"company_id": cid, "kind": "global"}, {"_id": 0}) or {}
    all_statuses = _resolve_statuses(s)
    target_ok = next((x for x in all_statuses if x["value"] == data.target and x.get("active", True)), None)
    if not target_ok:
        raise HTTPException(status_code=400, detail=f"Statut cible '{data.target}' introuvable ou inactif")
    r = await db.sales.update_many(
        {**cq(user), "status": data.source},
        {"$set": {"status": data.target, "updated_at": now_iso(), "updated_by": user["id"]}},
    )
    system_values = {d["value"] for d in DEFAULT_SALE_STATUSES}
    if data.source not in system_values:
        new_list = [it for it in all_statuses if it["value"] != data.source]
        payload = [{"value": it["value"], "label": it["label"], "color": it["color"], "active": it.get("active", True), "default": it.get("default", False), "system": it.get("system", False)} for it in new_list]
        await db.settings.update_one(
            {"company_id": cid, "kind": "global"},
            {"$set": {"sale_statuses": payload, "kind": "global", "company_id": cid, "sale_status_order": [it["value"] for it in payload]}},
            upsert=True,
        )
    return {"reassigned": int(r.modified_count or 0), "removed_source": data.source not in system_values}


app.include_router(api_router)


@app.middleware("http")
async def security_headers_and_request_limits(request: Request, call_next):
    """Apply a coarse request-size guard and baseline browser security headers."""
    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > MAX_REQUEST_BYTES:
        return JSONResponse(
            status_code=413,
            content={"detail": f"Requête trop volumineuse (max {MAX_REQUEST_BYTES // (1024 * 1024)} Mo)"},
        )
    # Content-Length can be absent or false for chunked requests. Wrap the ASGI
    # receive callable so the body is counted while downstream consumes it.
    original_receive = request._receive
    received_bytes = 0

    async def receive():
        nonlocal received_bytes
        message = await original_receive()
        if message.get("type") == "http.request":
            received_bytes += len(message.get("body") or b"")
            if received_bytes > MAX_REQUEST_BYTES:
                raise HTTPException(status_code=413, detail="Requête trop volumineuse")
        return message

    request._receive = receive
    try:
        response = await call_next(request)
    except HTTPException as exc:
        if exc.status_code != 413:
            raise
        return JSONResponse(status_code=413, content={"detail": exc.detail})
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path not in ("/docs", "/redoc", "/openapi.json"):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    environment = (os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "development").lower()
    if environment in ("production", "prod"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# --- Kubernetes / load-balancer health probes -------------------------------
# Emergent's deployment platform hits GET /health (no /api prefix) as its
# liveness / readiness probe. Return 200 without touching the database so the
# pod stays "Ready" even during brief DB blips.
@app.get("/health", include_in_schema=False)
@app.get("/healthz", include_in_schema=False)
@app.get("/api/health", include_in_schema=False)
@app.get("/api/healthz", include_in_schema=False)
async def _health():
    return {"status": "ok"}


@app.get("/ready", include_in_schema=False)
@app.get("/readyz", include_in_schema=False)
@app.get("/api/ready", include_in_schema=False)
async def _ready():
    """Readiness probe: only accept traffic when MongoDB answers."""
    try:
        await db.command("ping")
    except Exception:
        raise HTTPException(status_code=503, detail="Base de données indisponible")
    return {"status": "ready"}


# iter55 : version du bundle serveur (utilisé par le frontend pour détecter un redeploy)
APP_VERSION = os.environ.get("APP_VERSION", "iter178")
APP_STARTED_AT = now_iso()

@app.get("/api/version", include_in_schema=False)
async def _version():
    return {"version": APP_VERSION, "started_at": APP_STARTED_AT}

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)
