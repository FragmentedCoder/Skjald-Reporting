// Sample template, context and answers for the prototype. Everything here is fictional.

let counter = 0
export const uid = (prefix) => `${prefix}-${Date.now().toString(36)}-${(counter++).toString(36)}`

export const FIELD_TYPES = {
  text: {label: 'Short text', icon: 'Aa'},
  longtext: {label: 'Long text', icon: '¶'},
  number: {label: 'Number', icon: '#'},
  yesno: {label: 'Yes / no', icon: '✓'},
  dropdown: {label: 'Dropdown', icon: '▾'},
  datetime: {label: 'Date and time', icon: '◷'},
  ip: {label: 'IP address', icon: 'IP'},
  repeating: {label: 'Repeating group', icon: '≡'},
  secret: {label: 'Secret', icon: '•••'},
}

export const BLOCK_TYPES = {
  section: {label: 'Section', hint: 'Starts a part of the report'},
  heading: {label: 'Heading', hint: 'A sub-heading'},
  text: {label: 'Text', hint: 'Paragraph with variables'},
  answer: {label: 'Answer', hint: 'One answer with its label'},
  table: {label: 'Table', hint: 'Rows from a repeating group'},
  callout: {label: 'Callout', hint: 'Boxed note'},
  pagebreak: {label: 'Page break', hint: 'Forces a new page'},
  signatures: {label: 'Signatures', hint: 'Sign-off boxes'},
}

export function newQuestion(type) {
  const base = {id: uid('q'), type, key: `field_${counter}`, label: `New ${FIELD_TYPES[type].label.toLowerCase()} question`, required: false, help: ''}
  if (type === 'dropdown') base.options = ['Option 1', 'Option 2']
  if (type === 'repeating') base.columns = [{key: 'value', label: 'Value', type: 'text'}]
  return base
}

export function newBlock(kind) {
  const base = {id: uid('b'), kind, showWhen: null}
  switch (kind) {
    case 'section': return {...base, title: 'New section', newPage: true}
    case 'heading': return {...base, text: 'New heading'}
    case 'text': return {...base, text: 'Write here. Insert answers like {{answers.summary}}.'}
    case 'answer': return {...base, question: 'summary'}
    case 'table': return {...base, question: 'attackers'}
    case 'callout': return {...base, text: 'A note for the reader.'}
    case 'signatures': return {...base, signers: ['technician', 'reviewer', 'company']}
    default: return base
  }
}

export const initialQuestions = [
  {id: 'q1', key: 'summary', type: 'longtext', label: 'Summary of the incident', required: true, help: 'Two or three sentences the customer can read on the cover page.'},
  {id: 'q2', key: 'detected', type: 'datetime', label: 'Detected at', required: true, help: ''},
  {id: 'q3', key: 'cvss', type: 'number', label: 'Highest CVSS score', required: true, help: 'From 0.0 to 10.0. Sets the severity label.'},
  {id: 'q4', key: 'attack_found', type: 'yesno', label: 'Was the attacking address found?', required: true, help: ''},
  {id: 'q5', key: 'attackers', type: 'repeating', label: 'Attacking addresses', required: false, help: 'One row per address.',
    columns: [{key: 'ip', label: 'Address', type: 'ip'}, {key: 'attempts', label: 'Attempts', type: 'number'}, {key: 'status', label: 'Status', type: 'text'}],
    showWhen: {field: 'attack_found', op: 'is', value: true}},
  {id: 'q6', key: 'actions', type: 'longtext', label: 'Actions taken', required: true, help: ''},
  {id: 'q7', key: 'credentials', type: 'secret', label: 'Credentials found during the investigation', required: false, help: 'Always masked in the PDF.'},
]

export const initialBlocks = [
  {id: 'b1', kind: 'section', title: 'Summary', newPage: false, showWhen: null},
  {id: 'b2', kind: 'answer', question: 'summary', showWhen: null},
  {id: 'b3', kind: 'callout', text: 'Severity: {{severity_label}} (CVSS {{answers.cvss}})', showWhen: null},
  {id: 'b4', kind: 'section', title: 'Attacking addresses', newPage: true, showWhen: {field: 'attack_found', op: 'is', value: true}},
  {id: 'b5', kind: 'text', text: 'Traffic from these addresses was blocked at the firewall.', showWhen: null},
  {id: 'b6', kind: 'table', question: 'attackers', showWhen: null},
  {id: 'b7', kind: 'section', title: 'Actions taken', newPage: true, showWhen: null},
  {id: 'b8', kind: 'answer', question: 'actions', showWhen: null},
  {id: 'b9', kind: 'heading', text: 'Credentials found', showWhen: {field: 'cvss', op: 'atLeast', value: 7}},
  {id: 'b10', kind: 'text', text: 'The following credential must be rotated: {{answers.credentials}}', showWhen: {field: 'cvss', op: 'atLeast', value: 7}},
  {id: 'b11', kind: 'section', title: 'Sign-off', newPage: true, showWhen: null},
  {id: 'b12', kind: 'signatures', signers: ['technician', 'reviewer', 'company'], showWhen: null},
]

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
  actions: 'Firewall rules were added for both addresses, rate limiting was tightened on the portal, and MFA enforcement was brought forward for all portal users.',
  credentials: 'Hunter2-portal-admin',
}

export const context = {
  company: {name: 'Nordlys IT ApS', cvr: '00000000'},
  customer: {name: 'Fjordvik Logistik A/S', cvr: '00000000', address: 'Havnevej 1, 9999 Fjordvik'},
  project: {name: 'Portal incident October 2026', number: 'P-2026-031'},
  report: {number: 'INC-2026-0142', classification: 'TLP:AMBER', technician: 'Freja Holm', reviewer: 'Ivar Lund'},
}

export const computed = [
  {name: 'severity_label', label: 'Severity label',
    expr: 'answers.cvss >= 9.0 ? "Critical" : answers.cvss >= 7.0 ? "High" : answers.cvss >= 4.0 ? "Medium" : "Low"'},
  {name: 'blocked_count', label: 'Blocked addresses',
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

export const lookupTables = {
  severity_da: {critical: 'Kritisk', high: 'Høj', medium: 'Middel', low: 'Lav'},
}
