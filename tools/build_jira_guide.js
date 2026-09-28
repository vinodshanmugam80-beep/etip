// Build the ETIP ↔ Jira Integration Guide (.docx) — beginner-friendly, both tools.
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType, PageBreak, LevelFormat,
} = require("docx");

const NAVY = "0F1B2D", ACCENT = "0E9488", INK = "101828", MUTE = "667085", LINE = "D8DEE7";
const CW = 9360;

const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 280, after: 120 }, children: [new TextRun({ text: t, bold: true, color: NAVY, size: 30 })] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 200, after: 90 }, children: [new TextRun({ text: t, bold: true, color: ACCENT, size: 24 })] });
const P = (t) => new Paragraph({ spacing: { after: 100 }, children: Array.isArray(t) ? t : [new TextRun({ text: t, size: 21, color: INK })] });
const MUTED = (t) => new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: "Tip: " + t, size: 19, color: MUTE, italics: true })] });
const WARN = (t) => new Paragraph({ spacing: { after: 120 }, shading: { type: ShadingType.CLEAR, fill: "FFF7ED" }, children: [new TextRun({ text: "Note: " + t, size: 19, color: "9A3412" })] });
const CODE = (t) => new Paragraph({ spacing: { after: 40 }, shading: { type: ShadingType.CLEAR, fill: "F2F4F7" }, children: [new TextRun({ text: t, font: "Consolas", size: 18, color: "0B3B36" })] });
let stepInst = 0;
const resetSteps = () => { stepInst++; };
const step = (t) => new Paragraph({ numbering: { reference: "nl", level: 0, instance: stepInst }, spacing: { after: 60 }, children: Array.isArray(t) ? t : [new TextRun({ text: t, size: 21, color: INK })] });
const bullets = (items) => items.map((it) => new Paragraph({ numbering: { reference: "bl", level: 0 }, spacing: { after: 50 }, children: Array.isArray(it) ? it : [new TextRun({ text: it, size: 21, color: INK })] }));
const b = (t) => new TextRun({ text: t, bold: true, size: 21, color: INK });
const tx = (t) => new TextRun({ text: t, size: 21, color: INK });
const mono = (t) => new TextRun({ text: t, font: "Consolas", size: 19, color: "0B3B36" });

function cell(text, w, opts = {}) {
  const runs = Array.isArray(text) ? text : [new TextRun({ text: String(text), size: opts.size ?? 19, bold: opts.bold ?? false, color: opts.color ?? INK })];
  return new TableCell({ width: { size: w, type: WidthType.DXA }, shading: opts.fill ? { type: ShadingType.CLEAR, fill: opts.fill } : undefined, margins: { top: 60, bottom: 60, left: 90, right: 90 }, children: [new Paragraph({ children: runs })] });
}
function table(headers, rows, widths) {
  const b2 = { style: BorderStyle.SINGLE, size: 4, color: LINE };
  const borders = { top: b2, bottom: b2, left: b2, right: b2, insideHorizontal: b2, insideVertical: b2 };
  const trs = [new TableRow({ tableHeader: true, children: headers.map((c, i) => cell(c, widths[i], { bold: true, color: "FFFFFF", fill: NAVY })) })];
  rows.forEach((r, idx) => trs.push(new TableRow({ children: r.map((c, i) => cell(c, widths[i], { fill: idx % 2 ? "F7F9FB" : "FFFFFF" })) })));
  return new Table({ columnWidths: widths, width: { size: CW, type: WidthType.DXA }, rows: trs, borders });
}

const c = [];
// Cover
c.push(new Paragraph({ spacing: { before: 1500 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "ETIP  ×  Jira", bold: true, color: ACCENT, size: 54 })] }));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 }, children: [new TextRun({ text: "Connecting ETIP to Jira — a complete beginner's guide", bold: true, color: NAVY, size: 28 })] }));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 }, children: [new TextRun({ text: "Set up, sync and test the Jira integration end to end. No prior experience needed.", italics: true, color: MUTE, size: 20 })] }));
c.push(new Paragraph({ children: [new PageBreak()] }));

