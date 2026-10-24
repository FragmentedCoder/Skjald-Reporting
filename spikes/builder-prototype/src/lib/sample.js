// Sample template, context, answers and library for the prototype. Everything here is fictional.

let counter = 0
export const uid = (prefix) => `${prefix}-${Date.now().toString(36)}-${(counter++).toString(36)}`

// Field types for the Questions tab. "group" is not a field: it starts a new step in the technician's form.
export const FIELD_TYPES = {
  group: {label: 'Form step', icon: '▸', hint: 'Starts a new step'},
  text: {label: 'Short text', icon: 'Aa', hint: 'One line'},
  longtext: {label: 'Long text', icon: '¶', hint: 'Paragraphs'},
  number: {label: 'Number', icon: '#', hint: 'Scores, counts'},
  yesno: {label: 'Yes / no', icon: '✓', hint: 'A single choice'},
  dropdown: {label: 'Dropdown', icon: '▾', hint: 'Pick from a list'},
  datetime: {label: 'Date and time', icon: '◷', hint: 'When it happened'},
  ip: {label: 'IP address', icon: 'IP', hint: 'IPv4 or IPv6'},
  photo: {label: 'Photo', icon: '▣', hint: 'Screenshot or picture'},
  repeating: {label: 'Repeating group', icon: '≡', hint: 'A table of rows'},
  secret: {label: 'Secret', icon: '•••', hint: 'Password or key'},
}

// Block types for the Layout tab: everything here is printed in the PDF.
export const BLOCK_TYPES = {
  section: {label: 'Section', hint: 'A numbered part of the report', glyph: '§'},
  heading: {label: 'Heading', hint: 'A sub-heading', glyph: 'H'},
  text: {label: 'Text', hint: 'Paragraph with variables', glyph: 'T'},
  answer: {label: 'Answer', hint: 'One answer with its label', glyph: 'A'},
  table: {label: 'Table', hint: 'Rows from a repeating group', glyph: '⊞'},
  image: {label: 'Image', hint: 'A picture or diagram', glyph: '▣'},
  callout: {label: 'Callout', hint: 'Coloured note', glyph: '▭'},
  sources: {label: 'Sources', hint: 'References and links', glyph: '¹'},
  pagebreak: {label: 'Page break', hint: 'Forces a new page', glyph: '⤓'},
  signatures: {label: 'Signatures', hint: 'Sign-off boxes', glyph: '✍'},
}

export const SIGNER_ROLES = {technician: 'Technician', reviewer: 'Reviewer', company: 'Company seal'}

export function newQuestion(type) {
  if (type === 'group') return {id: uid('g'), type, key: `step_${counter}`, label: 'New step', help: ''}
  const base = {id: uid('q'), type, key: `field_${counter}`, label: `New ${FIELD_TYPES[type].label.toLowerCase()} question`, required: false, help: ''}
  if (type === 'dropdown') base.options = ['Option 1', 'Option 2']
  if (type === 'repeating') base.columns = [{key: 'value', label: 'Value', type: 'text'}]
  if (type === 'secret') base.secret = {pdf: 'partial', ends: 2}
  return base
}

export function newBlock(kind) {
  const base = {id: uid('b'), kind, showWhen: null}
  switch (kind) {
    case 'section': return {...base, title: 'New section', newPage: true, intro: '', numbered: true}
    case 'heading': return {...base, text: 'New heading'}
    case 'text': return {...base, text: 'Write here. Insert answers like {{answers.summary}}.'}
    case 'answer': return {...base, question: 'summary', showLabel: true}
    case 'table': return {...base, question: 'attackers', caption: '', columns: null, emptyText: 'No rows.'}
    case 'image': return {...base, source: 'template', asset: 'network', question: '', caption: '', width: 'full'}
    case 'callout': return {...base, tone: 'info', color: '#DCE6EE', title: '', text: 'A note for the reader.'}
    case 'sources': return {...base, intro: '', items: [], question: ''}
    case 'signatures': return {...base, signers: [{role: 'technician', label: 'Technician', style: 'handwritten'}], layout: 'row', showDate: true}
    default: return base
  }
}

