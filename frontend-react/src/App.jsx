import { useState, useEffect } from 'react'
import './index.css'

import Navbar from './components/Navbar'
import Footer from './components/Footer'
import HomeSection from './sections/HomeSection'
import HowItWorksSection from './sections/HowItWorksSection'
import VerifySection from './sections/VerifySection'
import AboutSection from './sections/AboutSection'

const translations = {
  en: {
    nav: { home: 'Home', howItWorks: 'How it works', verify: 'Verify', about: 'About us' },
    form: { title: 'Verify Vineyard', subtitle: 'Run a full audit for any tokenized vineyard asset', lat: 'Latitude', lon: 'Longitude', farm: 'Farm ID', asset: 'NFT contract (Rootstock)', token: 'Token ID', button: 'Run Verification', tabVerify: 'New Audit', tabCheck: 'Verify Certificate' },
    result: { status: 'CERTIFIED', score: 'VitisScore', loading: 'Verifying...', error: 'Verification Failed', existing: 'EXISTING CERTIFICATE', comparedRegion: 'Compared to region', percentile: 'NDVI Percentile', delta: 'Delta vs Avg' },
    stats: { satellites: 'Satellites', networks: 'Networks', audits: 'Audits' },
    hero: { title: 'VitisTrust', subtitle: 'Decentralized Oracle', description: 'We verify tokenized vineyards using satellite data and AI. Every audit is recorded immutably on Hedera (Trust Layer) and Rootstock (Asset Layer, Solidity).' },
    features: { title: 'Features', sat: { title: 'Satellite Data', desc: '10m resolution Sentinel-2 images. Objective NDVI analysis.' }, ai: { title: 'AI Analysis', desc: 'Llama 3.3 (Groq) generates VitisScore (0-100) with detailed justification.' }, chain: { title: 'Blockchains', desc: 'Hedera HCS (notarization) + Rootstock EVM (VitisRegistry).' }, invest: { title: 'Investment Analysis', desc: 'BUY/HOLD/SELL recommendations based on real data.' } },
    problem: { title: 'The Problem', text: 'In vineyard tokenization as NFTs, investors cannot verify if the underlying asset really exists and is healthy. There is no way to validate that the yielding vineyard exists or is in good condition.' },
    solution: { title: 'Our Solution', text: 'VitisTrust is a decentralized oracle that uses objective satellite data and AI to audit vineyards. Each certification is recorded immutably on Hedera and Rootstock (VitisRegistry), creating a verifiable history that no one can falsify.' },
    process: { title: 'How It Works', steps: [{ title: 'Enter Coordinates', desc: 'Provide vineyard coordinates (lat/lon) and farm ID.' }, { title: 'Satellite Analysis', desc: 'We query Sentinel-2 for NDVI images of the vineyard area.' }, { title: 'AI Processes Data', desc: 'Llama 3.3 (Groq) analyzes vegetation and generates VitisScore.' }, { title: 'Hedera Notarization', desc: 'Result is recorded on Hedera Consensus Service.' }, { title: 'Rootstock', desc: 'VitisScore certified on-chain via VitisRegistry (RSK).' }] },
    about: { title: 'About Us', mission: { title: 'Mission', desc: 'Bring verifiable transparency to the tokenized wine market.' }, vision: { title: 'Vision', desc: 'Be the verification standard for all Web3 agricultural assets.' }, values: { title: 'Values', desc: 'Transparency, decentralization, objective data, and tech innovation.' } },
    footer: { network: 'Hedera + Rootstock Testnet', rights: '© 2026 VitisTrust' },
    oracle: {
      title: 'Blockchain Proofs',
      subtitle: 'Immutable audit trail',
      hederaTopic: 'Hedera transaction',
      rskTx: 'Rootstock TX',
      viewExplorer: 'View explorer',
      close: 'Close',
      mockBadge: 'MOCK',
      mockNote: 'Rootstock is in stub mode — this hash is not on-chain.',
    },
  },
  es: {
    nav: { home: 'Home', howItWorks: 'Cómo funciona', verify: 'Verificar', about: 'Sobre nosotros' },
    form: { title: 'Verificar Viñedo', subtitle: 'Ejecuta una auditoría completa para cualquier activo tokenizado', lat: 'Latitud', lon: 'Longitud', farm: 'ID del Viñedo', asset: 'Contrato NFT (Rootstock)', token: 'ID de Token', button: 'Ejecutar Verificación', tabVerify: 'Nueva Auditoría', tabCheck: 'Verificar Certificado' },
    result: { status: 'CERTIFICADO', score: 'VitisScore', loading: 'Verificando...', error: 'Verificación Fallida', existing: 'CERTIFICADO EXISTENTE', comparedRegion: 'Comparado con la región', percentile: 'Percentil NDVI', delta: 'Delta vs Promedio' },
    stats: { satellites: 'Satélites', networks: 'Redes', audits: 'Auditorías' },
    hero: { title: 'VitisTrust', subtitle: 'Oráculo Descentralizado', description: 'Verificamos viñedos tokenizados usando datos satelitales e IA. Cada auditoría queda registrada de forma inmutable en Hedera (Trust Layer) y Rootstock (Asset Layer, Solidity).' },
    features: { title: 'Características', sat: { title: 'Datos Satelitales', desc: 'Imágenes Sentinel-2 de 10m. Análisis NDVI objetivo.' }, ai: { title: 'Análisis IA', desc: 'Llama 3.3 (Groq) genera VitisScore (0-100) con justificación.' }, chain: { title: 'Blockchains', desc: 'Hedera HCS (notarización) + Rootstock EVM (VitisRegistry).' }, invest: { title: 'Análisis de Inversión', desc: 'Recomendaciones BUY/HOLD/SELL basadas en datos reales.' } },
    problem: { title: 'El Problema', text: 'En la tokenización de viñedos como NFTs, el inversor no puede verificar si el activo subyacente existe y está sano.' },
    solution: { title: 'Nuestra Solución', text: 'VitisTrust es un oráculo descentralizado que usa datos satelitales objetivos y IA para auditar viñedos. Cada certificación queda registrada de forma inmutable en Hedera y en Rootstock (VitisRegistry).' },
    process: { title: 'Cómo Funciona', steps: [{ title: 'Ingresa Coordenadas', desc: 'Proporciona lat/lon del viñedo y un ID.' }, { title: 'Análisis Satelital', desc: 'Consultamos Sentinel-2 para obtener imágenes NDVI.' }, { title: 'IA Procesa Datos', desc: 'Llama 3.3 (Groq) analiza y genera VitisScore.' }, { title: 'Notarización Hedera', desc: 'Resultado registrado en Hedera HCS.' }, { title: 'Rootstock', desc: 'VitisScore certificado on-chain con VitisRegistry (RSK).' }] },
    about: { title: 'Sobre Nosotros', mission: { title: 'Misión', desc: 'Traer transparencia al mercado de vinos tokenizados.' }, vision: { title: 'Visión', desc: 'Ser el estándar de verificación para activos agrícolas en Web3.' }, values: { title: 'Valores', desc: 'Transparencia, descentralización, datos objetivos e innovación.' } },
    footer: { network: 'Hedera + Rootstock Testnet', rights: '© 2026 VitisTrust' },
    oracle: {
      title: 'Pruebas Blockchain',
      subtitle: 'Trazabilidad inmutable',
      hederaTopic: 'Transacción Hedera',
      rskTx: 'TX Rootstock',
      viewExplorer: 'Ver explorer',
      close: 'Cerrar',
      mockBadge: 'MOCK',
      mockNote: 'Rootstock está en modo stub — este hash no está on-chain.',
    },
  }
}

