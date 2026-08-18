# Lulu Line Control Center — Full Final Security Build

Main entry point: `app.py`

## Roles
Admin, Partner, Manager, Accountant, PRO, HR, Project, Fleet.

## First deployment
Set `BOOTSTRAP_ADMIN_PASSWORD` in Streamlit Secrets before starting with a fresh database.

## Data policy
The application is designed for manual data entry with duplicate controls. Do not commit live database or employee documents to GitHub.


## Production/mobile foundation

The existing Streamlit ERP remains the source of truth. The `mobile/` project is a Capacitor-based native Android/iOS client with app ID `ae.lululine.controlcenter`; it connects only to the configured HTTPS deployment. It is not the old PWA/Add-to-Home-Screen manifest.

GitHub Actions validates Python, validates secure mobile configuration, builds an unsigned Android APK/AAB, and validates the iOS simulator build. Configure the encrypted repository secret `LLCC_SERVER_URL` with the production HTTPS URL before running mobile workflows.

For a multi-user production rollout, keep the current live database intact and perform a separately verified migration from SQLite to a managed transactional database. See `SECURITY.md`.
