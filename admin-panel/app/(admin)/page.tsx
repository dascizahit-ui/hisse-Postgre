import prisma from '@/lib/prisma';
import { Users, Bell, Ban, Activity, Signal, Clock, TrendingUp, TrendingDown, Radio, Flag } from 'lucide-react';

export const dynamic = 'force-dynamic';

function directionLabel(direction: string) {
  if (direction === 'above' || direction === 'yukari') return { text: 'Üstüne', color: '#10b981', icon: TrendingUp };
  if (direction === 'below' || direction === 'asagi') return { text: 'Altına', color: '#ef4444', icon: TrendingDown };
  return { text: direction, color: '#9ca3af', icon: TrendingUp };
}

export default async function Dashboard() {
  let stats = {
    userCount: 0,
    banCount: 0,
    muteCount: 0,
    activeAlerts: 0,
    totalSignals: 0,
    pendingReports: 0,
    activeSubscriptions: 0,
    signalBreakdown: [] as Array<{ signal_type: string; count: number }>,
    recentSignals: [] as any[],
    recentAlerts: [] as any[],
    topSymbols: [] as Array<{ symbol: string; count: number }>,
    dbError: '',
  };

  try {
    const [
      userCount,
      banCount,
      muteCount,
      activeAlerts,
      totalSignals,
      pendingReports,
      activeSubscriptions,
      recentSignals,
      recentAlerts,
    ] = await Promise.all([
      prisma.user.count(),
      prisma.ban.count(),
      prisma.mute.count(),
      prisma.alert.count({ where: { is_active: 1 } }),
      prisma.hourlySignal.count(),
      prisma.report.count({ where: { status: 'pending' } }),
      prisma.signalSubscription.count({ where: { is_active: 1 } }),
      prisma.hourlySignal.findMany({ take: 8, orderBy: { created_at: 'desc' } }),
      prisma.alert.findMany({ take: 6, include: { user: true }, orderBy: { created_at: 'desc' } }),
    ]);

    stats.userCount = userCount;
    stats.banCount = banCount;
    stats.muteCount = muteCount;
    stats.activeAlerts = activeAlerts;
    stats.totalSignals = totalSignals;
    stats.pendingReports = pendingReports;
    stats.activeSubscriptions = activeSubscriptions;
    stats.recentSignals = recentSignals;
    stats.recentAlerts = recentAlerts;

    const rawBreakdown = await prisma.hourlySignal.groupBy({
      by: ['signal_type'],
      _count: { signal_type: true },
    });
    stats.signalBreakdown = rawBreakdown.map((r) => ({ signal_type: r.signal_type, count: r._count.signal_type }));

    const rawTop = await prisma.signalSubscription.groupBy({
      by: ['symbol'],
      where: { is_active: 1 },
      _count: { symbol: true },
      orderBy: { _count: { symbol: 'desc' } },
      take: 5,
    });
    stats.topSymbols = rawTop.map((r) => ({ symbol: r.symbol, count: r._count.symbol }));
  } catch (e: any) {
    stats.dbError = e.message || 'Veritabanı bağlantı hatası';
    console.error('Dashboard DB Error:', e);
  }

  const signalColor = (type: string) =>
    type === 'AL' ? '#10b981' : type === 'SAT' ? '#ef4444' : '#9ca3af';

  return (
    <div>
      <h1 className="header-gradient" style={{ fontSize: '2.5rem', marginBottom: '2rem', fontWeight: 800 }}>Dashboard</h1>

      {stats.dbError && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid #ef4444', borderRadius: '12px', padding: '1rem', marginBottom: '2rem', color: '#ef4444' }}>
          ⚠️ Veritabanı Hatası: {stats.dbError}
        </div>
      )}

      <div className="stat-grid">
        <StatCard icon={<Users size={28} />} color="blue" label="Toplam Kullanıcı" value={stats.userCount} />
        <StatCard icon={<Bell size={28} />} color="green" label="Aktif Uyarılar" value={stats.activeAlerts} />
        <StatCard icon={<Radio size={28} />} color="purple" label="Aktif Sinyal Takibi" value={stats.activeSubscriptions} />
        <StatCard icon={<Ban size={28} />} color="red" label="Yasaklı Kullanıcı" value={stats.banCount} />
        <StatCard icon={<Activity size={28} />} color="purple" label="Toplam Sinyal" value={stats.totalSignals} />
        <StatCard icon={<Flag size={28} />} color="yellow" label="Bekleyen Rapor" value={stats.pendingReports} />
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
                  <th>RSI</th>
                </tr>
              </thead>
              <tbody>
                {stats.recentSignals.length === 0 && (
                  <tr><td colSpan={5} style={{ textAlign: 'center', opacity: 0.5 }}>Henüz sinyal yok</td></tr>
                )}
                {stats.recentSignals.map((s) => (
                  <tr key={s.id}>
                    <td style={{ fontWeight: 700 }}>{s.symbol}</td>
                    <td>
                      <span className="status-badge" style={{ background: `${signalColor(s.signal_type)}20`, color: signalColor(s.signal_type) }}>
                        {s.signal_type}
                      </span>
                    </td>
                    <td>{s.price.toFixed(2)} ₺</td>
                    <td>{s.signal_strength}/10</td>
                    <td style={{ opacity: 0.7 }}>{s.rsi.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card glass-panel">
          <div className="card-header">
            <Clock size={20} className="icon-yellow" />
            <h2>Son Uyarılar</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {stats.recentAlerts.length === 0 && <div style={{ opacity: 0.5, textAlign: 'center' }}>Henüz uyarı yok</div>}
            {stats.recentAlerts.map((alert: any) => {
              const dir = directionLabel(alert.direction);
              const Icon = dir.icon;
              return (
                <div key={alert.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem', background: 'rgba(255,255,255,0.03)', borderRadius: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <div className="user-avatar" style={{ width: '28px', height: '28px', fontSize: '0.7rem' }}>
                      {alert.user?.username?.[0]?.toUpperCase() || '?'}
                    </div>
                    <div>
                      <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>{alert.symbol}</div>
                      <div style={{ fontSize: '0.7rem', opacity: 0.5 }}>{alert.user?.username || 'İsimsiz'}</div>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '0.85rem', fontWeight: 700 }}>{alert.price.toFixed(2)} ₺</div>
                    <div style={{ fontSize: '0.7rem', color: dir.color, display: 'flex', alignItems: 'center', gap: '3px', justifyContent: 'flex-end' }}>
                      <Icon size={12} /> {dir.text}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="card-container two-columns" style={{ marginTop: '1.5rem' }}>
        <div className="card glass-panel">
          <div className="card-header">
            <Activity size={20} className="icon-purple" />
            <h2>Sinyal Dağılımı</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {stats.signalBreakdown.length === 0 && <div style={{ opacity: 0.5, textAlign: 'center' }}>Veri yok</div>}
            {stats.signalBreakdown.map((s) => (
              <div key={s.signal_type} className="system-item">
                <div className="system-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span className="status-badge" style={{ background: `${signalColor(s.signal_type)}20`, color: signalColor(s.signal_type) }}>
                    {s.signal_type}
                  </span>
                </div>
                <div className="system-status" style={{ color: signalColor(s.signal_type), background: `${signalColor(s.signal_type)}15` }}>
                  {s.count}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card glass-panel">
          <div className="card-header">
            <Radio size={20} className="icon-green" />
            <h2>En Çok Takip Edilen</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {stats.topSymbols.length === 0 && <div style={{ opacity: 0.5, textAlign: 'center' }}>Takip edilen hisse yok</div>}
            {stats.topSymbols.map((s, i) => (
              <div key={s.symbol} className="system-item">
                <div className="system-label" style={{ fontWeight: 600 }}>
                  <span style={{ opacity: 0.4, marginRight: '0.5rem' }}>{i + 1}.</span>
                  {s.symbol}
                </div>
                <div className="system-status fast">{s.count} takipçi</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon, color, label, value }: { icon: React.ReactNode; color: string; label: string; value: number }) {
  const bg: Record<string, string> = {
    blue: 'rgba(59,130,246,0.1)',
    green: 'rgba(16,185,129,0.1)',
    red: 'rgba(239,68,68,0.1)',
    purple: 'rgba(139,92,246,0.1)',
    yellow: 'rgba(245,158,11,0.1)',
  };
  return (
    <div className="card glass-panel flex-row">
      <div className={`icon-${color}`} style={{ background: bg[color], padding: '1rem', borderRadius: '12px' }}>
        {icon}
      </div>
      <div>
        <span className="stat-label">{label}</span>
        <div className="stat-value">{value}</div>
      </div>
    </div>
  );
}
