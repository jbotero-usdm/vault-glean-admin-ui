import { NextRequest, NextResponse } from 'next/server';
import { isApiAuthorized } from '@/lib/auth';
import { triggerMonitorReport } from '@/lib/worker';

export async function POST(req: NextRequest) {
  if (!isApiAuthorized(req)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  
  const body = await req.json().catch(() => ({}));
  const userEmail = body.user_email || 'jbotero@partnersi-usdm.com';
  
  try {
    const job = await triggerMonitorReport(userEmail);
    return NextResponse.json(job);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
