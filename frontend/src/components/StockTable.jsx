export default function StockTable({ stock }) {
  if (stock.length === 0) return <p className="muted">No SKUs yet — create one below.</p>

  return (
    <table>
      <thead>
        <tr>
          <th>SKU</th>
          <th>Total</th>
          <th>Available</th>
          <th>Reserved</th>
          <th>Sold</th>
        </tr>
      </thead>
      <tbody>
        {stock.map((s) => (
          <tr key={s.sku}>
            <td>{s.sku}</td>
            <td>{s.total}</td>
            <td>{s.available}</td>
            <td>{s.reserved}</td>
            <td>{s.total - s.available - s.reserved}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
