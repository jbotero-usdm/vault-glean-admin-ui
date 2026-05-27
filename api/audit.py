import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "_scripts"))
from runner import run_script, check_password

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not check_password({k.lower(): v for k, v in self.headers.items()}):
            self.send_response(401); self.end_headers()
            self.wfile.write(b'{"error":"Unauthorized"}')
            return
        
        job = run_script("vault_security_apply_gxp.py",
                         extra_args=["--audit-only"],
                         job_type="Vault Security Audit")
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(job).encode())
