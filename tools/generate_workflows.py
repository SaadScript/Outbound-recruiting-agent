"""Recruiting Agent v2 - n8n workflow generator."""
import json, os, uuid

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "workflows")
os.makedirs(OUT, exist_ok=True)

CAND_COLS = ["candidate_id", "job_id", "role", "name", "headline", "linkedin_url", "snippet",
             "email", "email_status", "current_title", "current_company",
             "score", "summary", "strengths", "gaps", "status",
             "outreach_subject", "outreach_body", "thread_id", "outreach_sent_at", "followup_sent_at",
             "last_reply_at", "interview_time", "meet_link", "candidate_notified_at",
             "recruiter_notes", "system_note", "created_at", "updated_at", "interview_booked_at"]
JOB_COLS = ["job_id", "role", "location", "seniority", "summary", "responsibilities", "must_have",
            "nice_to_have", "search_titles", "status", "created_at"]

PICK = ("const COLS = " + json.dumps(CAND_COLS) + ";\n"
        "const pick = o => { const r = {}; for (const k of COLS) if (o[k] !== undefined) r[k] = o[k]; return r; };\n")

SETTINGS_JS = r"""
// Turns the Settings tab (key | value rows) into one object.
const s = {};
for (const it of $input.all()) {
  const k = String(it.json.key ?? '').trim();
  if (k) s[k] = String(it.json.value ?? '').trim();
}
for (const k of ['agency_name', 'recruiter_name', 'recruiter_email']) {
  if (!s[k]) throw new Error(`Settings tab is missing a value for "${k}"`);
}
return [{ json: s }];
"""

RETRY = {"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 5000}
CRED_SHEETS = {"googleSheetsOAuth2Api": {"id": "", "name": "Google Sheets account"}}
CRED_GMAIL = {"gmailOAuth2": {"id": "", "name": "Gmail account"}}
CRED_OPENAI = {"openAiApi": {"id": "", "name": "OpenAI account"}}


class WF:
    def __init__(self, name, settings=None):
        self.name, self.nodes, self.conns = name, [], {}
        self.settings = {"executionOrder": "v1", **(settings or {})}

    def add(self, name, type_, ver, pos, params, creds=None, **extra):
        n = {"parameters": params, "id": str(uuid.uuid4()), "name": name, "type": type_,
             "typeVersion": ver, "position": list(pos)}
        if creds:
            n["credentials"] = creds
        n.update(extra)
        self.nodes.append(n)
        return name

    def link(self, a, b, out=0):
        m = self.conns.setdefault(a, {"main": []})["main"]
        while len(m) <= out:
            m.append([])
        m[out].append({"node": b, "type": "main", "index": 0})

    def chain(self, *names):
        for a, b in zip(names, names[1:]):
            self.link(a, b)

    def note(self, text, pos, w=420, h=200, color=7):
        self.add("Note " + str(len(self.nodes)), "n8n-nodes-base.stickyNote", 1, pos,
                 {"content": text, "width": w, "height": h, "color": color})

    def dump(self, fname):
        with open(os.path.join(OUT, fname), "w") as f:
            json.dump({"name": self.name, "nodes": self.nodes, "connections": self.conns,
                       "active": False, "settings": self.settings, "pinData": {}}, f, indent=2)


def config(wf, pos, extra=None):
    vals = {"sheet_id": "PASTE_YOUR_GOOGLE_SHEET_ID_HERE", **(extra or {})}
    return wf.add("Config", "n8n-nodes-base.set", 3.4, pos, {
        "assignments": {"assignments": [{"id": str(uuid.uuid4()), "name": k, "value": v, "type": "string"}
                                        for k, v in vals.items()]},
        "includeOtherFields": False, "options": {}})


def code(wf, name, pos, js, each=False, **extra):
    p = {"jsCode": js.strip() + "\n"}
    if each:
        p = {"mode": "runOnceForEachItem", **p}
    return wf.add(name, "n8n-nodes-base.code", 2, pos, p, **extra)


def sheet_read(wf, name, pos, tab):
    return wf.add(name, "n8n-nodes-base.googleSheets", 4.5, pos, {
        "documentId": {"__rl": True, "value": "={{ $('Config').first().json.sheet_id }}", "mode": "id"},
        "sheetName": {"__rl": True, "value": tab, "mode": "name"}, "options": {}},
        CRED_SHEETS, executeOnce=True, alwaysOutputData=True, **RETRY)


def sheet_upsert(wf, name, pos, tab, key):
    return wf.add(name, "n8n-nodes-base.googleSheets", 4.5, pos, {
        "operation": "appendOrUpdate",
        "documentId": {"__rl": True, "value": "={{ $('Config').first().json.sheet_id }}", "mode": "id"},
        "sheetName": {"__rl": True, "value": tab, "mode": "name"},
        "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [key], "schema": []},
        "options": {"cellFormat": "RAW", "handlingExtraData": "ignoreIt"}}, CRED_SHEETS, **RETRY)


def settings_block(wf, x, y):
    a = config(wf, (x, y))
    b = sheet_read(wf, "Load Settings", (x + 220, y), "Settings")
    c = code(wf, "Settings", (x + 440, y), SETTINGS_JS)
    wf.chain(a, b, c)
    return a, c


CRED_AI = {"httpHeaderAuth": {"id": "", "name": "AI API key"}}


def llm(wf, name, pos, batch=False, soft=False):
    # Provider is a setting: any OpenAI-compatible endpoint (OpenAI, Groq, Gemini) via llm_url + llm_model.
    opts = {"timeout": 90000}
    if batch:
        opts["batching"] = {"batch": {"batchSize": 5, "batchInterval": 1500}}
    extra = {"onError": "continueRegularOutput"} if soft else {}
    return wf.add(name, "n8n-nodes-base.httpRequest", 4.2, pos, {
        "method": "POST",
        "url": "={{ $('Settings').first().json.llm_url || 'https://api.openai.com/v1/chat/completions' }}",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.request) }}",
        "options": opts}, CRED_AI, **RETRY, **extra)


def gmail_node(wf, name, pos, to, subject, message, html=True):
    return wf.add(name, "n8n-nodes-base.gmail", 2.1, pos, {
        "sendTo": to, "subject": subject, "emailType": "html" if html else "text", "message": message,
        "options": {"appendAttribution": False}}, CRED_GMAIL, **RETRY)


