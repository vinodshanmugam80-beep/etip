// ETIP — Executive Overview deck (.pptx)
const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
const W = 13.33, H = 7.5;

const NAVY = "0F1B2D", NAVY2 = "18263F", TEAL = "0E9488", TEAL2 = "12B0A8", MINT = "2DD4BF";
const INK = "101828", MUTE = "667085", LINE = "E4E9F0", PANEL = "F7F9FB", WHITE = "FFFFFF";
const GREEN = "059669", AMBER = "D97706", RED = "DC2626";
const TITLE_F = "Calibri", BODY_F = "Calibri";

const notes = (s, t) => s.addNotes(t);

function bgDark(s){ s.background = { color: NAVY }; }
function eyebrow(s, t, color){ s.addText(t.toUpperCase(), { isTextBox:true, x:0.7, y:0.5, w:12, h:0.3, fontFace:BODY_F, fontSize:12, bold:true, color:color||TEAL, charSpacing:3 }); }
function title(s, t, color){ s.addText(t, { isTextBox:true, x:0.7, y:0.8, w:12, h:0.9, fontFace:TITLE_F, fontSize:34, bold:true, color:color||NAVY }); }

// circle "icon" with a glyph
function iconCircle(s, x, y, d, glyph, fill, gcolor){
  s.addShape(p.ShapeType.ellipse, { x, y, w:d, h:d, fill:{ color:fill||TEAL }, line:{ type:"none" } });
  s.addText(glyph, { isTextBox:true, x, y:y-0.02, w:d, h:d, align:"center", valign:"middle", fontFace:TITLE_F, fontSize:16, bold:true, color:gcolor||WHITE });
}
function statCard(s, x, y, w, big, label, sub, color){
  s.addShape(p.ShapeType.roundRect, { x, y, w, h:1.55, rectRadius:0.08, fill:{ color:WHITE }, line:{ color:LINE, width:1 }, shadow:{ type:"outer", color:"9AA5B1", blur:6, offset:2, angle:90, opacity:0.25 } });
  s.addText(big, { isTextBox:true, x:x+0.05, y:y+0.18, w:w-0.1, h:0.7, align:"center", fontFace:TITLE_F, fontSize:34, bold:true, color:color||TEAL });
  s.addText(label, { isTextBox:true, x:x+0.05, y:y+0.9, w:w-0.1, h:0.3, align:"center", fontFace:BODY_F, fontSize:12.5, bold:true, color:INK });
  if(sub) s.addText(sub, { isTextBox:true, x:x+0.05, y:y+1.18, w:w-0.1, h:0.3, align:"center", fontFace:BODY_F, fontSize:9.5, color:MUTE });
}
function featureCard(s, x, y, w, h, glyph, head, body){
  s.addShape(p.ShapeType.roundRect, { x, y, w, h, rectRadius:0.07, fill:{ color:WHITE }, line:{ color:LINE, width:1 }, shadow:{ type:"outer", color:"9AA5B1", blur:5, offset:2, angle:90, opacity:0.2 } });
  iconCircle(s, x+0.25, y+0.25, 0.55, glyph, TEAL, WHITE);
  s.addText(head, { isTextBox:true, x:x+0.95, y:y+0.28, w:w-1.1, h:0.5, fontFace:TITLE_F, fontSize:14.5, bold:true, color:NAVY, valign:"middle" });
  s.addText(body, { isTextBox:true, x:x+0.25, y:y+0.95, w:w-0.5, h:h-1.1, fontFace:BODY_F, fontSize:11, color:INK, valign:"top" });
}

