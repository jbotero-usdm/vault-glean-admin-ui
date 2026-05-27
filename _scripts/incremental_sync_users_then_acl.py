#!/usr/bin/env python3
"""
Veeva Vault Quality -> Glean incremental sync with datasource user indexing + strict ACLs

What this script does
- Uses Vault Direct Data incremental files for changed content when available
- Uses a periodic full reconcile to handle deletes/stale cleanup safely
- Ensures the custom Glean datasource exists
- Indexes Vault users into the SAME datasource before applying ACLs
- Resolves document/object ACLs from Vault live role APIs
- Expands Vault groups to user emails
- INCLUDES dynamic access control from user_role_setup__v for object records
  (because the per-record /roles API does NOT return URS-granted users)
- Indexes changed documents and objects with permissions.allowedUsers

Why URS expansion is required for objects
- Vault QMS objects use dynamic security via user_role_setup__v + application_role__v
- A user can have read access to ALL records of an object type via URS, but the
  per-record /vobjects/{name}/{id}/roles endpoint will NOT list them
- Without URS expansion, the script would push allowedUsers = [creator only],
  making the records invisible in Glean to users who can actually see them in Vault

Defaults
- STRICT_ACL defaults to true
- ACL_FALLBACK defaults to deny
- FULL_RECONCILE_HOURS defaults to 24
- REFRESH_DATA defaults to true

Run examples
- Incremental/normal:
    STRICT_ACL=true ACL_FALLBACK=deny python incremental_sync_users_then_acl.py
- Force full reconcile now:
    FORCE_FULL_RECONCILE=true STRICT_ACL=true ACL_FALLBACK=deny python incremental_sync_users_then_acl.py
- Reuse existing extracted files instead of downloading again:
    REFRESH_DATA=false STRICT_ACL=true ACL_FALLBACK=deny python incremental_sync_users_then_acl.py
"""

import json
import os
import re
import shutil
import tarfile
import time
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
VAULT_DNS = os.getenv("VAULT_DNS")
VAULT_USER = os.getenv("VAULT_USERNAME")
VAULT_PASS = os.getenv("VAULT_PASSWORD")
GLEAN_URL = os.getenv("GLEAN_API_URL", "").rstrip("/")
GLEAN_TOKEN = os.getenv("GLEAN_INDEXING_API_TOKEN")

API_VERSION = os.getenv("VAULT_API_VERSION", "v26.1")
DATASOURCE_NAME = os.getenv("GLEAN_DATASOURCE_NAME", "veevavaultquality")
DATASOURCE_DISPLAY_NAME = os.getenv("GLEAN_DATASOURCE_DISPLAY_NAME", "Vault Quality")
DOC_CATEGORY = "PUBLISHED_CONTENT"

MAX_DOCS = int(os.getenv("MAX_DOCS", "999999"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))
INDEX_OBJECTS = os.getenv("INDEX_OBJECTS", "true").lower() == "true"
STRICT_ACL = os.getenv("STRICT_ACL", "true").lower() == "true"
ACL_FALLBACK = os.getenv("ACL_FALLBACK", "deny").lower()  # deny|owner_creator|all_datasource_users|anonymous

FULL_RECONCILE_HOURS = int(os.getenv("FULL_RECONCILE_HOURS", "24"))
FORCE_FULL_RECONCILE = os.getenv("FORCE_FULL_RECONCILE", "false").lower() == "true"
REFRESH_DATA = os.getenv("REFRESH_DATA", "true").lower() == "true"
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))

# When True, applies URS-derived emails to object permissions even if per-record
# /vobjects/.../roles returns no users beyond the owner. This honestly reflects
# who can actually see the record in Vault. Set false to disable URS expansion.
EXPAND_URS_FOR_OBJECTS = os.getenv("EXPAND_URS_FOR_OBJECTS", "true").lower() == "true"

# URS roles that grant READ access — used to filter which URS records imply visibility.
# Default covers the common Vault read-access roles. Extend if you have custom roles.
URS_READ_ROLE_NAMES = set(
    os.getenv(
        "URS_READ_ROLE_NAMES",
        "viewer,consumer,reviewer,owner,editor,coordinator,approver,qa,available_qa,document_change_control_reviewer,document_change_control_approver,periodic_reviewer,trainee,process_viewer",
    ).lower().split(",")
)

