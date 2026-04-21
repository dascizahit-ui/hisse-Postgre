import prisma from '@/lib/prisma';
import { Flag, Check, X, AlertCircle, Ban } from 'lucide-react';
import { revalidatePath } from 'next/cache';

export const dynamic = 'force-dynamic';

const PAGE_SIZE = 25;

type SearchParams = { status?: string; page?: string };

async function setReportStatusAction(formData: FormData) {
  'use server';
  const reportId = parseInt(formData.get('reportId') as string, 10);
  const status = formData.get('status') as string;
  try {
    await prisma.report.update({ where: { report_id: reportId }, data: { status } });
    revalidatePath('/reports');
  } catch (e) {
    console.error('Report status error:', e);
  }
}

async function banReportedUserAction(formData: FormData) {
  'use server';
  const userId = BigInt(formData.get('userId') as string);
  const reportId = parseInt(formData.get('reportId') as string, 10);
  try {
    await prisma.ban.upsert({
      where: { user_id: userId },
      update: { reason: 'Rapor üzerine yasaklandı' },
      create: { user_id: userId, reason: 'Rapor üzerine yasaklandı' },
    });
    await prisma.report.update({ where: { report_id: reportId }, data: { status: 'resolved' } });
    revalidatePath('/reports');
  } catch (e) {
    console.error('Ban from report error:', e);
  }
}

