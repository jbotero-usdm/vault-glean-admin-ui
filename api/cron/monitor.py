"""Nightly monitor — 06:30 UTC."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "_scripts"))
from runner import run_script, check_password

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not check_password({k.lower(): v for k, v in self.headers.items()}):
            self.send_response(401); self.end_headers()
            return
        
        job = run_script("glean_monitor.py",
                         extra_args=["--user-email", "jbotero@partnersi-usdm.com"],
                         job_type="Nightly Monitor")
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(job).encode())
