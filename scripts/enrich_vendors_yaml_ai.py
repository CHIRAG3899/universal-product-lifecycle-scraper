#!/usr/bin/env python3
"""
Enterprise Vendor Configuration AI Enrichment Script.
1. Re-integrates high-value missing entry points from v16 / v18 reference configs.
2. Eliminates all 'strategy: None' entry points by mapping to concrete strategies
   ('dom_table', 'sitemap', 'search_portal', 'rest_api').
3. Adds verified sitemaps and discovery endpoints for low-yield (<1000) and zero-data vendors.
4. Synchronizes allowed_domains across all configured entry points.
5. Strictly preserves vendor category (Hardware/Software/Hybrid) and sector (OT/IoT/IT/IoMT).
6. Preserves zero duplicate keys and zero duplicate names.
"""

import logging
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("enrich_vendors")

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "configs" / "vendors.yaml"
V16_PATH = BASE_DIR / "configs" / "vendors_lifecycle_enriched_v16.yaml"
V18_PATH = BASE_DIR / "configs" / "vendors_lifecycle_discovery_v18.yaml"


def determine_strategy(ep: dict) -> str:
    """Deterministically resolves the optimal scraping strategy for an entry point."""
    strat = str(ep.get("strategy") or "").strip().lower()
    c_type = str(ep.get("crawler_type") or "").strip().lower()
    rec_strat = str(ep.get("recommended_crawler_type") or "").strip().lower()
    url = str(ep.get("url") or "").strip().lower()

    if strat and strat not in ("none", "null", ""):
        return strat

    # 1. Sitemap strategy
    if (
        c_type in ("sitemap", "sitemap_auto", "sitemap_index", "sitemap_gzip_auto", "sitemap_probe")
        or rec_strat in ("sitemap", "sitemap_index", "sitemap_xml_or_index")
        or url.endswith((".xml", ".xml.gz"))
        or "sitemap" in url
    ):
        return "sitemap"

    # 2. Search portal strategy
    if (
        c_type in ("search_portal", "interactive_search")
        or rec_strat in ("search_portal", "interactive_search")
        or "product-lifecycle-status" in url
    ):
        return "search_portal"

    # 3. REST API strategy
    if c_type in ("rest_api", "json_api", "api") or "/api/" in url:
        return "rest_api"

    # 4. Default to universal dom_table
    return "dom_table"