/* 1 — Title */
let s = p.addSlide(); bgDark(s);
s.addShape(p.ShapeType.roundRect, { x:0.7, y:2.3, w:0.9, h:0.9, rectRadius:0.14, fill:{ color:TEAL }, line:{ type:"none" } });
s.addText("E", { isTextBox:true, x:0.7, y:2.28, w:0.9, h:0.9, align:"center", valign:"middle", fontFace:TITLE_F, fontSize:40, bold:true, color:WHITE });
s.addText("ETIP", { isTextBox:true, x:1.8, y:2.35, w:8, h:0.9, fontFace:TITLE_F, fontSize:52, bold:true, color:WHITE, charSpacing:6 });
s.addText("Enterprise Transformation Intelligence Platform", { isTextBox:true, x:0.72, y:3.5, w:11.5, h:0.6, fontFace:TITLE_F, fontSize:26, bold:true, color:MINT });
s.addText("Plan.  Execute.  Govern.  Transform.", { isTextBox:true, x:0.72, y:4.15, w:11.5, h:0.5, fontFace:BODY_F, fontSize:16, italic:true, color:"C3C2B7" });
s.addText("Executive Overview  ·  2026 Build", { isTextBox:true, x:0.72, y:6.4, w:11.5, h:0.4, fontFace:BODY_F, fontSize:13, bold:true, color:"8FA0B5", charSpacing:2 });
notes(s, "ETIP is a production-grade, multi-tenant platform for managing projects, programs, portfolios and enterprise transformation — combining planning, execution, governance and intelligence in one product.");

/* 2 — The challenge */
s = p.addSlide(); s.background = { color:WHITE };
eyebrow(s, "The challenge"); title(s, "Transformation is hard to see and harder to govern");
const ch = [
  ["!", "Fragmented tooling", "Plans in MS Project, work in Jira, money in spreadsheets, status in slides — no single source of truth."],
  ["?", "Blind to real status", "Health is reported, not measured. Cost overruns and slippage surface too late to act."],
  ["<>", "Weak governance", "Stage gates and approvals live in email; sign-offs and payments aren't linked to deliverables."],
  ["$", "Value not tracked", "Budgets are set but benefits, EAC and ETC are rarely tracked to completion."],
];
ch.forEach((c,i)=>{ const x = 0.7 + (i%2)*6.1, y = 2.0 + Math.floor(i/2)*2.3; featureCard(s, x, y, 5.75, 2.0, c[0], c[1], c[2]); });
notes(s, "Executives lack a single, measured view. ETIP replaces fragmented tooling with one governed, evidence-based platform.");

/* 3 — What ETIP is */
s = p.addSlide(); s.background = { color:WHITE };
eyebrow(s, "What it is"); title(s, "One platform, four disciplines");
s.addText("ETIP unifies delivery and executive intelligence: teams plan and execute the work, leaders govern it through stage gates, and an Earned-Value intelligence layer measures it end to end — all multi-tenant, auditable and secure.", { isTextBox:true, x:0.7, y:1.75, w:11.9, h:0.8, fontFace:BODY_F, fontSize:14, color:INK });
const pillars = [["PLAN","Portfolios, programs, projects, roadmaps, milestones & resources"],["EXECUTE","Tasks, sprints, RAID, change, timesheets & documents"],["GOVERN","SDLC stage gates, approvals, financial milestones & RBAC"],["TRANSFORM","EVM intelligence, forecasts, KPIs, benefits & AI delivery"]];
pillars.forEach((c,i)=>{ const x=0.7+i*3.03; s.addShape(p.ShapeType.roundRect,{x,y:2.9,w:2.85,h:3.4,rectRadius:0.09,fill:{color:i%2?NAVY:NAVY2},line:{type:"none"}}); s.addText(c[0],{isTextBox:true,x,y:3.15,w:2.85,h:0.5,align:"center",fontFace:TITLE_F,fontSize:19,bold:true,color:MINT,charSpacing:2}); s.addText(c[1],{isTextBox:true,x:x+0.25,y:3.85,w:2.35,h:2.2,align:"center",fontFace:BODY_F,fontSize:12.5,color:"E6EAF0"}); });
notes(s, "The four pillars map to what different stakeholders need from the same system of record.");