export const initialQuestions = [
  {id: 'g1', type: 'group', key: 'step_incident', label: 'The incident', help: 'What happened and when. The summary goes on the first page of the report.'},
  {id: 'q1', key: 'summary', type: 'longtext', label: 'Summary of the incident', required: true, help: 'Two or three sentences the customer can read on the first page.'},
  {id: 'q2', key: 'detected', type: 'datetime', label: 'Detected at', required: true, help: ''},
  {id: 'q3', key: 'cvss', type: 'number', label: 'Highest CVSS score', required: true, help: 'From 0.0 to 10.0. Sets the severity label.'},
  {id: 'g2', type: 'group', key: 'step_attack', label: 'The attack', help: 'Where the attack came from. Add one row per address.'},
  {id: 'q4', key: 'attack_found', type: 'yesno', label: 'Was the attacking address found?', required: true, help: ''},
  {id: 'q5', key: 'attackers', type: 'repeating', label: 'Attacking addresses', required: false, help: 'One row per address.',
    columns: [{key: 'ip', label: 'Address', type: 'ip'}, {key: 'attempts', label: 'Attempts', type: 'number'}, {key: 'status', label: 'Status', type: 'text'}],
    showWhen: {field: 'attack_found', op: 'is', value: true}},
  {id: 'q8', key: 'evidence', type: 'photo', label: 'Screenshot of the evidence', required: false, help: 'For example the firewall graph. Location data is removed from photos.'},
  {id: 'g3', type: 'group', key: 'step_actions', label: 'Actions and handover', help: 'What you did, and anything the customer must receive.'},
  {id: 'q6', key: 'actions', type: 'longtext', label: 'Actions taken', required: true, help: ''},
  {id: 'q7', key: 'credentials', type: 'secret', label: 'New portal admin password', required: false,
    help: 'Printed partly in the PDF. Give the customer the full password by phone.', secret: {pdf: 'partial', ends: 2}},
  {id: 'q9', key: 'sources', type: 'repeating', label: 'Sources you used', required: false, help: 'Advisories, vendor articles or logs the customer can look up.',
    columns: [{key: 'title', label: 'Title', type: 'text'}, {key: 'link', label: 'Link or reference', type: 'text'}]},
]

export const initialBlocks = [
  {id: 'b1', kind: 'section', title: 'Summary', newPage: false, intro: '', numbered: true, showWhen: null},
  {id: 'b2', kind: 'answer', question: 'summary', showLabel: false, showWhen: null},
  {id: 'b3', kind: 'callout', tone: 'warning', color: '#FBEFD9', title: '{{severity_label}} severity', text: 'Highest CVSS score {{answers.cvss}}. Contact {{vars.support_phone}} if the attack starts again.', showWhen: null},
  {id: 'b4', kind: 'section', title: 'Attacking addresses', newPage: true, numbered: true, intro: 'Addresses that attacked the customer portal, and what was done about each one.',
    showWhen: {field: 'attack_found', op: 'is', value: true}},
  {id: 'b5', kind: 'text', text: 'Traffic from these addresses was blocked at the firewall.', showWhen: null},
  {id: 'b6', kind: 'table', question: 'attackers', caption: 'Attacking addresses and sign-in attempts', columns: null, emptyText: 'No addresses were recorded.', showWhen: null},
  {id: 'b13', kind: 'image', source: 'question', asset: 'network', question: 'evidence', caption: 'Sign-in attempts per 10 minutes, from the firewall', width: 'full',
    showWhen: {field: 'evidence', op: 'isFilled', value: ''}},
  {id: 'b7', kind: 'section', title: 'Actions taken', newPage: true, numbered: true, intro: '', showWhen: null},
  {id: 'b8', kind: 'answer', question: 'actions', showLabel: false, showWhen: null},
  {id: 'b14', kind: 'image', source: 'template', asset: 'network', question: '', caption: 'Where the firewall rules were added', width: 'full', showWhen: null},
  {id: 'b9', kind: 'heading', text: 'New credentials', showWhen: {field: 'credentials', op: 'isFilled', value: ''}},
  {id: 'b10', kind: 'text', text: 'The portal admin password was changed to {{answers.credentials}}. {{text.password_handover}}',
    showWhen: {field: 'credentials', op: 'isFilled', value: ''}},
  {id: 'b15', kind: 'section', title: 'Sources', newPage: false, numbered: true, intro: '', showWhen: null},
  {id: 'b16', kind: 'sources', intro: 'Background for the findings in this report.', question: 'sources',
    items: [{title: 'NIS2 Directive (EU) 2022/2555, article 23: reporting obligations', link: 'https://eur-lex.europa.eu/eli/dir/2022/2555/oj'}], showWhen: null},
  {id: 'b11', kind: 'section', title: 'Sign-off', newPage: true, numbered: true, intro: '', showWhen: null},
  {id: 'b17', kind: 'text', text: '{{text.confidentiality}}', showWhen: null},
  {id: 'b12', kind: 'signatures', layout: 'row', showDate: true, showWhen: null, signers: [
    {role: 'technician', label: 'Technician', style: 'handwritten'},
    {role: 'reviewer', label: 'Reviewer', style: 'handwritten'},
    {role: 'company', label: 'Company seal', style: 'stamp'},
  ]},
]

