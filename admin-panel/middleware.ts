import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Login sayfası + Next iç endpointleri serbest
  if (
    pathname.startsWith('/login') ||
    pathname.startsWith('/_next') ||
    pathname.startsWith('/api/login') ||
    pathname === '/favicon.ico'
  ) {
    return NextResponse.next();
  }

  const auth = req.cookies.get('admin_auth')?.value;
  const expected = process.env.ADMIN_PASSWORD;

  if (!expected) {
    // ADMIN_PASSWORD ayarlanmamışsa panel kilitli
    const url = req.nextUrl.clone();
    url.pathname = '/login';
    url.searchParams.set('error', 'no-password-set');
    return NextResponse.redirect(url);
  }

  if (auth !== expected) {
    const url = req.nextUrl.clone();
    url.pathname = '/login';
    url.searchParams.set('from', pathname);
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
