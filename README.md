# MOTH

**Multi-Operator Transmission Hub**

```text
ཐི༏ཋྀ    ཐིཋྀ    ʚïɞ    ᖭི༏ᖫྀ

࿔‧ ֶָ֢˚˖𐦍˖˚ֶָ֢ ‧࿔

⁺‧₊˚ ཐི⋆♱⋆ཋྀ ˚₊‧⁺
```

> A small flag relay for attack-defense CTFs, supervised by MORI and operated by one increasingly capable moth.

MOTH is a lightweight FastAPI service for receiving captured flags from multiple operators or exploit scripts, validating and deduplicating them, storing them securely, and forwarding them to a CTF submission server.

The project is currently being built for FAUST CTF 2026.

MOTH is intentionally small, understandable, and boring where security matters.

The moth jokes are not considered part of the threat model.

---

## Current Status

```text
𐔌՞. .՞𐦯
```

MOTH currently supports:

* FastAPI HTTP API
* Pydantic request validation
* official FAUST 2026 flag-format validation
* encrypted local flag storage
* keyed duplicate detection
* local duplicate suppression
* asynchronous TCP flag submission
* FAUST-style response parsing
* configurable submission host, port, and timeout
* connection timeout handling
* response timeout handling
* connection failure handling
* distinction between retryable and terminal submission results
* pytest-based automated testing
* disposable temporary databases during tests
* full localhost end-to-end testing with a fake gameserver
* retry-safe HTTP 502 handling
* retry-safe HTTP 504 handling

Current automated test status:

```text
23 passed
```

The complete local path has also been manually tested:

```text
HTTP request
    ↓
FAUST flag validation
    ↓
duplicate check
    ↓
TCP submission
    ↓
fake gameserver
    ↓
submission response
    ↓
encrypted storage
    ↓
HTTP response
```

A second submission of the same flag is detected locally and does not reach the gameserver again.

Malformed flags are rejected before MOTH attempts a network connection.

---

## What MOTH Is For

During an attack-defense CTF, several people and automated exploits may discover flags at the same time.

Without a central relay, every tool needs to independently handle:

* submission server connections
* duplicate detection
* retries
* response parsing
* secrets
* logging
* submission state

MOTH provides one small service between the team and the gameserver.

```mermaid
flowchart LR
    A[Exploit Script] --> M[MOTH]
    B[Operator] --> M
    C[Another Tool] --> M

    M --> V[Flag Validation]
    V --> D[Local Duplicate Check]
    D --> S[TCP Submitter]
    S --> G[Gameserver]

    G --> S
    S --> E[Encrypted SQLite Storage]
    S --> M
```

Exploit scripts only need to know how to send a flag to MOTH.

Mof handles the rest.

```text
ཐི༏ཋྀ
```

---

## Architecture

MOTH currently consists of four main pieces.

```mermaid
flowchart TB
    API[FastAPI API]

    CONFIG[Configuration]
    DB[Encrypted SQLite Storage]
    SUB[TCP Submitter]

    API --> CONFIG
    API --> DB
    API --> SUB

    SUB --> GS[Submission Server]
```

### API

FastAPI receives flags from operators and exploit scripts.

Current endpoint:

```text
POST /api/flags
```

Example request:

```json
{
  "flag": "FAUST_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
  "service": "example-service",
  "source": "exploit-script"
}
```

`service` and `source` are currently accepted as metadata but are not yet persisted.

---

## FAUST Flag Validation

```text
⁺‧₊˚ ཐི⋆♱⋆ཋྀ ˚₊‧⁺
```

MOTH validates incoming flags before duplicate checks or network submission.

The current FAUST 2026 format is:

```text
FAUST_[A-Za-z0-9/+]{32}
```

This means a flag must:

* start with `FAUST_`
* contain exactly 32 characters after the prefix
* contain only letters, digits, `/`, or `+` after the prefix

MOTH uses a full regular-expression match so additional data before or after the flag is rejected.

Example valid shape:

```text
FAUST_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
```

Example rejected shapes:

```text
FAUST_TOO_SHORT
MOTH_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
FAUST_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA!
```

Invalid flags are rejected by Pydantic with HTTP `422`.

They never reach the TCP submission layer.

```mermaid
flowchart TD
    A[Incoming Flag] --> B{Valid FAUST Format?}

    B -->|No| C[HTTP 422]
    B -->|Yes| D[Duplicate Check]

    C --> E[No TCP Connection]
    D --> F[Continue Processing]
```

Mof has standards now.

---

## Flag Processing

A new flag currently moves through MOTH like this:

