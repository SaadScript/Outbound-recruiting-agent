// Runs each n8n Code node against mock data, emulating $input, $json, $('Node'), Buffer.
const fs = require('fs');
const assert = require('assert');
const DIR = require('path').join(__dirname, '..', 'workflows') + '/';
const wf = f => JSON.parse(fs.readFileSync(DIR + f, 'utf8'));
const W = { 1: wf('1-source-and-screen.json'), 2: wf('2-outbox.json'), 3: wf('3-interview-booked.json'), 4: wf('4-weekly-report.json') };
const codeOf = (w, name) => { const n = W[w].nodes.find(n => n.name === name); if (!n) throw new Error('no node ' + name); return n.parameters; };
const wrap = arr => arr.map(j => ({ json: j }));

async function run(w, name, input, refs = {}) {
  const p = codeOf(w, name);
  const items = wrap(input);
  const mk = (idx) => (n) => {
    if (!(n in refs)) throw new Error(`Node '${n}' hasn't been executed`);
    const its = wrap(refs[n]);
    return { first: () => its[0], all: () => its, item: its[idx] ?? its[0] };
  };
  const $input = { all: () => items, first: () => items[0] };
  const fn = new Function('$input', '$json', '$', 'Buffer', 'URLSearchParams', `return (async () => { ${p.jsCode} })();`);
  if (p.mode === 'runOnceForEachItem') {
    const out = [];
    for (let i = 0; i < items.length; i++) { const r = await fn($input, items[i].json, mk(i), Buffer, undefined); if (r) out.push(r.json); }
    return out;
  }
  const r = await fn($input, undefined, mk(0), Buffer, undefined);
  return (r || []).map(x => x.json);
}

const SETTINGS = { agency_name: 'Acme Talent', recruiter_name: 'Sara Ali', recruiter_email: 'sara@acmetalent.com',
  score_threshold: '70', max_candidates_per_role: '25', daily_send_limit: '3', followup_after_days: '3', close_after_days: '7',
  booking_link: 'https://cal.com/acme/intro', recontact_cooldown_days: '60', mailing_address: '1 Main St, Austin TX',
  llm_model: 'gpt-4.1-mini', search_country: 'us' };
const CONFIG = { sheet_id: 'SHEET123' };
const llmResp = obj => ({ choices: [{ message: { content: typeof obj === 'string' ? obj : JSON.stringify(obj) } }] });
const daysAgo = d => new Date(Date.now() - d * 864e5).toISOString();
const ok = m => console.log('  ✓ ' + m);

