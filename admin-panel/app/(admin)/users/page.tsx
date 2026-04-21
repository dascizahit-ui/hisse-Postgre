import prisma from '@/lib/prisma';
import { Ban, ShieldCheck, VolumeX, Volume2, Search } from 'lucide-react';
import { revalidatePath } from 'next/cache';

export const dynamic = 'force-dynamic';

const PAGE_SIZE = 25;

type SearchParams = { q?: string; page?: string; filter?: string };

async function toggleBanAction(formData: FormData) {
  'use server';
  const userIdStr = formData.get('userId') as string;
  const currentlyBanned = formData.get('currentlyBanned') === 'true';
  const userId = BigInt(userIdStr);

  try {
    if (currentlyBanned) {
      await prisma.ban.delete({ where: { user_id: userId } });
    } else {
      await prisma.ban.create({
        data: { user_id: userId, reason: 'Yönetici tarafından yasaklandı' },
      });
    }
    revalidatePath('/users');
  } catch (e: any) {
    console.error('Ban action error:', e);
  }
}

async function toggleMuteAction(formData: FormData) {
  'use server';
  const userIdStr = formData.get('userId') as string;
  const currentlyMuted = formData.get('currentlyMuted') === 'true';
  const userId = BigInt(userIdStr);

  try {
    if (currentlyMuted) {
      await prisma.mute.delete({ where: { user_id: userId } });
    } else {
      const muteUntil = new Date();
      muteUntil.setHours(muteUntil.getHours() + 24);
      await prisma.mute.create({
        data: {
          user_id: userId,
          mute_until: muteUntil,
          reason: 'Yönetici tarafından 24 saat susturuldu',
        },
      });
    }
    revalidatePath('/users');
  } catch (e: any) {
    console.error('Mute action error:', e);
  }
}

