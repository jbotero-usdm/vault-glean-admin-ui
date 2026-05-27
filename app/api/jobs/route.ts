import { NextRequest, NextResponse } from 'next/server';
import { isApiAuthorized } from '@/lib/auth';
import { listRecentJobs } from '@/lib/worker';

export async function GET(req: NextRequest) {
  if (!isApiAuthorized(req)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  
  try {
    const jobs = await listRecentJobs();
    return NextResponse.json(jobs);
  } catch (e: any) {
    return NextResponse.json([], { status: 200 });
  }
}
