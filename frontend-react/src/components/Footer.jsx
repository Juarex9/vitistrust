export default function Footer({ t }) {
  return (
    <footer>
      <div className="network-status">
        <div className="network-dot" />
        {t.footer.network}
      </div>
      <span className="copyright">{t.footer.rights}</span>
    </footer>
  )
}