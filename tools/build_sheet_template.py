import json, os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.comments import Comment

cols = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'columns.json')))
F = Font(name='Arial', size=10); B = Font(name='Arial', size=10, bold=True, color='FFFFFF')
HF = PatternFill('solid', fgColor='7A3B12'); EDIT = PatternFill('solid', fgColor='FFF2CC')
wrap = Alignment(wrap_text=True, vertical='top')
wb = Workbook()

def header(ws, names, widths):
    ws.append(names)
    for i, c in enumerate(ws[1]):
        c.font = B; c.fill = HF; c.alignment = Alignment(vertical='center')
        ws.column_dimensions[c.column_letter].width = widths[i] if isinstance(widths, list) else widths
    ws.freeze_panes = 'A2'

def body_font(ws):
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.font = F; c.alignment = wrap

# Start here
ws = wb.active; ws.title = 'Start here'
ws.column_dimensions['A'].width = 110
lines = [
 ('Recruiting Agent - control sheet', True),
 ('', False),
 ('1. Settings tab: fill in every yellow cell in the "value" column. This is the only per-client setup inside the sheet.', False),
 ('2. Templates tab: edit the follow-up, selected, rejected and footer emails if you like. Placeholders: {{first_name}} {{name}} {{role}} {{agency}} {{recruiter}} {{recruiter_email}} {{booking_link}} {{mailing_address}}', False),
 ('3. Jobs and Candidates are filled by the agent. Do not rename tabs or column headers.', False),
 ('', False),
 ('Your daily routine (Candidates tab):', True),
 ('  - Filter status = "Ready for review". Read the outreach_subject and outreach_body, edit them if you want, then set status to "Approved".', False),
 ('  - Filter status = "Needs email". Paste an email into the email column if you can find one, then set status to "Approved".', False),
 ('  - Filter status = "Replied". Answer them from Gmail (the replies land in the sending inbox).', False),
 ('  - After an interview set status to "Selected" or "Rejected". The candidate gets the matching template email once.', False),
 ('  - Use recruiter_notes for your own notes. The agent never writes there. It writes problems to system_note.', False),
 ('', False),
 ('Statuses the agent sets: Sourced, Shortlisted, Not a fit, Ready for review, Needs email, Contacted, Followed up, Replied, Opted out, Email bounced, No response, Interview scheduled, Interview cancelled.', False),
 ('Statuses you set: Approved, Selected, Rejected, On hold. Never set "Opted out" back to anything else.', False),
 ('', False),
 ('Example of a finished Candidates row (for reference only, do not paste it in):', True),
 ('  candidate_id JOB-20261120-K3P9-jane-doe-123 | role Property Manager | name Jane Doe | email jane@greystar.com | score 85 | status Ready for review | outreach_subject "Austin property manager role" | outreach_body "Hi Jane, ..."', False),
]
for t, bold in lines:
    ws.append([t]); c = ws.cell(ws.max_row, 1); c.font = Font(name='Arial', size=12 if bold and ws.max_row == 1 else 10, bold=bold); c.alignment = Alignment(wrap_text=True)

# Settings
ws = wb.create_sheet('Settings'); header(ws, ['key', 'value', 'description'], [28, 45, 80])
settings = [
 ('agency_name', 'Your Agency', 'Shown in emails and reports'),
 ('recruiter_name', 'Your Name', 'Signs the outreach emails'),
 ('recruiter_email', 'you@youragency.com', 'Gets summaries, alerts and the weekly report. Use the same address as the Gmail account the agent sends from'),
 ('mailing_address', '123 Main St, City, ST 00000', 'Postal address in the email footer (required for US commercial email under CAN-SPAM)'),
 ('booking_link', 'https://cal.com/your-agency/intro-call', 'Your Cal.com event link. The agent adds the candidate name, email and ID to it'),
 ('sheet_url', '', 'Optional: link to this sheet, used in emails. Leave blank to build it from the sheet ID'),
 ('score_threshold', '70', 'Candidates at or above this AI score (0-100) are shortlisted'),
 ('max_candidates_per_role', '25', 'How many new profiles to screen per role submission'),
 ('daily_send_limit', '30', 'Max emails per rolling 24 hours. Keep low (20-40) for a new Gmail account'),
 ('followup_after_days', '3', 'Days after outreach before the single follow-up'),
 ('close_after_days', '7', 'Days after the follow-up before status becomes "No response"'),
 ('recontact_cooldown_days', '60', 'People emailed within this many days are not sourced again'),
 ('search_country', 'us', 'Two-letter country code for search results'),
 ('search_use_site', 'no', 'yes = precise LinkedIn-only search (needs a paid Serper plan). no = works on the free plan'),
 ('llm_url', 'https://api.openai.com/v1/chat/completions', 'AI endpoint (any OpenAI-compatible API). Free testing with Groq: https://api.groq.com/openai/v1/chat/completions'),
 ('llm_model', 'gpt-4.1-mini', 'AI model name. OpenAI: gpt-4.1-mini. Free testing with Groq: llama-3.3-70b-versatile'),
]
for r in settings: ws.append(list(r))
body_font(ws)
for r in range(2, ws.max_row + 1): ws.cell(r, 2).fill = EDIT

