# AGENTS.md — Rules for AI Agents on VR Inspector

> **Stack:** FastAPI (Python) · PostgreSQL (AWS RDS) · Auth0 PKCE · AWS S3 · nginx · staging.vrinspector.com
> **Repo:** Field Inspect LLC / VR Inspector SaaS platform
> **Full protocol:** `flagprompt.md` (ChrisRoyse/UsefulPrompts)

---

## Non-Negotiable Rules

1. **File rule.** Observe any defect, smell, security issue, or test gap you are NOT fixing this turn → open a labeled Issue before the turn ends.
2. **Claim rule.** Before touching code tied to an Issue: assign self, flip `status:needs-triage` → `status:in-progress`, post a plan comment listing files you'll touch. Comment at every milestone. Pause/done = explicit comment. **No silent work.**

If both rules followed, parallel agents never collide.

---

## Pre-Work Scan (run at the start of EVERY session)

```bash
REPO="vrinspector/backend"   # ← replace with actual GitHub repo path

# 1. What's claimed? Avoid these files.
gh issue list --repo $REPO --state open --label "status:in-progress" \
  --json number,title,assignees,updatedAt,labels

# 2. What's open + unclaimed? Your candidate queue.
gh issue list --repo $REPO --state open --label "source:agent" \
  --search "no:assignee" --sort updated --json number,title,labels,updatedAt

# 3. High-priority queue — do these first.
gh issue list --repo $REPO --state open \
  --label "priority:p0,priority:p1" --json number,title,labels,assignees
```

**Never edit files referenced by a `status:in-progress` issue assigned to another agent without commenting on that issue first.**

---

## VRI Architecture — Know Before You Touch

| Layer | Tech | Key files |
|---|---|---|
| Backend | FastAPI + Python 3.x | `/opt/vrinspector/backend/` |
| DB | PostgreSQL on AWS RDS | `app/database.py`, `app/models/` |
| Auth | Auth0 JWT (PKCE) | `app/auth.py` — `AUTH0_API_AUDIENCE=https://api.vrinspector.com` |
| Storage | AWS S3 (`vrinspector-files`, `us-east-1`) | `app/routers/photos.py` |
| Frontend | Static SPA | `staging.vrinspector.com` |
| Proxy | nginx | `/etc/nginx/sites-available/` |
| Venv | **Always use** `/opt/vrinspector/backend/venv/bin/python3` | Never system Python |
| File transfer | **Base64 encode/decode only** | Heredoc paste corrupts >~20 lines |

---

## VRI-Specific Coding Rules

- **URLs:** Always string-concatenate — never hardcode `https://` literals directly in code.
- **Python scripts to server:** Write to `/tmp` via `sudo tee`, then execute from there.
- **DB connections:** `DATABASE_URL` uses asyncpg; `DATABASE_URL_SYNC` uses psycopg2. Keep both.
- **Auth0 env key:** Must be `AUTH0_API_AUDIENCE` (not `AUTH0_IDENTIFIER` or any variant).
- **AWS keys:** Already in `.env` — never commit, never log.

---

## Claiming an Issue (atomic)

```bash
gh issue edit $N --repo $REPO \
  --add-assignee @me \
  --remove-label "status:needs-triage" \
  --add-label "status:in-progress" \
  --add-label "agent:claude"

gh issue comment $N --repo $REPO --body "$(cat <<'EOF'
**CLAIM** — agent:claude session:<id> commit:<sha>
**Plan:** <2–4 bullet steps>
**Files I'll touch:** <list>
**ETA:** <this turn / multi-turn>
EOF
)"
```

---

## Pause Note (highest-leverage habit)

```bash
gh issue comment $N --repo $REPO --body "$(cat <<'EOF'
**PAUSE** — agent:claude session:<id> commit:<sha>
**Done:** <bullets>
**Tried & failed:** <bullets — save next agent the dead-end>
**Learned:** <invariants/gotchas>
**Resume at:** <file:line> with <next test/command>
**Hypothesis to verify:** <one sentence>
EOF
)"
```

---

## Done

```bash
gh issue comment $N --repo $REPO --body "$(cat <<'EOF'
**RESOLVED** — agent:claude commit:<sha> PR:#<pr>
**Fix summary:** <2 sentences>
**Verification:** <test added / FSV done / SoT readback>
**Side effects observed:** <or "none">
EOF
)"
# Reference in commit: "Fixes #N" or "Closes #N" → auto-closes on PR merge.
```

---

## Filing a New Issue

1. Search 3–6 distinctive keywords (symbol names, error strings, file paths) — open + closed:
   ```bash
   gh issue list --repo $REPO --state all --limit 50 \
     --search "<keyword1> <keyword2> <keyword3> in:title,body"
   ```
2. Score similarity: ≥8/10 → comment on existing. 5–7 → file, link related. <5 → file new.
3. Use a template from `.github/ISSUE_TEMPLATE/`. Title prefix: `[BUG]` / `[SEC]` / `[TEST]` / `[DEBT]` / `[ARCH]` / `[DEAD]` / `[ANOMALY]`.
4. Body must include: evidence (file:line, log, SHA), expected vs observed, scope/blast radius, suggested next action, agent+session footer.
5. Labels: 1 `type:*` + 1 `priority:*` (default `p2`) + `status:needs-triage` + `source:agent` + `agent:claude`.

---

## VRI Current Phase Tracking

| Block | Status | Key issue area |
|---|---|---|
| Phase 1 Block 1 — DB + API routers | ✅ Complete (May 10 2026) | `area:backend` |
| Phase 1 Block 2 — Frontend SPA + Auth0 | ✅ Complete (May 10 2026) | `area:frontend` |
| Phase 1 Block 3 — S3 Photo Upload | 🔄 Next | `area:storage` |
| Phase 1 Block 4+ | Pending | TBD |

**Before starting Block 3:** run the pre-work scan above, file a claim issue, list files you'll touch.

---

## Priority Heuristic

| Priority | Condition |
|---|---|
| `p0` | Security exploit possible now, prod outage, data loss risk |
| `p1` | User-facing bug, auth weakness, anomaly ≥3σ |
| `p2` | Tech debt, test gap on critical path, anomaly 2–3σ. **Default.** |
| `p3` | Cosmetic, micro-opt, far-future risk |

---

## Tools

`gh` CLI · GitHub REST API · GitHub MCP server (`github/github-mcp-server`)

**$0 budget — GitHub Free plan on private repo. Never enable paid features. If a task needs one, file an issue with cost/free-alternative and let the operator decide.**
