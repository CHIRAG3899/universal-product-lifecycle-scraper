# Enterprise Canonical Status Normalization & Deduplication Specification

## 1. Executive Summary

Enterprise equipment lifecycle management requires harmonizing disparate, multi-lingual, and vendor-proprietary milestone terminology across more than 219 industrial OT, IoT, IoMT, and IT manufacturers into a structured, deterministic lifecycle taxonomy.

This document formalizes:
1. The **6 Canonical ENUM Statuses** recognized by the framework.
2. The **Multi-Lingual Normalization Matrix** spanning English, German, Japanese, Chinese, French, Swedish, Spanish, and Italian.
3. The **Vendor-by-Vendor Terminology Mapping** across key enterprise manufacturers.
4. The **Canonical Deduplication Invariant & Latest Date Retention Rule** (Mandates 11 & 12).
5. The **Dual CSV Segmentation Standard** (`eol_products_lifecycle.csv` vs `active_products_lifecycle.csv`).

---

## 2. The 6 Canonical Lifecycle ENUM Statuses

Every vendor-specific raw status string is normalized into one of six strictly typed canonical values defined in `CanonicalStatus(str, Enum)`:

```
[ Active ] ──────> [ Active Mature ] ──────> [ Phase Out ] ──────> [ End of Sale ] ──────> [ End of Support ] ──────> [ Obsolete ]
  Orderable          Active but NRND           Announced EOL          Last Time Buy           No Bugfixes/Patches      End of Service
  Full Production    Sustaining Only           Transition Period      Order Stop              No Hardware Repairs      Historical / Scrap
```

| Canonical Status | ENUM Key | Category | Lifecycle Milestone Meaning | Typical Vendor Terms |
| :--- | :--- | :--- | :--- | :--- |
| **`Active`** | `CanonicalStatus.ACTIVE` | Active | Fully supported, actively produced, standard catalog availability. | Active, Current, Regular Availability, In Production, General Availability (GA), Orderable, Series Delivery. |
| **`Active Mature`** | `CanonicalStatus.ACTIVE_MATURE` | Active | Active and orderable, but Not Recommended for New Designs (NRND). Sustaining production only. | Mature, Active Mature, NRND, Classic (Siemens/ABB), Limited, Sustaining, Post-Production, Maintenance Only. |
| **`Phase Out`** | `CanonicalStatus.PHASE_OUT` | EOL | Formal discontinuation announcement issued. Migration to successor models recommended before order cutoff. | Phase-Out, Auslauftyp (German), Retiring, Announced EOL, Pending Discontinuation, Vorabkündigung. |
| **`End of Sale`** | `CanonicalStatus.END_OF_SALE` | EOL | Final purchase milestone reached. No new orders accepted after this date (Last Time Buy). | End of Sale (EOS), Last Time Buy (LTB), Final Order Date, Order Stop, Verkaufsstopp, End-of-Build, Stop Shipment. |
| **`End of Support`** | `CanonicalStatus.END_OF_SUPPORT` | EOL | Software patches, security vulnerability fixes, engineering support, and warranty repairs cease. | End of Support (EOS), End of Service Life (EOSL), End of Maintenance (EOM), LDOS, Support Ends, Ersatzteilende. |
| **`Obsolete`** | `CanonicalStatus.OBSOLETE` | EOL | Product is completely discontinued, unsupported, unrepairable, and archived. | Discontinued, Obsolete, End of Life (EOL), Vintage, Retired, Produktabkündigung (German), 生産終了 (Japanese). |

---

## 3. Multi-Lingual Canonical Normalization Matrix

The framework incorporates automatic regional translation and keyword tokenization across global manufacturer portals:

### 3.1 German Portals (Siemens, Phoenix Contact, WAGO, Beckhoff, Festo, SEW)
| German Term | Canonical ENUM Status | Semantic Significance |
| :--- | :--- | :--- |
| `Lieferfreigabe` / `Serienlieferung` | `Active` | Delivery release / Standard volume series delivery |
| `Reifephase` / `Klassik` | `Active Mature` | Mature production phase / Classic maintenance |
| `Auslauftyp` / `Auslaufphase` | `Phase Out` | Phase-out product / Withdrawal announced |
| `Vorabkündigung` / `Abkündigung angekündigt` | `Phase Out` | Advance notice of discontinuation |
| `Letzte Bestellmöglichkeit` | `End of Sale` | Final ordering opportunity (Last Time Buy) |
| `Verkaufsstopp` / `Bestellstopp` | `End of Sale` | Sales halt / Ordering cutoff |
| `Einstellung der Reparatur` | `End of Support` | Discontinuation of hardware repair services |
| `Ersatzteilende` / `Wartungsende` | `End of Support` | End of spare parts supply / End of maintenance |
| `Produktabkündigung` / `Abkündigung` | `Obsolete` | Formal product discontinuation (EOL) |
| `Eingestellt` / `Lieferstopp` | `Obsolete` | Discontinued / Delivery terminated |

### 3.2 Japanese Portals (Mitsubishi Electric, Omron, Fanuc, Keyence, Yokogawa)
| Japanese Term | Canonical ENUM Status | Semantic Significance |
| :--- | :--- | :--- |
| `販売中` / `標準品` | `Active` | Currently on sale / Standard catalog product |
| `推奨代替品あり` / `縮小生産` | `Active Mature` | Reduced production / Substitute recommended |
| `生産終了予告` | `Phase Out` | Production termination notice / Advance EOL |
| `最終注文受付` / `最終受注日` | `End of Sale` | Final order receipt date (Last Time Buy) |
| `修理対応終了` / `保守終了` | `End of Support` | Hardware repair support termination / End of maintenance |
| `生産終了` / `販売終了` | `Obsolete` | Production terminated / Sales discontinued (Obsolete) |