def if_node(wf, name, pos, left, op_type, op, right=None):
    cond = {"id": str(uuid.uuid4()), "leftValue": left, "rightValue": right if right is not None else "",
            "operator": {"type": op_type, "operation": op}}
    if right is None:
        cond["operator"]["singleValue"] = True
    return wf.add(name, "n8n-nodes-base.if", 2.2, pos, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                       "conditions": [cond], "combinator": "and"}, "options": {}})


def switch_expr(wf, name, pos, expr, n):
    return wf.add(name, "n8n-nodes-base.switch", 3.2, pos, {
        "mode": "expression", "numberOutputs": n, "output": expr})


# =====================================================================================
# WF1  Source & Screen
# =====================================================================================
w1 = WF("Recruiting Agent 1 - Source and Screen")
w1.note("## 1. Source and Screen\nRecruiter submits a role in the form. The agent writes the JD, searches public "
        "LinkedIn profiles via Serper, screens them with AI, looks up work emails (Apollo, shortlisted only), "
        "drafts outreach and saves everything to the Sheet as **Ready for review**.\n\n"
        "**Nothing is emailed to candidates here.** The recruiter approves in the Sheet; workflow 2 sends.",
        (-40, -40), w=560, h=220, color=4)

form = w1.add("New Role Form", "n8n-nodes-base.formTrigger", 2.2, (0, 300), {
    "authentication": "basicAuth",
    "formTitle": "New Role", "formDescription": "Submit a hiring need. You'll get an email when candidates are ready to review.",
    "formFields": {"values": [
        {"fieldLabel": "Job Title", "requiredField": True},
        {"fieldLabel": "Location", "requiredField": True, "placeholder": "e.g. Austin, TX  or  Remote US"},
        {"fieldLabel": "Seniority", "fieldType": "dropdown", "requiredField": True,
         "fieldOptions": {"values": [{"option": "Junior"}, {"option": "Mid"}, {"option": "Senior"}, {"option": "Lead"}]}},
        {"fieldLabel": "Must-have skills", "requiredField": True, "placeholder": "comma separated"},
        {"fieldLabel": "Nice-to-have skills", "placeholder": "comma separated"},
        {"fieldLabel": "Notes", "fieldType": "textarea", "placeholder": "Anything the AI should know about the role"}]},
    "options": {"respondWithOptions": {"values": {"formSubmittedText":
        "Got it. The agent is sourcing now; you'll get an email in a few minutes."}}}},
    {"httpBasicAuth": {"id": "", "name": "Form login"}})
cfg1, st1 = settings_block(w1, 220, 300)
w1.link(form, cfg1)
readc1 = sheet_read(w1, "Read Candidates", (880, 300), "Candidates")
w1.link(st1, readc1)

prep_jd = code(w1, "Prep JD Request", (1100, 300), r"""
const f = $('New Role Form').first().json;
const s = $('Settings').first().json;
const sys = 'You are a senior recruiter. Return ONLY a JSON object with keys: job_title (string), summary (2-3 sentences), '
  + 'responsibilities (array of strings, max 6), must_have_skills (array of strings), nice_to_have_skills (array of strings), '
  + 'search_titles (array of exactly 3 alternative job titles people doing this job commonly hold). '
  + 'Never add requirements about age, gender, ethnicity, religion, disability, nationality or any other protected characteristic. Do not invent salary.';
const user = JSON.stringify({ title: f['Job Title'], location: f['Location'], seniority: f['Seniority'],
  must_have: f['Must-have skills'], nice_to_have: f['Nice-to-have skills'] || '', notes: f['Notes'] || '' });
return [{ json: { request: { model: s.llm_model || 'gpt-4.1-mini', temperature: 0.3,
  response_format: { type: 'json_object' },
  messages: [{ role: 'system', content: sys }, { role: 'user', content: user }] } } }];
""")
llm_jd = llm(w1, "AI: Build JD", (1320, 300))

parse_jd = code(w1, "Parse JD", (1540, 300), r"""
const f = $('New Role Form').first().json;
let jd;
try { jd = JSON.parse($input.first().json.choices[0].message.content); }
catch (e) { throw new Error('AI returned an unreadable job description: ' + e.message); }
const list = v => Array.isArray(v) ? v.map(x => String(x).trim()).filter(Boolean)
  : String(v || '').split(',').map(x => x.trim()).filter(Boolean);
const now = new Date();
const stamp = now.toISOString().slice(0, 10).replace(/-/g, '');
return [{ json: {
  job_id: 'JOB-' + stamp + '-' + Math.random().toString(36).slice(2, 6).toUpperCase(),
  role: String(jd.job_title || f['Job Title']).trim(),
  location: String(f['Location']).trim(),
  seniority: f['Seniority'],
  summary: String(jd.summary || ''),
  responsibilities: list(jd.responsibilities).join('\n'),
  must_have: (list(jd.must_have_skills).length ? list(jd.must_have_skills) : list(f['Must-have skills'])).join(', '),
  nice_to_have: (list(jd.nice_to_have_skills).length ? list(jd.nice_to_have_skills) : list(f['Nice-to-have skills'])).join(', '),
  search_titles: list(jd.search_titles).slice(0, 3).join(' | '),
  status: 'Open',
  created_at: now.toISOString()
} }];
""")
save_job = sheet_upsert(w1, "Save Job", (1760, 300), "Jobs", "job_id")

