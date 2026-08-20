export default function HealthBadge({ health }) {
  if (!health) return <div className="badge badge-unknown">checking...</div>

  if (health.halted) {
    return <div className="badge badge-bad">HALTED — {health.halted_reason}</div>
  }
  if (!health.ledger_balanced || !health.stock_conserved) {
    return <div className="badge badge-warn">INVARIANT VIOLATION DETECTED</div>
  }
  return <div className="badge badge-good">invariants OK — ledger balanced, stock conserved</div>
}
