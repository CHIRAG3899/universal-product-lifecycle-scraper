"""
Multi-Vendor Registry & Internationalization (i18n) Normalization Module.
Enables the AI scraper to handle diverse industrial automation vendors
and automatically translate regional/local language product notices into English.
"""

import re
from typing import Any, Dict, Optional

# Multi-lingual stage mapping dictionary (maps localized & vendor terms to clean English Stages)
# Vendors do NOT follow a single fixed status list; vendor-specific lifecycle phases are preserved as-is.
STAGE_TRANSLATIONS: Dict[str, str] = {
    # Vendor-Specific English Stages (Preserved Exactly)
    "end of sales announcement": "End of Life (EOL)",  # Legacy sentence mapping for backward compatibility
    "end of sale": "End of Sale",
    "end of sales": "End of Sale",
    "last date of support": "Last Date of Support",
    "ldos": "Last Date of Support (LDoS)",
    "end of sw maintenance": "End of SW Maintenance",
    "end of software maintenance": "End of SW Maintenance",
    "end of new service": "End of New Service",
    "delivery release": "Delivery Release",
    "announced discontinuation": "Announced Discontinuation",
    "product cancellation": "Product Cancellation",
    "product discontinuation": "Product Discontinuation",
    "phase-out product": "Phase-Out Product",
    "phase-out announced": "Phase-Out Announced",
    "phase out": "Phase-Out Announced",
    "phase-out": "Phase-Out",
    "classic": "Classic",
    "limited": "Limited",
    "obsolete": "Obsolete",
    "active mature": "Active Mature",
    "active": "Active",
    "stop shipment": "Stop Shipment",
    "repair termination": "Repair Termination",
    "production termination": "Production Termination",
    "maintenance only": "Maintenance Only",
    "extended maintenance": "Extended Maintenance",

    # Standard EOL / LTB / EOS Terms
    "end of life": "End of Life (EOL)",
    "eol": "End of Life (EOL)",
    "product end of life": "End of Life (EOL)",
    "end of life cycle": "End of Life (EOL)",
    "end of support": "End of Support",
    "support end": "End of Support",
    "eosl": "End of Service Life (EOSL)",
    "end of service life": "End of Service Life (EOSL)",
    "end of availability": "End of Availability (EOA)",
    "eoa": "End of Availability (EOA)",
    "last support date": "Last Date of Support",
    "final order date": "Last Time Buy (LTB)",
    "last order date": "Last Time Buy (LTB)",
    "last order": "Last Time Buy (LTB)",
    "last purchase date": "Last Time Buy (LTB)",
    "last purchase": "Last Time Buy (LTB)",
    "last time buy": "Last Time Buy (LTB)",
    "ltb": "Last Time Buy (LTB)",
    "end of service": "End of Service (EOS)",
    "eos": "End of Service (EOS)",
    "discontinued": "Discontinued",
    "discontinued model": "Discontinued",
    "discontinued product": "Discontinued",
    "discontinuation notification": "Discontinuation Notification",
    "legacy product": "Discontinued",
    "no longer sold": "Discontinued",
    "to be discontinued": "Phase-Out Announced",
    "withdrawal": "Production Withdrawal",
    "final order": "Last Time Buy (LTB)",
    "repair end": "End of Service (EOS)",
    "phaseout": "Phase-Out",
    "end of maintenance": "End of Maintenance",

    # German (Siemens, Phoenix Contact, Beckhoff)
    "produktabkündigung": "End of Life (EOL)",
    "abkündigung": "End of Life (EOL)",
    "auslauftyp": "Phase-Out Announced",
    "auslaufphase": "Phase-Out Announced",
    "letzte bestellmöglichkeit": "Last Time Buy (LTB)",
    "einstellung der reparatur": "End of Service (EOS)",
    "ersatzteilende": "End of Service (EOS)",
    "lieferstopp": "Discontinued",
    "nachfolgeprodukt": "Replacement Model",
    "ersatztyp": "Replacement Model",
    "abkündigungstermin": "Discontinuation Date",
    "serviceende": "End of Service (EOS)",

    # Japanese (Mitsubishi, Omron, Keyence, Fanuc, Yaskawa, JTEKT, Fuji Electric)
    "生産終了": "End of Life (EOL)",
    "販売終了": "End of Life (EOL)",
    "製造中止": "Discontinued",
    "最終受注": "Last Time Buy (LTB)",
    "最終注文": "Last Time Buy (LTB)",
    "最終出荷": "Last Time Ship (LTS)",
    "保守終了": "End of Service (EOS)",
    "修理対応終了": "End of Service (EOS)",
    "修理対応期間": "Maintenance / Repair Period",
    "修理対応終了予定": "Scheduled End of Support",
    "補修用性能部品保有期間終了": "End of Spare Parts Retention",
    "補修部品供給終了": "End of Service (EOS)",
    "代替品": "Replacement Model",
    "代替推奨品": "Recommended Replacement",
    "後継機種": "Successor Model",
    "現行品": "Active / In Production",

    # Swedish / Nordic (Mitsubishi Scandinavian branch, ABB)
    "utgående produkt": "End of Life (EOL)",
    "avveckling": "End of Life (EOL)",
    "sista orderdatum": "Last Time Buy (LTB)",
    "sista beställning": "Last Time Buy (LTB)",
    "service upphör": "End of Service (EOS)",
    "support upphör": "End of Service (EOS)",

    # French (Schneider Electric)
    "fin de vie": "End of Life (EOL)",
    "arrêt de commercialisation": "End of Life (EOL)",
    "fin de commercialisation": "End of Sale",
    "dernière commande": "Last Time Buy (LTB)",
    "fin de support": "End of Service (EOS)",
    "fin de maintenance": "End of Service (EOS)",
    "obsolescence": "End of Life (EOL)",
    "produit de remplacement": "Replacement Model",
    "substitut": "Replacement Model",

    # Chinese (Delta Electronics, Inovance, Moxa, Advantech)
    "停产": "Discontinued",
    "停售": "End of Sale",
    "停产公告": "End of Life (EOL)",
    "最后订购": "Last Time Buy (LTB)",
    "最后订购日": "Last Time Buy (LTB)",
    "最后发货日": "Last Time Ship (LTS)",
    "终止服务": "End of Service (EOS)",
    "终止支持": "End of Support",
    "替代型号": "Replacement Model",
    "推荐替代": "Recommended Replacement",

    # Spanish / Italian
    "fine vita": "End of Life (EOL)",
    "fuori produzione": "Discontinued",
    "fine servizio": "End of Service (EOS)",
    "fine supporto": "End of Support",
    "fin de vida": "End of Life (EOL)",
    "fin de comercialización": "End of Sale",
    "última compra": "Last Time Buy (LTB)",
    "fin de soporte": "End of Support",
    "fin de servicio": "End of Service (EOS)",
    "producto de reemplazo": "Replacement Model",

    # Korean (LS Electric, Hanwha)
    "단종": "Discontinued",
    "생산종료": "End of Life (EOL)",
    "판매종료": "End of Sale",
    "지원종료": "End of Support",
    "최종주문": "Last Time Buy (LTB)",
    "대체모델": "Replacement Model"
}

