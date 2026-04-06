import prisma from '@/lib/prisma';
import { Users, Bell, Ban, Activity, TrendingUp, TrendingDown, Signal, Clock } from 'lucide-react';

export const dynamic = 'force-dynamic';

export default async function Dashboard() {
  let stats = {
    userCount: 0,
    banCount: 0,
    activeAlerts: 0,
    totalSignals: 0,
    recentSignals: [] as any[],
    recentAlerts: [] as any[],
    dbError: ''
  };

  try {
    stats.userCount = await prisma.user.count();
    stats.banCount = await prisma.ban.count();
    stats.activeAlerts = await prisma.alert.count({ where: { is_active: 1 } });
    stats.totalSignals = await prisma.hourlySignal.count();
    
    stats.recentSignals = await prisma.hourlySignal.findMany({
      take: 5,
      orderBy: { created_at: 'desc' }
    });

    stats.recentAlerts = await prisma.alert.findMany({
      take: 5,
      include: { user: true },
      orderBy: { created_at: 'desc' }
    });
  } catch (e: any) {
    stats.dbError = e.message || 'Veritabanı bağlantı hatası';
    console.error('Dashboard DB Error:', e);
  }

  return (
    <div>
      <h1 className="header-gradient" style={{ fontSize: '2.5rem', marginBottom: '2rem', fontWeight: 800 }}>
        Dashboard
      </h1>
      
      {stats.dbError && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid #ef4444', borderRadius: '12px', padding: '1rem', marginBottom: '2rem', color: '#ef4444' }}>
          ⚠️ Veritabanı Hatası: {stats.dbError}
        </div>
      )}

      <div className="stat-grid">
        <div className="card glass-panel flex-row">
          <div className="icon-blue" style={{background: 'rgba(59,130,246,0.1)', padding: '1rem', borderRadius: '12px'}}>
            <Users size={28} />
          </div>
          <div>
            <span className="stat-label">Toplam Kullanıcı</span>
            <div className="stat-value">{stats.userCount}</div>
          </div>
        </div>
        
        <div className="card glass-panel flex-row">
          <div className="icon-green" style={{background: 'rgba(16,185,129,0.1)', padding: '1rem', borderRadius: '12px'}}>
            <Bell size={28} />
          </div>
          <div>
            <span className="stat-label">Aktif Uyarılar</span>
            <div className="stat-value">{stats.activeAlerts}</div>
          </div>
        </div>

        <div className="card glass-panel flex-row">
          <div className="icon-red" style={{background: 'rgba(239,68,68,0.1)', padding: '1rem', borderRadius: '12px'}}>
            <Ban size={28} />
          </div>
          <div>
            <span className="stat-label">Yasaklı Kullanıcı</span>
            <div className="stat-value">{stats.banCount}</div>
          </div>
        </div>

        <div className="card glass-panel flex-row">
          <div className="icon-purple" style={{background: 'rgba(139,92,246,0.1)', padding: '1rem', borderRadius: '12px'}}>
            <Activity size={28} />
          </div>
          <div>
            <span className="stat-label">Sinyal Analizi</span>
            <div className="stat-value">{stats.totalSignals}</div>
          </div>
        </div>
      </div>

      <div className="card-container two-columns">
        <div className="card glass-panel">
          <div className="card-header">
            <Signal size={20} className="icon-blue" />
            <h2>Son Teknik Sinyaller</h2>
          </div>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Hisse</th>
                  <th>Sinyal</th>
                  <th>Fiyat</th>
                  <th>Güç</th>
                </tr>
              </thead>
              <tbody>
                {stats.recentSignals.map((s) => (
                  <tr key={s.id}>
                    <td style={{ fontWeight: 700 }}>{s.symbol}</td>
                    <td>
                      <span className={`status-badge ${s.signal_type === 'AL' ? 'status-active' : 'status-banned'}`}>
                        {s.signal_type}
                      </span>
                    </td>
                    <td>{s.price.toFixed(2)} ₺</td>
                    <td>{s.signal_strength}/10</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card glass-panel">
          <div className="card-header">
            <Clock size={20} className="icon-yellow" />
            <h2>Son Kullanıcı Uyarıları</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {stats.recentAlerts.map((alert) => (
              <div key={alert.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem', background: 'rgba(255,255,255,0.03)', borderRadius: '10px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <div className="user-avatar" style={{width: '28px', height: '28px', fontSize: '0.7rem'}}>{alert.user?.username?.[0] || '?'}</div>
                  <div>
                    <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>{alert.symbol}</div>
                    <div style={{ fontSize: '0.7rem', opacity: 0.5 }}>{alert.user?.username || 'İsimsiz'}</div>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '0.85rem', fontWeight: 700 }}>{alert.price} ₺</div>
                  <div style={{ fontSize: '0.7rem', color: alert.direction === 'yukari' ? '#10b981' : '#ef4444' }}>
                    {alert.direction === 'yukari' ? 'Yukarı' : 'Aşağı'}
                  </div>
                </div>
              </div>
            ))}
            {stats.recentAlerts.length === 0 && <div style={{ opacity: 0.5, textAlign: 'center' }}>Henüz uyarı yok</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
