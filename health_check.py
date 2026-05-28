#!/usr/bin/env python3
"""
Lightweight health-check for the Vault -> Glean integration.
Probes Vault and Glean to report current sync health metrics.

No Direct Data download. No record indexing. Just diagnostics.
Designed to run inside a Vercel Python function (< 30 seconds total).

Outputs a single JSON line to stdout with all metrics.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

# Reuse env vars from the main sync
VAULT_DNS = os.getenv("VAULT_DNS", "")
VAULT_USER = os.getenv("VAULT_USERNAME", "")
VAULT_PASS = os.getenv("VAULT_PASSWORD", "")
GLEAN_URL = os.getenv("GLEAN_API_URL", "").rstrip("/")
GLEAN_TOKEN = os.getenv("GLEAN_INDEXING_API_TOKEN", "")
DATASOURCE_NAME = os.getenv("GLEAN_DATASOURCE_NAME", "veevavaultquality")
API_VERSION = os.getenv("VAULT_API_VERSION", "v26.1")

TIMEOUT = 15


def safe(fn, default=None):
    try:
        return fn()
    except Exception as e:
        return default


def vault_auth(session):
    """Auth to Vault. Return session ID or None on failure."""
    try:
        resp = session.post(
            f"https://{VAULT_DNS}/api/{API_VERSION}/auth",
            data={"username": VAULT_USER, "password": VAULT_PASS},
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json().get("sessionId")
    except Exception:
        pass
    return None


def main():
    started = time.time()
    report = {
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "vault": {"status": "unknown"},
        "glean": {"status": "unknown"},
        "metadata": {},
        "alerts": [],
    }
    
    session = requests.Session()
    
    # --- VAULT CHECKS ---
    sid = vault_auth(session)
    if not sid:
        report["vault"]["status"] = "error"
        report["alerts"].append({"severity": "critical", "message": "Vault auth failed — check VAULT_PASSWORD env var"})
    else:
        vh = {"Authorization": sid, "Accept": "application/json"}
        report["vault"]["status"] = "ok"
        report["vault"]["dns"] = VAULT_DNS
        
        # User count
        def count_users():
            r = session.get(f"https://{VAULT_DNS}/api/{API_VERSION}/objects/users", headers=vh, timeout=TIMEOUT)
            return len(r.json().get("users", [])) if r.status_code == 200 else None
        report["vault"]["users"] = safe(count_users)
        
        # Group count
        def count_groups():
            r = session.get(f"https://{VAULT_DNS}/api/{API_VERSION}/objects/groups", headers=vh, timeout=TIMEOUT)
            return len(r.json().get("groups", [])) if r.status_code == 200 else None
        report["vault"]["groups"] = safe(count_groups)
        
        # URS record count
        def count_urs():
            r = session.post(
                f"https://{VAULT_DNS}/api/{API_VERSION}/query",
                headers={**vh, "Content-Type": "application/x-www-form-urlencoded"},
                data={"q": "SELECT id FROM user_role_setup__v WHERE status__v = 'active__v'"},
                timeout=TIMEOUT,
            )
            return len(r.json().get("data", [])) if r.status_code == 200 else None
        report["vault"]["urs_records"] = safe(count_urs)
        
        # Tab config (for URL building)
        def count_tabs():
            r = session.get(f"https://{VAULT_DNS}/api/{API_VERSION}/configuration/Tab", headers=vh, timeout=TIMEOUT)
            if r.status_code != 200:
                return None
            tabs = r.json().get("data", [])
            obj_count = 0
            for t in tabs:
                for sub in t.get("subtabs", []):
                    if sub.get("object") or sub.get("object_type"):
                        obj_count += 1
            return obj_count
        report["metadata"]["object_tab_mappings"] = safe(count_tabs)
        
        # Object type labels
        def count_object_types():
            r = session.get(f"https://{VAULT_DNS}/api/{API_VERSION}/configuration/Objecttype", headers=vh, timeout=TIMEOUT)
            if r.status_code != 200:
                return None
            return len(r.json().get("data", []))
        ot = safe(count_object_types)
        report["metadata"]["object_type_labels"] = ot
        if ot == 0:
            report["alerts"].append({"severity": "warning", "message": "/configuration/Objecttype returned 0 results — user may lack Admin permissions"})
        
        # Picklists
        def count_picklists():
            r = session.get(f"https://{VAULT_DNS}/api/{API_VERSION}/objects/picklists", headers=vh, timeout=TIMEOUT)
            if r.status_code != 200:
                return None
            return len(r.json().get("picklists", []))
        report["metadata"]["picklists"] = safe(count_picklists)
        
        # Direct Data extract availability
        def check_direct_data():
            r = session.get(
                f"https://{VAULT_DNS}/api/{API_VERSION}/services/directdata/files",
                headers=vh,
                params={"extract_type": "full_directdata"},
                timeout=TIMEOUT,
            )
            if r.status_code != 200:
                return {"available": False, "status_code": r.status_code}
            data = r.json().get("data", [])
            ready = [d for d in data if d.get("filepart_details")]
            delayed = [d for d in data if d.get("error")]
            latest = ready[0] if ready else None
            return {
                "available": bool(ready),
                "ready_count": len(ready),
                "delayed_count": len(delayed),
                "latest_filename": latest.get("filename") if latest else None,
                "latest_stop_time": latest.get("stop_time") if latest else None,
            }
        report["vault"]["direct_data"] = safe(check_direct_data, {"available": False})
        
        # Document and object record counts
        def count_documents():
            r = session.get(
                f"https://{VAULT_DNS}/api/{API_VERSION}/objects/documents",
                headers=vh,
                params={"limit": 1},
                timeout=TIMEOUT,
            )
            if r.status_code != 200:
                return None
            return r.json().get("responseDetails", {}).get("total_count")
        report["vault"]["document_count"] = safe(count_documents)
        
        # Estimate object record counts for QMS objects
        qms_counts = {}
        qms_objects = [
            "deviation__v", "change_control__v", "nonconformance__v",
            "audit__qdm", "capa_action__qdm", "finding__v", "complaint__v",
            "quality_batch__v", "investigation__qdm",
        ]
        for obj_name in qms_objects:
            def count_obj(name=obj_name):
                r = session.post(
                    f"https://{VAULT_DNS}/api/{API_VERSION}/query",
                    headers={**vh, "Content-Type": "application/x-www-form-urlencoded"},
                    data={"q": f"SELECT COUNT() FROM {name}"},
                    timeout=TIMEOUT,
                )
                if r.status_code != 200:
                    return None
                data = r.json().get("data", [])
                return data[0].get("count") if data else 0
            c = safe(count_obj)
            if c is not None:
                qms_counts[obj_name] = c
        report["vault"]["qms_object_counts"] = qms_counts
        report["vault"]["qms_object_total"] = sum(qms_counts.values()) if qms_counts else 0
    
    # --- GLEAN CHECKS ---
    if GLEAN_URL and GLEAN_TOKEN:
        gh = {"Authorization": f"Bearer {GLEAN_TOKEN}", "Content-Type": "application/json"}
        
        # Datasource exists?
        def get_datasource():
            r = session.post(
                f"{GLEAN_URL}/api/index/v1/getdatasourceconfig",
                headers=gh,
                json={"datasource": DATASOURCE_NAME},
                timeout=TIMEOUT,
            )
            if r.status_code == 200:
                return r.json()
            return None
        
        ds = safe(get_datasource)
        if ds:
            report["glean"]["status"] = "ok"
            report["glean"]["datasource"] = DATASOURCE_NAME
            report["glean"]["object_definitions"] = len(ds.get("objectDefinitions", []))
        else:
            report["glean"]["status"] = "error"
            report["alerts"].append({"severity": "critical", "message": f"Datasource '{DATASOURCE_NAME}' not found or token invalid"})
    
    # --- DERIVED HEALTH SCORE ---
    score = 100
    if report["vault"]["status"] != "ok":
        score -= 50
    if report["glean"]["status"] != "ok":
        score -= 30
    if report["metadata"].get("object_type_labels") == 0:
        score -= 10
    if not report["vault"].get("direct_data", {}).get("available"):
        score -= 10
    report["health_score"] = max(score, 0)
    
    if score >= 90:
        report["overall_status"] = "healthy"
    elif score >= 60:
        report["overall_status"] = "degraded"
    else:
        report["overall_status"] = "unhealthy"
    
    report["duration_ms"] = int((time.time() - started) * 1000)
    
    print(json.dumps(report))


if __name__ == "__main__":
    main()
