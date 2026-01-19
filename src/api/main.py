"""FastAPI main application."""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Header, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from src.config import config, Config
from src.fetch.client import FetchClient
from src.fetch.endpoints import get_urls_for_nr
from src.config import config
from src.parse.html_parser import contains_location_vehicule, parse_html_pages
from src.parse.models import SaleRecord
from src.store.supabase_writer import SupabaseWriter
from src.store.state import StateDB

logger = logging.getLogger(__name__)

app = FastAPI(title="DigiFactory Scraper API", version="0.1.0")

# API Key security (if configured)
API_KEY_HEADER = APIKeyHeader(name="X-API-KEY", auto_error=False)

def verify_api_key(api_key: str = Depends(API_KEY_HEADER)) -> bool:
    """Verify API key if configured."""
    expected_key = config.API_KEY if hasattr(config, "API_KEY") else None
    if expected_key:
        if not api_key or api_key != expected_key:
            raise HTTPException(status_code=403, detail="Invalid API key")
    return True

# Initialize components
state_db = StateDB()
writer = SupabaseWriter()


@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    await state_db.initialize()
    if not await writer.test_connection():
        logger.warning("Supabase connection test failed, but continuing...")


class ScrapeRequest(BaseModel):
    """Request model for scraping."""
    nr: int


class ScrapeResponse(BaseModel):
    """Response model for scraping."""
    nr: int
    gate_passed: bool
    status: str
    message: str
    data: Optional[dict] = None


@app.get("/health")
async def health():
    """Health check endpoint (no auth required)."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "supabase_connected": await writer.test_connection(),
    }


@app.get("/metrics")
async def get_metrics(_: bool = Depends(verify_api_key)):
    """Get current metrics (requires API key if configured)."""
    # Read from metrics.jsonl
    from src.config import DATA_DIR
    import json
    
    metrics_file = DATA_DIR / "metrics.jsonl"
    if not metrics_file.exists():
        return {"error": "No metrics available"}
    
    # Return last 100 lines
    lines = []
    with open(metrics_file, "r") as f:
        for line in f:
            lines.append(json.loads(line))
    
    return {"metrics": lines[-100:]}


@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_nr(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
    _: bool = Depends(verify_api_key),
):
    """
    Scrape a single nr.
    Applies gating: only does full extraction if "Location de véhicule" is present.
    """
    nr = request.nr

    try:
        # Step 1: Fetch main view page for gating
        view_url = f"{config.BASE_URL}/digi/com/cto/view?nr={nr}"
        
        async with FetchClient() as client:
            view_response = await client.fetch(view_url)

        if not view_response:
            raise HTTPException(status_code=500, detail="Failed to fetch view page")

        if view_response.status_code == 404:
            return ScrapeResponse(
                nr=nr,
                gate_passed=False,
                status="not_found",
                message="Page not found",
            )

        # Step 2: Check gate
        html_content = view_response.text
        gate_passed = contains_location_vehicule(html_content)

        if not gate_passed:
            # Gate failed - minimal record
            record = SaleRecord(
                nr=nr,
                status="ok",
                data={
                    "nr": nr,
                    "gate_passed": False,
                    "reason": "Location de véhicule not found",
                },
            )
            
            # Save in background
            background_tasks.add_task(_save_record, record)
            
            return ScrapeResponse(
                nr=nr,
                gate_passed=False,
                status="ok",
                message="Gate failed: Location de véhicule not found",
                data=record.data,
            )

        # Step 3: Gate passed - fetch all 5 pages
        urls = get_urls_for_nr(nr)
        
        async with FetchClient() as client:
            responses = await client.fetch_all(urls)

        # Parse with full extraction
        html_responses = {
            url: (r.text if r else None) for url, r in responses.items()
        }
        
        # Add status codes
        page_results = {}
        for url, response in responses.items():
            if response:
                page_results[url] = {
                    "status_code": response.status_code,
                    "final_url": str(response.url),
                }

        parsed_data = parse_html_pages(html_responses, config.BASE_URL, gate_passed=True)
        
        # Merge page results
        for page_type, page_data in parsed_data.get("pages", {}).items():
            if page_data.get("url") in page_results:
                page_data.update(page_results[page_data["url"]])

        # Create full record
        data = {
            "nr": nr,
            "gate_passed": True,
            **parsed_data,
        }

        record = SaleRecord(
            nr=nr,
            status="ok",
            data=data,
        )

        # Save in background
        background_tasks.add_task(_save_record, record)

        return ScrapeResponse(
            nr=nr,
            gate_passed=True,
            status="ok",
            message="Full extraction completed",
            data=record.data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scraping nr {nr}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/scrape/{nr}", response_model=ScrapeResponse)
async def scrape_nr_get(
    nr: int,
    background_tasks: BackgroundTasks,
    _: bool = Depends(verify_api_key),
):
    """Scrape a single nr (GET version)."""
    return await scrape_nr(ScrapeRequest(nr=nr), background_tasks)


async def _save_record(record: SaleRecord):
    """Save record to Supabase (background task)."""
    try:
        await writer.upsert_batch([record])
        await state_db.mark_done(record.nr)
        logger.info(f"Saved record for nr {record.nr}")
    except Exception as e:
        logger.error(f"Failed to save record for nr {record.nr}: {e}")
        await state_db.mark_failed(record.nr, str(e))


if __name__ == "__main__":
    import uvicorn
    Config.validate()
    uvicorn.run(app, host="0.0.0.0", port=8000)

