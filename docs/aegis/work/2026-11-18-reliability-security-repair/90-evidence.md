# Reliability and Security Repair - Evidence


## EvidenceBundleDraft: verification

- Artifact key: full-regression
- Slice ID: verification
- Type: test
- Source: ./.venv/bin/pytest -q
- Summary: 164 tests passed after all security, indexing, deletion, restart, and compose fixes.
- Verifier: pytest
- Evidence status: evidence-finalized

## EvidenceBundleDraft: deployment-config

- Artifact key: compose-validation
- Slice ID: deployment-config
- Type: validation
- Source: docker compose -f compose.yaml config; docker compose -f docker-compose.yml config
- Summary: Both Compose variants parse with localhost-only port binding and an explicit admin-token requirement.
- Verifier: docker-compose
- Evidence status: evidence-finalized
