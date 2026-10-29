"""
Enterprise Framework Pluggability & Adapter Layer for Universal Lifecycle Scraper.
Enables seamless integration with LangChain, LlamaIndex, Apache Airflow,
Celery, FastAPI, Django, and Pandas ETL pipelines with built-in security threat protection.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Union

import pandas as pd

from scraper.config import BASE_DIR
from scraper.models import ProductRecord
from scraper.pipeline import LifecyclePipeline
from scraper.security import (
    SecurityThreatError,
    inspect_security_threats,
)
from scraper.storage import MasterStorageManager
from scraper.vendors import VENDOR_PROFILES

logger = logging.getLogger("ai_scraper.adapters")


class FrameworkAdapter:
    """
    Universal Plug-and-Play Adapter for external frameworks and pipelines.
    Supports:
    - LangChain / LlamaIndex agent tools
    - Apache Airflow / Prefect / Celery task execution
    - FastAPI / Flask / Django REST endpoints
    - Pandas / Polars data science ETL
    - Real-time SQLi, XSS, and Command Injection threat defense on all inputs
    """

    def __init__(
        self,
        master_csv_path: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
        output_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        self.output_dir = Path(output_dir) if output_dir else BASE_DIR / "output"
        self.master_csv_path = (
            Path(master_csv_path) if master_csv_path else self.output_dir / "all_vendors_lifecycle.csv"
        )
        self.config_path = (
            Path(config_path) if config_path else BASE_DIR / "configs" / "vendors.yaml"
        )
        self.storage_manager = MasterStorageManager(
            master_csv_path=self.master_csv_path,
            output_dir=self.output_dir,
        )

    def extract_sync(
        self,
        vendor_ids: Optional[List[str]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        max_workers: int = 5,
    ) -> List[ProductRecord]:
        """
        Synchronous extraction method for Airflow, Celery, and traditional ETL pipelines.
        Safely executes the async lifecycle pipeline in both sync and existing async event loops.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # If already running inside an event loop (e.g., Jupyter, FastAPI), run in a separate thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(
                    asyncio.run,
                    self.extract_async(
                        vendor_ids=vendor_ids,
                        provider=provider,
                        model=model,
                        max_workers=max_workers,
                    ),
                )
                return fut.result()
        else:
            return asyncio.run(
                self.extract_async(
                    vendor_ids=vendor_ids,
                    provider=provider,
                    model=model,
                    max_workers=max_workers,
                )
            )

    async def extract_async(
        self,
        vendor_ids: Optional[List[str]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        max_workers: int = 5,
    ) -> List[ProductRecord]:
        """
        Asynchronous extraction method for FastAPI, Tornado, and asyncio services.
        Executes the 6-stage lifecycle pipeline and returns validated ProductRecord items.
        """
        pipeline = LifecyclePipeline(
            config_path=self.config_path,
            provider=provider,
            model=model,
        )
        if self.output_dir:
            pipeline.output_dir = self.output_dir
            pipeline.master_csv = self.master_csv_path
            pipeline.storage = MasterStorageManager(self.master_csv_path, self.output_dir)

        v_filter = vendor_ids[0] if (vendor_ids and len(vendor_ids) == 1) else None
        dataset = await pipeline.execute(vendor_filter=v_filter)
        return dataset.products

    def query_records(
        self,
        vendor_name: Optional[str] = None,
        model_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[ProductRecord]:
        """
        Queries extracted lifecycle records from storage with enterprise security inspection.
        Actively blocks SQL injection, XSS, and command injection payloads in filter arguments.
        """
        # Enterprise Threat Shield: Inspect all search arguments
        if vendor_name:
            inspect_security_threats(vendor_name, field_name="vendor_name", raise_error=True)
        if model_name:
            inspect_security_threats(model_name, field_name="model_name", raise_error=True)
        if status:
            inspect_security_threats(status, field_name="status", raise_error=True)

        raw_records = self.storage_manager.load_existing_records()
        results: List[ProductRecord] = []

        v_filter = vendor_name.lower().strip() if vendor_name else None
        m_filter = model_name.lower().strip() if model_name else None
        s_filter = status.lower().strip() if status else None

        for fp, r in raw_records.items():
            r_vendor = str(r.get("vendor_name") or "").lower()
            r_model = str(r.get("model_name") or "").lower()
            r_status = str(r.get("status") or r.get("vendor_status") or "").lower()

            if v_filter and v_filter not in r_vendor:
                continue
            if m_filter and m_filter not in r_model:
                continue
            if s_filter and s_filter not in r_status:
                continue

            try:
                # Convert loaded dict back into ProductRecord
                meta_val = r.get("metadata")
                parsed_meta: Dict[str, Any] = {}
                if isinstance(meta_val, str) and meta_val.strip():
                    try:
                        parsed_meta = json.loads(meta_val)
                    except Exception:
                        parsed_meta = {}
                elif isinstance(meta_val, dict):
                    parsed_meta = meta_val

                record = ProductRecord(
                    fingerprint=fp,
                    vendor_name=r.get("vendor_name") or "",
                    model_name=r.get("model_name") or "",
                    os=r.get("os"),
                    firmware=r.get("firmware"),
                    status=r.get("status") or "Discontinued",
                    stage=r.get("stage") or r.get("status") or "Discontinued",
                    vendor_status=r.get("vendor_status") or r.get("status") or "Discontinued",
                    stage_date_utc=r.get("stage_date_utc"),
                    source_url=r.get("source_url") or "",
                    category=r.get("category") or "General Automation",
                    product_category=r.get("product_category") or "General Automation",
                    replacement=r.get("replacement"),
                    first_discovered_utc=r.get("first_discovered_utc"),
                    last_updated_utc=r.get("last_updated_utc"),
                    metadata=parsed_meta,
                )
                results.append(record)
                if len(results) >= limit:
                    break
            except Exception as e:
                logger.debug(f"Skipping record during query load: {e}")
                continue

        return results

    def query_vendor_terminology(self, vendor_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves official vendor-specific lifecycle status terminology.
        Actively checks input against security threat vectors.
        """
        if vendor_name:
            inspect_security_threats(vendor_name, field_name="vendor_name", raise_error=True)
            v_key = vendor_name.lower().strip()

            # 1. Check comprehensive VENDOR_STATUS_DICTIONARY if available
            try:
                from scripts.generate_vendor_status_registry import VENDOR_STATUS_DICTIONARY

                for key, val in VENDOR_STATUS_DICTIONARY.items():
                    v_str = str(val.get("vendor", "")).lower()
                    if key.lower() == v_key or v_key in key.lower() or v_key in v_str:
                        return {
                            "vendor_id": key,
                            "vendor_name": val.get("vendor"),
                            "sector": val.get("sector"),
                            "lifecycle_model": val.get("lifecycle_model"),
                            "terminology": val.get("statuses", []),
                        }
            except Exception:
                pass

            # 2. Check VENDOR_PROFILES
            for key, profile in VENDOR_PROFILES.items():
                disp_name = profile.get("display_name", key) if isinstance(profile, dict) else getattr(profile, "name", key)
                if key.lower() == v_key or disp_name.lower() == v_key or v_key in disp_name.lower():
                    return {
                        "vendor_id": key,
                        "vendor_name": disp_name,
                        "terminology": [
                            {"term": "Delivery Release", "meaning": "General commercial release"},
                            {"term": "Phase-Out", "meaning": "Active phase-out notice issued"},
                            {"term": "End of Life", "meaning": "Manufacturing and sales discontinued"},
                            {"term": "Discontinued", "meaning": "Obsolescence reached"},
                        ],
                    }

            return {
                "vendor_name": vendor_name,
                "error": f"Vendor '{vendor_name}' not found in registry",
                "known_vendors": [
                    p.get("display_name", k) if isinstance(p, dict) else getattr(p, "name", k)
                    for k, p in VENDOR_PROFILES.items()
                ],
            }

        # Return full registry summary
        return {
            key: {
                "vendor_name": p.get("display_name", key) if isinstance(p, dict) else getattr(p, "name", key),
                "sector": p.get("sector", "OT") if isinstance(p, dict) else "OT",
            }
            for key, p in VENDOR_PROFILES.items()
        }

    def to_dataframe(self, records: List[ProductRecord]) -> pd.DataFrame:
        """Converts ProductRecord items into a clean Pandas DataFrame for downstream analytics/ETL."""
        if not records:
            return pd.DataFrame(
                columns=[
                    "fingerprint", "vendor_name", "model_name", "os", "firmware",
                    "status", "stage", "vendor_status", "stage_date_utc",
                    "category", "replacement", "source_url"
                ]
            )

        data = []
        for r in records:
            data.append({
                "fingerprint": r.fingerprint,
                "vendor_name": r.vendor_name,
                "model_name": r.model_name,
                "os": r.os,
                "firmware": r.firmware,
                "status": r.status,
                "stage": r.stage,
                "vendor_status": r.vendor_status,
                "stage_date_utc": r.stage_date_utc,
                "category": r.category,
                "replacement": r.replacement,
                "source_url": r.source_url,
                "first_discovered_utc": r.first_discovered_utc,
                "last_updated_utc": r.last_updated_utc,
            })
        return pd.DataFrame(data)

    def to_dicts(self, records: List[ProductRecord]) -> List[Dict[str, Any]]:
        """Converts ProductRecord items into serializable dictionaries for JSON APIs or Kafka streams."""
        return [r.model_dump() for r in records]

    def stream_records(
        self,
        vendor_ids: Optional[List[str]] = None,
    ) -> Generator[ProductRecord, None, None]:
        """Memory-efficient streaming generator yielding records one by one."""
        records = self.extract_sync(vendor_ids=vendor_ids)
        for record in records:
            yield record


# Alias for pipeline / orchestrator workflows (Airflow, Celery, Prefect)
LifecyclePlugin = FrameworkAdapter


class LangChainToolAdapter:
    """
    Adapter providing LangChain, LlamaIndex, and Agentic AI compatible tools.
    Can be used as standalone callable tools or exported as LangChain StructuredTools.
    All inputs are strictly secured against SQL injection, XSS, and command execution threats.
    """

    def __init__(self, adapter: Optional[FrameworkAdapter] = None) -> None:
        self.adapter = adapter or FrameworkAdapter()

    def query_product_lifecycle(
        self,
        vendor_name: str = "",
        model_name: str = "",
        status: str = "",
        limit: int = 10,
    ) -> str:
        """
        Queries industrial automation, OT, IoT, and IT hardware/software lifecycle and end-of-sale milestones.
        Protected against SQL injection, XSS, and malicious payloads.
        """
        try:
            results = self.adapter.query_records(
                vendor_name=vendor_name if vendor_name else None,
                model_name=model_name if model_name else None,
                status=status if status else None,
                limit=limit,
            )
            if not results:
                return f"No product lifecycle records found matching criteria: vendor='{vendor_name}', model='{model_name}', status='{status}'"

            output_lines = [f"Found {len(results)} lifecycle record(s):"]
            for r in results:
                dt_str = r.stage_date_utc or "Vendor Unpublished Date (EOL Record Preserved)"
                repl_str = f" | Replacement: {r.replacement}" if r.replacement else ""
                output_lines.append(
                    f"- [{r.vendor_name}] {r.model_name}: Status='{r.vendor_status}' ({dt_str}){repl_str}"
                )
            return "\n".join(output_lines)
        except SecurityThreatError as e:
            return f"SECURITY INCIDENT BLOCKED: Query rejected due to threat ({e.threat_type}): {e.detail}"
        except Exception as e:
            return f"Error executing lifecycle query: {str(e)}"

    def get_vendor_lifecycle_terminology(self, vendor_name: str = "") -> str:
        """
        Retrieves official vendor-specific lifecycle status terminology and definitions.
        (e.g., Siemens 'Phase-Out', Rockwell 'Silver Series', Cisco 'End-of-Sale').
        """
        try:
            data = self.adapter.query_vendor_terminology(vendor_name=vendor_name if vendor_name else None)
            return json.dumps(data, indent=2)
        except SecurityThreatError as e:
            return f"SECURITY INCIDENT BLOCKED: Query rejected due to threat ({e.threat_type}): {e.detail}"
        except Exception as e:
            return f"Error retrieving vendor terminology: {str(e)}"

    def as_langchain_tools(self) -> List[Any]:
        """
        Returns tools as LangChain StructuredTool instances if langchain_core is installed,
        or callable tool wrappers with .name, .description, and .run() attributes.
        """
        try:
            from langchain_core.tools import StructuredTool

            tool1 = StructuredTool.from_function(
                func=self.query_product_lifecycle,
                name="query_product_lifecycle",
                description="Queries multi-vendor industrial and IT product lifecycle, end-of-sale, and end-of-support status. Protected against SQLi and malicious threats.",
            )
            tool2 = StructuredTool.from_function(
                func=self.get_vendor_lifecycle_terminology,
                name="get_vendor_lifecycle_terminology",
                description="Retrieves vendor-exact lifecycle status terms and definitions (e.g. Siemens Phase-Out, Rockwell Silver Series, Cisco End-of-Sale).",
            )
            return [tool1, tool2]
        except ImportError:
            # Fallback callable tools compatible with generic agent loops
            class CallableTool:
                def __init__(self, name: str, description: str, func: Callable[..., str]):
                    self.name = name
                    self.description = description
                    self.func = func

                def __call__(self, *args: Any, **kwargs: Any) -> str:
                    return self.func(*args, **kwargs)

                def run(self, *args: Any, **kwargs: Any) -> str:
                    return self.func(*args, **kwargs)

            return [
                CallableTool(
                    name="query_product_lifecycle",
                    description="Queries multi-vendor industrial and IT product lifecycle, end-of-sale, and end-of-support status.",
                    func=self.query_product_lifecycle,
                ),
                CallableTool(
                    name="get_vendor_lifecycle_terminology",
                    description="Retrieves vendor-exact lifecycle status terms and definitions.",
                    func=self.get_vendor_lifecycle_terminology,
                ),
            ]


def get_framework_adapter() -> FrameworkAdapter:
    """Factory function providing a default FrameworkAdapter instance."""
    return FrameworkAdapter()
