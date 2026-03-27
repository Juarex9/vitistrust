import { useState } from 'react'
import './index.css'

const translations = {
  en: {
    hero: {
      title: 'Vineyard Oracle',
      description: 'Satellite-verified NFT certification with blockchain proofs on Hedera & Rootstock.'
    },
    form: {
      title: 'Verify Vineyard',
      subtitle: 'Run a full audit for any tokenized vineyard asset',
      lat: 'Latitude',
      lon: 'Longitude',
      asset: 'Asset Address',
      token: 'Token ID',
      button: 'Run Verification',
      tabVerify: 'New Audit',
      tabCheck: 'Verify Certificate'
    },
    result: {
      status: 'CERTIFIED',
      score: 'VitisScore',
      risk: 'Risk Level',
      hedera: 'Hedera Topic',
      tx: 'RSK TX',
      loading: 'Verifying...',
      error: 'Verification Failed',
      existing: 'EXISTING CERTIFICATE'
    },
    investment: {
      title: 'Investment Analysis',
      recommendation: 'Recommendation',
      yieldForecast: 'Yield Forecast',
      confidence: 'Confidence'
    },
    stats: {
      satellites: 'Satellites',
      networks: 'Networks',
      audits: 'Audits'
    },
    sidebar: {
      process: 'Process Flow',
      chains: 'Supported Chains'
    },
    footer: {
      network: 'Hedera + Rootstock Testnet',
      rights: '© 2026 VitisTrust'
    }
  },
  es: {
    hero: {
      title: 'Oráculo de Viñedos',
      description: 'Certificación NFT verificada por satélite con pruebas blockchain en Hedera & Rootstock.'
    },
    form: {
      title: 'Verificar Viñedo',
      subtitle: 'Ejecuta una auditoría completa para cualquier activo tokenizado',
      lat: 'Latitud',
      lon: 'Longitud',
      asset: 'Dirección del Activo',
      token: 'ID de Token',
      button: 'Ejecutar Verificación',
      tabVerify: 'Nueva Auditoría',
      tabCheck: 'Verificar Certificado'
    },
    result: {
      status: 'CERTIFICADO',
      score: 'VitisScore',
      risk: 'Nivel de Riesgo',
      hedera: 'Tópico Hedera',
      tx: 'TX RSK',
      loading: 'Verificando...',
      error: 'Verificación Fallida',
      existing: 'CERTIFICADO EXISTENTE'
    },
    investment: {
      title: 'Análisis de Inversión',
      recommendation: 'Recomendación',
      yieldForecast: 'Rendimiento Estimado',
      confidence: 'Confianza'
    },
    stats: {
      satellites: 'Satélites',
      networks: 'Redes',
      audits: 'Auditorías'
    },
    sidebar: {
      process: 'Flujo del Proceso',
      chains: 'Cadenas Soportadas'
    },
    footer: {
      network: 'Hedera + Rootstock Testnet',
      rights: '© 2026 VitisTrust'
    }
  }
}

