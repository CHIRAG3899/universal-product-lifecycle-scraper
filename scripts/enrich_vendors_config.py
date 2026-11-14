#!/usr/bin/env python3
"""
Vendor Configuration Categorization & IoMT Enrichment Script.

Applies User Directive 15:
1. Adds 'category' attribute to each vendor in configs/vendors.yaml:
   - 'Hardware': Physical devices, instruments, robotics, medical equipment, servers.
   - 'Software': Operating systems, SCADA platforms, enterprise security, cloud.
   - 'Hybrid': Vendors with both prominent hardware device lines and OS/platform software.
2. Refines 'sector' to explicitly designate 'IoMT' for medical device manufacturers.
3. Adds high-value hardware manufacturers in IoMT, OT, and IoT.
4. Preserves YAML structure and comments cleanly.
"""

import logging
import sys
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

IOMT_VENDORS = {
    "abbott", "baxter", "bbraun", "bd", "beckman_coulter", "canon_medical",
    "drager", "fresenius_medical_care", "fujifilm_healthcare", "ge_healthcare",
    "getinge", "heidelberg_engineering", "karl_storz", "masimo", "medtronic",
    "mindray", "nihon_kohden", "olympus", "philips", "resmed", "roche_diagnostics",
    "siemens_healthineers", "stryker", "wer_fen", "smiths_medical", "hillrom"
}

SOFTWARE_VENDORS = {
    "canonical", "citrix", "codesys", "commvault", "crowdstrike", "dragos",
    "genetec", "inductive_automation", "microsoft", "milestone_systems",
    "nozomi_networks", "okta", "oracle", "red_hat", "suse", "trend_micro",
    "veeam", "vmware", "zscaler", "aveva", "tridium", "ge_digital"
}

HYBRID_VENDORS = {
    "apple", "arista", "barracuda_networks", "check_point", "cisco",
    "cisco_meraki", "dell", "extreme_networks", "f5", "fortinet",
    "honeywell", "hpe", "ibm", "juniper", "netapp", "nutanix", "palo_alto",
    "pure_storage", "qnap", "rockwell_automation", "schneider_electric",
    "siemens", "sonicwall", "sophos", "supermicro", "synology", "watchguard"
}

NEW_HARDWARE_VENDORS = {
    "smiths_medical": {
        "id": "smiths_medical",
        "name": "Smiths Medical",
        "category": "Hardware",
        "sector": "IoMT",
        "sectors": ["IoMT"],
        "website": "https://www.smiths-medical.com",
        "allowed_domains": ["smiths-medical.com", "icumed.com"],
        "entry_points": [
            {
                "name": "Smiths Medical Infusion Systems Catalog",
                "url": "https://www.smiths-medical.com/products/infusion-systems",
                "strategy": "sitemap",
                "crawler_type": "sitemap",
                "category": "Medical Infusion Pumps",
                "confidence": "high",
            }
        ]
    },
    "hillrom": {
        "id": "hillrom",
        "name": "Hillrom",
        "category": "Hardware",
        "sector": "IoMT",
        "sectors": ["IoMT"],
        "website": "https://www.hillrom.com",
        "allowed_domains": ["hillrom.com", "welchallyn.com", "baxter.com"],
        "entry_points": [
            {
                "name": "Hillrom Welch Allyn Vital Signs Catalog",
                "url": "https://www.hillrom.com/en/products/category/patient-monitoring",
                "strategy": "dom_table",
                "crawler_type": "dom_table",
                "category": "Patient Monitoring Hardware",
                "confidence": "high",
            }
        ]
    },
    "te_connectivity": {
        "id": "te_connectivity",
        "name": "TE Connectivity",
        "category": "Hardware",
        "sector": "IoT",
        "sectors": ["IoT", "OT"],
        "website": "https://www.te.com",
        "allowed_domains": ["te.com"],
        "entry_points": [
            {
                "name": "TE Connectivity Industrial Sensors Catalog",
                "url": "https://www.te.com/en/products/sensors.html",
                "strategy": "sitemap",
                "crawler_type": "sitemap",
                "category": "Industrial Sensors & Connectivity",
                "confidence": "high",
            }
        ]
    },
    "sensata": {
        "id": "sensata",
        "name": "Sensata Technologies",
        "category": "Hardware",
        "sector": "IoT",
        "sectors": ["IoT", "OT"],
        "website": "https://www.sensata.com",
        "allowed_domains": ["sensata.com"],
        "entry_points": [
            {
                "name": "Sensata Industrial Pressure & Temperature Sensor Catalog",
                "url": "https://www.sensata.com/products/pressure-sensors",
                "strategy": "dom_table",
                "crawler_type": "dom_table",
                "category": "Industrial Sensors",
                "confidence": "high",
            }
        ]
    },
    "horiba": {
        "id": "horiba",
        "name": "HORIBA",
        "category": "Hardware",
        "sector": "OT",
        "sectors": ["OT"],
        "website": "https://www.horiba.com",
        "allowed_domains": ["horiba.com"],
        "entry_points": [
            {
                "name": "HORIBA Process & Semiconductor Equipment Catalog",
                "url": "https://www.horiba.com/en_en/products/process-and-environmental/",
                "strategy": "dom_table",
                "crawler_type": "dom_table",
                "category": "Industrial & Process Instrumentation",
                "confidence": "high",
            }
        ]
    },
    "meidensha": {
        "id": "meidensha",
        "name": "Meidensha Corporation",
        "category": "Hardware",
        "sector": "OT",
        "sectors": ["OT"],
        "website": "https://www.meidensha.com",
        "allowed_domains": ["meidensha.com", "meidensha.co.jp"],
        "entry_points": [
            {
                "name": "Meidensha Industrial Power & Drive Systems",
                "url": "https://www.meidensha.com/products/industry/index.html",
                "strategy": "dom_table",
                "crawler_type": "dom_table",
                "category": "Industrial Drives & Substation Equipment",
                "confidence": "high",
            }
        ]
    }
}


def enrich_vendors_yaml():
    yaml_path = BASE_DIR / "configs" / "vendors.yaml"
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    vendors = data.get("vendors", {})
    logger.info(f"Loaded {len(vendors)} vendors from {yaml_path.name}")

    # 1. Update existing vendors with category and sector
    for k, v in vendors.items():
        v_key = str(k).lower()
        if v_key in SOFTWARE_VENDORS:
            v["category"] = "Software"
        elif v_key in HYBRID_VENDORS:
            v["category"] = "Hybrid"
        else:
            v["category"] = "Hardware"

        if v_key in IOMT_VENDORS:
            v["sector"] = "IoMT"
            sectors = v.get("sectors", [])
            if "IoMT" not in sectors:
                sectors = ["IoMT"] + [s for s in sectors if s != "IoMT"]
            v["sectors"] = sectors

    # 2. Add new hardware vendors
    added_count = 0
    for k, v_dict in NEW_HARDWARE_VENDORS.items():
        if k not in vendors:
            vendors[k] = v_dict
            added_count += 1

    logger.info(f"Added {added_count} new hardware vendors. Total vendors: {len(vendors)}")

    # 3. Save enriched vendors.yaml
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    logger.info(f"Successfully wrote enriched configuration to {yaml_path.name}")


if __name__ == "__main__":
    enrich_vendors_yaml()
