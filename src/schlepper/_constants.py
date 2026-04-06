"""Constants matching Cloudflare Pages limits and defaults."""

MAX_ASSET_SIZE: int = 25 * 1024 * 1024  # 25 MiB per file
MAX_ASSET_COUNT: int = 20_000
MAX_BUCKET_SIZE: int = 40 * 1024 * 1024  # 40 MiB per upload batch
MAX_BUCKET_FILE_COUNT: int = 2_000
BULK_UPLOAD_CONCURRENCY: int = 3

MAX_UPLOAD_ATTEMPTS: int = 5
MAX_CHECK_MISSING_ATTEMPTS: int = 5
MAX_DEPLOYMENT_ATTEMPTS: int = 3
MAX_DEPLOYMENT_STATUS_ATTEMPTS: int = 5

MAX_COMMIT_MESSAGE_BYTES: int = 384

CF_API_BASE_URL: str = "https://api.cloudflare.com/client/v4"