// A small bar chart of sign-in attempts, standing in for a screenshot the technician uploaded.
function evidenceSvg() {
  const bars = [14, 22, 380, 512, 498, 301, 115, 0]
  const labels = ['03:00', '03:10', '03:20', '03:30', '03:40', '03:50', '04:00', '04:10']
  const w = 640, h = 260, left = 48, bottom = 222, top = 24, bw = 56, gap = 18
  const max = 600
  const y = (v) => bottom - ((bottom - top) * v) / max
  const grid = [0, 200, 400, 600].map((v) => `<line x1="${left}" x2="${w - 12}" y1="${y(v)}" y2="${y(v)}" stroke="#E5E5E5"/><text x="${left - 8}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="#5B6675">${v}</text>`).join('')
  const rects = bars.map((v, i) => {
    const x = left + 12 + i * (bw + gap)
    return `<rect x="${x}" y="${y(v)}" width="${bw}" height="${bottom - y(v)}" rx="3" fill="#2B5D8A"/><text x="${x + bw / 2}" y="${bottom + 16}" text-anchor="middle" font-size="11" fill="#5B6675">${labels[i]}</text>`
  }).join('')
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" font-family="IBM Plex Sans, sans-serif"><rect width="${w}" height="${h}" fill="#FFFFFF"/>${grid}${rects}<text x="${left}" y="14" font-size="12" font-weight="600" fill="#0F1B2D">Failed sign-ins, portal.fjordvik.example</text></svg>`
  return `data:image/svg+xml;base64,${btoa(svg)}`
}

// A network diagram uploaded with the template, used by an image block.
function networkSvg() {
  const box = (x, y, w, label, sub, fill = '#FFFFFF') =>
    `<rect x="${x}" y="${y}" width="${w}" height="52" rx="8" fill="${fill}" stroke="#0F1B2D" stroke-width="1.5"/><text x="${x + w / 2}" y="${y + 23}" text-anchor="middle" font-size="13" font-weight="600" fill="#0F1B2D">${label}</text><text x="${x + w / 2}" y="${y + 40}" text-anchor="middle" font-size="11" fill="#5B6675">${sub}</text>`
  const arrow = (x1, x2, y) => `<line x1="${x1}" y1="${y}" x2="${x2 - 8}" y2="${y}" stroke="#0F1B2D" stroke-width="1.5"/><path d="M${x2 - 8} ${y - 5} L${x2} ${y} L${x2 - 8} ${y + 5} Z" fill="#0F1B2D"/>`
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 150" font-family="IBM Plex Sans, sans-serif"><rect width="640" height="150" fill="#FFFFFF"/>` +
    box(10, 48, 130, 'Internet', 'attackers') + arrow(140, 230, 74) +
    box(230, 48, 170, 'Firewall', 'new block rules', '#FBEFD9') + arrow(400, 490, 74) +
    box(490, 48, 140, 'Customer portal', 'rate limited') +
    `<text x="315" y="128" text-anchor="middle" font-size="11" fill="#8A5A12">Rules added 21 Oct 2026, 04:05</text></svg>`
  return `data:image/svg+xml;base64,${btoa(svg)}`
}

// Images uploaded with the template (in Skjald: stored with the template version).
export const templateAssets = {network: {label: 'Network diagram (network.svg)', src: networkSvg()}}

export const initialAnswers = {
  summary: 'Between 03:14 and 04:02, 1 842 sign-in attempts against the customer portal used credentials from a known breach list. Twelve accounts were locked; no account was taken over.',
  detected: '2026-10-21T03:14',
  cvss: 7.5,
  attack_found: true,
  attackers: [
    {ip: '198.51.100.23', attempts: 1204, status: 'Blocked'},
    {ip: '203.0.113.77', attempts: 611, status: 'Blocked'},
    {ip: '2001:db8::5', attempts: 27, status: 'Monitoring'},
  ],
  evidence: evidenceSvg(),
  actions: 'Firewall rules were added for both addresses, rate limiting was tightened on the portal, and MFA enforcement was brought forward for all portal users.',
  credentials: 'Hunter2-portal-admin',
  sources: [{title: 'Vendor advisory: portal rate limiting', link: 'VA-2026-117'}],
}

export const context = {
  company: {name: 'Nordlys IT ApS', cvr: '00000000'},
  customer: {name: 'Fjordvik Logistik A/S', cvr: '00000000', address: 'Havnevej 1, 9999 Fjordvik', contact: 'Jens Hansen'},
  project: {name: 'Portal incident October 2026', number: 'P-2026-031'},
  report: {number: 'INC-2026-0142', classification: 'TLP:AMBER', technician: 'Freja Holm', reviewer: 'Ivar Lund'},
}

