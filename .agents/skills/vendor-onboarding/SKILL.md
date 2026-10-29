---
name: vendor-onboarding
description: >-
  Use this skill when onboarding a new hardware/software manufacturer into configs/vendors.yaml,
  adding lifecycle portals, validating allowed domains for SSRF protection, or checking zero-defaults compliance.
---

# Enterprise Vendor Onboarding Runbook

This skill guides the onboarding of new enterprise vendors (OT, IoT, IT) into the configuration-driven framework without breaking existing vendors. The repository natively supports **140 verified global enterprise vendors** (54 OT, 44 IoT, 42 IT).

---

## 📋 Onboarding Steps

### Step 1: Open and Edit `configs/vendors.yaml`
Add a new vendor entry under the `vendors:` mapping in [`configs/vendors.yaml`](configs/vendors.yaml):

```yaml
  toyoda:
    id: "toyoda"
    name: "JTEKT Toyoda (Toyopuc)"
    sector: "OT"
    website: "https://toyoda.jtekt.co.jp"
    allowed_domains:
      - "jtekt.co.jp"
      - "toyoda.jtekt.co.jp"
    entry_points:
      - url: "https://toyoda.jtekt.co.jp/e/support/"
        name: "Toyopuc PLC Support & Discontinuation"
        region: "Global"
```

### Step 2: Enforce Zero-Defaults Policy
- **DO NOT** add `default_os` or `default_firmware`.
- If a product does not specify an operating system or firmware version, it MUST remain `None` / `""` (SQL `NULL`).
- Official vendor terminology must be dynamically extracted from the page.
- **Zero Status Limitations**: Do NOT constrain vendor lifecycle phases to a predefined status list. The pipeline extracts and preserves the vendor's genuine milestone terms (*Phase-Out Product, Classic, Delivery Release, Announced Discontinuation, etc.*).

### Step 3: Verify SSRF Domain Whitelist & Deep Coverage
- Ensure all hostnames used in `entry_points` or `website` have their base domain explicitly listed in `allowed_domains`.
- If entry points link to paginated portals (`?page=`) or downloadable PDF bulletins (`.pdf`), ensure document hosting domains (e.g. `dl.mitsubishielectric.com`, `support.industry.siemens.com`) are included in `allowed_domains`.
- Disallowed: Any private IP, loopback, or cloud metadata IP (`169.254.169.254`).

### Step 4: Validate Configuration Integrity
Run the automated pre-commit config check:
```bash
python scripts/pre_commit_check.py
```
Check 5 will automatically validate that all 140+ vendor entries conform to all schema requirements.

---

## 🏭 Recently Onboarded Well-Known Vendors
- **JTEKT Toyoda (`toyoda`)**: Operational Technology (OT) - Toyopuc PLCs, CNC machinery controllers.
- **Hitachi Industrial Equipment (`hitachi_industrial`)**: OT - EH-150 / HX series PLCs, SJ series inverters.
- **Shibaura Machine (`shibaura_machine`)**: OT - TCmini / TC200 machine controllers, industrial robotics.
- **Dragos (`dragos`)**: OT - ICS/SCADA cybersecurity appliances, network sensors.
- **Cisco Meraki (`cisco_meraki`)**: IoT - MV smart cameras, MT environmental sensors, cloud switches.
- **Nozomi Networks (`nozomi_networks`)**: IoT/OT - Guardian industrial monitoring appliances.
- **Barracuda Networks (`barracuda_networks`)**: IT - CloudGen firewalls, email protection appliances.
- **Fluke Networks (`fluke_networks`)**: IT/OT - DSX CableAnalyzer, LinkIQ network test appliances.
