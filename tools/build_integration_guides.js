// ETIP Integration Guides (.docx) — SSO, Webhooks, API keys, CI/CD. Beginner style.
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType, PageBreak, LevelFormat,
} = require("docx");

const NAVY = "0F1B2D", ACCENT = "0E9488", INK = "101828", MUTE = "667085", LINE = "D8DEE7";
const CW = 9360;

const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 300, after: 120 }, pageBreakBefore: true, children: [new TextRun({ text: t, bold: true, color: NAVY, size: 30 })] });
const H1n = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 280, after: 120 }, children: [new TextRun({ text: t, bold: true, color: NAVY, size: 30 })] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 200, after: 80 }, children: [new TextRun({ text: t, bold: true, color: ACCENT, size: 23 })] });
const P = (t) => new Paragraph({ spacing: { after: 100 }, children: Array.isArray(t) ? t : [new TextRun({ text: t, size: 21, color: INK })] });
const MUTED = (t) => new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: "Tip: " + t, size: 19, color: MUTE, italics: true })] });
const WARN = (t) => new Paragraph({ spacing: { after: 120 }, shading: { type: ShadingType.CLEAR, fill: "FFF7ED" }, children: [new TextRun({ text: "Note: " + t, size: 19, color: "9A3412" })] });
const CODE = (t) => new Paragraph({ spacing: { after: 40 }, shading: { type: ShadingType.CLEAR, fill: "F2F4F7" }, children: [new TextRun({ text: t, font: "Consolas", size: 18, color: "0B3B36" })] });
let inst = 0;
const reset = () => { inst++; };
const step = (t) => new Paragraph({ numbering: { reference: "nl", level: 0, instance: inst }, spacing: { after: 60 }, children: Array.isArray(t) ? t : [new TextRun({ text: t, size: 21, color: INK })] });
const bullets = (items) => items.map((it) => new Paragraph({ numbering: { reference: "bl", level: 0 }, spacing: { after: 50 }, children: Array.isArray(it) ? it : [new TextRun({ text: it, size: 21, color: INK })] }));
const b = (t) => new TextRun({ text: t, bold: true, size: 21, color: INK });
const tx = (t) => new TextRun({ text: t, size: 21, color: INK });
const mono = (t) => new TextRun({ text: t, font: "Consolas", size: 19, color: "0B3B36" });
function cell(text, w, opts = {}) {
  const runs = Array.isArray(text) ? text : [new TextRun({ text: String(text), size: opts.size ?? 19, bold: opts.bold ?? false, color: opts.color ?? INK })];
  return new TableCell({ width: { size: w, type: WidthType.DXA }, shading: opts.fill ? { type: ShadingType.CLEAR, fill: opts.fill } : undefined, margins: { top: 60, bottom: 60, left: 90, right: 90 }, children: [new Paragraph({ children: runs })] });
}
function table(headers, rows, widths) {
  const bd = { style: BorderStyle.SINGLE, size: 4, color: LINE };
  const borders = { top: bd, bottom: bd, left: bd, right: bd, insideHorizontal: bd, insideVertical: bd };
  const trs = [new TableRow({ tableHeader: true, children: headers.map((c, i) => cell(c, widths[i], { bold: true, color: "FFFFFF", fill: NAVY })) })];
  rows.forEach((r, idx) => trs.push(new TableRow({ children: r.map((c, i) => cell(c, widths[i], { fill: idx % 2 ? "F7F9FB" : "FFFFFF" })) })));
  return new Table({ columnWidths: widths, width: { size: CW, type: WidthType.DXA }, rows: trs, borders });
}

