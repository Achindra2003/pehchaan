"""Throughput under concurrent load, in-process (no network): what one Pehchaan process sustains.

uv run python scripts/loadtest.py --requests 60 --concurrency 12
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

CONSENT = {"accepted": True, "notice_version": "loadtest", "accepted_at": "2026-09-17T00:00:00Z"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=60)
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    work = Path(tempfile.mkdtemp(prefix="pehchaan-load-"))
    key = sp.make_test_signing_key(work / "certs")
    rng = random.Random(42)
    people = [sp.make_person(rng) for _ in range(args.requests)]
    photos = [sp.photograph(sp.render_aadhaar(p, qr_payload=sp.secure_qr_for(p, key)), rng) for p in people]

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

        def one(i: int) -> tuple[int, float, str]:
            body = {
                "registration_id": f"load-{i}",
                "event_id": "ai-build-challenge-blr",
                "form": {"name": people[i].name, "dob": str(people[i].dob)},
                "consent": CONSENT,
            }
            started = time.perf_counter()
            response = client.post(
                "/v1/verifications",
                data={"payload": json.dumps(body)},
                files={"id_image": ("id.jpg", photos[i], "image/jpeg")},
                headers={"X-API-Key": "load"},
            )
            decision = response.json().get("decision", str(response.status_code))
            return response.status_code, (time.perf_counter() - started) * 1000, decision

        one(0)  # warm-up
        started = time.perf_counter()
        with ThreadPoolExecutor(args.concurrency) as pool:
            results = list(pool.map(one, range(1, args.requests)))
        # Requests answered 202 keep running; wait for the queue to drain so throughput counts finished work.
        while (status := client.get("/v1/status", headers={"X-API-Key": "load"}).json()["queue"])["waiting"] or status[
            "running"
        ]:
            time.sleep(0.2)
        elapsed = time.perf_counter() - started
        stats = client.get("/v1/stats", headers={"X-API-Key": "load"}).json()
        detail = client.get("/v1/verifications", params={"limit": 5}, headers={"X-API-Key": "load"}).json()
        sample = client.get(f"/v1/verifications/{detail[0]['verification_id']}", headers={"X-API-Key": "load"}).json()
        print("check durations (ms):", {c["check"]: c["duration_ms"] for c in sample["checks"]})
        print(
            f"completed={stats['total'] - 1} processing p50={stats['p50_latency_ms']}ms p95={stats['p95_latency_ms']}ms"
        )

    latencies = sorted(r[1] for r in results)
    decisions: dict[str, int] = {}
    for _, _, decision in results:
        decisions[decision] = decisions.get(decision, 0) + 1
    n = len(results)
    print(f"requests={n} concurrency={args.concurrency} workers={args.workers}")
    print(f"throughput={n / elapsed:.2f} completed verifications/s ({n / elapsed * 60:.0f}/min)")
    print(f"latency p50={statistics.median(latencies):.0f}ms p95={latencies[int(n * 0.95) - 1]:.0f}ms")
    print(f"decisions={decisions}")


if __name__ == "__main__":
    main()
