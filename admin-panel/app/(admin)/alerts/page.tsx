import prisma from '@/lib/prisma';
import { Bell, TrendingUp, TrendingDown, Trash2, Search } from 'lucide-react';
import { revalidatePath } from 'next/cache';

export const dynamic = 'force-dynamic';

const PAGE_SIZE = 30;

type SearchParams = { q?: string; page?: string; status?: string };

async function cancelAlertAction(formData: FormData) {
  'use server';
  const alertId = parseInt(formData.get('alertId') as string, 10);
  try {
    await prisma.alert.update({ where: { id: alertId }, data: { is_active: 0 } });
    revalidatePath('/alerts');
  } catch (e) {
    console.error('Cancel alert error:', e);
  }
}

async function deleteAlertAction(formData: FormData) {
  'use server';
  const alertId = parseInt(formData.get('alertId') as string, 10);
  try {
    await prisma.alert.delete({ where: { id: alertId } });
    revalidatePath('/alerts');
  } catch (e) {
    console.error('Delete alert error:', e);
  }
}

function directionInfo(direction: string) {
  if (direction === 'above' || direction === 'yukari')
    return { text: 'Üstüne çıkınca', color: '#10b981', icon: TrendingUp };
  if (direction === 'below' || direction === 'asagi')
    return { text: 'Altına inince', color: '#ef4444', icon: TrendingDown };
  return { text: direction, color: '#9ca3af', icon: TrendingUp };
}

