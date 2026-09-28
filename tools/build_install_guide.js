// Build the ETIP Install & Test Guide (.docx).
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType,
  PageBreak, LevelFormat,
} = require("docx");

const NAVY = "0F1B2D", ACCENT = "0E9488", INK = "101828", MUTE = "667085", LINE = "D8DEE7";
const CW = 9360; // content width in DXA (US Letter, 1" margins)

const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 260, after: 120 }, children: [new TextRun({ text: t, bold: true, color: NAVY, size: 30 })] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 200, after: 90 }, children: [new TextRun({ text: t, bold: true, color: ACCENT, size: 24 })] });
const P = (t, opts = {}) => new Paragraph({ spacing: { after: opts.after ?? 90 }, children: Array.isArray(t) ? t : [new TextRun({ text: t, size: 21, color: INK })] });
const MUTED = (t) => new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: t, size: 19, color: MUTE, italics: true })] });
const CODE = (t) => new Paragraph({ spacing: { after: 40 }, shading: { type: ShadingType.CLEAR, fill: "F2F4F7" }, children: [new TextRun({ text: t, font: "Consolas", size: 19, color: "0B3B36" })] });
const bullets = (items) => items.map((it) => new Paragraph({ numbering: { reference: "bl", level: 0 }, spacing: { after: 50 }, children: [new TextRun({ text: it, size: 21, color: INK })] }));
const steps = (items) => items.map((it) => new Paragraph({ numbering: { reference: "nl", level: 0 }, spacing: { after: 50 }, children: [new TextRun({ text: it, size: 21, color: INK })] }));

function cell(text, w, opts = {}) {
  const runs = Array.isArray(text) ? text : [new TextRun({ text: String(text), size: opts.size ?? 19, bold: opts.bold ?? false, color: opts.color ?? INK })];
  return new TableCell({
    width: { size: w, type: WidthType.DXA },
    shading: opts.fill ? { type: ShadingType.CLEAR, fill: opts.fill } : undefined,
    margins: { top: 60, bottom: 60, left: 90, right: 90 },
    children: [new Paragraph({ children: runs })],
  });
}
function headerRow(cols, widths) {
  return new TableRow({ tableHeader: true, children: cols.map((c, i) => cell(c, widths[i], { bold: true, color: "FFFFFF", fill: NAVY, size: 19 })) });
}
function testTable(rows) {
  const widths = [2500, 4500, 2360];
  const trs = [headerRow(["Feature", "How to test", "Expected result"], widths)];
  rows.forEach((r, idx) => {
    trs.push(new TableRow({ children: [
      cell(r[0], widths[0], { bold: true, fill: idx % 2 ? "F7F9FB" : "FFFFFF", size: 19 }),
      cell(r[1], widths[1], { fill: idx % 2 ? "F7F9FB" : "FFFFFF", size: 19 }),
      cell(r[2], widths[2], { fill: idx % 2 ? "F7F9FB" : "FFFFFF", size: 19 }),
    ] }));
  });
  return new Table({ columnWidths: widths, width: { size: CW, type: WidthType.DXA }, rows: trs,
    borders: allBorders() });
}
function kvTable(rows) {
  const widths = [3000, 6360];
  const trs = rows.map((r, idx) => new TableRow({ children: [
    cell(r[0], widths[0], { bold: true, fill: idx % 2 ? "F7F9FB" : "FFFFFF" }),
    cell(r[1], widths[1], { fill: idx % 2 ? "F7F9FB" : "FFFFFF" }),
  ] }));
  return new Table({ columnWidths: widths, width: { size: CW, type: WidthType.DXA }, rows: trs, borders: allBorders() });
}
function allBorders() {
  const b = { style: BorderStyle.SINGLE, size: 4, color: LINE };
  return { top: b, bottom: b, left: b, right: b, insideHorizontal: b, insideVertical: b };
}
const rule = () => new Paragraph({ spacing: { before: 60, after: 120 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT } }, children: [] });

const children = [];