queries = code(w1, "Build Search Queries", (1980, 300), r"""
const job = $('Parse JD').first().json;
const s = $('Settings').first().json;
// Serper's free plan rejects site:, quoted phrases and more than 10 results per search.
// search_use_site = yes (paid Serper plan): precise LinkedIn-only search, 20 results.
// Anything else (free plan, default): plain words, 10 results.
const paid = String(s.search_use_site || 'no').trim().toLowerCase() === 'yes';
const plain = v => String(v).replace(/["\u201C\u201D]/g, '').replace(/\s+/g, ' ').trim();
const titles = [...new Set([job.role, ...String(job.search_titles).split('|')].map(t => t.trim()).filter(Boolean))].slice(0, 4);
const loc = job.location.replace(/\bremote\b/ig, '').replace(/[(),]+/g, ' ').replace(/\s+/g, ' ').trim();
const skillList = job.must_have.split(',').map(x => x.trim()).filter(Boolean).slice(0, 2);
const num = paid ? 20 : 10;
const out = [];
for (const t of titles) {
  const base = paid ? `site:linkedin.com/in "${t}"` + (loc ? ` "${loc}"` : '') : plain(`LinkedIn ${t} ${loc}`);
  const skills = paid ? skillList.map(x => `"${x}"`).join(' ') : plain(skillList.join(' '));
  out.push({ json: { q: (base + ' ' + skills).trim(), num } });   // strict: title + location + top skills
  out.push({ json: { q: base, num } });                          // broad: title + location
}
return out;
""")
serper = w1.add("Search LinkedIn (Serper)", "n8n-nodes-base.httpRequest", 4.2, (2200, 300), {
    "method": "POST", "url": "https://google.serper.dev/search",
    "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
    "sendBody": True, "specifyBody": "json",
    "jsonBody": "={{ JSON.stringify({ q: $json.q, num: $json.num || 10, gl: $('Settings').first().json.search_country || 'us' }) }}",
    "options": {"batching": {"batch": {"batchSize": 2, "batchInterval": 1000}}, "timeout": 30000}},
    {"httpHeaderAuth": {"id": "", "name": "Serper API key"}}, **RETRY)

normalize = code(w1, "Normalize and Dedupe", (2420, 300), r"""
const job = $('Parse JD').first().json;
const s = $('Settings').first().json;
const max = Number(s.max_candidates_per_role) || 25;
const coolDays = Number(s.recontact_cooldown_days) || 60;
const handleOf = url => {
  const m = String(url || '').match(/linkedin\.com\/in\/([^\/?#]+)/i);
  if (!m) return null;
  try { return decodeURIComponent(m[1]).toLowerCase(); } catch (e) { return m[1].toLowerCase(); }
};
// People who opted out, or were emailed recently for any role, are not sourced again.
const blocked = new Set();
const now = Date.now();
for (const it of $('Read Candidates').all()) {
  const r = it.json; const h = handleOf(r.linkedin_url);
  if (!h) continue;
  if (r.status === 'Opted out') { blocked.add(h); continue; }
  const sent = [r.outreach_sent_at, r.followup_sent_at].map(v => Date.parse(v)).filter(n => !isNaN(n));
  if (sent.length && now - Math.max(...sent) < coolDays * 864e5) blocked.add(h);
}
const seen = new Set(); const rows = []; let skipped = 0;
for (const it of $input.all()) {
  for (const r of (it.json.organic || [])) {
    const h = handleOf(r.link);
    if (!h || seen.has(h)) continue;
    seen.add(h);
    if (blocked.has(h)) { skipped++; continue; }
    const title = String(r.title || '').replace(/\s*[|–\-]\s*LinkedIn\s*$/i, '');
    const parts = title.split(/\s+[–\-|]\s+/);
    const ts = new Date().toISOString();
    rows.push({
      candidate_id: job.job_id + '-' + h, job_id: job.job_id, role: job.role,
      name: (parts[0] || '').trim(), headline: parts.slice(1).join(' - ').trim(),
      linkedin_url: 'https://www.linkedin.com/in/' + h,
      snippet: String(r.snippet || '').replace(/\s+/g, ' ').trim(),
      status: 'Sourced', created_at: ts, updated_at: ts, _skipped: skipped
    });
  }
}
for (const r of rows) r._skipped = skipped;
return rows.slice(0, max).map(j => ({ json: j }));
""", alwaysOutputData=True)

has_c = if_node(w1, "Found Anyone?", (2640, 300), "={{ $json.candidate_id }}", "string", "notEmpty")
none_mail = gmail_node(w1, "Email: Nothing Found", (2860, 560),
    "={{ $('Settings').first().json.recruiter_email }}",
    "={{ 'No new candidates for ' + $('Parse JD').first().json.role }}",
    "={{ '<p>The search for <b>' + $('Parse JD').first().json.role + '</b> (' + $('Parse JD').first().json.location + ') found no new LinkedIn profiles.</p><p>Try a broader location, fewer must-have skills, or a more common job title, then submit the form again.</p>' }}")

prep_scr = code(w1, "Prep Screening", (2860, 300), PICK + r"""
const job = $('Parse JD').first().json;
const s = $('Settings').first().json;
const sys = 'You screen candidates for a recruiter using ONLY the public profile snippet given. Never invent experience. '
  + 'Ignore name, gender, age, ethnicity, nationality, photos and any other protected characteristic. '
  + 'Return ONLY a JSON object: score (integer 0-100, fit to the job), summary (1-2 sentences), strengths (array, max 3), gaps (array, max 3). '
  + 'If the snippet says little, score conservatively and say the profile needs a manual look.';
return $input.all().map(it => {
  const c = it.json;
  const user = JSON.stringify({
    job: { role: job.role, seniority: job.seniority, location: job.location, must_have: job.must_have, nice_to_have: job.nice_to_have },
    candidate: { headline: c.headline, snippet: c.snippet } });
  return { json: { row: c, request: { model: s.llm_model || 'gpt-4.1-mini', temperature: 0.2,
    response_format: { type: 'json_object' },
    messages: [{ role: 'system', content: sys }, { role: 'user', content: user }] } } };
});
""")
llm_scr = llm(w1, "AI: Screen", (3080, 300), batch=True, soft=True)
parse_scr = code(w1, "Parse Screening", (3300, 300), PICK + r"""
const row = $('Prep Screening').item.json.row;
const threshold = Number($('Settings').first().json.score_threshold) || 70;
let r;
try { r = JSON.parse($json.choices[0].message.content); }
catch (e) { r = { score: 0, summary: 'AI screening failed - review manually.', strengths: [], gaps: [] }; }
const score = Math.max(0, Math.min(100, Math.round(Number(r.score) || 0)));
const arr = v => Array.isArray(v) ? v.join('; ') : String(v || '');
return { json: pick({ ...row, score, summary: String(r.summary || ''), strengths: arr(r.strengths), gaps: arr(r.gaps),
  status: score >= threshold ? 'Shortlisted' : 'Not a fit', updated_at: new Date().toISOString() }) };
""", each=True)

is_short = if_node(w1, "Shortlisted?", (3520, 300), "={{ $json.status }}", "string", "equals", "Shortlisted")

