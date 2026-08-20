"""Definition-of-done demo: 1000 concurrent purchases against 100 units of one
SKU via the running HTTP API. Exactly 100 should succeed, ledger balances to
zero net stock created, invariant checker stays green.

Usage (with the API and invariant checker already running):
    python scripts/chaos_demo.py --base-url http://localhost:8000 --stock 100 --attempts 1000
"""
import argparse
import concurrent.futures
import time

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--stock", type=int, default=100)
    parser.add_argument("--attempts", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=50)
    args = parser.parse_args()

    sku = f"chaos-demo-{int(time.time())}"
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        r = client.post("/stock", json={"sku": sku, "total": args.stock})
        r.raise_for_status()
        print(f"Created SKU {sku} with {args.stock} units")

        def purchase(_):
            resp = client.post("/chaos/purchase", json={"sku": sku, "amount_cents": 500})
            return resp.json()

        start = time.time()
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            for res in pool.map(purchase, range(args.attempts)):
                results.append(res)
        elapsed = time.time() - start

        successes = sum(1 for r in results if r.get("ok"))
        failures = args.attempts - successes

        item = client.get(f"/stock/{sku}").json()
        health = client.get("/health").json()

        print(f"\n{args.attempts} attempts in {elapsed:.2f}s")
        print(f"Successes: {successes}  (expected {args.stock})")
        print(f"Failures (correctly rejected): {failures}")
        print(f"Final stock: {item}")
        print(f"Health: {health}")

        assert successes == args.stock, "OVERSELL DETECTED" if successes > args.stock else "undersold"
        assert item["available"] == 0
        assert item["reserved"] == 0
        assert health["ledger_balanced"] and health["stock_conserved"] and not health["halted"]
        print("\nPASS: no oversell, ledger balanced, invariant checker green.")


if __name__ == "__main__":
    main()