# Regional equipment classification and technical term translation map
REGIONAL_CATEGORY_MAP: Dict[str, str] = {
    # Japanese
    "プログラマブルコントローラ": "Programmable Logic Controller (PLC)",
    "プログラマブル表示器": "HMI (Human-Machine Interface)",
    "表示器": "HMI (Human-Machine Interface)",
    "タッチパネル": "Touch Panel / HMI",
    "インバータ": "Inverter / Drive",
    "サーボモータ": "Servo Motor",
    "サーボアンプ": "Servo Amplifier / Drive",
    "産業用pc": "Industrial PC (IPC)",
    "産業用ロボット": "Industrial Robot",
    "センサ": "Sensor",
    "スイッチ": "Switch",
    "温度調節器": "Temperature Controller",
    "電源": "Power Supply",
    # German
    "speicherprogrammierbare steuerung": "Programmable Logic Controller (PLC)",
    "bedien- und beobachtungssysteme": "HMI (Human-Machine Interface)",
    "bediengerät": "HMI (Human-Machine Interface)",
    "frequenzumrichter": "Inverter / Drive",
    "servoverstärker": "Servo Amplifier / Drive",
    "industrie-pc": "Industrial PC (IPC)",
    "schaltgeräte": "Switchgear",
    "sensoren": "Sensor",
    "stromversorgungen": "Power Supply",
    # French
    "automate programmable industriel": "Programmable Logic Controller (PLC)",
    "interface homme-machine": "HMI (Human-Machine Interface)",
    "variateur de vitesse": "Inverter / Drive",
    "servovariateur": "Servo Drive",
    "pc industriel": "Industrial PC (IPC)",
    "capteurs": "Sensor",
    "alimentation": "Power Supply",
    # Chinese
    "可编程逻辑控制器": "Programmable Logic Controller (PLC)",
    "人机界面": "HMI (Human-Machine Interface)",
    "触摸屏": "Touch Panel / HMI",
    "变频器": "Inverter / Drive",
    "伺服驱动器": "Servo Drive",
    "工控机": "Industrial PC (IPC)",
    "工业机器人": "Industrial Robot",
    "传感器": "Sensor",
    "交换机": "Industrial Switch",
    "电源": "Power Supply"
}


