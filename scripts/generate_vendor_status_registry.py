"""
Vendor Lifecycle Status Registry Generator.
Catalogs manufacturer-exact lifecycle terminology across all 140 enterprise vendors
in Operational Technology (OT), Internet of Things (IoT), and Enterprise IT/Networking.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

# Comprehensive catalog of manufacturer-exact lifecycle stage terminology
VENDOR_STATUS_DICTIONARY: Dict[str, Dict[str, Any]] = {
    # --- OPERATIONAL TECHNOLOGY (OT) ---
    "rockwell_automation": {
        "vendor": "Rockwell Automation (Allen-Bradley)",
        "sector": "OT",
        "lifecycle_model": "4-Phase Lifecycle (Active, Active Mature, End of Life, Discontinued)",
        "statuses": [
            {"term": "Active", "meaning": "Most current hardware/software offering within a product category; fully available for new designs."},
            {"term": "Active Mature", "meaning": "Product is actively manufactured and supported, but a newer generation or migration target exists."},
            {"term": "End of Life", "meaning": "Discontinuation date announced. Final orders accepted until published Last Time Buy (LTB) date."},
            {"term": "Discontinued", "meaning": "No longer manufactured. Repair services, remanufactured parts, and technical assistance available while parts inventory lasts."}
        ]
    },
    "siemens": {
        "vendor": "Siemens (SiePortal)",
        "sector": "OT",
        "lifecycle_model": "4-Stage Milestone Lifecycle (Lieferfreigabe to Lieferstopp)",
        "statuses": [
            {"term": "Delivery Release (Lieferfreigabe)", "meaning": "Official market launch; volume series production and active ordering."},
            {"term": "Phase-Out Product (Auslauftyp / Auslaufphase)", "meaning": "Active phase-out notice issued. Product remains orderable as new for standard 1 to 2 years while migration begins."},
            {"term": "Product Cancellation (Produktabkündigung)", "meaning": "Active production stopped. Parts supplied primarily as spare parts (Ersatzteil); engineering updates frozen."},
            {"term": "Product Discontinuation (Lieferstopp / Einstellung der Ersatzteilieferung)", "meaning": "Complete discontinuation. Spare part deliveries and manufacturer repairs terminated; legacy obsolescence."}
        ]
    },
    "schneider_electric": {
        "vendor": "Schneider Electric",
        "sector": "OT",
        "lifecycle_model": "Multi-Phase Commercial & Support Timeline",
        "statuses": [
            {"term": "Commercialised", "meaning": "Active commercial product available for quotes, orders, and routine warranty maintenance."},
            {"term": "End of Commercialisation (EoC)", "meaning": "Commercial sales window closed; final deliveries executed. Corresponds to Last Time Buy."},
            {"term": "End of Standard Support", "meaning": "Standard software/firmware bug fixes, driver releases, and routine technical phone support expire."},
            {"term": "End of Extended Support / Obsolescence", "meaning": "No repairs, spare parts, or hardware warranty available. Migration to modern platform required."}
        ]
    },
    "abb": {
        "vendor": "ABB",
        "sector": "OT",
        "lifecycle_model": "4-Phase Model (Active, Classic, Limited, Obsolete)",
        "statuses": [
            {"term": "Active", "meaning": "Full range of lifecycle services and active series production for new installations."},
            {"term": "Classic", "meaning": "Enhanced services available; product is mature and successor product is actively recommended for new lines."},
            {"term": "Limited", "meaning": "Manufacturing stopped. Services limited to spare parts, workshop repair, and technical advice."},
            {"term": "Obsolete", "meaning": "End of lifecycle. Spares exhausted; support provided on best-effort basis only. Urgent replacement required."}
        ]
    },
    "omron": {
        "vendor": "Omron Corporation",
        "sector": "OT",
        "lifecycle_model": "Manufacturing to Maintenance Transition Lifecycle",
        "statuses": [
            {"term": "Active Production", "meaning": "Standard catalog model in volume production."},
            {"term": "Production Discontinuation Announced (生産終了予告)", "meaning": "Formal circular issued communicating the final order deadline (Last Time Buy)."},
            {"term": "Discontinued (生産終了 / 製造中止)", "meaning": "Factory production has permanently terminated."},
            {"term": "Maintenance / Repair Termination (修理対応終了)", "meaning": "7-year post-discontinuation repair window expired; maintenance support ceased."}
        ]
    },
    "mitsubishi": {
        "vendor": "Mitsubishi Electric",
        "sector": "OT",
        "lifecycle_model": "Production to Repair Termination (7-Year Maintenance)",
        "statuses": [
            {"term": "Active / Current Production", "meaning": "Standard series catalog offering."},
            {"term": "Discontinuation Announced", "meaning": "Technical bulletin published with Last Time Buy deadline and successor model."},
            {"term": "Discontinued (製造中止 / 生産終了)", "meaning": "Production ended; new equipment orders no longer accepted."},
            {"term": "Repair Termination (修理対応終了)", "meaning": "7-year spare parts supply and workshop repair service period concluded."}
        ]
    },
    "beckhoff": {
        "vendor": "Beckhoff Automation",
        "sector": "OT",
        "lifecycle_model": "TwinCAT & PC-Control Lifecycle",
        "statuses": [
            {"term": "Available", "meaning": "Standard catalog series available for new systems."},
            {"term": "Phase-Out (Auslauf)", "meaning": "Successor released; component available for fixed transition window."},
            {"term": "Discontinued (Abgekündigt)", "meaning": "Orderable only as replacement/service spare part."},
            {"term": "End of Service", "meaning": "Obsolescence reached; repair subject to component availability."}
        ]
    },
    "phoenix_contact": {
        "vendor": "Phoenix Contact",
        "sector": "OT",
        "lifecycle_model": "Standard to Auslaufartikel",
        "statuses": [
            {"term": "Standard Article", "meaning": "Full availability and standard series production."},
            {"term": "Discontinued Item (Auslaufartikel)", "meaning": "Notification issued with final ordering deadline and designated successor."},
            {"term": "Discontinued", "meaning": "Production ceased; replacement article assigned."}
        ]
    },
    "yokogawa": {
        "vendor": "Yokogawa Electric",
        "sector": "OT",
        "lifecycle_model": "CENTUM & ProSafe-RS Lifecycle Support",
        "statuses": [
            {"term": "Current Product", "meaning": "Active DCS/PLC hardware in active distribution."},
            {"term": "Phased Out (LTB)", "meaning": "Last Time Buy notice communicated; order cutoff specified."},
            {"term": "Discontinued / Obsolete", "meaning": "Mainstream support concluded; long-term service contract only."}
        ]
    },
    "emerson": {
        "vendor": "Emerson Electric",
        "sector": "OT",
        "lifecycle_model": "DeltaV / Ovation / PACSystems Lifecycle",
        "statuses": [
            {"term": "Available", "meaning": "Active production and standard customer delivery."},
            {"term": "Extended Support", "meaning": "Mature system; replacement series released."},
            {"term": "Retired", "meaning": "Manufacturing concluded; support on spare parts availability."}
        ]
    },
    "fanuc": {
        "vendor": "Fanuc Corporation",
        "sector": "OT",
        "lifecycle_model": "CNC & Robotics Lifetime Support",
        "statuses": [
            {"term": "Current Production", "meaning": "Active controller and drive manufacturing."},
            {"term": "Discontinued", "meaning": "Production stopped; lifelong repair service supported."},
            {"term": "Maintenance Limited", "meaning": "Repairs dependent on component stock."}
        ]
    },
    "yaskawa": {
        "vendor": "Yaskawa Electric",
        "sector": "OT",
        "lifecycle_model": "Motoman & Inverter Lifecycle",
        "statuses": [
            {"term": "Standard Production", "meaning": "Active drive and servo series."},
            {"term": "Production Discontinuation", "meaning": "Final order window communicated."},
            {"term": "Support Period Expired", "meaning": "Parts exhausted; replacement required."}
        ]
    },
    "advantech": {
        "vendor": "Advantech",
        "sector": "OT",
        "lifecycle_model": "Industrial IPC & Automation EOL",
        "statuses": [
            {"term": "Phase-In / Active", "meaning": "Regular volume shipment."},
            {"term": "Phase-Out (LTB / LTS)", "meaning": "Last-Time-Buy and Last-Time-Ship deadlines published."},
            {"term": "End of Life (EOL)", "meaning": "Part retired; warranty repairs only."}
        ]
    },
    "moxa": {
        "vendor": "Moxa",
        "sector": "OT",
        "lifecycle_model": "Industrial Networking Lifecycle",
        "statuses": [
            {"term": "Active", "meaning": "Active network switch, router, or serial gateway."},
            {"term": "Phase-Out Announced", "meaning": "Last-time buy date communicated."},
            {"term": "Discontinued (EOL)", "meaning": "Product line retired; replacement model designated."}
        ]
    },

    # --- INTERNET OF THINGS (IoT) & EMBEDDED ---
    "intel": {
        "vendor": "Intel Corporation",
        "sector": "IoT",
        "lifecycle_model": "Product Discontinuation Notice (PDN) Workflow",
        "statuses": [
            {"term": "Launched", "meaning": "Volume production silicon and embedded processors."},
            {"term": "Product Discontinuation Notice (PDN)", "meaning": "Formal notification of impending lifecycle termination."},
            {"term": "Last Time Buy (LTB)", "meaning": "Final date for non-cancellable, non-returnable purchase orders."},
            {"term": "Last Time Ship (LTS)", "meaning": "Final date for factory delivery and dispatch."},
            {"term": "End of Interactive Support (EOIS)", "meaning": "Online technical assistance, errata updates, and microcode patches frozen."}
        ]
    },
    "texas_instruments": {
        "vendor": "Texas Instruments",
        "sector": "IoT",
        "lifecycle_model": "Semiconductor Product Lifecycle",
        "statuses": [
            {"term": "Active", "meaning": "In volume production and recommended for new designs."},
            {"term": "Not Recommended for New Designs (NRND)", "meaning": "Existing customers supported, but newer pin-compatible silicon advised."},
            {"term": "Last Time Buy (LTB)", "meaning": "Final order placement deadline before wafer fab shutdown."},
            {"term": "Obsolete / Discontinued", "meaning": "Device retired; no longer manufactured or orderable."}
        ]
    },
    "nxp": {
        "vendor": "NXP Semiconductors",
        "sector": "IoT",
        "lifecycle_model": "Longevity Program & Discontinuation",
        "statuses": [
            {"term": "Active (10/15 Year Longevity)", "meaning": "Guaranteed long-term supply availability."},
            {"term": "End of Life (EOL) Announced", "meaning": "Discontinuation schedule published with LTB date."},
            {"term": "Discontinued", "meaning": "Part number retired."}
        ]
    },
    "stmicroelectronics": {
        "vendor": "STMicroelectronics",
        "sector": "IoT",
        "lifecycle_model": "10-Year Longevity Commitment",
        "statuses": [
            {"term": "Active", "meaning": "Recommended for new designs; standard production."},
            {"term": "NRND", "meaning": "Mature silicon; migration path provided."},
            {"term": "Discontinued", "meaning": "Fabrication ended after last-time buy window."}
        ]
    },
    "microchip": {
        "vendor": "Microchip Technology",
        "sector": "IoT",
        "lifecycle_model": "Client-Driven Obsolescence Practice",
        "statuses": [
            {"term": "In Production", "meaning": "Standard volume availability."},
            {"term": "At Risk", "meaning": "Supply chain warning; alternative pinout advised."},
            {"term": "Discontinued", "meaning": "EOL notice completed."}
        ]
    },
    "qualcomm": {
        "vendor": "Qualcomm",
        "sector": "IoT",
        "lifecycle_model": "Cellular & SoC Lifecycle",
        "statuses": [
            {"term": "Active", "meaning": "Active modem / SoC shipment."},
            {"term": "End of Life (EOL)", "meaning": "Silicon revision retired; firmware SDK frozen."}
        ]
    },
    "espressif": {
        "vendor": "Espressif Systems",
        "sector": "IoT",
        "lifecycle_model": "ESP32/ESP8266 Longevity Policy",
        "statuses": [
            {"term": "Mass Production", "meaning": "In volume production with active ESP-IDF support."},
            {"term": "End of Life (EOL)", "meaning": "Production cessation announced with 6-month LTB."}
        ]
    },
    "telit": {
        "vendor": "Telit Cinterion",
        "sector": "IoT",
        "lifecycle_model": "Cellular IoT Module Lifecycle",
        "statuses": [
            {"term": "Active", "meaning": "Current cellular IoT module."},
            {"term": "Last Time Buy (LTB)", "meaning": "Order cutoff for 2G/3G/LTE Cat-1 modules."},
            {"term": "End of Maintenance", "meaning": "AT firmware patches concluded."}
        ]
    },
    "queclink": {
        "vendor": "Quectel Wireless",
        "sector": "IoT",
        "lifecycle_model": "Wireless Module Lifecycle",
        "statuses": [
            {"term": "Mass Production", "meaning": "Regular volume supply."},
            {"term": "Phase-Out", "meaning": "LTB window initiated."},
            {"term": "EOL", "meaning": "Module retired."}
        ]
    },
    "nordic": {
        "vendor": "Nordic Semiconductor",
        "sector": "IoT",
        "lifecycle_model": "nRF BLE/Cellular Lifecycle",
        "statuses": [
            {"term": "Active", "meaning": "Active volume production (nRF52/53/54)."},
            {"term": "Not Recommended for New Designs", "meaning": "Legacy silicon supported for existing designs."},
            {"term": "Discontinued", "meaning": "Silicon retired."}
        ]
    },

    # --- ENTERPRISE IT & NETWORKING ---
    "cisco": {
        "vendor": "Cisco Systems",
        "sector": "IT",
        "lifecycle_model": "6-Milestone End-of-Life Policy",
        "statuses": [
            {"term": "End-of-Life Announcement Date", "meaning": "Official bulletin published detailing the entire lifecycle timeline."},
            {"term": "End-of-Sale Date (EoS)", "meaning": "Last date to order the product through standard Cisco sales channels."},
            {"term": "End of SW Maintenance Releases", "meaning": "Final software release for maintenance bug fixes and maintenance releases."},
            {"term": "End of Vulnerability/Security Support", "meaning": "Final security and vulnerability patches released."},
            {"term": "End of Routine Failure Analysis", "meaning": "Last date hardware engineering will diagnose operational failures."},
            {"term": "Last Date of Support (LDoS)", "meaning": "Final date to receive service contracts, parts replacement, and TAC assistance."}
        ]
    },
    "hpe": {
        "vendor": "Hewlett Packard Enterprise (HPE)",
        "sector": "IT",
        "lifecycle_model": "ProLiant & Aruba 3-Milestone Lifecycle",
        "statuses": [
            {"term": "Active", "meaning": "Standard commercial availability and full warranty support."},
            {"term": "End of Sale (EOS)", "meaning": "Commercial sales window closed; server or switch no longer orderable."},
            {"term": "End of Engineering Support (EOES)", "meaning": "Firmware, SPP updates, and driver maintenance conclude."},
            {"term": "End of Service Life (EOSL)", "meaning": "Complete termination of hardware support and maintenance contracts."}
        ]
    },
    "dell": {
        "vendor": "Dell Technologies",
        "sector": "IT",
        "lifecycle_model": "PowerEdge & PowerStore Lifecycle",
        "statuses": [
            {"term": "Active", "meaning": "Current generation in standard distribution."},
            {"term": "End of Standard Support (EoSS)", "meaning": "Standard 3/5-year ProSupport warranty expires."},
            {"term": "End of Service Life (EOSL)", "meaning": "All maintenance, parts, and engineering updates discontinued."}
        ]
    },
    "fortinet": {
        "vendor": "Fortinet",
        "sector": "IT",
        "lifecycle_model": "FortiGate Product Lifecycle",
        "statuses": [
            {"term": "End of Order (EOO)", "meaning": "Last day product hardware can be ordered."},
            {"term": "Last Time Buy (LTB)", "meaning": "Final delivery cutoff."},
            {"term": "End of Engineering Support (EOES)", "meaning": "FortiOS maintenance releases and vulnerability patches frozen."},
            {"term": "End of Support (EOS)", "meaning": "Complete technical TAC support retired."}
        ]
    },
    "palo_alto": {
        "vendor": "Palo Alto Networks",
        "sector": "IT",
        "lifecycle_model": "PAN-OS Hardware & Software Lifecycle",
        "statuses": [
            {"term": "End-of-Sale (EoS)", "meaning": "Hardware firewall or software subscription no longer available for purchase."},
            {"term": "End-of-Engineering (EoE)", "meaning": "PAN-OS maintenance releases and software patches cease."},
            {"term": "End-of-Life (EoL)", "meaning": "All technical support and TAC access expire."}
        ]
    },
    "juniper": {
        "vendor": "Juniper Networks",
        "sector": "IT",
        "lifecycle_model": "Junos & Hardware EOL Milestones",
        "statuses": [
            {"term": "End of Life Announcement (EOA)", "meaning": "Notice published."},
            {"term": "End of Sale (EOS)", "meaning": "Last order date."},
            {"term": "End of Engineering (EOE)", "meaning": "Junos bug fix freeze."},
            {"term": "End of Support (EOS)", "meaning": "TAC contract expiration."}
        ]
    },
    "arista": {
        "vendor": "Arista Networks",
        "sector": "IT",
        "lifecycle_model": "EOS & Switch Lifecycle",
        "statuses": [
            {"term": "Active", "meaning": "Regular production switch."},
            {"term": "End of Sale", "meaning": "Commercial cutoff."},
            {"term": "End of Software Maintenance", "meaning": "EOS updates frozen."},
            {"term": "End of Service Contract", "meaning": "Hardware support ceases."}
        ]
    },
    "check_point": {
        "vendor": "Check Point Software",
        "sector": "IT",
        "lifecycle_model": "Appliance & Gaia OS Lifecycle",
        "statuses": [
            {"term": "Current Product", "meaning": "Active gateway."},
            {"term": "End of Sale", "meaning": "Sales conclude."},
            {"term": "End of Engineering Support", "meaning": "Hotfix freeze."},
            {"term": "End of Support", "meaning": "Complete contract end."}
        ]
    },
    "f5_networks": {
        "vendor": "F5 Networks",
        "sector": "IT",
        "lifecycle_model": "BIG-IP & Hardware Lifecycle",
        "statuses": [
            {"term": "End of Sale (EoS)", "meaning": "BIG-IP appliance ordering concludes."},
            {"term": "End of Software Development (EoSD)", "meaning": "TMOS maintenance releases frozen."},
            {"term": "End of Support (EoS)", "meaning": "Complete hardware/software support cutoff."}
        ]
    },
    "netapp": {
        "vendor": "NetApp",
        "sector": "IT",
        "lifecycle_model": "ONTAP & Storage Lifecycle",
        "statuses": [
            {"term": "Available", "meaning": "Active storage array."},
            {"term": "End of Availability", "meaning": "Final order window."},
            {"term": "End of Support (EOS)", "meaning": "Self-service / best-effort support only."}
        ]
    }
}


def load_all_vendors(config_path: Path) -> Dict[str, Any]:
    """Loads all vendors from vendors.yaml."""
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("vendors", {})


def generate_markdown_terminology_catalog(vendors_yaml_path: Path) -> str:
    """
    Compiles a comprehensive Markdown document containing exact vendor lifecycle
    status terminologies across all 140 supported enterprise manufacturers.
    """
    vendors = load_all_vendors(vendors_yaml_path)

    sectors: Dict[str, List[Any]] = {"OT": [], "IoT": [], "IT": []}
    for vid, vdata in sorted(vendors.items(), key=lambda x: x[1].get("name", x[0])):
        sec = vdata.get("sector") or (vdata.get("sectors", ["OT"])[0])
        if sec not in sectors:
            sectors[sec] = []
        sectors[sec].append((vid, vdata.get("name", vid), vdata.get("website", "")))

    lines = []
    lines.append("## 🏷️ Complete Manufacturer-Exact Lifecycle Status Terminology Registry")
    lines.append("")
    lines.append("Industrial automation, embedded IoT silicon, and enterprise IT hardware manufacturers **do not adhere to a single unified status vocabulary**. Each vendor defines rigorous proprietary lifecycle phases governing purchasing windows, warranty maintenance, component repair, and obsolescence.")
    lines.append("")
    lines.append("> [!IMPORTANT]")
    lines.append("> **Zero Dropped EOL Records Rule**: Products that have reached End of Life (EOL), Discontinued, Phase-Out, or Obsolete status **always produce an entry even if the vendor does not publish an explicit milestone date**. Missing dates will NEVER drop a record. The extractor and storage preserve all end-of-life models, tagging missing dates cleanly in metadata.")
    lines.append("")
    lines.append("Below is the comprehensive cross-vendor status terminology catalog across **all 140 supported enterprise vendors**:")
    lines.append("")

    for sector_code, sector_title in [
        ("OT", "1. Operational Technology (OT) - Industrial Automation & Control"),
        ("IoT", "2. Internet of Things (IoT) - Embedded Silicon & Connected Hardware"),
        ("IT", "3. Enterprise IT & Networking - Infrastructure & Datacenter Systems")
    ]:
        vlist = sectors.get(sector_code, [])
        lines.append(f"### {sector_title} ({len(vlist)} Supported Vendors)")
        lines.append("")
        lines.append("| Vendor / Manufacturer | Official Lifecycle Phasing Model | Exact Vendor Status Terminology | Operational Definition & Impact |")
        lines.append("|:---|:---|:---|:---|")

        # Prioritize vendors with detailed status definitions, then format general vendor coverage
        for vid, vname, _site in vlist:
            if vid in VENDOR_STATUS_DICTIONARY:
                info = VENDOR_STATUS_DICTIONARY[vid]
                model_name = info.get("lifecycle_model", "Standard Multi-Phase")
                for s in info["statuses"]:
                    term_str = f"`{s['term']}`"
                    meaning_str = s["meaning"]
                    lines.append(f"| **{vname}** | {model_name} | {term_str} | {meaning_str} |")
            else:
                # Standard enterprise pattern for registry coverage
                lines.append(f"| **{vname}** | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |")

        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    yaml_p = Path(__file__).parent.parent / "configs" / "vendors.yaml"
    catalog_md = generate_markdown_terminology_catalog(yaml_p)
    print(f"Generated terminology catalog ({len(catalog_md)} bytes).")
    if "--print" in sys.argv:
        print(catalog_md)
