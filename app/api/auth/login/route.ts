import { NextRequest, NextResponse } from 'next/server';
import { checkPassword, SESSION_COOKIE_NAME } from '@/lib/auth';

export async function POST(req: NextRequest) {
  const { password } = await req.json();
  
  if (!checkPassword(password)) {
    return NextResponse.json({ error: 'Invalid password' }, { status: 401 });
  }
  
  const res = NextResponse.json({ ok: true });
  res.cookies.set(SESSION_COOKIE_NAME, password, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 60 * 60 * 8,
    path: '/',
  });
  return res;
}
