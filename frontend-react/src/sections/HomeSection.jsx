export default function HomeSection({ t, scrollTo }) {
  return (
    <section id="home" className="page-section">
      <div className="hero-section">
        <h1 className="hero-title">
          <span className="gradient-text">{t.hero.title}</span>
          <span className="hero-subtitle">{t.hero.subtitle}</span>
        </h1>
        <p className="hero-description">{t.hero.description}</p>
        <div className="hero-cta">
          <button onClick={() => scrollTo('verify')} className="cta-btn primary">{t.nav.verify}</button>
          <button onClick={() => scrollTo('how-it-works')} className="cta-btn secondary">{t.nav.howItWorks}</button>
        </div>
      </div>

      <div className="features-grid">
        <div className="feature-card">
          <div className="feature-icon">🛰️</div>
          <h3>{t.features.sat.title}</h3>
          <p>{t.features.sat.desc}</p>
        </div>
        <div className="feature-card">
          <div className="feature-icon">🤖</div>
          <h3>{t.features.ai.title}</h3>
          <p>{t.features.ai.desc}</p>
        </div>
        <div className="feature-card">
          <div className="feature-icon">⛓️</div>
          <h3>{t.features.chain.title}</h3>
          <p>{t.features.chain.desc}</p>
        </div>
        <div className="feature-card">
          <div className="feature-icon">📊</div>
          <h3>{t.features.invest.title}</h3>
          <p>{t.features.invest.desc}</p>
        </div>
      </div>

      <div className="home-content">
        <div className="content-card">
          <h2>{t.problem.title}</h2>
          <p>{t.problem.text}</p>
        </div>
        <div className="content-card">
          <h2>{t.solution.title}</h2>
          <p>{t.solution.text}</p>
        </div>
      </div>

      <div className="stats-hero">
        <div className="stat-hero"><span className="stat-hero-value">10m</span><span className="stat-hero-label">Resolution</span></div>
        <div className="stat-hero"><span className="stat-hero-value">2</span><span className="stat-hero-label">Blockchains</span></div>
        <div className="stat-hero"><span className="stat-hero-value">0-100</span><span className="stat-hero-label">VitisScore</span></div>
        <div className="stat-hero"><span className="stat-hero-value">24</span><span className="stat-hero-label">Meses Historia</span></div>
      </div>

      <div className="cta-section">
        <h2>¿Listo para verificar tu viñedo?</h2>
        <button onClick={() => scrollTo('verify')} className="cta-btn primary large">Comenzar Verificación</button>
      </div>
    </section>
  )
}