/* 4 — At a glance (stats) */
s = p.addSlide(); s.background = { color:PANEL };
eyebrow(s, "At a glance"); title(s, "Enterprise-grade by construction");
const stats = [["39","API modules","25 capability areas"],["EVM","Earned Value","SPI · CPI · EAC · ETC · VAC"],["418","Automated tests","ruff + mypy clean"],["Multi","Tenant isolation","org · dept · BU · project"]];
stats.forEach((c,i)=>{ statCard(s, 0.7+i*3.05, 2.2, 2.75, c[0], c[1], c[2], i===1?NAVY:TEAL); });
const stats2 = [["RBAC","Permission-based access","JWT + refresh, audit trail"],["Clean","Architecture","API → Service → Repo → DB"],["Offline","Self-contained UI","bundled fonts + charts"],["100%","Audited writes","UUID · version · soft-delete"]];
stats2.forEach((c,i)=>{ statCard(s, 0.7+i*3.05, 4.15, 2.75, c[0], c[1], c[2], i===1?NAVY:TEAL); });
notes(s, "Every table carries a UUID primary key, audit fields, a version column and soft-delete. The build ships with 418 automated tests.");

/* 5 — Capability map */
s = p.addSlide(); s.background = { color:WHITE };
eyebrow(s, "Capability map"); title(s, "Everything a transformation office needs");
const caps = [
  ["Delivery","Projects · Tasks · Sprints · Milestones · Dependencies"],
  ["Portfolio","Portfolios · Programs · Roadmaps · Prioritisation"],
  ["Governance","SDLC stage gates · Approvals · Change control"],
  ["Financials","Budget · Cost ledger · EAC/ETC · Benefits · Procurement"],
  ["Risk & RAID","Risks · Issues · Assumptions · Dependencies · Heat maps"],
  ["Resources","Capacity · Allocation · Utilisation · Timesheets"],
  ["Intelligence","EVM · Variance · Forecast · KPIs · Recommendations"],
  ["AI & Delivery","AI Copilot · AI code-gen · Build/QA/deploy pipeline"],
  ["Integrations","Webhooks · API keys · SSO · Jira · Board-pack export"],
];
caps.forEach((c,i)=>{ const x=0.7+(i%3)*4.05, y=1.95+Math.floor(i/3)*1.6; s.addShape(p.ShapeType.roundRect,{x,y,w:3.8,h:1.4,rectRadius:0.07,fill:{color:PANEL},line:{color:LINE,width:1}}); iconCircle(s,x+0.22,y+0.24,0.42,String(i+1),TEAL,WHITE); s.addText(c[0],{isTextBox:true,x:x+0.8,y:y+0.22,w:2.9,h:0.4,fontFace:TITLE_F,fontSize:13.5,bold:true,color:NAVY,valign:"middle"}); s.addText(c[1],{isTextBox:true,x:x+0.25,y:y+0.72,w:3.35,h:0.6,fontFace:BODY_F,fontSize:9.8,color:MUTE}); });
notes(s, "Nine capability groups spanning delivery, portfolio, governance, financials, risk, resources, intelligence, AI and integrations.");

