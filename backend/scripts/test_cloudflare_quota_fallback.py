"""One-shot check of the Cloudflare daily-quota degradation path.

Mocks a 429 "daily free allocation" response and verifies:
1. post_with_backoff fails FAST (no 1s/2s/4s retry storm on a hard quota).
2. generate_alert(require_live=True) raises CloudflareQuotaError once.
3. Afterwards the client is paused and serves labelled templates without
   touching the network again.
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, ".")

from app.services import cloudflare_client as cf
from app.services.provider_common import is_hard_quota_response

QUOTA_BODY = (
    '{"errors":[{"message":"AiError: you have used up your daily free '
    "allocation of 10,000 neurons, please upgrade to Cloudflare's Workers "
    'Paid plan","code":1005}],"success":false,"result":null}'
)


class FakeResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        import json
        return json.loads(self.text)


class FakeSession:
    headers: dict = {}

    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls = 0

    def post(self, url, **kwargs):  # noqa: ANN001, ANN003
        self.calls += 1
        return self.response


def main() -> int:
    failures: list[str] = []

    # 1. helper classification
    if not is_hard_quota_response(429, QUOTA_BODY):
        failures.append("is_hard_quota_response did not classify daily-allocation 429 as hard quota")
    if is_hard_quota_response(429, '{"error":"Rate limit reached. Please wait 30 seconds."}'):
        failures.append("Transient 429 misclassified as hard quota")

    client = cf.CloudflareClient.__new__(cf.CloudflareClient)
    client._api_token = "test-token"
    client._account_id = "test-account"
    client._model = "@cf/meta/llama-3.1-8b-instruct"
    client._max_tokens = 64
    client._session = FakeSession(FakeResponse(429, QUOTA_BODY))

    # 2. first live call must raise CloudflareQuotaError after ONE network try
    t0 = time.monotonic()
    try:
        client.generate_alert(require_live=True)
        failures.append("require_live call on quota exhaustion did not raise")
    except cf.CloudflareQuotaError as exc:
        print(f"  raised CloudflareQuotaError as expected: {str(exc)[:90]}...")
    elapsed = time.monotonic() - t0
    print(f"  elapsed={elapsed:.2f}s  network_calls={client._session.calls}")
    if elapsed > 2.0:
        failures.append(f"hard-quota path still retried (took {elapsed:.1f}s)")
    if client._session.calls != 1:
        failures.append(f"expected 1 network call, got {client._session.calls}")

    # 3. cooldown engaged, further alerts come from labelled templates with no I/O
    if not client.quota_paused:
        failures.append("quota_paused not set after quota error")
    calls_before = client._session.calls
    alert = client.generate_alert(require_live=True, inject_poison=True)
    if client._session.calls != calls_before:
        failures.append("client hit the network again while quota-paused")
    if alert.get("generated_by") != "template-quota-fallback":
        failures.append(f"wrong provenance tag: {alert.get('generated_by')}")
    if not alert.get("raw_payload", {}).get("description"):
        failures.append("template fallback produced an empty payload")

    print(f"  paused until {cf.quota_resets_at()}")
    print(f"  fallback alert: {alert['alert_type']} generated_by={alert['generated_by']}")

    if failures:
        print("\nFAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nPASS: fail-fast + cooldown + labelled template fallback all verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
