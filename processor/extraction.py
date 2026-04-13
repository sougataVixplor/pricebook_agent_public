import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict
import asyncio
from concurrent.futures import ThreadPoolExecutor

from processor.db import get_db

logger = logging.getLogger(__name__)

DOC_CATEGORY_DOOR_FRAME = "DOOR & FRAME"
_bg_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bg_extraction")

def generate_session_id(filename: str, manufacturer: Optional[str] = None, brand: Optional[str] = None) -> str:
    import hashlib
    base_str = f"{filename}_{manufacturer}_{brand}_{datetime.now().isoformat()}"
    return hashlib.md5(base_str.encode()).hexdigest()

def run_extraction_job_sync(job_id: str, file_path: str, file_id: str, original_filename: str, manufacturer: Optional[str], brand: Optional[str], rules: Optional[str], doc_category: str = DOC_CATEGORY_DOOR_FRAME, force_fresh: bool = False):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            _run_extraction_async(
                job_id, file_path, file_id, original_filename,
                manufacturer, brand, rules, doc_category, force_fresh
            )
        )
    except Exception as e:
        logger.error(f"Error in async workflow: {e}")
    finally:
        loop.close()

async def _run_extraction_async(job_id: str, file_path: str, file_id: str, original_filename: str, manufacturer: Optional[str], brand: Optional[str], rules: Optional[str], doc_category: str = DOC_CATEGORY_DOOR_FRAME, force_fresh: bool = False):
    db = get_db()
    jobs_collection = db.get_collection("jobs")
    session_id = generate_session_id(original_filename, manufacturer, brand)
    try:
        jobs_collection.update_one(
            {"_id": job_id},
            {"$set": {"status": "running", "progress": "Workflow started (Mocked inside streamlit)", "session_id": session_id, "started_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        # We are not allowed to call external functions, so run_extraction_workflow is mocked here
        await asyncio.sleep(2)
        
        final_state = {"workflow_status": "completed", "series_count": 0}
        
        jobs_collection.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "completed", "progress": "Workflow completed", "series_count": 0, "door_count": 0, "frame_count": 0, "hardware_count": 0, "session_id": session_id,
                "completed_at": datetime.now(timezone.utc).isoformat(), "state": {
                    "upload_status": "completed", "extraction_status": "completed", "save_status": "completed"
                }
            }}
        )
    except Exception as e:
        jobs_collection.update_one(
            {"_id": job_id},
            {"$set": {"status": "failed", "error": str(e), "session_id": session_id, "completed_at": datetime.now(timezone.utc).isoformat()}}
        )

def start_extraction(file_content: bytes, filename: str, manufacturer: Optional[str] = None, brand: Optional[str] = None, rules: Optional[str] = None, doc_category: str = DOC_CATEGORY_DOOR_FRAME, force_fresh: bool = False) -> Dict:
    try:
        db = get_db()
        files_collection = db.get_collection("files")
        jobs_collection = db.get_collection("jobs")
        
        session_id = generate_session_id(filename, manufacturer, brand)
        file_ext = os.path.splitext(filename)[1]
        
        upload_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        
        file_path = os.path.join("uploads", f"{session_id}{file_ext}")
        abs_file_path = os.path.join(os.path.dirname(__file__), "..", file_path)
        
        file_id = session_id
        
        with open(abs_file_path, "wb") as f:
            f.write(file_content)
        
        job_id = str(uuid.uuid4())
        job_doc = {
            "_id": job_id, "file_id": file_id, "file_path": file_path, "filename": filename, "original_filename": filename,
            "manufacturer": manufacturer, "brand": brand, "rules": rules, "doc_category": doc_category, "session_id": session_id,
            "status": "pending", "progress": "Job submitted", "created_at": datetime.now(timezone.utc).isoformat()
        }
        jobs_collection.insert_one(job_doc)
        
        _bg_executor.submit(
            run_extraction_job_sync,
            job_id=job_id, file_path=file_path, file_id=file_id, original_filename=filename,
            manufacturer=manufacturer, brand=brand, rules=rules, doc_category=doc_category, force_fresh=force_fresh
        )
        
        return {"job_id": job_id, "status": "pending", "message": "Extraction job submitted", "file_id": file_id}
    except Exception as e:
        logger.error(f"Error starting extraction: {e}")
        return {"status": "error", "error": str(e)}
