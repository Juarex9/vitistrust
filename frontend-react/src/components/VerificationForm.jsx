export default function VerificationForm({ 
  t, 
  mode, 
  setMode, 
  loading, 
  handleSubmit,
  setResult,
  setError
}) {
  return (
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
      </div>
    </div>
  )
}