apollo = w1.add("Find Work Email (Apollo)", "n8n-nodes-base.httpRequest", 4.2, (3740, 200), {
    "method": "POST", "url": "https://api.apollo.io/api/v1/people/match",
    "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
    "sendQuery": True, "queryParameters": {"parameters": [
        {"name": "linkedin_url", "value": "={{ $json.linkedin_url }}"},
        {"name": "reveal_personal_emails", "value": "false"},
        {"name": "reveal_phone_number", "value": "false"}]},
    "options": {"batching": {"batch": {"batchSize": 3, "batchInterval": 1000}}, "timeout": 30000}},
    {"httpHeaderAuth": {"id": "", "name": "Apollo API key"}},
    onError="continueRegularOutput", retryOnFail=True, maxTries=2, waitBetweenTries=3000)

merge_en = code(w1, "Add Email", (3960, 200), PICK + r"""
const row = $('Shortlisted?').item.json;
const p = ($json && $json.person) || {};
let email = String(p.email || '').trim();
if (!email || /not_unlocked|domain\.com$/i.test(email)) email = '';
const note = $json.error ? 'Email lookup failed: ' + String($json.error.message || $json.error).slice(0, 120)
  : (!email ? 'No email found - add one manually' : (p.email_status && p.email_status !== 'verified' ? 'Email is ' + p.email_status + ', not verified' : ''));
return { json: pick({ ...row, email, email_status: email ? (p.email_status || 'unknown') : '',
  current_title: p.title || '', current_company: (p.organization && p.organization.name) || '',
  system_note: note }) };
""", each=True)

prep_out = code(w1, "Prep Outreach", (4180, 200), r"""
const s = $('Settings').first().json;
const job = $('Parse JD').first().json;
const sys = 'You write short, warm, honest recruiter outreach emails in plain text (max 110 words, no subject in the body). '
  + 'Personalise only from the facts given (headline, current title, company). Do not claim to have read their full profile. '
  + 'Do not invent salary, client names or benefits. Include the literal token BOOKING_LINK once, as an invitation to book a 20-minute intro call. '
  + 'Sign off with the recruiter name and agency. Return ONLY a JSON object with keys subject and body.';
return $input.all().map(it => {
  const c = it.json;
  const user = JSON.stringify({ first_name: (c.name || '').split(' ')[0], headline: c.headline,
    current_title: c.current_title, current_company: c.current_company,
    role: job.role, role_summary: job.summary, location: job.location,
    recruiter: s.recruiter_name, agency: s.agency_name });
  return { json: { row: c, request: { model: s.llm_model || 'gpt-4.1-mini', temperature: 0.6,
    response_format: { type: 'json_object' },
    messages: [{ role: 'system', content: sys }, { role: 'user', content: user }] } } };
});
""")
llm_out = llm(w1, "AI: Draft Outreach", (4400, 200), batch=True, soft=True)
parse_out = code(w1, "Parse Outreach", (4620, 200), PICK + r"""
const row = $('Prep Outreach').item.json.row;
const s = $('Settings').first().json;
let r;
try { r = JSON.parse($json.choices[0].message.content); } catch (e) { r = {}; }
const first = (row.name || '').split(' ')[0] || 'there';
const subject = String(r.subject || `${row.role} opportunity`).trim();
let body = String(r.body || `Hi ${first},\n\nI'm recruiting for a ${row.role} role and your background looks like a strong match. Would you be open to a 20-minute intro call? BOOKING_LINK\n\n${s.recruiter_name}\n${s.agency_name}`);
// (URLSearchParams is not available in the n8n Code sandbox)
const qs = o => Object.entries(o).filter(([, v]) => v).map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('&');
const link = (s.booking_link || '') + (String(s.booking_link).includes('?') ? '&' : '?')
  + qs({ name: row.name || '', email: row.email || '', 'metadata[candidate_id]': row.candidate_id });
body = body.includes('BOOKING_LINK') ? body.replace('BOOKING_LINK', link) : body + '\n\nBook a time: ' + link;
return { json: pick({ ...row, outreach_subject: subject, outreach_body: body,
  status: row.email ? 'Ready for review' : 'Needs email', updated_at: new Date().toISOString() }) };
""", each=True)
save_c = sheet_upsert(w1, "Save Candidates", (4840, 300), "Candidates", "candidate_id")

summary = code(w1, "Build Summary", (3520, 620), r"""
const s = $('Settings').first().json;
const job = $('Parse JD').first().json;
const screened = $input.all().map(i => i.json);
let drafted = [];
try { drafted = $('Parse Outreach').all().map(i => i.json); } catch (e) { drafted = []; }
let skipped = 0;
try { skipped = Number($('Normalize and Dedupe').first().json._skipped) || 0; } catch (e) {}
const esc = v => String(v ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const ready = drafted.filter(r => r.status === 'Ready for review');
const needs = drafted.filter(r => r.status === 'Needs email');
const notFit = screened.filter(r => r.status === 'Not a fit').length;
const top = [...drafted].sort((a, b) => b.score - a.score).slice(0, 8);
const url = s.sheet_url || ('https://docs.google.com/spreadsheets/d/' + $('Config').first().json.sheet_id);
const rowsHtml = top.map(r => `<tr><td>${esc(r.score)}</td><td><a href="${esc(r.linkedin_url)}">${esc(r.name)}</a></td><td>${esc(r.headline)}</td><td>${esc(r.status)}</td></tr>`).join('');
const html = `<h2>${esc(job.role)} - candidates ready for review</h2>
<p>Screened <b>${screened.length}</b> profiles: <b>${ready.length}</b> ready for review, <b>${needs.length}</b> shortlisted but need an email, <b>${notFit}</b> not a fit` + (skipped ? `, ${skipped} skipped (opted out or contacted recently)` : '') + `.</p>
<table border="1" cellpadding="6" cellspacing="0"><tr><th>Score</th><th>Name</th><th>Headline</th><th>Status</th></tr>${rowsHtml}</table>
<p><b>Next step:</b> open the <a href="${esc(url)}">Candidates sheet</a>, read each draft (edit it if you like), then change the status to <b>Approved</b>. Approved emails go out automatically within the hour.</p>`;
return [{ json: { subject: `${ready.length + needs.length} candidates ready for review: ${job.role}`, html } }];
""")
sum_mail = gmail_node(w1, "Email: Review Summary", (3740, 620),
    "={{ $('Settings').first().json.recruiter_email }}", "={{ $json.subject }}", "={{ $json.html }}")

