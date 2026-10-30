#!/usr/bin/env python3
"""
AI-Powered Vendor Source & Regional Website Discovery Tool.

Leverages Gemini and intelligent domain heuristics to discover authentic global and
regional product lifecycle hubs, discontinued product catalogs, replacement matrices,
and XML sitemaps across industrial automation (OT), enterprise networking (IT), and IoT.

Usage:
    # Discover sources for a single vendor (preview mode)
    python scripts/discover_vendor_sources.py --vendor toyoda

    # Discover and apply verified sources directly to configs/vendors.yaml
    python scripts/discover_vendor_sources.py --vendor toyoda --apply

    # Discover sources across an entire sector
    python scripts/discover_vendor_sources.py --sector OT

    # Probe website sitemaps directly
    python scripts/discover_vendor_sources.py --vendor toyoda --probe-sitemaps
"""

import argparse
import json
import logging
import re
import shutil
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.ai_extractor import UniversalAIExtractor
from scraper.config import USER_AGENT


def strip_json_code_fences(text: str) -> str:
    """Strips markdown code fences (```json ... ```) from LLM responses."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("discover_vendor_sources")

CONFIGS_PATH = BASE_DIR / "configs" / "vendors.yaml"

DISCOVERY_PROMPT_TEMPLATE = """You are a world-class industrial automation, IoT, and IT hardware intelligence specialist.
For the manufacturer listed below, identify authentic, verified global and regional websites, discontinued product portals, and lifecycle matrices.

### Target Manufacturer:
- **Vendor Name**: {vendor_name}
- **Vendor ID**: {vendor_id}
- **Sector**: {sector}
- **Primary Website**: {website}
- **Currently Configured Entry Points**:
{current_entry_points}

### Instructions:
1. **Regional Subsidiaries & Specialized Portals**:
   - Check if this vendor operates specialized subsidiaries or regional websites (e.g., Japan `.co.jp`, Germany `.de`, European FA sites, Americas machinery/support divisions).
   - For example: JTEKT has JTEKT Electronics at `electronics.jtekt.co.jp` (formerly Koyo Electronics `koyoele.co.jp`) and JTEKT Machinery Americas at `jtektmachinery.com`.
   - Siemens operates `sieportal.siemens.com` and `support.industry.siemens.com`.
   - Mitsubishi Electric has regional FA sites `se-fa.mitsubishielectric.com`, `no-fa.mitsubishielectric.com`, and Japanese factory automation discontinued catalogs.
2. **Lifecycle, EOL, and Discontinued Catalogs**:
   - Locate the exact URLs where the vendor publishes discontinued products catalogs, replacement model cross-references, migration guides, and lifecycle notices.
3. **XML Sitemaps**:
   - Provide suspected XML sitemap locations (e.g. `/sitemap.xml`, `/sitemap_index.xml`, `/en/sitemap.xml`, `/jp/sitemap.xml`).

