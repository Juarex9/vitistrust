export default function TimeMachine({ t, timeMachineData, timeMachineIndex, setTimeMachineIndex }) {
  if (!timeMachineData?.history) return null

  const currentData = timeMachineData.history[timeMachineIndex]
  const firstData = timeMachineData.history[0]
  
  const change = currentData?.ndvi - firstData?.ndvi || 0
  const changePercent = (change * 100).toFixed(1)
  const isPositive = change > 0

  return (
    <div className="time-machine">
      <div className="tm-header">
        <span className="tm-title">⏱️ {t.timeMachine.title}</span>
        <span className="tm-current-date">
          {currentData?.date || '2025-01'}
        </span>
      </div>
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
          <span className="tm-stat-label">{t.timeMachine.change}</span>
          <span className={`tm-stat-value ${isPositive ? 'positive' : 'negative'}`}>
            {isPositive ? '+' : ''}{changePercent}%
          </span>
        </div>
        <div className="tm-stat">
          <span className="tm-stat-label">{t.timeMachine.trend}</span>
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