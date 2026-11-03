#!/usr/bin/env python3
"""
Enterprise Runtime Endpoint Health, Audit, and Enrichment Tool.

Inspects live vendor endpoints configured in `configs/vendors.yaml`:
1. Audits reachability, HTTP status, canonical redirects, and SSL validity.
2. Detects Bot Management & WAF challenges (AWS WAF 202 challenge, Cloudflare, Imperva, Akamai).
3. Automatically probes for XML sitemaps, sitemap indexes, crisp sitemaps, and robots.txt.
4. Categorizes child sitemaps into product/PDP sitemaps and EOL/discontinued lifecycle sitemaps.
5. Infers product regex extraction patterns from live sample URLs.
6. Generates JSON and Markdown audit reports (`output/endpoint_audit_report.json` and `.md`).
7. Auto-enriches and auto-fixes broken or sub-optimal endpoints in `configs/vendors.yaml` via `--auto-fix`.

Usage:
    # Audit a single vendor
    python scripts/audit_and_enrich_endpoints.py --vendor yokogawa

    # Audit and auto-fix/enrich a single vendor's entry points in configs/vendors.yaml
    python scripts/audit_and_enrich_endpoints.py --vendor emerson --auto-fix

    # Audit an entire sector
    python scripts/audit_and_enrich_endpoints.py --sector OT

    # Audit all vendors and save full report
    python scripts/audit_and_enrich_endpoints.py --all
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.config import USER_AGENT  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("audit_enrich")

VENDORS_YAML_PATH = BASE_DIR / "configs" / "vendors.yaml"

COMMON_EOL_PATHS = [
    "/discontinued/",
    "/solutions/discontinued/",
    "/support/lifecycle/",
    "/products/discontinued/",
    "/obsolete-products/",
    "/eos-eol-notice",
    "/eos-eol-listing",
    "/end-of-life",
    "/discontinued-products",
    "/products/end-of-life",
]

COMMON_SITEMAP_CANDIDATES = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/crisp_sitemap_index.xml",
    "/en/sitemap.xml",
    "/en-us/sitemap.xml",
]


class EndpointAuditor:
    """Audits HTTP endpoints, detects WAF barriers, and discovers authentic lifecycle entry points."""

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504], raise_on_status=False)
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self.session.mount("http://", HTTPAdapter(max_retries=retries))
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def probe_http(self, url: str) -> Dict[str, Any]:
        """Probes a URL and captures status, redirects, headers, and WAF challenge signatures."""
        res: Dict[str, Any] = {
            "url": url,
            "status_code": 0,
            "final_url": url,
            "is_redirect": False,
            "redirect_hops": [],
            "waf_challenge": None,
            "is_success": False,
            "content_type": "",
            "has_table": False,
            "error": None,
        }
        if not url or not url.startswith(("http://", "https://")):
            res["error"] = "Invalid URL schema"
            return res

        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            res["status_code"] = resp.status_code
            res["final_url"] = str(resp.url)
            res["is_redirect"] = str(resp.url) != url
            res["content_type"] = resp.headers.get("Content-Type", "")

            if resp.history:
                res["redirect_hops"] = [str(r.url) for r in resp.history]

            waf_action = resp.headers.get("x-amzn-waf-action", "")
            cf_ray = resp.headers.get("cf-ray", "")
            server_hdr = resp.headers.get("server", "").lower()

            text_preview = resp.text[:15000].lower() if resp.text else ""

            if resp.status_code == 202 or "challenge" in waf_action.lower():
                res["waf_challenge"] = "AWS_WAF_CHALLENGE"
            elif resp.status_code in (403, 503) and cf_ray:
                res["waf_challenge"] = "CLOUDFLARE_CHALLENGE"
            elif "imperva" in server_hdr or "incapsula" in server_hdr:
                res["waf_challenge"] = "IMPERVA_CHALLENGE"
            elif resp.status_code == 403 and (
                "akamai" in server_hdr
                or "edgesuite.net" in (resp.text or "")
                or "ak_p" in resp.headers.get("server-timing", "")
                or "x-akamai-transformed" in resp.headers
                or "reference #" in text_preview
            ):
                res["waf_challenge"] = "AKAMAI_CHALLENGE"

            res["has_table"] = "<table" in text_preview
            res["is_success"] = 200 <= resp.status_code < 400

        except requests.exceptions.SSLError as e:
            res["error"] = f"SSL_ERROR: {e}"
        except requests.exceptions.Timeout:
            res["error"] = "TIMEOUT"
        except requests.exceptions.ConnectionError as e:
            res["error"] = f"CONNECTION_ERROR: {e}"
        except Exception as e:
            res["error"] = f"REQUEST_ERROR: {e}"

        return res

    def discover_sitemaps(self, base_url: str) -> List[str]:
        """Discovers active XML sitemaps via robots.txt and standard candidate paths."""
        discovered: List[str] = []
        parsed = urlparse(base_url)
        domain_root = f"{parsed.scheme}://{parsed.netloc}"

        # 1. Check robots.txt
        robots_url = f"{domain_root}/robots.txt"
        try:
            r = self.session.get(robots_url, timeout=self.timeout)
            if r.status_code == 200:
                for line in r.text.splitlines():
                    if line.strip().lower().startswith("sitemap:"):
                        s_url = line.split(":", 1)[1].strip()
                        if s_url.startswith(("http://", "https://")) and s_url not in discovered:
                            discovered.append(s_url)
        except Exception:
            pass

        # 2. Check candidate sitemap locations
        for cand in COMMON_SITEMAP_CANDIDATES:
            full_cand = f"{domain_root}{cand}"
            if full_cand in discovered:
                continue
            try:
                head_resp = self.session.head(full_cand, timeout=self.timeout, allow_redirects=True)
                if head_resp.status_code == 200:
                    discovered.append(full_cand)
            except Exception:
                pass

        return discovered

    def inspect_sitemap_index(self, sitemap_url: str) -> Dict[str, Any]:
        """Inspects an XML sitemap to detect child sitemaps, product catalogs, and EOL notices."""
        result: Dict[str, Any] = {
            "sitemap_url": sitemap_url,
            "is_index": False,
            "child_count": 0,
            "product_sitemaps": [],
            "eol_sitemaps": [],
            "sample_urls": [],
            "suggested_child_filter": None,
            "suggested_pattern": None,
        }

        try:
            resp = self.session.get(sitemap_url, timeout=self.timeout)
            if resp.status_code != 200 or not resp.text:
                return result

            # Clean namespaces for easy tag parsing
            xml_text = re.sub(r' xmlns="[^"]+"', "", resp.text, count=1)
            root = ET.fromstring(xml_text.encode("utf-8", errors="replace"))

            if root.tag.endswith("sitemapindex"):
                result["is_index"] = True
                children: List[str] = []
                for s_elem in root.findall(".//sitemap"):
                    loc = s_elem.find("loc")
                    if loc is not None and loc.text:
                        children.append(loc.text.strip())

                result["child_count"] = len(children)
                # Categorize children
                for c in children:
                    c_lower = c.lower()
                    if any(k in c_lower for k in ("product", "pdp", "catalog", "item", "part")):
                        result["product_sitemaps"].append(c)
                    if any(k in c_lower for k in ("discontinued", "eol", "lifecycle", "obsolete", "phaseout", "eos")):
                        result["eol_sitemaps"].append(c)

                # Identify child filter heuristic
                if result["product_sitemaps"]:
                    sample_child = result["product_sitemaps"][0]
                    # Derive distinguishing filename token
                    child_name = Path(urlparse(sample_child).path).name
                    token = child_name.split(".")[0].split("-")[0]
                    result["suggested_child_filter"] = token if token else child_name

                    # Probe first product child sitemap for sample PDP URLs
                    self._sample_child_urls(sample_child, result)

            elif root.tag.endswith("urlset"):
                result["is_index"] = False
                urls: List[str] = []
                for u_elem in root.findall(".//url"):
                    loc = u_elem.find("loc")
                    if loc is not None and loc.text:
                        urls.append(loc.text.strip())
                result["sample_urls"] = urls[:10]
                result["suggested_pattern"] = self._infer_url_regex_pattern(urls[:25])

        except Exception as e:
            logger.debug(f"Error inspecting sitemap {sitemap_url}: {e}")

        return result

    def _sample_child_urls(self, child_sitemap_url: str, result: Dict[str, Any]) -> None:
        """Fetches a child sitemap to extract sample product URLs and infer regex."""
        try:
            c_resp = self.session.get(child_sitemap_url, timeout=self.timeout)
            if c_resp.status_code == 200 and c_resp.text:
                cleaned = re.sub(r' xmlns="[^"]+"', "", c_resp.text, count=1)
                c_root = ET.fromstring(cleaned.encode("utf-8", errors="replace"))
                urls: List[str] = []
                for u_elem in c_root.findall(".//url"):
                    loc = u_elem.find("loc")
                    if loc is not None and loc.text:
                        urls.append(loc.text.strip())
                result["sample_urls"] = urls[:10]
                result["suggested_pattern"] = self._infer_url_regex_pattern(urls[:30])
        except Exception:
            pass

    def _infer_url_regex_pattern(self, sample_urls: List[str]) -> Optional[str]:
        """Infers product model URL regex pattern from sample URLs."""
        if not sample_urls:
            return None
        # Look for common product path segments
        common_prefixes = ["/products/", "/product/", "/p/", "/item/", "/goods/", "/catalog/"]
        for pfx in common_prefixes:
            matches = [u for u in sample_urls if pfx in u]
            if len(matches) >= max(2, len(sample_urls) // 3):
                # Check extension
                if any(u.endswith(".html") for u in matches):
                    return f"{pfx}([A-Za-z0-9\\-_.]+)\\.html"
                return f"{pfx}([A-Za-z0-9\\-_.]+)"
        return "/([A-Za-z0-9\\-_.]+)"

    def check_eol_subpaths(self, base_url: str) -> List[Dict[str, Any]]:
        """Checks well-known EOL and discontinued subpaths on the vendor's primary domain."""
        valid_eol_portals: List[Dict[str, Any]] = []
        parsed = urlparse(base_url)
        domain_root = f"{parsed.scheme}://{parsed.netloc}"

        for subpath in COMMON_EOL_PATHS:
            test_url = urljoin(domain_root, subpath)
            probe = self.probe_http(test_url)
            if probe.get("is_success") and (probe.get("has_table") or probe.get("status_code") == 200):
                valid_eol_portals.append({
                    "url": probe["final_url"],
                    "status_code": probe["status_code"],
                    "has_table": probe["has_table"],
                    "waf_challenge": probe["waf_challenge"],
                })

        return valid_eol_portals

    def audit_vendor(self, vendor_id: str, vendor_conf: Dict[str, Any]) -> Dict[str, Any]:
        """Comprehensive audit of an individual vendor's endpoints and potential enrichments."""
        entry_points = vendor_conf.get("entry_points", [])
        website = vendor_conf.get("website", "")
        sector = vendor_conf.get("sector", "")
        vendor_name = vendor_conf.get("name", vendor_id)

        audited_entry_points: List[Dict[str, Any]] = []
        needs_fix = False

        for ep in entry_points:
            url = ep.get("url", "")
            probe = self.probe_http(url)
            ep_audit = {
                "configured_url": url,
                "strategy": ep.get("strategy", "unknown"),
                "status_code": probe["status_code"],
                "final_url": probe["final_url"],
                "is_redirect": probe["is_redirect"],
                "is_success": probe["is_success"],
                "waf_challenge": probe["waf_challenge"],
                "error": probe["error"],
            }
            if not probe["is_success"] or probe["status_code"] in (404, 503):
                needs_fix = True
            audited_entry_points.append(ep_audit)

        # Sitemap auto-discovery
        sitemaps = self.discover_sitemaps(website or (entry_points[0].get("url") if entry_points else ""))
        sitemap_details: List[Dict[str, Any]] = []
        for sm in sitemaps[:3]:
            detail = self.inspect_sitemap_index(sm)
            sitemap_details.append(detail)

        # EOL subpaths check
        eol_candidates = self.check_eol_subpaths(website or (entry_points[0].get("url") if entry_points else ""))

        return {
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "sector": sector,
            "website": website,
            "needs_fix": needs_fix,
            "entry_points_audit": audited_entry_points,
            "discovered_sitemaps": sitemaps,
            "sitemap_details": sitemap_details,
            "eol_portals": eol_candidates,
            "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }


def enrich_and_apply_fixes(
    vendor_id: str,
    vendor_conf: Dict[str, Any],
    audit_data: Dict[str, Any],
    vendors_yaml_data: Dict[str, Any],
) -> bool:
    """Updates `configs/vendors.yaml` entry if broken endpoints or rich sitemaps are found."""
    modified = False
    v_data = vendors_yaml_data.get("vendors", {}).get(vendor_id)
    if not v_data:
        return False

    current_eps = v_data.get("entry_points", [])

    # 1. Update redirect URLs if canonical final_url is clean 200
    for i, ep in enumerate(current_eps):
        ep_audit = next((a for a in audit_data.get("entry_points_audit", []) if a.get("configured_url") == ep.get("url")), None)
        if ep_audit and ep_audit.get("is_redirect") and ep_audit.get("is_success"):
            new_url = ep_audit["final_url"]
            if new_url != ep["url"]:
                logger.info(f"[{vendor_id}] Canonical URL redirect fix: {ep['url']} -> {new_url}")
                current_eps[i]["url"] = new_url
                modified = True

    # 2. If broken (404/503), replace or augment with discovered valid sitemap
    broken_eps = [a for a in audit_data.get("entry_points_audit", []) if a.get("status_code") in (404, 503)]
    if broken_eps:
        # Check if sitemap discovery found a product sitemap
        for sm_info in audit_data.get("sitemap_details", []):
            if sm_info.get("product_sitemaps") or sm_info.get("suggested_pattern"):
                sm_url = sm_info["sitemap_url"]
                new_ep: Dict[str, Any] = {
                    "url": sm_url,
                    "strategy": "sitemap",
                }
                if sm_info.get("suggested_child_filter"):
                    new_ep["child_filter"] = sm_info["suggested_child_filter"]
                if sm_info.get("suggested_pattern"):
                    new_ep["pattern"] = sm_info["suggested_pattern"]

                # Append or replace broken entry
                logger.info(f"[{vendor_id}] Enriching broken endpoint with discovered sitemap: {sm_url}")
                current_eps.append(new_ep)
                modified = True
                break

    # 3. If valid EOL table portal discovered and not present, add it
    for eol in audit_data.get("eol_portals", []):
        if eol.get("has_table") and not any(ep.get("url") == eol["url"] for ep in current_eps):
            logger.info(f"[{vendor_id}] Enriching with newly discovered EOL table portal: {eol['url']}")
            current_eps.append({
                "url": eol["url"],
                "strategy": "dom_table",
            })
            modified = True

    if modified:
        v_data["entry_points"] = current_eps
        vendors_yaml_data["vendors"][vendor_id] = v_data

    return modified


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit, probe, and enrich vendor endpoints.")
    parser.add_argument("--vendor", help="Specific vendor ID to audit (e.g. yokogawa, emerson).")
    parser.add_argument("--sector", choices=["OT", "IT", "IoT"], help="Audit all vendors in a sector.")
    parser.add_argument("--all", action="store_true", help="Audit all vendors in configs/vendors.yaml.")
    parser.add_argument("--auto-fix", action="store_true", help="Automatically enrich and fix broken URLs in vendors.yaml.")
    parser.add_argument("--output-json", default="output/endpoint_audit_report.json", help="Path to save audit JSON.")
    parser.add_argument("--output-md", default="output/endpoint_audit_report.md", help="Path to save audit Markdown.")
    parser.add_argument("--timeout", type=float, default=8.0, help="HTTP request timeout in seconds.")

    args = parser.parse_args()

    if not VENDORS_YAML_PATH.exists():
        logger.error(f"Cannot find {VENDORS_YAML_PATH}")
        return 1

    with open(VENDORS_YAML_PATH, "r", encoding="utf-8") as f:
        conf_data = yaml.safe_load(f) or {}

    all_vendors = conf_data.get("vendors", {})
    target_vendors: Dict[str, Any] = {}

    if args.vendor:
        if args.vendor not in all_vendors:
            logger.error(f"Vendor '{args.vendor}' not found in configs/vendors.yaml.")
            return 1
        target_vendors[args.vendor] = all_vendors[args.vendor]
    elif args.sector:
        target_vendors = {k: v for k, v in all_vendors.items() if v.get("sector") == args.sector}
    elif args.all:
        target_vendors = all_vendors
    else:
        logger.info("No vendor/sector specified. Defaulting to first 5 vendors in vendors.yaml.")
        first_5_keys = list(all_vendors.keys())[:5]
        target_vendors = {k: all_vendors[k] for k in first_5_keys}

    logger.info(f"Auditing {len(target_vendors)} vendor(s)...")

    auditor = EndpointAuditor(timeout=args.timeout)
    results: Dict[str, Any] = {
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_audited": len(target_vendors),
        "vendors": {},
        "summary": {
            "healthy_count": 0,
            "broken_count": 0,
            "waf_challenged_count": 0,
            "enriched_fixed_count": 0,
        },
    }

    yaml_modified = False

    for vid, vconf in target_vendors.items():
        logger.info(f"Auditing vendor '{vid}' ({vconf.get('name')})...")
        v_res = auditor.audit_vendor(vid, vconf)
        results["vendors"][vid] = v_res

        has_broken = any(not ep["is_success"] for ep in v_res["entry_points_audit"])
        has_waf = any(bool(ep["waf_challenge"]) for ep in v_res["entry_points_audit"])

        if has_waf:
            results["summary"]["waf_challenged_count"] += 1
        if has_broken:
            results["summary"]["broken_count"] += 1
        else:
            results["summary"]["healthy_count"] += 1

        if args.auto_fix:
            was_fixed = enrich_and_apply_fixes(vid, vconf, v_res, conf_data)
            if was_fixed:
                results["summary"]["enriched_fixed_count"] += 1
                yaml_modified = True

    if yaml_modified:
        logger.info("Applying auto-fix updates to configs/vendors.yaml...")
        with open(VENDORS_YAML_PATH, "w", encoding="utf-8") as f:
            yaml.dump(conf_data, f, sort_keys=False, indent=2, allow_unicode=True)
        logger.info("Successfully updated configs/vendors.yaml.")

    # Save outputs
    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    out_md = Path(args.output_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(_render_markdown_report(results))

    logger.info(f"Audit completed. Report saved to {out_json} and {out_md}.")
    print(f"\nAudit Summary: Healthy={results['summary']['healthy_count']}, "
          f"Broken={results['summary']['broken_count']}, "
          f"WAF Challenges={results['summary']['waf_challenged_count']}, "
          f"Auto-Fixed={results['summary']['enriched_fixed_count']}")

    return 0


def _render_markdown_report(results: Dict[str, Any]) -> str:
    lines = [
        "# Vendor Endpoint Health & Enrichment Audit Report",
        "",
        f"> **Generated UTC:** `{results.get('audit_timestamp_utc')}`",
        "",
        "## Summary",
        "",
        f"- **Total Vendors Audited:** `{results.get('total_audited')}`",
        f"- **Healthy Vendors:** `{results['summary']['healthy_count']}`",
        f"- **Broken/Degraded Vendors:** `{results['summary']['broken_count']}`",
        f"- **WAF / Challenge Barriers:** `{results['summary']['waf_challenged_count']}`",
        f"- **Auto-Enriched / Fixed:** `{results['summary']['enriched_fixed_count']}`",
        "",
        "---",
        "",
        "## Detailed Vendor Audits",
        "",
        "| Vendor ID | Sector | Endpoints | Status | WAF Challenge | Discovered Sitemaps | EOL Portals |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for vid, vdata in results.get("vendors", {}).items():
        eps = vdata.get("entry_points_audit", [])
        status_badges = []
        waf_badges = []
        for ep in eps:
            code = ep.get("status_code", 0)
            status_badges.append(f"`{code}`")
            if ep.get("waf_challenge"):
                waf_badges.append(f"`{ep['waf_challenge']}`")

        status_str = " ".join(status_badges) if status_badges else "None"
        waf_str = " ".join(waf_badges) if waf_badges else "None"
        sms_count = len(vdata.get("discovered_sitemaps", []))
        eol_count = len(vdata.get("eol_portals", []))

        lines.append(
            f"| `{vid}` | {vdata.get('sector')} | {len(eps)} | {status_str} | {waf_str} | {sms_count} found | {eol_count} found |"
        )

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())

