import prisma from '@/lib/prisma';
import { ShieldAlert, ShieldCheck, Mail, Activity, Ban, MessageSquareOff } from 'lucide-react';
import { revalidatePath } from 'next/cache';

export const dynamic = 'force-dynamic';

export default async function UsersPage() {
  const users = await prisma.user.findMany({
    include: {
      bans: true,
      mutes: true,
      settings: true,
      alerts: true,
      portfolio: true
    },
    orderBy: { created_at: 'desc' }
  });

  async function toggleBanAction(formData: FormData) {
    'use server';
    const userIdStr = formData.get('userId') as string;
    const currentlyBanned = formData.get('currentlyBanned') === 'true';
    const userIdToken = BigInt(userIdStr);

    try {
      if (currentlyBanned) {
        await prisma.ban.delete({
          where: { user_id: userIdToken }
        });
      } else {
        await prisma.ban.create({
          data: {
            user_id: userIdToken,
            reason: 'Yönetici tarafından yasaklandı'
          }
        });
      }
      revalidatePath('/users');
    } catch (e: any) {
      console.error('Ban action error:', e);
    }
  }

  return (
    <div>
      <h1 className="header-gradient" style={{ fontSize: '2.5rem', marginBottom: '2rem', fontWeight: 800 }}>Kullanıcı Yönetimi</h1>
      
      <div className="card glass-panel" style={{ padding: '1rem', marginBottom: '2rem', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem' }}>
         <div className="system-item">
            <div className="system-label">👥 Toplam Kullanıcı</div>
            <div className="system-status online">{users.length}</div>
         </div>
         <div className="system-item">
            <div className="system-label">🚫 Yasaklı Kullanıcılar</div>
            <div className="system-status" style={{ color: '#ef4444' }}>{users.filter(u => u.bans).length}</div>
         </div>
         <div className="system-item">
            <div className="system-label">💼 Portföyü Olanlar</div>
            <div className="system-status fast">{users.filter(u => u.portfolio.length > 0).length}</div>
         </div>
      </div>

      <div className="card glass-panel">
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Kullanıcı</th>
                <th>Telegram ID</th>
                <th>Portföy / Uyarı</th>
                <th>Durum</th>
                <th>Son Aktivite</th>
                <th>İşlemler</th>
              </tr>
            </thead>
            <tbody>
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
                          <div className="user-date">Kayıt: {u.created_at?.toLocaleDateString('tr-TR')}</div>
                        </div>
                      </div>
                    </td>
                    <td><code>{u.user_id.toString()}</code></td>
                    <td>
                       <div style={{ display: 'flex', gap: '0.5rem', opacity: 0.8, fontSize: '0.85rem' }}>
                          <span title="Portföyündeki Hisse Sayısı">📂 {u.portfolio.length}</span>
                          <span title="Aktif Uyarı Sayısı">🔔 {u.alerts.filter((a:any) => a.is_active === 1).length}</span>
                       </div>
                    </td>
                    <td>
                      {isBanned ? (
                        <span className="status-badge status-banned">YASAKLI</span>
                      ) : isMuted ? (
                        <span className="status-badge status-neutral">SESSİZ</span>
                      ) : (
                        <span className="status-badge status-active">AKTİF</span>
                      )}
                    </td>
                    <td style={{ opacity: 0.6, fontSize: '0.85rem' }}>
                      {u.last_active?.toLocaleString('tr-TR') || '-'}
                    </td>
                    <td>
                      <div className="action-row">
                        <form action={toggleBanAction}>
                          <input type="hidden" name="userId" value={u.user_id.toString()} />
                          <input type="hidden" name="currentlyBanned" value={isBanned.toString()} />
                          <button 
                            type="submit"
                            title={isBanned ? 'Yasağı Kaldır' : 'Kullanıcıyı Yasakla'}
                            className={isBanned ? 'btn-primary' : 'btn-outline'}
                            style={{ 
                                padding: '0.4rem', 
                                display: 'flex', 
                                alignItems: 'center', 
                                borderRadius: '8px', 
                                transition: 'all 0.2s',
                                border: '1px solid currentColor',
                                background: isBanned ? '#ef4444' : 'transparent',
                                borderColor: isBanned ? '#ef4444' : 'rgba(255,255,255,0.1)',
                                color: isBanned ? 'white' : '#fca5a5',
                                cursor: 'pointer'
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
      </div>
    </div>
  );
}
