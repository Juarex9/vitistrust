import { useState, useEffect } from 'react'
import SatelliteView from '../components/SatelliteView'
import TimeMachine from '../components/TimeMachine'
import OracleModal from '../components/OracleModal'

const API_BASE = import.meta.env.VITE_API_URL || 'https://vitistrust.onrender.com'

export default function VerifySection({ t }) {
  const [verifyMode, setVerifyMode] = useState('verify')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [statusType, setStatusType] = useState('idle')
  
  const [activeLayer, setActiveLayer] = useState('ndvi')
  const [timeMachineIndex, setTimeMachineIndex] = useState(0)
  const [timeMachineData, setTimeMachineData] = useState(null)
  const [showOracleModal, setShowOracleModal] = useState(false)

  useEffect(() => {
    if (result?.ndvi && result.validation?.geolocation?.valid) {
      const lat = parseFloat(result.validation.geolocation.region?.split(',')[0] || '-33.5')
      const lon = parseFloat(result.validation.geolocation.region?.split(',')[1] || '-69.2')
      fetch(`${API_BASE}/satellite/history?lat=${lat}&lon=${lon}&months=24`)
        .then(res => res.json())
        .then(data => setTimeMachineData(data))
        .catch(console.error)
    }
  }, [result])

  useEffect(() => {
    if (result?.validation?.geolocation?.valid) {
      fetch(`${API_BASE}/satellite/layers?lat=-33.5&lon=-69.2`)
        .then(res => res.json())
        .then(data => {
          if (data.layers?.[activeLayer]) {
            setResult(prev => ({ ...prev, satellite_img: data.layers[activeLayer] }))
          }
        })
        .catch(console.error)
    }
  }, [activeLayer])

  const getRiskColor = (risk) => {
    const colors = { low: '#10b981', medium: '#f59e0b', high: '#f43f5e' }
    return colors[risk?.toLowerCase()] || '#6b7280'
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
      const url = verifyMode === 'check' 
        ? `${API_BASE}/certificate/${assetAddress}/${tokenId}`
        : `${API_BASE}/verify-vineyard?lat=${lat}&lon=${lon}&asset_address=${assetAddress}&token_id=${tokenId}`
      
      const response = await fetch(url)
      if (!response.ok) throw new Error((await response.json()).detail || 'Verification failed')
      
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
    <section id="verify" className="page-section">
      <div className="page-header">
        <h1>{t.form.title}</h1>
        <p>{t.form.subtitle}</p>
      </div>

      <div className="panel">
        <div className="panel-header"><span className="panel-title">{t.form.title}</span></div>
        <div className="form-section">
          <div className="form-title">{t.form.title}</div>
          <div className="form-subtitle">{t.form.subtitle}</div>

          <div className="mode-tabs">
            <button type="button" className={`mode-tab ${verifyMode === 'verify' ? 'active' : ''}`} onClick={() => { setVerifyMode('verify'); setResult(null); setError(null); }}>
              {t.form.tabVerify}
            </button>
            <button type="button" className={`mode-tab ${verifyMode === 'check' ? 'active' : ''}`} onClick={() => { setVerifyMode('check'); setResult(null); setError(null); }}>
              {t.form.tabCheck}
            </button>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="form-grid">
              {verifyMode === 'verify' && (
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
              {loading ? <><span className="spinner"></span>{t.result.loading}</> : <>{t.form.button}→</>}
            </button>
          </form>

          <div className={`result-panel ${statusType !== 'idle' ? 'visible' : ''}`}>
            <div className="result-header">
              <span className={`result-status ${statusType}`}>
                {statusType === 'loading' && t.result.loading}
                {statusType === 'success' && (verifyMode === 'check' ? t.result.existing : t.result.status)}
                {statusType === 'error' && t.result.error}
              </span>
            </div>

            {result && (
              <div className="audit-dashboard">
                {verifyMode === 'check' ? (
                  <div className="existing-cert">
                    <div className="cert-details">
                      <div className="cert-score">
                        <span className="cert-score-value">{result.vitis_score}</span>
                        <span className="cert-score-label">{t.result.score}</span>
                      </div>
                      <div className="cert-info">
                        <div className="cert-row"><span className="cert-label">Asset</span><span className="cert-value">{result.asset_address}</span></div>
                        <div className="cert-row"><span className="cert-label">Token ID</span><span className="cert-value">#{result.token_id}</span></div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="layer-toggle">
                      <button type="button" className={`layer-btn ndvi ${activeLayer === 'ndvi' ? 'active' : ''}`} onClick={() => setActiveLayer('ndvi')}>NDVI</button>
                      <button type="button" className={`layer-btn ndmi ${activeLayer === 'ndmi' ? 'active' : ''}`} onClick={() => setActiveLayer('ndmi')}>Moisture</button>
                      <button type="button" className={`layer-btn truecolor ${activeLayer === 'truecolor' ? 'active' : ''}`} onClick={() => setActiveLayer('truecolor')}>True Color</button>
                    </div>
                    
                    <div className="technical-view">
                      <div className="satellite-container">
                        <div className="scan-line"></div>
                        <img src={result.satellite_img} alt="Satellite" className="satellite-img" />
                        <div className="oracle-badge" onClick={() => setShowOracleModal(true)}><span>🛡️</span></div>
                        <div className="overlay-tag top-left">SENTINEL-2</div>
                        <div className="overlay-tag bottom-right">MZA_{result.vitis_score}</div>
                      </div>
                      <div className="main-score-card">
                        <div className="score-circle" style={{ borderColor: getRiskColor(result.risk) }}>
                          <span className="score-value">{result.vitis_score}</span>
                          <span className="score-label">VitisScore</span>
                        </div>
                        <div className="risk-badge" style={{ backgroundColor: getRiskColor(result.risk) }}>{result.risk?.toUpperCase()} RISK</div>
                      </div>
                    </div>

                    {timeMachineData?.history && (
                      <div className="time-machine">
                        <div className="tm-header">
                          <span className="tm-title">⏱️ Time Machine</span>
                          <span className="tm-current-date">{timeMachineData.history[timeMachineIndex]?.date}</span>
                        </div>
                        <input type="range" className="tm-slider" min="0" max={timeMachineData.history.length - 1} value={timeMachineIndex} onChange={(e) => setTimeMachineIndex(parseInt(e.target.value))} />
                        <div className="tm-stats">
                          <div className="tm-stat"><span className="tm-stat-label">NDVI</span><span className="tm-stat-value">{timeMachineData.history[timeMachineIndex]?.ndvi?.toFixed(3)}</span></div>
                          <div className="tm-stat"><span className="tm-stat-label">Status</span><span className="tm-stat-value">{timeMachineData.history[timeMachineIndex]?.status?.toUpperCase()}</span></div>
                        </div>
                      </div>
                    )}

                    <div className="quick-validation-grid">
                      <div className={`val-pill ${result.validation?.geolocation?.valid ? 'ok' : 'warn'}`}>📍 Geo</div>
                      <div className={`val-pill ${result.validation?.vegetation?.valid ? 'ok' : 'warn'}`}>🌿 NDVI: {result.ndvi?.toFixed(3)}</div>
                    </div>

                    {result.investment_analysis && (
                      <div className="investment-analysis-panel">
                        <div className="investment-header">
                          <h3>Investment Analysis</h3>
                          <span className={`recommendation-label ${result.investment_analysis.recommendation?.toLowerCase()}`}>{result.investment_analysis.recommendation}</span>
                        </div>
                        <p className="ai-justification">"{result.justification}"</p>
                      </div>
                    )}

                    <div className="blockchain-proofs">
                      <div className="proof-item">
                        <span className="p-icon">◈</span>
                        <div className="p-data">
                          <span className="p-label">Hedera Topic</span>
                          <span className="p-hash">{result.hedera_notarization}</span>
                        </div>
                      </div>
                      <div className="proof-item">
                        <span className="p-icon">⬡</span>
                        <div className="p-data">
                          <span className="p-label">Rootstock TX</span>
                          <a href={`https://explorer.testnet.rsk.co/tx/${result.rsk_tx_hash}`} target="_blank" className="p-link">{result.rsk_tx_hash?.substring(0, 16)}...</a>
                        </div>
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}

            {error && <div className="error-message">{error}</div>}
          </div>
        </div>
      </div>

      <OracleModal t={t} result={showOracleModal ? result : null} onClose={() => setShowOracleModal(false)} />
    </section>
  )
}