# ShipGate interview walkthrough (5–8 minutes)

This is an implementation demo, **not** a claim of production deployment.
It was built with AI-assisted coding and engineering review. The applicant should be
prepared to explain the trade-offs, the API, tests, and the remaining validation gates.

## 1. Run and inspect

1. Follow the SQLite quick-start commands in [README](../README.md).
2. Open `/docs` on localhost or inspect the OpenAPI schema.
3. Provision a tenant's admin, operator, and three approver keys; store tokens securely.

## 2. Explain the use case

- A green build alone does not demonstrate authorized deployment.
- ShipGate tracks the release artifact digest, required independent approvals,
  explicit state transitions, and recorded evidence.
- One tenant's admins cannot enumerate or mutate other tenants' projects or policies.

## 3. Show the v0.3 policy flow

- `GET /v1/projects/{project_id}/policies` shows all nine environment/risk rules.
- Admin `PUT /v1/projects/{project_id}/policies/production/high` with
  `{"min_approvals":3,"expected_version":0}` creates a policy at version 1.
- A second write with `expected_version:0` returns **409 Conflict**; below-baseline
  quorum returns **422**.
- Create a release with a unique `Idempotency-Key`. The response snapshots
  `required_approvals:3`, `policy_source:project`, `policy_version:1`.
- Update policy to four approvals using `expected_version:1`; the original release
  still requires three. New releases require four.
- Verify `/v1/audit/verify` and `policy.updated` audit events.

## 4. Engineering decisions to defend

| Decision | Reason | Trade-off |
| --- | --- | --- |
| Immutable release quorum | Avoid retroactive authorization changes | Future policy tightening does not alter in-flight releases |
| PostgreSQL project-row lock | Serialize same-scope policy creation and new release snapshot | Longer transaction lock duration |
| Immutable baseline safety floor | Prevent accidentally removing required production approvals | Cannot configure a less strict project rule |
| Optimistic policy versions | Stale update conflict is explicit | Caller needs read-before-write or retry logic |
| Actor-key-based reviewer identity | Simple integration for machine service accounts | Key rotation does not link reviews to a stable human identity; SSO needed |
| Hash-linked audit chain | Detect modifications with externally anchored head | DB superuser could rewrite chain and head without external anchoring |

## 5. Validation honesty

Run `pytest -q --cov=shipgate`; SQLite tests cover workflows and isolation.
Real PostgreSQL migration and concurrent-lock behavior must be validated through
CI infrastructure before this is production-qualified. Neither this demo nor
`completion_evidence` is proof of an external deployment.

## 6. Suggested next work (for live AI-assisted coding session)

- Connect an OIDC identity to review approvals to prevent one human from approving
  through several independently issued keys.
- Add policy simulation to evaluate a proposed policy against draft releases.
- Add independently verifiable audit anchoring (S3 Object Lock or external transparency log).
- Load and failure-test PostgreSQL release/policy concurrent writes and retries.
