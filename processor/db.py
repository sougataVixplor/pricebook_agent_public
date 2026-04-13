import os
import logging
from typing import List, Dict, Optional
import streamlit as st
from pymongo import MongoClient, errors
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# ============================================
# DATABASE CONSTANTS
# ============================================
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "pricebookAI")

# ============================================
# MONGODB CONNECTION MANAGER
# ============================================
class MongoDB:
    """MongoDB connection and operations manager"""
    
    _instance = None
    _client = None
    _db = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDB, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._client is None:
            self.connect()
    
    def connect(self):
        """Establish MongoDB connection"""
        try:
            self._client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=30000, connectTimeoutMS=30000)
            self._db = self._client[MONGODB_DB_NAME]
            logger.info(f"Connected to MongoDB: {MONGODB_DB_NAME}")
        except errors.ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    def _ensure_connected(self):
        """Ensure MongoDB connection is alive, reconnect if needed"""
        try:
            # Try to ping the server
            if self._client is not None:
                self._client.admin.command('ping')
        except Exception as e:
            logger.warning(f"MongoDB connection lost, reconnecting: {e}")
            self._client = None
            self._db = None
            self.connect()
    
    def get_collection(self, collection_name: str):
        """Get collection instance"""
        self._ensure_connected()
        return self._db[collection_name]
    
    # CRUD Operations
    def insert_one(self, collection_name: str, document: Dict) -> str:
        try:
            collection = self.get_collection(collection_name)
            result = collection.insert_one(document)
            return str(result.inserted_id)
        except errors.PyMongoError as e:
            logger.error(f"Error inserting document: {e}")
            raise
    
    def find_one(self, collection_name: str, query: Dict, projection: Dict = None) -> Optional[Dict]:
        try:
            collection = self.get_collection(collection_name)
            result = collection.find_one(query, projection)
            if result and '_id' in result:
                result['_id'] = str(result['_id'])
            return result
        except errors.PyMongoError as e:
            logger.error(f"Error finding document: {e}")
            raise

# Singleton instance
db = MongoDB()

def get_db() -> MongoDB:
    """Dependency injection for FastAPI / Streamlit"""
    return db

# ============================================
# STREAMLIT DATA QUERIES
# ============================================
@st.cache_data(ttl=60)
def get_all_manufacturers():
    try:
        database = get_db()
        return sorted(database.get_collection("series").distinct("manufacturer"))
    except Exception:
        return []

@st.cache_data(ttl=60)
def get_brands_for_manufacturer(manufacturer: str):
    try:
        database = get_db()
        brands = database.get_collection("series").distinct("brand", {"manufacturer": manufacturer})
        return sorted([b for b in brands if b])
    except Exception:
        return []

@st.cache_data(ttl=60)
def get_series_for_manufacturer_brand(manufacturer: str, brand: str = None):
    try:
        database = get_db()
        query = {"manufacturer": manufacturer}
        if brand:
            query["brand"] = brand
        cursor = database.get_collection("series").find(
            query, {"series_name": 1, "category": 1, "brand": 1, "_id": 1}
        ).sort("series_name", 1)
        res = list(cursor)
        for r in res:
            r["_id"] = str(r["_id"])
        return res
    except Exception:
        return []

