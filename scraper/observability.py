"""
Enterprise Observability & Alerting Module.
Collects pipeline operational metrics, computes data quality health scores,
detects urgent procurement deadlines (impending LTB windows), and dispatches alerts.
"""

import json
import logging
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from scraper.models import ProductRecord

logger = logging.getLogger("ai_scraper.observability")


class PipelineMetricsCollector:
    """
    Collects execution metrics, calculates data quality scores,
    and identifies critical lifecycle events.
    """

    def __init__(self, run_id: str, alert_ltb_days: int = 90):
        self.run_id = run_id
        self.alert_ltb_days = alert_ltb_days
        self.start_time = datetime.now(timezone.utc)
        self.end_time: Optional[datetime] = None
        self.errors: List[str] = []
        self.vendor_stats: Dict[str, Dict[str, Any]] = {}

    def record_vendor_result(
        self,
        vendor_name: str,
        record_count: int,
        duration_sec: float,
        error: Optional[str] = None
    ):
        self.vendor_stats[vendor_name] = {
            "records": record_count,
            "duration_seconds": round(duration_sec, 2),
            "status": "FAILED" if error else "SUCCESS",
            "error": error
        }
        if error:
            self.errors.append(f"[{vendor_name}] {error}")

    def compute_metrics(
        self,
        all_products: List[ProductRecord],
        new_appended: int,
        refreshed_existing: int
    ) -> Dict[str, Any]:
        """Calculates comprehensive operational and quality metrics."""
        self.end_time = datetime.now(timezone.utc)
        duration = (self.end_time - self.start_time).total_seconds()
        now_dt = datetime.now(timezone.utc)
        ltb_threshold_dt = now_dt + timedelta(days=self.alert_ltb_days)

        # 1. Lifecycle Stage Distribution
        ltb_records = []
        eol_count = 0
        eos_count = 0
        discontinued_count = 0

        # Urgent LTB notices (impending within threshold days)
        urgent_ltb_alerts = []

        # 2. Quality Metrics
        valid_utc_dates = 0
        firmware_cleaned = 0
        metadata_populated = 0

        for p in all_products:
            stg_lower = p.stage.lower()
            if "last time buy" in stg_lower or "ltb" in stg_lower:
                ltb_records.append(p)
                # Check for urgency
                if p.stage_date_utc:
                    try:
                        p_dt = datetime.fromisoformat(p.stage_date_utc.replace("Z", "+00:00"))
                        if now_dt <= p_dt <= ltb_threshold_dt:
                            days_remaining = (p_dt - now_dt).days
                            urgent_ltb_alerts.append({
                                "vendor": p.vendor_name,
                                "model": p.model_name,
                                "stage_date_utc": p.stage_date_utc,
                                "days_remaining": days_remaining,
                                "replacement": p.metadata.get("replacement", "Consult Representative"),
                                "bulletin": p.metadata.get("bulletin_title", "N/A")
                            })
                    except Exception:
                        pass
            elif "end of life" in stg_lower or "eol" in stg_lower:
                eol_count += 1
            elif "end of service" in stg_lower or "eos" in stg_lower:
                eos_count += 1
            else:
                discontinued_count += 1

            if p.stage_date_utc and p.stage_date_utc.endswith("Z"):
                valid_utc_dates += 1
            if p.firmware and p.firmware != "N/A":
                firmware_cleaned += 1
            if p.metadata and len(p.metadata) >= 4:
                metadata_populated += 1

        total = len(all_products)
        quality_score = round((valid_utc_dates / total * 100), 1) if total > 0 else 0.0

        # Determine overall pipeline status
        status = "HEALTHY"
        if self.errors:
            status = "DEGRADED" if total > 0 else "CRITICAL_FAILURE"
        elif len(urgent_ltb_alerts) > 0:
            status = "ACTION_REQUIRED"

        metrics = {
            "run_id": self.run_id,
            "pipeline_status": status,
            "start_time_utc": self.start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_time_utc": self.end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_seconds": round(duration, 2),
            "volumes": {
                "total_records_ingested": total,
                "new_records_appended": new_appended,
                "existing_records_refreshed": refreshed_existing,
                "vendors_processed": len(self.vendor_stats),
                "vendors_succeeded": sum(1 for v in self.vendor_stats.values() if v["status"] == "SUCCESS"),
                "vendors_failed": sum(1 for v in self.vendor_stats.values() if v["status"] == "FAILED")
            },
            "stage_breakdown": {
                "last_time_buy_count": len(ltb_records),
                "end_of_life_count": eol_count,
                "end_of_service_count": eos_count,
                "other_discontinued_count": discontinued_count
            },
            "procurement_alerts": {
                "urgent_ltb_window_days": self.alert_ltb_days,
                "urgent_ltb_count": len(urgent_ltb_alerts),
                "urgent_items": urgent_ltb_alerts[:15]  # Top 15 urgent deadlines
            },
            "data_quality": {
                "utc_date_coverage_pct": quality_score,
                "metadata_coverage_pct": round((metadata_populated / total * 100), 1) if total > 0 else 0.0,
                "semantic_firmware_count": firmware_cleaned
            },
            "errors": self.errors,
            "vendor_details": self.vendor_stats
        }

        return metrics


