import prisma from '@/lib/prisma';
import { Signal, Radio, TrendingUp, Search, Users } from 'lucide-react';

export const dynamic = 'force-dynamic';

const PAGE_SIZE = 40;

type SearchParams = { q?: string; type?: string; page?: string; tab?: string };

function signalColor(type: string) {
  if (type === 'AL') return '#10b981';
  if (type === 'SAT') return '#ef4444';
  return '#9ca3af';
}

export default async function SignalsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const tab = sp.tab || 'history';
  const query = (sp.q || '').trim().toUpperCase();
  const type = sp.type || 'all';
  const page = Math.max(1, parseInt(sp.page || '1', 10) || 1);

  if (tab === 'subscriptions') {
    return <SubscriptionsTab query={query} page={page} />;
  }

  const where: any = {};
  if (query) where.symbol = { contains: query };
  if (type !== 'all') where.signal_type = type;

  const [totalCount, signals, alCount, satCount, bekleCount] = await Promise.all([
    prisma.hourlySignal.count({ where }),
    prisma.hourlySignal.findMany({
      where,
      orderBy: { created_at: 'desc' },
      skip: (page - 1) * PAGE_SIZE,
      take: PAGE_SIZE,
    }),
    prisma.hourlySignal.count({ where: { signal_type: 'AL' } }),
    prisma.hourlySignal.count({ where: { signal_type: 'SAT' } }),
    prisma.hourlySignal.count({ where: { signal_type: 'BEKLE' } }),
  ]);

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  return (
    <div>
      <h1 className="header-gradient" style={{ fontSize: '2.5rem', marginBottom: '2rem', fontWeight: 800 }}>Sinyaller</h1>

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
        <TabLink label="📊 Sinyal Geçmişi" active={tab === 'history'} href="/signals?tab=history" />
        <TabLink label="📡 Takipler" active={tab === 'subscriptions'} href="/signals?tab=subscriptions" />
      </div>

      <div className="card glass-panel" style={{ padding: '1rem', marginBottom: '1.5rem', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem' }}>
        <FilterLink label="📋 Hepsi" active={type === 'all'} value={alCount + satCount + bekleCount} href={`/signals?type=all${query ? `&q=${encodeURIComponent(query)}` : ''}`} />
        <FilterLink label="🟢 AL" active={type === 'AL'} value={alCount} href={`/signals?type=AL${query ? `&q=${encodeURIComponent(query)}` : ''}`} color="#10b981" />
        <FilterLink label="🔴 SAT" active={type === 'SAT'} value={satCount} href={`/signals?type=SAT${query ? `&q=${encodeURIComponent(query)}` : ''}`} color="#ef4444" />
        <FilterLink label="🟡 BEKLE" active={type === 'BEKLE'} value={bekleCount} href={`/signals?type=BEKLE${query ? `&q=${encodeURIComponent(query)}` : ''}`} color="#9ca3af" />
      </div>

      <form method="GET" className="card glass-panel" style={{ padding: '1rem', marginBottom: '1.5rem', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
        <Search size={18} style={{ opacity: 0.5 }} />
        <input
          type="text"
          name="q"
          defaultValue={query}
          placeholder="Hisse sembolüne göre ara..."
          style={{
            flex: 1,
            padding: '0.6rem 0.75rem',
            borderRadius: '8px',
            border: '1px solid var(--card-border)',
            background: 'rgba(255,255,255,0.03)',
            color: 'var(--foreground)',
            fontSize: '0.9rem',
            outline: 'none',
            fontFamily: 'inherit',
            textTransform: 'uppercase',
          }}
        />
        <input type="hidden" name="type" value={type} />
        <input type="hidden" name="tab" value="history" />
        <button type="submit" className="btn-primary" style={{ border: 'none' }}>Ara</button>
        {query && <a href={`/signals?type=${type}`} style={{ color: '#9ca3af', fontSize: '0.85rem', textDecoration: 'none' }}>Temizle</a>}
      </form>

      <div className="card glass-panel">
        <div className="card-header">
          <Signal size={20} className="icon-blue" />
          <h2>Sinyal Geçmişi ({totalCount})</h2>
        </div>
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Hisse</th>
                <th>Sinyal</th>
                <th>Fiyat</th>
                <th>Güç</th>
                <th>RSI</th>
                <th>MACD</th>
                <th>BB</th>
                <th>EMA Kesişim</th>
                <th>Tarih</th>
              </tr>
            </thead>
            <tbody>
              {signals.length === 0 && (
                <tr><td colSpan={9} style={{ textAlign: 'center', opacity: 0.5, padding: '2rem' }}>Sinyal bulunamadı</td></tr>
              )}
              {signals.map((s: any) => (
                <tr key={s.id}>
                  <td style={{ fontWeight: 800, color: '#3b82f6' }}>{s.symbol}</td>
                  <td>
                    <span className="status-badge" style={{ background: `${signalColor(s.signal_type)}20`, color: signalColor(s.signal_type) }}>
                      {s.signal_type}
                    </span>
                  </td>
                  <td style={{ fontWeight: 600 }}>{s.price.toFixed(2)} ₺</td>
                  <td>{s.signal_strength}/10</td>
                  <td style={{ color: s.rsi > 70 ? '#ef4444' : s.rsi < 30 ? '#10b981' : 'inherit' }}>{s.rsi.toFixed(1)}</td>
                  <td style={{ color: s.macd > 0 ? '#10b981' : '#ef4444' }}>{s.macd.toFixed(4)}</td>
                  <td style={{ fontSize: '0.8rem' }}>{s.bb_position}</td>
                  <td>{s.ema_cross ? '✓' : '-'}</td>
                  <td style={{ opacity: 0.6, fontSize: '0.85rem' }}>{s.created_at.toLocaleString('tr-TR')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', padding: '1rem', alignItems: 'center' }}>
            <PageLink page={page - 1} disabled={page === 1} label="← Önceki" params={sp} tab="history" />
            <span style={{ opacity: 0.6, fontSize: '0.85rem', padding: '0 1rem' }}>Sayfa {page} / {totalPages}</span>
            <PageLink page={page + 1} disabled={page >= totalPages} label="Sonraki →" params={sp} tab="history" />
          </div>
        )}
      </div>
    </div>
  );
}

async function SubscriptionsTab({ query, page }: { query: string; page: number }) {
  const where: any = { is_active: 1 };
  if (query) where.symbol = { contains: query };

  const [totalCount, subscriptions, bySymbol] = await Promise.all([
    prisma.signalSubscription.count({ where }),
    prisma.signalSubscription.findMany({
      where,
      include: { user: true },
      orderBy: { subscribed_at: 'desc' },
      skip: (page - 1) * PAGE_SIZE,
      take: PAGE_SIZE,
    }),
    prisma.signalSubscription.groupBy({
      by: ['symbol'],
      where: { is_active: 1 },
      _count: { symbol: true },
      orderBy: { _count: { symbol: 'desc' } },
      take: 10,
    }),
  ]);

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  return (
    <div>
      <h1 className="header-gradient" style={{ fontSize: '2.5rem', marginBottom: '2rem', fontWeight: 800 }}>Sinyaller</h1>

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
        <TabLink label="📊 Sinyal Geçmişi" active={false} href="/signals?tab=history" />
        <TabLink label="📡 Takipler" active={true} href="/signals?tab=subscriptions" />
      </div>

      <div className="card-container two-columns">
        <div className="card glass-panel">
          <div className="card-header">
            <Radio size={20} className="icon-green" />
            <h2>Aktif Takipler ({totalCount})</h2>
          </div>

          <form method="GET" style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
            <input
              type="text"
              name="q"
              defaultValue={query}
              placeholder="Sembol ara..."
              style={{
                flex: 1,
                padding: '0.5rem 0.75rem',
                borderRadius: '8px',
                border: '1px solid var(--card-border)',
                background: 'rgba(255,255,255,0.03)',
                color: 'var(--foreground)',
                fontSize: '0.85rem',
                outline: 'none',
                textTransform: 'uppercase',
              }}
            />
            <input type="hidden" name="tab" value="subscriptions" />
            <button type="submit" className="btn-primary" style={{ border: 'none', padding: '0.5rem 1rem', fontSize: '0.85rem' }}>Ara</button>
          </form>

          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Kullanıcı</th>
                  <th>Sembol</th>
                  <th>Takip Tarihi</th>
                </tr>
              </thead>
              <tbody>
                {subscriptions.length === 0 && (
                  <tr><td colSpan={3} style={{ textAlign: 'center', opacity: 0.5, padding: '2rem' }}>Takip yok</td></tr>
                )}
                {subscriptions.map((sub: any) => (
                  <tr key={`${sub.user_id.toString()}-${sub.symbol}`}>
                    <td>
                      <div className="user-info">
                        <div className="user-avatar" style={{ width: '28px', height: '28px', fontSize: '0.7rem' }}>
                          {sub.user?.username?.[0]?.toUpperCase() || '?'}
                        </div>
                        <div>
                          <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>{sub.user?.username || 'İsimsiz'}</div>
                          <div style={{ fontSize: '0.7rem', opacity: 0.5 }}><code>{sub.user_id.toString()}</code></div>
                        </div>
                      </div>
                    </td>
                    <td style={{ fontWeight: 700, color: '#3b82f6' }}>{sub.symbol}</td>
                    <td style={{ fontSize: '0.85rem', opacity: 0.6 }}>{sub.subscribed_at.toLocaleString('tr-TR')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', padding: '1rem', alignItems: 'center' }}>
              <PageLink page={page - 1} disabled={page === 1} label="←" params={{ tab: 'subscriptions', q: query }} tab="subscriptions" />
              <span style={{ opacity: 0.6, fontSize: '0.85rem' }}>{page} / {totalPages}</span>
              <PageLink page={page + 1} disabled={page >= totalPages} label="→" params={{ tab: 'subscriptions', q: query }} tab="subscriptions" />
            </div>
          )}
        </div>

        <div className="card glass-panel">
          <div className="card-header">
            <Users size={20} className="icon-purple" />
            <h2>En Popüler 10</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {bySymbol.length === 0 && <div style={{ opacity: 0.5, textAlign: 'center' }}>Takip edilen hisse yok</div>}
            {bySymbol.map((s, i) => (
              <div key={s.symbol} className="system-item" style={{ padding: '0.5rem 0.75rem', borderRadius: '8px', background: 'rgba(255,255,255,0.02)' }}>
                <div className="system-label" style={{ fontWeight: 600 }}>
                  <span style={{ opacity: 0.4, marginRight: '0.5rem' }}>{i + 1}.</span>
                  {s.symbol}
                </div>
                <div className="system-status fast">{s._count.symbol} takipçi</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function TabLink({ label, active, href }: { label: string; active: boolean; href: string }) {
  return (
    <a
      href={href}
      style={{
        padding: '0.6rem 1.25rem',
        borderRadius: '10px',
        textDecoration: 'none',
        fontSize: '0.9rem',
        fontWeight: 600,
        background: active ? 'rgba(59,130,246,0.15)' : 'rgba(255,255,255,0.03)',
        color: active ? '#3b82f6' : 'rgba(255,255,255,0.6)',
        border: `1px solid ${active ? 'rgba(59,130,246,0.3)' : 'var(--card-border)'}`,
      }}
    >
      {label}
    </a>
  );
}

function FilterLink({ label, active, value, href, color }: { label: string; active: boolean; value: number; href: string; color?: string }) {
  return (
    <a href={href} style={{ textDecoration: 'none' }}>
      <div className="system-item" style={{ padding: '0.5rem', borderRadius: '10px', background: active ? 'rgba(59,130,246,0.1)' : 'transparent' }}>
        <div className="system-label" style={{ color: active ? '#3b82f6' : 'inherit', fontWeight: active ? 700 : 500 }}>{label}</div>
        <div className="system-status" style={{ color: color || '#3b82f6', background: `${color || '#3b82f6'}15` }}>{value}</div>
      </div>
    </a>
  );
}

function PageLink({ page, disabled, label, params, tab }: { page: number; disabled: boolean; label: string; params: any; tab: string }) {
  if (disabled) return <span style={{ opacity: 0.3, padding: '0.5rem 1rem' }}>{label}</span>;
  const sp = new URLSearchParams();
  if (params.q) sp.set('q', params.q);
  if (params.type) sp.set('type', params.type);
  sp.set('tab', tab);
  sp.set('page', String(page));
  return (
    <a href={`/signals?${sp.toString()}`} style={{ padding: '0.5rem 1rem', borderRadius: '8px', background: 'rgba(59,130,246,0.1)', color: '#3b82f6', textDecoration: 'none', fontSize: '0.85rem' }}>
      {label}
    </a>
  );
}
