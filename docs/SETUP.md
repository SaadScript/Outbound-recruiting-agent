# Setup guide

About 90 minutes the first time. Everything below works on free plans.

> **Testing rule:** the candidates the search finds are real people. While testing, only approve rows where you have replaced the email with an address of your own.

## 1. Accounts and keys

| Service | What to get |
|---|---|
| [n8n Cloud](https://n8n.io) (free trial) or self-hosted n8n | A workspace |
| Google account | Used for the Sheet and as the sending Gmail |
| AI provider | **Groq** (free, [console.groq.com](https://console.groq.com)) for testing, or OpenAI for production: an API key |
| [Serper](https://serper.dev) | API key (2,500 free queries) |
| [Apollo](https://www.apollo.io) | API key with *People Enrichment* access, integration type **Private**. Optional for testing |
| [Cal.com](https://cal.com) | Free account connected to Google Calendar, with the Google Meet app installed |
| Webhook secret | Any long random string you make up |

## 2. Google Sheet

1. Upload `templates/Recruiting-Agent-Sheet-Template.xlsx` to Google Drive, open it and choose **File → Save as Google Sheets**.
2. Copy the Sheet ID (the part of the URL between `/d/` and `/edit`).
3. Fill in the **Settings** tab:

| Key | Value |
|---|---|
| `agency_name`, `recruiter_name` | Names shown in emails |
| `recruiter_email` | The Gmail that sends the emails |
| `mailing_address` | Postal address for the email footer |
| `booking_link` | Your Cal.com booking link (step 6) |
| `llm_url` / `llm_model` | OpenAI: `https://api.openai.com/v1/chat/completions` / `gpt-4.1-mini`. Groq: `https://api.groq.com/openai/v1/chat/completions` / a model listed in Groq's playground, e.g. `openai/gpt-oss-120b` |
| `max_candidates_per_role` | `5` while testing |
| `search_use_site` | `no` on Serper's free plan, `yes` on a paid plan |

Do not rename tabs or column headers.

## 3. Import the workflows

In n8n, create a new workflow, choose **⋯ → Import from File** and pick a file from `workflows/`. Repeat for all five.

## 4. Credentials

Create these in **Credentials → Create credential**:

| Name | Type | Fields |
|---|---|---|
| AI API key | Header Auth | Name `Authorization`, Value `Bearer <your key>` |
| Serper API key | Header Auth | Name `X-API-KEY`, Value `<your key>` |
| Apollo API key | Header Auth | Name `x-api-key`, Value `<your key>` (or `none` to skip email lookup) |
| Google Sheets account | Google Sheets OAuth2 API | Sign in with Google |
| Gmail account | Gmail OAuth2 API | Sign in with Google, then set **Allowed HTTP Request Domains** to `gmail.googleapis.com` |
| Form login | Basic Auth | A username and password for recruiters |
| Webhook secret | Header Auth | Name `x-webhook-secret`, Value `<your secret>` |

The Gmail setting matters: the Outbox talks to the Gmail API directly, and n8n blocks this unless the domain is allowed.

## 5. Connect each workflow

In workflows 1–4:

1. Paste the Sheet ID into the **Config** node.
2. Open every node with a warning triangle and pick its credential (HTTP nodes: Generic Credential Type → Header Auth → the matching key).
3. **⋯ → Settings:** set **Error workflow** to *Recruiting Agent 5 - Error Alerts* and set the timezone.

In workflow 5, put the admin email in **Config** and pick the Gmail credential.

Publish workflows **1**, **3** and **5**. Leave **2** and **4** unpublished while testing and run them with **Execute workflow**. After any change to a published workflow, publish it again.

## 6. Cal.com

1. In Cal.com, open **Links → New**: title *Intro call*, 20 minutes, location Google Meet. Copy the link into `booking_link`.
2. In n8n, open workflow 3's **Cal.com Webhook** node and copy the **Production URL** (it contains `/webhook/`, not `/webhook-test/`).
3. In Cal.com, open **Settings → Developer → Webhooks → New**: paste the URL and select only *Booking created*, *Booking rescheduled* and *Booking canceled*. Leave **Secret** empty.
4. If Cal.com offers custom headers, add `x-webhook-secret` with your secret. If it does not, set the webhook node's **Authentication** to **None** for testing.
5. Click **Ping test**; it should succeed.

No public URL (self-hosted on a laptop)? Send `templates/test-booking.json` to the webhook with curl to simulate a booking.

## 7. Test run

1. Open workflow 1's form (Production URL), submit a role and check that the **Jobs** and **Candidates** tabs fill up and a summary email arrives.
2. Pick one row, replace its email with a second address of yours (not the sending Gmail) and set status to **Approved**.
3. Run workflow 2: the email arrives and the row becomes **Contacted**.
4. Reply from the second inbox and run workflow 2 again: **Replied**.
5. Book a slot from the email's link: **Interview scheduled**, with time and Meet link.
6. Set the row to **Rejected** and run workflow 2: the rejection email arrives once.
7. Run workflow 4: the weekly report arrives.

## Troubleshooting

| Error | Cause and fix |
|---|---|
| AI step: *Authorization failed* | Key sent to the wrong provider. Check `llm_url` / the node URL and the `Bearer ` prefix |
| AI step: *resource could not be found* | Model name not offered by the provider. Use one from its model list |
| Serper: *Query pattern not allowed for free accounts* | Free plan: keep `search_use_site` = `no` |
| Gmail: *credential is configured to prevent use within an HTTP Request node* | Set the Gmail credential's **Allowed HTTP Request Domains** to `gmail.googleapis.com` |
| Cal.com ping: *403* | Missing secret header. Add the header in Cal.com or set webhook Authentication to None |
| Row shows *Send failed* | See `system_note`. The row stays Approved and retries next run |
