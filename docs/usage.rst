Usage
=====

Installation
------------

.. code-block:: sh

   uv add schlepper

Or with pip:

.. code-block:: sh

   pip install schlepper

Basic usage
-----------

Create an :class:`~schlepper.ApiToken` (or :class:`~schlepper.ApiKey`) and
call :func:`~schlepper.deploy` with the directory you want to publish:

.. code-block:: python

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

:func:`~schlepper.deploy` handles the full lifecycle: validating the
directory, hashing and uploading assets, creating the deployment, and polling
until it reaches a terminal state.  It returns a :class:`~schlepper.Deployment`
with the result.

Authentication
--------------

Cloudflare supports two credential types:

**API Token** (recommended) — a scoped token created in the Cloudflare
dashboard:

.. code-block:: python

   credentials = schlepper.ApiToken(token="your-api-token")

**Global API Key** — the legacy key plus your account email:

.. code-block:: python

   credentials = schlepper.ApiKey(key="your-global-api-key", email="you@example.com")

Commit metadata
---------------

You can attach git metadata to each deployment:

.. code-block:: python

   result = schlepper.deploy(
       "./dist",
       project_name="my-site",
       account_id="your-account-id",
       credentials=credentials,
       branch="production",
       commit_hash="abc1234",
       commit_message="Fix homepage layout",
       commit_dirty=False,
   )

Special files
-------------

Cloudflare Pages recognises several special files in the deploy directory:

- ``_headers`` — custom HTTP response headers
- ``_redirects`` — URL redirect rules
- ``_routes.json`` — custom routing configuration

These files are **not** uploaded as static assets.  Instead, schlepper sends
them as metadata alongside the deployment so that Cloudflare can process them
as configuration.

Error handling
--------------

All errors raised by schlepper are subclasses of
:exc:`~schlepper.SchlepperError`:

.. code-block:: python

   try:
       result = schlepper.deploy(...)
   except schlepper.ValidationError:
       # Directory validation failed (too many files, file too large, etc.)
       ...
   except schlepper.AuthenticationError:
       # Invalid or missing credentials
       ...
   except schlepper.UploadError:
       # Asset upload failed after retries
       ...
   except schlepper.DeploymentError:
       # Deployment creation or polling failed
       ...
   except schlepper.APIError as e:
       # Cloudflare API returned an error
       print(f"HTTP {e.status}: {e}")
       ...
