import StatsRow from '../components/StatsRow'

export default function HowItWorksSection({ t, scrollTo }) {
  return (
    <section id="how-it-works" className="page-section">
      <div className="page-header">
        <h1>{t.process.title}</h1>
        <p>The audit process in 5 steps</p>
      </div>

      <StatsRow t={t} />

      <div className="steps-container">
        {t.process.steps.map((step, i) => (
          <div key={i} className="step-card">
            <div className="step-num">0{i + 1}</div>
            <div className="step-icon">{['📍', '🛰️', '🤖', '◈', '⬡'][i]}</div>
            <div className="step-content">
              <h3>{step.title}</h3>
              <p>{step.desc}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="process-details">
        <div className="detail-card">
          <h3>🛰️ Sentinel-2</h3>
          <p>European satellite provides 10m multispectral images. We use NDVI to measure vegetation health objectively.</p>
        </div>
        <div className="detail-card">
          <h3>🤖 DeepSeek-R1</h3>
          <p>AI analyzes satellite data and generates a VitisScore (0-100) with detailed justification.</p>
        </div>
        <div className="detail-card">
          <h3>⛓️ Doble Blockchain</h3>
          <p>Hedera records results immutably. Rootstock smart contracts certify the NFT on Bitcoin's blockchain.</p>
        </div>
      </div>

      <div className="cta-section">
        <h2>¿Querés ver el proceso en acción?</h2>
        <button onClick={() => scrollTo('verify')} className="cta-btn primary large">Verificar Viñedo</button>
      </div>
    </section>
  )
}