w1.chain(readc1, prep_jd, llm_jd, parse_jd, save_job, queries, serper, normalize, has_c)
w1.link(has_c, prep_scr, 0); w1.link(has_c, none_mail, 1)
w1.chain(prep_scr, llm_scr, parse_scr)
w1.link(parse_scr, is_short)       # upper branch runs first (v1 order)
w1.link(parse_scr, summary)        # lower branch: runs after the shortlist branch finishes
w1.link(is_short, apollo, 0); w1.link(is_short, save_c, 1)
w1.chain(apollo, merge_en, prep_out, llm_out, parse_out, save_c)
w1.link(summary, sum_mail)
w1.dump("1-source-and-screen.json")

# =====================================================================================
# WF2  Outbox
# =====================================================================================
w2 = WF("Recruiting Agent 2 - Outbox (send, follow up, detect replies)",
        {"timezone": "America/New_York"})
w2.note("## 2. Outbox (runs hourly, Mon-Fri 9am-5pm)\n"
        "- **Approved** rows: sends the outreach email, status -> Contacted\n"
        "- **Contacted / Followed up**: checks the Gmail thread for a reply. Reply -> Replied (or Opted out if they said unsubscribe). "
        "Bounce -> Email bounced. No reply after N days -> one follow-up in the same thread, then No response.\n"
        "- **Selected / Rejected** (set by the recruiter): sends the matching template once\n"
        "- Respects `daily_send_limit` (rolling 24h)", (-40, -60), w=620, h=260, color=4)
tick = w2.add("Hourly, Weekdays 9-5", "n8n-nodes-base.scheduleTrigger", 1.2, (0, 300), {
    "rule": {"interval": [{"field": "cronExpression", "expression": "0 9-17 * * 1-5"}]}})
cfg2, st2 = settings_block(w2, 220, 300)
w2.link(tick, cfg2)
tpl2 = sheet_read(w2, "Load Templates", (880, 300), "Templates")
readc2 = sheet_read(w2, "Read Candidates", (1100, 300), "Candidates")
w2.chain(st2, tpl2, readc2)

plan = code(w2, "Plan Actions", (1320, 300), r"""
const s = $('Settings').first().json;
const T = {};
for (const it of $('Load Templates').all()) { const k = String(it.json.key || '').trim().toLowerCase(); if (k) T[k] = it.json; }
const rows = $input.all().map(i => i.json).filter(r => r.candidate_id);
const DAY = 864e5, now = Date.now();
const ts = v => { const n = Date.parse(v); return isNaN(n) ? null : n; };
const isEmail = e => /^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$/.test(String(e || '').trim());
const fuDays = Number(s.followup_after_days) || 3;
const closeDays = Number(s.close_after_days) || 7;

// Rolling 24h send cap protects the sender's domain reputation.
let sent24 = 0;
for (const r of rows) for (const k of ['outreach_sent_at', 'followup_sent_at', 'candidate_notified_at']) {
  const t = ts(r[k]); if (t && now - t < DAY) sent24++;
}
let cap = Math.max(0, (Number(s.daily_send_limit) || 30) - sent24);

const bookingLink = r => {
  const qs = o => Object.entries(o).filter(([, v]) => v).map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('&');
  return (s.booking_link || '') + (String(s.booking_link).includes('?') ? '&' : '?')
    + qs({ name: r.name || '', email: String(r.email || '').trim(), 'metadata[candidate_id]': r.candidate_id });
};
const fill = (str, r) => String(str || '').replace(/\{\{\s*(\w+)\s*\}\}/g, (m, k) => {
  const v = { first_name: String(r.name || '').split(' ')[0] || 'there', name: r.name, role: r.role,
    agency: s.agency_name, recruiter: s.recruiter_name, recruiter_email: s.recruiter_email,
    mailing_address: s.mailing_address, booking_link: bookingLink(r) }[k];
  return v == null ? '' : String(v);
});
const footer = r => T.footer ? '\n\n--\n' + fill(T.footer.body, r) : '';
const out = [];
const send = j => out.push({ json: { route: 'send', ...j } });
const mark = (r, upd) => out.push({ json: { route: 'mark', update: { candidate_id: r.candidate_id, updated_at: new Date().toISOString(), ...upd } } });

// 1) Selected / Rejected -> tell the candidate once
for (const r of rows) {
  const st = String(r.status || '').trim();
  if ((st !== 'Selected' && st !== 'Rejected') || r.candidate_notified_at) continue;
  const t = T[st.toLowerCase()];
  if (!t) continue;
  if (!isEmail(r.email)) { if (r.system_note !== 'No valid email to send the update to') mark(r, { system_note: 'No valid email to send the update to' }); continue; }
  if (cap <= 0) continue;
  cap--;
  send({ kind: 'notify', candidate_id: r.candidate_id, to: String(r.email).trim(), subject: fill(t.subject, r), body: fill(t.body, r) });
}
// 2) Contacted / Followed up -> check the thread (follow-ups reserve capacity first)
for (const r of rows) {
  const st = String(r.status || '').trim();
  if ((st !== 'Contacted' && st !== 'Followed up') || !r.thread_id) continue;
  const sentAt = ts(r.outreach_sent_at), fuAt = ts(r.followup_sent_at);
  let followup_due = false;
  if (st === 'Contacted' && !fuAt && sentAt && now - sentAt >= fuDays * DAY && T.followup && cap > 0) { followup_due = true; cap--; }
  const close_due = (st === 'Followed up' && fuAt && now - fuAt >= closeDays * DAY)
                 || (st === 'Contacted' && !T.followup && sentAt && now - sentAt >= (fuDays + closeDays) * DAY);
  out.push({ json: { route: 'check', candidate_id: r.candidate_id, thread_id: String(r.thread_id), to: String(r.email || '').trim(),
    followup_due, close_due,
    subject: 'Re: ' + String(r.outreach_subject || r.role).replace(/^re:\s*/i, ''),
    body: T.followup ? fill(T.followup.body, r) + footer(r) : '' } });
}
// 3) Approved -> send the outreach the recruiter reviewed
for (const r of rows) {
  if (String(r.status || '').trim() !== 'Approved') continue;
  if (!isEmail(r.email)) { mark(r, { status: 'Needs email', system_note: 'Approved, but the email column is empty or invalid' }); continue; }
  if (!String(r.outreach_body || '').trim()) { mark(r, { status: 'Ready for review', system_note: 'Approved, but the outreach body is empty' }); continue; }
  if (cap <= 0) continue;   // waits for the next run
  cap--;
  send({ kind: 'outreach', candidate_id: r.candidate_id, to: String(r.email).trim(),
    subject: String(r.outreach_subject || r.role), body: String(r.outreach_body) + footer(r) });
}
return out;
""")
route1 = switch_expr(w2, "Route", (1540, 300), "={{ ({ send: 0, check: 1, mark: 2 })[$json.route] ?? 3 }}", 4)

