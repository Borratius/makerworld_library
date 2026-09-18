"""Constants for the MakerWorld Library integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "makerworld_library"
PLATFORMS = ["sensor", "button"]

CONF_COLLECTION_ID = "collection_id"
CONF_COLLECTION_SLUG = "collection_slug"
CONF_ACCESS_TOKEN = "access_token"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_PRINTER_DEVICE_ID = "printer_device_id"

DEFAULT_COLLECTION_ID = "35678497"
DEFAULT_COLLECTION_SLUG = "35678497-home-prints"
DEFAULT_COLLECTION_NAME = "Home Prints"
DEFAULT_SCAN_INTERVAL = 45
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 60

API_BASE_URL = "https://api.bambulab.com/v1/design-service"
CLOUD_API_BASE_URL = "https://api.bambulab.com/v1/iot-service/api/user"
REQUEST_TIMEOUT = 20
PAGE_SIZE = 20
MAX_COLLECTION_ITEMS = 500
MAX_PARALLEL_DETAIL_REQUESTS = 4
MAX_ENTITY_PROFILES = 25

UPDATE_INTERVAL = timedelta(minutes=DEFAULT_SCAN_INTERVAL)
