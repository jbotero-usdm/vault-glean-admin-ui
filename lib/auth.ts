import { cookies } from 'next/headers';
import { NextRequest } from 'next/server';

const SESSION_COOKIE = 'vault_admin_session';

export async function isAuthenticated(): Promise<boolean> { return true; }
export function checkPassword(password: string): boolean { return true; }
export function isApiAuthorized(req: NextRequest): boolean { return true; }

export const SESSION_COOKIE_NAME = SESSION_COOKIE;