build = code(w2, "Build Email", (1980, 120), r"""
const j = $json;
const s = $('Settings').first().json;
const b64 = str => Buffer.from(String(str), 'utf8').toString('base64');
const headers = [
  `To: ${j.to}`,
  `Subject: =?UTF-8?B?${b64(j.subject)}?=`,
  'MIME-Version: 1.0',
  'Content-Type: text/plain; charset=UTF-8',
  'Content-Transfer-Encoding: base64',
  `List-Unsubscribe: <mailto:${s.recruiter_email}?subject=unsubscribe>`
];
if (j.in_reply_to) headers.push(`In-Reply-To: ${j.in_reply_to}`, `References: ${j.in_reply_to}`);
const mime = headers.join('\r\n') + '\r\n\r\n' + b64(j.body).replace(/(.{76})/g, '$1\r\n');
const raw = Buffer.from(mime, 'utf8').toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
return { json: { ...j, gmail: j.thread_id ? { raw, threadId: j.thread_id } : { raw } } };
""", each=True)
gsend = w2.add("Gmail: Send", "n8n-nodes-base.httpRequest", 4.2, (2200, 120), {
    "method": "POST", "url": "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
    "authentication": "predefinedCredentialType", "nodeCredentialType": "gmailOAuth2",
    "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.gmail) }}",
    "options": {"batching": {"batch": {"batchSize": 1, "batchInterval": 2000}}}},
    CRED_GMAIL, onError="continueRegularOutput")
after = code(w2, "After Send", (2420, 120), r"""
const req = $('Build Email').item.json;
const now = new Date().toISOString();
const u = { candidate_id: req.candidate_id, updated_at: now };
if ($json.error || !$json.id) {
  const msg = $json.error ? ($json.error.message || JSON.stringify($json.error)) : 'no message id returned';
  u.system_note = `Send failed ${now.slice(0, 16)}: ${String(msg).slice(0, 150)}`;
  return { json: u };
}
u.system_note = '';
if (req.kind === 'outreach') Object.assign(u, { status: 'Contacted', thread_id: $json.threadId, outreach_sent_at: now });
if (req.kind === 'followup') Object.assign(u, { status: 'Followed up', followup_sent_at: now });
if (req.kind === 'notify') Object.assign(u, { candidate_notified_at: now });
return { json: u };
""", each=True)

thread = w2.add("Gmail: Get Thread", "n8n-nodes-base.httpRequest", 4.2, (1980, 380), {
    "method": "GET",
    "url": "=https://gmail.googleapis.com/gmail/v1/users/me/threads/{{ encodeURIComponent($json.thread_id) }}?format=metadata&metadataHeaders=From&metadataHeaders=Message-ID",
    "authentication": "predefinedCredentialType", "nodeCredentialType": "gmailOAuth2", "options": {}},
    CRED_GMAIL, onError="continueRegularOutput", **RETRY)
decide = code(w2, "Decide", (2200, 380), r"""
const p = $('Plan Actions').item.json;
const now = new Date().toISOString();
if ($json.error || !Array.isArray($json.messages) || !$json.messages.length) return { json: { route: 'skip' } };
const msgs = $json.messages;
const hdr = (m, n) => (((m.payload || {}).headers) || []).find(h => String(h.name).toLowerCase() === n.toLowerCase())?.value || '';
const addr = v => { const m = String(v).match(/<([^>]+)>/); return (m ? m[1] : String(v)).trim().toLowerCase(); };
const me = addr(hdr(msgs[0], 'From'));
const others = msgs.filter(m => addr(hdr(m, 'From')) !== me);
const bounce = others.find(m => /mailer-daemon|postmaster/i.test(hdr(m, 'From')));
if (bounce) return { json: { route: 'mark', update: { candidate_id: p.candidate_id, status: 'Email bounced', system_note: 'Delivery failed - check the address', updated_at: now } } };
if (others.length) {
  const last = others[others.length - 1];
  const optOut = /\b(unsubscribe|remove me|stop (emailing|contacting)|do not (email|contact)|don'?t (email|contact)|not interested)\b/i.test(last.snippet || '');
  return { json: { route: 'mark', update: { candidate_id: p.candidate_id, status: optOut ? 'Opted out' : 'Replied',
    last_reply_at: new Date(Number(last.internalDate) || Date.now()).toISOString(), updated_at: now } } };
}
if (p.followup_due && p.to) {
  return { json: { route: 'send', kind: 'followup', candidate_id: p.candidate_id, to: p.to, subject: p.subject,
    body: p.body, thread_id: p.thread_id, in_reply_to: hdr(msgs[msgs.length - 1], 'Message-ID') } };
}
if (p.close_due) return { json: { route: 'mark', update: { candidate_id: p.candidate_id, status: 'No response', updated_at: now } } };
return { json: { route: 'skip' } };
""", each=True)
route2 = switch_expr(w2, "Route After Check", (2420, 380), "={{ ({ send: 0, mark: 1 })[$json.route] ?? 2 }}", 3)
shape = code(w2, "Shape Update", (2640, 560), "return { json: $json.update };", each=True)
upd2 = sheet_upsert(w2, "Update Sheet", (2860, 300), "Candidates", "candidate_id")

w2.chain(readc2, plan, route1)
w2.link(route1, build, 0); w2.link(route1, thread, 1); w2.link(route1, shape, 2)
w2.chain(build, gsend, after, upd2)
w2.chain(thread, decide, route2)
w2.link(route2, build, 0); w2.link(route2, shape, 1)
w2.link(shape, upd2)
w2.dump("2-outbox.json")

# =====================================================================================
# WF3  Interview booked (Cal.com webhook)
# =====================================================================================
w3 = WF("Recruiting Agent 3 - Interview Booked (Cal.com)")
w3.note("## 3. Interview Booked\nCal.com calls this webhook when a candidate books, reschedules or cancels. "
        "Cal.com creates the Google Calendar event and Meet link itself, so this workflow only updates the "
        "Sheet and tells the recruiter.\n\nMatches the booking by `candidate_id` (sent in the booking link), "
        "falling back to the attendee's email.", (-40, -60), w=560, h=220, color=4)