# Additional verified catalog and sitemap endpoints for zero and low-yield vendors
VENDOR_CATALOG_EXPANSIONS = {
    "endress_hauser": [
        {
            "name": "Endress_Hauser_Sitemap",
            "url": "https://www.endress.com/sitemap.xml",
            "strategy": "sitemap",
            "crawler_type": "sitemap",
            "region": "Global"
        }
    ],
    "br_automation": [
        {
            "name": "BR_Automation_Sitemap",
            "url": "https://www.br-automation.com/sitemap.xml",
            "strategy": "sitemap",
            "crawler_type": "sitemap",
            "region": "Global"
        }
    ],
    "kuka": [
        {
            "name": "KUKA_Robots_Sitemap",
            "url": "https://www.kuka.com/sitemap.xml",
            "strategy": "sitemap",
            "crawler_type": "sitemap",
            "region": "Global"
        }
    ],
    "turck": [
        {
            "name": "Turck_Germany_Sitemap",
            "url": "https://www.turck.de/sitemap.xml",
            "strategy": "sitemap",
            "crawler_type": "sitemap",
            "region": "Global"
        }
    ],
    "festo": [
        {
            "name": "Festo_Global_Sitemap",
            "url": "https://www.festo.com/sitemap.xml",
            "strategy": "sitemap",
            "crawler_type": "sitemap",
            "region": "Global"
        }
    ],
    "sick": [
        {
            "name": "SICK_Global_Sitemap",
            "url": "https://www.sick.com/sitemap.xml",
            "strategy": "sitemap",
            "crawler_type": "sitemap",
            "region": "Global"
        }
    ],
    "pepperl_fuchs": [
        {
            "name": "Pepperl_Fuchs_Global_Sitemap",
            "url": "https://www.pepperl-fuchs.com/sitemap.xml",
            "strategy": "sitemap",
            "crawler_type": "sitemap",
            "region": "Global"
        }
    ],
    "pilz": [
        {
            "name": "Pilz_International_Sitemap",
            "url": "https://www.pilz.com/sitemap.xml",
            "strategy": "sitemap",
            "crawler_type": "sitemap",
            "region": "Global"
        }
    ],
    "dell": [
        {
            "name": "Dell_Support_All_EMC_Documents",
            "url": "https://www.dell.com/support/kbdoc/en-us/000185734/all-dell-emc-end-of-life-documents",
            "strategy": "dom_table",
            "crawler_type": "dom_table",
            "region": "Global"
        },
        {
            "name": "Dell_Product_Pages_Sitemap_GZ",
            "url": "https://www.dell.com/index-product-pages-hreflang-sitemap.xml.gz",
            "strategy": "sitemap",
            "crawler_type": "sitemap_gzip_auto",
            "region": "Global"
        }
    ],
    "fortinet": [
        {
            "name": "Fortinet_Product_Lifecycle_Portal",
            "url": "https://support.fortinet.com/Information/ProductLifeCycle.aspx",
            "strategy": "dom_table",
            "crawler_type": "dom_table",
            "region": "Global"
        },
        {
            "name": "Fortinet_FortiOS_Lifecycle_Portal",
            "url": "https://support.fortinet.com/Information/ProductLifeCycle.aspx?type=FortiOS",
            "strategy": "dom_table",
            "crawler_type": "dom_table",
            "region": "Global"
        }
    ],
    "hpe": [
        {
            "name": "HPE_FlexNetwork_EOS_Notices",
            "url": "https://support.hpe.com/hpesc/public/docDisplay?docId=c05278946",
            "strategy": "dom_table",
            "crawler_type": "dom_table",
            "region": "Global"
        },
        {
            "name": "HPE_3PAR_Nimble_Storage_EOSL",
            "url": "https://support.hpe.com/hpesc/public/docDisplay?docId=a00115011en_us",
            "strategy": "dom_table",
            "crawler_type": "dom_table",
            "region": "Global"
        }
    ],
    "ibm": [
        {
            "name": "IBM_Systems_Hardware_Lifecycle",
            "url": "https://www.ibm.com/support/pages/lifecycle/",
            "strategy": "dom_table",
            "crawler_type": "dom_table",
            "region": "Global"
        },
        {
            "name": "IBM_Storage_End_of_Service_Dates",
            "url": "https://www.ibm.com/support/pages/ibm-storage-end-service-dates",
            "strategy": "dom_table",
            "crawler_type": "dom_table",
            "region": "Global"
        }
    ],
    "arista": [
        {
            "name": "Arista_End_of_Sale_Lifecycle_Notices",
            "url": "https://www.arista.com/en/support/advisories-notices/end-of-sale-lifecycle",
            "strategy": "dom_table",
            "crawler_type": "dom_table",
            "region": "Global"
        },
        {
            "name": "Arista_Software_EOS_Notices",
            "url": "https://www.arista.com/en/support/advisories-notices/end-of-software-support",
            "strategy": "dom_table",
            "crawler_type": "dom_table",
            "region": "Global"
        }
    ],
    "intel": [
        {
            "name": "Intel_Discontinued_Processors_Database",
            "url": "https://www.intel.com/content/www/us/en/support/articles/000022396/processors.html",
            "strategy": "dom_table",
            "crawler_type": "dom_table",
            "region": "Global"
        },
        {
            "name": "Intel_Discontinued_Ethernet_Adapters",
            "url": "https://www.intel.com/content/www/us/en/support/articles/000005779/ethernet-products.html",
            "strategy": "dom_table",
            "crawler_type": "dom_table",
            "region": "Global"
        }
    ]
}


