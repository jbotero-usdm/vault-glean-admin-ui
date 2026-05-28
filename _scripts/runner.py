"""Shared script runner used by all Vercel Python functions."""
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

# Vercel ephemeral storage at /tmp (max 512 MB, persists for warm function lifetime)
JOBS_DIR = Path("/tmp/jobs")
JOBS_DIR.mkdir(parents=True, exist_ok=True)

# Vercel includes _scripts/ in the deployment, scripts live here too
SCRIPT_DIR = Path(__file__).parent


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_file(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def write_job(job: dict):
    with open(job_file(job["jobId"]), "w") as f:
        json.dump(job, f)


def read_job(job_id: str) -> Optional[dict]:
    f = job_file(job_id)
    if not f.exists():
        return None
    with open(f) as fp:
        return json.load(fp)


def list_jobs(limit: int = 20) -> list:
    files = sorted(JOBS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    out = []
    for f in files:
        try:
            out.append(json.load(open(f)))
        except Exception:
            pass
    return out


def parse_metrics(output: str) -> dict:
    metrics = {}
    for line in output.splitlines():
        line = line.strip()
        if ":" in line:
            label, _, value = line.partition(":")
            label = label.strip().lstrip("✓✗⚠ ").lower().replace(" ", "_")
            value = value.strip()
            if value.isdigit():
                metrics[label] = int(value)
    return metrics


def run_script(script_name: str, env_overrides: dict = None, extra_args: List[str] = None,
               job_type: str = "Script Run") -> dict:
    """Run a script synchronously and return the job record."""
    job_id = str(uuid.uuid4())[:12]
    job = {
        "jobId": job_id,
        "type": job_type,
        "status": "running",
        "startedAt": now_iso(),
    }
    write_job(job)
    
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    
    script_path = SCRIPT_DIR / script_name
    cmd = [sys.executable, str(script_path)]
    if extra_args:
        cmd.extend(extra_args)
    
    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("SCRIPT_TIMEOUT", "780")),
            cwd=str(SCRIPT_DIR),
        )
        output = result.stdout + (("\n--- STDERR ---\n" + result.stderr) if result.stderr else "")
        job["output"] = output[-20000:]
        job["metrics"] = parse_metrics(output)
        job["finishedAt"] = now_iso()
        if result.returncode == 0:
            job["status"] = "success"
        else:
            job["status"] = "failure"
            job["error"] = f"Exit code {result.returncode}"
    except subprocess.TimeoutExpired:
        job["status"] = "failure"
        job["error"] = "Script timeout"
        job["finishedAt"] = now_iso()
    except Exception as e:
        job["status"] = "failure"
        job["error"] = str(e)
        job["finishedAt"] = now_iso()
    
    write_job(job)
    return job


def check_password(req_headers: dict) -> bool:
    """BYPASSED — Python auth disabled, matches Next.js bypass in lib/auth.ts."""
    return True


def notify_slack(text: str):
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        return
    try:
        import urllib.request
        data = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(webhook, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass
