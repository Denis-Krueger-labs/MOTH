# MOTH Team Usage Guide

This document is the internal operator guide for the TTZ FAUST CTF team.

It may contain operational details that should not be copied into the public GitHub repository before the competition.

```text
/•᷅‎‎•᷄\੭

MORI checks you first.

ཐི༏ཋྀ

Then Mof takes the flag.
```

---

## Quick Start

Activate the environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Start MOTH:

```powershell
uvicorn app.main:app --reload
```

Run tests before operational changes:

```powershell
pytest -v
```

Expected current result:

```text
31 passed
```

---

## Required Configuration

MOTH expects configuration through environment variables.

```text
MOTH_DB_KEY
MOTH_API_TOKEN

MOTH_SUBMISSION_HOST
MOTH_SUBMISSION_PORT
MOTH_SUBMISSION_TIMEOUT
```

Local development uses `.env`.

Never commit `.env`.

### Example development `.env`

```text
MOTH_DB_KEY=<local-development-key>
MOTH_API_TOKEN=<local-development-token>

MOTH_SUBMISSION_HOST=127.0.0.1
MOTH_SUBMISSION_PORT=6666
MOTH_SUBMISSION_TIMEOUT=5.0
```

Competition values belong in the deployment environment, not in Git.

---

## Generate Secrets

### API token

Generate a new token locally:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Store it as:

```text
MOTH_API_TOKEN=<generated-token>
```

### Database key

Use a separately generated database key.

Do not reuse the API token.

Do not give `MOTH_DB_KEY` to exploit scripts or teammates who only need API access.

---

## Authentication

Every protected request uses:

```text
Authorization: Bearer <MOTH_API_TOKEN>
```

Missing token:

```text
401
MORI found no authorization at the nest entrance
```

Wrong token:

```text
401
MORI does not recognize this visitor
```

Malformed authentication:

```text
401
MORI swatted away malformed authorization
```

If the server itself has no API token configured:

```text
503
```

MORI fails closed.

---

## Submit a Flag Manually

PowerShell:

```powershell
$token = (
    Get-Content .env |
    Where-Object { $_ -like "MOTH_API_TOKEN=*" }
).Split("=", 2)[1]
```

Create a request:

```powershell
$body = @{
    flag = "FAUST_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    service = "manual-test"
    source = "operator"
} | ConvertTo-Json
```

Submit:

```powershell
Invoke-RestMethod `
    -Uri "http://127.0.0.1:8000/api/flags" `
    -Method Post `
    -ContentType "application/json" `
    -Headers @{
        Authorization = "Bearer $token"
    } `
    -Body $body
```

Successful result:

```text
status     code message  remembered
------     ---- -------  ----------
submitted OK   accepted       True
```

---

## Exploit Script Integration

An exploit only needs to perform an authenticated HTTP POST.

Generic Python example:

```python
import os

import httpx


MOTH_URL = os.environ["MOTH_URL"]
MOTH_API_TOKEN = os.environ["MOTH_API_TOKEN"]


def submit_flag(
    flag: str,
    service: str | None = None,
    source: str | None = None,
) -> dict:
    response = httpx.post(
        f"{MOTH_URL}/api/flags",
        headers={
            "Authorization": (
                f"Bearer {MOTH_API_TOKEN}"
            ),
        },
        json={
            "flag": flag,
            "service": service,
            "source": source,
        },
        timeout=5.0,
    )

    response.raise_for_status()

    return response.json()
```

Do not hardcode the API token directly into exploit repositories.

Use the runtime environment.

---

## Supported Flag Shape

```text
FAUST_[A-Za-z0-9/+]{32}
```

Example:

```text
FAUST_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
```

Malformed authenticated flags receive HTTP `422`.

---

## Response Handling

### Successful submission

```json
{
  "status": "submitted",
  "code": "OK",
  "message": "accepted",
  "remembered": true
}
```

### Local duplicate

```json
{
  "status": "duplicate",
  "code": "LOCAL",
  "message": "mof has already seen this offering",
  "remembered": true
}
```

No second backend submission occurs.

### Retryable backend result

Example:

```json
{
  "status": "submitted",
  "code": "ERR",
  "message": "try again later",
  "remembered": false
}
```

The flag remains retryable.

### Connection failure

```text
502 Bad Gateway
```

The flag is not permanently remembered.

### Backend timeout

```text
504 Gateway Timeout
```

The flag is not permanently remembered.

---

## Local Fake Gameserver

Use this during development instead of contacting competition infrastructure.

```powershell
@'
import asyncio


async def handle_client(reader, writer):
    print("mof arrived at fake gameserver")

    writer.write(
        b"Welcome to fake moth gameserver\n\n"
    )
    await writer.drain()

    flag = await reader.readline()
    flag_text = flag.decode().strip()

    print("received:", flag_text)

    writer.write(
        f"{flag_text} OK accepted\n".encode()
    )
    await writer.drain()

    writer.close()
    await writer.wait_closed()


async def main():
    server = await asyncio.start_server(
        handle_client,
        "127.0.0.1",
        6666,
    )

    print(
        "fake gameserver listening "
        "on 127.0.0.1:6666"
    )

    async with server:
        await server.serve_forever()


asyncio.run(main())
'@ | python -
```

---

## Fake Silent Backend

For timeout testing:

```powershell
@'
import asyncio


async def handle_client(reader, writer):
    print(
        "mof connected, pretending to be asleep"
    )

    await asyncio.sleep(60)

    writer.close()
    await writer.wait_closed()


async def main():
    server = await asyncio.start_server(
        handle_client,
        "127.0.0.1",
        6666,
    )

    print(
        "sleepy gameserver listening "
        "on 127.0.0.1:6666"
    )

    async with server:
        await server.serve_forever()


asyncio.run(main())
'@ | python -
```

Expected API behavior:

```text
504 Gateway Timeout
```

The same flag should remain eligible for retry afterward.

---

## Health Endpoint

Current health endpoint:

```text
GET /api/health
```

Current development response:

```json
{
  "status": "alive",
  "mori": "watching",
  "moth": "awake"
}
```

Note that health endpoint authentication behavior may evolve as deployment design is finalized.

---

## Competition Deployment

### Final values

```text
MOTH host:
TODO

MOTH port:
TODO

Submission backend host:
TODO

Submission backend port:
TODO

Transport:
TODO

Startup method:
TODO

Restart policy:
TODO

Log location:
TODO
```

Fill these values only after the final deployment design is decided.

---

## Team Token Distribution

Final token-distribution method:

```text
TODO
```

Requirements:

* never post tokens into public repositories
* never place tokens into screenshots
* never embed tokens into exploit source
* never reuse `MOTH_DB_KEY`
* rotate the API token if exposure is suspected

---

## Competition-Day Startup Checklist

```text
[ ] Correct private branch checked out
[ ] Working tree clean
[ ] Latest TTZ changes pulled
[ ] Tests passing
[ ] MOTH_DB_KEY configured
[ ] MOTH_API_TOKEN configured
[ ] Submission host configured
[ ] Submission port configured
[ ] Timeout configured
[ ] Correct network path available
[ ] MOTH API started
[ ] Health endpoint checked
[ ] Authentication checked
[ ] Test flag path checked where safe
[ ] Logs visible
```

---

## Competition-Day Sanity Check

Before teammates begin sending flags:

1. Verify MOTH is running.
2. Verify MORI rejects a request with no token.
3. Verify the correct token reaches flag validation.
4. Verify submission backend connectivity.
5. Verify the database is writable.
6. Verify no secrets are printed into logs.
7. Verify teammates know the current MOTH endpoint.
8. Verify exploit scripts use environment variables for credentials.

---

## Troubleshooting

### `401`

Likely causes:

* no Bearer token
* wrong token
* malformed Authorization header

MORI has swatted the request.

### `422`

Authentication succeeded, but the flag is malformed.

Check the FAUST flag shape.

### `502`

MOTH could not establish or maintain the backend connection.

Check:

* backend availability
* routing
* configured host
* configured port

The flag remains retryable.

### `504`

The backend connection was established but did not answer within the configured timeout.

The flag remains retryable.

### Local duplicate

MOTH already remembers the flag as terminal.

It will not submit it again.

### `MOTH_API_TOKEN is missing`

The server authentication configuration is incomplete.

MORI refuses to fail open.

### `MOTH_DB_KEY is missing`

Database cryptographic configuration is incomplete.

Do not replace the key casually if an existing encrypted database needs to remain readable.

---

## Logs and Secrets

Do not log:

```text
MOTH_API_TOKEN
MOTH_DB_KEY
Authorization headers
private SSH keys
```

Treat captured flags as sensitive competition data.

Avoid unnecessary plaintext exposure.

---

## Database

Default local database:

```text
moth.db
```

This file is ignored by Git.

Do not commit it.

The current database stores encrypted flag material and keyed fingerprints.

Future versions will add richer submission state.

---

## Git Workflow

Active private repository:

```text
ttz
```

Public snapshot:

```text
origin
```

Before coding:

```powershell
git status
git pull
```

After testing:

```powershell
git add .
git commit -m "mof did something suspiciously functional"
git push
```

Plain `git push` should target TTZ.

Never casually run:

```powershell
git push origin main
```

during private competition development.

---

## Signed Commits

Future MOTH commits should be SSH-signed.

Verify repository configuration:

```powershell
git config --get gpg.format
git config --get user.signingkey
git config --get commit.gpgsign
```

Expected:

```text
ssh
<SSH signing public key>
true
```

Do not share the private signing key.

---

## After the Competition

Once FAUST is over, we can decide what to publish back to the public repository.

Possible post-competition publication:

* final architecture
* operational lessons
* deployment design
* failure modes
* interesting bugs
* benchmarks
* retrospective
* cleaned competition runbook

Do not automatically push the private TTZ history to GitHub.

Review it first.

```text
/•᷅‎‎•᷄\੭

MORI says:
review before publishing.
```

---

## Emergency Rule

If something looks wrong and you are not sure whether MOTH is safely submitting flags:

```text
stop sending new traffic
check logs
check configuration
check network connectivity
check with the team
```

Do not blindly restart, rotate keys, delete the database, or change submission state during the competition without understanding what failed.

Mof is small.

Please do not panic the moth.

```text
ཐི༏ཋྀ
```