// Where each context value comes from, and what it is, for the Data tab.
export const contextInfo = {
  company: {source: 'Company settings', about: 'Your company, set once by an administrator.'},
  customer: {source: 'Customer record', about: 'The customer the project belongs to.'},
  project: {source: 'Project', about: 'The project the report was started in.'},
  report: {source: 'Report', about: 'Set when the report is started; technician and reviewer come from the assignment.'},
}

export const computed = [
  {name: 'severity_label', label: 'Severity label', about: 'Turns the CVSS score into a word for headings and callouts.',
    expr: 'answers.cvss >= 9.0 ? "Critical" : answers.cvss >= 7.0 ? "High" : answers.cvss >= 4.0 ? "Medium" : "Low"'},
  {name: 'blocked_count', label: 'Blocked addresses', about: 'Counts the rows in "Attacking addresses" whose status is Blocked.',
    expr: 'answers.attackers.filter(a, a.status == "Blocked").size()'},
]

// The cover's key facts are template text too, so they follow renamed variables.
export const coverFacts = [
  {label: 'Report', text: '{{report.number}}', mono: true},
  {label: 'Project', text: '{{project.number}}', mono: true},
  {label: 'Detected', text: '{{answers.detected}}'},
  {label: 'Severity', text: '{{severity_label}} · CVSS {{answers.cvss}}'},
  {label: 'Technician', text: '{{report.technician}}'},
  {label: 'Reviewer', text: '{{report.reviewer}}'},
]

// The shared library: technicians and designers can add and edit; every change is logged.
const h = (at, by, change) => ({at, by, change})
export const initialLibrary = {
  vars: [
    {key: 'support_phone', value: '+45 12 34 56 78', about: 'Service desk phone number for customers.', locked: false,
      history: [h('2026-09-02T09:14', 'Ivar Lund', 'Added')]},
    {key: 'support_email', value: 'servicedesk@nordlys.example', about: 'Service desk email address.', locked: false,
      history: [h('2026-09-02T09:15', 'Ivar Lund', 'Added')]},
    {key: 'retention_years', value: '5', about: 'How long signed reports are kept. Locked: it must match the retention policy.', locked: true,
      history: [h('2026-09-02T09:20', 'Ivar Lund', 'Added'), h('2026-09-02T09:21', 'Ivar Lund', 'Locked')]},
  ],
  text: [
    {key: 'password_handover', about: 'Explains how a new password reached the customer.', locked: false,
      value: 'The full password was given to {{customer.contact}} by phone, and must be changed at the first sign-in.',
      history: [h('2026-09-10T13:02', 'Freja Holm', 'Added'), h('2026-10-01T08:40', 'Ivar Lund', 'Changed the text')]},
    {key: 'confidentiality', about: 'The classification notice printed above the signatures.', locked: true,
      value: 'This report is classified {{report.classification}}. Share it only with people at {{customer.name}} who need it. Questions: {{vars.support_email}}.',
      history: [h('2026-09-02T09:30', 'Ivar Lund', 'Added'), h('2026-09-02T09:31', 'Ivar Lund', 'Locked')]},
    {key: 'nis2_deadlines', about: 'The NIS2 reporting deadlines, for incident reports.', locked: false,
      value: 'Under NIS2, an early warning is due within 24 hours, an incident notification within 72 hours and a final report within one month.',
      history: [h('2026-09-12T11:05', 'Freja Holm', 'Added')]},
  ],
  tables: [
    {key: 'severity_da', about: 'Severity labels in Danish, for Danish templates.', locked: false,
      rows: [{key: 'critical', value: 'Kritisk'}, {key: 'high', value: 'Høj'}, {key: 'medium', value: 'Middel'}, {key: 'low', value: 'Lav'}],
      history: [h('2026-09-03T10:00', 'Ivar Lund', 'Added')]},
    {key: 'media_destruction', about: 'How each kind of storage device is destroyed, for destruction certificates.', locked: false,
      rows: [{key: 'hdd', value: 'Degaussed and shredded (NIST SP 800-88, Destroy)'}, {key: 'ssd', value: 'Shredded to 2 mm (NIST SP 800-88, Destroy)'},
        {key: 'usb', value: 'Shredded (NIST SP 800-88, Destroy)'}],
      history: [h('2026-09-15T14:22', 'Freja Holm', 'Added'), h('2026-09-16T08:01', 'Freja Holm', 'Added the row usb')]},
  ],
}

export const lookupTablesFrom = (library) => Object.fromEntries(library.tables.map((t) => [t.key, Object.fromEntries(t.rows.map((r) => [r.key, r.value]))]))

// People in the prototype, one per role.
export const USERS = {
  admin: {name: 'Ivar Lund', role: 'Administrator'},
  designer: {name: 'Sofie Dahl', role: 'Report designer'},
  technician: {name: 'Freja Holm', role: 'Technician'},
}