// ---- Cover ----
children.push(new Paragraph({ spacing: { before: 1400, after: 0 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "ETIP", bold: true, color: ACCENT, size: 72 })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 }, children: [new TextRun({ text: "Enterprise Transformation Intelligence Platform", bold: true, color: NAVY, size: 34 })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 300 }, children: [new TextRun({ text: "Plan. Execute. Govern. Transform.", italics: true, color: MUTE, size: 24 })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 }, children: [new TextRun({ text: "Installation & Feature Test Guide", bold: true, color: INK, size: 30 })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 }, children: [new TextRun({ text: "Build: 2026-09-27  ·  39 modules  ·  418 automated tests", color: MUTE, size: 20 })] }));
children.push(new Paragraph({ children: [new PageBreak()] }));

// ---- 1. What's in this build ----
children.push(H1("1. What's in this build"));
children.push(P("ETIP is a production-grade, multi-tenant Project / Program / Portfolio and Transformation management platform. This build is a modular monolith (FastAPI + SQLAlchemy 2 + PostgreSQL/SQLite, clean layering: API → Service → Repository → DB) with a single-page executive dashboard served by the same app."));
children.push(kvTable([
  ["Backend", "Python 3.11+, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, JWT auth, RBAC"],
  ["Frontend", "Self-contained HTML/JS dashboard (offline: self-hosted fonts + vendored Chart.js)"],
  ["Database", "PostgreSQL in production; SQLite out-of-the-box for the demo"],
  ["Modules", "39 API modules (authentication, org/user/roles, portfolio/program/project, tasks, sprints, milestones, resources, timesheets, finance, risk/issue/RAID/change/dependency, documents, meetings, notifications, reports, dashboards, intelligence, metrics, governance/workflow, vendor/procurement, integrations, API keys, SSO, Jira, AI delivery, AI copilot, admin)"],
  ["Quality", "418 automated tests; ruff + mypy clean; every table carries UUID PK, audit fields, soft-delete and a version column"],
]));
children.push(H2("Highlighted capabilities in this release"));
children.push(...bullets([
  "Intelligence layer — Earned Value (SPI/CPI/EAC/ETC/VAC), variance, forecasting, KPI attainment, risk/health heat maps, recommendations and a consolidated transformation briefing.",
  "Cost & budget on the main dashboard — Budget (BAC), Cost to date (AC), Forecast (EAC), To complete (ETC) and Variance (VAC), plus per-project cost columns.",
  "Metric history & sparklines — daily KPI/EVM snapshots rendered as real trend lines.",
  "SDLC stage-gate governance — projects run through Requirements → Design → Development → QA → UAT → Go-Live gates with recorded approvals and separation of duties.",
  "Financial milestones linked to deliverables — a payment released only once its deliverable is accepted at the gate, posting to the project ledger.",
  "Per-project KPIs & scorecards — a KPI register on each project with attainment, shown as a scorecard when a project is selected.",
  "AI Delivery — an AI code-generation and build/test/QA/deploy pipeline with a quality gate.",
]));
children.push(new Paragraph({ children: [new PageBreak()] }));

// ---- 2. Prerequisites ----
children.push(H1("2. Prerequisites"));
children.push(...bullets([
  "Python 3.11 or newer (python3 --version).",
  "pip and the venv module (bundled with Python).",
  "~500 MB free disk for the virtual environment and demo database.",
  "A modern browser (Chrome, Edge, Firefox or Safari) for the dashboard.",
  "Optional for production: PostgreSQL 14+, Redis, and Docker. The demo runs entirely on SQLite with no external services.",
]));
children.push(MUTED("No internet access is required at runtime — fonts and the charting library are bundled and served locally."));

// ---- 3. Quick install ----
children.push(H1("3. Quick install (one command)"));
children.push(P("The launcher creates the virtual environment, installs dependencies, applies migrations, seeds demo data on first run, and starts the server."));
children.push(H2("macOS / Linux"));
children.push(CODE("unzip etip.zip && cd etip"));
children.push(CODE("./run.sh"));
children.push(H2("Windows"));
children.push(CODE("Expand the zip, open the etip folder, then double-click run.bat"));
children.push(CODE("(or from a terminal:)   run.bat"));
children.push(P([new TextRun({ text: "When it finishes it prints the URLs and the demo credentials. Open ", size: 21 }), new TextRun({ text: "http://localhost:8000/", bold: true, size: 21, color: ACCENT }), new TextRun({ text: " for the dashboard and ", size: 21 }), new TextRun({ text: "http://localhost:8000/docs", bold: true, size: 21, color: ACCENT }), new TextRun({ text: " for the interactive API (Swagger).", size: 21 })]));
children.push(H2("Demo sign-in"));
children.push(kvTable([
  ["Organization", "demo-transformation-co"],
  ["Admin", "admin@demo.co  /  Str0ng-Passphrase!1"],
  ["Read-only viewer", "viewer@demo.co  /  Str0ng-Passphrase!1  (role-based view demo)"],
  ["PMO initiator", "pmo@demo.co  /  Str0ng-Passphrase!1  (starts governance/acceptance workflows)"],
]));

