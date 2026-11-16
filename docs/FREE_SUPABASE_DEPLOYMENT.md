# Free Render Status Deployment with Supabase

This deployment keeps TripoSR inference on your computer and publishes only the
small authenticated status API through Supabase. It does not upload model files
or expose model URLs.

## 1. Create the status table

In the Supabase dashboard, open **SQL Editor**, create a new query, paste the
contents of
`supabase/migrations/20261117000000_create_render_jobs.sql`, and select **Run**.

The table has Row Level Security enabled and grants no access to anonymous or
signed-in browser clients. The server-only key bypasses RLS.

## 2. Deploy the function in the dashboard

Open **Edge Functions**, select **Deploy a new function > Via Editor**, name it
`render-status`, replace the example with the contents of
`supabase/functions/render-status/index.ts`, and select **Deploy function**.

Open the deployed function's **Details** tab and turn off **JWT verification**.
The function authenticates RenderPulse itself with a dedicated bearer secret;
the Supabase JWT check must be off so it does not reject that credential first.

Its base URL is:

```text
https://YOUR_PROJECT_REF.supabase.co/functions/v1/render-status
```

You can find the project reference under **Project Settings > General**.

If you prefer the CLI, deploy the checked-in function instead:

```powershell
npx supabase login
npx supabase link --project-ref YOUR_PROJECT_REF
npx supabase functions deploy render-status --no-verify-jwt
```

## 3. Add Edge Function secrets

Generate one long random value and use the same value for Image-to-3D,
RenderPulse, and the Edge Function:

```powershell
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
[Convert]::ToHexString($bytes)
```

Open **Edge Functions > Secrets** and add these three secrets:

```dotenv
RENDER_STATUS_API_KEY=PASTE_RANDOM_VALUE
RENDER_STATUS_ALLOWED_TEAM_ID=T_YOUR_SLACK_TEAM
RENDER_STATUS_ALLOWED_CHANNEL_IDS=C_YOUR_SLACK_CHANNEL
```

Or set the same values with the CLI:

```powershell
npx supabase secrets set `
  RENDER_STATUS_API_KEY=PASTE_RANDOM_VALUE `
  RENDER_STATUS_ALLOWED_TEAM_ID=T_YOUR_SLACK_TEAM `
  RENDER_STATUS_ALLOWED_CHANNEL_IDS=C_YOUR_SLACK_CHANNEL
```

Do not add any secret beginning with `SUPABASE_`; Supabase automatically
supplies `SUPABASE_URL` and its server-only key collection to hosted functions.

## 4. Configure the local Image-to-3D app

Add these values to `web-Brickrat/.env`:

```dotenv
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
RENDER_STATUS_SUPABASE_KEY=YOUR_SERVER_ONLY_SECRET_OR_SERVICE_ROLE_KEY
RENDER_STATUS_SUPABASE_TABLE=render_jobs
```

Get the server-only key from **Project Settings > API Keys**. Never put this key
in browser code, commit it, or send it to RenderPulse.

Restart Image-to-3D and run one conversion. Its RenderPulse ID will be written
to `render_jobs` as it changes from queued to processing to completed or failed.

## 5. Configure RenderPulse

Set these environment variables where RenderPulse runs:

```dotenv
RENDER_API_BASE_URL=https://YOUR_PROJECT_REF.supabase.co/functions/v1/render-status
RENDER_API_KEY=PASTE_RANDOM_VALUE
```

Keep the existing Slack signing secret and allowlist values. RenderPulse calls:

```text
GET <RENDER_API_BASE_URL>/api/renders/<RENDER_ID>/status
```

## 6. Verify before connecting Slack

Replace the values below and test one real ID:

```powershell
$headers = @{
  Authorization = "Bearer PASTE_RANDOM_VALUE"
  "X-RenderPulse-Slack-Team" = "T_YOUR_SLACK_TEAM"
  "X-RenderPulse-Slack-Channel" = "C_YOUR_SLACK_CHANNEL"
}
Invoke-RestMethod `
  -Uri "https://YOUR_PROJECT_REF.supabase.co/functions/v1/render-status/api/renders/R123456789ABC/status" `
  -Headers $headers
```

Use a RenderPulse ID produced by an actual conversion. A made-up ID correctly
returns HTTP 404.

## Free-plan limitation

Supabase may pause a free project after a period of low activity. If the status
endpoint stops responding after inactivity, open the Supabase dashboard and
restore the project. Local 3D conversion continues to work independently.
