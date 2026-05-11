# Security policy

## Supported versions

`ambesa-bench` is pre-1.0. Only the `main` branch is supported. Security fixes ship as patch releases against the latest tag.

## Reporting a vulnerability

Please report security issues privately via **GitHub Security Advisories** rather than a public issue:

https://github.com/ambesaenterprise/ambesa-bench/security/advisories/new

This is a private channel that only the project maintainers can read. Public issues are visible to everyone immediately and are not appropriate for vulnerability reports.

When reporting, include:

- A description of the vulnerability.
- The version / commit SHA you observed it on.
- Steps to reproduce.
- (Optional) a suggested fix or mitigation.

You should receive an acknowledgement within 7 days. Triage and fix timing depends on severity:

| Severity | Triage | Fix target |
|---|---|---|
| Critical (RCE, auth bypass) | 24h | 7 days |
| High (data leak, sandbox escape in tool surface) | 72h | 30 days |
| Medium (DoS, info disclosure) | 7 days | 90 days |
| Low (hardening) | 14 days | Best-effort |

## Out of scope

- Vulnerabilities in third-party dependencies (`anthropic`, `pydantic`, `click`, `pyyaml`, `structlog`, `dbt-core`, `dbt-duckdb`). Report those upstream; we'll bump our pins once upstream releases a fix.
- Issues that require an attacker with shell access to the machine running the bench.
- Theoretical attacks on the LLM provider (prompt injection, model jailbreaks) — by design the bench runs models against untrusted-by-default inputs from dbt artifacts; the agent's tool surface and `_lab_filter` are the mitigations. Report concrete agent-level escapes (e.g., reading `expected.yaml` despite `_lab_filter`) as bugs.

## Coordinated disclosure

If you report a vulnerability via the channel above, we'll coordinate a disclosure timeline with you before any public advisory. Default: 90-day embargo from the date a fix is available, or earlier if the report is already public.

## Hall of fame

Security reporters who follow this policy and contribute to a published advisory will be credited in the advisory and in the project's release notes (unless they request otherwise).