```mermaid
flowchart TD
    A[Receive flag] --> B[Validate FAUST format]
    B --> C[Calculate keyed fingerprint]
    C --> D{Already stored?}

    D -->|Yes| E[Return local duplicate]

    D -->|No| F[Connect to submission server]
    F --> G[Send flag]
    G --> H[Read response]
    H --> I[Parse response code]

    I --> J{Terminal result?}

    J -->|Yes| K[Encrypt and store flag]
    J -->|No| L[Leave flag retryable]

    K --> M[Return result]
    L --> M
```

This ordering is intentional.

MOTH does not permanently remember a flag before attempting submission.

If the submission server cannot be reached, the flag remains eligible for another attempt.

---

## Duplicate Detection

MOTH does not need to decrypt every stored flag to determine whether a new flag has already been seen.

Instead, every flag receives a deterministic keyed fingerprint.

```mermaid
flowchart LR
    F[Plaintext Flag] --> H[HMAC-SHA256]
    K[Derived Fingerprint Key] --> H
    H --> FP[Fingerprint]
```

The fingerprint is stored in SQLite with a `UNIQUE` constraint.

This allows MOTH to efficiently answer:

> Have I seen this offering before?

without storing the plaintext flag.

Because the fingerprint uses HMAC with a secret key, a database-only attacker cannot directly perform the same offline guessing attacks that would be possible against ordinary unkeyed hashes.

---

## Encrypted Storage

```text
ʚïɞ
```

Flags are encrypted before being written to SQLite.

MOTH currently uses:

* AES-256-GCM
* random 12-byte nonces
* a 256-bit master key
* HKDF-SHA256 for key separation
* HMAC-SHA256 for duplicate fingerprints

The database stores:

```text
id
flag_ciphertext
flag_nonce
flag_fingerprint
```

It does not intentionally store plaintext flags.

The plaintext absence is also covered by an automated test.

```mermaid
flowchart LR
    MASTER[MOTH_DB_KEY]

    MASTER --> HKDF[HKDF-SHA256]

    HKDF --> ENC[Encryption Key]
    HKDF --> FP[Fingerprint Key]

    FLAG[Flag]

    FLAG --> AES[AES-256-GCM]
    ENC --> AES
    AES --> CT[Ciphertext]

    FLAG --> HMAC[HMAC-SHA256]
    FP --> HMAC
    HMAC --> HASH[Fingerprint]

    CT --> DB[(SQLite)]
    HASH --> DB
```

---

## Key Separation

MOTH uses one master secret but derives separate keys for separate cryptographic purposes.

```mermaid
flowchart TB
    MASTER[MOTH_DB_KEY]

    MASTER --> A[HKDF]
    MASTER --> B[HKDF]

    A --> ENC[Flag Encryption Key]
    B --> FP[Flag Fingerprint Key]
```

The encryption key is never reused directly as the fingerprint key.

This prevents two unrelated cryptographic operations from sharing identical key material.

---

## Secrets

The database master key is provided through:

```text
MOTH_DB_KEY
```

It must decode to exactly 32 bytes.

The key belongs to the MOTH server.

Clients submitting flags do not need access to it.

A generated key may be stored in a local `.env` file during development.

`.env` is excluded from Git.

Never commit the database key.

---

## MORI Is Watching

```text
/•᷅‎‎•᷄\੭
```

MORI does not submit flags.

MORI watches the nest.

```mermaid
flowchart LR
    CLIENT[Team Client]
    API[MOTH API]
    SECRET[MOTH_DB_KEY]
    DB[(Encrypted SQLite)]
    GS[Submission Server]

    CLIENT --> API
    API --> DB
    API --> GS
    SECRET --> API
```

Clients should never receive the database encryption key.

MORI considers unnecessary secret sharing suspicious.

```text
/•᷅‎‎•᷄\੭
```

---

## Submission Configuration

The TCP submitter is configured through environment variables.

```text
MOTH_SUBMISSION_HOST
MOTH_SUBMISSION_PORT
MOTH_SUBMISSION_TIMEOUT
```

Safe development defaults are:

```text
MOTH_SUBMISSION_HOST=127.0.0.1
MOTH_SUBMISSION_PORT=6666
MOTH_SUBMISSION_TIMEOUT=5.0
```

The localhost default is deliberate.

Running MOTH without submission configuration should not accidentally send anything to external infrastructure.

During development, the submitter is pointed at a local fake gameserver.

---

## Submission Client

```text
ᖭི༏ᖫྀ
```

The submission client uses Python's asynchronous networking support.

Its basic flow is:

```mermaid
sequenceDiagram
    participant M as MOTH
    participant G as Gameserver

    M->>G: Open TCP connection
    G-->>M: Welcome banner
    M->>G: FLAG + newline
    G-->>M: FLAG CODE message
    M->>M: Parse response
    M->>G: Close connection
```

A submission response is represented internally as:

```python
SubmissionResult(
    flag="...",
    code="OK",
    message="accepted",
)
```

MOTH validates the structure of the response separately from the meaning of the response code.

Uppercase ASCII response codes are accepted structurally so that a future gameserver response code does not automatically break the parser.

---

## Submission Results

Known terminal response codes currently include:

```text
OK
DUP
OWN
OLD
INV
```

Terminal results cause MOTH to remember the flag locally.

A gameserver error such as:

```text
ERR
```

does not cause the flag to be permanently remembered, allowing it to be retried later.

Unknown response codes are also not automatically treated as terminal.

This keeps MOTH conservative when the gameserver says something she does not understand.

New species of lämp require observation before classification.

---

## Network Failure Handling

### Connection could not be established

Possible internal errors include:

```text
mof flew toward the lämp, but there was no lämp
```

or:

```text
mof flew toward the lämp, but could not find it
```

The API converts submission connection failures into:

```text
HTTP 502 Bad Gateway
```

The flag is not remembered.

This has been manually verified end to end.

After a `502`, restarting the fake gameserver and submitting the same flag again successfully sends the flag.

---

### Connection exists but the server stops responding

Example internal error:

```text
mof waited for the lämp, but it never answered
```

The API converts submission timeouts into:

```text
HTTP 504 Gateway Timeout
```

The flag is not remembered.

This has also been manually verified end to end.

After a `504`, replacing the silent server with a working fake gameserver and submitting the same flag again succeeds.

---

### Connection disappears unexpectedly

MOTH also detects when a server closes the connection before returning a submission response.

The TCP writer is closed in cleanup code even when submission fails.

Mof does not leave abandoned sockets lying around the nest.

```text
𐔌՞. .՞𐦯
```

---

## API Responses

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

A locally detected duplicate never reaches the submission server again.

### Retryable gameserver result

```json
{
  "status": "submitted",
  "code": "ERR",
  "message": "try again later",
  "remembered": false
}
```

The flag remains eligible for another submission attempt.

---

## Development Setup

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install development dependencies:

```powershell
pip install -r requirements-dev.txt
```

Create a local `.env` containing the database key and optional submission configuration.

Example:

```text
MOTH_DB_KEY=<your-secret-key>

MOTH_SUBMISSION_HOST=127.0.0.1
MOTH_SUBMISSION_PORT=6666
MOTH_SUBMISSION_TIMEOUT=2.0
```

Do not copy a database key from documentation or another installation.

Generate your own.

---

## Running MOTH

Start the development server with:

```powershell
uvicorn app.main:app --reload
```

The API is then available locally at:

```text
http://127.0.0.1:8000
```

FastAPI's interactive API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

---

## Testing

```text
࿔‧ ֶָ֢˚˖𐦍˖˚ֶָ֢ ‧࿔
```

Run the complete test suite with:

```powershell
pytest -v
```

The current suite covers:

* empty flag rejection
* valid FAUST flag acceptance
* short malformed flag rejection
* incorrect flag prefix rejection
* invalid flag character rejection
* duplicate detection
* keyed flag memory checks
* absence of plaintext flags in SQLite
* response parsing
* malformed response rejection
* fake TCP submission
* socket cleanup
* silent server timeout
* connection failure
* connection establishment timeout
* safe localhost configuration defaults
* environment configuration
* invalid port handling
* invalid timeout handling
* successful API submission
* local duplicate suppression
* retryable gameserver errors
* HTTP 502 translation
* HTTP 504 translation

Current status:

```text
23 passed
```

---

## Disposable Science Nest

Database tests do not use the normal development database.

Pytest creates a temporary database using:

```text
tmp_path
```

The application's database path is redirected for the duration of the test.

```mermaid
flowchart LR
    P[pytest] --> T[Temporary Directory]
    T --> D[test_moth.db]

    P --> M[Monkeypatch DATABASE_PATH]
    M --> APP[MOTH Database Code]
    APP --> D
```

This allows tests to freely insert flags, create duplicates, and inspect raw database bytes without contaminating the normal MOTH database.

When the test finishes, pytest cleans up the temporary nest.

---

## Manual End-to-End Testing

MOTH has been manually tested against local fake gameservers.

```mermaid
flowchart LR
    PS[PowerShell Client]
    API[MOTH FastAPI]
    TCP[MOTH TCP Submitter]
    FAKE[Fake Gameserver]
    DB[(Encrypted SQLite)]

    PS -->|HTTP POST| API
    API --> TCP
    TCP -->|TCP flag submission| FAKE
    FAKE -->|Response| TCP
    TCP --> API
    API --> DB
    API --> PS
```

### Successful submission

A valid-shaped flag was submitted through the entire stack.

The fake gameserver received it and returned `OK`.

MOTH remembered the flag.

Submitting the same flag again returned a local duplicate without another TCP submission.

### Missing gameserver

A fresh flag was submitted while the fake gameserver was offline.

MOTH returned HTTP `502`.

