import prisma from '@/lib/prisma';
import { Bell, User, Clock, TrendingUp, TrendingDown } from 'lucide-react';

export const dynamic = 'force-dynamic';

export default async function AlertsPage() {
  const alerts = await prisma.alert.findMany({
    include: {
      user: true
    },
    orderBy: { created_at: 'desc' }
  });

  return (
    <div>
      <h1 className="header-gradient" style={{ fontSize: '2.5rem', marginBottom: '2rem', fontWeight: 800 }}>Hisse Uyarıları</h1>
      
      <div className="card glass-panel">
        <div className="card-header">
          <Bell size={20} className="icon-blue" />
          <h2>Aktif ve Geçmiş Uyarılar</h2>
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
              </tr>
            </thead>
            <tbody>
              {alerts.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: 'center', opacity: 0.5 }}>Henüz bir uyarı eklenmemiş</td></tr>
              )}
              {alerts.map((alert: any) => (
                <tr key={alert.id}>
                  <td>
                    <div className="user-info">
                      <div className="user-avatar" style={{ width: '32px', height: '32px', fontSize: '0.8rem' }}>
                        {alert.user?.username?.[0]?.toUpperCase() || '?'}
                      </div>
                      <div>
                        <div className="user-name" style={{ fontSize: '0.9rem' }}>{alert.user?.username || 'İsimsiz'}</div>
                        <div className="user-date" style={{ fontSize: '0.7rem' }}>{alert.user_id.toString()}</div>
                      </div>
                    </div>
                  </td>
                  <td style={{ fontWeight: 800, color: '#3b82f6' }}>{alert.symbol}</td>
                  <td style={{ fontWeight: 600 }}>{alert.price.toFixed(2)} ₺</td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      {alert.direction === 'yukari' ? (
                        <><TrendingUp size={14} color="#10b981" /> <span style={{ color: '#10b981', fontSize: '0.85rem' }}>Yukarı</span></>
                      ) : (
                        <><TrendingDown size={14} color="#ef4444" /> <span style={{ color: '#ef4444', fontSize: '0.85rem' }}>Aşağı</span></>
                      )}
                    </div>
                  </td>
                  <td>
                    {alert.is_active === 1 ? (
                      <span className="status-badge status-active">BEKLEMEDE</span>
                    ) : (
                      <span className="status-badge status-neutral">TAMAMLANDI</span>
                    )}
                  </td>
                  <td style={{ opacity: 0.6, fontSize: '0.85rem' }}>
                    {alert.created_at?.toLocaleString('tr-TR')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      
      <div style={{ marginTop: '2rem', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1.5rem' }}>
         <div className="card glass-panel">
            <h3>📊 Uyarı İstatistikleri</h3>
            <div style={{ marginTop: '1rem' }}>
               <div className="system-item">
                  <div className="system-label">Aktif Uyarılar</div>
                  <div className="system-status online">{alerts.filter(a => a.is_active === 1).length}</div>
               </div>
               <div className="system-item">
                  <div className="system-label">Toplam Uyarı</div>
                  <div className="system-status fast">{alerts.length}</div>
               </div>
            </div>
         </div>
      </div>
    </div>
  );
}