(async () => {
  // ---------------- Settings
  console.log('Settings');
  const st = await run(1, 'Settings', Object.entries(SETTINGS).map(([key, value]) => ({ key, value, row_number: 2 })));
  assert.equal(st[0].recruiter_email, 'sara@acmetalent.com'); ok('rows -> object');
  await assert.rejects(run(1, 'Settings', [{ key: 'agency_name', value: 'x' }]), /recruiter_name/); ok('missing key -> clear error');

  // ---------------- WF1
  console.log('WF1 Source and Screen');
  const form = { 'Job Title': 'Property Manager', 'Location': 'Austin, TX', 'Seniority': 'Mid', 'Must-have skills': 'Yardi, Lease administration, Tenant relations', 'Nice-to-have skills': '', 'Notes': '' };
  const base = { 'New Role Form': [form], Settings: [SETTINGS], Config: [CONFIG] };
  const pj = await run(1, 'Prep JD Request', [{}], base);
  assert.equal(pj[0].request.response_format.type, 'json_object'); ok('JD request built');
  await assert.rejects(run(1, 'Parse JD', [llmResp('not json')], base), /unreadable/); ok('bad AI JSON -> clear error');
  const job = (await run(1, 'Parse JD', [llmResp({ job_title: 'Property Manager', summary: 'Run a 300-unit portfolio.', responsibilities: ['a', 'b'],
    must_have_skills: ['Yardi', 'Lease administration'], nice_to_have_skills: [], search_titles: ['Community Manager', 'Leasing Manager', 'Asset Manager'] })], base))[0];
  assert.match(job.job_id, /^JOB-\d{8}-[A-Z0-9]{4}$/); assert.equal(job.must_have, 'Yardi, Lease administration'); ok('JD parsed: ' + job.job_id);
  const R1 = { ...base, 'Parse JD': [job] };
  const qs = await run(1, 'Build Search Queries', [job], { ...R1, Settings: [{ ...SETTINGS, search_use_site: 'yes' }] });
  assert.equal(qs.length, 8); assert.ok(qs[0].q.startsWith('site:linkedin.com/in "Property Manager" "Austin TX" "Yardi"')); ok(`paid plan: ${qs[0].q}`);
  const qf = await run(1, 'Build Search Queries', [job], R1);
  assert.equal(qf[0].q, 'LinkedIn Property Manager Austin TX Yardi Lease administration'); assert.ok(!qf.some(q => /site:|"/.test(q.q)) && qf.every(q => q.num === 10) && qs.every(q => q.num === 20)); ok(`free plan (default): ${qf[0].q} | num ${qf[0].num}`);
  const remoteQ = await run(1, 'Build Search Queries', [job], { ...R1, 'Parse JD': [{ ...job, location: 'Remote US' }] });
  assert.equal(remoteQ[1].q, 'LinkedIn Property Manager US'); ok('"Remote US" -> US');

  const serp = [{ organic: [
    { title: 'Jane Doe - Property Manager - Greystar | LinkedIn', link: 'https://www.linkedin.com/in/jane-doe-123', snippet: 'Property Manager at Greystar. Yardi expert.' },
    { title: 'Bob Roe – Leasing Manager – LinkedIn', link: 'https://www.linkedin.com/in/bobroe?trk=x', snippet: 'Leasing' },
    { title: 'Company page', link: 'https://www.linkedin.com/company/greystar', snippet: '' } ] },
    { organic: [
    { title: 'Jane Doe - Property Manager | LinkedIn', link: 'https://uk.linkedin.com/in/jane-doe-123/', snippet: 'dup' },
    { title: 'Opted Out - PM | LinkedIn', link: 'https://www.linkedin.com/in/optedout', snippet: '' },
    { title: 'Recent Guy - PM | LinkedIn', link: 'https://www.linkedin.com/in/recentguy', snippet: '' },
    { title: 'Old Contact - PM | LinkedIn', link: 'https://www.linkedin.com/in/oldcontact', snippet: '' } ] }, {}];
  const existing = [{ linkedin_url: 'https://www.linkedin.com/in/optedout', status: 'Opted out' },
    { linkedin_url: 'https://www.linkedin.com/in/recentguy', status: 'Contacted', outreach_sent_at: daysAgo(10) },
    { linkedin_url: 'https://www.linkedin.com/in/oldcontact', status: 'No response', outreach_sent_at: daysAgo(90) }];
  const cands = await run(1, 'Normalize and Dedupe', serp, { ...R1, 'Read Candidates': existing });
  assert.deepEqual(cands.map(c => c.name), ['Jane Doe', 'Bob Roe', 'Old Contact']);
  assert.equal(cands[0].headline, 'Property Manager - Greystar'); assert.equal(cands[1].linkedin_url, 'https://www.linkedin.com/in/bobroe');
  assert.equal(cands[0]._skipped, 2); ok('dedupe across subdomains, skip opted-out + recently contacted, keep 90-day-old contact');
  const empty = await run(1, 'Normalize and Dedupe', [{}], { ...R1, 'Read Candidates': [{}] });
  assert.equal(empty.length, 0); ok('no results -> empty (routes to "Nothing Found" email)');

  const ps = await run(1, 'Prep Screening', cands, R1);
  assert.ok(!JSON.stringify(ps[0].request.messages[1]).includes('Jane')); ok('name not sent to the screening AI');
  const scr = await run(1, 'Parse Screening', [llmResp({ score: 85, summary: 'Strong', strengths: ['Yardi'], gaps: [] }), llmResp({ score: 40, summary: 'Weak' }), llmResp('garbage')],
    { ...R1, 'Prep Screening': ps });
  assert.deepEqual(scr.map(s => s.status), ['Shortlisted', 'Not a fit', 'Not a fit']);
  assert.ok(!('_skipped' in scr[0]) && !('row' in scr[0])); assert.match(scr[2].summary, /review manually/); ok('threshold applied, unparseable AI -> Not a fit with note, only sheet columns kept');

  const short = [scr[0], { ...scr[0], candidate_id: 'x2', name: 'Al Two' }, { ...scr[0], candidate_id: 'x3', name: 'Cy Three' }];
  const apolloOut = [{ person: { email: 'jane@greystar.com', email_status: 'verified', title: 'Property Manager', organization: { name: 'Greystar' } } },
    { person: { email: 'email_not_unlocked@domain.com' } }, { error: { message: '401 - invalid api key' } }];
  const en = await run(1, 'Add Email', apolloOut, { ...R1, 'Shortlisted?': short });
  assert.equal(en[0].email, 'jane@greystar.com'); assert.equal(en[0].current_company, 'Greystar');
  assert.equal(en[1].email, ''); assert.match(en[1].system_note, /add one manually/); assert.match(en[2].system_note, /lookup failed/); ok('Apollo: verified / locked / error handled');
  const po = await run(1, 'Prep Outreach', en, R1);
  const out = await run(1, 'Parse Outreach', [llmResp({ subject: 'Austin PM role', body: 'Hi Jane,\n\nBook here: BOOKING_LINK\n\nSara' }), llmResp({}), llmResp('x')], { ...R1, 'Prep Outreach': po });
  assert.equal(out[0].status, 'Ready for review'); assert.equal(out[1].status, 'Needs email');
  assert.ok(out[0].outreach_body.includes('https://cal.com/acme/intro?name=Jane%20Doe&email=jane%40greystar.com&metadata%5Bcandidate_id%5D=')); assert.ok(!out[0].outreach_body.includes('BOOKING_LINK'));
  assert.ok(out[2].outreach_body.includes('cal.com/acme/intro')); ok('drafts: personalised booking link, fallback draft when AI fails');
  const sum = await run(1, 'Build Summary', scr, { ...R1, 'Parse Outreach': out, 'Normalize and Dedupe': cands });
  assert.match(sum[0].subject, /^3 candidates ready for review/); assert.match(sum[0].html, /2 skipped/); ok('summary: ' + sum[0].subject);
  const sum2 = await run(1, 'Build Summary', [{ ...scr[1] }], { ...R1, 'Normalize and Dedupe': cands });
  assert.match(sum2[0].subject, /^0 candidates/); ok('summary works when nobody was shortlisted');

  // ---------------- WF2
  console.log('WF2 Outbox');
  const TPL = [{ key: 'followup', subject: '', body: 'Hi {{first_name}}, bumping this. {{booking_link}}' },
    { key: 'selected', subject: 'Good news: {{role}}', body: 'Hi {{first_name}}, you are through.' },
    { key: 'rejected', subject: 'Update: {{role}}', body: 'Hi {{first_name}}, not this time.' },
    { key: 'footer', subject: '', body: 'Reply "unsubscribe" to opt out. {{agency}} · {{mailing_address}}' }];
  const R2 = { Settings: [SETTINGS], Config: [CONFIG], 'Load Templates': TPL };
  const row = (id, extra) => ({ candidate_id: id, name: 'Jane Doe', role: 'Property Manager', email: 'jane@x.com', outreach_subject: 'PM role', outreach_body: 'Hello', ...extra });
  const rows = [
    row('A1', { status: 'Approved' }),
    row('A2', { status: 'Approved', email: '' }),
    row('A3', { status: 'Approved' }),
    row('A4', { status: 'Approved' }),
    row('C1', { status: 'Contacted', thread_id: 't1', outreach_sent_at: daysAgo(4) }),
    row('C2', { status: 'Contacted', thread_id: 't2', outreach_sent_at: daysAgo(1) }),
    row('F1', { status: 'Followed up', thread_id: 't3', outreach_sent_at: daysAgo(12), followup_sent_at: daysAgo(8) }),
    row('S1', { status: 'Selected' }),
    row('S2', { status: 'Rejected', candidate_notified_at: daysAgo(0.5) }),
    row('N1', { status: 'Ready for review' }),
    {} ];
  const plan = await run(2, 'Plan Actions', rows, R2);
  const by = id => plan.filter(p => (p.candidate_id || p.update?.candidate_id) === id);
  assert.equal(by('S1')[0].kind, 'notify'); assert.equal(by('S1')[0].subject, 'Good news: Property Manager');
  assert.equal(by('S2').length, 0); assert.equal(by('N1').length, 0);
  assert.equal(by('A2')[0].update.status, 'Needs email');
  assert.equal(by('C1')[0].followup_due, true); assert.equal(by('C2')[0].followup_due, false); assert.equal(by('F1')[0].close_due, true);
  // daily limit 3 (1 sent in last 24h by S2) -> 2 slots: notify S1, follow-up C1, then outreach waits
  assert.equal(plan.filter(p => p.kind === 'outreach').length, 0); ok('priorities + daily cap (notify, follow-up, then outreach waits for next run)');
  const plan2 = await run(2, 'Plan Actions', rows, { ...R2, Settings: [{ ...SETTINGS, daily_send_limit: '30' }] });
  const o = plan2.filter(p => p.kind === 'outreach');
  assert.equal(o.length, 3); assert.ok(o[0].body.endsWith('Reply "unsubscribe" to opt out. Acme Talent · 1 Main St, Austin TX')); ok('outreach gets the opt-out footer');
  assert.ok(by('C1')[0].body.includes('metadata%5Bcandidate_id%5D=C1')); ok('follow-up has a personalised booking link');

  const be = await run(2, 'Build Email', [{ ...o[0], subject: 'Rôle à Austin ✓' }, { kind: 'followup', candidate_id: 'C1', to: 'jane@x.com', subject: 'Re: PM role', body: 'bump', thread_id: 't1', in_reply_to: '<abc@mail.gmail.com>' }], R2);
  const dec = Buffer.from(be[0].gmail.raw.replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString();
  assert.ok(dec.includes('To: jane@x.com')); assert.ok(dec.includes('List-Unsubscribe: <mailto:sara@acmetalent.com?subject=unsubscribe>'));
  const subj = dec.match(/Subject: =\?UTF-8\?B\?(.+)\?=/)[1]; assert.equal(Buffer.from(subj, 'base64').toString(), 'Rôle à Austin ✓');
  const bodyB64 = dec.split('\r\n\r\n')[1].replace(/\r\n/g, ''); assert.ok(Buffer.from(bodyB64, 'base64').toString().startsWith('Hello'));
  assert.ok(!be[0].gmail.threadId); assert.equal(be[1].gmail.threadId, 't1');
  assert.ok(Buffer.from(be[1].gmail.raw.replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString().includes('In-Reply-To: <abc@mail.gmail.com>')); ok('MIME: UTF-8 subject/body, unsubscribe header, threading headers');

  const as = await run(2, 'After Send', [{ id: 'm1', threadId: 'T9' }, { error: { message: 'Invalid To header' } }, { id: 'm3' }],
    { ...R2, 'Build Email': [{ kind: 'outreach', candidate_id: 'A1' }, { kind: 'outreach', candidate_id: 'A3' }, { kind: 'notify', candidate_id: 'S1' }] });
  assert.equal(as[0].status, 'Contacted'); assert.equal(as[0].thread_id, 'T9');
  assert.equal(as[1].status, undefined); assert.match(as[1].system_note, /Send failed.*Invalid To/);
  assert.ok(as[2].candidate_notified_at && !as[2].status); ok('after send: status/thread saved; failures noted, status unchanged');

  const H = (from, extra = {}) => ({ payload: { headers: [{ name: 'From', value: from }, { name: 'Message-ID', value: '<' + Math.random() + '@x>' }] }, internalDate: String(Date.now()), snippet: '', ...extra });
  const me = 'Sara Ali <sara@acmetalent.com>';
  const checks = [
    { route: 'check', candidate_id: 'C1', followup_due: true, close_due: false, to: 'jane@x.com', subject: 'Re: PM role', body: 'bump', thread_id: 't1' },
    { route: 'check', candidate_id: 'C2', followup_due: true, close_due: false, to: 'j@x.com', subject: 'Re: PM role', body: 'bump', thread_id: 't2' },
    { route: 'check', candidate_id: 'C3', followup_due: true, close_due: false, to: 'j@x.com', subject: 'Re: PM role', body: 'bump', thread_id: 't3' },
    { route: 'check', candidate_id: 'C4', followup_due: false, close_due: false, to: 'j@x.com', thread_id: 't4' },
    { route: 'check', candidate_id: 'F1', followup_due: false, close_due: true, to: 'j@x.com', thread_id: 't5' },
    { route: 'check', candidate_id: 'C5', followup_due: false, close_due: false, to: 'j@x.com', thread_id: 't6' },
    { route: 'check', candidate_id: 'C6', followup_due: false, close_due: false, thread_id: 't7' } ];
  const threads = [
    { messages: [H(me)] },
    { messages: [H(me), H('Jane <jane@x.com>', { snippet: 'Sounds great, happy to chat' })] },
    { messages: [H(me), H('Jane <j@x.com>', { snippet: 'Please remove me from your list' })] },
    { messages: [H(me)] },
    { messages: [H(me), H(me)] },
    { messages: [H(me), H('Mail Delivery Subsystem <mailer-daemon@googlemail.com>', { snippet: 'Address not found' })] },
    { error: { message: '404' } } ];
  const d = await run(2, 'Decide', threads, { ...R2, 'Plan Actions': checks });
  assert.equal(d[0].route, 'send'); assert.equal(d[0].kind, 'followup'); assert.ok(d[0].in_reply_to);
  assert.equal(d[1].update.status, 'Replied'); assert.equal(d[2].update.status, 'Opted out'); assert.equal(d[3].route, 'skip');
  assert.equal(d[4].update.status, 'No response'); assert.equal(d[5].update.status, 'Email bounced'); assert.equal(d[6].route, 'skip');
  ok('thread check: follow-up / replied / opted out / wait / no response / bounced / API error');

  // ---------------- WF3
  console.log('WF3 Interview Booked');
  const cands3 = [{ candidate_id: 'JOB-1-jane', name: 'Jane Doe', role: 'Property Manager', email: 'jane@x.com', score: 85, summary: 'Strong', linkedin_url: 'u', outreach_sent_at: daysAgo(3) },
    { candidate_id: 'JOB-0-jane', name: 'Jane Doe', role: 'Old role', email: 'Jane@X.com', outreach_sent_at: daysAgo(90) }];
  const cal = (ev, meta, email = 'jane@x.com') => ({ body: { triggerEvent: ev, payload: { startTime: '2026-11-25T15:00:00Z', attendees: [{ name: 'Jane Doe', email }], metadata: meta, location: 'integrations:google:meet' } } });
  const R3 = { Settings: [SETTINGS], Config: [CONFIG] };
  let m = await run(3, 'Match Booking', cands3, { ...R3, 'Cal.com Webhook': [cal('BOOKING_CREATED', { candidate_id: 'JOB-0-jane', videoCallUrl: 'https://meet.google.com/abc' })] });
  assert.equal(m[0].update.candidate_id, 'JOB-0-jane'); assert.equal(m[0].update.meet_link, 'https://meet.google.com/abc'); assert.equal(m[0].update.status, 'Interview scheduled'); assert.ok(m[0].update.interview_booked_at); ok('match by candidate_id, booking time recorded');
  m = await run(3, 'Match Booking', cands3, { ...R3, 'Cal.com Webhook': [cal('BOOKING_CREATED', { videoCallUrl: 'https://meet.google.com/abc' })] });
  assert.equal(m[0].update.candidate_id, 'JOB-1-jane'); ok('fallback: match by email (case-insensitive), most recent outreach');
  m = await run(3, 'Match Booking', cands3, { ...R3, 'Cal.com Webhook': [cal('BOOKING_CANCELLED', { candidate_id: 'JOB-1-jane' })] });
  assert.equal(m[0].update.status, 'Interview cancelled'); assert.equal(m[0].update.interview_time, ''); ok('cancellation clears time and link');
  m = await run(3, 'Match Booking', cands3, { ...R3, 'Cal.com Webhook': [cal('BOOKING_CREATED', {}, 'stranger@y.com')] });
  assert.equal(m[0].matched, false); assert.match(m[0].html, /did not match/); ok('unknown booker -> recruiter told, sheet untouched');
  m = await run(3, 'Match Booking', cands3, { ...R3, 'Cal.com Webhook': [cal('MEETING_ENDED', {})] });
  assert.equal(m.length, 0); ok('other Cal.com events ignored');

  // ---------------- WF4
  console.log('WF4 Weekly Report');
  const rows4 = [
    { candidate_id: '1', job_id: 'J1', role: 'PM', status: 'Not a fit', created_at: daysAgo(2) },
    { candidate_id: '2', job_id: 'J1', role: 'PM', status: 'Replied', outreach_sent_at: daysAgo(5), last_reply_at: daysAgo(2), name: 'A <b>', created_at: daysAgo(6) },
    { candidate_id: '3', job_id: 'J1', role: 'PM', status: 'Rejected', outreach_sent_at: daysAgo(5), last_reply_at: daysAgo(3), interview_time: new Date(Date.now() + 2 * 864e5).toISOString(), interview_booked_at: daysAgo(2), updated_at: daysAgo(0.1), name: 'B' },
    { candidate_id: '4', job_id: 'J1', role: 'PM', status: 'Ready for review' },
    { candidate_id: '5', job_id: 'J2', role: 'Recruiter', status: 'Contacted', outreach_sent_at: daysAgo(20) }, {} ];
  const c4 = await run(4, 'Count Pipeline', rows4, { Settings: [SETTINGS], Config: [CONFIG] });
  const j1 = c4[0].roles.find(r => r.job_id === 'J1');
  assert.deepEqual([j1.sourced, j1.shortlisted, j1.contacted, j1.replied, j1.interviews, j1.awaiting_review, j1.reply_rate], [4, 3, 2, 2, 1, 1, '100%']);
  assert.equal(c4[0].week.emails_sent, 2); assert.equal(c4[0].upcoming.length, 1); assert.equal(c4[0].week.interviews_booked, 1); ok('funnel counts; a booking still counts after the row is set to Rejected');
  const rep = await run(4, 'Build Report', [llmResp({ actions: ['Call A back', 'Review 1 draft', 'Broaden Recruiter search'] })], { Settings: [SETTINGS], Config: [CONFIG], 'Count Pipeline': c4 });
  assert.ok(rep[0].html.includes('A &lt;b&gt;')); assert.ok(rep[0].html.includes('Call A back')); ok('report HTML escaped, AI actions included');
  const rep2 = await run(4, 'Build Report', [{ error: { message: 'timeout' } }], { Settings: [SETTINGS], Config: [CONFIG], 'Count Pipeline': c4 });
  assert.ok(!rep2[0].html.includes('Suggested next actions') && rep2[0].html.includes('Pipeline by role')); ok('report still sends if the AI call fails');

  console.log('\nALL CODE-NODE TESTS PASSED');
})().catch(e => { console.error('\nFAILED:', e); process.exit(1); });
