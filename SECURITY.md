# Security

## Reporting a vulnerability

Please report security issues by opening a private report via GitHub's
[Security Advisories](../../security/advisories/new) for this repository, rather than a
public issue. If that isn't available, open a regular issue asking a maintainer to reach
out for a private channel — don't post exploit details in the open issue itself.

## Never paste real API keys anywhere in an issue, PR, or advisory

This project is bring-your-own-key: you supply your own Anthropic/OpenAI/Gemini/
OpenAI-compatible API key via `.env` (never committed — see `.gitignore`). If you're
reporting a bug that involves an error message containing part of a key, redact it
first. A key pasted into a public issue should be treated as compromised — rotate it
immediately, don't wait for someone to tell you.

## Scope

This is a v0.1, self-hosted tool with no accounts, no multi-tenant deployment, and no
hosted service operated by the maintainers. The realistic security surface is: the
FastAPI backend (`backend/app/api/`), file parsing of untrusted uploads (PyMuPDF,
python-docx, openpyxl), and whatever LLM provider credentials you configure. Reports
about any of these are welcome.