DOWNLOAD_DIR = Path("downloads")
WORK_DIR = Path("data")
STATE_DIR = Path(".state")
STATE_FILE = STATE_DIR / "incremental_state.json"

DOCUMENT_CSV_NAME = "document_version__sys.csv"

ALLOWED_OBJECT_CSVS = {
    "deviation__v.csv",
    "change_control__v.csv",
    "nonconformance__v.csv",
    "audit__qdm.csv",
    "investigation__qdm.csv",
    "capa_action__qdm.csv",
    "capa_deviation__v.csv",
    "effectiveness_check__qdm.csv",
    "finding__v.csv",
    "quality_batch__v.csv",
    "quality_material__v.csv",
    "risk_level__v.csv",
    "risk_matrix__v.csv",
    "severity__v.csv",
    "facility__v.csv",
    "product__v.csv",
    "product_family__v.csv",
    "product_variant__v.csv",
    "product_change_control__v.csv",
    "product_deviation__v.csv",
}

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def require_env(name, value):
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")


def now_utc():
    return datetime.now(timezone.utc)


def fmt_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def clean_value(value):
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    if text.upper() in {"", "FALSE", "NONE", "NAN", "NULL"}:
        return ""
    return text


def sanitize_id(value):
    cleaned = re.sub(r"[^A-Za-z0-9]", "", str(value))
    if not cleaned:
        raise ValueError(f"Unable to build valid alphanumeric ID from: {value}")
    return cleaned


def safe_list(value):
    return value if isinstance(value, list) else []


def normalize_emails(values):
    out = []
    for v in safe_list(values):
        e = str(v).strip().lower()
        if not e or "@" not in e:
            continue
        if e not in out:
            out.append(e)
    return out


def read_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def find_csv(root: Path, filename: str):
    matches = list(root.rglob(filename))
    return matches[0] if matches else None


def make_doc_view_url(doc_num):
    return f"https://{VAULT_DNS}/ui/#doc_info/{doc_num}/0/0"


def make_object_view_url(object_type, object_id):
    return f"https://{VAULT_DNS}/ui/#t/{object_type.lower()}/0/{object_id}"


def fetch_text_content(session, url, headers):
    url = clean_value(url)
    if not url:
        return ""
    try:
        resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception:
        pass
    return ""


def api_name_to_glean_object_type(api_name: str) -> str:
    base = api_name.replace("__v", "").replace("__qdm", "").replace("__c", "").replace("__sys", "")
    return "".join(part.capitalize() for part in base.split("_") if part)


def discover_object_csv_map(extract_dir: Path):
    object_dir = extract_dir / "Object"
    mapping = {}
    if not object_dir.exists():
        return mapping

    for csv_path in sorted(object_dir.glob("*.csv")):
        csv_name = csv_path.name
        stem = csv_path.stem
        if csv_name not in ALLOWED_OBJECT_CSVS:
            continue
        mapping[csv_name] = (api_name_to_glean_object_type(stem), stem)
    return mapping


def choose_title(row, object_type, object_id):
    candidates = [
        "name__v",
        "title__v",
        "description__v",
        "document_number__v",
        "external_id__v",
        "code__v",
        "name__sys",
    ]
    for field in candidates:
        value = clean_value(row.get(field))
        if value:
            return value
    return f"{object_type} {object_id}"


