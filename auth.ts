import { cookies } from 'next/headers';
import { NextRequest } from 'next/server';

const SESSION_COOKIE = 'vault_admin_session';

/**
 * Compare a cookie value (which may be URL-encoded) to the expected password.
 * Browsers automatically percent-encode special characters in cookies, so a
 * password like "Letmein@828" gets stored as "Letmein%40828" — a raw equality
 * check would fail. We decode the cookie value before comparing.
 */
function cookieMatches(cookieValue: string | undefined, expected: string | undefined): boolean {
  if (!cookieValue || !expected) return false;
  // Try raw first (common case where no special chars present)
  if (cookieValue === expected) return true;
  // Then try URL-decoded
  try {
    return decodeURIComponent(cookieValue) === expected;
  } catch {
    return false;
  }
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
  // Allow if browser session cookie matches (handle URL-encoded chars)
  const sessionCookie = req.cookies.get(SESSION_COOKIE);
  if (cookieMatches(sessionCookie?.value, process.env.ADMIN_PASSWORD)) return true;
  
  // Allow internal cron with secret
  const auth = req.headers.get('authorization');
  if (auth === `Bearer ${process.env.CRON_SECRET}`) return true;
  
  return false;
}

export const SESSION_COOKIE_NAME = SESSION_COOKIE;
