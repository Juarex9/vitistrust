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

  const hasResultCoords = Number.isFinite(result?.lat) && Number.isFinite(result?.lon)
  const validationGeo = result?.validation?.validations?.geolocation
  const validationVegetation = result?.validation?.validations?.vegetation

  useEffect(() => {
    if (result?.ndvi && hasResultCoords) {
      fetch(`${API_BASE}/satellite/history?lat=${result.lat}&lon=${result.lon}&months=24`)
        .then(res => res.json())
        .then(data => setTimeMachineData(data))
        .catch(console.error)
    } else {
      setTimeMachineData(null)
    }
  }, [result, hasResultCoords])

  useEffect(() => {
    if (hasResultCoords) {
      fetch(`${API_BASE}/satellite/layers?lat=${result.lat}&lon=${result.lon}`)
        .then(res => res.json())
        .then(data => {
          if (data.layers?.[activeLayer]) {
            setResult(prev => ({ ...prev, satellite_img: data.layers[activeLayer] }))
          }
        })
        .catch(console.error)
    }
  }, [activeLayer, hasResultCoords, result?.lat, result?.lon])

  const getRiskColor = (risk) => {
    const colors = { low: '#10b981', medium: '#f59e0b', high: '#f43f5e' }
    return colors[risk?.toLowerCase()] || '#6b7280'
  }

  const getAlertColor = (severity) => {
    const colors = { low: '#38bdf8', medium: '#f59e0b', high: '#f43f5e' }
    return colors[severity?.toLowerCase()] || '#6b7280'
  const breakdownLabels = {
    vegetation: 'Vegetation',
    humidity: 'Humidity',
    temporal_consistency: 'Temporal',
    data_quality: 'Data Quality',
    ai_reliability: 'AI Reliability'
  }

  const breakdownColors = {
    vegetation: '#22c55e',
    humidity: '#3b82f6',
    temporal_consistency: '#a78bfa',
    data_quality: '#f59e0b',
    ai_reliability: '#14b8a6'
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const formData = new FormData(e.target)
    const lat = formData.get('lat')
    const lon = formData.get('lon')
    const farmId = formData.get('farmId')

    setLoading(true)
    setError(null)
    setResult(null)
    setStatusType('loading')

    try {
      const url = verifyMode === 'check' 
        ? `${API_BASE}/certificate/${farmId}`
        : `${API_BASE}/verify-vineyard?lat=${lat}&lon=${lon}&farm_id=${farmId}`
      
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
                  <div className="form-group full-width">
                    <label htmlFor="farmId">{t.form.farm}</label>
                    <input type="text" id="farmId" name="farmId" placeholder="mendoza_1" required />
                  </div>
                </>
              )}
              {verifyMode === 'check' && (
                <div className="form-group full-width">
                  <label htmlFor="farmId">{t.form.farm}</label>
                  <input type="text" id="farmId" name="farmId" placeholder="mendoza_1" required />
                </div>
              )}
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
                        <span className="cert-score-value">{result.vitis_score || result.vitals_score}</span>
                        <span className="cert-score-label">{t.result.score}</span>
                      </div>
                      <div className="cert-info">
                        <div className="cert-row"><span className="cert-label">Farm ID</span><span className="cert-value">{result.farm_id}</span></div>
                        <div className="cert-row"><span className="cert-label">Timestamp</span><span className="cert-value">{result.timestamp}</span></div>
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
                        {result?.satellite_img ? (
                          <img src={result.satellite_img} alt="Satellite" className="satellite-img" />
                        ) : (
                          <div className="satellite-img">No satellite image available</div>
                        )}
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
                        {result.regional_benchmark && (
                          <div className="regional-benchmark-card">
                            <span className="regional-title">{t.result.comparedRegion}</span>
                            <span className="regional-region">{result.regional_benchmark.region}</span>
                            <div className="regional-row">
                              <span>{t.result.percentile}</span>
                              <strong>{result.regional_benchmark.percentile_ndvi}%</strong>
                            </div>
                            <div className="regional-row">
                              <span>{t.result.delta}</span>
                              <strong className={result.regional_benchmark.delta_vs_region_avg >= 0 ? 'positive' : 'negative'}>
                                {result.regional_benchmark.delta_vs_region_avg >= 0 ? '+' : ''}
                                {result.regional_benchmark.delta_vs_region_avg}
                              </strong>
                            </div>
                          </div>
                        )}
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
                          <div className="tm-stat">
                            <span className="tm-stat-label">Δ mensual</span>
                            <span className={`tm-stat-value ${(timeMachineData.history[timeMachineIndex]?.monthly_change || 0) >= 0 ? 'positive' : 'negative'}`}>
                              {timeMachineData.history[timeMachineIndex]?.monthly_change == null
                                ? 'N/A'
                                : `${timeMachineData.history[timeMachineIndex]?.monthly_change > 0 ? '+' : ''}${timeMachineData.history[timeMachineIndex]?.monthly_change?.toFixed(3)}`}
                            </span>
                          </div>
                          <div className="tm-stat">
                            <span className="tm-stat-label">Media móvil 3m</span>
                            <span className="tm-stat-value">{timeMachineData.history[timeMachineIndex]?.moving_avg_3m?.toFixed(3)}</span>
                          </div>
                        </div>
                      </div>
                    )}

                    {(result.alerts?.length > 0 || timeMachineData?.alerts?.length > 0) && (
                      <div className="alerts-panel">
                        <div className="alerts-title">Alertas de salud</div>
                        {[...(result.alerts || []), ...(timeMachineData?.alerts || [])]
                          .filter((alert, index, self) => self.findIndex((item) => item.rule_id === alert.rule_id) === index)
                          .map((alert) => (
                            <div
                              key={alert.rule_id}
                              className="alert-badge"
                              style={{ borderColor: getAlertColor(alert.severity) }}
                            >
                              <span
                                className="alert-severity"
                                style={{ backgroundColor: getAlertColor(alert.severity) }}
                              >
                                {alert.severity?.toUpperCase()}
                              </span>
                              <div className="alert-content">
                                <div className="alert-title">{alert.title}</div>
                                <div className="alert-cause">{alert.probable_cause}</div>
                              </div>
                            </div>
                          ))}
                      </div>
                    )}

                    <div className="quick-validation-grid">
                      <div className={`val-pill ${result.validation?.geolocation?.valid ? 'ok' : 'warn'}`}>📍 Geo</div>
                      <div className={`val-pill ${result.validation?.vegetation?.valid ? 'ok' : 'warn'}`}>🌿 NDVI: {result.ndvi?.toFixed(3)}</div>
                    </div>
                    {result?.validation && (
                      <div className="quick-validation-grid">
                        <div className={`val-pill ${validationGeo?.valid ? 'ok' : 'warn'}`}>📍 Geo</div>
                        <div className={`val-pill ${validationVegetation?.valid ? 'ok' : 'warn'}`}>
                          🌿 NDVI: {typeof result?.ndvi === 'number' ? result.ndvi.toFixed(3) : 'N/A'}
                        </div>
                      </div>
                    )}

                    {result.investment_analysis && (
                      <div className="investment-analysis-panel">
                        <div className="investment-header">
                          <h3>Investment Analysis</h3>
                          <span className={`recommendation-label ${result.investment_analysis.recommendation?.toLowerCase() || ''}`}>
                            {result.investment_analysis.recommendation || 'N/A'}
                          </span>
                        </div>
                        {result.justification && <p className="ai-justification">"{result.justification}"</p>}
                      </div>
                    )}

                    {result.score_breakdown?.components && (
                      <div className="score-breakdown-panel">
                        <div className="investment-header">
                          <h3>Score Breakdown</h3>
                          <span className="score-model-version">{result.score_model_version || 'v1.0.0'}</span>
                        </div>
                        <div className="stacked-bar">
                          {Object.entries(result.score_breakdown.components).map(([key, component]) => (
                            <div
                              key={key}
                              className="stacked-segment"
                              style={{
                                width: `${component.weight * 100}%`,
                                backgroundColor: breakdownColors[key] || '#334155'
                              }}
                              title={`${breakdownLabels[key] || key}: +${component.contribution}`}
                            />
                          ))}
                        </div>
                        <div className="breakdown-list">
                          {Object.entries(result.score_breakdown.components).map(([key, component]) => (
                            <div key={key} className="breakdown-row">
                              <span className="breakdown-dot" style={{ backgroundColor: breakdownColors[key] || '#334155' }} />
                              <span className="breakdown-name">{breakdownLabels[key] || key}</span>
                              <span className="breakdown-values">
                                {component.component_score?.toFixed(1)} × {(component.weight * 100).toFixed(0)}% = +{component.contribution?.toFixed(2)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="blockchain-proofs">
                      <div className="proof-item">
                        <span className="p-icon">◈</span>
                        <div className="p-data">
                          <span className="p-label">Hedera HCS</span>
                          <span className="p-hash">{result.hedera_notarization}</span>
                        </div>
                      </div>
                      <div className="proof-item">
                        <span className="p-icon">✦</span>
                        <div className="p-data">
                          <span className="p-label">Stellar TX</span>
                          <span className="p-hash">{result.stellar_tx_hash?.substring(0, 16)}...</span>
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