### Response Format:
Respond ONLY with a valid JSON object matching this exact schema:
```json
{{
  "vendor_id": "{vendor_id}",
  "official_domains": [
    "example.com",
    "electronics.example.co.jp"
  ],
  "candidate_portals": [
    {{
      "name": "Short descriptive name (e.g. JTEKT_Electronics_Discontinued_Catalog)",
      "url": "https://example.com/en/product/discon/",
      "region": "Global|Americas|Europe|Japan|APAC",
      "crawler_type": "dom_table|nextjs_apollo|pdf",
      "rationale": "High-yield discontinued PLC/HMI catalog with HTML tables"
    }}
  ],
  "sitemap_candidates": [
    "https://example.com/sitemap.xml"
  ]
}}
```
"""


class VendorSourceDiscoverer:
    """
    Automated source discovery and verification engine for vendor lifecycle portals.
    Combines LLM-driven subsidiary research with live HTTP probing and XML sitemap parsing.
    """

    def __init__(self, extractor: Optional[UniversalAIExtractor] = None):
        self.extractor = extractor or UniversalAIExtractor()
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        self.session = requests.Session()
        retries = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504], raise_on_status=False)
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self.session.mount("http://", HTTPAdapter(max_retries=retries))
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ja;q=0.8,de;q=0.7",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
        })

    def probe_url(self, url: str) -> Dict[str, Any]:
        """
        Probes candidate URL via HTTP GET to verify availability, status, and lifecycle content signals.
        """
        result: Dict[str, Any] = {
            "url": url,
            "is_valid": False,
            "status_code": 0,
            "final_url": url,
            "has_tables": False,
            "has_lifecycle_keywords": False,
            "content_length": 0,
            "error": None,
        }
        try:
            resp = self.session.get(url, timeout=12, allow_redirects=True)
            result["status_code"] = resp.status_code
            result["final_url"] = resp.url

            if resp.status_code < 400:
                html = resp.text
                result["content_length"] = len(html)
                result["is_valid"] = len(html.strip()) > 100

                # Check table markers
                result["has_tables"] = "<table" in html.lower() or "__APOLLO_STATE__" in html

                # Check lifecycle keywords
                lifecycle_pat = re.compile(
                    r'(?:lifecycle|life[-_\s]?cycle|eol|ltb|eos|eosl|ldos|eoa|'
                    r'end[-_\s]?of[-_\s]?(?:life|sale|sales|support|service|availability)|'
                    r'discontinu|obsolesc|phase[-_\s]?out|phaseout|last[-_\s]?time[-_\s]?buy|final[-_\s]?order|last[-_\s]?order|'
                    r'classic|limited|bulletin|support|abk[uü]ndigung|auslauf|生産終了|製造中止|販売終了|保守終了|修理対応)',
                    re.IGNORECASE
                )
                result["has_lifecycle_keywords"] = bool(lifecycle_pat.search(html))
        except Exception as e:
            result["error"] = str(e)

        return result

    def probe_sitemap(self, sitemap_url: str) -> List[str]:
        """
        Probes and parses an XML sitemap for high-value lifecycle and discontinued product URLs.
        """
        discovered_urls: List[str] = []
        try:
            resp = self.session.get(sitemap_url, timeout=8)
            if resp.status_code == 200:
                raw_xml = resp.content
                import gzip
                if resp.headers.get("Content-Encoding") == "gzip" or sitemap_url.endswith(".gz"):
                    try:
                        raw_xml = gzip.decompress(raw_xml)
                    except Exception:
                        pass

                import xml.etree.ElementTree as ET
                root = ET.fromstring(raw_xml)

                lifecycle_kw = re.compile(
                    r'(?:lifecycle|life[-_\s]?cycle|eol|ltb|eos|eosl|ldos|eoa|'
                    r'end[-_\s]?of[-_\s]?(?:life|sale|sales|support|service|availability)|'
                    r'discontinu|obsolesc|phase[-_\s]?out|phaseout|last[-_\s]?time[-_\s]?buy|final[-_\s]?order|'
                    r'classic|limited|bulletin|product|catalog|support|archive|'
                    r'abk[uü]ndigung|auslauf|生産終了|製造中止|販売終了|保守終了|修理対応)',
                    re.IGNORECASE
                )
                for url_node in root.findall(".//{*}url"):
                    loc = url_node.find("{*}loc")
                    if loc is not None and loc.text:
                        u = loc.text.strip().split("#")[0]
                        if lifecycle_kw.search(u):
                            discovered_urls.append(u)
                            if len(discovered_urls) >= 15:
                                break
        except Exception as e:
            logger.debug(f"Sitemap probe error on {sitemap_url}: {e}")

        return discovered_urls

    def discover_via_gemini(self, vendor_cfg: Dict[str, Any]) -> Dict[str, Any]:
        """
        Queries Gemini to discover authentic subsidiaries, regional portals, and lifecycle catalogs.
        """
        vendor_name = vendor_cfg.get("name", "")
        vendor_id = vendor_cfg.get("id", "")
        sector = vendor_cfg.get("sector", "")
        website = vendor_cfg.get("website", "")
        entry_points = vendor_cfg.get("entry_points", [])

        ep_lines = []
        for ep in entry_points:
            ep_lines.append(f"  - {ep.get('name')}: {ep.get('url')} ({ep.get('region', 'Global')})")
        ep_summary = "\n".join(ep_lines) if ep_lines else "  - None configured"

        prompt = DISCOVERY_PROMPT_TEMPLATE.format(
            vendor_name=vendor_name,
            vendor_id=vendor_id,
            sector=sector,
            website=website,
            current_entry_points=ep_summary
        )

        if not self.extractor.is_configured():
            logger.info("AI Provider not configured with API key. Falling back to heuristic domain synthesis.")
            return self.discover_via_heuristics(vendor_cfg)

        try:
            logger.info(f"Querying AI provider ({getattr(self.extractor, 'provider', 'gemini')}) for {vendor_name} sources...")
            # Use raw model generation
            resp_text = ""
            if hasattr(self.extractor, "client") and getattr(self.extractor, "client", None):
                response = self.extractor.client.models.generate_content(
                    model=getattr(self.extractor, "model_name", "gemini-2.5-flash"),
                    contents=prompt
                )
                resp_text = getattr(response, "text", "") or ""

            cleaned = strip_json_code_fences(resp_text)
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.warning(f"AI discovery failed for {vendor_name}: {e}. Falling back to heuristics.")

        return self.discover_via_heuristics(vendor_cfg)

    def discover_via_heuristics(self, vendor_cfg: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deterministic fallback synthesizing standard regional subdomains and paths.
        """
        vendor_id = vendor_cfg.get("id", "")
        website = vendor_cfg.get("website", "")
        parsed = urllib.parse.urlsplit(website)
        domain = parsed.netloc.replace("www.", "")

        candidates = []
        official_domains = [domain]

        # Standard lifecycle paths
        standard_paths = [
            ("/support/lifecycle", "Support_Lifecycle_Portal", "Global"),
            ("/en/support/discontinued/", "Discontinued_Products_Support", "Global"),
            ("/support/eol", "EOL_Product_Notices", "Global"),
            ("/en/product/discon/", "Discontinued_Catalog", "Global"),
            ("/jp/product/discon/", "Japan_Discontinued_Catalog", "Japan"),
            ("/de/support/auslauftypen", "German_Phaseout_Catalog", "Europe"),
        ]

        for path, name, reg in standard_paths:
            candidates.append({
                "name": f"{vendor_id.title()}_{name}",
                "url": f"https://www.{domain}{path}",
                "region": reg,
                "crawler_type": "dom_table",
                "rationale": "Standard corporate lifecycle pattern"
            })

        sitemaps = [
            f"https://www.{domain}/sitemap.xml",
            f"https://www.{domain}/robots.txt"
        ]

        return {
            "vendor_id": vendor_id,
            "official_domains": official_domains,
            "candidate_portals": candidates,
            "sitemap_candidates": sitemaps
        }

    def run_discovery_for_vendor(self, vendor_cfg: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes end-to-end discovery: AI research -> HTTP probe verification -> sitemap mapping.
        """
        vendor_id = vendor_cfg.get("id", "")
        vendor_name = vendor_cfg.get("name", vendor_id)
        print(f"\n[*] Initiating Source & Regional Discovery for: {vendor_name} ({vendor_id})")

        ai_results = self.discover_via_gemini(vendor_cfg)

        raw_candidates = ai_results.get("candidate_portals", [])
        verified_portals: List[Dict[str, Any]] = []
        new_domains: Set[str] = set(ai_results.get("official_domains", []))

        existing_urls = {ep.get("url") for ep in vendor_cfg.get("entry_points", [])}

        print(f"  -> Generated {len(raw_candidates)} candidate portals. Probing live servers...")
        for cand in raw_candidates:
            u = cand.get("url", "")
            if not u:
                continue

            probe = self.probe_url(u)
            if probe["is_valid"]:
                final_u = probe["final_url"]
                p_domain = urllib.parse.urlsplit(final_u).netloc.replace("www.", "")
                new_domains.add(p_domain)

                cand["url"] = final_u
                cand["status_code"] = probe["status_code"]
                cand["has_tables"] = probe["has_tables"]
                cand["has_lifecycle_keywords"] = probe["has_lifecycle_keywords"]
                cand["is_new"] = final_u not in existing_urls

                verified_portals.append(cand)
                marker = "[NEW]" if cand["is_new"] else "[EXISTING]"
                print(f"     [+] {marker} HTTP {probe['status_code']}: {final_u} (Tables: {probe['has_tables']}, Keywords: {probe['has_lifecycle_keywords']})")
            else:
                err_str = f"HTTP {probe['status_code']}" if probe['status_code'] else f"Error: {probe['error']}"
                print(f"     [-] Unreachable ({err_str}): {u}")

        # Probe sitemaps
        sitemap_urls = ai_results.get("sitemap_candidates", [])
        discovered_sitemap_links: List[str] = []
        for sm in sitemap_urls:
            links = self.probe_sitemap(sm)
            if links:
                print(f"     [+] Sitemap {sm} yielded {len(links)} relevant catalog links.")
                discovered_sitemap_links.extend(links)

        return {
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "verified_portals": verified_portals,
            "new_domains": list(new_domains),
            "sitemap_links": discovered_sitemap_links
        }


def apply_discovery_to_config(discovery_results: List[Dict[str, Any]], config_path: Path = CONFIGS_PATH) -> int:
    """
    Applies newly discovered portals and domains to configs/vendors.yaml safely with backup.
    """
    if not config_path.exists():
        logger.error(f"Config path {config_path} does not exist.")
        return 0

    backup_path = config_path.with_suffix(".yaml.bak")
    shutil.copy2(config_path, backup_path)
    logger.info(f"Created config backup at {backup_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    vendors = data.get("vendors", {})
    total_added = 0

    for res in discovery_results:
        vid = res.get("vendor_id")
        if vid not in vendors:
            continue

        v_cfg = vendors[vid]
        current_entry_points = v_cfg.setdefault("entry_points", [])
        current_urls = {ep.get("url") for ep in current_entry_points}
        current_allowed = set(v_cfg.setdefault("allowed_domains", []))

        # Update allowed domains
        for d in res.get("new_domains", []):
            if d and d not in current_allowed:
                v_cfg["allowed_domains"].append(d)
                current_allowed.add(d)

        # Add new verified portals
        for p in res.get("verified_portals", []):
            p_url = p.get("url")
            if p_url and p_url not in current_urls:
                current_entry_points.append({
                    "name": p.get("name", "Discovered_Lifecycle_Portal"),
                    "url": p_url,
                    "region": p.get("region", "Global"),
                    "crawler_type": p.get("crawler_type", "dom_table"),
                })
                current_urls.add(p_url)
                total_added += 1

    # Preserve format and write back
    with open(config_path, "w", encoding="utf-8", newline="\r\n") as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True)

    print(f"\n[SUCCESS] Applied discovery results to {config_path} (+{total_added} new verified entry points added).")
    return total_added


def main():
    parser = argparse.ArgumentParser(description="AI Vendor Source & Regional Website Discovery Tool")
    parser.add_argument("--vendor", default=None, help="Target vendor ID (e.g. toyoda, siemens, mitsubishi)")
    parser.add_argument("--sector", default=None, choices=["OT", "IoT", "IT"], help="Filter by sector")
    parser.add_argument("--all", action="store_true", help="Run discovery across all configured vendors")
    parser.add_argument("--apply", action="store_true", help="Automatically update configs/vendors.yaml with verified portals")
    parser.add_argument("--probe-sitemaps", action="store_true", help="Deep probe XML sitemaps for links")
    args = parser.parse_args()

    with open(CONFIGS_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    vendors = config.get("vendors", {})
    targets = []

    if args.vendor:
        target_vid = args.vendor.lower()
        if target_vid in vendors:
            targets.append(vendors[target_vid])
        else:
            print(f"[!] Vendor '{args.vendor}' not found in configs/vendors.yaml.")
            return
    elif args.sector:
        targets = [v for v in vendors.values() if str(v.get("sector")).lower() == args.sector.lower()]
    elif args.all:
        targets = list(vendors.values())
    else:
        # Default to toyoda as the reference vendor requested by user
        targets = [vendors.get("toyoda")] if "toyoda" in vendors else list(vendors.values())[:1]

    discoverer = VendorSourceDiscoverer()
    all_results = []

    for v_cfg in targets:
        if not v_cfg:
            continue
        res = discoverer.run_discovery_for_vendor(v_cfg)
        all_results.append(res)

    if args.apply:
        apply_discovery_to_config(all_results)
    else:
        print("\n[*] Dry-run complete. Run with --apply to write verified portals to configs/vendors.yaml.")


if __name__ == "__main__":
    main()
