"""Live check of every configured connector. Usage: python scripts/smoke.py [keyword] [--save]"""

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from app.config import get_settings
from app.connectors.registry import make_all_connectors

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("keyword", nargs="?", default="nurse")
    parser.add_argument("--save", action="store_true", help="save first raw payload as fixture")
    args = parser.parse_args()

    failed = False
    for connector in make_all_connectors(get_settings()):
        if not connector.enabled():
            print(f"[skip] {connector.name}: not configured")
            continue
        try:
            raw = await connector.fetch([args.keyword])
        except Exception as exc:
            print(f"[FAIL] {connector.name}: {type(exc).__name__}: {exc}")
            failed = True
            continue
        batch = connector.normalize(raw, date.today())
        with_image = sum(1 for p in batch.products if p.image_url)
        status = "FAIL" if raw.errors and not raw.payloads else "ok"
        failed = failed or status == "FAIL"
        print(
            f"[{status}] {connector.name}: {len(raw.payloads)} payloads, {len(raw.errors)} errors, "
            f"{len(batch.products)} products ({with_image} with image), {len(batch.signals)} signals"
        )
        for error in raw.errors[:3]:
            print(f"    error: {error}")
        for p in batch.products[:5]:
            print(
                f"    - [{p.product_type}] {p.title[:70]} | {p.price} {p.currency} "
                f"| fav={p.favorites} rev={p.reviews} | shop={p.shop_name}"
            )
        if args.save and raw.payloads:
            out = FIXTURES / connector.name / "live_sample.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(raw.payloads[0], indent=2))
            print(f"    saved {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
