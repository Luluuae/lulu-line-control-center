# Security policy

## Sensitive data

Never commit passwords, Streamlit secrets, API keys, database credentials, signing keys, employee documents, live SQLite files, or exported backups. Configure secrets only in the deployment platform and GitHub Actions encrypted secrets.

## Production data

The repository's SQLite support preserves the current application and local development workflow. A Streamlit Community Cloud filesystem is not durable multi-user production storage. Before broad staff rollout, migrate live data through a verified backup to a managed transactional database and private object storage. Keep the existing production database untouched until reconciliation and rollback checks pass.

## Reporting

Report suspected access or data issues privately to the Lulu Line system administrator. Do not place sensitive details in public GitHub issues.