After restarting the gameserver, submitting the same flag succeeded.

The failed attempt had not been remembered.

### Silent gameserver

A fake gameserver accepted the TCP connection but deliberately stopped responding.

MOTH returned HTTP `504`.

After replacing it with the normal fake gameserver, submitting the same flag succeeded.

The timed-out attempt had not been remembered.

### Invalid flag

The old development flag:

```text
FAUST_END_TO_END_MOF_001
```

was submitted after strict flag validation was introduced.

MOTH rejected it before networking with:

```text
mof does not recognize this as a FAUST flag
```

A correctly shaped flag was then accepted and submitted normally.

```text
ཐིཋྀ
```

---

## Project Structure

```text
MOTH/
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py
│   │   └── flags.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── crypto.py
│   │   └── submitter.py
│   └── db/
│       ├── __init__.py
│       └── database.py
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_flags.py
│   └── test_submitter.py
├── .gitignore
├── pytest.ini
├── requirements.txt
└── requirements-dev.txt
```

---

## Security Model

```text
/•᷅‎‎•᷄\੭
```

MOTH currently protects flag contents primarily against exposure from a copied or accidentally leaked SQLite database.

Application-layer encryption protects the flag ciphertext itself.

It does not hide all database metadata.

An observer with access to the database may still learn information such as:

* number of stored flags
* row identifiers
* ciphertext sizes
* fingerprints
* database schema

An attacker with full access to the MOTH host, process memory, or environment may also be able to recover the database key.

MOTH should therefore not treat application-layer database encryption as a replacement for host security.

The current design is defense in depth.

MORI remains concerned.

```text
/•᷅‎‎•᷄\੭
```

---

## Current Trust Boundary

At the moment, MOTH is designed for local development and trusted team infrastructure.

```mermaid
flowchart LR
    TEAM[Trusted Team Clients]
    API[MOTH API]
    SECRET[Server Secrets]
    DB[(Encrypted Database)]
    GS[Submission Server]

    TEAM --> API
    API --> SECRET
    API --> DB
    API --> GS
```

The database encryption key remains server-side.

Clients should never receive `MOTH_DB_KEY`.

API authentication has not yet been implemented.

MOTH should therefore not currently be exposed directly to an untrusted network.

That is the next major security boundary to add.

---

## Nest Residents

```text
ཐི༏ཋྀ
ཐིཋྀ
࿔‧ ֶָ֢˚˖𐦍˖˚ֶָ֢ ‧࿔
𐔌՞. .՞𐦯
⁺‧₊˚ ཐི⋆♱⋆ཋྀ ˚₊‧⁺
ʚïɞ
ᖭི༏ᖫྀ

/•᷅‎‎•᷄\੭
```

Classification remains disputed.

All residents appear to be authorized.

MORI is watching.

---

## Planned Work

```mermaid
flowchart TD
    A[Encrypted Storage ✓]
    B[Duplicate Detection ✓]
    C[TCP Submission ✓]
    D[Failure Handling ✓]
    E[API Integration ✓]
    F[API Failure End-to-End Tests ✓]
    G[FAUST Flag Validation ✓]
    H[API Authentication]
    I[Submission State and Retry Queue]
    J[Operational Dashboard]

    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
    G --> H
    H --> I
    I --> J
```

### Near Term

Planned next steps include:

* add client authentication with `MOTH_API_TOKEN`
* keep the API token separate from `MOTH_DB_KEY`
* test authenticated and unauthenticated API requests
* reject invalid credentials before flag processing
* add persistent submission state
* design retry behavior

### Later

Possible later additions include:

* retry queue
* timestamps
* submission history
* service metadata
* source metadata
* concurrent workers
* structured logging
* metrics
* dashboard
* operator view
* rate limiting
* health information for the submission backend

---

## Mof Development Log

MOTH has been built in deliberately small checkpoints.

Notable discoveries so far:

```text
mof built a tiny nest
mof discovered fastapi
mof found the api
mori started watching the nest
mof learned what a flag looks like
mof refuses suspiciously empty offerings
mof found a memory box
mori taught mof to keep secrets
mof remembers without telling secrets
mof remembers repeat visitors
mof survived scientific poking
mof got a disposable science nest
mori checked under the floorboards
mof learned gameserver dialect
mof learned to speak tcp
mof learned when to stop staring at the lämp
mof learned the difference between silence and absence
mof learned where the lämp lives
mof learned to check the nest first
mof carried her first flag through the whole nest
mof learned what a real flag looks like
```

More incidents are expected.

---

## Why MOTH?

Because every attack-defense team eventually creates some cursed little script that forwards flags.

This one gets tests.

```text
⁺‧₊˚ ཐི⋆♱⋆ཋྀ ˚₊‧⁺

      lämp acquired

/•᷅‎‎•᷄\੭
```