export default async function UsersPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const query = (sp.q || '').trim();
  const page = Math.max(1, parseInt(sp.page || '1', 10) || 1);
  const filter = sp.filter || 'all';

  const where: any = {};
  if (query) {
    const asBigInt = /^\d+$/.test(query) ? BigInt(query) : null;
    where.OR = [
      { username: { contains: query, mode: 'insensitive' } },
      ...(asBigInt !== null ? [{ user_id: asBigInt }] : []),
    ];
  }
  if (filter === 'banned') where.bans = { isNot: null };
  else if (filter === 'muted') where.mutes = { isNot: null };
  else if (filter === 'active') where.AND = [{ bans: { is: null } }, { mutes: { is: null } }];

  const [totalCount, users, banCount, muteCount] = await Promise.all([
    prisma.user.count({ where }),
    prisma.user.findMany({
      where,
      include: { bans: true, mutes: true, alerts: { where: { is_active: 1 } } },
      orderBy: { last_active: 'desc' },
      skip: (page - 1) * PAGE_SIZE,
      take: PAGE_SIZE,
    }),
    prisma.ban.count(),
    prisma.mute.count(),
  ]);

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  return (
    <div>
      <h1 className="header-gradient" style={{ fontSize: '2.5rem', marginBottom: '2rem', fontWeight: 800 }}>Kullanıcı Yönetimi</h1>

      <div className="card glass-panel" style={{ padding: '1rem', marginBottom: '1.5rem', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1.5rem' }}>
        <FilterLink label="👥 Hepsi" active={filter === 'all'} value={totalCount} href={`/users?filter=all${query ? `&q=${encodeURIComponent(query)}` : ''}`} />
        <FilterLink label="🚫 Yasaklı" active={filter === 'banned'} value={banCount} href={`/users?filter=banned${query ? `&q=${encodeURIComponent(query)}` : ''}`} color="#ef4444" />
        <FilterLink label="🔇 Susturulmuş" active={filter === 'muted'} value={muteCount} href={`/users?filter=muted${query ? `&q=${encodeURIComponent(query)}` : ''}`} color="#f59e0b" />
        <FilterLink label="✅ Aktif" active={filter === 'active'} value={totalCount - (filter === 'active' ? 0 : banCount + muteCount) } href={`/users?filter=active${query ? `&q=${encodeURIComponent(query)}` : ''}`} color="#10b981" />
      </div>

      <form method="GET" className="card glass-panel" style={{ padding: '1rem', marginBottom: '1.5rem', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
        <Search size={18} style={{ opacity: 0.5 }} />
        <input
          type="text"
          name="q"
          defaultValue={query}
          placeholder="Kullanıcı adı veya Telegram ID ile ara..."
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
          }}
        />
        <input type="hidden" name="filter" value={filter} />
        <button type="submit" className="btn-primary" style={{ border: 'none' }}>Ara</button>
        {query && (
          <a href={`/users?filter=${filter}`} style={{ color: '#9ca3af', fontSize: '0.85rem', textDecoration: 'none' }}>Temizle</a>
        )}
      </form>

      <div className="card glass-panel">
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Kullanıcı</th>
                <th>Telegram ID</th>
                <th>Aktif Uyarı</th>
                <th>Durum</th>
                <th>Son Aktivite</th>
                <th style={{ textAlign: 'right' }}>İşlemler</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: 'center', opacity: 0.5, padding: '2rem' }}>Kullanıcı bulunamadı</td></tr>
              )}
              {users.map((u: any) => {
                const isBanned = !!u.bans;
                const isMuted = !!u.mutes;

                return (
                  <tr key={u.user_id.toString()}>
                    <td>
                      <div className="user-info">
                        <div className="user-avatar" style={{ background: isBanned ? '#1e293b' : 'linear-gradient(135deg, #3b82f6, #8b5cf6)' }}>
                          {u.username?.[0]?.toUpperCase() || '?'}
                        </div>
                        <div>
                          <div className="user-name">{u.username || 'İsimsiz'}</div>
                          <div className="user-date">Kayıt: {u.created_at?.toLocaleDateString('tr-TR') || '-'}</div>
                        </div>
                      </div>
                    </td>
                    <td><code>{u.user_id.toString()}</code></td>
                    <td>
                      <span title="Aktif Uyarı Sayısı" style={{ opacity: 0.9, fontSize: '0.9rem' }}>🔔 {u.alerts.length}</span>
                    </td>
                    <td>
                      {isBanned ? (
                        <span className="status-badge status-banned">YASAKLI</span>
                      ) : isMuted ? (
                        <span className="status-badge" style={{ background: 'rgba(245,158,11,0.1)', color: '#f59e0b' }}>SESSİZ</span>
                      ) : (
                        <span className="status-badge status-active">AKTİF</span>
                      )}
                    </td>
                    <td style={{ opacity: 0.6, fontSize: '0.85rem' }}>
                      {u.last_active?.toLocaleString('tr-TR') || '-'}
                    </td>
                    <td>
                      <div className="action-row" style={{ justifyContent: 'flex-end' }}>
                        <form action={toggleMuteAction}>
                          <input type="hidden" name="userId" value={u.user_id.toString()} />
                          <input type="hidden" name="currentlyMuted" value={isMuted.toString()} />
                          <button
                            type="submit"
                            title={isMuted ? 'Susturmayı Kaldır' : '24 Saat Sustur'}
                            style={{
                              padding: '0.4rem',
                              display: 'flex',
                              alignItems: 'center',
                              borderRadius: '8px',
                              background: isMuted ? '#f59e0b' : 'transparent',
                              border: `1px solid ${isMuted ? '#f59e0b' : 'rgba(255,255,255,0.1)'}`,
                              color: isMuted ? 'white' : '#fcd34d',
                              cursor: 'pointer',
                            }}
                          >
                            {isMuted ? <Volume2 size={18} /> : <VolumeX size={18} />}
                          </button>
                        </form>
                        <form action={toggleBanAction}>
                          <input type="hidden" name="userId" value={u.user_id.toString()} />
                          <input type="hidden" name="currentlyBanned" value={isBanned.toString()} />
                          <button
                            type="submit"
                            title={isBanned ? 'Yasağı Kaldır' : 'Yasakla'}
                            style={{
                              padding: '0.4rem',
                              display: 'flex',
                              alignItems: 'center',
                              borderRadius: '8px',
                              background: isBanned ? '#ef4444' : 'transparent',
                              border: `1px solid ${isBanned ? '#ef4444' : 'rgba(255,255,255,0.1)'}`,
                              color: isBanned ? 'white' : '#fca5a5',
                              cursor: 'pointer',
                            }}
                          >
                            {isBanned ? <ShieldCheck size={18} /> : <Ban size={18} />}
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
            <PageLink page={page - 1} disabled={page === 1} label="← Önceki" params={sp} />
            <span style={{ opacity: 0.6, fontSize: '0.85rem', padding: '0 1rem' }}>
              Sayfa {page} / {totalPages} · Toplam {totalCount}
            </span>
            <PageLink page={page + 1} disabled={page >= totalPages} label="Sonraki →" params={sp} />
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
  if (disabled) {
    return <span style={{ opacity: 0.3, padding: '0.5rem 1rem' }}>{label}</span>;
  }
  const sp = new URLSearchParams();
  if (params.q) sp.set('q', params.q);
  if (params.filter) sp.set('filter', params.filter);
  sp.set('page', String(page));
  return (
    <a href={`/users?${sp.toString()}`} style={{ padding: '0.5rem 1rem', borderRadius: '8px', background: 'rgba(59,130,246,0.1)', color: '#3b82f6', textDecoration: 'none', fontSize: '0.85rem' }}>
      {label}
    </a>
  );
}
