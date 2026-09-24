# Security Policy

## Scope

This is a portfolio/demo project. It is not intended for production use and processes **fictional data only**.

## Reporting a vulnerability

Please report vulnerabilities privately using GitHub's **"Report a vulnerability"** (private security advisory) feature on this repository. Do not open public issues for security problems.

Please include:
- a description of the issue and its impact,
- steps to reproduce,
- affected files or endpoints.

## Secrets

- The repository must never contain credentials, API keys, tokens, private keys or certificates.
- `.env.example` contains only non-secret local development defaults.
- CI runs a Gitleaks secret scan on every push and pull request.

See [docs/security-and-privacy.md](docs/security-and-privacy.md) for the design-level security and privacy considerations.

