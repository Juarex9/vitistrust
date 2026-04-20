export default function Navbar({ lang, setLang, activeSection, scrollToSection }) {
  const t = {
    en: { links: ['Home', 'How it works', 'Verify', 'About us'] },
    es: { links: ['Home', 'Cómo funciona', 'Verificar', 'Sobre nosotros'] }
  }

  const ids = ['home', 'how-it-works', 'verify', 'about']

  return (
    <nav className="navbar">
      <div className="nav-brand">
        <span className="nav-logo">VitisTrust</span>
        <span className="nav-version">v2.0</span>
      </div>
      
      <div className="nav-links">
        {t[lang].links.map((label, i) => (
          <button 
            key={ids[i]}
            onClick={() => scrollToSection(ids[i])} 
            className={`nav-link ${activeSection === ids[i] ? 'active' : ''}`}
          >
            {label}
          </button>
        ))}
      </div>
      
      <div className="nav-right">
        <div className="lang-toggle">
          <button className={`lang-btn ${lang === 'en' ? 'active' : ''}`} onClick={() => setLang('en')}>EN</button>
          <button className={`lang-btn ${lang === 'es' ? 'active' : ''}`} onClick={() => setLang('es')}>ES</button>
        </div>
      </div>
    </nav>
  )
}