// ---- 4. Manual install ----
children.push(H1("4. Manual install (step by step)"));
children.push(P("Use this if you prefer to control each step, or to run against PostgreSQL."));
children.push(...steps([
  "Create and activate a virtual environment.",
]));
children.push(CODE("python3 -m venv .venv"));
children.push(CODE("source .venv/bin/activate        # Windows: .venv\\Scripts\\activate"));
children.push(...steps(["Install the project and its dependencies."]));
children.push(CODE("pip install --upgrade pip && pip install -e ."));
children.push(...steps(["Choose the database. SQLite needs nothing; for PostgreSQL set the URL."]));
children.push(CODE('export DATABASE_URL="sqlite:///./etip_demo.db"'));
children.push(CODE('# or:  export DATABASE_URL="postgresql+psycopg://etip:etip@localhost:5432/etip"'));
children.push(CODE('export JWT_SECRET_KEY="a-strong-32-byte-minimum-secret-key"'));
children.push(...steps([
  "Apply the database migrations.",
]));
children.push(CODE("alembic upgrade head"));
children.push(...steps(["Start the API + dashboard."]));
children.push(CODE("uvicorn app.main:app --port 8000"));
children.push(...steps(["In a second terminal (venv active), seed the demo dataset."]));
children.push(CODE("python scripts/seed_demo.py"));
children.push(MUTED("Re-running the seed is safe; it skips creation where the demo org already exists."));
children.push(new Paragraph({ children: [new PageBreak()] }));

// ---- 5. Dashboard tour ----
children.push(H1("5. Dashboard tour"));
children.push(P("After signing in, the left sidebar exposes the main areas. The scope selector at the top filters the whole Overview to All portfolios, a single portfolio, or a single project."));
children.push(kvTable([
  ["Overview", "Health, Cost & budget tiles, projects table (Budget/Cost/EAC/ETC + SPI trend), health mix, benefits, KPI attainment, recommendations. When a project is scoped it becomes a project scorecard."],
  ["Heat Map", "Risk/health heat map across the portfolio."],
  ["Forecast", "Schedule and cost forecast (completion dates, overrun projections)."],
  ["Procurement", "Vendors, contracts, purchase orders and spend."],
  ["Integrations", "Outbound webhooks and delivery outbox."],
  ["API Keys", "Programmatic access keys (create / revoke)."],
  ["AI Delivery", "AI code-generation build pipeline: generate → build → test → QA → deploy → perf, with a quality gate."],
  ["Governance", "SDLC stage-gate approvals per project, and financial milestones with deliverable acceptance & payment release."],
  ["Manage", "Create/edit/delete portfolios, programs, projects, risks, tasks, benefits, milestones and more."],
]));

// ---- 6. Feature test checklist ----
children.push(H1("6. Feature test checklist"));
children.push(MUTED("Sign in as admin unless a row says otherwise. Each row is an end-to-end check against the running app; API paths are under /api/v1 and can be exercised from /docs."));

children.push(H2("6.1 Authentication, tenancy & RBAC"));
children.push(testTable([
  ["Login", "Sign in with the admin credentials on the dashboard.", "Dashboard loads; header shows the user and role."],
  ["Role-based view", "Sign out, sign in as viewer@demo.co.", "Only permitted tabs/actions appear; management actions are hidden."],
  ["Data isolation", "In /docs, register a second organization and log in; list projects.", "You see only the new org's data — never the demo org's."],
  ["JWT + refresh", "POST /auth/login, then POST /auth/refresh with the refresh token.", "A new access token is issued."],
  ["Permissions", "As viewer, call a POST endpoint (e.g. create a project) in /docs.", "403 Forbidden (permission enforced server-side)."],
]));