const c = [];
// Cover
c.push(new Paragraph({ spacing: { before: 1500 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "ETIP", bold: true, color: ACCENT, size: 54 })] }));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 }, children: [new TextRun({ text: "Integration Guides", bold: true, color: NAVY, size: 30 })] }));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 500 }, children: [new TextRun({ text: "SSO sign-in · Outbound webhooks · API keys · CI/CD reporters", italics: true, color: MUTE, size: 20 })] }));
c.push(P("These guides assume no prior experience. Each one is a standalone, click-by-click walkthrough. ETIP's built-in API page (Swagger) at http://localhost:8000/docs is used to drive the setup — sign in there first, as shown in each guide's Part A."));
c.push(P([b("Companion guide: "), tx("the Jira connector has its own document (ETIP × Jira Integration Guide).")]));

// ============ GUIDE 1: SSO ============
c.push(H1("Guide 1 — Single Sign-On (SSO / OIDC)"));
c.push(P([tx("SSO lets your people sign in to ETIP with their existing company account (Okta, Microsoft Entra/Azure AD, Google Workspace, Keycloak, …) instead of a separate ETIP password. ETIP uses the "), b("OpenID Connect (OIDC)"), tx(" standard: the user is sent to your identity provider (IdP) to log in, and on success ETIP creates their account automatically the first time and maps their roles from the IdP's groups.")]));
c.push(H2("1A. Sign in to ETIP's API page"));
reset();
c.push(step([tx("Start ETIP ("), mono("./run.sh"), tx(" or "), mono("run.bat"), tx("), open "), mono("http://localhost:8000/docs"), tx(".")]));
c.push(step([tx("Use "), b("POST /api/v1/auth/login"), tx(" ("), b("Try it out → Execute"), tx(") with the admin credentials, copy the "), mono("access_token"), tx(", click "), b("Authorize"), tx(" at the top, paste it, "), b("Authorize → Close"), tx(".")]));
c.push(H2("1B. Decide your ETIP address"));
c.push(P([tx("ETIP builds its login return address (the "), b("redirect URI"), tx(") from a setting. For a laptop test you can leave it as "), mono("http://localhost:8000"), tx("; for real users set the environment variable "), mono("PUBLIC_BASE_URL"), tx(" to the address people use, e.g. "), mono("https://etip.acme.com"), tx(", before starting ETIP.")]));
c.push(P([b("Your redirect URI is: "), mono("<that base>/api/v1/auth/sso/callback")]));
c.push(WARN("Whatever this URI is, you must register the EXACT same string in your IdP (next step). A mismatch is the #1 SSO error."));
c.push(H2("1C. Create an OIDC app in your identity provider"));
c.push(P("Do this in your IdP's admin console. Labels differ per provider, but you always create a “web / confidential” OIDC application and collect three things: a Client ID, a Client Secret, and an Issuer URL."));
c.push(table(["Provider", "Where", "Notes"], [
  ["Okta", "Admin → Applications → Create App Integration → OIDC → Web Application", "Issuer: https://<your-org>.okta.com"],
  ["Microsoft Entra / Azure AD", "App registrations → New registration (Web)", "Issuer: https://login.microsoftonline.com/<tenant-id>/v2.0"],
  ["Google Workspace", "Google Cloud Console → APIs & Services → Credentials → OAuth client ID (Web)", "Issuer: https://accounts.google.com"],
  ["Keycloak", "Clients → Create (OpenID Connect, confidential)", "Issuer: https://<host>/realms/<realm>"],
], [2600, 4400, 2360]));
reset();
c.push(step([tx("In the app, set the "), b("redirect URI / sign-in redirect"), tx(" to your ETIP callback URI from 1B (exactly).")]));
c.push(step([tx("Enable scopes "), mono("openid email profile"), tx(" (usually on by default). If you want role mapping, also emit a "), mono("groups"), tx(" (or "), mono("roles"), tx(") claim — see 1F.")]));
c.push(step("Save, then copy the Client ID, Client Secret, and the Issuer URL."));
c.push(H2("1D. Configure SSO in ETIP"));
reset();
c.push(step([tx("In Swagger: "), b("SSO → PUT /api/v1/auth/sso/config"), tx(" → "), b("Try it out"), tx(". Body:")]));
c.push(CODE('{ "client_id": "<from IdP>",'));
c.push(CODE('  "client_secret": "<from IdP>",'));
c.push(CODE('  "issuer": "<issuer URL from IdP>",'));
c.push(CODE('  "default_role_name": "Member",'));
c.push(CODE('  "allowed_domains": ["acme.com"],'));
c.push(CODE('  "role_mappings": {"etip-admins": "Organization Admin"},'));
c.push(CODE('  "is_enabled": true }'));
c.push(step([tx("Click "), b("Execute"), tx(". (You can leave authorize/token/JWKS URLs blank — the next step fills them.)")]));
c.push(step([tx("Run "), b("POST /api/v1/auth/sso/discover"), tx(" with body "), mono('{ "issuer": "<issuer URL>" }'), tx(". ETIP reads the IdP's discovery document and fills the authorize, token and JWKS endpoints automatically.")]));
c.push(MUTED("allowed_domains (optional) restricts SSO to specific email domains. Leave it [] to allow any. The client secret is stored securely and never shown again."));
c.push(H2("1E. Test the sign-in"));
reset();
c.push(step([tx("Call "), b("GET /api/v1/auth/sso/login"), tx(" with "), mono("organization_slug = demo-transformation-co"), tx(" (or your org's slug). Copy the "), mono("authorize_url"), tx(" from the response.")]));
c.push(step("Paste that URL into a browser. You'll land on your IdP's login page. Sign in with a company account."));
c.push(step([tx("The IdP sends you back to ETIP's callback, which returns ETIP "), b("access and refresh tokens"), tx(". First-time users are created automatically (just-in-time) with the mapped roles.")]));
c.push(step([tx("Confirm the user exists: as admin, "), b("GET /api/v1/users"), tx(" — the SSO user is listed.")]));
c.push(H2("1F. Role mapping (optional)"));
c.push(P([tx("If your IdP includes a "), mono("groups"), tx(" or "), mono("roles"), tx(" claim in the token, ETIP maps those values to ETIP roles using "), mono("role_mappings"), tx(". Example: "), mono('{"etip-admins": "Organization Admin", "pmo": "Project Manager"}'), tx(". A user in the IdP group "), mono("etip-admins"), tx(" is provisioned as an ETIP Organization Admin. Unmapped users fall back to "), mono("default_role_name"), tx(".")]));
c.push(H2("1G. Troubleshooting SSO"));
c.push(table(["Symptom", "Fix"], [
  ["redirect_uri mismatch (at IdP)", "The IdP's redirect URI must equal <PUBLIC_BASE_URL>/api/v1/auth/sso/callback exactly."],
  ["Could not verify token", "Re-run discover so JWKS URL is set; confirm the issuer matches the IdP."],
  ["Email domain not permitted", "Add the domain to allowed_domains, or set it to []."],
  ["User gets the wrong role", "Check role_mappings keys match the exact group values in the IdP token."],
], [3400, 5960]));

