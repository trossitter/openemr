"""
Configuration for the Clinical Co-Pilot service.
All values are read from environment variables, with safe defaults for development.
"""
import os

# Anthropic
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

# Database (reads from the OpenEMR MariaDB container)
DB_HOST = os.environ.get("DB_HOST", "mysql")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_NAME = os.environ.get("DB_NAME", "openemr")
DB_USER = os.environ.get("DB_USER", "openemr")
DB_PASS = os.environ.get("DB_PASS", "openemr")

# Security
# Shared secret that the OpenEMR module passes in X-Copilot-Secret header.
# Must match COPILOT_SECRET in the OpenEMR module config.
COPILOT_SECRET = os.environ.get("COPILOT_SECRET", "dev-secret-change-in-production")

# HIPAA guard: when True, the service operates on demo data only.
# Must be explicitly set to "false" after a BAA with Anthropic is executed.
DEMO_MODE = os.environ.get("COPILOT_DEMO_MODE", "true").lower() != "false"

# Conversation TTL in seconds (30 minutes matches OpenEMR session timeout guidance)
CONVERSATION_TTL = int(os.environ.get("CONVERSATION_TTL", "1800"))

# Max encounters to retrieve per patient
MAX_ENCOUNTERS = int(os.environ.get("MAX_ENCOUNTERS", "5"))

# Observability log file path
LOG_FILE = os.environ.get("LOG_FILE", "/var/log/copilot/copilot.jsonl")

# Cost per token (claude-sonnet-4-5 pricing, USD)
COST_PER_INPUT_TOKEN = 3.0 / 1_000_000   # $3 per 1M input tokens
COST_PER_OUTPUT_TOKEN = 15.0 / 1_000_000  # $15 per 1M output tokens
