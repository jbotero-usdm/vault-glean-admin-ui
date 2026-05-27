import { NextRequest, NextResponse } from 'next/server';
import { triggerMonitorReport, notifySlack } from '@/lib/worker';

function isCronAuthorized(req: NextRequest): boolean {
  const auth = req.headers.get('authorization');
  return auth === `Bearer ${process.env.CRON_SECRET}`;
}

export async function GET(req: NextRequest) {
  if (!isCronAuthorized(req)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  
  try {
    const job = await triggerMonitorReport('jbotero@partnersi-usdm.com');
    return NextResponse.json({ ok: true, jobId: job.jobId });
  } catch (e: any) {
    notifySlack(`❌ Daily monitor report failed to start: ${e.message}`);
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
