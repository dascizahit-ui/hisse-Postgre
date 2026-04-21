import Link from 'next/link';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

async function logoutAction() {
  'use server';
  cookies().delete('admin_auth');
  redirect('/login');
}

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <div className="sidebar glass-panel" style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ marginBottom: '2.5rem', fontSize: '1.5rem', fontWeight: 700, background: 'linear-gradient(to right, #3b82f6, #8b5cf6)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
          Hisse Bot Admin
        </div>
        <nav style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <Link href="/" className="nav-link">📊 Dashboard</Link>
          <Link href="/users" className="nav-link">👥 Kullanıcılar</Link>
          <Link href="/alerts" className="nav-link">🔔 Uyarılar</Link>
          <Link href="/signals" className="nav-link">📡 Sinyaller</Link>
          <Link href="/reports" className="nav-link">🚨 Raporlar</Link>
          <Link href="/mutes" className="nav-link">🔇 Susturmalar</Link>
        </nav>
        <form action={logoutAction} style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--card-border)' }}>
          <button type="submit" style={{ width: '100%', background: 'transparent', border: 'none', textAlign: 'left', cursor: 'pointer', color: '#ef4444', padding: '0.75rem 1rem', borderRadius: '10px', fontSize: '0.95rem' }}>
            🚪 Çıkış Yap
          </button>
        </form>
      </div>
      <main className="main-content">
        {children}
      </main>
    </>
  );
}
