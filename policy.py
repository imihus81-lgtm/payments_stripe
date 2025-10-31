
import sqlite3, random, yaml
from pathlib import Path
DB = Path(__file__).resolve().parents[1] / "brain.db"
ARMS_YAML = Path(__file__).parent / "arms.yaml"

def load_arms():
    data = yaml.safe_load(ARMS_YAML.read_text(encoding="utf-8"))
    return data.get("arms", [])

def _ensure_priors():
    cx = sqlite3.connect(DB); cx.row_factory = sqlite3.Row
    rows = cx.execute("SELECT arm, alpha, beta FROM bandit").fetchall()
    have = {r["arm"] for r in rows}
    arms = load_arms()
    changed=False
    for a in arms:
        if a["name"] not in have:
            cx.execute("INSERT OR REPLACE INTO bandit(arm,alpha,beta) VALUES (?,?,?)", (a["name"], 1.0, 1.0))
            changed=True
    if changed: cx.commit()
    cx.close()

def sample_arm():
    _ensure_priors()
    cx = sqlite3.connect(DB); cx.row_factory = sqlite3.Row
    rows = cx.execute("SELECT arm, alpha, beta FROM bandit").fetchall(); cx.close()
    best=None; best_draw=-1
    import random as _r
    for r in rows:
        draw = _r.betavariate(max(r["alpha"],1e-3), max(r["beta"],1e-3))
        if draw>best_draw: best_draw=draw; best=r["arm"]
    arms = load_arms()
    return next(a for a in arms if a["name"]==best)

def update_reward(arm: str, reward: float):
    cx = sqlite3.connect(DB)
    row = cx.execute("SELECT alpha,beta FROM bandit WHERE arm=?", (arm,)).fetchone()
    success = 1 if reward>=0.5 else 0
    if row is None:
        cx.execute("INSERT INTO bandit(arm,alpha,beta) VALUES(?,?,?)", (arm, 1.0+success, 1.0+(1-success)))
    else:
        alpha,beta = row
        cx.execute("UPDATE bandit SET alpha=?, beta=? WHERE arm=?", (alpha+success, beta+(1-success), arm))
    cx.commit(); cx.close()