// ============ GUIDE 2: Webhooks ============
c.push(H1("Guide 2 — Outbound webhooks (Integration Hub)"));
c.push(P([tx("A "), b("webhook"), tx(" lets ETIP notify another system the moment something happens — for example post to a Slack or Teams channel, or trigger an automation. You register a target URL and the events you care about; ETIP delivers a JSON message to that URL, records every delivery, and retries failures.")]));
c.push(H2("2A. Sign in to Swagger"));
c.push(P("As in Guide 1 (Part 1A): open /docs, log in, Authorize."));
c.push(H2("2B. Get a target URL to receive events"));
c.push(...bullets([
  [b("Slack: "), tx("in Slack, create an “Incoming Webhook” app and copy its URL (https://hooks.slack.com/services/…).")],
  [b("Microsoft Teams: "), tx("a channel → Connectors → Incoming Webhook → copy the URL.")],
  [b("Anything else: "), tx("any HTTPS URL that accepts a POST. For a quick test use a free inbox like https://webhook.site and copy your unique URL.")],
]));
c.push(H2("2C. Register the webhook in ETIP"));
reset();
c.push(step([tx("In Swagger: "), b("Integrations → POST /api/v1/integrations/webhooks"), tx(" → "), b("Try it out"), tx(". Body:")]));
c.push(CODE('{ "name": "Ops Slack",'));
c.push(CODE('  "target_url": "https://webhook.site/your-unique-id",'));
c.push(CODE('  "event_types": ["project.created", "workflow.approved"],'));
c.push(CODE('  "secret": "any-signing-secret",'));
c.push(CODE('  "is_active": true }'));
c.push(step([tx("Click "), b("Execute"), tx(". Leave "), mono("event_types"), tx(" empty ("), mono("[]"), tx(") to receive "), b("all"), tx(" events.")]));
c.push(step([tx("Send a test delivery: "), b("POST /api/v1/integrations/webhooks/{endpoint_id}/test"), tx(" with the id from the previous response. Check your target URL received a POST.")]));
c.push(H2("2D. Publish an event and watch delivery"));
reset();
c.push(step([tx("Publish a sample event: "), b("POST /api/v1/integrations/events/publish"), tx(" with:")]));
c.push(CODE('{ "event_type": "project.created", "payload": {"code": "DEMO", "name": "Test"} }'));
c.push(step([tx("The response shows how many endpoints matched and how many delivered. View history at "), b("GET /api/v1/integrations/webhooks/deliveries"), tx(".")]));
c.push(step([tx("If a delivery failed (target was down), ETIP schedules a retry. Force pending retries with "), b("POST /api/v1/integrations/webhooks/deliveries/retry-due"), tx(", or retry one with "), b("POST /…/deliveries/{delivery_id}/retry"), tx(".")]));
c.push(MUTED("If you set a secret, ETIP signs each delivery so the receiver can verify it really came from ETIP. The secret is stored hidden (secret_set: true)."));
c.push(H2("2E. Troubleshooting webhooks"));
c.push(table(["Symptom", "Fix"], [
  ["No delivery arrives", "Check the webhook is_active, and that event_types is empty or includes the event you published."],
  ["Deliveries show failed", "The target URL was unreachable or returned an error; fix the URL and use retry-due."],
  ["Receiver rejects the call", "If you set a secret, verify the signature on the receiving side; or clear the secret to test."],
], [3400, 5960]));