export default async function AlertsPage({ searchParams }: { searchParams: SearchParams }) {
  const query = (searchParams.q || '').trim().toUpperCase();
  const page = Math.max(1, parseInt(searchParams.page || '1', 10) || 1);
  const status = searchParams.status || 'all';

  const where: any = {};
  if (query) where.symbol = { contains: query };
  if (status === 'active') where.is_active = 1;
  else if (status === 'completed') where.is_active = 0;

  const [totalCount, alerts, activeCount, completedCount] = await Promise.all([
    prisma.alert.count({ where }),
    prisma.alert.findMany({
      where,
      include: { user: true },
      orderBy: { created_at: 'desc' },
      skip: (page - 1) * PAGE_SIZE,
      take: PAGE_SIZE,
    }),
    prisma.alert.count({ where: { is_active: 1 } }),
    prisma.alert.count({ where: { is_active: 0 } }),
  ]);

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  return (
    <div>
      <h1 className="header-gradient" style={{ fontSize: '2.5rem', marginBottom: '2rem', fontWeight: 800 }}>Hisse Uyarıları</h1>

      <div className="card glass-panel" style={{ padding: '1rem', marginBottom: '1.5rem', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1.5rem' }}>
        <FilterLink label="📋 Tümü" active={status === 'all'} value={totalCount} href={`/alerts?status=all${query ? `&q=${encodeURIComponent(query)}` : ''}`} />
        <FilterLink label="⏳ Beklemede" active={status === 'active'} value={activeCount} href={`/alerts?status=active${query ? `&q=${encodeURIComponent(query)}` : ''}`} color="#10b981" />
        <FilterLink label="✔ Tamamlanan" active={status === 'completed'} value={completedCount} href={`/alerts?status=completed${query ? `&q=${encodeURIComponent(query)}` : ''}`} color="#9ca3af" />
      </div>

      <form method="GET" className="card glass-panel" style={{ padding: '1rem', marginBottom: '1.5rem', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
        <Search size={18} style={{ opacity: 0.5 }} />
        <input
          type="text"
          name="q"
          defaultValue={query}
          placeholder="Hisse sembolüne göre ara (ör. THYAO)..."
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
        <input type="hidden" name="status" value={status} />
        <button type="submit" className="btn-primary" style={{ border: 'none' }}>Ara</button>
        {query && <a href={`/alerts?status=${status}`} style={{ color: '#9ca3af', fontSize: '0.85rem', textDecoration: 'none' }}>Temizle</a>}
      </form>

      <div className="card glass-panel">
        <div className="card-header">
          <Bell size={20} className="icon-blue" />
          <h2>Uyarı Listesi ({totalCount})</h2>
        </div>

        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Kullanıcı</th>
                <th>Sembol</th>
                <th>Hedef Fiyat</th>
                <th>Yön</th>
                <th>Durum</th>
                <th>Tarih</th>
                <th style={{ textAlign: 'right' }}>İşlem</th>
              </tr>
            </thead>
            <tbody>
              {alerts.length === 0 && (
                <tr><td colSpan={7} style={{ textAlign: 'center', opacity: 0.5, padding: '2rem' }}>Uyarı bulunamadı</td></tr>
              )}
              {alerts.map((alert: any) => {
                const dir = directionInfo(alert.direction);
                const Icon = dir.icon;
                const isActive = alert.is_active === 1;
                return (
                  <tr key={alert.id}>
                    <td>
                      <div className="user-info">
                        <div className="user-avatar" style={{ width: '32px', height: '32px', fontSize: '0.8rem' }}>
                          {alert.user?.username?.[0]?.toUpperCase() || '?'}
                        </div>
                        <div>
                          <div className="user-name" style={{ fontSize: '0.9rem' }}>{alert.user?.username || 'İsimsiz'}</div>
                          <div className="user-date" style={{ fontSize: '0.7rem' }}><code>{alert.user_id.toString()}</code></div>
                        </div>
                      </div>
                    </td>
                    <td style={{ fontWeight: 800, color: '#3b82f6' }}>{alert.symbol}</td>
                    <td style={{ fontWeight: 600 }}>{alert.price.toFixed(2)} ₺</td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: dir.color, fontSize: '0.85rem' }}>
                        <Icon size={14} /> {dir.text}
                      </div>
                    </td>
                    <td>
                      {isActive ? (
                        <span className="status-badge status-active">BEKLEMEDE</span>
                      ) : (
                        <span className="status-badge" style={{ background: 'rgba(156,163,175,0.1)', color: '#9ca3af' }}>TAMAMLANDI</span>
                      )}
                    </td>
                    <td style={{ opacity: 0.6, fontSize: '0.85rem' }}>{alert.created_at?.toLocaleString('tr-TR')}</td>
                    <td>
                      <div className="action-row" style={{ justifyContent: 'flex-end' }}>
                        {isActive && (
                          <form action={cancelAlertAction}>
                            <input type="hidden" name="alertId" value={alert.id} />
                            <button type="submit" title="İptal Et" style={{ padding: '0.4rem 0.6rem', borderRadius: '8px', background: 'transparent', border: '1px solid rgba(245,158,11,0.4)', color: '#f59e0b', cursor: 'pointer', fontSize: '0.8rem' }}>
                              İptal
                            </button>
                          </form>
                        )}
                        <form action={deleteAlertAction}>
                          <input type="hidden" name="alertId" value={alert.id} />
                          <button type="submit" title="Sil" style={{ padding: '0.4rem', display: 'flex', alignItems: 'center', borderRadius: '8px', background: 'transparent', border: '1px solid rgba(239,68,68,0.3)', color: '#fca5a5', cursor: 'pointer' }}>
                            <Trash2 size={16} />
                          </button>
                        </form>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', padding: '1rem', alignItems: 'center' }}>
            <PageLink page={page - 1} disabled={page === 1} label="← Önceki" params={searchParams} />
            <span style={{ opacity: 0.6, fontSize: '0.85rem', padding: '0 1rem' }}>Sayfa {page} / {totalPages}</span>
            <PageLink page={page + 1} disabled={page >= totalPages} label="Sonraki →" params={searchParams} />
          </div>
        )}
      </div>
    </div>
  );
}

function FilterLink({ label, active, value, href, color }: { label: string; active: boolean; value: number; href: string; color?: string }) {
  return (
    <a href={href} style={{ textDecoration: 'none' }}>
      <div className="system-item" style={{ padding: '0.5rem', borderRadius: '10px', background: active ? 'rgba(59,130,246,0.1)' : 'transparent', transition: '0.2s' }}>
        <div className="system-label" style={{ color: active ? '#3b82f6' : 'inherit', fontWeight: active ? 700 : 500 }}>{label}</div>
        <div className="system-status" style={{ color: color || '#3b82f6', background: `${color || '#3b82f6'}15` }}>{value}</div>
      </div>
    </a>
  );
}

function PageLink({ page, disabled, label, params }: { page: number; disabled: boolean; label: string; params: SearchParams }) {
  if (disabled) return <span style={{ opacity: 0.3, padding: '0.5rem 1rem' }}>{label}</span>;
  const sp = new URLSearchParams();
  if (params.q) sp.set('q', params.q);
  if (params.status) sp.set('status', params.status);
  sp.set('page', String(page));
  return (
    <a href={`/alerts?${sp.toString()}`} style={{ padding: '0.5rem 1rem', borderRadius: '8px', background: 'rgba(59,130,246,0.1)', color: '#3b82f6', textDecoration: 'none', fontSize: '0.85rem' }}>
      {label}
    </a>
  );
}