export default async function ReportsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const status = sp.status || 'pending';
  const page = Math.max(1, parseInt(sp.page || '1', 10) || 1);

  const where: any = {};
  if (status !== 'all') where.status = status;

  const [totalCount, reports, pendingCount, resolvedCount, dismissedCount] = await Promise.all([
    prisma.report.count({ where }),
    prisma.report.findMany({
      where,
      include: { reporter: true, reportedUser: { include: { bans: true } } },
      orderBy: { timestamp: 'desc' },
      skip: (page - 1) * PAGE_SIZE,
      take: PAGE_SIZE,
    }),
    prisma.report.count({ where: { status: 'pending' } }),
    prisma.report.count({ where: { status: 'resolved' } }),
    prisma.report.count({ where: { status: 'dismissed' } }),
  ]);

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  return (
    <div>
      <h1 className="header-gradient" style={{ fontSize: '2.5rem', marginBottom: '2rem', fontWeight: 800 }}>Raporlar</h1>

      <div className="card glass-panel" style={{ padding: '1rem', marginBottom: '1.5rem', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem' }}>
        <FilterLink label="📋 Hepsi" active={status === 'all'} value={pendingCount + resolvedCount + dismissedCount} href="/reports?status=all" />
        <FilterLink label="⏳ Bekleyen" active={status === 'pending'} value={pendingCount} href="/reports?status=pending" color="#f59e0b" />
        <FilterLink label="✔ Çözüldü" active={status === 'resolved'} value={resolvedCount} href="/reports?status=resolved" color="#10b981" />
        <FilterLink label="✖ Reddedildi" active={status === 'dismissed'} value={dismissedCount} href="/reports?status=dismissed" color="#9ca3af" />
      </div>

      <div className="card glass-panel">
        <div className="card-header">
          <Flag size={20} className="icon-yellow" />
          <h2>Kullanıcı Raporları</h2>
        </div>

        {reports.length === 0 ? (
          <div style={{ opacity: 0.5, textAlign: 'center', padding: '3rem' }}>
            <AlertCircle size={32} style={{ opacity: 0.3, marginBottom: '0.5rem' }} />
            <div>Bu kategoride rapor yok</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {reports.map((r: any) => {
              const alreadyBanned = !!r.reportedUser?.bans;
              return (
                <div key={r.report_id} style={{ padding: '1.25rem', background: 'rgba(255,255,255,0.02)', borderRadius: '12px', border: '1px solid var(--card-border)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem', gap: '1rem', flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <StatusBadge status={r.status} />
                      <span style={{ fontSize: '0.75rem', opacity: 0.5 }}>#{r.report_id}</span>
                      <span style={{ fontSize: '0.75rem', opacity: 0.5 }}>{new Date(r.timestamp).toLocaleString('tr-TR')}</span>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                    <UserBlock label="👤 Raporlayan" user={r.reporter} />
                    <UserBlock label="🎯 Raporlanan" user={r.reportedUser} highlight banned={alreadyBanned} />
                  </div>

                  <div style={{ background: 'rgba(0,0,0,0.3)', borderRadius: '8px', padding: '0.75rem 1rem', marginBottom: '1rem', borderLeft: '3px solid #f59e0b' }}>
                    <div style={{ fontSize: '0.7rem', opacity: 0.5, marginBottom: '0.25rem' }}>MESAJ</div>
                    <div style={{ fontSize: '0.9rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{r.message}</div>
                  </div>

                  {r.status === 'pending' && (
                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                      {!alreadyBanned && (
                        <form action={banReportedUserAction}>
                          <input type="hidden" name="userId" value={r.reported_user_id.toString()} />
                          <input type="hidden" name="reportId" value={r.report_id} />
                          <button type="submit" style={{ padding: '0.5rem 1rem', borderRadius: '8px', background: '#ef4444', border: 'none', color: 'white', cursor: 'pointer', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.4rem', fontWeight: 600 }}>
                            <Ban size={14} /> Yasakla + Çöz
                          </button>
                        </form>
                      )}
                      <form action={setReportStatusAction}>
                        <input type="hidden" name="reportId" value={r.report_id} />
                        <input type="hidden" name="status" value="resolved" />
                        <button type="submit" style={{ padding: '0.5rem 1rem', borderRadius: '8px', background: 'rgba(16,185,129,0.1)', border: '1px solid #10b981', color: '#10b981', cursor: 'pointer', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <Check size={14} /> Çözüldü İşaretle
                        </button>
                      </form>
                      <form action={setReportStatusAction}>
                        <input type="hidden" name="reportId" value={r.report_id} />
                        <input type="hidden" name="status" value="dismissed" />
                        <button type="submit" style={{ padding: '0.5rem 1rem', borderRadius: '8px', background: 'transparent', border: '1px solid rgba(156,163,175,0.4)', color: '#9ca3af', cursor: 'pointer', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <X size={14} /> Reddet
                        </button>
                      </form>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {totalPages > 1 && (
          <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', padding: '1rem', alignItems: 'center', marginTop: '1rem' }}>
            <PageLink page={page - 1} disabled={page === 1} label="← Önceki" params={sp} />
            <span style={{ opacity: 0.6, fontSize: '0.85rem', padding: '0 1rem' }}>Sayfa {page} / {totalPages}</span>
            <PageLink page={page + 1} disabled={page >= totalPages} label="Sonraki →" params={sp} />
          </div>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; bg: string; color: string }> = {
    pending: { label: 'BEKLEMEDE', bg: 'rgba(245,158,11,0.1)', color: '#f59e0b' },
    resolved: { label: 'ÇÖZÜLDÜ', bg: 'rgba(16,185,129,0.1)', color: '#10b981' },
    dismissed: { label: 'REDDEDİLDİ', bg: 'rgba(156,163,175,0.1)', color: '#9ca3af' },
  };
  const s = map[status] || { label: status.toUpperCase(), bg: 'rgba(255,255,255,0.05)', color: '#fff' };
  return <span className="status-badge" style={{ background: s.bg, color: s.color }}>{s.label}</span>;
}

function UserBlock({ label, user, highlight, banned }: { label: string; user: any; highlight?: boolean; banned?: boolean }) {
  return (
    <div style={{ padding: '0.75rem', background: highlight ? 'rgba(239,68,68,0.05)' : 'rgba(255,255,255,0.02)', borderRadius: '10px', border: `1px solid ${highlight ? 'rgba(239,68,68,0.2)' : 'var(--card-border)'}` }}>
      <div style={{ fontSize: '0.7rem', opacity: 0.5, marginBottom: '0.4rem' }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
        <div className="user-avatar" style={{ width: '28px', height: '28px', fontSize: '0.75rem' }}>
          {user?.username?.[0]?.toUpperCase() || '?'}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            {user?.username || 'İsimsiz'}
            {banned && <span style={{ fontSize: '0.6rem', background: 'rgba(239,68,68,0.2)', color: '#ef4444', padding: '1px 6px', borderRadius: '4px' }}>YASAKLI</span>}
          </div>
          <div style={{ fontSize: '0.7rem', opacity: 0.5 }}><code>{user?.user_id?.toString() || '-'}</code></div>
        </div>
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
  if (params.status) sp.set('status', params.status);
  sp.set('page', String(page));
  return (
    <a href={`/reports?${sp.toString()}`} style={{ padding: '0.5rem 1rem', borderRadius: '8px', background: 'rgba(59,130,246,0.1)', color: '#3b82f6', textDecoration: 'none', fontSize: '0.85rem' }}>
      {label}
    </a>
  );
}
