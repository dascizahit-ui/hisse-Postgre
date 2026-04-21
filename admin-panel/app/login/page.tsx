import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { Lock, AlertCircle } from 'lucide-react';

export const dynamic = 'force-dynamic';

async function loginAction(formData: FormData) {
  'use server';
  const password = formData.get('password') as string;
  const from = (formData.get('from') as string) || '/';
  const expected = process.env.ADMIN_PASSWORD;

  if (!expected) {
    redirect('/login?error=no-password-set');
  }

  if (password !== expected) {
    redirect('/login?error=wrong-password');
  }

  const cookieStore = await cookies();
  cookieStore.set('admin_auth', password, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
    maxAge: 60 * 60 * 24 * 7, // 7 gün
  });

  redirect(from);
}

type LoginSearch = { error?: string; from?: string };

export default async function LoginPage({ searchParams }: { searchParams: Promise<LoginSearch> }) {
  const params = await searchParams;
  const error = params.error;
  const errorMessage =
    error === 'no-password-set'
      ? 'Sunucuda ADMIN_PASSWORD ayarlanmamış. Lütfen .env dosyasına ekleyin.'
      : error === 'wrong-password'
      ? 'Yanlış şifre.'
      : null;

  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: '2rem' }}>
      <div className="card glass-panel" style={{ width: '100%', maxWidth: '400px', padding: '2.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1.5rem' }}>
          <div style={{ background: 'rgba(59,130,246,0.1)', padding: '1rem', borderRadius: '50%' }}>
            <Lock size={32} className="icon-blue" />
          </div>
        </div>
        <h1 className="header-gradient" style={{ fontSize: '1.75rem', fontWeight: 800, textAlign: 'center', marginBottom: '0.5rem' }}>
          Yönetici Girişi
        </h1>
        <p style={{ textAlign: 'center', opacity: 0.6, fontSize: '0.9rem', marginBottom: '2rem' }}>
          Devam etmek için şifrenizi girin
        </p>

        {errorMessage && (
          <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid #ef4444', borderRadius: '10px', padding: '0.75rem', marginBottom: '1rem', color: '#ef4444', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <AlertCircle size={16} />
            {errorMessage}
          </div>
        )}

        <form action={loginAction} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <input type="hidden" name="from" value={params.from || '/'} />
          <input
            type="password"
            name="password"
            placeholder="Şifre"
            required
            autoFocus
            style={{
              padding: '0.85rem 1rem',
              borderRadius: '10px',
              border: '1px solid var(--card-border)',
              background: 'rgba(255,255,255,0.03)',
              color: 'var(--foreground)',
              fontSize: '1rem',
              outline: 'none',
              fontFamily: 'inherit',
            }}
          />
          <button
            type="submit"
            className="btn-primary"
            style={{ padding: '0.85rem', fontSize: '1rem', fontWeight: 600, border: 'none' }}
          >
            Giriş Yap
          </button>
        </form>
      </div>
    </div>
  );
}
