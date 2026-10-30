"""
HTTP Web Server & REST API for Enterprise Multi-Vendor Lifecycle Scraper.
Serves the interactive Web Dashboard, provides real-time JSON APIs,
manages master CSV export, and displays observability metrics.
"""

import asyncio
import json
import logging
import os
import sys
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn

# Ensure project root is on sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from scraper.config import DEFAULT_CSV_OUTPUT, DEFAULT_JSON_OUTPUT, GEMINI_API_KEY, GEMINI_MODEL
from scraper.pipeline import LifecyclePipeline
from scraper.providers import resolve_provider_and_model
from scraper.storage import MasterStorageManager
from setup_key import test_and_save_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ai_scraper.server")

from scraper.crawler_comparison import CRAWLER_COMPARISON_MATRIX

WEB_DIR = BASE_DIR / "web"
OUTPUT_DIR = BASE_DIR / "output"
MASTER_CSV = OUTPUT_DIR / "all_vendors_lifecycle.csv"
ARTIFACTS_DIR = BASE_DIR / "artifacts" / "runs"


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server for handling concurrent web requests."""
    daemon_threads = True


class ScraperAPIHandler(SimpleHTTPRequestHandler):
    """Handles API requests and static assets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def _send_json(self, data: dict, status_code: int = 200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        """Handle CORS pre-flight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/products":
            self.handle_get_products()
        elif path == "/api/status":
            self.handle_get_status()
        elif path == "/api/vendors":
            self.handle_get_vendors()
        elif path == "/api/comparison":
            self._send_json({"comparison": CRAWLER_COMPARISON_MATRIX})
        elif path == "/api/export/csv":
            target = MASTER_CSV if MASTER_CSV.exists() else DEFAULT_CSV_OUTPUT
            self.handle_export_file(target, "text/csv", "all_vendors_lifecycle.csv")
        elif path == "/api/export/json":
            self.handle_export_file(DEFAULT_JSON_OUTPUT, "application/json", "lifecycle_dataset.json")
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/crawl":
            self.handle_trigger_crawl()
        elif path == "/api/test-key":
            self.handle_test_key()
        elif path == "/api/clean-artifacts":
            self.handle_clean_artifacts()
        else:
            self._send_json({"error": "Endpoint not found"}, 404)

    def handle_clean_artifacts(self):
        """Purges old run artifacts and temporary files after review."""
        import shutil
        deleted_count = 0
        if ARTIFACTS_DIR.exists():
            for item in ARTIFACTS_DIR.iterdir():
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                    deleted_count += 1
        storage = MasterStorageManager(MASTER_CSV, OUTPUT_DIR)
        tmp_count = storage.cleanup_temporary_files()
        self._send_json({
            "success": True,
            "message": f"Successfully deleted {deleted_count} artifact directories and {tmp_count} temporary files."
        })

    def handle_test_key(self):
        """Tests and validates an AI API key for any configured provider."""
        content_len = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            payload = json.loads(post_data)
        except Exception:
            payload = {}

        provider = payload.get("provider") or None
        api_key = payload.get("api_key") if "api_key" in payload else None
        model = payload.get("model") or None
        api_base = payload.get("api_base") or payload.get("endpoint") or None
        save_to_env = bool(payload.get("save", False))

        from scraper.ai_extractor import UniversalAIExtractor
        extractor = UniversalAIExtractor(
            provider=provider,
            api_key=api_key,
            model_name=model,
            api_base=api_base,
        )
        success, message = extractor.test_connection()

        if success and save_to_env:
            effective_key = api_key or extractor.api_key or ""
            extra_env = {}
            if extractor.provider == "azure" and api_base:
                extra_env["AZURE_OPENAI_ENDPOINT"] = api_base
            test_and_save_key(
                api_key=effective_key,
                model_name=extractor.model_name,
                provider=extractor.provider,
                api_base=api_base or "",
                extra_env=extra_env,
            )

        self._send_json({
            "success": success,
            "message": message,
            "provider": extractor.provider,
            "model": extractor.model_name
        })

    def handle_get_status(self):
        """Returns crawler & multi-provider AI configuration status."""
        prov, active_model, _ = resolve_provider_and_model()

        gemini_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)
        has_gemini = bool(gemini_key and gemini_key != "your_gemini_api_key_here")

        openai_key = os.getenv("OPENAI_API_KEY", "")
        has_openai = bool(openai_key and not openai_key.startswith("your_"))

        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        has_anthropic = bool(anthropic_key and not anthropic_key.startswith("your_"))

        azure_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        has_azure = bool(azure_key and not azure_key.startswith("your_"))

        aws_key = os.getenv("AWS_ACCESS_KEY_ID", "")
        has_bedrock = bool(aws_key and not aws_key.startswith("your_"))

        has_any = has_gemini or has_openai or has_anthropic or has_azure or has_bedrock

        self._send_json({
            "status": "online",
            "provider": prov,
            "model": active_model,
            "ai_configured": has_any,
            "gemini_configured": has_gemini,
            "gemini_model": os.getenv("GEMINI_MODEL", GEMINI_MODEL),
            "openai_configured": has_openai,
            "anthropic_configured": has_anthropic,
            "azure_configured": has_azure,
            "bedrock_configured": has_bedrock,
            "ollama_configured": True,
            "master_csv_exists": MASTER_CSV.exists(),
            "artifacts_dir_exists": ARTIFACTS_DIR.exists()
        })

    def handle_get_vendors(self):
        """Returns configured vendors from vendors.yaml."""
        pipeline = LifecyclePipeline()
        vendors = pipeline.config.get("vendors", {})
        self._send_json({"vendors": vendors})

    def handle_get_products(self):
        """Returns the current scraped product dataset."""
        # Check master vendor json or default output json
        target_json = OUTPUT_DIR / "mitsubishi_electric_lifecycle.json"
        if not target_json.exists():
            target_json = DEFAULT_JSON_OUTPUT

        if not target_json.exists():
            if MASTER_CSV.exists():
                try:
                    import pandas as pd
                    df = pd.read_csv(MASTER_CSV, dtype=str)
                    records = df.fillna("").to_dict(orient="records")
                    self._send_json({"total_records": len(records), "products": records})
                    return
                except Exception:
                    pass
            self._send_json({"total_records": 0, "products": []})
            return

        try:
            with open(target_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._send_json(data)
        except Exception as e:
            logger.error(f"Failed to read dataset: {e}")
            self._send_json({"error": str(e)}, 500)

    def handle_trigger_crawl(self):
        """Triggers a live multi-vendor or custom URL crawl."""
        content_len = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            payload = json.loads(post_data)
        except Exception:
            payload = {}

        target_url = payload.get("url") or None
        vendor = payload.get("vendor") or "all"
        sector = payload.get("sector") or None
        site_crawl = bool(payload.get("site_crawl", False))
        provider = payload.get("provider") or None
        api_key = payload.get("api_key") or None
        model = payload.get("model") or None
        api_base = payload.get("api_base") or None

        logger.info(f"Triggering live crawl (url={target_url}, vendor={vendor}, sector={sector}, site_crawl={site_crawl}, provider={provider}, model={model})...")
        try:
            pipeline = LifecyclePipeline(
                provider=provider,
                api_key=api_key,
                model=model,
                api_base=api_base,
            )
            dataset = asyncio.run(pipeline.execute(
                vendor_filter=vendor,
                sector_filter=sector,
                target_url=target_url,
                site_crawl=site_crawl
            ))
            self._send_json({
                "success": True,
                "message": f"Successfully processed {dataset.total_products} records into master storage.",
                "dataset": dataset.model_dump()
            })
        except Exception as e:
            logger.exception("Crawl execution failed")
            self._send_json({"success": False, "error": str(e)}, 500)

    def handle_export_file(self, file_path: Path, mime_type: str, filename: str):
        if not file_path.exists():
            self._send_json({"error": "File not found. Please run a scrape first."}, 404)
            return

        with open(file_path, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", f"{mime_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)


def run_server(port: int = 8000, host: str = "0.0.0.0"):
    server_address = (host, port)
    httpd = ThreadedHTTPServer(server_address, ScraperAPIHandler)
    logger.info(f"Enterprise Multi-Vendor Lifecycle Scraper Web Dashboard running at: http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server shutting down.")
        httpd.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port=port)
