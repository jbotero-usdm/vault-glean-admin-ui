import { NextRequest, NextResponse } from 'next/server';
import { isApiAuthorized } from '@/lib/auth';
import { triggerSync, notifySlack } from '@/lib/worker';

export async function POST(req: NextRequest) {
  if (!isApiAuthorized(req)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  
  const body = await req.json().catch(() => ({}));
  const force = !!body.force_full_reconcile;
  
  try {
    const job = await triggerSync({ force_full_reconcile: force });
    
    notifySlack(
      `🔄 Vault→Glean sync started ${force ? '(force full reconcile)' : '(incremental)'}\nJob ID: \`${job.jobId}\``
    );
    
    return NextResponse.json(job);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