def get_series_parameters(series_id: str) -> Dict:
    """Get parameters for a series"""
    try:
        from bson import ObjectId
        
        database = get_db()
        series_collection = database.get_collection("series")
        params_collection = database.get_collection("parameters")
        opt_params_collection = database.get_collection("optional_parameters")
        
        obj_id = ObjectId(series_id)
        
        # Get series
        series = series_collection.find_one({"_id": obj_id}, {"series_name": 1})
        if not series:
            return {"status": "error", "error": "Series not found"}
        
        # Get parameters
        parameters = list(params_collection.find(
            {"series_id": obj_id},
            {"_id": 0, "series_id": 0, "file_id": 0}
        ))
        
        # Get optional parameters
        optional_parameters = list(opt_params_collection.find(
            {"series_id": obj_id},
            {"_id": 0, "series_id": 0, "file_id": 0}
        ))
        
        return {
            "status": "success",
            "data": {
                "series_id": series_id,
                "series_name": series.get("series_name"),
                "parameters": parameters,
                "optional_parameters": optional_parameters,
                "parameter_count": len(parameters),
                "optional_parameter_count": len(optional_parameters)
            }
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

def check_health() -> Dict:
    """Check database health"""
    try:
        database = get_db()
        database._db.command("ping")
        return {
            "status": "healthy",
            "database": "connected"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

def get_job_status(job_id: str) -> Dict:
    """Get the status of an extraction job"""
    try:
        from bson import ObjectId
        database = get_db()
        jobs_collection = database.get_collection("jobs")
        
        job = jobs_collection.find_one({"_id": job_id})
        if not job:
            return {"status": "error", "error": "Job not found"}
        
        return {
            "status": "success",
            "data": {
                "job_id": str(job["_id"]),
                "filename": job.get("filename"),
                "status": job.get("status"),
                "progress": job.get("progress"),
                "file_id": job.get("file_id"),
                "manufacturer": job.get("manufacturer"),
                "brand": job.get("brand"),
                "series_count": job.get("series_count", 0),
                "door_count": job.get("door_count", 0),
                "frame_count": job.get("frame_count", 0),
                "hardware_count": job.get("hardware_count", 0),
                "error": job.get("error"),
                "session_id": job.get("session_id"),
                "started_at": job.get("started_at"),
                "completed_at": job.get("completed_at"),
                "elapsed_time": job.get("elapsed_time"),
                "state": job.get("state")
            }
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

def list_jobs(limit: int = 50) -> Dict:
    """List recent jobs"""
    try:
        database = get_db()
        jobs_collection = database.get_collection("jobs")
        
        jobs = list(jobs_collection.find().sort("created_at", -1).limit(limit))
        
        jobs_list = []
        for job in jobs:
            jobs_list.append({
                "job_id": str(job["_id"]),
                "file_id": job.get("file_id"),
                "filename": job.get("filename"),
                "status": job.get("status"),
                "progress": job.get("progress"),
                "manufacturer": job.get("manufacturer"),
                "brand": job.get("brand"),
                "series_count": job.get("series_count", 0),
                "door_count": job.get("door_count", 0),
                "frame_count": job.get("frame_count", 0),
                "hardware_count": job.get("hardware_count", 0),
                "created_at": job.get("created_at"),
                "completed_at": job.get("completed_at")
            })
        
        return {
            "status": "success",
            "data": jobs_list,
            "count": len(jobs_list)
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

def list_files() -> Dict:
    """List all files"""
    try:
        database = get_db()
        files_collection = database.get_collection("files")
        
        files = list(files_collection.find().sort("uploaded_at", -1))
        
        files_list = []
        for file in files:
            files_list.append({
                "file_id": str(file["_id"]),
                "filename": file.get("filename"),
                "manufacturer": file.get("manufacturer"),
                "brand": file.get("brand"),
                "extraction_status": file.get("extraction_status"),
                "series_count": file.get("series_count", 0),
                "uploaded_at": file.get("uploaded_at")
            })
        
        return {
            "status": "success",
            "data": files_list,
            "count": len(files_list)
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

def get_series(file_id: Optional[str] = None, manufacturer: Optional[str] = None, brand: Optional[str] = None) -> Dict:
    """Get series by file_id or manufacturer/brand"""
    try:
        database = get_db()
        series_collection = database.get_collection("series")
        
        query = {}
        if file_id:
            query["file_id"] = file_id
        if manufacturer:
            query["manufacturer"] = manufacturer
        if brand:
            query["brand"] = brand
        
        series_list = list(series_collection.find(query))
        
        for series in series_list:
            series["_id"] = str(series["_id"])
            series["series_id"] = series["_id"]
        
        return {
            "status": "success",
            "data": {
                "series": series_list,
                "count": len(series_list)
            }
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

