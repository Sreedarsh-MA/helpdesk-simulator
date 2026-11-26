"""
Personal HelpDesk — a self-contained IT support ticket system.

- SQLite database (no external dependencies, Python stdlib only).
- A MANAGER account (automated) owns the queue and generates tickets.
- A personal AGENT account (you) receives DAILY_TICKET_COUNT new tickets each day.
- The daily generator is idempotent: running it many times a day never exceeds the cap.
- Optional true automation via Windows Task Scheduler (menu option 8).

Run interactively:      python helpdesk.py
Generate + exit (cron):  python helpdesk.py --auto
Generate a custom count: python helpdesk.py --generate 20
"""
import os
import sys
import sqlite3
import random
import argparse
import subprocess
from datetime import datetime, date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "helpdesk.db")

# ----------------- Configuration (edit freely) -----------------
DAILY_TICKET_COUNT = 20
MANAGER = {"username": "manager", "name": "Auto Manager", "role": "manager"}
AGENT = {"username": "sreed", "name": "Sreed", "role": "agent"}

CATEGORIES = ["Hardware", "Software", "Network", "Email", "Access/Permissions", "Printer", "Account"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
PRIORITY_WEIGHTS = [30, 40, 20, 10]  # relative likelihood
STATUSES = ["open", "in_progress", "resolved", "closed"]

TICKET_TEMPLATES = [
    ("Cannot log in to {sys}", "User reports invalid credentials when signing in to {sys}. Needs password reset and MFA check.", "Access/Permissions"),
    ("{sys} is running very slowly", "Multiple users report {sys} takes over a minute to load. Suspect disk or network bottleneck.", "Software"),
    ("No network connectivity on floor {n}", "Workstations on floor {n} dropped off the network. Switch or DHCP issue suspected.", "Network"),
    ("Printer on floor {n} not responding", "Shared printer on floor {n} shows offline. Needs driver reinstall and queue clear.", "Printer"),
    ("Email not syncing on mobile", "Mail app on a phone stopped syncing after the last update. Re-add account / check IMAP.", "Email"),
    ("Request access to {sys}", "New starter needs read/write access to {sys}. Manager approval attached, provision the role.", "Access/Permissions"),
    ("Blue screen on workstation {n}", "Workstation {n} restarted with a BSOD twice today. Pull event logs and check drivers/RAM.", "Hardware"),
    ("Software license expired for {sys}", "License for {sys} expired. Renew or reassign a spare seat from the pool.", "Software"),
    ("VPN disconnects repeatedly", "Remote user's VPN drops every few minutes. Check client version and gateway logs.", "Network"),
    ("Cannot access shared drive", "User lost access to the team share. Verify group membership and NTFS permissions.", "Access/Permissions"),
    ("Monitor shows no signal", "Second monitor on desk {n} shows 'no signal'. Test cable/port and display settings.", "Hardware"),
    ("Antivirus blocked a legitimate app", "Endpoint protection quarantined a signed installer. Review and whitelist if safe.", "Software"),
    ("Password reset request for {sys}", "User locked out of {sys} after failed attempts. Verify identity and reset.", "Account"),
    ("Laptop won't charge", "Charging light off on a laptop. Test charger, port, and battery health.", "Hardware"),
    ("Update failed on {sys}", "Patch for {sys} failed to install and rolled back. Investigate logs and retry.", "Software"),
]

SYSTEMS = ["the ERP", "Salesforce", "the file server", "Office 365", "the VPN portal", "the HR system", "Slack", "the ticketing tool", "Zoom", "the intranet"]


# ----------------- Database -----------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                name TEXT,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_key TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                category TEXT,
                priority TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                created_by INTEGER REFERENCES users(id),
                assigned_to INTEGER REFERENCES users(id),
                day_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
    _ensure_user(MANAGER)
    _ensure_user(AGENT)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today():
    return date.today().isoformat()


def _ensure_user(u):
    with get_conn() as c:
        row = c.execute("SELECT id FROM users WHERE username = ?", (u["username"],)).fetchone()
        if not row:
            c.execute(
                "INSERT INTO users (username, name, role, created_at) VALUES (?,?,?,?)",
                (u["username"], u["name"], u["role"], _now()),
            )


def get_user_id(username):
    with get_conn() as c:
        row = c.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        return row["id"] if row else None


def _next_ticket_key(c):
    row = c.execute("SELECT COALESCE(MAX(id), 0) + 1 AS n FROM tickets").fetchone()
    return f"TKT-{row['n']:06d}"


# ----------------- Ticket generation -----------------
def tickets_generated_today():
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) AS n FROM tickets WHERE day_key = ?", (_today(),)).fetchone()["n"]