/* 6 — Executive intelligence */
s = p.addSlide(); s.background = { color:WHITE };
eyebrow(s, "Executive intelligence"); title(s, "Health that is measured, not reported");
s.addText("The intelligence layer computes Earned Value across every project and rolls it up to program, portfolio and the whole transformation — with a plain-language executive briefing and prioritised recommendations.", { isTextBox:true, x:0.7, y:1.75, w:6.0, h:1.6, fontFace:BODY_F, fontSize:13.5, color:INK });
const il = [["Performance","SPI, CPI, health RAG per project & rollup"],["Forecast","Completion dates, slippage, cost overrun"],["Variance","Schedule / cost / budget, favourable vs adverse"],["Recommendations","Ranked actions with rationale"]];
il.forEach((c,i)=>{ const y=3.5+i*0.82; iconCircle(s,0.7,y,0.5,"✓",TEAL,WHITE); s.addText([{text:c[0]+"  ",options:{bold:true,color:NAVY}},{text:c[1],options:{color:MUTE}}],{isTextBox:true,x:1.35,y:y-0.02,w:5.4,h:0.55,fontFace:BODY_F,fontSize:12.5,valign:"middle"}); });
// simple native chart: SPI/CPI style — budget vs forecast columns
s.addShape(p.ShapeType.roundRect,{x:7.0,y:1.8,w:5.6,h:4.9,rectRadius:0.08,fill:{color:NAVY},line:{type:"none"}});
s.addText("Portfolio EVM (illustrative)",{isTextBox:true,x:7.3,y:2.0,w:5,h:0.4,fontFace:TITLE_F,fontSize:13,bold:true,color:MINT});
s.addChart(p.ChartType.bar,[
  { name:"USD (000s)", labels:["Budget","Earned","Actual","Forecast"], values:[530,320,263,459] },
], { x:7.2, y:2.5, w:5.2, h:4.0, barDir:"col", chartColors:[MINT], showValue:true, dataLabelPosition:"outEnd", dataLabelColor:"FFFFFF", dataLabelFontSize:10, showLegend:false, showTitle:false, catAxisLabelColor:"C3C2B7", valAxisLabelColor:"C3C2B7", valAxisHidden:true, valGridLine:{style:"none"}, catGridLine:{style:"none"} });
notes(s, "EVM turns raw project data into SPI/CPI, EAC/ETC and health, rolled up for executives. The chart illustrates budget vs earned vs actual vs forecast.");

/* 7 — Cost & budget control */
s = p.addSlide(); s.background = { color:PANEL };
eyebrow(s, "Cost & budget control"); title(s, "The money view, on the main dashboard");
const money = [["BAC","Budget at completion","the approved baseline"],["AC","Cost to date","actuals from the ledger"],["EAC","Forecast at completion","BAC × AC / EV"],["ETC","To complete","EAC − AC"],["VAC","Variance","under / over budget"]];
money.forEach((c,i)=>{ statCard(s, 0.7+i*2.44, 2.3, 2.2, c[0], c[1], c[2], c[0]==="VAC"?GREEN:TEAL); });
s.addText("Shown as headline tiles and as per-project columns (Budget · Cost · EAC · ETC) — with EAC flagged red wherever it exceeds budget. Available at transformation, portfolio and single-project scope.", { isTextBox:true, x:0.7, y:4.4, w:11.9, h:0.9, fontFace:BODY_F, fontSize:13.5, color:INK });
notes(s, "Cost, EAC, ETC and budget are first-class on the dashboard — reconciled with the executive narrative on the same EVM basis.");

/* 8 — Governance / stage gates */
s = p.addSlide(); s.background = { color:WHITE };
eyebrow(s, "Governance"); title(s, "Every project runs the SDLC gates");
const gates = ["Requirements","Design","Development","QA & Test","UAT","Go-Live"];
gates.forEach((g,i)=>{ const x=0.7+i*2.03; const done=i<3; s.addShape(p.ShapeType.ellipse,{x:x+0.55,y:2.6,w:0.7,h:0.7,fill:{color:done?GREEN:(i===3?AMBER:LINE)},line:{type:"none"}}); s.addText(done?"✓":(i===3?"●":String(i+1)),{isTextBox:true,x:x+0.55,y:2.58,w:0.7,h:0.7,align:"center",valign:"middle",fontFace:TITLE_F,fontSize:15,bold:true,color:done||i===3?WHITE:MUTE}); if(i<gates.length-1) s.addShape(p.ShapeType.line,{x:x+1.25,y:2.95,w:0.78,h:0,line:{color:i<3?GREEN:LINE,width:2}}); s.addText(g,{isTextBox:true,x:x-0.1,y:3.45,w:1.9,h:0.6,align:"center",fontFace:BODY_F,fontSize:11,bold:true,color:NAVY}); });
const gg = [["Recorded approvals","Every gate sign-off is captured with approver and date, and audited."],["Separation of duties","The approver must differ from the initiator — enforced by the engine."],["Portfolio roll-up","See gates approved, pending and awaiting your sign-off across all projects."]];
gg.forEach((c,i)=>{ const x=0.7+i*4.05; s.addShape(p.ShapeType.roundRect,{x,y:4.6,w:3.8,h:1.9,rectRadius:0.07,fill:{color:PANEL},line:{color:LINE,width:1}}); s.addText(c[0],{isTextBox:true,x:x+0.25,y:4.8,w:3.3,h:0.5,fontFace:TITLE_F,fontSize:13,bold:true,color:TEAL}); s.addText(c[1],{isTextBox:true,x:x+0.25,y:5.3,w:3.35,h:1.0,fontFace:BODY_F,fontSize:11,color:INK}); });
notes(s, "A canonical six-gate SDLC workflow governs each project, with recorded approvals, separation of duties, and a portfolio roll-up.");