function App() {
  const [lang, setLang] = useState('en')
  const [activeSection, setActiveSection] = useState('home')

  const t = translations[lang]

  // Scroll a sección
  const scrollToSection = (sectionId) => {
    const element = document.getElementById(sectionId)
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' })
      setActiveSection(sectionId)
    }
  }

  // Scroll spy
  useEffect(() => {
    const handleScroll = () => {
      const sections = [
        { id: 'home', offset: 300 },
        { id: 'how-it-works', offset: 150 },
        { id: 'verify', offset: 150 },
        { id: 'about', offset: 150 }
      ]
      
      for (const section of sections) {
        const element = document.getElementById(section.id)
        if (element) {
          const rect = element.getBoundingClientRect()
          if (rect.top <= section.offset) {
            setActiveSection(section.id)
            break
          }
        }
      }
    }

    window.addEventListener('scroll', handleScroll, { passive: true })
    handleScroll()

    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  return (
    <div className="app-container">
      <div className="bg-pattern" />
      <div className="particles">
        {[...Array(8)].map((_, i) => <div key={i} className="particle"></div>)}
      </div>
      
      <div className="content">
        <Navbar 
          lang={lang} 
          setLang={setLang} 
          activeSection={activeSection} 
          scrollToSection={scrollToSection} 
        />

        <main>
          <HomeSection t={t} scrollTo={scrollToSection} />
          <HowItWorksSection t={t} scrollTo={scrollToSection} />
          <VerifySection t={t} />
          <AboutSection t={t} scrollTo={scrollToSection} />
        </main>

        <Footer t={t} />
      </div>
    </div>
  )
}

export default App
