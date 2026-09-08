# Contributing

Thanks for looking at TOR Analyzer. A few things this project is specific about.

## Running tests

```bash
cd backend
.venv/bin/python -m pytest tests/unit -q   # 120 tests, must stay green
```

Frontend type-check:

```bash
cd frontend
npx tsc -b
```

There's no CI configured yet — run both locally before opening a PR.

## The five rules

The extraction pipeline exists to enforce five rules, cited by number throughout
`schema.py`, `pricing.py`, `calculations.py`, and `client.py` (see the README's "Design
rules" section for the full list). A change that makes the model compute something, or
that lets a value through without a source/reason/confidence, is a rule violation even
if it makes the code shorter — don't relax a rule to make a model or provider pass.

## `schema.py` and `schema.ts` move together

`backend/app/models/schema.py` is the source of truth for the extraction call, the API
response, and the eval scorer, all at once. `frontend/src/types/schema.ts` is a
hand-maintained copy — there is no codegen. If your change touches `schema.py`, update
`schema.ts` in the same PR, or the two will drift silently and the frontend will either
break or silently mis-render a field.

Also: a change to `schema.py`'s shape invalidates the hand-annotated ground truth in
`backend/tests/expected/*.json`. Check whether your change requires updating those too.

## Adding a new document format or provider

This repo distinguishes **"verified against a real document"** from **"implemented and
unit-tested"** — see the README's capability matrix. Don't move a format or provider out
of "implemented, unverified" until it has actually been run against a real document and
the result checked by a human. A PR that adds a new format/provider should say plainly
which state it's landing in.

## Commit process

All commits in this repo go through the project's `/quick-commit` flow (interactive file
selection, message review, no `Co-Authored-By`). If you're using Claude Code against this
repo, that convention is documented in the repo's `CLAUDE.md` — please follow it rather
than committing directly.

## Licensing

This project is AGPL-3.0, forced by the PyMuPDF dependency (dual AGPL/commercial). Any
new dependency needs its license checked for AGPL compatibility before being added — see
the README's License section for what that means in practice.
