import './globals.css';
import { Outfit } from 'next/font/google';
import Link from 'next/link';

const outfit = Outfit({ subsets: ['latin'] });

export const metadata = {
  title: 'Hisse Bot Admin',
  description: 'Telegram Hisse Bot Yönetim Paneli',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="tr">
      <body className={outfit.className}>
        <div className="sidebar glass-panel">
          <div style={{ marginBottom: '3rem', fontSize: '1.5rem', fontWeight: 700, background: 'linear-gradient(to right, #3b82f6, #8b5cf6)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            Hisse Bot Admin
          </div>
          <nav>
            <Link href="/" className="nav-link">
              📊 Dashboard
            </Link>
            <Link href="/users" className="nav-link">
              👥 Kullanıcılar
            </Link>
            <Link href="/alerts" className="nav-link">
              🔔 Hisse Uyarıları
            </Link>
          </nav>
        </div>
        <main className="main-content">
          {children}
        </main>
      </body>
    </html>
  );
}