children.push(H2("6.2 Structure: organizations, portfolios, programs, projects"));
children.push(testTable([
  ["Create project", "Manage → Projects → New; fill code/name/budget and save.", "Project appears in the list and on the Overview."],
  ["Portfolios / programs", "Manage → Portfolios / Programs; create one and assign a project.", "Hierarchy is reflected in the scope selector and rollups."],
  ["Edit / soft-delete", "Edit a project, then delete it.", "Change persists; deleted item disappears but audit/version retained."],
  ["Scope filter", "Top selector → pick a portfolio, then a single project.", "Overview refocuses; project scope shows the scorecard."],
]));

children.push(H2("6.3 Delivery: tasks, sprints, milestones, dependencies"));
children.push(testTable([
  ["Tasks", "Manage → Tasks; create tasks under a project.", "Tasks listed; status transitions validated."],
  ["Sprints", "POST /sprints; add tasks to a sprint.", "Sprint scope and status update."],
  ["Milestones", "Manage → Milestones; create with a target date.", "Milestone shows with overdue flag logic."],
  ["Dependencies", "POST /dependencies to link two items.", "Dependency recorded; cycle protection enforced."],
]));

children.push(H2("6.4 Financials & Earned Value"));
children.push(testTable([
  ["Cost & budget tiles", "Overview → Cost & budget strip.", "BAC, AC, EAC, ETC and VAC shown; VAC green under / red over budget."],
  ["Per-project cost", "Overview → projects table.", "Budget/Cost/EAC/ETC per project; EAC red where it exceeds budget."],
  ["Cost ledger", "POST /financial-entries (budget/forecast/actual); GET /projects/{id}/financial-summary.", "Summary rolls up approved budget, forecast, actuals and variances."],
  ["EVM engine", "GET /intelligence/performance/projects/{id}.", "SPI, CPI, EV, AC, EAC, ETC, VAC, TCPI computed correctly."],
]));

children.push(H2("6.5 Intelligence layer"));
children.push(testTable([
  ["Transformation briefing", "GET /intelligence/transformation.", "Health, SPI/CPI, success score, EAC/overrun and a plain-language narrative."],
  ["Variance", "GET /intelligence/variance/projects/{id}.", "Schedule/cost/budget/forecast variance with favourable/adverse flags."],
  ["Forecast", "GET /intelligence/forecast/transformation.", "Forecast completion, slippage and overrun projections."],
  ["Heat map", "Overview → Heat Map tab.", "Projects plotted by risk/health severity."],
  ["Recommendations", "Overview → Recommended actions.", "Prioritised actions with rationale (cost/schedule/risk)."],
]));

children.push(H2("6.6 Metric history & sparklines"));
children.push(testTable([
  ["Trend capture", "POST /intelligence/metrics/capture (or backfill-demo).", "A daily snapshot of success/SPI/CPI/realization + per-project SPI is stored."],
  ["Sparklines", "Overview → KPI tiles and the projects 'SPI trend' column.", "Real trend lines from captured history, not fabricated data."],
]));

children.push(H2("6.7 Per-project KPIs & scorecard"));
children.push(testTable([
  ["Scorecard", "Scope selector → choose a project.", "Project scorecard shows KPI cards with attainment and on/off-track status."],
  ["Add KPI", "Open the project workspace → Manage KPIs → Add KPI.", "KPI created with baseline/current/target and a live attainment meter."],
  ["Update / delete", "In the workspace, Update a KPI's current value, then delete one.", "Attainment recomputes; KPI removed."],
  ["Summary", "GET /projects/{id}/kpi-summary.", "On-target / off-target counts and average attainment."],
]));

children.push(H2("6.8 Governance — SDLC stage gates"));
children.push(testTable([
  ["Gate overview", "Governance tab.", "Each project shows its 6 SDLC gates with approved/pending/rejected/upcoming state."],
  ["Set up gates", "POST /workflows/setup-sdlc (idempotent).", "The canonical SDLC definition with 6 approval gates exists."],
  ["Approve a gate", "As admin, approve a pending gate (Approve gate).", "Gate turns approved with approver + date; project advances."],
  ["Separation of duties", "Try to approve a workflow you initiated.", "409 — the approver must differ from the initiator."],
]));