def _random_ticket():
    sysname = random.choice(SYSTEMS)
    n = random.randint(1, 12)
    title_t, desc_t, category = random.choice(TICKET_TEMPLATES)
    title = title_t.format(sys=sysname, n=n)
    desc = desc_t.format(sys=sysname, n=n)
    priority = random.choices(PRIORITIES, weights=PRIORITY_WEIGHTS, k=1)[0]
    return title, desc, category, priority


def generate_daily_tickets(count=DAILY_TICKET_COUNT, verbose=True):
    """Top up today's queue to `count` tickets. Idempotent per calendar day."""
    manager_id = get_user_id(MANAGER["username"])
    agent_id = get_user_id(AGENT["username"])
    already = tickets_generated_today()
    remaining = max(0, count - already)

    if remaining == 0:
        if verbose:
            print(f"Already generated {already}/{count} tickets for {_today()}. Nothing to do.")
        return 0

    now = _now()
    today = _today()
    with get_conn() as c:
        for _ in range(remaining):
            title, desc, category, priority = _random_ticket()
            key = _next_ticket_key(c)
            c.execute(
                """INSERT INTO tickets
                   (ticket_key, title, description, category, priority, status,
                    created_by, assigned_to, day_key, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (key, title, desc, category, priority, "open",
                 manager_id, agent_id, today, now, now),
            )
    if verbose:
        print(f"Generated {remaining} new ticket(s). Today's total: {already + remaining}/{count}.")
    return remaining


# ----------------- Views -----------------
def _fmt_rows(rows, cols, widths):
    def line(vals):
        return "  ".join(str(v)[:w].ljust(w) for v, w in zip(vals, widths))
    out = [line(cols), line(["-" * w for w in widths])]
    for r in rows:
        out.append(line(r))
    return "\n".join(out)


def dashboard():
    with get_conn() as c:
        total = c.execute("SELECT COUNT(*) n FROM tickets").fetchone()["n"]
        today = tickets_generated_today()
        agent_id = get_user_id(AGENT["username"])
        mine_open = c.execute(
            "SELECT COUNT(*) n FROM tickets WHERE assigned_to=? AND status IN ('open','in_progress')",
            (agent_id,),
        ).fetchone()["n"]
        by_status = c.execute(
            "SELECT status, COUNT(*) n FROM tickets GROUP BY status ORDER BY n DESC"
        ).fetchall()
        by_prio = c.execute(
            "SELECT priority, COUNT(*) n FROM tickets WHERE status IN ('open','in_progress') GROUP BY priority"
        ).fetchall()

    print("\n================ HELPDESK DASHBOARD ================")
    print(f"  Date: {_today()}    Total tickets: {total}")
    print(f"  Generated today: {today}/{DAILY_TICKET_COUNT}    Your open+in-progress: {mine_open}")
    print("\n  By status:")
    for r in by_status:
        print(f"    {r['status']:<12} {r['n']}")
    if by_prio:
        print("  Open by priority:")
        order = {p: i for i, p in enumerate(PRIORITIES)}
        for r in sorted(by_prio, key=lambda x: order.get(x["priority"], 99)):
            print(f"    {r['priority']:<12} {r['n']}")
    print("====================================================\n")


def list_tickets(only_mine=True, only_open=True):
    agent_id = get_user_id(AGENT["username"])
    q = "SELECT ticket_key, title, category, priority, status FROM tickets WHERE 1=1"
    params = []
    if only_mine:
        q += " AND assigned_to = ?"
        params.append(agent_id)
    if only_open:
        q += " AND status IN ('open','in_progress')"
    q += " ORDER BY CASE priority WHEN 'Critical' THEN 0 WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, id DESC LIMIT 50"
    with get_conn() as c:
        rows = c.execute(q, params).fetchall()
    if not rows:
        print("No tickets match that filter.")
        return
    data = [(r["ticket_key"], r["title"], r["category"], r["priority"], r["status"]) for r in rows]
    print()
    print(_fmt_rows(data, ["KEY", "TITLE", "CATEGORY", "PRIORITY", "STATUS"], [11, 34, 16, 9, 12]))
    print()


def show_ticket(key):
    with get_conn() as c:
        r = c.execute("SELECT * FROM tickets WHERE ticket_key = ?", (key.upper(),)).fetchone()
    if not r:
        print(f"No ticket with key '{key}'.")
        return
    print(f"\n--- {r['ticket_key']} ---")
    print(f"  Title:      {r['title']}")
    print(f"  Category:   {r['category']}")
    print(f"  Priority:   {r['priority']}")
    print(f"  Status:     {r['status']}")
    print(f"  Created:    {r['created_at']}  (day {r['day_key']})")
    print(f"  Updated:    {r['updated_at']}")
    print(f"  Details:\n    {r['description']}\n")


def work_ticket(key, new_status):
    new_status = new_status.strip().lower()
    if new_status not in STATUSES:
        print(f"Invalid status. Choose one of: {', '.join(STATUSES)}")
        return
    with get_conn() as c:
        cur = c.execute(
            "UPDATE tickets SET status = ?, updated_at = ? WHERE ticket_key = ?",
            (new_status, _now(), key.upper()),
        )
        if cur.rowcount == 0:
            print(f"No ticket with key '{key}'.")
        else:
            print(f"{key.upper()} -> {new_status}")


def create_manual_ticket(title, category="Software", priority="Medium"):
    manager_id = get_user_id(MANAGER["username"])
    agent_id = get_user_id(AGENT["username"])
    now = _now()
    with get_conn() as c:
        key = _next_ticket_key(c)
        c.execute(
            """INSERT INTO tickets
               (ticket_key, title, description, category, priority, status,
                created_by, assigned_to, day_key, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (key, title, "(manually created)", category, priority, "open",
             manager_id, agent_id, _today(), now, now),
        )
    print(f"Created {key}: {title}")


def list_users():
    with get_conn() as c:
        rows = c.execute("SELECT username, name, role, created_at FROM users ORDER BY id").fetchall()
    data = [(r["username"], r["name"], r["role"], r["created_at"]) for r in rows]
    print()
    print(_fmt_rows(data, ["USERNAME", "NAME", "ROLE", "CREATED"], [14, 18, 10, 20]))
    print()


def add_user(username, name, role):
    if role not in ("manager", "agent"):
        print("Role must be 'manager' or 'agent'.")
        return
    try:
        _ensure_user({"username": username, "name": name, "role": role})
        print(f"User '{username}' ready (role: {role}).")
    except Exception as e:
        print(f"Could not add user: {e}")


# ----------------- Windows Task Scheduler (true daily auto-run) -----------------
def _task_name():
    return "PersonalHelpDeskDaily"


def enable_autorun(hour=8, minute=0):
    """Register a Windows Scheduled Task that runs `helpdesk.py --auto` daily."""
    if sys.platform != "win32":
        print("Auto-run via Task Scheduler is Windows-only. On other OS use cron with: python helpdesk.py --auto")
        return
    py = sys.executable
    script = os.path.abspath(__file__)
    when = f"{hour:02d}:{minute:02d}"
    cmd = [
        "schtasks", "/Create", "/F", "/SC", "DAILY", "/TN", _task_name(),
        "/TR", f'"{py}" "{script}" --auto', "/ST", when,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"Scheduled task '{_task_name()}' created — runs daily at {when}.")
            print("It will top up your queue to 20 tickets each day automatically.")
        else:
            print(f"schtasks failed: {res.stderr.strip() or res.stdout.strip()}")
    except Exception as e:
        print(f"Could not create scheduled task: {e}")


def disable_autorun():
    if sys.platform != "win32":
        print("Windows-only.")
        return
    try:
        res = subprocess.run(["schtasks", "/Delete", "/F", "/TN", _task_name()],
                             capture_output=True, text=True)
        print("Auto-run task removed." if res.returncode == 0 else f"Delete failed: {res.stderr.strip()}")
    except Exception as e:
        print(f"Could not remove task: {e}")


# ----------------- CLI -----------------
MENU = """
 ===== Personal HelpDesk =====
  1) Generate today's tickets (top up to 20)
  2) Dashboard
  3) My open tickets
  4) All tickets (incl. closed)
  5) View a ticket        (by key)
  6) Update a ticket status
  7) Create a manual ticket
  8) Enable daily auto-run (Windows Task Scheduler)
  9) Disable daily auto-run
 10) List users
 11) Add a user
  0) Quit
"""


def _ask(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def main_cli():
    init_db()
    # Auto top-up on launch so "20 per day" happens without remembering to click.
    if tickets_generated_today() < DAILY_TICKET_COUNT:
        generate_daily_tickets()
    dashboard()

    while True:
        print(MENU)
        choice = _ask("Choose> ")
        if choice in ("0", "q", "quit", "exit"):
            print("Goodbye.")
            break
        elif choice == "1":
            generate_daily_tickets()
        elif choice == "2":
            dashboard()
        elif choice == "3":
            list_tickets(only_mine=True, only_open=True)
        elif choice == "4":
            list_tickets(only_mine=False, only_open=False)
        elif choice == "5":
            show_ticket(_ask("Ticket key (e.g. TKT-000001): "))
        elif choice == "6":
            k = _ask("Ticket key: ")
            s = _ask(f"New status ({'/'.join(STATUSES)}): ")
            if k and s:
                work_ticket(k, s)
        elif choice == "7":
            t = _ask("Title: ")
            if t:
                cat = _ask("Category [Software]: ") or "Software"
                pri = _ask("Priority [Medium]: ") or "Medium"
                create_manual_ticket(t, cat, pri)
        elif choice == "8":
            hh = _ask("Hour (0-23) [8]: ") or "8"
            mm = _ask("Minute (0-59) [0]: ") or "0"
            try:
                enable_autorun(int(hh), int(mm))
            except ValueError:
                print("Invalid time.")
        elif choice == "9":
            disable_autorun()
        elif choice == "10":
            list_users()
        elif choice == "11":
            un = _ask("Username: ")
            if un:
                nm = _ask("Display name: ") or un
                rl = _ask("Role (manager/agent) [agent]: ") or "agent"
                add_user(un, nm, rl)
        else:
            print("Unknown option.")


def main():
    parser = argparse.ArgumentParser(description="Personal HelpDesk ticket system")
    parser.add_argument("--auto", action="store_true", help="Generate today's tickets and exit (for schedulers)")
    parser.add_argument("--generate", type=int, metavar="N", help="Generate/top up to N tickets for today and exit")
    parser.add_argument("--dashboard", action="store_true", help="Print the dashboard and exit")
    args = parser.parse_args()

    init_db()
    if args.auto:
        generate_daily_tickets()
        return
    if args.generate is not None:
        generate_daily_tickets(count=args.generate)
        return
    if args.dashboard:
        dashboard()
        return
    main_cli()


if __name__ == "__main__":
    main()
