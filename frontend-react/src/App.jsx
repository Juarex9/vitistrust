import { useState, useEffect } from 'react'
import { ethers } from 'ethers'
import './index.css'

const RSK_TESTNET_CHAIN_ID = '0x1f'

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
      button: 'Run Verification'
    },
    result: {
      status: 'CERTIFIED',
      score: 'VitisScore',
      risk: 'Risk Level',
      hedera: 'Hedera Topic',
      tx: 'RSK TX',
      loading: 'Verifying...',
      error: 'Verification Failed'
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
    },
    wallet: {
      connect: 'Connect',
      connecting: 'Connecting...',
      disconnect: 'Disconnect',
      wrongNetwork: 'Wrong Network',
      connected: 'Connected'
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
      button: 'Ejecutar Verificación'
    },
    result: {
      status: 'CERTIFICADO',
      score: 'VitisScore',
      risk: 'Nivel de Riesgo',
      hedera: 'Tópico Hedera',
      tx: 'TX RSK',
      loading: 'Verificando...',
      error: 'Verificación Fallida'
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
    },
    wallet: {
      connect: 'Conectar',
      connecting: 'Conectando...',
      disconnect: 'Desconectar',
      wrongNetwork: 'Red Incorrecta',
      connected: 'Conectado'
    }
  }
}

const RSK_TESTNET_PARAMS = {
  chainId: RSK_TESTNET_CHAIN_ID,
  chainName: 'Rootstock Testnet',
  nativeCurrency: {
    name: 'RBTC',
    symbol: 'RBTC',
    decimals: 18
  },
  rpcUrls: ['https://public-node.testnet.rsk.co'],
  blockExplorerUrls: ['https://explorer.testnet.rsk.co']
}

function App() {
  const [lang, setLang] = useState('en')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [statusType, setStatusType] = useState('idle')
  
  const [wallet, setWallet] = useState({
    connected: false,
    address: null,
    connecting: false,
    wrongNetwork: false
  })
  
  const t = translations[lang]

  useEffect(() => {
    checkWalletConnection()
    if (window.ethereum) {
      window.ethereum.on('chainChanged', handleChainChanged)
      window.ethereum.on('accountsChanged', handleAccountsChanged)
    }
    return () => {
      if (window.ethereum) {
        window.ethereum.removeListener('chainChanged', handleChainChanged)
        window.ethereum.removeListener('accountsChanged', handleAccountsChanged)
      }
    }
  }, [])

  const checkWalletConnection = async () => {
    if (!window.ethereum) return
    
    try {
      const provider = new ethers.BrowserProvider(window.ethereum)
      const accounts = await provider.listAccounts()
      if (accounts.length > 0) {
        const network = await provider.getNetwork()
        setWallet({
          connected: true,
          address: accounts[0].address,
          connecting: false,
          wrongNetwork: network.chainId !== 31n
        })
      }
    } catch (err) {
      console.error('Error checking wallet:', err)
    }
  }

  const handleChainChanged = (chainId) => {
    const isRSK = parseInt(chainId, 16) === 31
    setWallet(prev => ({ ...prev, wrongNetwork: !isRSK }))
  }

  const handleAccountsChanged = (accounts) => {
    if (accounts.length === 0) {
      setWallet({ connected: false, address: null, connecting: false, wrongNetwork: false })
    } else {
      setWallet(prev => ({ ...prev, address: accounts[0] }))
    }
  }

  const connectWallet = async () => {
    if (!window.ethereum) {
      alert('MetaMask not installed. Please install MetaMask to use this feature.')
      return
    }

    setWallet(prev => ({ ...prev, connecting: true }))

    try {
      const provider = new ethers.BrowserProvider(window.ethereum)
      await provider.send('eth_requestAccounts', [])
      
      const network = await provider.getNetwork()
      const isRSK = network.chainId === 31n

      if (!isRSK) {
        try {
          await provider.send('wallet_switchEthereumChain', [{ chainId: RSK_TESTNET_CHAIN_ID }])
        } catch {
          await provider.send('wallet_addEthereumChain', [RSK_TESTNET_PARAMS])
        }
      }

      const accounts = await provider.listAccounts()
      setWallet({
        connected: true,
        address: accounts[0].address,
        connecting: false,
        wrongNetwork: false
      })
    } catch (err) {
      console.error('Error connecting wallet:', err)
      setWallet(prev => ({ ...prev, connecting: false }))
    }
  }

  const disconnectWallet = () => {
    setWallet({ connected: false, address: null, connecting: false, wrongNetwork: false })
  }

  const shortenAddress = (addr) => {
    return `${addr.slice(0, 6)}...${addr.slice(-4)}`
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
      <div className="bg-pattern" />
      
      <div className="content">
        <header>
          <div className="logo">
            <div className="logo-icon">⬡</div>
            <span className="logo-text">VitisTrust</span>
            <span className="logo-version">v1.0</span>
          </div>
          
          <div className="header-right">
            {wallet.connected ? (
              <div className="wallet-info">
                <span className={`wallet-badge ${wallet.wrongNetwork ? 'wrong-network' : 'connected'}`}>
                  {wallet.wrongNetwork ? t.wallet.wrongNetwork : t.wallet.connected}
                </span>
                <span className="wallet-address">{shortenAddress(wallet.address)}</span>
                <button className="wallet-btn disconnect" onClick={disconnectWallet} aria-label="Disconnect wallet">
                  ×
                </button>
              </div>
            ) : (
              <button className="wallet-btn connect" onClick={connectWallet} disabled={wallet.connecting}>
                {wallet.connecting ? t.wallet.connecting : t.wallet.connect}
              </button>
            )}
            
            <div className="lang-toggle">
              <button 
                className={`lang-btn ${lang === 'en' ? 'active' : ''}`}
                onClick={() => setLang('en')}
                aria-label="English"
              >
                EN
              </button>
              <button 
                className={`lang-btn ${lang === 'es' ? 'active' : ''}`}
                onClick={() => setLang('es')}
                aria-label="Español"
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

                  <form onSubmit={handleSubmit}>
                    <div className="form-grid">
                      <div className="form-group">
                        <label htmlFor="lat">{t.form.lat}</label>
                        <input type="text" id="lat" name="lat" placeholder="40.4123" required />
                      </div>
                      <div className="form-group">
                        <label htmlFor="lon">{t.form.lon}</label>
                        <input type="text" id="lon" name="lon" placeholder="-3.6912" required />
                      </div>
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
                        {statusType === 'success' && t.result.status}
                        {statusType === 'error' && t.result.error}
                      </span>
                    </div>

                    {result && (
                      <>
                        <div className="score-section">
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
                    <span className="info-val">DeepSeek-R1</span>
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
                    <span className="info-key">Update</span>
                    <span className="info-val">Real-time</span>
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