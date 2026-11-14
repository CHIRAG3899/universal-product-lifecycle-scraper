# Enterprise Lifecycle Scraper - Master Data Contract & Lifecycle Normalization Specification

## 1. Document Overview & Contract Scope

This Data Contract defines the architectural, schema, typing, and validation invariants governing all records harvested by the **Universal Multi-Vendor EOL & Lifecycle AI Scraper** across **219 enterprise manufacturers** spanning Operational Technology (OT), Internet of Things (IoT), Information Technology (IT), and Internet of Medical Things (IoMT).

---

## 2. Master CSV Database Schema (Strict 11 Columns)

All records exported to disk are strictly partitioned into two production CSV files in Database Snake Case. The legacy `all_vendors_lifecycle.csv` has been permanently eliminated.

1. **`output/eol_products_lifecycle.csv`**: Contains all products reaching end-of-lifecycle milestones (`Phase Out`, `End of Sale`, `End of Support`, `Obsolete`).
2. **`output/active_products_lifecycle.csv`**: Contains currently supported and active commercial products (`Active`, `Active Mature`).

### 2.1 Column Definitions and Constraints

| # | Column Name | SQL Type | Nullable | Description & Constraints |
|:---:|:---|:---|:---:|:---|
| **1** | `vendor_name` | `VARCHAR(120)` | **NO** | Canonical manufacturer name (e.g. `Cisco Systems`, `Siemens`, `Rockwell Automation`). Rejects `N/A`, `None`, empty. |
| **2** | `model_name` | `VARCHAR(120)` | Conditional | Genuine product SKU or hardware model identifier (e.g. `WS-C2960X-48FPS-L`, `6ES7515-2AM02-0AB0`). **Mandatory for hardware**. Permitted empty ONLY for standalone software/OS packages where `os` is set. |
| **3** | `aliases` | `TEXT` | YES | Secondary product designations, family groupings, or unbundled variants. **Strict Invariant: Zero date leaks or narrative boilerplate**. |
| **4** | `status` | `VARCHAR(40)` | **NO** | Normalized Canonical Status ENUM value. Strictly restricted to one of the 6 canonical states. Maximum length 40 characters. |
| **5** | `stage_date_utc` | `VARCHAR(30)` | YES | Milestone occurrence timestamp in strict ISO 8601 UTC format: `YYYY-MM-DDTHH:MM:SSZ`. Empty string if unknown. Never invalid days or unparsed text. |
| **6** | `source_url` | `TEXT` | YES | Authoritative HTTP/HTTPS URL from which the lifecycle milestone was crawled. Must pass SSRF security guard. |
| **7** | `os` | `VARCHAR(80)` | YES | Extracted operating system name and version (e.g. `macOS Sonoma 14.7.1`, `iOS 18.2`, `FortiOS 7.4.1`). |
| **8** | `firmware` | `VARCHAR(80)` | YES | Hardware firmware revision or ROM microcode release. |
| **9** | `category` | `VARCHAR(80)` | **NO** | Product taxonomy classification (e.g. `Hardware - Industrial Controller`, `Software - OS`, `Networking - Switch`). |
| **10** | `replacement` | `VARCHAR(120)` | YES | Recommended successor hardware/software model SKU. Must pass model validation. **Rejects boilerplate phrases** (e.g. `CONTACT REPAIR & REPLACEMENT`, `NOT APPLICABLE`). |
| **11** | `metadata` | `JSON` | YES | Structured JSON string storing ingestion audit trail (`raw_vendor_status`, `bulletin_code`, `first_discovered_utc`, `run_id`). |

---

## 3. The 6 Canonical Status ENUMs

To eliminate vendor-specific fragmentation, all raw lifecycle statuses are mapped to the 6 Canonical ENUM values:

```
[ Active ] ──────> [ Active Mature ] ──────> [ Phase Out ] ──────> [ End of Sale ] ──────> [ End of Support ] ──────> [ Obsolete ]
```

### 3.1 Status Semantics & Definitions

