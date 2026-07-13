# Microsoft 365 / Outlook (Microsoft Graph) Provider Setup

Connect an Outlook.com or Microsoft 365 / Office 365 mailbox to the ftt job
tracker via the [Microsoft Graph](https://learn.microsoft.com/graph/) API.
Email is fetched from `/me/messages`, classified, and synced into the pipeline
DB using the **same** categories as the Gmail and IMAP providers.

> ### Status: honestly-labeled SCAFFOLD
>
> `mcp-servers/graph-server/graph_tracker.py` is fully structured and the Graph
> calls are written out, **but it has not been run end-to-end** in this repo. It
> requires:
>
> 1. an **Azure app registration** (a client id + tenant), and
> 2. the `msal` and `requests` packages, which are **not installed** here.
>
> With both in place it should work, but treat it as **unverified** until you
> exercise it against your own tenant. Until it is configured, every command
> prints these setup instructions and exits non-zero — never a traceback.
>
> If your Microsoft mailbox happens to allow IMAP access, the fully-verified
> [generic IMAP provider](imap-setup.md) is an alternative that needs no Azure
> app.

---

## Step 1: Register an Azure (Entra ID) app

1. Go to the [Azure Portal](https://portal.azure.com) →
   **Microsoft Entra ID** → **App registrations** → **New registration**.
2. Name it e.g. `ftt-job-tracker`.
3. **Supported account types**: pick what matches your mailbox. For a personal
   Outlook.com account plus work/school accounts, choose
   *Accounts in any organizational directory and personal Microsoft accounts*.
4. Leave **Redirect URI** empty (device-code flow does not need one). Register.
5. Copy the **Application (client) ID** and the **Directory (tenant) ID** from
   the Overview page.

---

## Step 2: Add the delegated permission

1. In your app → **API permissions** → **Add a permission** →
   **Microsoft Graph** → **Delegated permissions**.
2. Add **`Mail.Read`** (read the signed-in user's mail). This is the only scope
   the tracker requests.
3. If your organization requires it, click **Grant admin consent**. Personal
   accounts consent at first sign-in.

---

## Step 3: Enable public-client (device-code) flows

1. In your app → **Authentication** → **Advanced settings**.
2. Set **Allow public client flows** to **Yes**. (The device-code flow used
   here is a public-client flow — no client secret is stored.)

---

## Step 4: Install dependencies and set env vars

```bash
pip install -r mcp-servers/graph-server/requirements.txt   # msal, requests, mcp

export FTT_GRAPH_CLIENT_ID=<application-client-id>   # required
export FTT_GRAPH_TENANT_ID=common                    # or your tenant id (default: common)
export FTT_GRAPH_SCOPES='Mail.Read'                  # optional (default: Mail.Read)
```

Use `common` for the tenant if you want to sign in with either personal or
work/school accounts; use your specific tenant id to restrict to your org.

---

## Step 5: Device-code login and sync

```bash
python3 mcp-servers/graph-server/graph_tracker.py --sync
```

On first run MSAL prints something like:

```
To sign in, use a web browser to open the page https://microsoft.com/devicelogin
and enter the code ABCD-EFGH to authenticate.
```

Open the URL, enter the code, approve `Mail.Read`. The token is cached at
`~/.mcp/config/graph_token_cache.json`, so later runs are silent until it
expires.

Flags mirror the other providers:

| Flag        | Meaning                                       |
| ----------- | --------------------------------------------- |
| `--sync`    | Fetch, classify, upsert to DB, print summary  |
| `--summary` | Alias of `--sync`                             |
| `--raw`     | Print parsed emails as JSON (no DB write)     |
| `--days N`  | Look back N days (default 30)                 |
| `--max N`   | Cap at N messages (default 50)                |
| `--mcp`     | Run as a stdio MCP server                     |

---

## Step 6 (optional): Wire it as an MCP server

The `--mcp` flag starts a stdio MCP server exposing:

- `sync_graph_to_tracker(days=30, max_results=50)`
- `get_email_summary(days=30, max_results=50)`

```json
{
  "mcpServers": {
    "graph-tracker": {
      "command": "python3",
      "args": ["/path/to/forget-the-thunderdome/mcp-servers/graph-server/graph_tracker.py", "--mcp"],
      "env": { "FTT_GRAPH_CLIENT_ID": "<application-client-id>" }
    }
  }
}
```

---

## Limitations & notes

- **Unverified**: not exercised end-to-end in this repo (no Azure creds, `msal`
  not installed). The classifier it reuses *is* verified via the IMAP provider.
- **Delegated only**: this uses delegated `Mail.Read` (the signed-in user's own
  mailbox). Reading other users' mailboxes would need application permissions +
  admin consent, which is out of scope here.
- **Graph query**: messages are pulled with
  `$filter=receivedDateTime ge <cutoff>`, `$orderby=receivedDateTime desc`, and
  paged via `@odata.nextLink` up to `--max`. Graph caps `$top` at 50 per page.
- **Classifier reuse**: `graph_tracker.py` imports `classify_email` from the
  IMAP provider via a `sys.path` shim, with a small inline duplicate as a
  fallback. A future refactor could lift the classifier into `src/` for all
  providers to share.
- **Throttling**: Graph may return HTTP 429; the scaffold surfaces the error
  rather than implementing backoff. Add retry handling before heavy use.