hook = w3.add("Cal.com Webhook", "n8n-nodes-base.webhook", 2, (0, 300), {
    "httpMethod": "POST", "path": "recruiting-agent/booking", "authentication": "headerAuth",
    "responseMode": "onReceived", "options": {}},
    {"httpHeaderAuth": {"id": "", "name": "Webhook secret"}}, webhookId=str(uuid.uuid4()))
cfg3, st3 = settings_block(w3, 220, 300)
w3.link(hook, cfg3)
readc3 = sheet_read(w3, "Read Candidates", (880, 300), "Candidates")
w3.link(st3, readc3)
match = code(w3, "Match Booking", (1100, 300), r"""
const body = $('Cal.com Webhook').first().json.body || {};
const ev = String(body.triggerEvent || '');
const p = body.payload || {};
const att = (p.attendees && p.attendees[0]) || {};
const meta = p.metadata || {};
const responses = p.responses || {};
const email = String(att.email || (responses.email && responses.email.value) || '').trim().toLowerCase();
const name = att.name || (responses.name && responses.name.value) || 'Someone';
const rows = $input.all().map(i => i.json).filter(r => r.candidate_id);
let row = meta.candidate_id ? rows.find(r => r.candidate_id === meta.candidate_id) : null;
if (!row && email) row = rows.filter(r => String(r.email || '').trim().toLowerCase() === email)
  .sort((a, b) => String(b.outreach_sent_at || '').localeCompare(String(a.outreach_sent_at || '')))[0];
const statusFor = { BOOKING_CREATED: 'Interview scheduled', BOOKING_RESCHEDULED: 'Interview scheduled', BOOKING_CANCELLED: 'Interview cancelled' };
if (!statusFor[ev]) return [];   // ignore other Cal.com events
const meet = meta.videoCallUrl || (/^https?:/.test(String(p.location || '')) ? p.location : '');
const when = p.startTime || '';
const update = row ? { candidate_id: row.candidate_id, status: statusFor[ev], updated_at: new Date().toISOString(),
  interview_time: ev === 'BOOKING_CANCELLED' ? '' : when, meet_link: ev === 'BOOKING_CANCELLED' ? '' : meet,
  ...(ev === 'BOOKING_CREATED' ? { interview_booked_at: new Date().toISOString() } : {}),
  ...(email && !row.email ? { email } : {}) } : null;
const verb = { BOOKING_CREATED: 'booked', BOOKING_RESCHEDULED: 'rescheduled', BOOKING_CANCELLED: 'cancelled' }[ev];
const esc = v => String(v ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const subject = `Interview ${verb}: ${name}` + (row ? ` (${row.role})` : '');
const html = `<p><b>${esc(name)}</b> (${esc(email)}) ${verb} an interview` + (when && ev !== 'BOOKING_CANCELLED' ? ` for <b>${esc(new Date(when).toUTCString())}</b>` : '') + `.</p>`
  + (meet && ev !== 'BOOKING_CANCELLED' ? `<p>Meeting link: <a href="${esc(meet)}">${esc(meet)}</a></p>` : '')
  + (row ? `<p>Score ${esc(row.score)} - ${esc(row.summary)}<br><a href="${esc(row.linkedin_url)}">LinkedIn profile</a></p>`
         : '<p>This booking did not match anyone in the Candidates sheet, so the sheet was not updated.</p>');
return [{ json: { matched: !!row, update, subject, html } }];
""")
matched = if_node(w3, "Matched a Candidate?", (1320, 300), "={{ $json.matched }}", "boolean", "true")
shape3 = code(w3, "Shape Update", (1540, 200), "return { json: $json.update };", each=True)
upd3 = sheet_upsert(w3, "Update Sheet", (1760, 200), "Candidates", "candidate_id")
notify3 = gmail_node(w3, "Email Recruiter", (1980, 300), "={{ $('Settings').first().json.recruiter_email }}",
                     "={{ $('Match Booking').first().json.subject }}", "={{ $('Match Booking').first().json.html }}")
w3.chain(readc3, match, matched)
w3.link(matched, shape3, 0); w3.link(matched, notify3, 1)
w3.chain(shape3, upd3, notify3)
w3.dump("3-interview-booked.json")

# =====================================================================================
# WF4  Weekly report
# =====================================================================================
w4 = WF("Recruiting Agent 4 - Weekly Hiring Report", {"timezone": "America/New_York"})
w4.note("## 4. Weekly Hiring Report (Mondays 9am)\nAll numbers are counted in code from the Sheet. "
        "The AI only writes the three suggested next actions; if the AI call fails the report still sends.",
        (-40, -60), w=520, h=160, color=4)
mon = w4.add("Mondays 9am", "n8n-nodes-base.scheduleTrigger", 1.2, (0, 300), {
    "rule": {"interval": [{"field": "weeks", "weeksInterval": 1, "triggerAtDay": [1], "triggerAtHour": 9}]}})
