const WORKER_URL = process.env.WORKER_URL!;
const WORKER_API_KEY = process.env.WORKER_API_KEY!;

export interface WorkerResponse {
  jobId: string;
  status: 'queued' | 'running' | 'success' | 'failure';
  startedAt?: string;
  finishedAt?: string;
  output?: string;
  metrics?: Record<string, any>;
  error?: string;
}

async function callWorker(path: string, body?: any): Promise<WorkerResponse> {
  const url = `${WORKER_URL}${path}`;
  const resp = await fetch(url, {
    method: body ? 'POST' : 'GET',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': WORKER_API_KEY,
    },
    body: body ? JSON.stringify(body) : undefined,
    // Vercel: don't cache worker responses
    cache: 'no-store',
  });
  
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Worker ${path} failed: ${resp.status} ${text.substring(0, 500)}`);
  }
  
  return resp.json();
}

export async function triggerSync(options: { force_full_reconcile?: boolean }): Promise<WorkerResponse> {
  return callWorker('/jobs/sync', options);
}

export async function triggerSecurityAudit(): Promise<WorkerResponse> {
  return callWorker('/jobs/security-audit');
}

export async function triggerMonitorReport(userEmail: string): Promise<WorkerResponse> {
  return callWorker('/jobs/monitor', { user_email: userEmail });
}

export async function getJobStatus(jobId: string): Promise<WorkerResponse> {
  return callWorker(`/jobs/${jobId}`);
}

export async function listRecentJobs(): Promise<WorkerResponse[]> {
  const resp = await fetch(`${WORKER_URL}/jobs?limit=20`, {
    headers: { 'X-API-Key': WORKER_API_KEY },
    cache: 'no-store',
  });
  if (!resp.ok) throw new Error(`Worker /jobs failed: ${resp.status}`);
  return resp.json();
}

export async function notifySlack(text: string, blocks?: any[]): Promise<void> {
  const url = process.env.SLACK_WEBHOOK_URL;
  if (!url) return;
  
  try {
    await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, blocks }),
    });
  } catch (e) {
    console.error('Slack notify failed:', e);
  }
}
