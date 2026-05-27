import { NextRequest, NextResponse } from 'next/server';
import { notifySlack } from '@/lib/worker';

export async function POST(req: NextRequest) {
  const apiKey = req.headers.get('x-api-key');
  if (apiKey !== process.env.WORKER_API_KEY) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  
  const { jobId, type, status, metrics, error } = await req.json();
  
  // Notify Slack on completion
  if (status === 'success') {
    const metricSummary = metrics 
      ? Object.entries(metrics).map(([k, v]) => `${k}=${v}`).join(' · ')
      : '';
    notifySlack(`✅ ${type} completed (${jobId})\n${metricSummary}`);
  } else if (status === 'failure') {
    notifySlack(`❌ ${type} FAILED (${jobId})\n${error || 'No error message'}`);
  }
  
  return NextResponse.json({ ok: true });
}