1. **`Active`**: Standard catalog item. In mass production, orderable with standard commercial lead times, and under full active warranty and engineering support.
2. **`Active Mature`**: Active and orderable, but Not Recommended for New Designs (NRND). Older architecture maintained for existing customer expansion; newer replacement families exist.
3. **`Phase Out`**: Advance notice of impending discontinuation (*Vorabkündigung* / *Auslaufphase*). Transition period initiated to allow customers to plan architectural migrations before ordering stops.
4. **`End of Sale`**: Discontinued for new commercial orders. Last Time Buy (LTB) date reached. No new factory purchase orders accepted.
5. **`End of Support`**: Software engineering development, security vulnerability patches, maintenance updates, and standard customer support contracts cease (LDoS / EOSL).
6. **`Obsolete`**: Complete lifecycle termination. Hardware repair services, replacement parts inventories, and calibration capabilities expired. Archived equipment.

---

## 4. Multi-Vendor Terminology Normalization Matrix

The table below documents how raw vendor terminology maps into the 6 Canonical Statuses across key manufacturers:

### 4.1 Enterprise IT & Networking

| Vendor | Raw Vendor Terminology | Canonical Normalized Status | Notes |
|:---|:---|:---|:---|
| **Cisco Systems** | General Availability (GA) | `Active` | Active catalog shipping |
| **Cisco Systems** | End-of-Life Announcement Date | `Phase Out` | Initial customer notification |
| **Cisco Systems** | End-of-Sale Date (EoS) / Last Time Buy (LTB) | `End of Sale` | Final order placement deadline |
| **Cisco Systems** | End of SW Maintenance Releases Date | `End of Support` | Maintenance releases ceased |
| **Cisco Systems** | End of Vulnerability/Security Support | `End of Support` | Security CVE patches ceased |
| **Cisco Systems** | Last Date of Support (LDoS) | `End of Support` | Final technical support cutoff |
| **Cisco Systems** | Obsolete / End of Life | `Obsolete` | Hardware completely unsupportable |
| *Cisco Filtered* | *Last Ship Date, Routine Failure Analysis, Service Attachment* | *Collapsed* | Filtered to prevent redundant duplicate rows |
| **Check Point** | Generally Available | `Active` | Current production |
| **Check Point** | End of Sale (EOS) | `End of Sale` | Sales terminated |
| **Check Point** | End of Support (EOS) / End of Engineering | `End of Support` | Software updates ceased |
| **Check Point** | End of Life (EOL) | `Obsolete` | Total discontinuation |
| **Palo Alto Networks** | End of Sale (EoS) | `End of Sale` | Hardware order cutoff |
| **Palo Alto Networks** | End of Software Maintenance | `End of Support` | PAN-OS maintenance stops |
| **Palo Alto Networks** | End of Support (EoL) | `End of Support` | Customer TAC assistance stops |
| **Fortinet** | End of Order Date (EOO) / Last Time Buy (LTB) | `End of Sale` | Hardware order deadline |
| **Fortinet** | End of Standard Support (EOS) | `End of Support` | Bugfix updates terminated |
| **Fortinet** | End of Support (EOL) | `Obsolete` | Final hardware support end |
| **Extreme Networks** | End of Sale (EOS) | `End of Sale` | Hardware sales halted |
| **Extreme Networks** | End of Software Maintenance (EOSW) | `End of Support` | Maintenance patches stop |
| **Extreme Networks** | End of Service Life (EOSL) | `End of Support` | TAC & repair stops |
| **F5 Networks** | End of Sale (EoS) | `End of Sale` | BIG-IP platform order stop |
| **F5 Networks** | End of Software Development (EoSD) | `End of Support` | No new software updates |
| **F5 Networks** | End of Technical Support (EoTS) | `End of Support` | TAC assistance stops |
| **F5 Networks** | End of Life (EoL) | `Obsolete` | Archived platform |
| **Juniper Networks** | End of Life (EOL) Announced | `Phase Out` | Initial advance notice |
| **Juniper Networks** | End of Sale (EOS) | `End of Sale` | Hardware ordering stops |
| **Juniper Networks** | End of Engineering (EOE) | `End of Support` | Junos engineering fixes stop |
| **Juniper Networks** | End of Support (EOS) / End of Service Life | `End of Support` | Full TAC cutoff |
| **Dell Technologies** | Active / Available | `Active` | PowerEdge / PowerStore current |
| **Dell Technologies** | End of Sale (RTS End) | `End of Sale` | Ready-to-Ship cutoff |
| **Dell Technologies** | End of Standard Support | `End of Support` | Standard maintenance ends |
| **Dell Technologies** | End of Service Life (EOSL) | `Obsolete` | Post-standard support ends |
| **HPE / Aruba** | End of Sale (EOS) | `End of Sale` | ProLiant / Aruba order stop |
| **HPE / Aruba** | End of Support (EOS) | `End of Support` | Pointnext support ceases |
| **HPE / Aruba** | End of Life (EOL) | `Obsolete` | Total hardware retirement |
| **IBM Systems** | General Availability | `Active` | Current shipping systems |
| **IBM Systems** | End of Marketing (EOM) | `End of Sale` | Withdrawal from marketing |
| **IBM Systems** | End of Service (EOS) | `End of Support` | Defect support ends |

