# Cursor API key (pipeline agent)

When the pipeline uses the **cursor** backend, it runs the Cursor CLI (`agent`). That CLI needs to be authenticated. If it isn’t, you’ll see:

```
Error: Authentication required. Please run 'agent login' first, or set CURSOR_API_KEY environment variable.
```

This doc explains where to get the key and where to put it.

---

## Where to get the key

1. Open **[Cursor Dashboard](https://cursor.com/dashboard)** and sign in.
2. Go to **Integrations** or **Background Agents / API**:
   - [Integrations](https://cursor.com/dashboard?tab=integrations)
   - [Background Agents](https://cursor.com/dashboard?tab=background-agents)
3. Create or copy a **User API key** (for headless CLI and scripts).

---

## Where to put it

**Recommended: `.env` in the project root**

Create or edit `.env` in the project root (same folder as `README.md`):

```
CURSOR_API_KEY=your_key_here
```

Scripts like `test_evaluate.py` load `.env` from the project root. The pipeline subprocess receives `CURSOR_API_KEY` from the environment, so the Cursor CLI can authenticate.

**Alternative: shell**

Before running:

```bash
export CURSOR_API_KEY=your_key_here
python examples/test_evaluate.py ...
```

**Alternative: interactive login**

If the `agent` command is on your PATH:

```bash
agent login
```

Use this for interactive use. For scripts and CI, prefer `.env` or `export CURSOR_API_KEY`.

---

## Security

- **Do not commit `.env`** or any file that contains `CURSOR_API_KEY`.
- Keep `.env` in `.gitignore` (it usually is already).

---

## If you use the `claude` backend

The pipeline can use **claude** instead of **cursor** (set `pipeline_backend: "claude"` in config or pass the right flag). Then the Claude CLI is used and you don’t need a Cursor API key for that run.