// 1. Concepts
c.push(H1("1. What you're building (in plain English)"));
c.push(P([b("Jira"), tx(" is a tool teams use to track work items called "), b("issues"), tx(" (bugs, stories, tasks). "), b("ETIP"), tx(" is your platform for managing projects and portfolios; its work items are called "), b("tasks"), tx(". The "), b("Jira connector"), tx(" keeps the two in step so you don't type the same thing twice.")]));
c.push(P("There are three ways information moves between them:"));
c.push(table(["Feature", "Direction", "What it does"], [
  ["Import", "Jira → ETIP (you click)", "Pulls existing Jira issues in and creates matching ETIP tasks."],
  ["Webhook", "Jira → ETIP (automatic)", "Whenever an issue changes in Jira, Jira notifies ETIP and the task updates itself."],
  ["Push", "ETIP → Jira (you click)", "Sends an ETIP task to Jira as an issue, and keeps it updated."],
], [1900, 3200, 4260]));
c.push(MUTED("This guide sets up all three. If you only want to see it work quickly without a Jira account, jump to the Appendix — it simulates Jira with a couple of commands."));

// 2. Prerequisites
c.push(H1("2. Before you start"));
c.push(...bullets([
  "A computer that can run ETIP (see the ETIP Install & Test Guide) — you'll have it running at http://localhost:8000.",
  "A free Atlassian (Jira Cloud) account — we create it together in Part B.",
  "About 30–40 minutes.",
]));
c.push(P([b("Words you'll see: "), tx("“API token” = a password-like key for programs. “Project key” = a short code for a Jira project, like "), mono("ETIP"), tx(". “Webhook” = an automatic web notification. “Swagger” = ETIP's built-in web page for calling its API, at "), mono("http://localhost:8000/docs"), tx(".")]));

// 3. Part A — start ETIP
c.push(H1("3. Part A — Start ETIP and get your access key"));
c.push(P("ETIP's connector is configured through its API page (Swagger). First we sign in there."));
resetSteps();
c.push(step([tx("Start ETIP. In its folder run "), mono("./run.sh"), tx(" (macOS/Linux) or double-click "), mono("run.bat"), tx(" (Windows). Wait for it to print the URLs.")]));
c.push(step([tx("Open a browser to "), mono("http://localhost:8000/docs"), tx(". This is the Swagger API page.")]));
c.push(step([tx("Find "), b("Authentication → POST /api/v1/auth/login"), tx(". Click it, click "), b("Try it out"), tx(", and replace the request body with:")]));
c.push(CODE('{ "organization_slug": "demo-transformation-co",'));
c.push(CODE('  "email": "admin@demo.co",'));
c.push(CODE('  "password": "Str0ng-Passphrase!1" }'));
c.push(step([tx("Click "), b("Execute"), tx(". In the response, copy the long "), mono("access_token"), tx(" value (between the quotes).")]));
c.push(step([tx("Scroll to the top of the page and click the "), b("Authorize"), tx(" button. Paste the token, click "), b("Authorize"), tx(", then "), b("Close"), tx(". You are now signed in for every call on this page.")]));
c.push(MUTED("The token expires after a while. If calls start returning 401, repeat steps 3–5 to get a fresh one."));

// 4. Part B — Jira account/project/token
c.push(H1("4. Part B — Create your Jira account, project and API token"));
c.push(H2("B1. Create a free Jira Cloud site"));
resetSteps();
c.push(step([tx("Go to "), mono("https://www.atlassian.com/software/jira"), tx(" and click "), b("Get it free"), tx(".")]));
c.push(step("Sign up with your email (or Google). Choose Jira when asked which product."));
c.push(step([tx("Pick a site name. You'll get a web address like "), mono("https://yourname.atlassian.net"), tx(" — this is your "), b("base URL"), tx(". Write it down.")]));
c.push(step("When prompted, create a project. Choose a simple “Kanban” or “Scrum” software project and give it a name."));
c.push(step([tx("Note the "), b("project key"), tx(" — the short uppercase code shown next to the project (for example "), mono("ETIP"), tx(" or "), mono("KAN"), tx("). You'll need it.")]));
c.push(H2("B2. Create an API token (your program key)"));
c.push(step([tx("Go to "), mono("https://id.atlassian.com/manage-profile/security/api-tokens"), tx(".")]));
c.push(step([tx("Click "), b("Create API token"), tx(", give it a label like "), mono("etip"), tx(", and click "), b("Create"), tx(".")]));
c.push(step([tx("Click "), b("Copy"), tx(" and paste the token somewhere safe now — Jira won't show it again.")]));
c.push(WARN("Treat the API token like a password. It, plus your Jira login email, lets ETIP act as you in Jira."));
c.push(P([b("You now have four things from Jira: "), tx("(1) base URL, (2) project key, (3) your Jira login email, (4) the API token.")]));