### 3.3 French, Swedish, Spanish, and Chinese Terminology
| Term | Language | Canonical ENUM Status |
| :--- | :--- | :--- |
| `En vente` / `Disponible` | French | `Active` |
| `Fin de vente` | French | `End of Sale` |
| `Fin de support` / `Fin de service` | French | `End of Support` |
| `Produit obsolète` / `Arrêt de commercialisation` | French | `Obsolete` |
| `Utgått sortiment` / `Slutat säljas` | Swedish | `Obsolete` |
| `Discontinuado` / `Obsoleto` | Spanish | `Obsolete` |
| `现货/在产` | Chinese | `Active` |
| `停止销售` | Chinese | `End of Sale` |
| `停止技术支持` | Chinese | `End of Support` |
| `淘汰` / `完全停产` | Chinese | `Obsolete` |

---

## 4. Vendor-by-Vendor Terminology Mapping

### 4.1 Siemens AG (SIMATIC, SINAMICS, SCALANCE, Desigo)
Siemens structures product lifecycles according to distinct Product Milestone (PM) numbers:
- **PM300 (Delivery Release)**: `Active`
- **PM400 (Phase-out Announcement)**: `Phase Out`
- **PM410 (Order Stop / Discontinuation)**: `End of Sale`
- **PM490 (End of Spare Parts / Total Discontinuation)**: `Obsolete`

### 4.2 Rockwell Automation / Allen-Bradley (ControlLogix, CompactLogix, PanelView)
Rockwell publishes 4 official lifecycle stages:
- **Active**: `Active` (Standard catalog item)
- **Active Mature**: `Active Mature` (Fully supported, but newer family recommended)
- **End of Life**: `Phase Out` (Discontinuation date announced; LTB pending)
- **Discontinued**: `Obsolete` (No longer manufactured or orderable)

### 4.3 Cisco Systems (Catalyst, Nexus, ISR, Secure Firewall)
Cisco follows a rigorous 5-milestone hardware & software EOL policy:
- **General Availability (GA)**: `Active`
- **End of Sale (EOS) / Last Time Buy (LTB)**: `End of Sale`
- **End of SW Maintenance Releases**: `End of Support`
- **End of Vulnerability & Security Support**: `End of Support`
- **Last Date of Support (LDOS)**: `Obsolete`

### 4.4 ABB (Robotics, DCS 800xA, Variable Speed Drives)
ABB operates a 4-phase lifecycle model:
- **Active**: `Active`
- **Classic**: `Active Mature` (Complete lifecycle support, limited enhancements)
- **Limited**: `Active Mature` / `Phase Out` (Limited spare parts, repair only)
- **Obsolete**: `Obsolete` (Spare parts available only on best-effort basis)

### 4.5 Schneider Electric (Modicon, Harmony, TeSys, EcoStruxure)
- **Commercialized**: `Active`
- **End of Commercialization**: `End of Sale`
- **End of Standard Service**: `End of Support`
- **Obsolete**: `Obsolete`

### 4.6 Mitsubishi Electric (MELSEC, GOT, MELSERVO)
- **Production**: `Active`
- **Transition / NRND**: `Active Mature`
- **Last Time Buy (LTB)**: `End of Sale`
- **Discontinued (Repair Period)**: `End of Support`
- **Repair Termination / EOL**: `Obsolete`

---

## 5. Deduplication Invariant & Latest Date Retention Rule

### 5.1 Mandate 11 & 12 Invariant
> **Strict Invariant**: For each normalized canonical status, there must be **strictly ONE record per `(vendor_name, model_name, canonical_status)` combination**.

When multiple crawl sources, bulletins, or regional feeds yield duplicate records for the same product and canonical status:
1. **Latest Date Retention**: The framework compares the `stage_date_utc` timestamps. The record with the newer (latest) UTC date is unconditionally retained as the canonical representative.
2. **Lossless Attribute Merging**: If the older (loser) record contains non-empty attributes (e.g. `replacement`, `aliases`, `os`, `firmware`, `source_url`, or detailed `metadata`) while the winner has empty fields, the loser's attributes are merged into the winner.
3. **Deterministic Fingerprinting**:
   $$\text{Fingerprint} = \text{SHA-256}(\text{VENDOR} \parallel \text{MODEL} \parallel \text{CANONICAL\_STATUS})[:16]$$
   This guarantees idempotence across incremental crawls, SQLite staging, and consolidated CSV exports.

---

## 6. Dual CSV Segmentation Standard

Per architecture standards, the deprecated `all_vendors_lifecycle.csv` is eliminated. Records are strictly partitioned into two 11-column SQL datasets:

1. **`output/eol_products_lifecycle.csv`**:
   - Contains records where `canonical_status` is in `{"Phase Out", "End of Sale", "End of Support", "Obsolete"}`.
2. **`output/active_products_lifecycle.csv`**:
   - Contains records where `canonical_status` is in `{"Active", "Active Mature"}`.
   - If a product model enters an EOL milestone, any legacy active placeholder is automatically pruned to prevent conflicting entries.
