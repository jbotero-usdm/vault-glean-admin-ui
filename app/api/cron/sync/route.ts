import { NextRequest, NextResponse } from 'next/server';
import { triggerSync, notifySlack } from '@/lib/worker';

// Vercel automatically injects Authorization: Bearer ${CRON_SECRET}
function isCronAuthorized(req: NextRequest): boolean {
  const auth = req.headers.get('authorization');
  return auth === `Bearer ${process.env.CRON_SECRET}`;
}

export async function GET(req: NextRequest) {
  if (!isCronAuthorized(req)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  
  try {
    const job = await triggerSync({ force_full_reconcile: false });
    
    notifySlack(
      `⏰ Nightly Vault→Glean sync started\nJob ID: \`${job.jobId}\``
    );
    
    return NextResponse.json({ ok: true, jobId: job.jobId });
  } catch (e: any) {
    notifySlack(`❌ Nightly sync failed to start: ${e.message}`);
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