def translate_regional_text(text: Optional[str]) -> str:
    """Translates regional category names, status descriptions, or notes to clean English."""
    if not text or not isinstance(text, str):
        return ""
    cleaned = text.strip()
    c_lower = cleaned.lower()
    for reg_key, en_val in REGIONAL_CATEGORY_MAP.items():
        if reg_key.lower() in c_lower:
            return en_val
    return cleaned

# Known Major Industrial Vendors (Defaults removed per specification: OS and Firmware must be dynamically found)
VENDOR_PROFILES: Dict[str, Dict[str, Any]] = {
    "mitsubishi": {
        "display_name": "Mitsubishi Electric",
        "domains": ["mitsubishielectric.com", "mitsubishielectricfa.com"],
        "sector": "OT"
    },
    "siemens": {
        "display_name": "Siemens",
        "domains": ["siemens.com", "sieportal.siemens.com", "industry.siemens.com"],
        "sector": "OT"
    },
    "schneider_electric": {
        "display_name": "Schneider Electric",
        "domains": ["se.com", "schneider-electric.com"],
        "sector": "OT"
    },
    "rockwell_automation": {
        "display_name": "Rockwell Automation (Allen-Bradley)",
        "domains": ["rockwellautomation.com", "ab.com"],
        "sector": "OT"
    },
    "omron": {
        "display_name": "Omron Corporation",
        "domains": ["omron.com", "ia.omron.com"],
        "sector": "OT"
    },
    "abb": {
        "display_name": "ABB",
        "domains": ["abb.com"],
        "sector": "OT"
    },
    "cisco_systems": {
        "display_name": "Cisco Systems",
        "domains": ["cisco.com"],
        "sector": "IT"
    },
    "hpe": {
        "display_name": "Hewlett Packard Enterprise",
        "domains": ["hpe.com", "arubanetworks.com"],
        "sector": "IT"
    },
    "dell": {
        "display_name": "Dell Technologies",
        "domains": ["dell.com"],
        "sector": "IT"
    },
    "intel_iot": {
        "display_name": "Intel Edge & Embedded",
        "domains": ["intel.com"],
        "sector": "IoT"
    },
    "digi_international": {
        "display_name": "Digi International",
        "domains": ["digi.com"],
        "sector": "IoT"
    }
}


_LOADED_YAML_VENDORS: Optional[Dict[str, Any]] = None


def _get_yaml_vendors() -> Dict[str, Any]:
    """Dynamically loads and caches the 100 enterprise vendors from configs/vendors.yaml."""
    global _LOADED_YAML_VENDORS
    if _LOADED_YAML_VENDORS is None:
        _LOADED_YAML_VENDORS = {}
        try:
            from pathlib import Path

            import yaml
            cfg_path = Path(__file__).resolve().parent.parent / "configs" / "vendors.yaml"
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                    _LOADED_YAML_VENDORS = data.get("vendors", {})
        except Exception:
            _LOADED_YAML_VENDORS = {}
    return _LOADED_YAML_VENDORS


def detect_vendor_from_url_or_text(url: str, text: Optional[str] = None) -> str:
    """Identifies the vendor name based on URL domain or page text dynamically without assuming static defaults."""
    url_lower = (url or "").lower()

    # 1. Check primary profiles
    for v_key, profile in VENDOR_PROFILES.items():
        if any(dom in url_lower for dom in profile.get("domains", [])):
            return profile.get("display_name", v_key.title())

    # 2. Check 100 enterprise vendors loaded from vendors.yaml
    yaml_vendors = _get_yaml_vendors()
    for vk, vcfg in yaml_vendors.items():
        v_doms = vcfg.get("allowed_domains", [])
        v_site = (vcfg.get("website") or "").lower()
        if any(dom.lower() in url_lower for dom in v_doms if dom) or (v_site and v_site in url_lower):
            return vcfg.get("name", vk.replace("_", " ").title())

    if text:
        text_lower = text[:5000].lower()
        if "mitsubishi" in text_lower:
            return "Mitsubishi Electric"
        elif "siemens" in text_lower:
            return "Siemens"
        elif "schneider" in text_lower:
            return "Schneider Electric"
        elif "rockwell" in text_lower or "allen-bradley" in text_lower:
            return "Rockwell Automation (Allen-Bradley)"
        elif "omron" in text_lower:
            return "Omron Corporation"
        elif "cisco" in text_lower:
            return "Cisco Systems"
        elif "dell" in text_lower:
            return "Dell Technologies"
        elif "hpe" in text_lower or "hewlett packard" in text_lower:
            return "Hewlett Packard Enterprise"

        # Check YAML vendor names in text
        for vk, vcfg in yaml_vendors.items():
            v_name = vcfg.get("name", "").lower()
            if v_name and v_name in text_lower:
                return vcfg.get("name", vk.title())

    # Derive from domain if possible
    m = re.search(r'https?://(?:www\.)?([^/]+)', url or "")
    if m:
        domain = m.group(1).split(".")[0].title()
        return domain

    return "Industrial Automation"


