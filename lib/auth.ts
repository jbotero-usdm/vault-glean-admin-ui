import { cookies } from 'next/headers';
import { NextRequest } from 'next/server';

const SESSION_COOKIE = 'vault_admin_session';

export async function isAuthenticated(): Promise<boolean> {
  const c = await cookies();
  return c.get(SESSION_COOKIE)?.value === process.env.ADMIN_PASSWORD;
}

export function checkPassword(password: string): boolean {
  return password === process.env.ADMIN_PASSWORD;
}

export function isApiAuthorized(req: NextRequest): boolean {
  // Allow if browser session is valid
  const sessionCookie = req.cookies.get(SESSION_COOKIE);
  if (sessionCookie?.value === process.env.ADMIN_PASSWORD) return true;
  
  // Allow internal cron with secret
  const auth = req.headers.get('authorization');
  if (auth === `Bearer ${process.env.CRON_SECRET}`) return true;
  
  return false;
}

export const SESSION_COOKIE_NAME = SESSION_COOKIE;