// ============ GUIDE 3: API keys ============
c.push(H1("Guide 3 — API keys (programmatic access)"));
c.push(P([tx("An "), b("API key"), tx(" lets another program call ETIP's API without a human logging in — for scripts, CI pipelines, or another system reading ETIP data. The key is tied to a user and inherits that user's permissions.")]));
c.push(H2("3A. Create a key"));
reset();
c.push(step([tx("In Swagger (signed in): "), b("API Keys → POST /api/v1/api-keys"), tx(" → "), b("Try it out"), tx(". Body:")]));
c.push(CODE('{ "name": "CI pipeline" }'));
c.push(step([tx("Click "), b("Execute"), tx(". The response includes "), mono("api_key"), tx(" — the full secret, shown "), b("once"), tx(". Copy it now; ETIP only stores a hash and will never show it again.")]));
c.push(WARN("Store the key like a password (a CI secret store, a vault). Anyone with it can act as that user within its permissions."));
c.push(H2("3B. Use the key"));
c.push(P([tx("Send it in the "), mono("X-API-Key"), tx(" header on any API request — no login needed:")]));
c.push(CODE('curl https://etip.acme.com/api/v1/projects \\'));
c.push(CODE('  -H "X-API-Key: <the api_key you copied>"'));
c.push(H2("3C. List and revoke"));
c.push(...bullets([
  [b("GET /api/v1/api-keys"), tx(" — list keys (shows a short prefix, never the secret).")],
  [b("POST /api/v1/api-keys/{key_id}/revoke"), tx(" — turn a key off immediately if it leaks or is no longer needed.")],
]));
c.push(MUTED("Give CI/reporting keys a user whose role has just the permissions they need (e.g. build:manage for the CI reporter in Guide 4)."));

