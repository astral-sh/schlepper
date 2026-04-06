# schlepper

A Python library for deploying static assets to [Cloudflare Pages](https://pages.cloudflare.com/).

## Installation

```console
uv add schlepper
```

## Usage

```python
import schlepper

result = schlepper.deploy(
    "./dist",
    project_name="my-site",
    account_id="your-account-id",
    credentials=schlepper.ApiToken(token="your-api-token"),
    branch="production",
    commit_message="Deploy v1.0.0",
)

print(f"Deployed to {result.url} (status: {result.status})")
```

`ApiKey` credentials are also supported:

```python
credentials = schlepper.ApiKey(key="your-global-api-key", email="you@example.com")
```

## Development

Linting/formatting/type checking:

```console
uv run ruff check
uv run ruff format --check
uv run ty check
```

Unit testing:

```console
uv run pytest
# with coverage
uv run coverage run -m pytest
```

Integration tests (requires Cloudflare credentials):

```console
# see it.env.example
export $(cat it.env | xargs)
uv run pytest -m integration
```