/* 9 — Financial milestones */
s = p.addSlide(); s.background = { color:WHITE };
eyebrow(s, "Governed spend"); title(s, "Payments linked to accepted deliverables");
const flow = [["Submit","Deliverable submitted for acceptance"],["Review","Deliverable reviewed at the gate"],["Accept","Business accepts (different approver)"],["Release","Payment posts to the project ledger"]];
flow.forEach((c,i)=>{ const x=0.7+i*3.03; s.addShape(p.ShapeType.roundRect,{x,y:2.4,w:2.75,h:2.1,rectRadius:0.08,fill:{color:i===3?NAVY:PANEL},line:{color:LINE,width:1}}); iconCircle(s,x+0.25,2.65,0.5,String(i+1),i===3?MINT:TEAL,i===3?NAVY:WHITE); s.addText(c[0],{isTextBox:true,x:x+0.9,y:2.68,w:1.7,h:0.5,fontFace:TITLE_F,fontSize:15,bold:true,color:i===3?MINT:NAVY,valign:"middle"}); s.addText(c[1],{isTextBox:true,x:x+0.25,y:3.35,w:2.3,h:1.0,fontFace:BODY_F,fontSize:11,color:i===3?"E6EAF0":INK}); if(i<3) s.addText("→",{isTextBox:true,x:x+2.72,y:3.0,w:0.35,h:0.6,align:"center",fontFace:TITLE_F,fontSize:20,bold:true,color:TEAL}); });
s.addText("A financial milestone names its deliverable and the payment it releases. The payment cannot be released until the deliverable is accepted at the gate — so spend always follows verified value, and posts straight to the cost ledger.", { isTextBox:true, x:0.7, y:5.0, w:11.9, h:1.1, fontFace:BODY_F, fontSize:13.5, color:INK });
notes(s, "Financial milestones tie money to deliverables: submit → review → accept → release, with the release posting an actual to the ledger.");

