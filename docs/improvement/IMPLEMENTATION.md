# Extraction and deployment improvement work

Baseline: web_data/REPORT.md, 27 October 2026. Original external predictions remain immutable.

Work requested: Groq-backed extraction; document preparation; receipt/amount schema; deterministic validation and evidence; fresh held-out evaluation; authentication/access controls, deployment, backups and monitoring.

Release gate: no claim of improved accuracy until real Groq responses have been scored. No unattended accounting posting. No public deployment until hosting/domain/secrets are configured and acceptance checks pass.

Track:
- [ ] Groq provider, bounded calls, immutable provenance and evidence validation
- [ ] Environment/secret loading and model-aware jobs
- [ ] Receipt, tip/service fee and distinct payable/balance amounts
- [ ] OCR robustness and locale normalization
- [ ] Authenticated deployment configuration and role enforcement
- [ ] Backup/restore integrity and operations diagnostics
- [ ] Provider/validation/security regression tests
- [ ] Baseline comparison and fresh external holdout with recorded responses

Credentials: GROQ_API_KEY in ignored project .env; never print or commit it. Public-source samples only for the initial API evaluation.