class AlertDispatcher:
    """
    Dispatches alerts to Slack, Microsoft Teams, Webhooks, and Terminal.
    """

    @staticmethod
    def format_alert_text(metrics: Dict[str, Any]) -> str:
        """Formats alert digest into high-visibility text message."""
        status = metrics["pipeline_status"]
        volumes = metrics["volumes"]
        stages = metrics["stage_breakdown"]
        alerts = metrics["procurement_alerts"]
        quality = metrics["data_quality"]

        status_icon = "[OK]" if status == "HEALTHY" else ("[ACTION REQUIRED]" if status == "ACTION_REQUIRED" else "[CRITICAL]")

        lines = [
            f"{status_icon} [LIFECYCLE PIPELINE ALERT] Status: {status} (Run: {metrics['run_id']})",
            f"  Duration: {metrics['duration_seconds']}s | Completed: {metrics['end_time_utc']}",
            f"  Ingestion: {volumes['total_records_ingested']} Total Records (+{volumes['new_records_appended']} New Appended, {volumes['existing_records_refreshed']} Refreshed)",
            f"  Vendors: {volumes['vendors_succeeded']}/{volumes['vendors_processed']} Succeeded",
            f"  Stages: {stages['last_time_buy_count']} LTB | {stages['end_of_life_count']} EOL | {stages['end_of_service_count']} EOS",
            f"  Quality: {quality['utc_date_coverage_pct']}% UTC Dates | {quality['metadata_coverage_pct']}% Rich Metadata",
        ]

        if alerts["urgent_ltb_count"] > 0:
            lines.append(f"\n[!] URGENT PROCUREMENT ALERTS ({alerts['urgent_ltb_count']} products closing orders in <{alerts['urgent_ltb_window_days']} days):")
            for item in alerts["urgent_items"][:5]:
                lines.append(f"  * [{item['vendor']}] {item['model']} - LTB Date: {item['stage_date_utc'][:10]} ({item['days_remaining']} days left!) - Repl: {item['replacement']}")

        if metrics["errors"]:
            lines.append(f"\n[x] ERRORS ({len(metrics['errors'])}):")
            for err in metrics["errors"][:3]:
                lines.append(f"  * {err}")

        return "\n".join(lines)

    @classmethod
    def dispatch_alert(cls, metrics: Dict[str, Any], webhook_url: Optional[str] = None):
        """Sends alert message to configured Webhook (Slack / Teams / Generic)."""
        alert_body = cls.format_alert_text(metrics)
        print("\n" + "=" * 90)
        try:
            print(alert_body)
        except Exception:
            print(alert_body.encode("ascii", errors="replace").decode("ascii"))
        print("=" * 90 + "\n")

        target_webhook = webhook_url or os.getenv("WEBHOOK_URL", "")
        if not target_webhook or not target_webhook.startswith("http"):
            logger.info("No external WEBHOOK_URL configured. Alert logged to console.")
            return

        try:
            payload = json.dumps({"text": alert_body}).encode("utf-8")
            req = urllib.request.Request(
                target_webhook,
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                logger.info(f"Successfully dispatched alert to Webhook (Status: {resp.status})")
        except Exception as e:
            logger.warning(f"Failed to post alert to Webhook: {e}")
