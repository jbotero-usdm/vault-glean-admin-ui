import { cookies } from 'next/headers';
import { NextRequest } from 'next/server';

const SESSION_COOKIE = 'vault_admin_session';

function cookieMatches(cookieValue: string | undefined, expected: string | undefined): boolean {
  if (!cookieValue || !expected) return false;
  if (cookieValue === expected) return true;
  try {
    if (decodeURIComponent(cookieValue) === expected) return true;
  } catch {}
  try {
    if (cookieValue === encodeURIComponent(expected)) return true;
  } catch {}
  return false;
}

export async function isAuthenticated(): Promise<boolean> {
  const c = await cookies();
  const cookieValue = c.get(SESSION_COOKIE)?.value;
  return cookieMatches(cookieValue, process.env.ADMIN_PASSWORD);
}

export function checkPassword(password: string): boolean {
  return password === process.env.ADMIN_PASSWORD;
}

export function isApiAuthorized(req: NextRequest): boolean {
  const sessionCookie = req.cookies.get(SESSION_COOKIE);
  const expected = process.env.ADMIN_PASSWORD;
  const got = sessionCookie?.value;
  
  console.log(`[auth] cookie present: ${!!got}, length: ${got?.length}, expected length: ${expected?.length}, match: ${cookieMatches(got, expected)}`);
  
  if (cookieMatches(got, expected)) return true;
  
  const auth = req.headers.get('authorization');
  if (auth === `Bearer ${process.env.CRON_SECRET}`) return true;
  
  return false;
}

export const SESSION_COOKIE_NAME = SESSION_COOKIE;
