export default function StatsRow({ t }) {
  const stats = [
    { key: 'satellites', value: 'Sentinel-2', sub: '10m resolution', color: 'emerald' },
    { key: 'networks', value: '2', sub: 'Hedera + Stellar', color: 'violet' },
    { key: 'audits', value: 'AI', sub: 'DeepSeek-R1', color: 'amber' }
  ]

  return (
    <div className="stats-row">
      {stats.map((stat) => (
        <div key={stat.key} className={`stat-card ${stat.color}`}>
          <div className="stat-label">{t.stats[stat.key]}</div>
          <div className="stat-value">{stat.value}</div>
          <div className="stat-sub">{stat.sub}</div>
        </div>
      ))}
    </div>
  )
}