// ============ GUIDE 4: CI/CD ============
c.push(H1("Guide 4 — CI/CD reporters (AI-Delivery gate)"));
c.push(P([tx("ETIP's AI-Delivery module tracks builds through generate → build → test → QA → deploy → perf, with a quality gate. The "), b("CI reporter"), tx(" lets your existing pipeline (GitHub Actions, GitLab CI, Jenkins) send its results back to ETIP so the build's status and metrics stay current and the gate can be enforced.")]));
c.push(H2("4A. What you need"));
c.push(table(["Variable", "Meaning"], [
  ["ETIP_URL", "Base URL of your ETIP instance, e.g. https://etip.acme.com"],
  ["ETIP_API_KEY", "An ETIP API key (Guide 3) whose user has the build:manage permission"],
  ["ETIP_BUILD_ID", "The id of the ETIP build request this pipeline run reports against"],
], [2600, 6760]));
c.push(P([tx("The reporter script and ready-made pipeline files are in the bundle under "), mono("scripts/etip_report.py"), tx(" and "), mono("docs/examples/ci/"), tx(" ("), mono("ai-delivery.yml"), tx(" for GitHub Actions, "), mono(".gitlab-ci.yml"), tx(", and "), mono("Jenkinsfile"), tx(").")]));
c.push(H2("4B. Report results from the pipeline"));
c.push(P("The script has two commands — report a pipeline run, and report a deployment:"));
c.push(CODE('export ETIP_URL=https://etip.acme.com'));
c.push(CODE('export ETIP_API_KEY=<key from Guide 3>'));
c.push(CODE('export ETIP_BUILD_ID=<build id>'));
c.push(CODE('python scripts/etip_report.py run --status passed \\'));
c.push(CODE('   --provider github-actions --metrics \'{"coverage": 87, "p95_ms": 320}\''));
c.push(CODE('python scripts/etip_report.py deploy --environment staging \\'));
c.push(CODE('   --url https://staging.acme.com'));
c.push(H2("4C. Wire it into GitHub Actions"));
reset();
c.push(step([tx("Copy "), mono("docs/examples/ci/ai-delivery.yml"), tx(" into your repo at "), mono(".github/workflows/"), tx(".")]));
c.push(step([tx("In GitHub → repo "), b("Settings → Secrets and variables → Actions"), tx(", add secrets "), mono("ETIP_URL"), tx(", "), mono("ETIP_API_KEY"), tx(", "), mono("ETIP_BUILD_ID"), tx(".")]));
c.push(step("Push a commit. The workflow runs your build/tests, then calls the reporter so ETIP shows the run and its metrics on the AI Delivery tab."));
c.push(step([tx("Enforce the gate: in ETIP, "), b("GET /api/v1/builds/{id}/gate"), tx(" returns pass/fail against your coverage / performance / tests thresholds; fail the pipeline on a failing gate.")]));
c.push(MUTED("GitLab CI and Jenkins work the same way — use the matching example file and set the same three variables in that system's secret store."));
c.push(H1n("Where to go next"));
c.push(P("Each guide above is self-contained. For the Jira connector see the separate ETIP × Jira Integration Guide; for install and a full feature test checklist see the ETIP Install & Test Guide."));

const doc = new Document({
  creator: "ETIP", title: "ETIP Integration Guides",
  numbering: { config: [
    { reference: "bl", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 240 } } } }] },
    { reference: "nl", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 240 } } } }] },
  ] },
  styles: { default: { document: { run: { font: "Calibri", size: 21, color: INK } } } },
  sections: [{ properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } }, children: c }],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync("/home/claude/etip/ETIP_Integration_Guides.docx", buf); console.log("wrote ETIP_Integration_Guides.docx"); });