/* 10 — Per-project KPIs */
s = p.addSlide(); s.background = { color:PANEL };
eyebrow(s, "Focus on one project"); title(s, "A scorecard for every project");
s.addText("Select any project and the dashboard refocuses to it — its EVM, cost, benefits and a KPI scorecard. Each project carries its own KPI register: baseline, current and target, with live attainment and on/off-track status.", { isTextBox:true, x:0.7, y:1.8, w:6.0, h:1.8, fontFace:BODY_F, fontSize:13.5, color:INK });
const kp = [["Own KPI register","Define KPIs per project, higher- or lower-is-better"],["Live attainment","Progress from baseline to target, on/off-track"],["Manage in place","Add, update values and remove from the workspace"]];
kp.forEach((c,i)=>{ const y=3.7+i*0.95; iconCircle(s,0.7,y,0.5,"✓",TEAL,WHITE); s.addText([{text:c[0]+"  ",options:{bold:true,color:NAVY}},{text:c[1],options:{color:MUTE}}],{isTextBox:true,x:1.35,y:y-0.02,w:5.3,h:0.7,fontFace:BODY_F,fontSize:12.5,valign:"middle"}); });
// mock scorecard cards
const sc = [["CSAT","4.1 / 4.5","69%",AMBER],["Coverage","82 / 85 %","94%",GREEN],["MTTR","45 / 30 min","62%",AMBER],["Adoption","68 / 80 %","85%",GREEN]];
sc.forEach((c,i)=>{ const x=7.0+(i%2)*2.9, y=1.9+Math.floor(i/2)*2.35; s.addShape(p.ShapeType.roundRect,{x,y,w:2.7,h:2.1,rectRadius:0.08,fill:{color:WHITE},line:{color:LINE,width:1},shadow:{type:"outer",color:"9AA5B1",blur:5,offset:2,angle:90,opacity:0.2}}); s.addText(c[0],{isTextBox:true,x:x+0.2,y:y+0.18,w:2.3,h:0.35,fontFace:TITLE_F,fontSize:12.5,bold:true,color:NAVY}); s.addText(c[1],{isTextBox:true,x:x+0.2,y:y+0.6,w:2.3,h:0.5,fontFace:TITLE_F,fontSize:20,bold:true,color:INK}); s.addShape(p.ShapeType.roundRect,{x:x+0.2,y:y+1.35,w:2.3,h:0.16,rectRadius:0.08,fill:{color:"E7ECF2"},line:{type:"none"}}); s.addShape(p.ShapeType.roundRect,{x:x+0.2,y:y+1.35,w:2.3*parseInt(c[2])/100,h:0.16,rectRadius:0.08,fill:{color:c[3]},line:{type:"none"}}); s.addText(c[2]+" attained",{isTextBox:true,x:x+0.2,y:y+1.6,w:2.3,h:0.3,fontFace:BODY_F,fontSize:9.5,color:MUTE}); });
notes(s, "Per-project KPI scorecards give delivery leads a focused view while executives keep the rollup.");

/* 11 — AI delivery */
s = p.addSlide(); s.background = { color:WHITE };
eyebrow(s, "AI delivery"); title(s, "From spec to deployed, with a quality gate");
const pipe = ["Generate","Build","Unit test","QA review","Deploy","Perf test"];
pipe.forEach((g,i)=>{ const x=0.7+i*2.03; s.addShape(p.ShapeType.roundRect,{x,y:2.6,w:1.8,h:0.9,rectRadius:0.1,fill:{color:i%2?NAVY:TEAL},line:{type:"none"}}); s.addText(g,{isTextBox:true,x,y:2.6,w:1.8,h:0.9,align:"center",valign:"middle",fontFace:TITLE_F,fontSize:12,bold:true,color:WHITE}); if(i<pipe.length-1) s.addText("→",{isTextBox:true,x:x+1.8,y:2.6,w:0.23,h:0.9,align:"center",valign:"middle",fontFace:TITLE_F,fontSize:18,bold:true,color:MUTE}); });
const ai = [["AI code generation","Scaffold and generate across 50+ technology stacks from a spec."],["Quality gate","Coverage, performance and passing tests are enforced before deploy."],["CI reporters","GitHub Actions, GitLab CI and Jenkins reporters included."]];
ai.forEach((c,i)=>{ const x=0.7+i*4.05, y=4.1; s.addShape(p.ShapeType.roundRect,{x,y,w:3.8,h:2.2,rectRadius:0.07,fill:{color:PANEL},line:{color:LINE,width:1}}); iconCircle(s,x+0.25,y+0.25,0.5,String(i+1),TEAL,WHITE); s.addText(c[0],{isTextBox:true,x:x+0.9,y:4.28,w:2.8,h:0.5,fontFace:TITLE_F,fontSize:13,bold:true,color:NAVY,valign:"middle"}); s.addText(c[1],{isTextBox:true,x:x+0.25,y:4.95,w:3.35,h:1.2,fontFace:BODY_F,fontSize:11,color:INK}); });
notes(s, "ETIP includes an AI-assisted delivery pipeline that generates, builds, tests, QA-checks and deploys — gated on quality thresholds.");

