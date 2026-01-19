"""DEV mode storage: save outputs to data/dev/ for inspection."""
import gzip
import json
import logging
from pathlib import Path
from typing import Any
import orjson

from src.config import DATA_DIR
from src.parse.redact import redact_json

logger = logging.getLogger(__name__)

DEV_DIR = DATA_DIR / "dev"


class DevStorage:
    """Stores scraped data in DEV mode for inspection."""

    def __init__(self):
        self.dev_dir = DEV_DIR
        self.dev_dir.mkdir(parents=True, exist_ok=True)

    def save_nr_data(
        self,
        nr: int,
        gate_passed: bool,
        urls_status: dict[str, int],
        extracted_data: dict[str, Any],
        html_pages: dict[str, str | None] | None = None,
        store_html: bool = False,
    ) -> None:
        """Save all data for a single nr in DEV mode."""
        nr_dir = self.dev_dir / str(nr)
        nr_dir.mkdir(exist_ok=True)

        # Save summary.json (redacted)
        summary = {
            "nr": nr,
            "gate_passed": gate_passed,
            "urls_status": urls_status,
            "nb_jsinfos": self._count_jsinfos(extracted_data),
            "nb_basket_lines": len(extracted_data.get("basket_lines", [])),
            "nb_explorer_links": len(extracted_data.get("explorer_links", [])),
        }
        summary = redact_json(summary)
        summary_path = nr_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved summary to {summary_path}")

        # Save extracted.json (final data that would go to Supabase, redacted)
        extracted_data_redacted = redact_json(extracted_data)
        extracted_path = nr_dir / "extracted.json"
        with open(extracted_path, "wb") as f:
            f.write(orjson.dumps(extracted_data_redacted, option=orjson.OPT_INDENT_2))
        logger.info(f"Saved extracted data to {extracted_path}")

        # Save HTML pages (compressed) if requested
        if store_html and html_pages:
            pages_dir = nr_dir / "pages"
            pages_dir.mkdir(exist_ok=True)
            for url, html_content in html_pages.items():
                if html_content:
                    page_type = self._get_page_type_from_url(url)
                    html_path = pages_dir / f"{page_type}.html.gz"
                    with gzip.open(html_path, "wt", encoding="utf-8") as f:
                        f.write(html_content)
                    logger.debug(f"Saved HTML to {html_path}")

    def _count_jsinfos(self, data: dict) -> int:
        """Count total JSinfos found."""
        count = 0
        jsinfos = data.get("jsinfos", {})
        if isinstance(jsinfos, dict):
            for page_jsinfos in jsinfos.values():
                if isinstance(page_jsinfos, dict):
                    count += len(page_jsinfos)
        return count

    def _get_page_type_from_url(self, url: str) -> str:
        """Extract page type from URL."""
        if "viewLogistic" in url:
            return "logistic"
        elif "viewPayment" in url:
            return "payment"
        elif "viewInfos" in url:
            return "infos"
        elif "viewOrders" in url:
            return "orders"
        else:
            return "view"

