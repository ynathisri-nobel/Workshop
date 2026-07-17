"""Application configuration."""
import os

# --- AWS / Bedrock ---
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
# Claude chat model (inference profile). Haiku 4.5 confirmed available on-demand via profile.
CHAT_MODEL_ID = os.environ.get("CHAT_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
# Selectable answering models exposed in the UI (key -> Bedrock inference profile id).
CHAT_MODELS = {
    "haiku": os.environ.get("MODEL_HAIKU", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
    "sonnet": os.environ.get("MODEL_SONNET", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"),
}
# A cheaper/faster model for classification (fact/opinion). Reuse haiku by default.
CLASSIFY_MODEL_ID = os.environ.get("CLASSIFY_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
# Cohere multilingual embeddings: good for mixed Thai/English, 1024-dim, on-demand.
EMBED_MODEL_ID = os.environ.get("EMBED_MODEL_ID", "cohere.embed-multilingual-v3")
EMBED_DIM = 1024

# --- Web / external search (optional) ---
# Set WEB_SEARCH_PROVIDER=tavily and TAVILY_API_KEY=... to enable real web search.
WEB_SEARCH_PROVIDER = os.environ.get("WEB_SEARCH_PROVIDER", "").lower()
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

# --- Auth ---
JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production-crm-assistant-secret")
JWT_ALG = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "480"))

# --- Storage ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
DB_PATH = os.environ.get("DB_PATH", os.path.join(PROJECT_DIR, "crm.db"))
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(PROJECT_DIR, "uploads"))
FRONTEND_DIR = os.path.join(PROJECT_DIR, "..", "frontend")

# --- RAG ---
RETRIEVE_TOP_K = int(os.environ.get("RETRIEVE_TOP_K", "8"))

# Sensitivity levels (higher = more restricted)
SENSITIVITY_LEVELS = {1: "normal", 2: "confidential", 3: "restricted"}

os.makedirs(UPLOAD_DIR, exist_ok=True)
