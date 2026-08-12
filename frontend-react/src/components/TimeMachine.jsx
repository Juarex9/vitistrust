export default function TimeMachine({ t, timeMachineData, timeMachineIndex, setTimeMachineIndex }) {
  if (!timeMachineData?.history) return null

  const currentData = timeMachineData.history[timeMachineIndex]
  const firstData = timeMachineData.history[0]
  const isDemo = timeMachineData.demo || timeMachineData.source === 'synthetic_demo'

  const change = currentData?.ndvi - firstData?.ndvi || 0
  const changePercent = (change * 100).toFixed(1)
  const isPositive = change > 0
  const tm = t?.timeMachine || {}

  return (
    <div className="time-machine">
      <div className="tm-header">
        <span className="tm-title">
          ⏱️ {tm.title || 'Time Machine'}
          {isDemo && <span className="proof-mock-badge">DEMO</span>}
        </span>
        <span className="tm-current-date">
          {currentData?.date || '2025-01'}
        </span>
      </div>
      {isDemo && (
        <div className="modal-mock-note" style={{ marginBottom: '0.75rem' }}>
          {tm.demoNote || 'Synthetic NDVI history for demo — not live Sentinel series.'}
        </div>
      )}
      <div className="tm-slider-container">
        <input
          type="range"
          className="tm-slider"
          min="0"
          max={timeMachineData.history.length - 1}
          value={timeMachineIndex}
          onChange={(e) => setTimeMachineIndex(parseInt(e.target.value))}
        />
        <div className="tm-labels">
          <span>{firstData?.date}</span>
          <span>{timeMachineData.history[timeMachineData.history.length - 1]?.date}</span>
        </div>
      </div>
      <div className="tm-stats">
        <div className="tm-stat">
          <span className="tm-stat-label">NDVI</span>
          <span className="tm-stat-value">
            {currentData?.ndvi?.toFixed(3)}
          </span>
        </div>
        <div className="tm-stat">
          <span className="tm-stat-label">{tm.change || 'Change'}</span>
          <span className={`tm-stat-value ${isPositive ? 'positive' : 'negative'}`}>
            {isPositive ? '+' : ''}{changePercent}%
          </span>
        </div>
        <div className="tm-stat">
          <span className="tm-stat-label">{tm.trend || 'Trend'}</span>
          <span className={`tm-stat-value ${
            currentData?.status === 'healthy' ? 'positive' :
            currentData?.status === 'stressed' ? 'negative' : ''
          }`}>
            {currentData?.status?.toUpperCase()}
          </span>
        </div>
      </div>
    </div>
  )
}
