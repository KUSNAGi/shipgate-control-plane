# End-to-end API walk-through

The commands below require `API_KEY` from a local bootstrap and `jq` for extracting IDs.
Never paste API keys into a public PR, a screenshot, or terminal recording.

Start the API and provision a tenant as explained in README. Then:

```bash
BASE=http://127.0.0.1:8000
PROJECT=$(curl -fsS -X POST "$BASE/v1/projects" \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"slug":"revenue-services","description":"Revenue services"}' | jq -r .id)
OPERATOR=$(curl -fsS -X POST "$BASE/v1/keys" \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"label":"release-operator","role":"operator"}' | jq -r .key)
REVIEWER_A=$(curl -fsS -X POST "$BASE/v1/keys" \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"label":"security-reviewer","role":"approver"}' | jq -r .key)
REVIEWER_B=$(curl -fsS -X POST "$BASE/v1/keys" \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"label":"operations-reviewer","role":"approver"}' | jq -r .key)
SHA=$(printf 'a%.0s' {1..64})
RELEASE=$(curl -fsS -X POST "$BASE/v1/releases" \
  -H "X-API-Key: $OPERATOR" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: release-2026-001' \
  -d "{\"project_id\":\"$PROJECT\",\"environment\":\"production\",\"risk\":\"high\",\"artifact_sha256\":\"$SHA\",\"description\":\"Roll out approved payments release with evidence\"}" | jq -r .id)
curl -fsS -X POST "$BASE/v1/releases/$RELEASE/submit" \
  -H "X-API-Key: $OPERATOR" -H 'Content-Type: application/json' \
  -d '{"expected_version":1}'
curl -fsS -X POST "$BASE/v1/releases/$RELEASE/reviews" \
  -H "X-API-Key: $REVIEWER_A" -H 'Content-Type: application/json' \
  -d '{"expected_version":2,"decision":"approve","note":"Security reviewed"}'
curl -fsS -X POST "$BASE/v1/releases/$RELEASE/reviews" \
  -H "X-API-Key: $REVIEWER_B" -H 'Content-Type: application/json' \
  -d '{"expected_version":3,"decision":"approve","note":"Ops reviewed"}'
curl -fsS -X POST "$BASE/v1/releases/$RELEASE/complete" \
  -H "X-API-Key: $OPERATOR" -H 'Content-Type: application/json' \
  -d "{\"expected_version\":4,\"observed_artifact_sha256\":\"$SHA\",\"evidence_url\":\"https://ci.example.org/build/142\"}"
curl -fsS "$BASE/v1/audit/verify" -H "X-API-Key: $API_KEY"
```

The example `ci.example.org` address is illustrative, **not** evidence of a real deployment.
Do not record a completed release until the external deployment has genuinely happened.

## Idempotent release creation responses

`POST /v1/releases` uses the request's `Idempotency-Key` header to avoid creating
multiple releases on retried requests. The response distinguishes the outcomes:

| Outcome | HTTP status | `Idempotency-Replayed` |
| --- | --- | --- |
| Newly created release | `201 Created` | `false` |
| Same key, actor, and payload replay | `200 OK` | `true` |
| Same key reused with a different payload | `409 Conflict` | Not set |

A successful replay returns the **current** state of the existing release; it does
not repeat the original transition or append another `release.created` audit event.
Clients should use the returned resource ID and version rather than assuming the
release is still in draft state. Keys are scoped to the authenticated actor and tenant.