---

### 4.2 Operational Technology (OT) & Industrial Automation

| Vendor | Raw Vendor Terminology | Canonical Normalized Status | Notes |
|:---|:---|:---|:---|
| **Siemens** | PM300 (Delivery Release / Lieferfreigabe) | `Active` | Standard volume series delivery |
| **Siemens** | PM400 (Phase-out Product / Auslaufphase) | `Phase Out` | 1-year advance discontinuation notice |
| **Siemens** | PM410 (Product Cancellation / Typenstreichung) | `End of Sale` | Available only as spare part |
| **Siemens** | PM490 (Total Discontinuation / Totaler Produktauslauf) | `Obsolete` | Factory delivery ceased completely |
| **Siemens** | PM500 (End of Service & Spare Parts / Ersatzteilende) | `End of Support` | Hardware repairs and parts terminated |
| **Rockwell Automation** | Active | `Active` | Standard Allen-Bradley catalog item |
| **Rockwell Automation** | Active Mature | `Active Mature` | Fully supported, replacement family exists |
| **Rockwell Automation** | End of Life | `Phase Out` | Discontinuation date announced |
| **Rockwell Automation** | Discontinued | `Obsolete` | No longer manufactured or orderable |
| **ABB** | Active | `Active` | Complete lifecycle support & enhancement |
| **ABB** | Classic | `Active Mature` | Complete support, maintenance mode |
| **ABB** | Limited | `Phase Out` | Spare parts limited, migration advised |
| **ABB** | Obsolete | `Obsolete` | Best-effort support only |
| **Schneider Electric** | Commercialized | `Active` | Modicon / Harmony active catalog |
| **Schneider Electric** | End of Commercialization | `End of Sale` | Final sales milestone |
| **Schneider Electric** | End of Standard Support | `End of Support` | Software updates ceased |
| **Schneider Electric** | End of Service / Obsolete | `Obsolete` | Hardware support terminated |
| **Mitsubishi Electric** | Production | `Active` | MELSEC / MELSERVO standard supply |
| **Mitsubishi Electric** | Transition to Maintenance / NRND | `Phase Out` | Pre-discontinuation notification |
| **Mitsubishi Electric** | Production Discontinuation / Last Time Buy | `End of Sale` | Final factory manufacturing date |
| **Mitsubishi Electric** | Repair Period / Discontinued | `End of Support` | 7-year spare parts & repair window |
| **Mitsubishi Electric** | Repair Termination / EOL | `Obsolete` | Spare parts and repairs ceased |
| **Omron** | In Production / Standard Product | `Active` | Standard Sysmac delivery |
| **Omron** | Transition to Maintenance | `Phase Out` | Discontinuation announced |
| **Omron** | Discontinued | `Obsolete` | Production ceased |
| **Omron** | Maintenance / Repair End | `End of Support` | Repair service cutoff date |
| **WAGO** | In Production | `Active` | Standard catalog item |
| **WAGO** | Phase Out / Auslauftyp | `Phase Out` | Discontinuation announced |
| **WAGO** | Discontinued | `Obsolete` | Production terminated |
| **Phoenix Contact** | Current Series | `Active` | Standard production |
| **Phoenix Contact** | Product Discontinuation (PCN) | `Phase Out` | Advance notice with LTB date |
| **Phoenix Contact** | Discontinued | `Obsolete` | Production terminated |
| **Beckhoff** | In Production | `Active` | Standard availability |
| **Beckhoff** | Auslaufphase / Phasing Out | `Phase Out` | Successor available, LTB pending |
| **Beckhoff** | Abgekündigt / Discontinued | `Obsolete` | Discontinued |

