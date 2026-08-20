import { useEffect, useState, useCallback } from 'react'
import { api } from './api'
import StockTable from './components/StockTable.jsx'
import HealthBadge from './components/HealthBadge.jsx'
import TransactionLog from './components/TransactionLog.jsx'
import ChaosPanel from './components/ChaosPanel.jsx'
import NewSkuForm from './components/NewSkuForm.jsx'

export default function App() {
  const [stock, setStock] = useState([])
  const [health, setHealth] = useState(null)
  const [reservations, setReservations] = useState([])
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const [s, h, r] = await Promise.all([api.listStock(), api.health(), api.listReservations()])
      setStock(s)
      setHealth(h)
      setReservations(r)
      setError(null)
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 2000)
    return () => clearInterval(id)
  }, [refresh])

  return (
    <div className="app">
      <header>
        <h1>StockLedger</h1>
        <HealthBadge health={health} />
      </header>

      {error && <div className="banner banner-error">API error: {error}</div>}

      <div className="grid">
        <section className="card">
          <h2>Stock</h2>
          <NewSkuForm onCreated={refresh} />
          <StockTable stock={stock} />
        </section>

        <section className="card">
          <h2>Chaos test</h2>
          <ChaosPanel stock={stock} onDone={refresh} />
        </section>

        <section className="card card-wide">
          <h2>Transaction log</h2>
          <TransactionLog reservations={reservations} />
        </section>
      </div>
    </div>
  )
}
