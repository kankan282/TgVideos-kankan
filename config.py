import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH", "")
    PHONE_NUMBER = os.getenv("PHONE_NUMBER", "")
    API_KEY = os.getenv("API_KEY", "default")
    PORT = int(os.getenv("PORT", 10000))
    RENDER_URL = os.getenv("RENDER_URL", "")
    
    # ⚡ Speed Settings
    MAX_WORKERS = int(os.getenv("MAX_WORKERS", 5))
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1048576))  # 1MB chunks
    DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", 300))
    
    SESSION_NAME = "forwarder_pro"
