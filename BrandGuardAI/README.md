# BrandGuard AI — CodeStar 30 Round 2

A Flask + SQLite prototype for explainable brand-governance reviews.

## Features
- Create and activate/deactivate brand rules.
- Submit customer-facing content and run deterministic term checks.
- Flag selected quantitative/absolute claims as **unverified**, not automatically false.
- Show rule evidence and suggested actions.
- Edit content, re-check, and record approve / request changes / reject decisions.
- Review history stored in SQLite.
- Responsive interface for desktop and mobile.

## Run locally (Windows)
1. Install Python 3.10+ from https://www.python.org/downloads/ (select **Add Python to PATH** during setup).
2. Open this folder in VS Code.
3. Open Terminal → New Terminal.
4. Create a virtual environment:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   If PowerShell blocks activation, use Command Prompt terminal and run:
   ```bat
   .venv\Scripts\activate.bat
   ```
5. Install requirements:
   ```powershell
   python -m pip install -r requirements.txt
   ```
6. Start the app:
   ```powershell
   python app.py
   ```
7. Open http://127.0.0.1:5000 in your browser.

## Demo path
1. Open **Brand rules** and inspect the sample rules.
2. Open **Review content** → **Load sample draft** → **Check brand compliance**.
3. Inspect findings and evidence.
4. Edit the draft, click **Save and run checks again**.
5. Add a reviewer comment and approve/request changes/reject.
6. Open **Review history**.

## Deployment
Deploy as a Python web service using `gunicorn app:app` as the start command and `pip install -r requirements.txt` as the build command. Ensure the platform provides persistent storage for `brandguard.db`, or configure a persistent disk; otherwise SQLite data can reset on redeploy. Test the public URL in an incognito window before submitting.

## Limitations and responsible use
- This MVP uses deterministic rule checks and simple claim heuristics; it is not a full AI fact-checker.
- A claim marked unverified is not necessarily false.
- No content is published automatically; human approval is required.
- Do not use confidential customer drafts in this demo.
- No authentication/role-based access is included in this sprint MVP. Do not use for sensitive production content.
