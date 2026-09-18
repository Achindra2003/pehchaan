"""Throughput under concurrent load: what one process sustains, and what several sustain together.

    uv run python scripts/loadtest.py                                              # in-process
    uv run python scripts/loadtest.py --url http://localhost:8001 --key demo-key   # a running server

For the multi-process number, start the server with uvicorn's own workers and point --url at it:

    uvicorn pehchaan.main:app_factory --factory --port 8001 --workers 4
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from pehchaan import specimens as sp
from pehchaan.config import Settings
from pehchaan.main import create_app

CONSENT = {"accepted": True, "notice_version": "loadtest", "accepted_at": "2026-09-18T00:00:00Z"}
DEMO_CERTS = Path(__file__).resolve().parents[1] / "demo-samples" / "certs"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=60)
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--workers", type=int, default=2, help="in-process worker pool size")
    parser.add_argument("--url", help="measure a running server instead of an in-process app")
    parser.add_argument("--key", default="load", help="API key when using --url")
    args = parser.parse_args()

    work = Path(tempfile.mkdtemp(prefix="pehchaan-load-"))
    # Sign with the demo certificate when measuring a demo server, so its decisions are realistic.
    key = sp.make_test_signing_key(DEMO_CERTS if (args.url and DEMO_CERTS.exists()) else work / "certs")
    rng = random.Random(42)
    people = [sp.make_person(rng) for _ in range(args.requests)]
    photos = [sp.photograph(sp.render_aadhaar(p, qr_payload=sp.secure_qr_for(p, key)), rng) for p in people]

    if args.url:
        import httpx

        with httpx.Client(base_url=args.url, timeout=180) as client:
            measure(client, args, people, photos, args.key, label=args.url)
        return

    settings = Settings(
        env="test",
        api_keys="load",
        data_dir=work / "db",
        uidai_cert_path=work / "certs",
        ocr_provider="rapidocr",
        workers=args.workers,
        ocr_workers=args.workers,
        rate_limit_per_minute=100_000,
        web_dist=work / "none",
    )
    with TestClient(create_app(settings)) as client:
        measure(client, args, people, photos, "load", label=f"in-process, workers={args.workers}")


def measure(client, args, people, photos, api_key: str, label: str) -> None:
    headers = {"X-API-Key": api_key}

    def one(i: int) -> tuple[int, float, str]:
        body = {
            "registration_id": f"load-{time.time_ns()}-{i}",
            "event_id": "ai-build-challenge-blr",
            "form": {"name": people[i].name, "dob": str(people[i].dob)},
            "consent": CONSENT,
        }
        started = time.perf_counter()
        response = client.post(
            "/v1/verifications",
            data={"payload": json.dumps(body)},
            files={"id_image": ("id.jpg", photos[i], "image/jpeg")},
            headers=headers,
        )
        decision = response.json().get("decision", str(response.status_code)) if response.content else "empty"
        return response.status_code, (time.perf_counter() - started) * 1000, decision

    one(0)  # warm up models
    started = time.perf_counter()
    with ThreadPoolExecutor(args.concurrency) as pool:
        results = list(pool.map(one, range(1, args.requests)))
    _drain(client, headers)
    elapsed = time.perf_counter() - started

    latencies = sorted(r[1] for r in results)
    decisions: dict[str, int] = {}
    for _, _, decision in results:
        decisions[decision] = decisions.get(decision, 0) + 1
    n = len(results)
    print(f"\n{label}: {n} verifications, concurrency {args.concurrency}")
    print(f"  throughput  {n / elapsed:.2f}/s  ({n / elapsed * 60:.0f}/min)")
    print(f"  latency     p50 {statistics.median(latencies):.0f} ms   p95 {latencies[int(n * 0.95) - 1]:.0f} ms")
    print(f"  decisions   {decisions}\n")


def _drain(client, headers: dict[str, str]) -> None:
    """Requests answered 202 keep working in the background; wait so throughput counts finished work."""
    for _ in range(600):
        queue = client.get("/v1/status", headers=headers).json().get("queue", {})
        if not queue.get("waiting") and not queue.get("running"):
            return
        time.sleep(0.2)


if __name__ == "__main__":
    main()
