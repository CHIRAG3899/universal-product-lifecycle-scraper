# Operational Workflows & Execution Flows

## 1. End-to-End Crawl & Ingestion Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Operator as CLI / Automation
    participant Pipeline as LifecyclePipeline
    participant Auditor as EndpointAuditor
    participant Crawler as UniversalAICrawler
    participant Strategy as ScrapingStrategy
    participant AI as UniversalAIExtractor
    participant Storage as MasterStorageManager
    participant CSVs as Dual-CSV Storage

    Operator->>Pipeline: execute_pipeline(vendor_id)
    Pipeline->>Auditor: audit_endpoint(entry_point)
    Auditor-->>Pipeline: health_status (HTTP / Browser recommended)
    Pipeline->>Crawler: crawl(url, mode)
    Crawler->>Strategy: execute(entry_point, vendor_cfg)
    alt Tabular / Card Content Discovered
        Strategy->>AI: extract_products(html_or_markdown)
        AI-->>Strategy: List[ProductRecord]
    else PDF Bulletin Linked
        Strategy->>Crawler: fetch_pdf_bytes(pdf_url)
        Strategy->>AI: parse_pdf_table(pdf_bytes)
        AI-->>Strategy: List[ProductRecord] (discontinued + replacements)
    end
    Strategy-->>Pipeline: List[ProductRecord]
    Pipeline->>AI: verify_and_filter_records_with_llm(candidate_records)
    Note over AI,Pipeline: Validates genuine models, authentic status, strips leaks
    AI-->>Pipeline: List[ProductRecord] (Verified & Clean)
    Pipeline->>Storage: upsert_and_persist(verified_records)
    Storage->>Storage: filter_and_deduplicate()
    Storage->>CSVs: write eol_products_lifecycle.csv
    Storage->>CSVs: write active_products_lifecycle.csv
    Storage-->>Pipeline: (total, new_appended, updated)
    Pipeline-->>Operator: Execution Summary & Batch Metrics
```

---

## 2. Product Record Sanitization & Validation Flow

```mermaid
flowchart TD
    Raw["Raw Extracted Candidate<br/>(from LLM, DOM, or Table)"] --> S0["inspect_security_threats()<br/>(Check for SQLi, XSS, Path Traversal)"]
    S0 -- Threat Detected --> Drop["Drop & Record Security Violation"]
    S0 -- Clean --> S1["is_valid_product_model(model_name)"]
    
    S1 -- Fails (e.g. '3-phase', 'terms', 'privacy') --> Drop
    S1 -- Passes --> S2["sanitize_alias_string(aliases)"]
    
    S2 --> S2A{"Contains Date Pattern<br/>or Boilerplate?"}
    S2A -- Yes (e.g. 'April 30 - 2026') --> S2B["Strip Date / Boilerplate"]
    S2A -- No --> S2C["Retain Clean Aliases (e.g. 'MELIPC series')"]
    
    S2B --> S3["sanitize_replacement_string(replacement)"]
    S2C --> S3
    
    S3 --> S3A{"Is Authentic Successor Model?<br/>(is_valid_replacement_model)"}
    S3A -- No (e.g. 'Contact Sales') --> S3B["Set replacement = ''"]
    S3A -- Yes (e.g. 'NZ2GN2B-60AD4') --> S3C["Retain replacement SKU"]
    
    S3B --> S4["Validate stage_date_utc"]
    S3C --> S4
    
    S4 --> S4A{"Date Stated by Vendor?"}
    S4A -- Yes --> S4B["Normalize to UTC ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)"]
    S4A -- No --> S4C["Set stage_date_utc = '' and missing_date = true"]
    
    S4B --> S5["Compute SHA-256 Fingerprint"]
    S4C --> S5
    
    S5 --> S6{"is_eol_status(status)"}
    S6 -- True (Discontinued, EOL, LTB, Phase-out) --> EOL["Route to eol_products_lifecycle.csv"]
    S6 -- False (Active, Supported, Available) --> ACT["Route to active_products_lifecycle.csv"]
```

---

## 3. Knowledge Base Synchronization & Batch Queueing Flow

```mermaid
stateDiagram-v2
    [*] --> Discovered: Entry Point Invoked
    Discovered --> KB_Sync: Discover Child Sitemaps / Pages
    KB_Sync --> In_Queue: Add Unseen URLs to Pending Queue
    In_Queue --> Processing: Ingest Batch (N units)
    Processing --> Verified: Extraction & Sanitization
    Verified --> Completed: Mark Completed in State
    Processing --> Failure_DLQ: Network / Parse Error
    Failure_DLQ --> DeadLetterQueue: DLQ Record Stored
    Completed --> In_Queue: Next Batch Available
    Completed --> Cycle_Complete: All Queue Items Finished
    Cycle_Complete --> [*]: Cycle Increment & Artifact Generation
```