---

### 4.3 Internet of Things (IoT) & Embedded Computing

| Vendor | Raw Vendor Terminology | Canonical Normalized Status |
|:---|:---|:---|
| **Advantech** | Active / In Production | `Active` |
| **Advantech** | Phased Out / EOL Announced | `Phase Out` |
| **Advantech** | End of Sale (EOS) / Last Time Buy | `End of Sale` |
| **Advantech** | Discontinued | `Obsolete` |
| **Moxa Technologies** | Active | `Active` |
| **Moxa Technologies** | Phased Out | `Phase Out` |
| **Moxa Technologies** | Discontinued | `Obsolete` |
| **STMicroelectronics** | Active | `Active` |
| **STMicroelectronics** | NRND (Not Recommended for New Designs) | `Active Mature` |
| **STMicroelectronics** | EOL Announced / Last Time Buy | `End of Sale` |
| **STMicroelectronics** | Discontinued | `Obsolete` |
| **Texas Instruments** | ACTIVE | `Active` |
| **Texas Instruments** | NRND | `Active Mature` |
| **Texas Instruments** | LIFEBUY / LAST TIME BUY | `End of Sale` |
| **Texas Instruments** | OBSOLETE | `Obsolete` |
| **NXP Semiconductors** | In Production | `Active` |
| **NXP Semiconductors** | No Recommended for New Designs | `Active Mature` |
| **NXP Semiconductors** | End of Life (EOL) | `Obsolete` |

---

### 4.4 Operating Systems & Enterprise Software

| Vendor / OS | Raw Vendor Terminology | Canonical Normalized Status |
|:---|:---|:---|
| **Apple** | Supported | `Active` |
| **Apple** | Vintage (5 to 7 years after sale stop) | `Active Mature` |
| **Apple** | Obsolete (> 7 years after sale stop) | `Obsolete` |
| **Microsoft Windows** | General Availability | `Active` |
| **Microsoft Windows** | Mainstream Support End Date | `Active Mature` |
| **Microsoft Windows** | Extended Support End Date | `End of Support` |
| **Red Hat Enterprise Linux** | Full Support Phase | `Active` |
| **Red Hat Enterprise Linux** | Maintenance Support Phase | `Active Mature` |
| **Red Hat Enterprise Linux** | Extended Life Phase (ELP) | `End of Support` |
| **Red Hat Enterprise Linux** | End of Life (EOL) | `Obsolete` |
| **Ubuntu / Canonical** | Standard Support (LTS) | `Active` |
| **Ubuntu / Canonical** | End of Standard Support | `Active Mature` |
| **Ubuntu / Canonical** | End of Extended Security Maintenance (ESM) | `End of Support` |

---

## 5. Deduplication Invariant & Latest Date Retention Rule

### 5.1 Strict Uniqueness Invariant
> **Invariant**: For each normalized canonical status, there must be **strictly ONE record per `(vendor_name, model_name, canonical_status)` combination**.

The fingerprint hash is computed deterministically:
$$\text{Fingerprint} = \text{SHA-256}(\text{UPPER}(\text{vendor}) \parallel \text{UPPER}(\text{model or os}) \parallel \text{UPPER}(\text{canonical\_status}))[:16]$$

### 5.2 Latest Date Retention Algorithm
When an incoming record collides on the same `Fingerprint`:
1. **Timestamp Comparison**: If both records have valid ISO dates, the record with the newer (latest) UTC date is unconditionally chosen as the winner.
2. **Missing Date Resolution**: A record with an authentic lifecycle date always wins over a record with no date or a fallback date.
3. **Lossless Attribute Merge**: If the older (loser) record contains non-empty attributes (`replacement`, `aliases`, `os`, `firmware`, `source_url`, `category`) that are blank on the winner, they are merged into the winner.
4. **Active/EOL Mutual Exclusivity**: If a product enters an EOL milestone (`Phase Out`, `End of Sale`, `End of Support`, `Obsolete`), any legacy placeholder in `output/active_products_lifecycle.csv` is pruned.

