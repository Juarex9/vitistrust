export default function OracleModal({ t, result, onClose }) {
  if (!result) return null

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-icon">🛡️</div>
          <div>
            <div className="modal-title">{t.oracle.title}</div>
            <div className="modal-subtitle">{t.oracle.subtitle}</div>
          </div>
        </div>
        <div className="modal-body">
          <div className="modal-item">
            <div className="modal-label">◈ {t.oracle.hederaTopic}</div>
            <div className="modal-value">
              {result.hedera_notarization}
              <a 
                href={`https://testnet.hashscan.io/topic/${result.hedera_notarization}`} 
                target="_blank" 
                className="modal-link"
              >
                {t.oracle.viewExplorer} ↗
              </a>
            </div>
          </div>
          <div className="modal-item">
            <div className="modal-label">⬡ {t.oracle.rskTx}</div>
            <div className="modal-value">
              {result.rsk_tx_hash}
              <a 
                href={`https://explorer.testnet.rsk.co/tx/${result.rsk_tx_hash}`} 
                target="_blank" 
                className="modal-link"
              >
                {t.oracle.viewExplorer} ↗
              </a>
            </div>
          </div>
        </div>
        <button className="modal-close" onClick={onClose}>
          {t.oracle.close}
        </button>
      </div>
    </div>
  )
}