def normalize_stage_name(raw_stage: Optional[str]) -> str:
    """
    Normalizes any local language, regional term, or vendor-specific lifecycle phase into clean English.
    Places ZERO arbitrary limitations on vendor status: preserves exact vendor-specific lifecycle
    milestones (e.g. 'Phase-Out Product', 'Delivery Release', 'Classic', 'Limited', 'Obsolete',
    'Active Mature', 'End of Sale', 'Last Date of Support', 'Product Cancellation', 'Stop Shipment').
    """
    if not raw_stage or not isinstance(raw_stage, str):
        return "Discontinued"

    # Strip markdown and HTML noise
    cleaned = raw_stage.strip()
    cleaned = re.sub(r'[\*\_\#\`]', '', cleaned).strip()
    cleaned = re.sub(r':$', '', cleaned).strip()
    c_lower = cleaned.lower()

    if not c_lower:
        return "Discontinued"

    # 1. Exact or substring match in STAGE_TRANSLATIONS dictionary (longest pattern first)
    for pattern in sorted(STAGE_TRANSLATIONS.keys(), key=len, reverse=True):
        if pattern in c_lower:
            return STAGE_TRANSLATIONS[pattern]

    # 2. Check for common vendor status phrases
    if "last date of support" in c_lower or "last support date" in c_lower or "ldos" in c_lower:
        return "Last Date of Support"
    if "end of service life" in c_lower or "eosl" in c_lower:
        return "End of Service Life (EOSL)"
    if "end of support" in c_lower or "support end" in c_lower:
        return "End of Support"
    if "end of availability" in c_lower or "eoa" in c_lower:
        return "End of Availability (EOA)"
    if "end of sale" in c_lower or "eos" == c_lower or "end of sales" in c_lower:
        return "End of Sale"
    if "ltb" in c_lower or ("last" in c_lower and "buy" in c_lower) or "final order" in c_lower or "last order" in c_lower or "last purchase" in c_lower:
        return "Last Time Buy (LTB)"
    if "eol" in c_lower or "end of life" in c_lower:
        return "End of Life (EOL)"
    if "eos" in c_lower or "end of service" in c_lower or "repair end" in c_lower:
        return "End of Service (EOS)"
    if "phase-out" in c_lower or "phase out" in c_lower or "phaseout" in c_lower:
        return "Phase-Out"
    if "discontinu" in c_lower:
        return "Discontinued"
    if "obsolete" in c_lower:
        return "Obsolete"
    if "classic" in c_lower:
        return "Classic"
    if "limited" in c_lower:
        return "Limited"
    if "active mature" in c_lower:
        return "Active Mature"
    if "maintenance only" in c_lower:
        return "Maintenance Only"

    # 3. Preserve the exact vendor status cleanly title-cased or preserved (up to 100 chars, no truncation)
    clean_title = cleaned[:100].strip()
    if clean_title.isupper() or clean_title.islower():
        clean_title = clean_title.title()
    return clean_title or "Discontinued"


def show_vendor_terminology(vendor_query: Optional[str] = None, sector_query: Optional[str] = None) -> None:
    """Displays manufacturer-exact lifecycle terminology catalog in a clean terminal table."""
    vendors = _get_yaml_vendors()
    print("\n" + "=" * 90)
    print("  MANUFACTURER-EXACT LIFECYCLE STATUS & TERMINOLOGY CATALOG")
    print("=" * 90)
    print(f"{'Vendor ID':<25} | {'Sector':<8} | {'Vendor Name':<35} | {'Key Stages'}")
    print("-" * 90)

    for vid, vdata in sorted(vendors.items()):
        if vendor_query and vendor_query.lower() not in vid.lower() and vendor_query.lower() not in vdata.get("name", "").lower():
            continue
        if sector_query and sector_query.lower() != vdata.get("sector", "").lower() and sector_query.lower() != "all":
            continue

        stages = [s for s, t in list(STAGE_TRANSLATIONS.items())[:3]]
        stages_str = ", ".join(stages)
        print(f"{vid:<25} | {vdata.get('sector', 'OT'):<8} | {vdata.get('name', vid)[:35]:<35} | {stages_str}")

    print("=" * 90 + "\n")