// 5. Part C — ngrok
c.push(H1("5. Part C — Make ETIP reachable from the internet"));
c.push(P("Jira lives on the internet; your ETIP runs on your computer at localhost, which Jira can't reach. For the webhook and push to work with real Jira, we give ETIP a temporary public web address using a free tool called ngrok."));
c.push(WARN("If you only want to test Import and the webhook logic locally, you can skip this Part and use the Appendix simulation instead. Import and Push call OUT to Jira, so they work as long as your computer has internet — only Jira calling IN (the webhook) needs a public URL."));
resetSteps();
c.push(step([tx("Create a free account at "), mono("https://ngrok.com"), tx(" and follow its “Setup” page to install ngrok and run the one-time "), mono("ngrok config add-authtoken …"), tx(" command it gives you.")]));
c.push(step([tx("With ETIP running, open a new terminal and run: "), mono("ngrok http 8000")]));
c.push(step([tx("ngrok prints a "), b("Forwarding"), tx(" line like "), mono("https://ab12cd34.ngrok-free.app -> http://localhost:8000"), tx(". Copy that https address — this is your "), b("public ETIP URL"), tx(".")]));
c.push(MUTED("Keep this terminal open while testing. If you restart ngrok, the address changes and you must update the Jira webhook URL (Part G)."));

// 6. Part D — connect
c.push(H1("6. Part D — Connect ETIP to Jira"));
c.push(P("Back on the Swagger page (http://localhost:8000/docs), still signed in from Part A."));
resetSteps();
c.push(step([tx("Find "), b("Jira Connector → PUT /api/v1/integrations/jira/config"), tx(". Click it → "), b("Try it out"), tx(".")]));
c.push(step("Fill the request body with your four Jira values, a secret you invent for the webhook, and turn it on:"));
c.push(CODE('{ "base_url": "https://yourname.atlassian.net",'));
c.push(CODE('  "project_key": "ETIP",'));
c.push(CODE('  "user_email": "you@example.com",'));
c.push(CODE('  "api_token": "<paste the Jira API token>",'));
c.push(CODE('  "webhook_secret": "choose-any-secret-123",'));
c.push(CODE('  "default_project_id": "<an ETIP project id>",'));
c.push(CODE('  "is_enabled": true }'));
c.push(step([tx("For "), mono("default_project_id"), tx(" (the ETIP project that imported issues land in): open "), b("Projects → GET /api/v1/projects"), tx(", "), b("Try it out → Execute"), tx(", and copy any "), mono("id"), tx(" from the list. Paste it in.")]));
c.push(step([tx("Click "), b("Execute"), tx(". A 200 response means it saved. In that response, copy the "), mono("organization_id"), tx(" value — you need it for the webhook URL in Part G.")]));
c.push(MUTED("The API token is stored securely and never shown again; the response shows token_set: true instead."));

// 7. Part E — test connection
c.push(H1("7. Part E — Test the connection"));
resetSteps();
c.push(step([tx("Find "), b("Jira Connector → POST /api/v1/integrations/jira/test"), tx(" → "), b("Try it out → Execute"), tx(".")]));
c.push(step([tx("A 200 response with "), mono('"ok": true'), tx(" and your Jira display name means the credentials work.")]));
c.push(step([tx("If you see "), mono('"ok": false'), tx(" or an error: re-check the base URL (no trailing slash needed), the login email, and that the API token was pasted fully. Then run "), b("PUT config"), tx(" again and retry.")]));

// 8. Part F — import
c.push(H1("8. Part F — Import existing Jira issues into ETIP"));
resetSteps();
c.push(step("In Jira, create two or three issues in your project (click Create at the top, add a summary, Create)."));
c.push(step([tx("In Swagger: "), b("Jira Connector → POST /api/v1/integrations/jira/import"), tx(" → "), b("Try it out"), tx(". Body:")]));
c.push(CODE('{ "max_results": 100 }'));
c.push(step([tx("Click "), b("Execute"), tx(". The response shows counts like "), mono('{"created": 3, "updated": 0, …}'), tx(".")]));
c.push(step([tx("Verify: open "), b("Tasks → GET /api/v1/tasks"), tx(" and pass your project id, or open the ETIP dashboard (http://localhost:8000) → Manage → Tasks. Your Jira issues are now ETIP tasks.")]));
c.push(step([tx("Run import again — the counts move to "), mono('"updated"'), tx(", proving it never creates duplicates.")]));
c.push(MUTED("By default import pulls the whole project. To pull a subset, add a Jira query, e.g. \"jql\": \"status = 'To Do'\" in the body."));