def sha256_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# -----------------------------------------------------------------------------
# Glean datasource + users
# -----------------------------------------------------------------------------
def ensure_datasource(session, glean_headers, object_csv_map):
    object_definitions = [{"name": "Document", "docCategory": DOC_CATEGORY}]
    for object_type, _ in sorted(set(object_csv_map.values())):
        object_definitions.append({"name": object_type, "docCategory": DOC_CATEGORY})

    payload = {
        "name": DATASOURCE_NAME,
        "displayName": DATASOURCE_DISPLAY_NAME,
        "datasourceCategory": DOC_CATEGORY,
        "urlRegex": rf"^https://{re.escape(VAULT_DNS)}/ui/#.*",
        "objectDefinitions": object_definitions,
        "isUserReferencedByEmail": True,
    }

    resp = session.post(
        f"{GLEAN_URL}/api/index/v1/adddatasource",
        headers=glean_headers,
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code in (200, 201):
        print("✓ Datasource created")
    elif resp.status_code == 409:
        print("✓ Datasource already exists")
    else:
        print(f"⚠ Datasource response: {resp.status_code} {resp.text[:500]}")
        resp.raise_for_status()


def index_user(session, glean_headers, email, name):
    payload = {
        "datasource": DATASOURCE_NAME,
        "user": {
            "email": email,
            "name": name or email,
        },
    }
    return session.post(
        f"{GLEAN_URL}/api/index/v1/indexuser",
        headers=glean_headers,
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )


# -----------------------------------------------------------------------------
# Vault Direct Data
# -----------------------------------------------------------------------------
def retrieve_direct_data_files(session, vault_headers, extract_type, start_time=None, stop_time=None):
    params = {"extract_type": extract_type}
    if start_time:
        params["start_time"] = start_time
    if stop_time:
        params["stop_time"] = stop_time

    resp = session.get(
        f"https://{VAULT_DNS}/api/{API_VERSION}/services/directdata/files",
        headers=vault_headers,
        params=params,
        timeout=120,
    )
    resp.raise_for_status()
    entries = resp.json().get("data", [])

    ready = []
    delayed = []
    for entry in entries:
        if entry.get("filepart_details"):
            ready.append(entry)
        elif entry.get("error"):
            delayed.append(entry)
    return ready, delayed


def download_and_extract_direct_data(session, vault_headers, extract_type, start_time, stop_time, extract_dir: Path):
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    if extract_type == "full_directdata":
        ready, delayed = retrieve_direct_data_files(session, vault_headers, extract_type, None, None)
    else:
        ready, delayed = retrieve_direct_data_files(session, vault_headers, extract_type, start_time, stop_time)

    if delayed:
        print("⚠ Some Direct Data files are not ready yet:")
        for entry in delayed[:5]:
            name = entry.get("name")
            err = entry.get("error", {})
            print(f"  - {name}: {err.get('message', 'not ready')} next_retry={err.get('next_retry')}")

    if not ready:
        return False

    for entry in ready:
        archive_path = DOWNLOAD_DIR / entry["filename"]
        if archive_path.exists():
            archive_path.unlink()

        for part in sorted(entry["filepart_details"], key=lambda x: x.get("filepart", 0)):
            part_resp = session.get(part["url"], headers=vault_headers, stream=True, timeout=300)
            part_resp.raise_for_status()
            with open(archive_path, "ab") as out:
                for chunk in part_resp.iter_content(8192):
                    if chunk:
                        out.write(chunk)

        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(extract_dir)

    print(f"✓ Downloaded and extracted {len(ready)} {extract_type} file(s) to {extract_dir}")
    return True


# -----------------------------------------------------------------------------
# Vault users + groups
# -----------------------------------------------------------------------------
def get_user_map(session, vault_headers):
    resp = session.get(
        f"https://{VAULT_DNS}/api/{API_VERSION}/objects/users",
        headers=vault_headers,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    users = resp.json().get("users", [])

    user_map = {}
    for item in users:
        user = item.get("user", {})
        user_id = str(user.get("id", "")).strip()
        email = str(user.get("user_name__v", "")).strip().lower()
        first = str(user.get("user_first_name__v", "")).strip()
        last = str(user.get("user_last_name__v", "")).strip()
        active = user.get("active__v", False)
        if user_id and email and "@" in email:
            user_map[user_id] = {
                "email": email,
                "name": f"{first} {last}".strip() or email,
                "active": bool(active),
            }
    return user_map


def get_group_map(session, vault_headers):
    resp = session.get(
        f"https://{VAULT_DNS}/api/{API_VERSION}/objects/groups",
        headers=vault_headers,
        params={"includeImplied": "true"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    groups = resp.json().get("groups", [])

    group_map = {}
    for item in groups:
        group = item.get("group", {})
        group_id = str(group.get("id", "")).strip()
        name = str(group.get("name__v", "")).strip()
        if not group_id or not name:
            continue
        direct_members = [str(x) for x in safe_list(group.get("members__v"))]
        implied_members = [str(x) for x in safe_list(group.get("implied_members__v"))]
        group_map[group_id] = {
            "name": name,
            "members": sorted(set(direct_members + implied_members)),
        }
    return group_map


def get_urs_map(session, vault_headers, user_map):
    """Load user_role_setup__v (and the QMS-specific user_role_setup_qms__c if present).
    
    These records grant users dynamic access to object records via their assigned
    application role. The per-record /vobjects/{name}/{id}/roles endpoint does NOT
    return URS-granted users, so we read these directly.
    
    Returns a list of dicts: [{role_id, role_name, user_id, email}, ...]
    Filtered to records with status=active and where the user is known + active.
    """
    if not EXPAND_URS_FOR_OBJECTS:
        return []
    
    urs_records = []
    
    # Query the system URS object
    for object_name in ["user_role_setup__v", "user_role_setup_qms__c"]:
        try:
            vql = f"SELECT id, user__v, role__v, status__v FROM {object_name}"
            resp = session.post(
                f"https://{VAULT_DNS}/api/{API_VERSION}/query",
                headers={**vault_headers, "Content-Type": "application/x-www-form-urlencoded"},
                data={"q": vql},
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                continue
            
            for row in resp.json().get("data", []):
                status = row.get("status__v")
                if isinstance(status, list):
                    status = status[0] if status else ""
                if status != "active__v":
                    continue
                
                user_id = str(row.get("user__v") or "")
                role_id = str(row.get("role__v") or "")
                if not user_id or not role_id:
                    continue
                
                user_info = user_map.get(user_id)
                if not user_info or not user_info.get("active"):
                    continue
                
                urs_records.append({
                    "role_id": role_id,
                    "user_id": user_id,
                    "email": user_info["email"],
                    "source_object": object_name,
                })
        except Exception as e:
            print(f"  ⚠ URS query on {object_name} failed: {e}")
    
    return urs_records


def get_role_definitions(session, vault_headers, role_ids):
    """Resolve application_role__v IDs to names so we can filter to read roles only."""
    if not role_ids:
        return {}
    
    role_id_list = ",".join(f"'{r}'" for r in sorted(set(role_ids)))
    vql = f"SELECT id, name__v FROM application_role__v WHERE id CONTAINS ({role_id_list})"
    
    try:
        resp = session.post(
            f"https://{VAULT_DNS}/api/{API_VERSION}/query",
            headers={**vault_headers, "Content-Type": "application/x-www-form-urlencoded"},
            data={"q": vql},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            return {r["id"]: (r.get("name__v") or "").lower() for r in resp.json().get("data", [])}
    except Exception:
        pass
    
    return {}


def build_urs_email_pool(urs_records, role_name_by_id):
    """Filter URS records to only those granting read access, return set of emails."""
    emails = set()
    for r in urs_records:
        role_name = role_name_by_id.get(r["role_id"], "").lower()
        if not role_name:
            # Unknown role — include conservatively (better to over-share to known
            # active users than to silently drop)
            emails.add(r["email"])
            continue
        if role_name in URS_READ_ROLE_NAMES:
            emails.add(r["email"])
    return emails


def compute_topology_hash(user_map, group_map):
    compact = {
        "users": {k: v["email"] for k, v in sorted(user_map.items())},
        "groups": {k: v["members"] for k, v in sorted(group_map.items())},
    }
    return sha256_json(compact)


# -----------------------------------------------------------------------------
# ACL expansion
# -----------------------------------------------------------------------------
def expand_group_ids_to_user_emails(group_ids, group_map, user_map):
    emails = []
    for gid in safe_list(group_ids):
        group = group_map.get(str(gid))
        if not group:
            continue
        for uid in group["members"]:
            user = user_map.get(str(uid))
            if user and user["email"] not in emails:
                emails.append(user["email"])
    return emails


def fallback_user_emails_from_row(row, user_map):
    emails = []
    for field in ["owner__sys", "created_by__v", "created_by__sys", "modified_by__v", "modified_by__sys"]:
        raw = clean_value(row.get(field))
        if not raw:
            continue
        if raw in user_map:
            e = user_map[raw]["email"]
            if e not in emails:
                emails.append(e)
        elif "@" in raw:
            e = raw.lower()
            if e not in emails:
                emails.append(e)
    return emails


def make_permissions_from_emails(emails, fallback=None):
    emails = normalize_emails(emails)
    if emails:
        return {
            "allowAnonymousAccess": False,
            "allowedUsers": [{"email": e} for e in emails],
        }
    if fallback == "all_datasource_users":
        return {"allowAnonymousAccess": False, "allowAllDatasourceUsersAccess": True}
    if fallback == "deny":
        return None
    return {"allowAnonymousAccess": True}


def get_document_permissions(session, vault_headers, doc_id, row, user_map, group_map):
    resp = session.get(
        f"https://{VAULT_DNS}/api/{API_VERSION}/objects/documents/{doc_id}/roles",
        headers=vault_headers,
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        fallback_emails = fallback_user_emails_from_row(row, user_map)
        return make_permissions_from_emails(fallback_emails, fallback=ACL_FALLBACK)

    roles = safe_list(resp.json().get("documentRoles"))
    emails = []

    for role in roles:
        for uid in safe_list(role.get("assignedUsers")):
            user = user_map.get(str(uid))
            if user:
                emails.append(user["email"])
        for uid in safe_list(role.get("defaultUsers")):
            user = user_map.get(str(uid))
            if user:
                emails.append(user["email"])
        emails.extend(expand_group_ids_to_user_emails(role.get("assignedGroups"), group_map, user_map))
        emails.extend(expand_group_ids_to_user_emails(role.get("defaultGroups"), group_map, user_map))

    if not normalize_emails(emails):
        if ACL_FALLBACK == "owner_creator":
            emails = fallback_user_emails_from_row(row, user_map)
            return make_permissions_from_emails(emails, fallback="anonymous")
        return make_permissions_from_emails([], fallback=ACL_FALLBACK)

    return make_permissions_from_emails(emails, fallback=ACL_FALLBACK)


def get_object_permissions(session, vault_headers, object_name, object_id, row, user_map, group_map, urs_email_pool):
    """Build object ACL by UNIONing per-record roles + URS-granted users.
    
    Per-record /vobjects/{name}/{id}/roles only returns explicit role assignments
    (typically just owner__v). URS records grant additional dynamic access that
    must be merged in to reflect actual Vault visibility.
    """
    emails = []
    
    resp = session.get(
        f"https://{VAULT_DNS}/api/{API_VERSION}/vobjects/{object_name}/{object_id}/roles",
        headers=vault_headers,
        timeout=REQUEST_TIMEOUT,
    )
    
    if resp.status_code == 200:
        roles = safe_list(resp.json().get("data"))
        for role in roles:
            for uid in safe_list(role.get("users")):
                user = user_map.get(str(uid))
                if user:
                    emails.append(user["email"])
            emails.extend(expand_group_ids_to_user_emails(role.get("groups"), group_map, user_map))
    
    # UNION with URS-granted users (dynamic access control)
    if EXPAND_URS_FOR_OBJECTS and urs_email_pool:
        for e in urs_email_pool:
            if e not in emails:
                emails.append(e)
    
    if not normalize_emails(emails):
        if ACL_FALLBACK == "owner_creator":
            emails = fallback_user_emails_from_row(row, user_map)
            return make_permissions_from_emails(emails, fallback="anonymous")
        return make_permissions_from_emails([], fallback=ACL_FALLBACK)
    
    return make_permissions_from_emails(emails, fallback=ACL_FALLBACK)


# -----------------------------------------------------------------------------
# Payload builders
# -----------------------------------------------------------------------------
def build_document_payload(row, session, vault_headers, user_map, group_map):
    version_id = clean_value(row.get("id"))
    doc_num = clean_value(row.get("doc_id")) or version_id
    title = clean_value(row.get("title__v")) or f"Document {doc_num}"
    status = clean_value(row.get("status__v"))
    lifecycle = clean_value(row.get("lifecycle__v"))
    doc_type = clean_value(row.get("type__v"))
    classification = clean_value(row.get("classification__v"))

    permissions = get_document_permissions(session, vault_headers, doc_num, row, user_map, group_map)
    if STRICT_ACL and permissions is None:
        return None
    if permissions is None:
        permissions = {"allowAnonymousAccess": True}

    text_content = fetch_text_content(session, row.get("text_file"), vault_headers)
    if not text_content:
        parts = [
            f"Document {doc_num}: {title}",
            f"Status: {status}" if status else "",
            f"Lifecycle: {lifecycle}" if lifecycle else "",
            f"Type: {doc_type}" if doc_type else "",
            f"Classification: {classification}" if classification else "",
        ]
        text_content = "\n".join(p for p in parts if p)

    return {
        "document": {
            "datasource": DATASOURCE_NAME,
            "objectType": "Document",
            "id": sanitize_id(version_id),
            "title": title,
            "viewURL": make_doc_view_url(doc_num),
            "permissions": permissions,
            "body": {
                "mimeType": "text/plain",
                "textContent": text_content,
            },
        }
    }


def build_object_payload(row, object_type, object_name, source_csv_name, session, vault_headers, user_map, group_map, urs_email_pool):
    object_id = clean_value(row.get("id"))
    if not object_id:
        return None

    title = choose_title(row, object_type, object_id)
    status = clean_value(row.get("status__v"))
    state = clean_value(row.get("state__v"))

    permissions = get_object_permissions(session, vault_headers, object_name, object_id, row, user_map, group_map, urs_email_pool)
    if STRICT_ACL and permissions is None:
        return None
    if permissions is None:
        permissions = {"allowAnonymousAccess": True}

    parts = [
        f"{object_type}: {title}",
        f"Record ID: {object_id}",
        f"Status: {status}" if status else "",
        f"State: {state}" if state else "",
        f"Source CSV: {source_csv_name}",
    ]
    text_content = "\n".join(p for p in parts if p)

    return {
        "document": {
            "datasource": DATASOURCE_NAME,
            "objectType": object_type,
            "id": sanitize_id(f"{object_type}_{object_id}"),
            "title": title,
            "viewURL": make_object_view_url(object_type, object_id),
            "permissions": permissions,
            "body": {
                "mimeType": "text/plain",
                "textContent": text_content,
            },
        }
    }


def build_all_payloads(extract_dir, session, vault_headers, user_map, group_map, urs_email_pool, object_csv_map):
    payloads = []

    doc_csv = find_csv(extract_dir, DOCUMENT_CSV_NAME)
    if doc_csv:
        docs_df = pd.read_csv(doc_csv, low_memory=False)
        if MAX_DOCS < len(docs_df):
            docs_df = docs_df.head(MAX_DOCS)
        print(f"✓ Loaded {len(docs_df)} document-version rows from {doc_csv}")
        for _, row in docs_df.iterrows():
            try:
                payload = build_document_payload(row, session, vault_headers, user_map, group_map)
                if payload:
                    payloads.append(payload)
            except Exception as e:
                print(f"  ✗ Document row failed: {e}")
    else:
        print(f"⚠ {DOCUMENT_CSV_NAME} not found in {extract_dir}")

    if INDEX_OBJECTS:
        for csv_name, (object_type, object_name) in object_csv_map.items():
            csv_path = find_csv(extract_dir, csv_name)
            if not csv_path:
                continue
            obj_df = pd.read_csv(csv_path, low_memory=False)
            print(f" - Found {len(obj_df)} rows in {csv_path}")
            for _, row in obj_df.iterrows():
                try:
                    payload = build_object_payload(row, object_type, object_name, csv_name, session, vault_headers, user_map, group_map, urs_email_pool)
                    if payload:
                        payloads.append(payload)
                except Exception as e:
                    print(f"   ✗ Object row in {csv_name} failed: {e}")

    return payloads


# -----------------------------------------------------------------------------
# Glean indexing
# -----------------------------------------------------------------------------
def index_one_document(session, glean_headers, payload):
    return session.post(
        f"{GLEAN_URL}/api/index/v1/indexdocument",
        headers=glean_headers,
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )


def post_bulk_documents(session, glean_headers, documents):
    if not documents:
        return 0

    upload_id = f"{DATASOURCE_NAME}-reconcile-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    total = len(documents)
    indexed = 0
    page = 0

    for start in range(0, total, BATCH_SIZE):
        chunk = [d["document"] for d in documents[start:start + BATCH_SIZE]]
        page += 1
        payload = {
            "uploadId": upload_id,
            "datasource": DATASOURCE_NAME,
            "documents": chunk,
            "isFirstPage": start == 0,
            "isLastPage": start + BATCH_SIZE >= total,
            "forceRestartUpload": start == 0,
        }
        resp = session.post(
            f"{GLEAN_URL}/api/index/v1/bulkindexdocuments",
            headers=glean_headers,
            json=payload,
            timeout=120,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Bulk index failed on page {page}: {resp.status_code} {resp.text[:500]}")
        indexed += len(chunk)
        print(f"  ✓ Bulk indexed reconcile page {page} ({indexed}/{total})")

    return indexed


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    for env_name, env_value in [
        ("VAULT_DNS", VAULT_DNS),
        ("VAULT_USERNAME", VAULT_USER),
        ("VAULT_PASSWORD", VAULT_PASS),
        ("GLEAN_API_URL", GLEAN_URL),
        ("GLEAN_INDEXING_API_TOKEN", GLEAN_TOKEN),
    ]:
        require_env(env_name, env_value)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = read_json(
        STATE_FILE,
        {
            "last_incremental_stop_time": None,
            "last_full_reconcile_time": None,
            "last_topology_hash": None,
        },
    )

    session = requests.Session()
    glean_headers = {
        "Authorization": f"Bearer {GLEAN_TOKEN}",
        "Content-Type": "application/json",
    }

    print("=" * 80)
    print("VEEVA VAULT -> GLEAN INCREMENTAL SYNC WITH USER INDEXING + SOURCE ACLS")
    print("=" * 80)

    print("\n[1/8] Authenticating to Vault...")
    auth_resp = session.post(
        f"https://{VAULT_DNS}/api/{API_VERSION}/auth",
        data={"username": VAULT_USER, "password": VAULT_PASS},
        timeout=REQUEST_TIMEOUT,
    )
    auth_resp.raise_for_status()
    sid = auth_resp.json()["sessionId"]
    vault_headers = {"Authorization": sid}
    print("✓ Authenticated")

    print("\n[2/8] Loading Vault users, groups, and dynamic access control (URS)...")
    user_map = get_user_map(session, vault_headers)
    group_map = get_group_map(session, vault_headers)
    
    urs_records = get_urs_map(session, vault_headers, user_map)
    role_ids = list({r["role_id"] for r in urs_records})
    role_name_by_id = get_role_definitions(session, vault_headers, role_ids)
    urs_email_pool = build_urs_email_pool(urs_records, role_name_by_id)
    
    topology_hash = compute_topology_hash(user_map, group_map)
    print(f"✓ Users loaded: {len(user_map)}")
    print(f"✓ Groups loaded: {len(group_map)}")
    print(f"✓ URS records loaded: {len(urs_records)}")
    print(f"✓ URS-granted readers (after filter to read roles): {len(urs_email_pool)}")
    if EXPAND_URS_FOR_OBJECTS:
        print(f"  URS expansion: ENABLED — objects will include URS-granted users in allowedUsers")
    else:
        print(f"  URS expansion: DISABLED (set EXPAND_URS_FOR_OBJECTS=true to enable)")

    now = now_utc()
    stop_time = fmt_ts(now)

    last_full = parse_ts(state["last_full_reconcile_time"]) if state["last_full_reconcile_time"] else None
    reconcile_due = (
        FORCE_FULL_RECONCILE
        or last_full is None
        or (now - last_full) >= timedelta(hours=FULL_RECONCILE_HOURS)
        or state.get("last_topology_hash") != topology_hash
    )

    if reconcile_due:
        print("\n[3/8] Full reconcile path...")
        reconcile_dir = WORK_DIR / "reconcile_full"

        existing_doc_csv = find_csv(WORK_DIR, DOCUMENT_CSV_NAME)
        if existing_doc_csv and not FORCE_FULL_RECONCILE and not REFRESH_DATA:
            print("✓ Using existing extracted data for reconcile bootstrap")
            reconcile_dir = WORK_DIR
            ok = True
        else:
            ok = download_and_extract_direct_data(
                session,
                vault_headers,
                "full_directdata",
                None,
                None,
                reconcile_dir,
            )

        if not ok:
            print("⚠ No published full Direct Data file available; falling back to incremental path")
            reconcile_due = False
        else:
            object_csv_map = discover_object_csv_map(reconcile_dir)
            print(f"✓ Discovered {len(object_csv_map)} object CSV types for reconcile")

            print("\n[4/8] Ensuring Glean datasource exists...")
            ensure_datasource(session, glean_headers, object_csv_map)

            print("\n[5/8] Indexing datasource users into Glean...")
            user_indexed = 0
            user_errors = 0
            for info in user_map.values():
                resp = index_user(session, glean_headers, info["email"], info["name"])
                if resp.status_code in (200, 201):
                    user_indexed += 1
                else:
                    user_errors += 1
                    print(f"  ✗ User {info['email']} failed: {resp.status_code} {resp.text[:300]}")
            print(f"✓ Users indexed: {user_indexed}")
            print(f"✓ User indexing errors: {user_errors}")

            print("\n[6/8] Building full reconcile payloads...")
            payloads = build_all_payloads(reconcile_dir, session, vault_headers, user_map, group_map, urs_email_pool, object_csv_map)
            print(f"✓ Prepared {len(payloads)} total payloads for reconcile")

            print("\n[7/8] Bulk replacing datasource contents...")
            indexed = post_bulk_documents(session, glean_headers, payloads)

            state["last_incremental_stop_time"] = stop_time
            state["last_full_reconcile_time"] = stop_time
            state["last_topology_hash"] = topology_hash
            write_json(STATE_FILE, state)

            print("\n[8/8] Done")
            print("\n" + "=" * 80)
            print("RECONCILE COMPLETE")
            print("=" * 80)
            print(f"Users indexed: {user_indexed}")
            print(f"Documents+objects bulk indexed: {indexed}")
            print(f"ACL fallback mode: {ACL_FALLBACK}")
            print(f"URS-derived emails included in object ACLs: {len(urs_email_pool)}")
            print(f"Checkpoint advanced to: {stop_time}")
            print("=" * 80)
            return

    print("\n[3/8] Incremental path...")
    start_time = state["last_incremental_stop_time"]
    if not start_time:
        start_time = fmt_ts(now - timedelta(hours=1))

    incremental_dir = WORK_DIR / "incremental"
    ok = download_and_extract_direct_data(
        session,
        vault_headers,
        "incremental_directdata",
        start_time,
        stop_time,
        incremental_dir,
    )
    if not ok:
        print("✓ No published incremental files available yet; checkpoint unchanged")
        return

    object_csv_map = discover_object_csv_map(incremental_dir)
    print(f"✓ Discovered {len(object_csv_map)} object CSV types in incremental extract")

    print("\n[4/8] Ensuring Glean datasource exists...")
    ensure_datasource(session, glean_headers, object_csv_map)

    print("\n[5/8] Indexing datasource users into Glean...")
    user_indexed = 0
    user_errors = 0
    for info in user_map.values():
        resp = index_user(session, glean_headers, info["email"], info["name"])
        if resp.status_code in (200, 201):
            user_indexed += 1
        else:
            user_errors += 1
            print(f"  ✗ User {info['email']} failed: {resp.status_code} {resp.text[:300]}")
    print(f"✓ Users indexed: {user_indexed}")
    print(f"✓ User indexing errors: {user_errors}")

    print("\n[6/8] Building incremental payloads...")
    payloads = build_all_payloads(incremental_dir, session, vault_headers, user_map, group_map, urs_email_pool, object_csv_map)
    print(f"✓ Prepared {len(payloads)} changed payloads")

    print("\n[7/8] Indexing changed documents/objects...")
    indexed = 0
    errors = 0
    for payload in payloads:
        resp = index_one_document(session, glean_headers, payload)
        if resp.status_code in (200, 201):
            indexed += 1
            if indexed % 25 == 0:
                print(f"  ✓ Indexed {indexed} changed items")
        else:
            errors += 1
            print(f"  ✗ {payload['document']['id']} failed: {resp.status_code} {resp.text[:300]}")

    state["last_incremental_stop_time"] = stop_time
    state["last_topology_hash"] = topology_hash
    write_json(STATE_FILE, state)

    print("\n[8/8] Done")
    print("\n" + "=" * 80)
    print("INCREMENTAL SYNC COMPLETE")
    print("=" * 80)
    print(f"Users indexed: {user_indexed}")
    print(f"Changed documents+objects indexed: {indexed}")
    print(f"Errors: {errors}")
    print(f"ACL fallback mode: {ACL_FALLBACK}")
    print(f"URS-derived emails included in object ACLs: {len(urs_email_pool)}")
    print(f"Checkpoint advanced from {start_time} to {stop_time}")
    print("=" * 80)


if __name__ == "__main__":
    main()