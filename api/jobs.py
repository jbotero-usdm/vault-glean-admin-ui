import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "_scripts"))
from runner import list_jobs, check_password

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not check_password({k.lower(): v for k, v in self.headers.items()}):
            self.send_response(401); self.end_headers()
            self.wfile.write(b'[]')
            return
        
        jobs = list_jobs(20)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(jobs).encode())
