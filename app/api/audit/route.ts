import { NextRequest, NextResponse } from 'next/server';
import { isApiAuthorized } from '@/lib/auth';
import { triggerSecurityAudit } from '@/lib/worker';

export async function POST(req: NextRequest) {
  if (!isApiAuthorized(req)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  
  try {
    const job = await triggerSecurityAudit();
    return NextResponse.json(job);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