// 9. Part G — webhook
c.push(H1("9. Part G — Set up the webhook in Jira (automatic updates)"));
c.push(P("Now we make Jira notify ETIP automatically whenever an issue changes."));
c.push(P([b("Your webhook URL is: ")]));
c.push(CODE("<public ETIP URL>/api/v1/integrations/jira/webhook/<organization_id>?secret=<webhook_secret>"));
c.push(P([tx("Example: "), mono("https://ab12cd34.ngrok-free.app/api/v1/integrations/jira/webhook/1a2b…?secret=choose-any-secret-123")]));
resetSteps();
c.push(step([tx("In Jira, click the "), b("gear icon (Settings)"), tx(" at the top-right → "), b("System"), tx(".")]));
c.push(step([tx("In the left menu, scroll to the "), b("Advanced"), tx(" section and click "), b("WebHooks"), tx(".")]));
c.push(step([tx("Click "), b("Create a WebHook"), tx(".")]));
c.push(step("Give it a name (e.g. “ETIP sync”). Paste the full webhook URL above into the URL field (including the ?secret=… part)."));
c.push(step([tx("Under "), b("Events"), tx(", tick "), b("Issue: created"), tx(" and "), b("Issue: updated"), tx(". Leave the JQL filter blank to send all issues, or add one to scope it.")]));
c.push(step([tx("Click "), b("Create"), tx(". The webhook is now active.")]));
c.push(WARN("Menu labels in Jira can vary slightly by version; the path is Settings (gear) → System → (Advanced) WebHooks."));

// 10. Part H — test webhook
c.push(H1("10. Part H — Test the webhook"));
resetSteps();
c.push(step("In Jira, open one of your issues and change its summary or move it to another status (e.g. In Progress)."));
c.push(step([tx("Within a few seconds, check ETIP: open "), b("Jira Connector → GET /api/v1/integrations/jira/sync-log"), tx(" → "), b("Execute"), tx(". You'll see an "), mono('"direction": "inbound"'), tx(" entry.")]));
c.push(step([tx("Open the matching task (Tasks → GET, or the dashboard) — its title/status now matches Jira. "), b("You didn't touch ETIP; Jira updated it for you.")]));
c.push(step("Create a brand-new issue in Jira → a new ETIP task appears automatically in your default project."));
c.push(H2("If nothing happens"));
c.push(...bullets([
  [b("Check ngrok is still running"), tx(" and that the webhook URL uses the current ngrok address.")],
  [b("Check the secret matches"), tx(" exactly what you set in Part D (case-sensitive).")],
  [tx("In Jira's WebHooks screen, some versions show a delivery/last-fired status — confirm it attempted a POST.")],
  [tx("A wrong secret returns 401 and is ignored on purpose — that's the security guard working.")],
]));

// 11. Part I — push
c.push(H1("11. Part I — Push an ETIP task to Jira (the other direction)"));
resetSteps();
c.push(step("In the ETIP dashboard → Manage → Tasks, create a task (or pick one). Copy its id (or get it from Tasks → GET)."));
c.push(step([tx("In Swagger: "), b("Jira Connector → POST /api/v1/integrations/jira/tasks/{task_id}/push"), tx(". Click it, "), b("Try it out"), tx(", paste the task id, "), b("Execute"), tx(".")]));
c.push(step([tx("The response returns the new Jira issue key (e.g. "), mono("ETIP-42"), tx("). Open Jira — the issue is there.")]));
c.push(step("Edit the same ETIP task and push again — it updates the same Jira issue instead of creating a new one."));

// 12. Part J — links & log
c.push(H1("12. Part J — See what's linked and what happened"));
c.push(...bullets([
  [b("GET /api/v1/integrations/jira/links"), tx(" — every ETIP task ↔ Jira issue pairing, with a clickable Jira URL.")],
  [b("GET /api/v1/integrations/jira/sync-log"), tx(" — a timeline of every import, push, webhook and test, with counts and success/error status.")],
]));

