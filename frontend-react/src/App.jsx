import { useState, useEffect } from 'react'
import './index.css'

const translations = {
  en: {
    hero: {
      title: 'Satellite-Verified',
      subtitle: 'Vineyard Oracle',
      description: 'AI-powered vineyard certification using satellite imagery and blockchain verification. Audit NFT assets with cryptographically secure proofs on Hedera and Rootstock.'
    },
    features: {
      satellite: { title: 'Satellite Analysis', desc: 'Sentinel-2 NDVI imaging' },
      ai: { title: 'AI Reasoning', desc: 'DeepSeek-R1 health assessment' },
      chain: { title: 'Blockchain Proof', desc: 'Hedera + Rootstock notarization' }
    },
    form: {
      title: 'Verify Vineyard',
      subtitle: 'Run a full audit for any tokenized vineyard asset',
      lat: 'Latitude',
      lon: 'Longitude',
      asset: 'Asset Address',
      token: 'Token ID',
      button: 'Run Verification'
    },
    result: {
      status: 'ASSET_CERTIFIED',
      score: 'VitisScore',
      risk: 'Risk Level',
      hedera: 'Hedera Topic',
      tx: 'RSK TX',
      loading: 'Verifying...',
      error: 'Verification Failed'
    },
    flow: {
      title: 'How It Works',
      steps: [
        { num: '01', title: 'Satellite Query', desc: 'Fetch NDVI data from Sentinel-2' },
        { num: '02', title: 'AI Analysis', desc: 'DeepSeek-R1 evaluates vine health' },
        { num: '03', title: 'Hedera Notarize', desc: 'Record proof on HCS topic' },
        { num: '04', title: 'RSK Certify', desc: 'Mint VitisScore on-chain' }
      ]
    },
    footer: {
      network: 'Rootstock Testnet',
      rights: '© 2026 VitisTrust Oracle'
    }
  },
  es: {
    hero: {
      title: 'Verificado por Satélite',
      subtitle: 'Oráculo de Viñedos',
      description: 'Certificación de viñedos con IA usando imágenes satelitales y verificación blockchain. Audita activos NFT con pruebas criptográficamente seguras en Hedera y Rootstock.'
    },
    features: {
      satellite: { title: 'Análisis Satelital', desc: 'Imágenes NDVI Sentinel-2' },
      ai: { title: 'Razonamiento IA', desc: 'Evaluación de salud DeepSeek-R1' },
      chain: { title: 'Prueba Blockchain', desc: 'Notarización Hedera + Rootstock' }
    },
    form: {
      title: 'Verificar Viñedo',
      subtitle: 'Ejecuta una auditoría completa para cualquier activo tokenizado',
      lat: 'Latitud',
      lon: 'Longitud',
      asset: 'Dirección del Activo',
      token: 'ID de Token',
      button: 'Ejecutar Verificación'
    },
    result: {
      status: 'ACTIVO_CERTIFICADO',
      score: 'VitisScore',
      risk: 'Nivel de Riesgo',
      hedera: 'Tópico Hedera',
      tx: 'TX RSK',
      loading: 'Verificando...',
      error: 'Verificación Fallida'
    },
    flow: {
      title: 'Cómo Funciona',
      steps: [
        { num: '01', title: 'Consulta Satelital', desc: 'Obtén datos NDVI de Sentinel-2' },
        { num: '02', title: 'Análisis IA', desc: 'DeepSeek-R1 evalúa salud de vides' },
        { num: '03', title: 'Notarizar Hedera', desc: 'Registra prueba en tópico HCS' },
        { num: '04', title: 'Certificar RSK', desc: 'Minta VitisScore on-chain' }
      ]
    },
    footer: {
      network: 'Rootstock Testnet',
      rights: '© 2026 VitisTrust Oracle'
    }
  }
}

