import prisma from '@/lib/prisma';
import { VolumeX, Volume2, Clock, AlertCircle } from 'lucide-react';
import { revalidatePath } from 'next/cache';

export const dynamic = 'force-dynamic';

async function unmuteAction(formData: FormData) {
  'use server';
  const userId = BigInt(formData.get('userId') as string);
  try {
    await prisma.mute.delete({ where: { user_id: userId } });
    revalidatePath('/mutes');
  } catch (e) {
    console.error('Unmute error:', e);
  }
}

async function extendMuteAction(formData: FormData) {
  'use server';
  const userId = BigInt(formData.get('userId') as string);
  const hours = parseInt(formData.get('hours') as string, 10);
  try {
    const current = await prisma.mute.findUnique({ where: { user_id: userId } });
    const base = current?.mute_until && current.mute_until > new Date() ? current.mute_until : new Date();
    const newUntil = new Date(base.getTime() + hours * 60 * 60 * 1000);
    await prisma.mute.update({
      where: { user_id: userId },
      data: { mute_until: newUntil },
    });
    revalidatePath('/mutes');
  } catch (e) {
    console.error('Extend mute error:', e);
  }
}

export default async function MutesPage() {
  const mutes = await prisma.mute.findMany({
    include: { user: true },
    orderBy: { muted_at: 'desc' },
  });

  const now = new Date();
  const activeCount = mutes.filter((m) => !m.mute_until || m.mute_until > now).length;
  const expiredCount = mutes.length - activeCount;

  return (
    <div>
      <h1 className="header-gradient" style={{ fontSize: '2.5rem', marginBottom: '2rem', fontWeight: 800 }}>Susturmalar</h1>

      <div className="card glass-panel" style={{ padding: '1rem', marginBottom: '1.5rem', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1.5rem' }}>
        <div className="system-item">
          <div className="system-label">🔇 Toplam Susturma</div>
          <div className="system-status fast">{mutes.length}</div>
        </div>
        <div className="system-item">
          <div className="system-label">⏳ Aktif Susturma</div>
          <div className="system-status" style={{ color: '#f59e0b', background: 'rgba(245,158,11,0.1)' }}>{activeCount}</div>
        </div>
        <div className="system-item">
          <div className="system-label">✔ Süresi Dolmuş</div>
          <div className="system-status neutral">{expiredCount}</div>
        </div>
      </div>

      <div className="card glass-panel">
        <div className="card-header">
          <VolumeX size={20} style={{ color: '#f59e0b' }} />
          <h2>Susturulmuş Kullanıcılar</h2>
        </div>

        {mutes.length === 0 ? (
          <div style={{ opacity: 0.5, textAlign: 'center', padding: '3rem' }}>
            <AlertCircle size={32} style={{ opacity: 0.3, marginBottom: '0.5rem' }} />
            <div>Susturulmuş kullanıcı yok</div>
          </div>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Kullanıcı</th>
                  <th>Telegram ID</th>
                  <th>Susturma Tarihi</th>
                  <th>Bitiş</th>
                  <th>Sebep</th>
                  <th style={{ textAlign: 'right' }}>İşlemler</th>
                </tr>
              </thead>
              <tbody>
                {mutes.map((m: any) => {
                  const isActive = !m.mute_until || m.mute_until > now;
                  const timeLeft = m.mute_until ? Math.max(0, Math.floor((m.mute_until.getTime() - now.getTime()) / 60000)) : null;
                  return (
                    <tr key={m.user_id.toString()}>
                      <td>
                        <div className="user-info">
                          <div className="user-avatar" style={{ width: '32px', height: '32px', fontSize: '0.8rem', background: isActive ? 'linear-gradient(135deg, #f59e0b, #ef4444)' : '#1e293b' }}>
                            {m.user?.username?.[0]?.toUpperCase() || '?'}
                          </div>
                          <div>
                            <div className="user-name" style={{ fontSize: '0.9rem' }}>{m.user?.username || 'İsimsiz'}</div>
                          </div>
                        </div>
                      </td>
                      <td><code>{m.user_id.toString()}</code></td>
                      <td style={{ fontSize: '0.85rem', opacity: 0.7 }}>{m.muted_at.toLocaleString('tr-TR')}</td>
                      <td>
                        {m.mute_until ? (
                          <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <span style={{ fontSize: '0.85rem' }}>{m.mute_until.toLocaleString('tr-TR')}</span>
                            {isActive && timeLeft !== null && (
                              <span style={{ fontSize: '0.7rem', color: '#f59e0b' }}>
                                <Clock size={10} style={{ display: 'inline', marginRight: '3px' }} />
                                {timeLeft > 60 ? `${Math.floor(timeLeft / 60)}s ${timeLeft % 60}dk` : `${timeLeft}dk`} kaldı
                              </span>
                            )}
                            {!isActive && <span style={{ fontSize: '0.7rem', color: '#9ca3af' }}>Süresi doldu</span>}
                          </div>
                        ) : (
                          <span style={{ fontSize: '0.85rem', color: '#9ca3af' }}>Süresiz</span>
                        )}
                      </td>
                      <td style={{ fontSize: '0.85rem', opacity: 0.8, maxWidth: '200px' }}>{m.reason || '-'}</td>
                      <td>
                        <div className="action-row" style={{ justifyContent: 'flex-end' }}>
                          {isActive && (
                            <form action={extendMuteAction}>
                              <input type="hidden" name="userId" value={m.user_id.toString()} />
                              <input type="hidden" name="hours" value="24" />
                              <button type="submit" title="+24 Saat" style={{ padding: '0.4rem 0.6rem', borderRadius: '8px', background: 'transparent', border: '1px solid rgba(245,158,11,0.4)', color: '#f59e0b', cursor: 'pointer', fontSize: '0.8rem' }}>
                                +24s
                              </button>
                            </form>
                          )}
                          <form action={unmuteAction}>
                            <input type="hidden" name="userId" value={m.user_id.toString()} />
                            <button type="submit" title="Susturmayı Kaldır" style={{ padding: '0.4rem', display: 'flex', alignItems: 'center', borderRadius: '8px', background: '#10b981', border: 'none', color: 'white', cursor: 'pointer' }}>
                              <Volume2 size={16} />
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
        )}
      </div>
    </div>
  );
}
