# Editable todo titles: live-team acceptance

This feature was implemented in an isolated checkout by a real four-agent Go
team (coordinator, researcher, worker, verifier), coordinated by a running ACAMS
server. Model calls used the operator-authorized authenticated Codex CLI; the
fixture model and authentication bypass were not used. The operator reviewed the
result, ran independent acceptance, and prepared this document/PR. Agents did not
commit, push, deploy, or externally accept their own work.

## Result

- Title-only and combined title/completion PATCH updates validate before mutation.
- Both stores preserve identity and omitted fields; SQLite renames survive restart.
- Inline editing supports Save/Enter and Cancel/Escape, validation, accessible
  labels/focus, safe text rendering, busy-state controls and failed-save retry.
- Existing add/complete/delete behavior remains covered. README describes the API
  and UI. Six new regression cases bring the suite from 11 to 17 distinct tests.

## Validation

Run from this checkout with Python 3.11+:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Observed final results:

| Check | Result |
| --- | --- |
| Project unittest discovery | PASS: 17 tests |
| Read-only operator API acceptance | PASS: 4 tests |
| JavaScript syntax (`node --check static/app.js`) | PASS |
| Actual Chromium interaction acceptance | PASS |
| ACAMS-side discovery/card/health/readiness, four agents | PASS |
| Independent verifier source stability/worker matching | PASS |
| Coordinator outcome | needs_review; external acceptance pending |

The external browser suite exercised add/edit, Enter/save, Cancel/Escape, invalid
input, completed todo edits, reload persistence, a deliberately failed PATCH with
draft retention and successful retry, HTML-like title rendering without execution,
delete, and mobile/desktop screenshots. It reported no browser JavaScript errors.
Operator tests used temporary databases and loopback listeners, never real todos.
The extra API/browser suites were operator-owned outside the worker write scope;
they are acceptance observations, not additional project runtime dependencies.
The in-repo UI unit case checks source safeguards; actual browser coverage above
is separate and was not represented as being executed by the Go verifier.

## Revisions and native evidence

- App starting revision: `426bcf0ee8bb6a85e84fba2054d4a29276e7c575`.
- ACAMS server revision: `68918aa639d80298b2990184a5646bc757d9dd29`.
- Final Go agent candidate source: `0f49815dacce9bbcb26093d8364171272f4881da`
  (`v0.1.0-live-citations.1`, clean unpublished archives; no published release claimed).
- Final ACAMS work task: `6fbdba87-1195-4107-84a3-25e1dd9cbf83`.
- Matching worker/verifier run:
  `4fcc5f8acea66ba4707cbd8cc71581fc46ce38deffcbd3054894764d44b4bd3a`.
- Matching selected-source digest:
  `41d88728beebb1192260a7352d232f8adb018f76e38a2f4296803418e1816e9b`.

The team implemented the code across explicit attempts. The final worker confirmed
that complete snapshot without further changes; the independent verifier then
reran all configured checks and assessed the same source. This document was added
after verification and is outside that native selected-source digest.

## Problems exposed and corrected

The exercise intentionally retained failures rather than replaying them:

1. The container readiness/API-key login commands used a flag unsupported by the
   pinned CLI's login subcommand. The container repository now shares supported
   command construction and tests the actual CLI syntax in credential-free CI.
2. Research/verifier models sometimes guessed incorrect citation line numbers.
   The generic adapter now presents exact captured numbered lines while retaining
   strict path/line/evidence validation; its Go race tests and CI passed.
3. The operator's test checkout initially had an incorrectly owned static
   directory, blocking UI writes after an API-only partial patch. Ownership was
   corrected, that partial patch inspected, and a distinct continuation completed
   it. Readiness now checks configured write-scope directories before model work.
4. The syntax command was initially silent on success, so the evidence gate
   correctly classified it unverified. A read-only wrapper runs the same real
   syntax check and prints success evidence. An oversized duplicated source index
   was removed from the handover. Old terminal registries were preserved before
   adopting the corrected check policy; task records were not rewritten.

Each corrected attempt was a distinct ACAMS work item after explicit state review.
The final successful run made no automatic replay, false pass or external task
acceptance. No model/Git credentials or raw authentication logs are committed.
Disposable containers, their temporary state/login volumes and private network are
removed after evidence capture. Production deployment, multi-host behavior and
load testing of this app are outside this feature exercise.