# Templates
ws = wb.create_sheet('Templates'); header(ws, ['key', 'subject', 'body', 'when it is used'], [12, 34, 90, 40])
tpls = [
 ('followup', '(uses "Re:" + the outreach subject)', "Hi {{first_name}},\n\nJust bringing this back to the top of your inbox in case it got buried. If the {{role}} role sounds interesting, you can pick a 20-minute slot here: {{booking_link}}\n\nIf the timing isn't right, no problem at all.\n\n{{recruiter}}\n{{agency}}", 'Once, in the same thread, if no reply after followup_after_days. Delete this row to turn follow-ups off'),
 ('selected', 'Next steps for the {{role}} role', "Hi {{first_name}},\n\nThanks again for your time. Good news: we'd like to move you forward for the {{role}} role. I'll be in touch shortly with the next steps.\n\n{{recruiter}}\n{{agency}}", 'When you set status to Selected'),
 ('rejected', 'Update on the {{role}} role', "Hi {{first_name}},\n\nThank you for speaking with us about the {{role}} role. We've decided to move forward with other candidates this time, but we'd be glad to keep you in mind for future roles.\n\nAll the best,\n{{recruiter}}\n{{agency}}", 'When you set status to Rejected. Delete this row to stop rejection emails'),
 ('footer', '', "You're receiving this because your public profile matches roles we recruit for. Reply \"unsubscribe\" and we won't contact you again.\n{{agency}} | {{mailing_address}}", 'Added under every outreach and follow-up email'),
]
for r in tpls: ws.append(list(r))
body_font(ws)
for r in range(2, ws.max_row + 1):
    for c in (2, 3): ws.cell(r, c).fill = EDIT
    ws.row_dimensions[r].height = 110

# Jobs
ws = wb.create_sheet('Jobs'); header(ws, cols['JOB_COLS'], 18)

# Candidates
ws = wb.create_sheet('Candidates')
widths = {'outreach_body': 60, 'summary': 40, 'snippet': 40, 'headline': 30, 'linkedin_url': 34, 'candidate_id': 30, 'recruiter_notes': 30, 'system_note': 30, 'outreach_subject': 30, 'email': 26}
header(ws, cols['CAND_COLS'], [widths.get(c, 14) for c in cols['CAND_COLS']])
ws.freeze_panes = 'E2'
st_col = cols['CAND_COLS'].index('status') + 1
for name in ('status', 'email', 'outreach_subject', 'outreach_body', 'recruiter_notes'):
    ws.cell(1, cols['CAND_COLS'].index(name) + 1).fill = PatternFill('solid', fgColor='B8860B')
ws.cell(1, st_col).comment = Comment('Set Approved to send, Selected/Rejected after interviews. See the Start here tab.', 'Recruiting Agent')

# Lists + dropdown
lst = wb.create_sheet('Lists')
statuses = ['Sourced', 'Shortlisted', 'Not a fit', 'Ready for review', 'Needs email', 'Approved', 'Contacted', 'Followed up', 'Replied',
            'Opted out', 'Email bounced', 'No response', 'Interview scheduled', 'Interview cancelled', 'Selected', 'Rejected', 'On hold']
lst.append(['status']); [lst.append([s]) for s in statuses]
lst.sheet_state = 'hidden'
from openpyxl.utils import get_column_letter
L = get_column_letter(st_col)
dv = DataValidation(type='list', formula1=f"=Lists!$A$2:$A${len(statuses)+1}", allow_blank=True, showErrorMessage=True,
                    errorTitle='Unknown status', error='Pick a status from the list')
ws.add_data_validation(dv); dv.add(f'{L}2:{L}5000')
wb.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'templates', 'Recruiting-Agent-Sheet-Template.xlsx'))
print('saved; status column', L)
