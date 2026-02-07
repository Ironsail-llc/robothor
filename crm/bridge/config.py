"""Bridge service configuration."""
import os
from dotenv import load_dotenv

load_dotenv("/home/philip/robothor/crm/.env")

# Service URLs
TWENTY_URL = "http://localhost:3030"
CHATWOOT_URL = "http://localhost:3100"
MEMORY_URL = "http://localhost:9099"

# Auth
TWENTY_EMAIL = os.getenv("TWENTY_EMAIL", "robothor@ironsail.ai")
TWENTY_PASSWORD = os.getenv("TWENTY_PASSWORD", "")
CHATWOOT_API_TOKEN = os.getenv("CHATWOOT_API_TOKEN", "")
CHATWOOT_ACCOUNT_ID = int(os.getenv("CHATWOOT_ACCOUNT_ID", "1"))
CHATWOOT_INBOX_ID = 2  # Robothor Bridge API inbox

# Database
PG_DSN = "dbname=robothor_memory user=philip host=/var/run/postgresql"
