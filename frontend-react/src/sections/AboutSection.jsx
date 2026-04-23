export default function AboutSection({ t, scrollTo }) {
  return (
    <section id="about" className="page-section">
      <div className="page-header">
        <h1>{t.about.title}</h1>
        <p>Bringing transparency to agricultural tokenization</p>
      </div>

      <div className="about-section">
        <h2>{t.problem.title}</h2>
        <p>{t.problem.text}</p>
      </div>

      <div className="about-section">
        <h2>{t.solution.title}</h2>
        <p>{t.solution.text}</p>
      </div>

      <div className="about-features">
        <div className="about-feature">
          <div className="about-feature-icon">🎯</div>
          <h3>{t.about.mission.title}</h3>
          <p>{t.about.mission.desc}</p>
        </div>
        <div className="about-feature">
          <div className="about-feature-icon">🔭</div>
          <h3>{t.about.vision.title}</h3>
          <p>{t.about.vision.desc}</p>
        </div>
        <div className="about-feature">
          <div className="about-feature-icon">💎</div>
          <h3>{t.about.values.title}</h3>
          <p>{t.about.values.desc}</p>
        </div>
      </div>

      <div className="about-tech">
        <h2>Tech Stack</h2>
        <div className="tech-tags">
          <span className="tech-tag">Sentinel-2</span>
          <span className="tech-tag">DeepSeek-R1</span>
          <span className="tech-tag">Hedera HCS</span>
          <span className="tech-tag">Stellar Soroban</span>
          <span className="tech-tag">FastAPI</span>
          <span className="tech-tag">React</span>
        </div>
      </div>

      <div className="about-contact">
        <h2>Contacto</h2>
        <p>¿Interesado en integrar VitisTrust?</p>
        <p className="contact-email">hola@vitistrust.io</p>
      </div>
    </section>
  )
}