children.push(H2("6.9 Financial milestones & deliverable acceptance"));
children.push(testTable([
  ["Overview", "Governance tab → Financial milestones.", "Billing milestones with deliverable, amount, acceptance state and payment status."],
  ["Submit", "On a not-submitted milestone, click Submit.", "Deliverable enters the acceptance gate (status: awaiting acceptance)."],
  ["Accept", "As a different user, Accept the gate.", "Acceptance status → accepted; the milestone becomes releasable."],
  ["Release payment", "Click Release payment.", "An actual cost line posts to the project ledger; status → Paid."],
]));

children.push(H2("6.10 RAID, change & resources"));
children.push(testTable([
  ["Risks / Issues", "Manage → Risks; create a risk and an issue.", "Scored and reflected in the heat map and project risk score."],
  ["RAID register", "GET /raid endpoints.", "Risks, assumptions, issues and dependencies consolidated."],
  ["Change requests", "POST /change-requests then approve/reject.", "State machine enforced; decision recorded with approver."],
  ["Resources / timesheets", "Create a resource + allocation; log a timesheet.", "Allocation and utilisation tracked; timesheet approval flow."],
]));

children.push(H2("6.11 Collaboration, reporting & integrations"));
children.push(testTable([
  ["Documents", "Attach a document to a project/milestone.", "Versioned document stored (polymorphic owner)."],
  ["Meetings / notifications", "Create a meeting; trigger a notification.", "Records created and listable."],
  ["Board pack export", "Overview → Board pack (XLSX) / PDF.", "A formatted executive pack downloads."],
  ["AI Copilot", "Ask the copilot a question (chat bubble).", "A grounded answer referencing the platform's data."],
  ["Webhooks / API keys", "Integrations tab; API Keys tab.", "Create a webhook and an API key; dispatch and revoke work."],
  ["Jira connector", "PUT /integrations/jira/config, then POST /integrations/jira/test, /import, and GET /links, /sync-log.", "Test verifies credentials; import pulls issues into tasks (idempotent); two-way sync + a sync log. (Needs a reachable Jira instance for a live round-trip.)"],
  ["SSO (OIDC)", "PUT /auth/sso/config, POST /auth/sso/discover, then /auth/sso/login → /callback.", "Discovery auto-fills endpoints from the issuer; login provisions the user just-in-time with claim-based role mapping. (Needs a reachable IdP for a live round-trip.)"],
]));

children.push(new Paragraph({ children: [new PageBreak()] }));

// ---- 7. Automated tests ----
children.push(H1("7. Run the automated test suite"));
children.push(P("With the virtual environment active, from the project root:"));
children.push(CODE("pip install -e '.[dev]'          # test/lint tooling (first time)"));
children.push(CODE("pytest -q                        # 418 tests"));
children.push(CODE("ruff check app tests             # lint"));
children.push(CODE("mypy app                         # type-check"));
children.push(P("Focused runs while exploring a feature:"));
children.push(CODE("pytest tests/test_governance.py tests/test_financial_milestone.py -q"));
children.push(CODE("pytest tests/test_projectkpi.py tests/test_intelligence.py -q"));
children.push(MUTED("Tests run on an isolated in-memory SQLite database by default; set TEST_DATABASE_URL to run against PostgreSQL."));

// ---- 8. Troubleshooting ----
children.push(H1("8. Troubleshooting"));
children.push(kvTable([
  ["Login fails after start", "The first seed may not have completed. Stop, delete etip_demo.db, and re-run ./run.sh."],
  ["Port 8000 in use", "Start with a different port: PORT=8010 ./run.sh (or uvicorn --port 8010)."],
  ["Dashboard unstyled / blank", "Hard-refresh the browser; ensure you opened http://localhost:8000/ (not a file://)."],
  ["'No space left' during install", "Remove old build caches / virtualenvs; re-run install."],
  ["PostgreSQL connection error", "Verify DATABASE_URL and that the database exists; re-run alembic upgrade head."],
]));
children.push(rule());
children.push(MUTED("ETIP — Enterprise Transformation Intelligence Platform. This guide covers the 2026-09-27 build."));

const doc = new Document({
  creator: "ETIP",
  title: "ETIP Install & Test Guide",
  numbering: {
    config: [
      { reference: "bl", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 240 } } } }] },
      { reference: "nl", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 240 } } } }] },
    ],
  },
  styles: { default: { document: { run: { font: "Calibri", size: 21, color: INK } } } },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("/home/claude/etip/ETIP_Install_and_Test_Guide.docx", buf);
  console.log("wrote ETIP_Install_and_Test_Guide.docx");
});
