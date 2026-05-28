import { NextRequest, NextResponse } from 'next/server';
import { isApiAuthorized } from '@/lib/auth';
import { execFile } from 'child_process';
import { promisify } from 'util';
import path from 'path';

const execFileAsync = promisify(execFile);

export const maxDuration = 30; // Vercel function timeout

export async function GET(req: NextRequest) {
  if (!isApiAuthorized(req)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  
  const scriptPath = path.join(process.cwd(), '_scripts', 'health_check.py');
  
  try {
    const { stdout } = await execFileAsync('python3', [scriptPath], {
      timeout: 25000,
      env: { ...process.env },
      maxBuffer: 1024 * 1024 * 2, // 2 MB buffer
    });
    
    // Parse JSON output from the script
    const report = JSON.parse(stdout.trim().split('\n').pop() || '{}');
    return NextResponse.json(report);
  } catch (e: any) {
    return NextResponse.json({
      error: 'Health check failed',
      message: e.message,
      overall_status: 'unhealthy',
      health_score: 0,
    }, { status: 500 });
  }
}
