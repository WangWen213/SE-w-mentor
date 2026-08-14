# SE-Mentor Final Status

Repository: https://github.com/WangWen213/SE-w-mentor

Production: https://47.76.106.57

Final release reference: annotated tag `submission-2026-08-14` at the final closeout HEAD. The exact
immutable SHA and GitHub run URLs are reported by the final closeout report because a commit cannot
embed its own future SHA.

## Runtime Profiles

- `LOCAL_FULL`
- `CLOUD_DEMO`
- `ONLINE_SAFE`

## Verified

- Production HTTPS and ONLINE_SAFE runtime.
- GitHub Release CI and Release Gate.
- Automatic Production Deploy via `workflow_run`.
- Local deterministic real Harness CREATE_FILE acceptance.
- Unauthorized write fail-closed.
- Frontend recovery stability: type-check PASS and targeted 13 tests PASS (`4cef1ee`).
- Deterministic Mechanism Demo: focused 3 tests PASS and CLI scenarios 3/3 PASS (`7e40490`).

## Partially Verified

- Public real-provider browser execution reached Execution, then failed closed with
  `policy denied: outside_policy`; full ZIP → modified ZIP is not fully verified.

## Known Limitations

1. Small ZIP upload is verified; a larger ZIP can be rejected by public Nginx with HTTP 413 before
   Backend bounded ZIP validation.
2. Missing ONLINE_SAFE credential can still surface a raw provider/credential error instead of a
   Settings preflight UX.
3. One provider-compatible HTTP 402 was observed; manual retry succeeded and the upstream cause was
   not established.
4. The rejected `outside_policy` AgentAction path was not retained, so the exact scope-contract root
   cause remains unproven.
5. Full-tree strict mypy and the historical full backend suite retain debt tracked by the separate
   Repository Health workflow.
6. TLS renewal automation remains an operational follow-up if it has not been finalized externally.