// 13. Troubleshooting
c.push(H1("13. Troubleshooting"));
c.push(table(["Symptom", "Fix"], [
  ["401 on Swagger calls", "Your token expired — re-do Part A steps 3–5 and Authorize again."],
  ["test returns ok:false", "Wrong base URL, email or API token. Re-run PUT config and try test again."],
  ["import says 'Set a default project'", "default_project_id was empty in the config — set it (Part D step 3)."],
  ["422 'Jira is not enabled'", "is_enabled was false — set it to true in PUT config."],
  ["Webhook does nothing", "ngrok not running, URL out of date, or the secret doesn't match. Recheck Part G."],
  ["Webhook returns 401", "The ?secret= in the Jira URL doesn't match webhook_secret. Fix the URL in Jira."],
  ["ngrok address keeps changing", "Free ngrok gives a new URL each run — update the Jira webhook URL when it changes."],
], [3300, 6060]));

// 14. Appendix
c.push(new Paragraph({ children: [new PageBreak()] }));
c.push(H1("Appendix — Try it without a Jira account"));
c.push(P("You can prove the webhook works using only ETIP, by sending it a Jira-shaped message yourself. Run these in a terminal with ETIP running. (Requires the demo data — the launcher seeds it.)"));
c.push(CODE('# 1) get an admin token'));
c.push(CODE('TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" \\'));
c.push(CODE("  -d '{\"organization_slug\":\"demo-transformation-co\",\"email\":\"admin@demo.co\",\"password\":\"Str0ng-Passphrase!1\"}' \\"));
c.push(CODE('  | python -c "import sys,json;print(json.load(sys.stdin)[\'access_token\'])")'));
c.push(CODE('# 2) pick a project id'));
c.push(CODE('PID=$(curl -s "http://localhost:8000/api/v1/projects?limit=1" -H "Authorization: Bearer $TOKEN" \\'));
c.push(CODE('  | python -c "import sys,json;print(json.load(sys.stdin)[\'items\'][0][\'id\'])")'));
c.push(CODE('# 3) enable the connector and capture your organization id'));
c.push(CODE('ORG=$(curl -s -X PUT http://localhost:8000/api/v1/integrations/jira/config \\'));
c.push(CODE('  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \\'));
c.push(CODE('  -d "{\\"base_url\\":\\"https://acme.atlassian.net\\",\\"project_key\\":\\"ETIP\\",\\"user_email\\":\\"bot@acme.com\\",\\"api_token\\":\\"x\\",\\"webhook_secret\\":\\"whsec\\",\\"default_project_id\\":\\"$PID\\",\\"is_enabled\\":true}" \\'));
c.push(CODE('  | python -c "import sys,json;print(json.load(sys.stdin)[\'organization_id\'])")'));
c.push(CODE('# 4) simulate Jira firing a webhook (creates a task)'));
c.push(CODE('curl -s -X POST "http://localhost:8000/api/v1/integrations/jira/webhook/$ORG?secret=whsec" \\'));
c.push(CODE('  -H "Content-Type: application/json" \\'));
c.push(CODE('  -d \'{"issue":{"id":"10001","key":"ETIP-1","fields":{"summary":"Fix login","status":{"name":"To Do"}}}}\''));
c.push(CODE('# 5) send the same key again -> it UPDATES (no duplicate)'));
c.push(CODE('curl -s -X POST "http://localhost:8000/api/v1/integrations/jira/webhook/$ORG?secret=whsec" \\'));
c.push(CODE('  -H "Content-Type: application/json" \\'));
c.push(CODE('  -d \'{"issue":{"key":"ETIP-1","fields":{"summary":"Fix login page","status":{"name":"In Progress"}}}}\''));
c.push(P([tx("Then view the results: "), mono("GET /integrations/jira/links"), tx(" and "), mono("GET /integrations/jira/sync-log"), tx(", or open the dashboard → Manage → Tasks.")]));

const doc = new Document({
  creator: "ETIP", title: "ETIP × Jira Integration Guide",
  numbering: { config: [
    { reference: "bl", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 240 } } } }] },
    { reference: "nl", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 240 } } } }] },
  ] },
  styles: { default: { document: { run: { font: "Calibri", size: 21, color: INK } } } },
  sections: [{ properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } }, children: c }],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync("/home/claude/etip/ETIP_Jira_Integration_Guide.docx", buf); console.log("wrote ETIP_Jira_Integration_Guide.docx"); });
