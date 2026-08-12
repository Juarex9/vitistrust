function isMockRootstockTx(result) {
  if (result?.rootstock_stub) return true
  const hash = result?.rootstock_tx_hash || ''
  return hash.startsWith('mock_rsk_') || hash.includes('mock')
}

export default function OracleModal({ t, result, onClose }) {
  if (!result) return null

  const oracle = t.oracle || {}
  const hederaTopic = result.hedera_txn_id || result.hedera_notarization
  const rskTx = result.rootstock_tx_hash
  const stub = isMockRootstockTx(result)
  const hederaExplorerId = result.hedera_txn_id
  const canLinkHedera = Boolean(hederaExplorerId && !String(hederaExplorerId).includes('MOCK'))
  const canLinkRsk = Boolean(rskTx && !stub)

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-icon">🛡️</div>
          <div>
            <div className="modal-title">{oracle.title}</div>
            <div className="modal-subtitle">{oracle.subtitle}</div>
          </div>
        </div>
        <div className="modal-body">
          <div className="modal-item">
            <div className="modal-label">◈ {oracle.hederaTopic}</div>
            <div className="modal-value">
              {hederaTopic}
              {canLinkHedera && (
                <a
                  href={`https://hashscan.io/testnet/transaction/${hederaExplorerId}`}
                  target="_blank"
                  rel="noreferrer"
                  className="modal-link"
                >
                  {oracle.viewExplorer} ↗
                </a>
              )}
            </div>
          </div>
          <div className="modal-item">
            <div className="modal-label">
              ⬡ {oracle.rskTx}
              {stub && <span className="modal-mock-badge"> {oracle.mockBadge}</span>}
            </div>
            <div className="modal-value">
              {rskTx}
              {stub && (
                <div className="modal-mock-note">{oracle.mockNote}</div>
              )}
              {canLinkRsk && (
                <a
                  href={`https://explorer.testnet.rsk.co/tx/${rskTx}`}
                  target="_blank"
                  rel="noreferrer"
                  className="modal-link"
                >
                  {oracle.viewExplorer} ↗
                </a>
              )}
            </div>
          </div>
        </div>
        <button className="modal-close" onClick={onClose}>
          {oracle.close}
        </button>
      </div>
    </div>
  )
}
