"""Constants for the Cursor Usage integration."""

from datetime import timedelta

DOMAIN = "cursor_usage"

CONF_SESSION_TOKEN = "session_token"
CONF_NAME = "name"

DEFAULT_NAME = "Cursor"
DEFAULT_SCAN_INTERVAL = timedelta(hours=1)

USAGE_SUMMARY_URL = "https://cursor.com/api/usage-summary"
AUTH_ME_URL = "https://cursor.com/api/auth/me"
AGGREGATED_USAGE_URL = (
    "https://cursor.com/api/dashboard/get-aggregated-usage-events"
)
COOKIE_NAME = "WorkosCursorSessionToken"
ORIGIN_HEADER = "https://cursor.com"

ATTR_BILLING_CYCLE_START = "billing_cycle_start"
ATTR_BILLING_CYCLE_END = "billing_cycle_end"
ATTR_MEMBERSHIP_TYPE = "membership_type"
ATTR_USED = "used"
ATTR_LIMIT = "limit"
ATTR_REMAINING = "remaining"
ATTR_ENABLED = "enabled"
ATTR_AUTO_PERCENT_USED = "auto_percent_used"
ATTR_API_PERCENT_USED = "api_percent_used"
ATTR_MODELS = "models"
ATTR_INPUT_TOKENS = "input_tokens"
ATTR_OUTPUT_TOKENS = "output_tokens"
ATTR_CACHE_READ_TOKENS = "cache_read_tokens"
ATTR_CACHE_WRITE_TOKENS = "cache_write_tokens"
ATTR_TOTAL_CENTS = "total_cents"
