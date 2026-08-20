import { useState } from 'react'
import { api } from '../api'

export default function NewSkuForm({ onCreated }) {
  const [sku, setSku] = useState('')
  const [total, setTotal] = useState(100)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function submit(e) {
    e.preventDefault()
    if (!sku.trim()) return
    setBusy(true)
    setErr(null)
    try {
      await api.createStock(sku.trim(), Number(total))
      setSku('')
      onCreated()
    } catch (e2) {
      setErr(e2.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={submit}>
      <input placeholder="SKU name" value={sku} onChange={(e) => setSku(e.target.value)} />
      <input
        type="number"
        min="1"
        value={total}
        onChange={(e) => setTotal(e.target.value)}
        style={{ width: '6rem' }}
      />
      <button type="submit" disabled={busy}>Add SKU</button>
      {err && <span className="inline-error">{err}</span>}
    </form>
  )
}
