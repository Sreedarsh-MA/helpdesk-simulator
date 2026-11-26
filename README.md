# helpdesk-simulator

A local IT service-desk simulator for practicing ticket triage without a real queue. It generates realistic tickets each day, tracks them through a status lifecycle in SQLite, and keeps a dashboard of what is open by priority.

Built because reading about ticket workflows is not the same as doing them 20 times in a row.

## What it does

- Seven categories (Hardware, Software, Network, Email, Access/Permissions, Printer, Account) and four priorities weighted like a real queue: Low 30, Medium 40, High 20, Critical 10.
- Daily generator is idempotent — topping up twice a day never exceeds the cap.
- Ticket keys (`HD-0001` style), statuses `open -> in_progress -> resolved -> closed`, and per-ticket notes.
- Two roles: an automated manager that owns the queue, and an agent account that receives the work.
- Optional daily generation through Windows Task Scheduler.

```
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
```

## Run

```bash
python helpdesk.py                 # interactive
python helpdesk.py --auto          # generate today's tickets and exit
python helpdesk.py --generate 20   # custom count, then exit
python helpdesk.py --dashboard     # print dashboard and exit
```

Python 3.8+, standard library only. State lives in `helpdesk.db` next to the script and is gitignored — delete it to start from a clean desk.

## Config

At the top of `helpdesk.py`:

```python
DAILY_TICKET_COUNT = 20
AGENT = {"username": "sreed", "name": "Sreed", "role": "agent"}
```

Change `AGENT` to your own name, and edit `TICKET_TEMPLATES` to add scenarios you actually see at work.

## Relation to it-ticket-router

This one is the queue side — what a ticket looks like and how it moves. [`it-ticket-router`](https://github.com/Sreedarsh-MA/it-ticket-router) is the classifier that would route those tickets to the right queue automatically.