cfg4, st4 = settings_block(w4, 220, 300)
w4.link(mon, cfg4)
readc4 = sheet_read(w4, "Read Candidates", (880, 300), "Candidates")
w4.link(st4, readc4)
stats = code(w4, "Count Pipeline", (1100, 300), r"""
const s = $('Settings').first().json;
const rows = $input.all().map(i => i.json).filter(r => r.candidate_id);
const now = Date.now(), WEEK = 7 * 864e5;
const t = v => { const n = Date.parse(v); return isNaN(n) ? null : n; };
const roles = {};
for (const r of rows) {
  const k = r.job_id || 'unknown';
  const j = roles[k] = roles[k] || { role: r.role, sourced: 0, shortlisted: 0, awaiting_review: 0, needs_email: 0,
    contacted: 0, replied: 0, interviews: 0, selected: 0, opted_out: 0 };
  j.sourced++;
  if (!['Sourced', 'Not a fit'].includes(r.status)) j.shortlisted++;
  if (r.status === 'Ready for review') j.awaiting_review++;
  if (r.status === 'Needs email') j.needs_email++;
  if (r.outreach_sent_at) j.contacted++;
  if (r.last_reply_at) j.replied++;
  if (r.interview_booked_at || r.interview_time || r.status === 'Interview scheduled') j.interviews++;
  if (r.status === 'Selected') j.selected++;
  if (r.status === 'Opted out') j.opted_out++;
}
const list = Object.entries(roles).map(([job_id, j]) => ({ job_id, ...j,
  reply_rate: j.contacted ? Math.round(100 * j.replied / j.contacted) + '%' : '-' }));
const week = {
  new_candidates: rows.filter(r => t(r.created_at) > now - WEEK).length,
  emails_sent: rows.filter(r => t(r.outreach_sent_at) > now - WEEK).length,
  replies: rows.filter(r => t(r.last_reply_at) > now - WEEK).length,
  // counted by when the booking was made, so it still counts after Selected / Rejected
  interviews_booked: rows.filter(r => t(r.interview_booked_at) > now - WEEK).length
};
const waiting = rows.filter(r => r.status === 'Replied').map(r => ({ name: r.name, role: r.role, replied: r.last_reply_at, url: r.linkedin_url }));
const upcoming = rows.filter(r => r.status !== 'Interview cancelled' && t(r.interview_time) > now && t(r.interview_time) < now + WEEK)
  .map(r => ({ name: r.name, role: r.role, time: r.interview_time, meet: r.meet_link }));
const sys = 'You advise a recruiting agency owner. From the pipeline numbers given, return ONLY a JSON object {"actions": [three short, specific next actions]}. Use only the data given; do not invent numbers.';
return [{ json: { roles: list, week, waiting, upcoming,
  request: { model: s.llm_model || 'gpt-4.1-mini', temperature: 0.3, response_format: { type: 'json_object' },
    messages: [{ role: 'system', content: sys }, { role: 'user', content: JSON.stringify({ roles: list, week, waiting_on_recruiter: waiting.length }) }] } } }];
""")
llm4 = llm(w4, "AI: Suggest Actions", (1320, 300), soft=True)
report = code(w4, "Build Report", (1540, 300), r"""
const d = $('Count Pipeline').first().json;
const s = $('Settings').first().json;
let actions = [];
try { actions = JSON.parse($input.first().json.choices[0].message.content).actions || []; } catch (e) { actions = []; }
const esc = v => String(v ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const th = 'style="text-align:left;background:#f3f3f3"';
const roleRows = d.roles.map(r => `<tr><td>${esc(r.role)}</td><td>${r.sourced}</td><td>${r.shortlisted}</td><td>${r.awaiting_review}</td><td>${r.needs_email}</td><td>${r.contacted}</td><td>${r.replied} (${r.reply_rate})</td><td>${r.interviews}</td><td>${r.selected}</td></tr>`).join('');
const url = s.sheet_url || ('https://docs.google.com/spreadsheets/d/' + $('Config').first().json.sheet_id);
let html = `<h2>${esc(s.agency_name)} - weekly hiring report</h2>
<p>This week: <b>${d.week.new_candidates}</b> new candidates, <b>${d.week.emails_sent}</b> outreach emails sent, <b>${d.week.replies}</b> replies, <b>${d.week.interviews_booked}</b> interviews booked.</p>
<h3>Pipeline by role</h3>
<table border="1" cellpadding="6" cellspacing="0"><tr><th ${th}>Role</th><th ${th}>Sourced</th><th ${th}>Shortlisted</th><th ${th}>To review</th><th ${th}>Need email</th><th ${th}>Contacted</th><th ${th}>Replied</th><th ${th}>Interviews</th><th ${th}>Selected</th></tr>${roleRows || '<tr><td colspan="9">No candidates yet</td></tr>'}</table>`;
if (d.waiting.length) html += `<h3>Replied - waiting on you (${d.waiting.length})</h3><ul>` + d.waiting.map(w => `<li><a href="${esc(w.url)}">${esc(w.name)}</a> - ${esc(w.role)}</li>`).join('') + '</ul>';
if (d.upcoming.length) html += '<h3>Interviews in the next 7 days</h3><ul>' + d.upcoming.map(u => `<li>${esc(u.name)} - ${esc(u.role)} - ${esc(new Date(u.time).toUTCString())}${u.meet ? ` - <a href="${esc(u.meet)}">join</a>` : ''}</li>`).join('') + '</ul>';
if (actions.length) html += '<h3>Suggested next actions</h3><ul>' + actions.slice(0, 3).map(a => `<li>${esc(a)}</li>`).join('') + '</ul>';
html += `<p><a href="${esc(url)}">Open the Candidates sheet</a></p>`;
return [{ json: { html, subject: `${s.agency_name} - weekly hiring report` } }];
""")
send4 = gmail_node(w4, "Email Report", (1760, 300), "={{ $('Settings').first().json.recruiter_email }}",
                   "={{ $json.subject }}", "={{ $json.html }}")
w4.chain(readc4, stats, llm4, report, send4)
w4.dump("4-weekly-report.json")

# =====================================================================================
# WF5  Error alerts
# =====================================================================================
w5 = WF("Recruiting Agent 5 - Error Alerts")
w5.note("## 5. Error Alerts\nSet this as the **Error workflow** in the settings of workflows 1-4. "
        "Any failure emails the admin with the step that broke and a link to the run.", (-40, -60), w=460, h=160, color=4)
et = w5.add("On Workflow Error", "n8n-nodes-base.errorTrigger", 1, (0, 300), {})
cfg5 = config(w5, (220, 300), {"admin_email": "PASTE_ADMIN_EMAIL_HERE"})
cfg5_node = w5.nodes[-1]
cfg5_node["parameters"]["assignments"]["assignments"] = [a for a in cfg5_node["parameters"]["assignments"]["assignments"] if a["name"] != "sheet_id"]
cfg5_node["parameters"]["includeOtherFields"] = True
alert = gmail_node(w5, "Email Admin", (440, 300), "={{ $json.admin_email }}",
    "={{ '[Recruiting Agent] ' + $json.workflow.name + ' failed' }}",
    "={{ '<p><b>' + $json.workflow.name + '</b> failed at step <b>' + ($json.execution.lastNodeExecuted || '?') + '</b>.</p><p>Error: ' + (($json.execution.error || {}).message || 'unknown') + '</p><p><a href=\"' + ($json.execution.url || '') + '\">Open the failed run</a></p>' }}")
w5.chain(et, cfg5, alert)
w5.dump("5-error-alerts.json")

json.dump({"CAND_COLS": CAND_COLS, "JOB_COLS": JOB_COLS}, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "columns.json"), "w"))
print("generated")
