# Lulu Line Control Center — Security Notes

## Required before production use
1. Keep the GitHub repository PRIVATE.
2. In Streamlit App Settings → Secrets add:
   BOOTSTRAP_ADMIN_PASSWORD = "Use-a-strong-unique-password-here"
3. Never commit `.streamlit/secrets.toml`, database files, backups, passwords or API keys.
4. Each employee must use an individual login. Do not share one username.
5. Disable accounts immediately when staff leave.
6. Review the Audit Trail regularly.
7. Download backups regularly until a managed persistent database is connected.

## Built-in controls
- PBKDF2-SHA256 password hashing (600,000 iterations)
- 12-character complex password policy
- Temporary-password forced change
- 5 failed attempts → 15-minute lock
- 30-minute inactivity timeout
- Role-based access
- Account enable/disable, role change, unlock and admin reset
- Audit trail
- Duplicate passport/document/payroll/expense protections
- PRO/Visa limited desk without salary/commission exposure

## Important storage note
SQLite on Streamlit Community Cloud is not a production-grade permanent database. For real long-term company use, connect a managed persistent database before relying on the app as the sole record system.
