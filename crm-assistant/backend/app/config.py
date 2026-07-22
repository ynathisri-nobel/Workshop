"""Application configuration."""
import os

# --- AWS / Bedrock ---
# Singapore (ap-southeast-1): use IN-REGION model IDs (no us./cross-region profile) so
# requests never touch a us-* Bedrock resource ARN — avoids the account's Guardrails
# policy explicit deny on us-region foundation-model / inference-profile resources.
AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
# Claude chat model — in-region base model id (no "us." prefix), works directly in ap-southeast-1.
CHAT_MODEL_ID = os.environ.get("CHAT_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")
# Selectable answering models exposed in the UI (key -> Bedrock model id, in-region Singapore).
CHAT_MODELS = {
    "haiku": os.environ.get("MODEL_HAIKU", "anthropic.claude-3-haiku-20240307-v1:0"),
    "sonnet": os.environ.get("MODEL_SONNET", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
}
# A cheaper/faster model for classification (fact/opinion). Reuse haiku by default.
CLASSIFY_MODEL_ID = os.environ.get("CLASSIFY_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
# Cohere multilingual embeddings: good for mixed Thai/English, 1024-dim, on-demand, in-region SG.
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

# --- PostgreSQL ---
PG_HOST = os.environ.get("PG_HOST", "database-1.cav6m4s4mo5b.us-east-1.rds.amazonaws.com")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_DBNAME = os.environ.get("PG_DBNAME", "postgres")
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "nEGPFDsSOdsdTEEULZea")

# --- Storage ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(PROJECT_DIR, "uploads"))
FRONTEND_DIR = os.path.join(PROJECT_DIR, "..", "frontend")

# --- RAG ---
RETRIEVE_TOP_K = int(os.environ.get("RETRIEVE_TOP_K", "8"))

# Sensitivity levels (higher = more restricted)
SENSITIVITY_LEVELS = {1: "normal", 2: "confidential", 3: "restricted"}

os.makedirs(UPLOAD_DIR, exist_ok=True)
