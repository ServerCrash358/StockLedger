import { useState } from 'react'
import { api } from '../api'

export default function ChaosPanel({ stock, onDone }) {
  const [sku, setSku] = useState('')
  const [n, setN] = useState(50)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)

  const selected = sku || stock[0]?.sku || ''

  async function fire() {
    if (!selected) return
    setRunning(true)
    setResult(null)
    const startedAt = performance.now()

    const requests = Array.from({ length: Number(n) }, () => api.chaosPurchase(selected))
    const settled = await Promise.allSettled(requests)

    const successes = settled.filter((r) => r.status === 'fulfilled' && r.value.ok).length
    const rejected = settled.length - successes
    const elapsedMs = performance.now() - startedAt

    setResult({ successes, rejected, total: settled.length, elapsedMs })
    setRunning(false)
    onDone()
  }

  return (
    <div>
      <p className="muted">
        Fires N concurrent one-shot purchases (reserve + charge + commit) at a single SKU.
        With correct locking, successes never exceed available stock — no matter how high N goes.
      </p>
      <div className="inline-form">
        <select value={selected} onChange={(e) => setSku(e.target.value)}>
          {stock.map((s) => (
            <option key={s.sku} value={s.sku}>
              {s.sku} ({s.available} available)
            </option>
          ))}
        </select>
        <input type="number" min="1" value={n} onChange={(e) => setN(e.target.value)} style={{ width: '6rem' }} />
        <button onClick={fire} disabled={running || !selected} className="btn-danger">
          {running ? 'Firing...' : `Fire ${n} concurrent purchases`}
        </button>
      </div>

      {result && (
        <div className="result-box">
          <div>Requests: {result.total}</div>
          <div>Succeeded: {result.successes}</div>
          <div>Correctly rejected: {result.rejected}</div>
          <div>Elapsed: {result.elapsedMs.toFixed(0)}ms</div>
        </div>
      )}
    </div>
  )
}
