"""
Minimal load test harness for the AI Investment Analyst backend.
Runs concurrent requests against the production API and collects latency percentiles.

Usage:
    python scripts/load_test.py --base-url https://ai-investment-analyst.fly.dev --clients 10 --duration 1200
"""

import argparse
import asyncio
import time
import statistics

import httpx

TICKERS = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "AMZN", "META", "JPM"]


async def cached_request(client: httpx.AsyncClient, base_url: str, ticker: str) -> float:
    start = time.perf_counter()
    r = await client.get(f"{base_url}/api/analysis/{ticker}")
    elapsed = (time.perf_counter() - start) * 1000
    r.raise_for_status()
    return elapsed


async def sse_stream(client: httpx.AsyncClient, base_url: str, ticker: str) -> float:
    start = time.perf_counter()
    async with client.stream("POST", f"{base_url}/api/analyze", json={"query": f"analyze {ticker}"}) as r:
        async for _ in r.aiter_lines():
            pass
    return (time.perf_counter() - start) * 1000


async def worker(client: httpx.AsyncClient, base_url: str, results: list, stop: asyncio.Event):
    while not stop.is_set():
        ticker = TICKERS[len(results) % len(TICKERS)]
        try:
            elapsed = await cached_request(client, base_url, ticker)
            results.append(("cached", elapsed, None))
        except Exception as e:
            results.append(("cached", None, str(e)))
        await asyncio.sleep(0.1)


async def main(base_url: str, num_clients: int, duration_s: int):
    results: list = []
    stop = asyncio.Event()

    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
        tasks = [asyncio.create_task(worker(client, base_url, results, stop)) for _ in range(num_clients)]
        await asyncio.sleep(duration_s)
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)

    latencies = [r[1] for r in results if r[1] is not None]
    errors = [r for r in results if r[2] is not None]

    if latencies:
        latencies.sort()
        n = len(latencies)
        print(f"Requests: {len(results)} | Errors: {len(errors)} ({len(errors)/len(results)*100:.1f}%)")
        print(f"p50: {latencies[n//2]:.0f}ms | p95: {latencies[int(n*0.95)]:.0f}ms | p99: {latencies[int(n*0.99)]:.0f}ms")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load test harness")
    parser.add_argument("--base-url", default="https://ai-investment-analyst.fly.dev")
    parser.add_argument("--clients", type=int, default=5)
    parser.add_argument("--duration", type=int, default=60, help="seconds")
    args = parser.parse_args()
    asyncio.run(main(args.base_url, args.clients, args.duration))