function App() {
  const [lang, setLang] = useState('en')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [statusType, setStatusType] = useState('idle')
  const [mode, setMode] = useState('verify')
  
  const t = translations[lang]

  const getRiskColor = (risk) => {
    if (!risk) return '#6b7280'
    const r = risk.toLowerCase()
    if (r === 'low') return '#10b981'
    if (r === 'medium') return '#f59e0b'
    if (r === 'high') return '#f43f5e'
    return '#6b7280'
  }

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
      let url
      if (mode === 'check') {
        url = `http://localhost:8000/certificate/${assetAddress}/${tokenId}`
      } else {
        url = `http://localhost:8000/verify-vineyard?lat=${lat}&lon=${lon}&asset_address=${assetAddress}&token_id=${tokenId}`
      }
      
      const response = await fetch(url)
      
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
      <div className="bg-pattern" />
      
      <div className="content">
        <header>
          <div className="logo">
            <div className="logo-icon">🍇</div>
            <span className="logo-text">VitisTrust</span>
            <span className="logo-version">v2.0</span>
          </div>
          
          <div className="header-right">
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
          </div>
        </header>

        <main>
          <div className="dashboard-grid">
            <div className="sidebar-left">
              <div className="info-card">
                <div className="info-card-header">
                  <div className="info-icon">⚡</div>
                  <span className="info-title">{t.sidebar.process}</span>
                </div>
                <div className="chain-flow">
                  <div className="chain-step">
                    <span className="chain-icon">🛰️</span>
                    <span className="chain-name">NDVI</span>
                  </div>
                  <span className="chain-arrow">→</span>
                  <div className="chain-step">
                    <span className="chain-icon">🧠</span>
                    <span className="chain-name">AI</span>
                  </div>
                  <span className="chain-arrow">→</span>
                  <div className="chain-step">
                    <span className="chain-icon">◈</span>
                    <span className="chain-name">HCS</span>
                  </div>
                  <span className="chain-arrow">→</span>
                  <div className="chain-step">
                    <span className="chain-icon">⬡</span>
                    <span className="chain-name">RSK</span>
                  </div>
                </div>
              </div>

              <div className="info-card">
                <div className="info-card-header">
                  <div className="info-icon">⛓</div>
                  <span className="info-title">{t.sidebar.chains}</span>
                </div>
                <div className="info-list">
                  <div className="info-item">
                    <span className="info-key">Hedera</span>
                    <span className="info-val">HCS</span>
                  </div>
                  <div className="info-item">
                    <span className="info-key">Rootstock</span>
                    <span className="info-val">EVM</span>
                  </div>
                  <div className="info-item">
                    <span className="info-key">Token</span>
                    <span className="info-val">ERC-721</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="dashboard-main">
              <div className="stats-row">
                <div className="stat-card emerald">
                  <div className="stat-label">{t.stats.satellites}</div>
                  <div className="stat-value">Sentinel-2</div>
                  <div className="stat-sub">10m resolution</div>
                </div>
                <div className="stat-card violet">
                  <div className="stat-label">{t.stats.networks}</div>
                  <div className="stat-value">2</div>
                  <div className="stat-sub">Hedera + RSK</div>
                </div>
                <div className="stat-card amber">
                  <div className="stat-label">{t.stats.audits}</div>
                  <div className="stat-value">AI</div>
                  <div className="stat-sub">DeepSeek-R1</div>
                </div>
              </div>

              <div className="panel">
                <div className="panel-header">
                  <span className="panel-title">{t.form.title}</span>
                </div>
                <div className="form-section">
                  <div className="form-title">{t.form.title}</div>
                  <div className="form-subtitle">{t.form.subtitle}</div>

                  <div className="mode-tabs">
                    <button 
                      type="button"
                      className={`mode-tab ${mode === 'verify' ? 'active' : ''}`}
                      onClick={() => { setMode('verify'); setResult(null); setError(null); }}
                    >
                      {t.form.tabVerify}
                    </button>
                    <button 
                      type="button"
                      className={`mode-tab ${mode === 'check' ? 'active' : ''}`}
                      onClick={() => { setMode('check'); setResult(null); setError(null); }}
                    >
                      {t.form.tabCheck}
                    </button>
                  </div>

                  <form onSubmit={handleSubmit}>
                    <div className="form-grid">
                      {mode === 'verify' && (
                        <>
                          <div className="form-group">
                            <label htmlFor="lat">{t.form.lat}</label>
                            <input type="text" id="lat" name="lat" placeholder="-33.4942" required />
                          </div>
                          <div className="form-group">
                            <label htmlFor="lon">{t.form.lon}</label>
                            <input type="text" id="lon" name="lon" placeholder="-69.2429" required />
                          </div>
                        </>
                      )}
                      <div className="form-group full-width">
                        <label htmlFor="assetAddress">{t.form.asset}</label>
                        <input type="text" id="assetAddress" name="assetAddress" placeholder="0x..." required />
                      </div>
                      <div className="form-group full-width">
                        <label htmlFor="tokenId">{t.form.token}</label>
                        <input type="number" id="tokenId" name="tokenId" placeholder="1" required />
                      </div>
                    </div>

                    <button type="submit" className="verify-btn" disabled={loading}>
                      {loading ? (
                        <>
                          <span className="spinner" aria-hidden="true" />
                          {t.result.loading}
                        </>
                      ) : (
                        <>
                          {t.form.button}
                          <span aria-hidden="true">→</span>
                        </>
                      )}
                    </button>
                  </form>

                  <div className={`result-panel ${statusType !== 'idle' ? 'visible' : ''}`}>
                    <div className="result-header">
                      <span className={`result-status ${statusType}`}>
                        {statusType === 'loading' && t.result.loading}
                        {statusType === 'success' && (mode === 'check' ? t.result.existing : t.result.status)}
                        {statusType === 'error' && t.result.error}
                      </span>
                    </div>

                    {result && (
                      <div className="audit-dashboard">
                        {mode === 'check' ? (
                          <div className="existing-cert">
                            <div className="cert-details">
                              <div className="cert-score">
                                <span className="cert-score-value">{result.vitis_score}</span>
                                <span className="cert-score-label">{t.result.score}</span>
                              </div>
                              <div className="cert-info">
                                <div className="cert-row">
                                  <span className="cert-label">Asset</span>
                                  <span className="cert-value">{result.asset_address}</span>
                                </div>
                                <div className="cert-row">
                                  <span className="cert-label">Token ID</span>
                                  <span className="cert-value">#{result.token_id}</span>
                                </div>
                                <div className="cert-row">
                                  <span className="cert-label">Timestamp</span>
                                  <span className="cert-value">{result.timestamp}</span>
                                </div>
                                <div className="cert-row">
                                  <span className="cert-label">Hedera Topic</span>
                                  <span className="cert-value">{result.hedera_topic_id}</span>
                                </div>
                              </div>
                            </div>
                          </div>
                        ) : (
                          <div className="new-audit-result">
                            <div className="technical-view">
                              <div className="satellite-container">
                                <div className="scan-line"></div>
                                <img src={result.satellite_img} alt="Satellite NDVI Analysis" className="satellite-img" />
                                <div className="overlay-tag top-left">SENTINEL-2 L2A</div>
                                <div className="overlay-tag bottom-right">MZA_{result.vitis_score}_NDVI</div>
                                <div className="map-legend">
                                  <div className="legend-item"><span className="dot green"></span> 0.7+ High</div>
                                  <div className="legend-item"><span className="dot yellow"></span> 0.4+ Mod</div>
                                  <div className="legend-item"><span className="dot red"></span> 0.2- Stress</div>
                                </div>
                              </div>
                              <div className="main-score-card">
                                <div className="score-circle" style={{ borderColor: getRiskColor(result.risk) }}>
                                  <span className="score-value">{result.vitis_score}</span>
                                  <span className="score-label">VitisScore</span>
                                </div>
                                <div className="risk-badge" style={{ backgroundColor: getRiskColor(result.risk) }}>
                                  {result.risk?.toUpperCase()} RISK
                                </div>
                              </div>
                            </div>
                            <div className="quick-validation-grid">
                              <div className={`val-pill ${result.validation?.geolocation?.valid ? 'ok' : 'warn'}`}>
                                📍 {result.validation?.geolocation?.region || 'Geo Valid'}
                              </div>
                              <div className={`val-pill ${result.validation?.vegetation?.valid ? 'ok' : 'warn'}`}>
                                🌿 NDVI: {result.ndvi?.toFixed(3)}
                              </div>
                              <div className="val-pill ok">🛡️ Hedera Notarized</div>
                            </div>
                            {result.investment_analysis && (
                              <div className="investment-analysis-panel">
                                <div className="investment-header">
                                  <h3>{t.investment.title}</h3>
                                  <span className={`recommendation-label ${result.investment_analysis.recommendation?.toLowerCase()}`}>
                                    {result.investment_analysis.recommendation}
                                  </span>
                                </div>
                                <p className="ai-justification">"{result.justification}"</p>
                                <div className="investment-stats-grid">
                                  <div className="i-stat">
                                    <span className="i-label">{t.investment.yieldForecast}</span>
                                    <span className="i-value">{result.investment_analysis.yield_forecast}</span>
                                  </div>
                                  <div className="i-stat">
                                    <span className="i-label">{t.investment.confidence}</span>
                                    <span className="i-value">{result.investment_analysis.confidence}</span>
                                  </div>
                                  <div className="i-stat">
                                    <span className="i-label">Trend</span>
                                    <span className="i-value">{result.investment_analysis.price_trend}</span>
                                  </div>
                                </div>
                              </div>
                            )}
                            <div className="blockchain-proofs">
                              <div className="proof-item">
                                <span className="p-icon">◈</span>
                                <div className="p-data">
                                  <span className="p-label">Hedera Topic ID</span>
                                  <span className="p-hash">{result.hedera_notarization}</span>
                                </div>
                              </div>
                              <div className="proof-item">
                                <span className="p-icon">⬡</span>
                                <div className="p-data">
                                  <span className="p-label">Rootstock Transaction</span>
                                  <a href={`https://explorer.testnet.rsk.co/tx/${result.rsk_tx_hash}`} target="_blank" className="p-link">
                                    {result.rsk_tx_hash?.substring(0, 16)}...
                                  </a>
                                </div>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {error && (
                      <div className="error-message">{error}</div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="sidebar-right">
              <div className="info-card">
                <div className="info-card-header">
                  <div className="info-icon">🔎</div>
                  <span className="info-title">API</span>
                </div>
                <div className="info-list">
                  <div className="info-item">
                    <span className="info-key">Satellite</span>
                    <span className="info-val">Sentinel Hub</span>
                  </div>
                  <div className="info-item">
                    <span className="info-key">AI Model</span>
                    <span className="info-val">Groq LLMs</span>
                  </div>
                  <div className="info-item">
                    <span className="info-key">Endpoint</span>
                    <span className="info-val">:8000</span>
                  </div>
                </div>
              </div>

              <div className="info-card">
                <div className="info-card-header">
                  <div className="info-icon">📊</div>
                  <span className="info-title">Metrics</span>
                </div>
                <div className="info-list">
                  <div className="info-item">
                    <span className="info-key">NDVI Range</span>
                    <span className="info-val">0.1 - 0.9</span>
                  </div>
                  <div className="info-item">
                    <span className="info-key">Score Range</span>
                    <span className="info-val">0 - 100</span>
                  </div>
                  <div className="info-item">
                    <span className="info-key">Region</span>
                    <span className="info-val">Mendoza</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </main>

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