function App() {
  const [lang, setLang] = useState('en')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [statusType, setStatusType] = useState('idle')
  
  const t = translations[lang]

  const handleSubmit = async (e) => {
    e.preventDefault()
    const formData = new FormData(e.target)
    const lat = formData.get('lat')
    const lon = formData.get('lon')
    const assetAddress = formData.get('assetAddress')
    const tokenId = formData.get('tokenId')

    setLoading(true)
    setError(null)
    setResult(null)
    setStatusType('loading')

    try {
      const response = await fetch(
        `http://localhost:8000/verify-vineyard?lat=${lat}&lon=${lon}&asset_address=${assetAddress}&token_id=${tokenId}`
      )
      
      if (!response.ok) {
        const errData = await response.json()
        throw new Error(errData.detail || 'Verification failed')
      }
      
      const data = await response.json()
      setResult(data)
      setStatusType('success')
    } catch (err) {
      setError(err.message)
      setStatusType('error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app-container">
      <div className="bg-grid" />
      <div className="bg-glow" />
      
      <div className="content">
        <header>
          <div className="logo">
            <div className="logo-icon">🌿</div>
            <span className="logo-text">VitisTrust</span>
          </div>
          <div className="lang-toggle">
            <button 
              className={`lang-btn ${lang === 'en' ? 'active' : ''}`}
              onClick={() => setLang('en')}
            >
              EN
            </button>
            <button 
              className={`lang-btn ${lang === 'es' ? 'active' : ''}`}
              onClick={() => setLang('es')}
            >
              ES
            </button>
          </div>
        </header>

        <main>
          <section className="hero-content">
            <h1>
              {t.hero.title}<br />
              <span className="highlight">{t.hero.subtitle}</span>
            </h1>
            <p>{t.hero.description}</p>

            <div className="features-list">
              <div className="feature-item">
                <div className="feature-icon">🛰️</div>
                <div className="feature-info">
                  <strong>{t.features.satellite.title}</strong>
                  <span>{t.features.satellite.desc}</span>
                </div>
              </div>
              <div className="feature-item">
                <div className="feature-icon">🧠</div>
                <div className="feature-info">
                  <strong>{t.features.ai.title}</strong>
                  <span>{t.features.ai.desc}</span>
                </div>
              </div>
              <div className="feature-item">
                <div className="feature-icon">🔗</div>
                <div className="feature-info">
                  <strong>{t.features.chain.title}</strong>
                  <span>{t.features.chain.desc}</span>
                </div>
              </div>
            </div>
          </section>

          <section className="form-wrapper">
            <div className="form-card">
              <div className="form-header">
                <h2>{t.form.title}</h2>
                <p>{t.form.subtitle}</p>
              </div>

              <form onSubmit={handleSubmit}>
                <div className="form-grid">
                  <div className="form-group">
                    <label>{t.form.lat}</label>
                    <input type="text" name="lat" placeholder="40.4123" required />
                  </div>
                  <div className="form-group">
                    <label>{t.form.lon}</label>
                    <input type="text" name="lon" placeholder="-3.6912" required />
                  </div>
                  <div className="form-group full-width">
                    <label>{t.form.asset}</label>
                    <input type="text" name="assetAddress" placeholder="0x..." required />
                  </div>
                  <div className="form-group full-width">
                    <label>{t.form.token}</label>
                    <input type="number" name="tokenId" placeholder="1" required />
                  </div>
                </div>

                <button type="submit" className="verify-btn" disabled={loading}>
                  {loading ? (
                    <>
                      <span className="spinner" />
                      {t.result.loading}
                    </>
                  ) : (
                    <>
                      {t.form.button}
                      <span>→</span>
                    </>
                  )}
                </button>
              </form>

              <div className={`result-card ${statusType !== 'idle' ? 'visible' : ''}`}>
                <div className="result-header">
                  <span className={`result-status ${statusType}`}>
                    {statusType === 'loading' && t.result.loading}
                    {statusType === 'success' && t.result.status}
                    {statusType === 'error' && t.result.error}
                  </span>
                </div>

                {result && (
                  <>
                    <div className="score-display">
                      <div className="score-value">{result.vitis_score}</div>
                      <div className="score-label">{t.result.score}</div>
                    </div>

                    <div className="result-details">
                      <div className="detail-row">
                        <span className="detail-label">{t.result.risk}</span>
                        <span className="detail-value">{result.risk?.toUpperCase()}</span>
                      </div>
                      <div className="detail-row">
                        <span className="detail-label">{t.result.hedera}</span>
                        <span className="detail-value">{result.hedera_notarization}</span>
                      </div>
                      <div className="detail-row">
                        <span className="detail-label">{t.result.tx}</span>
                        <a 
                          href={`https://explorer.testnet.rsk.co/tx/${result.rsk_tx_hash}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="tx-link"
                        >
                          {result.rsk_tx_hash?.substring(0, 12)}...
                        </a>
                      </div>
                    </div>
                  </>
                )}

                {error && (
                  <div className="result-details">
                    <div className="detail-row">
                      <span className="detail-label" style={{ color: 'var(--error)' }}>{error}</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </section>
        </main>

        <section className="flow-section">
          <h3 className="flow-title">{t.flow.title}</h3>
          <div className="flow-steps">
            {t.flow.steps.map((step, idx) => (
              <div className="flow-step" key={idx}>
                <div className="flow-num">{step.num}</div>
                <div className="flow-info">
                  <strong>{step.title}</strong>
                  <span>{step.desc}</span>
                </div>
                {idx < t.flow.steps.length - 1 && <div className="flow-arrow">→</div>}
              </div>
            ))}
          </div>
        </section>

        <footer>
          <div className="network-status">
            <div className="network-dot" />
            {t.footer.network}
          </div>
          <span className="copyright">{t.footer.rights}</span>
        </footer>
      </div>
    </div>
  )
}

export default App
