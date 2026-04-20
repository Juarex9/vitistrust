export default function SatelliteView({ 
  result, 
  activeLayer, 
  setActiveLayer,
  setShowOracleModal,
  t,
  getRiskColor 
}) {
  const layers = [
    { key: 'ndvi', label: t.layers.ndvi },
    { key: 'ndmi', label: t.layers.ndmi },
    { key: 'truecolor', label: t.layers.truecolor }
  ]

  const layerTags = {
    ndvi: 'SENTINEL-2 L2A',
    ndmi: 'SENTINEL-2 NDMI',
    truecolor: 'SENTINEL-2 TRUE COLOR'
  }

  const legends = {
    ndvi: [
      { color: 'green', text: '0.7+ High' },
      { color: 'yellow', text: '0.4+ Mod' },
      { color: 'red', text: '0.2- Stress' }
    ],
    ndmi: [
      { color: 'green', text: '0.4+ Hydrated' },
      { color: 'yellow', text: '0.1- Moderate' },
      { color: 'red', text: '-0.2+ Stressed' }
    ],
    truecolor: [
      { color: 'green', text: 'Vegetation' },
      { color: 'yellow', text: 'Soil' },
      { color: 'red', text: 'Urban' }
    ]
  }

  return (
    <div className="new-audit-result">
      <div className="layer-toggle">
        {layers.map((layer) => (
          <button 
            key={layer.key}
            type="button"
            className={`layer-btn ${layer.key} ${activeLayer === layer.key ? 'active' : ''}`}
            onClick={() => setActiveLayer(layer.key)}
          >
            {layer.label}
          </button>
        ))}
      </div>
      
      <div className="technical-view">
        <div className="satellite-container">
          <div className="scan-line"></div>
          <img 
            src={result.satellite_img} 
            alt={`Satellite ${activeLayer.toUpperCase()} Analysis`} 
            className="satellite-img" 
          />
          
          <div 
            className="oracle-badge" 
            onClick={() => setShowOracleModal(true)}
            title="View Blockchain Proof"
          >
            <span className="oracle-badge-icon">🛡️</span>
          </div>
          
          <div className="overlay-tag top-left">
            {layerTags[activeLayer]}
          </div>
          <div className="overlay-tag bottom-right">
            MZA_{result.vitis_score}_{activeLayer.toUpperCase()}
          </div>
          <div className="map-legend">
            {legends[activeLayer].map((item) => (
              <div key={item.text} className="legend-item">
                <span className={`dot ${item.color}`}></span> {item.text}
              </div>
            ))}
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
    </div>
  )
}