import { NextRequest, NextResponse } from 'next/server';
import { isApiAuthorized } from '@/lib/auth';
import { getJobStatus } from '@/lib/worker';

export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  if (!isApiAuthorized(req)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  
  try {
    const job = await getJobStatus(params.id);
    return NextResponse.json(job);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
