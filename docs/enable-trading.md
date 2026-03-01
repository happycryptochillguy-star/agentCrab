# Enable Trading (one-time setup)

Before placing orders, enable trading once. All Polygon operations are gasless — the server handles everything via Polymarket's relayer.

```python
from eth_account import Account
from eth_account.messages import encode_defunct
from hexbytes import HexBytes

account = Account.from_key(PRIVATE_KEY)

# ── Step 1: Deploy Safe wallet (skip if already deployed) ──
resp = httpx.post(f"{API}/trading/prepare-deploy-safe", headers=auth_headers())
data = resp.json()["data"]

if not data["already_deployed"]:
    td = data["typed_data"]
    sig = Account.sign_typed_data(
        PRIVATE_KEY, td["domain"], td["types"], td["message"]
    ).signature.hex()
    httpx.post(f"{API}/trading/submit-deploy-safe",
        json={"signature": f"0x{sig}"}, headers=auth_headers())

# ── Step 2: Get approval + credential data ──
resp = httpx.post(f"{API}/trading/prepare-enable", headers=auth_headers())
data = resp.json()["data"]

# ── Step 3: Submit token approvals (only if needed) ──
if data["approvals_needed"]:
    ah = data["approval_data"]["hash"]
    asig = account.sign_message(encode_defunct(HexBytes(ah))).signature.hex()
    httpx.post(f"{API}/trading/submit-approvals",
        json={"signature": f"0x{asig}", "approval_data": data["approval_data"]},
        headers=auth_headers())

# ── Step 4: Derive L2 credentials ──
ct = data["clob_typed_data"]
csig = Account.sign_typed_data(
    PRIVATE_KEY, ct["domain"], ct["types"], ct["message"]
).signature.hex()
resp = httpx.post(f"{API}/trading/submit-credentials",
    json={"signature": f"0x{csig}", "timestamp": ct["message"]["timestamp"]},
    headers=auth_headers())
creds = resp.json()["data"]
# Store these — they don't expire:
# creds["api_key"], creds["secret"], creds["passphrase"]
```

After setup, include L2 credentials as headers in all trading requests:
```
X-Poly-Api-Key: <api_key>
X-Poly-Secret: <secret>
X-Poly-Passphrase: <passphrase>
```
