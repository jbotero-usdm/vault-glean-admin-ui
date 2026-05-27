"""POST /api/sync — runs the Vault→Glean sync. Up to 13 minutes."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "_scripts"))
from runner import run_script, check_password, notify_slack

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not check_password({k.lower(): v for k, v in self.headers.items()}):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":"Unauthorized"}')
            return
        
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length) or b'{}') if length else {}
        force = body.get('force_full_reconcile', False)
        
        env = {
            "FORCE_FULL_RECONCILE": "true" if force else "false",
            "STRICT_ACL": "true",
            "ACL_FALLBACK": "deny",
        }
        
        notify_slack(f"🔄 Vault→Glean sync started ({'force full' if force else 'incremental'})")
        
        job = run_script(
            "incremental_sync_users_then_acl.py",
            env_overrides=env,
            job_type=f"Vault → Glean Sync{' (Force Full)' if force else ''}",
        )
        
        if job["status"] == "success":
            metrics_str = " · ".join(f"{k}={v}" for k, v in (job.get("metrics") or {}).items())
            notify_slack(f"✅ Sync complete — {metrics_str}")
        else:
            notify_slack(f"❌ Sync failed: {job.get('error', 'unknown')}")
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(job).encode())