/* 12 — Architecture & security */
s = p.addSlide(); s.background = { color:PANEL };
eyebrow(s, "Architecture & security"); title(s, "Built to enterprise standards");
const arch = [
  ["Clean architecture","Presentation → API → Service → Repository → Database, with dependency injection and the unit-of-work pattern."],
  ["Multi-tenancy","Organizations with departments, business units, roles and strict data isolation."],
  ["Security","RBAC + permissions, JWT with refresh tokens, password hashing, rate limiting, security headers, OWASP-aware."],
  ["Auditability","Every row: UUID key, created/modified by & date, soft-delete, version and an audit trail."],
];
arch.forEach((c,i)=>{ const x=0.7+(i%2)*6.1, y=2.0+Math.floor(i/2)*2.25; featureCard(s, x, y, 5.75, 2.0, String(i+1), c[0], c[1]); });
notes(s, "Clean layering, multi-tenancy, defense-in-depth security and full auditability are foundational, not add-ons.");

/* 13 — Integrations */
s = p.addSlide(); s.background = { color:WHITE };
eyebrow(s, "Fits your stack"); title(s, "Open, connected, exportable");
const integ = [["Webhooks","Outbound events with a delivery outbox & retries"],["API keys","Programmatic access with scoped keys"],["SSO","Enterprise single sign-on configuration"],["Jira","Connector for issues & delivery data"],["Board packs","One-click XLSX & PDF executive packs"],["Open API","OpenAPI / Swagger for every endpoint"]];
integ.forEach((c,i)=>{ const x=0.7+(i%3)*4.05, y=2.1+Math.floor(i/3)*2.15; s.addShape(p.ShapeType.roundRect,{x,y,w:3.8,h:1.9,rectRadius:0.07,fill:{color:PANEL},line:{color:LINE,width:1}}); iconCircle(s,x+0.25,y+0.25,0.5,String(i+1),TEAL,WHITE); s.addText(c[0],{isTextBox:true,x:x+0.9,y:y+0.28,w:2.8,h:0.5,fontFace:TITLE_F,fontSize:13.5,bold:true,color:NAVY,valign:"middle"}); s.addText(c[1],{isTextBox:true,x:x+0.25,y:y+0.95,w:3.35,h:0.8,fontFace:BODY_F,fontSize:11,color:INK}); });
notes(s, "ETIP integrates through webhooks, API keys, SSO and Jira, and exports board-ready packs.");

/* 14 — Close */
s = p.addSlide(); bgDark(s);
s.addText("Plan. Execute. Govern. Transform.", { isTextBox:true, x:0.8, y:2.5, w:11.7, h:0.9, fontFace:TITLE_F, fontSize:34, bold:true, color:WHITE });
s.addText("One governed source of truth for your transformation — measured with Earned Value, controlled at every gate, and ready to run today.", { isTextBox:true, x:0.8, y:3.5, w:11.0, h:1.0, fontFace:BODY_F, fontSize:16, color:"C3C2B7" });
const cta = ["Run it in one command — ./run.sh","Sign in and explore the seeded demo","Test every feature with the included guide"];
cta.forEach((t,i)=>{ const y=4.7+i*0.55; iconCircle(s,0.85,y,0.4,"✓",TEAL,WHITE); s.addText(t,{isTextBox:true,x:1.4,y:y-0.05,w:10.5,h:0.5,fontFace:BODY_F,fontSize:14,bold:true,color:"E6EAF0",valign:"middle"}); });
notes(s, "Call to action: install in one command, explore the demo, and validate with the test guide.");

p.writeFile({ fileName: "/home/claude/etip/ETIP_Executive_Overview.pptx" }).then(f=>console.log("wrote", f));
