# schlepper

A Python library for deploying static assets to [Cloudflare Pages](https://pages.cloudflare.com/).

## Installation

```bash
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

```bash
uv run ruff check
uv run ruff format --check
uv run ty check
```

Unit testing:

```bash
uv run pytest
# with coverage
uv run coverage run -m pytest
```

Integration tests (requires Cloudflare credentials):

```bash
# see it.env.example
export $(cat it.env | xargs)
uv run pytest -m integration
```

Build docs:

```bash
uv run sphinx-build -b html docs docs/_build/html
```

## Licence

schlepper is licensed under either of

- Apache License, Version 2.0, ([LICENSE-APACHE](LICENSE-APACHE) or <https://www.apache.org/licenses/LICENSE-2.0>)
- MIT license ([LICENSE-MIT](LICENSE-MIT) or <https://opensource.org/licenses/MIT>)

at your option.

Unless you explicitly state otherwise, any contribution intentionally submitted
for inclusion in tsayt by you, as defined in the Apache-2.0 license, shall be
dually licensed as above, without any additional terms or conditions.

<div align="center">
  <a target="_blank" href="https://astral.sh" style="background:none">
    <img src="https://raw.githubusercontent.com/astral-sh/ruff/main/assets/svg/Astral.svg">
  </a>
</div>
