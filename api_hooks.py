# automation_suite/ceo_brain/brain/api_hooks.py

from __future__ import annotations
import os
import sys
import subprocess
from pathlib import Path
from typing import Optional

# Paths
THIS_DIR = Path(__file__).resolve().parent
SUITE_DIR = THIS_DIR.parents[1]               # .../automation_suite
WEB_DIR = SUITE_DIR / "web_automation"        # .../automation_suite/web_automation
WEB_SRC = WEB_DIR / "src"                     # .../automation_suite/web_automation/src
LEADS_DIR = WEB_DIR / "data" / "leads"

def _excel_out_path(niche: str, city: str, country: str = "USA") -> Path:
    # Match the naming logic in web_automation/src/cli.py (spaces -> underscores)
    fname = f"{niche}_{city}_{country}.xlsx".replace(" ", "_")
    return LEADS_DIR / fname

def _run_scraper(niche: str, city: str, country: str = "USA", rows: int = 60, email_flag: bool = True) -> int:
    """
    Launch the scraper synchronously so we know when the file is created.
    Uses the same venv Python if possible (sys.executable), cwd=WEB_DIR.
    """
    cmd = [
        sys.executable, "-m", "src.cli",
        "--niche", niche,
        "--city", city,
        "--country", country,
        "--rows", str(rows),
    ]
    if email_flag:
        cmd.append("--email")  # sends to recipients in src/config.yaml

    print("[brain] Running scraper:", " ".join(cmd), " cwd=", str(WEB_DIR))
    proc = subprocess.run(cmd, cwd=str(WEB_DIR), capture_output=False)
    print("[brain] Scraper finished with code:", proc.returncode)
    return proc.returncode

def _email_to_buyer(report_path: Path, buyer_email: str) -> bool:
    """
    Send the newly created Excel to the buyer in addition to the default recipients.
    We import delivery.py from web_automation/src dynamically.
    """
    if not report_path.exists():
        print(f"[brain] Report not found at {report_path}")
        return False

    # Make delivery.py importable
    sys.path.insert(0, str(WEB_SRC))
    try:
        from delivery import send_report  # type: ignore
    except Exception as e:
        print("[brain] Could not import delivery.send_report:", e)
        return False

    try:
        ok = send_report(str(report_path), [buyer_email])  # extra recipient
        print(f"[brain] Buyer delivery -> {buyer_email} : {ok}")
        return bool(ok)
    except Exception as e:
        print("[brain] send_report failed:", e)
        return False
    finally:
        # best-effort cleanup of sys.path injection
        try:
            sys.path.remove(str(WEB_SRC))
        except ValueError:
            pass

def record_purchase(email: Optional[str], niche: str = "roofing contractor", city: str = "Dallas") -> None:
    """
    Called by payments_stripe/app.py on checkout.session.completed.
    1) Runs the web_automation scraper (which also emails default recipients).
    2) Emails the buyer directly with the generated Excel (if email present).
    """
    buyer = (email or "").strip()
    print(f"[purchase] New Stripe payment from {buyer or 'unknown@buyer.com'} | niche={niche} city={city}")

    # Ensure output dir exists
    LEADS_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Run scraper (synchronous)
    code = _run_scraper(niche=niche, city=city, country="USA", rows=60, email_flag=True)

    # 2) If success, compute output path and email the buyer (extra)
    report = _excel_out_path(niche, city, country="USA")
    if code == 0 and buyer:
        _email_to_buyer(report, buyer)
    else:
        if code != 0:
            print("[brain] Skipping buyer email: scraper returned non-zero exit code.")
        elif not buyer:
            print("[brain] Skipping buyer email: no buyer email provided.")

def record_open(arm_name: str) -> None:
    # placeholder for future email-open tracking integration
    print(f"[event] email_open arm={arm_name}")

def record_click(arm_name: str) -> None:
    # placeholder for future click tracking integration
    print(f"[event] email_click arm={arm_name}")
