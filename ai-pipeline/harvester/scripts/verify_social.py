#!/usr/bin/env python3
"""Verify social media pages belong to specific organizations.

Crawls VK/OK pages and uses LLM to confirm they are official pages
of the expected organization, not personal pages or unrelated groups.

Usage:
  cd ai-pipeline/harvester
  python -m scripts.verify_social -i data/social_verify_candidates.json \
    -o data/social_verified.json
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

_harvester_root = Path(__file__).resolve().parent.parent
if str(_harvester_root) not in sys.path:
    sys.path.insert(0, str(_harvester_root))

_env_file = _harvester_root / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)

import structlog
from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


def _get_deepseek_client():
    from processors.deepseek_client import DeepSeekClient
    return DeepSeekClient(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model_name,
    )


async def verify_social_pages(items: list[dict], output_path: str):
    from search.site_verifier import SiteVerifier

    deepseek = _get_deepseek_client()
    verifier = SiteVerifier(deepseek)

    results = []
    total_pages = sum(len(item.get("social_pages", [])) for item in items)
    page_idx = 0

    for i, item in enumerate(items, 1):
        org_title = item.get("org_title", "")
        source_id = item.get("source_id", "")
        pages = item.get("social_pages", [])

        print(f"\n[{i}/{len(items)}] {org_title[:55]}")

        verified_pages = []
        for page in pages:
            page_idx += 1
            url = page.get("url", "")
            # Normalize m.ok.ru → ok.ru
            url = url.replace("https://m.ok.ru/", "https://ok.ru/").replace("http://m.ok.ru/", "https://ok.ru/")

            print(f"  [{page_idx}/{total_pages}] Verifying {url[:60]}...")

            try:
                result = await verifier.verify(
                    candidate_url=url,
                    expected_org_title=org_title,
                    expected_inn="",
                )
                conf = result.confidence
                match = result.is_match
                v = result.verification
                org_found = v.org_name_found if v else ""
                reasoning = v.reasoning if v else ""

                icon = "+" if match and conf >= 0.6 else "-"
                print(f"    [{icon}] conf={conf} match={match} found='{org_found[:50]}'")

                verified_pages.append({
                    "url": url,
                    "confidence": conf,
                    "is_match": match,
                    "org_name_found": org_found,
                    "reasoning": reasoning,
                    "platform": "vk" if "vk.com" in url else "ok" if "ok.ru" in url else "other",
                })
            except Exception as exc:
                print(f"    [!] Error: {exc}")
                verified_pages.append({
                    "url": url,
                    "confidence": 0.0,
                    "is_match": False,
                    "error": str(exc),
                    "platform": "vk" if "vk.com" in url else "ok" if "ok.ru" in url else "other",
                })

        approved = [p for p in verified_pages if p.get("is_match") and p["confidence"] >= 0.6]

        results.append({
            "source_id": source_id,
            "org_title": org_title,
            "original_url": item.get("original_url", ""),
            "verified_pages": verified_pages,
            "approved_pages": approved,
            "has_approved": len(approved) > 0,
        })

        if output_path and i % 5 == 0:
            with open(output_path, "w") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

    if output_path:
        with open(output_path, "w") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    approved_orgs = sum(1 for r in results if r["has_approved"])
    approved_pages = sum(len(r["approved_pages"]) for r in results)
    print(f"\n{'='*60}")
    print(f"Total orgs: {len(results)}")
    print(f"Orgs with approved social: {approved_orgs}")
    print(f"Total approved pages: {approved_pages}")
    print(f"Saved: {output_path}")

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--output", "-o", default="data/social_verified.json")
    args = parser.parse_args()

    with open(args.input) as f:
        items = json.load(f)

    print(f"Loaded {len(items)} items from {args.input}")
    asyncio.run(verify_social_pages(items, args.output))


if __name__ == "__main__":
    main()
