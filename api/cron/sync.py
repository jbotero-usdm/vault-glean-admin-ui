"""Nightly sync — Vercel calls this at 06:00 UTC."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "_scripts"))
from runner import run_script, check_password, notify_slack

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Vercel cron sends Authorization: Bearer ${CRON_SECRET}
        if not check_password({k.lower(): v for k, v in self.headers.items()}):
            self.send_response(401); self.end_headers()
            return
        
        notify_slack("⏰ Nightly Vault→Glean sync starting")
        job = run_script("incremental_sync_users_then_acl.py",
                         env_overrides={"STRICT_ACL": "true", "ACL_FALLBACK": "deny"},
                         job_type="Nightly Sync")
        
        if job["status"] == "success":
            metrics_str = " · ".join(f"{k}={v}" for k, v in (job.get("metrics") or {}).items())
            notify_slack(f"✅ Nightly sync complete — {metrics_str}")
        else:
            notify_slack(f"❌ Nightly sync failed: {job.get('error', 'unknown')}")
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(job).encode())
