const BASE = '/api'

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const err = new Error(body.detail || res.statusText)
    err.status = res.status
    err.body = body
    throw err
  }
  return res.json()
}

export const api = {
  listStock: () => req('/stock'),
  createStock: (sku, total) => req('/stock', { method: 'POST', body: JSON.stringify({ sku, total }) }),
  health: () => req('/health'),
  listReservations: () => req('/reservations'),
  listLedger: (sku) => req('/ledger/entries' + (sku ? `?sku=${encodeURIComponent(sku)}` : '')),
  chaosPurchase: (sku, amount_cents = 500) =>
    req('/chaos/purchase', { method: 'POST', body: JSON.stringify({ sku, amount_cents }) }),
}