def main():
    logger.info("Loading configurations...")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        curr_cfg = yaml.safe_load(f)
    curr_vendors = curr_cfg.get("vendors", {})

    with open(V16_PATH, "r", encoding="utf-8") as f:
        v16_cfg = yaml.safe_load(f)
    v16_vendors = v16_cfg.get("vendors", {})

    with open(V18_PATH, "r", encoding="utf-8") as f:
        v18_cfg = yaml.safe_load(f)
    v18_vendors = v18_cfg.get("vendors", {})

    endpoints_added = 0
    strategies_normalized = 0
    domains_expanded = 0

    for v_id, v_info in curr_vendors.items():
        existing_eps = v_info.get("entry_points", [])
        seen_urls = {ep.get("url") for ep in existing_eps if ep.get("url")}
        seen_names = {ep.get("name") for ep in existing_eps if ep.get("name")}

        # 1. Re-integrate missing endpoints from v16 & v18
        source_eps = []
        if v_id in v16_vendors:
            source_eps.extend(v16_vendors[v_id].get("entry_points", []))
        if v_id in v18_vendors:
            source_eps.extend(v18_vendors[v_id].get("entry_points", []))

        for ep in source_eps:
            u = ep.get("url")
            n = ep.get("name")
            if u and u not in seen_urls:
                # Deduplicate name if needed
                clean_name = n
                counter = 1
                while clean_name in seen_names:
                    counter += 1
                    clean_name = f"{n}_{counter}"

                strat = determine_strategy(ep)
                new_ep = dict(ep)
                new_ep["name"] = clean_name
                new_ep["strategy"] = strat
                existing_eps.append(new_ep)
                seen_urls.add(u)
                seen_names.add(clean_name)
                endpoints_added += 1

        # 2. Add extra catalog expansions
        if v_id in VENDOR_CATALOG_EXPANSIONS:
            for extra_ep in VENDOR_CATALOG_EXPANSIONS[v_id]:
                u = extra_ep.get("url")
                n = extra_ep.get("name")
                if u and u not in seen_urls:
                    clean_name = n
                    counter = 1
                    while clean_name in seen_names:
                        counter += 1
                        clean_name = f"{n}_{counter}"

                    extra_dict = dict(extra_ep)
                    extra_dict["name"] = clean_name
                    existing_eps.append(extra_dict)
                    seen_urls.add(u)
                    seen_names.add(clean_name)
                    endpoints_added += 1

        # 3. Normalize all strategies across all entry points
        allowed_domains = set(v_info.get("allowed_domains", []))
        for ep in existing_eps:
            old_strat = ep.get("strategy")
            new_strat = determine_strategy(ep)
            if old_strat != new_strat:
                ep["strategy"] = new_strat
                strategies_normalized += 1

            # Extract domain and whitelist in allowed_domains
            u = ep.get("url")
            if u:
                try:
                    host = urlsplit(u).hostname
                    if host:
                        clean_host = host.lower()
                        # Add naked or second-level domain if appropriate
                        if clean_host not in allowed_domains:
                            allowed_domains.add(clean_host)
                            domains_expanded += 1
                except Exception:
                    pass

        v_info["allowed_domains"] = sorted(list(allowed_domains))
        v_info["entry_points"] = existing_eps

    # Verify zero duplicate vendor names
    names = Counter(v["name"] for v in curr_vendors.values())
    dups = {n: c for n, c in names.items() if c > 1}
    if dups:
        logger.error(f"Duplicate vendor names detected: {dups}")
        raise ValueError(f"Duplicate vendor names: {dups}")

    logger.info("Enrichment summary:")
    logger.info(f"  Total vendors: {len(curr_vendors)}")
    logger.info(f"  Missing endpoints added: {endpoints_added}")
    logger.info(f"  Strategies normalized to concrete types: {strategies_normalized}")
    logger.info(f"  Allowed domains expanded: {domains_expanded}")

    # Write out cleanly formatted YAML
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(curr_cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    logger.info(f"Successfully wrote enriched configuration to {CONFIG_PATH}")


if __name__ == "__main__":
    main()
