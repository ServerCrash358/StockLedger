import { useState } from 'react'

export default function TransactionLog({ reservations }) {
  const [filterSku, setFilterSku] = useState('')
  const [filterState, setFilterState] = useState('')

  const filtered = reservations.filter((r) => {
    if (filterSku && !r.sku.includes(filterSku)) return false
    if (filterState && r.state !== filterState) return false
    return true
  })

  const states = [...new Set(reservations.map((r) => r.state))]

  return (
    <div>
      <div className="inline-form">
        <input placeholder="filter by SKU" value={filterSku} onChange={(e) => setFilterSku(e.target.value)} />
        <select value={filterState} onChange={(e) => setFilterState(e.target.value)}>
          <option value="">all states</option>
          {states.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <span className="muted">{filtered.length} of {reservations.length}</span>
      </div>

      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>SKU</th>
            <th>Qty</th>
            <th>Customer</th>
            <th>Amount</th>
            <th>State</th>
            <th>Failure reason</th>
          </tr>
        </thead>
        <tbody>
          {filtered.slice(0, 100).map((r) => (
            <tr key={r.id}>
              <td className="mono">{r.id.slice(0, 8)}</td>
              <td>{r.sku}</td>
              <td>{r.qty}</td>
              <td className="mono">{r.customer_id.slice(0, 12)}</td>
              <td>${(r.amount_cents / 100).toFixed(2)}</td>
              <td><span className={`pill pill-${r.state.toLowerCase()}`}>{r.state}</span></td>
              <td>{r.failure_reason || ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
