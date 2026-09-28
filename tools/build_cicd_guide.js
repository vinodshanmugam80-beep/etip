// ETIP — Running CI/CD, beginner guide (.docx)
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType, PageBreak, LevelFormat,
} = require("docx");

const NAVY = "0F1B2D", ACCENT = "0E9488", INK = "101828", MUTE = "667085", LINE = "D8DEE7";
const CW = 9360;

const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 300, after: 120 }, children: [new TextRun({ text: t, bold: true, color: NAVY, size: 30 })] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 200, after: 80 }, children: [new TextRun({ text: t, bold: true, color: ACCENT, size: 23 })] });
const P = (t) => new Paragraph({ spacing: { after: 100 }, children: Array.isArray(t) ? t : [new TextRun({ text: t, size: 21, color: INK })] });
const MUTED = (t) => new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: "Tip: " + t, size: 19, color: MUTE, italics: true })] });
const WARN = (t) => new Paragraph({ spacing: { after: 120 }, shading: { type: ShadingType.CLEAR, fill: "FFF7ED" }, children: [new TextRun({ text: "Note: " + t, size: 19, color: "9A3412" })] });
const OK = (t) => new Paragraph({ spacing: { after: 120 }, shading: { type: ShadingType.CLEAR, fill: "ECFDF3" }, children: [new TextRun({ text: "What success looks like: " + t, size: 19, color: "067647" })] });
const CODE = (t) => new Paragraph({ spacing: { after: 40 }, shading: { type: ShadingType.CLEAR, fill: "F2F4F7" }, children: [new TextRun({ text: t, font: "Consolas", size: 18, color: "0B3B36" })] });
let inst = 0;
const reset = () => { inst++; };
const step = (t) => new Paragraph({ numbering: { reference: "nl", level: 0, instance: inst }, spacing: { after: 70 }, children: Array.isArray(t) ? t : [new TextRun({ text: t, size: 21, color: INK })] });
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
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 }, children: [new TextRun({ text: "Running CI/CD — a beginner's guide", bold: true, color: NAVY, size: 28 })] }));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 500 }, children: [new TextRun({ text: "No prior experience assumed. Copy, paste, and read the results.", italics: true, color: MUTE, size: 20 })] }));
c.push(new Paragraph({ children: [new PageBreak()] }));

// 1. What is CI/CD
c.push(H1("1. What is CI/CD, in plain English"));
c.push(P([b("CI"), tx(" (Continuous Integration) means: every time the code changes, a set of automatic checks runs to prove the software is still healthy — the code is tidy, the types line up, the database sets up cleanly, and all the tests pass. "), b("CD"), tx(" (Continuous Delivery) means: once those checks pass, the software is automatically packaged (here, into a Docker image) ready to deploy.")]));
c.push(P("ETIP already comes with a CI/CD pipeline defined. This guide shows you how to run it. Here is what it checks:"));
c.push(table(["Stage", "What it does", "Why it matters"], [
  ["Lint", "Checks the code style is clean and consistent (ruff).", "Catches sloppy or broken code early."],
  ["Format", "Checks the code is formatted to the standard.", "Keeps the codebase uniform."],
  ["Type check", "Verifies data types line up (mypy).", "Prevents a whole class of bugs."],
  ["Migrations", "Builds the database from scratch.", "Proves a fresh install works."],
  ["Tests", "Runs 400+ automated tests and requires 85% coverage.", "Proves features actually work."],
  ["Build image", "Packages ETIP into a Docker image (on the main branch).", "The deployable artifact (the CD step)."],
], [1700, 4400, 3260]));
c.push(P([b("You have two ways to run it"), tx(", explained below. If you just want to see the checks pass, do "), b("Option A"), tx(" — it runs on your own computer and needs no accounts. "), b("Option B"), tx(" runs the same pipeline automatically on GitHub every time you save changes — that's the real CI/CD.")]));

// 2. Option A — local
c.push(H1("2. Option A — Run the checks on your own computer"));
c.push(P("This reproduces exactly what the automated pipeline does, on your machine. Best for a first look."));
c.push(H2("2.1  Install the one thing you need: Python"));
reset();
c.push(step([tx("Check if you already have it. Open a "), b("terminal"), tx(" (macOS: “Terminal” app; Windows: “PowerShell”) and type "), mono("python3 --version"), tx(" (Windows: "), mono("python --version"), tx(") and press Enter.")]));
c.push(step([tx("If it prints a version 3.11 or higher, skip to 2.2. If not, download it from "), mono("https://www.python.org/downloads/"), tx(", run the installer, and on Windows tick "), b("“Add Python to PATH”"), tx(" during install.")]));
c.push(H2("2.2  Get the ETIP project onto your computer"));
reset();
c.push(step([tx("Unzip "), mono("etip.zip"), tx(" (right-click → Extract All / Unzip). You'll get a folder named "), mono("etip"), tx(".")]));
c.push(step([tx("In your terminal, move into that folder. Type "), mono("cd "), tx("(with a space), then drag the "), mono("etip"), tx(" folder onto the terminal window (it pastes the path), and press Enter.")]));
c.push(MUTED("Every command from here on is run from inside the etip folder."));
c.push(H2("2.3  Set up the project (one time)"));
reset();
c.push(step("Create an isolated workspace for the project's tools (a “virtual environment”):"));
c.push(CODE("python3 -m venv .venv                 # Windows: python -m venv .venv"));
c.push(step("Turn it on:"));
c.push(CODE("source .venv/bin/activate             # Windows: .venv\\Scripts\\activate"));
c.push(step([tx("Install ETIP plus the CI tools (this may take a few minutes):")]));
c.push(CODE('pip install -e ".[dev]"'));
c.push(OK("The commands finish without a red “ERROR”. Your prompt now shows (.venv) at the start."));
c.push(H2("2.4  Run the pipeline checks, one by one"));
c.push(P("Run these five commands in order. Each prints its result; a line like “All checks passed!” or “passed” means that stage is green."));
reset();
c.push(step([b("Lint"), tx(" — tidy code check:")]));
c.push(CODE("ruff check app tests"));
c.push(step([b("Format"), tx(" — formatting check:")]));
c.push(CODE("ruff format --check app tests"));
c.push(step([b("Type check"), tx(" — data types line up:")]));
c.push(CODE("mypy app"));
c.push(step([b("Migrations"), tx(" — build the database from scratch:")]));
c.push(CODE("alembic upgrade head"));
c.push(step([b("Tests + coverage gate"), tx(" — run all tests, require 85% coverage:")]));
c.push(CODE("pytest --cov=app --cov-report=term-missing --cov-fail-under=85"));
c.push(OK("The last command ends with a green summary like “420 passed” and “Required test coverage of 85% reached”. If you see that, you have successfully run the CI pipeline."));
c.push(WARN("The tests take a few minutes. Let the last command finish — don't close the window."));
c.push(H2("2.5  (Optional) Build the deployable image — the CD step"));
c.push(P([tx("If you have "), b("Docker Desktop"), tx(" installed (from "), mono("https://www.docker.com/products/docker-desktop/"), tx("), you can build the same package the pipeline builds:")]));
c.push(CODE("docker build -t etip:local ."));
c.push(OK("It ends with “naming to docker.io/library/etip:local”. That image is what gets deployed."));

// 3. Option B — GitHub
c.push(H1("3. Option B — Run it automatically on GitHub"));
c.push(P("This is the real CI/CD: GitHub runs the whole pipeline for you, in the cloud, every time you save changes — and shows a green tick or red cross. One-time setup, then it's automatic forever."));
c.push(H2("3.1  Create a free GitHub account and install Git"));
reset();
c.push(step([tx("Sign up at "), mono("https://github.com"), tx(" (free).")]));
c.push(step([tx("Install Git (the tool that uploads code) from "), mono("https://git-scm.com/downloads"), tx(". Accept the defaults.")]));
c.push(H2("3.2  Create an empty repository on GitHub"));
reset();
c.push(step([tx("On GitHub, click the "), b("+"), tx(" top-right → "), b("New repository"), tx(".")]));
c.push(step([tx("Give it a name (e.g. "), mono("etip"), tx("), leave everything else default, click "), b("Create repository"), tx(".")]));
c.push(step("On the next page, copy the web address shown (it ends in .git) — you'll paste it below."));
c.push(H2("3.3  Upload the project (one time)"));
c.push(P("In your terminal, inside the etip folder, run these — replacing the address in the 4th line with the one you copied:"));
reset();
c.push(CODE('git init'));
c.push(CODE('git add .'));
c.push(CODE('git commit -m "ETIP first upload"'));
c.push(CODE('git branch -M main'));
c.push(CODE('git remote add origin https://github.com/<your-name>/etip.git'));
c.push(CODE('git push -u origin main'));
c.push(step([tx("Git may ask you to sign in the first time — follow the browser prompt and click "), b("Authorize"), tx(".")]));
c.push(OK("The last command uploads the files and prints “branch 'main' set up to track…”. Your code is now on GitHub."));
c.push(H2("3.4  Watch the pipeline run"));
reset();
c.push(step([tx("Open your repository page on GitHub and click the "), b("Actions"), tx(" tab at the top.")]));
c.push(step([tx("You'll see a run named after your commit (“ETIP first upload”) with a spinning yellow dot — it's running. Click it.")]));
c.push(step([tx("You'll see two jobs: "), b("quality-and-tests"), tx(" (lint, types, migrations, tests) and "), b("build-image"), tx(" (packages ETIP). Click either to watch the live logs.")]));
c.push(step([tx("When done, a "), b("green tick"), tx(" means everything passed. A "), b("red cross"), tx(" means a stage failed — click it to read which line failed.")]));
c.push(OK("A green tick on the Actions run. From now on, every time you push a change, this runs automatically."));
c.push(H2("3.5  Making a change and seeing CI re-run"));
c.push(P("To see CI/CD react to a change, edit any file, then in the terminal:"));
c.push(CODE('git add .'));
c.push(CODE('git commit -m "a small change"'));
c.push(CODE('git push'));
c.push(P("Refresh the Actions tab — a new run starts on its own. That is continuous integration in action."));

// 4. Understanding results
c.push(H1("4. Understanding the results"));
c.push(...bullets([
  [b("Green / “passed” / tick"), tx(" — that stage is healthy.")],
  [b("Red / “failed” / cross"), tx(" — something needs fixing; the log names the file and line.")],
  [b("Coverage gate"), tx(" — the tests must cover at least 85% of the code, or the tests stage fails on purpose.")],
  [b("build-image only on main"), tx(" — the packaging (CD) step runs only for the main branch, after tests pass.")],
]));

// 5. Troubleshooting
c.push(H1("5. Troubleshooting"));
c.push(table(["Message you see", "What to do"], [
  ["command not found: python3", "Use python instead of python3 (Windows), or reinstall Python and tick “Add to PATH”."],
  ["command not found: ruff / pytest / mypy", "The venv isn't active or deps aren't installed. Re-run the activate line, then pip install -e \".[dev]\"."],
  ["'.venv' activate fails on Windows", "Run in PowerShell: .venv\\Scripts\\Activate.ps1 (if blocked, run PowerShell as admin once: Set-ExecutionPolicy RemoteSigned)."],
  ["pytest says coverage below 85%", "A test or file changed. Read which lines are missing in the report; on a fresh unzip this should pass as-is."],
  ["git push asks for a password", "Use the browser sign-in it offers, or a GitHub personal access token instead of your account password."],
  ["Actions tab shows nothing", "Make sure the push succeeded and that .github/workflows/ci.yml exists in the repo."],
], [3400, 5960]));

// 6. Appendix
c.push(H1("6. A different “CI/CD”: reporting your app's pipeline to ETIP"));
c.push(P([tx("The steps above run "), b("ETIP's own"), tx(" build pipeline. Separately, ETIP can receive results from "), b("your application's"), tx(" pipeline into its AI-Delivery module (so a build's status and metrics show up inside ETIP). That is a different feature — its steps are in "), b("Guide 4 of the ETIP Integration Guides"), tx(" (set ETIP_URL, ETIP_API_KEY, ETIP_BUILD_ID, then the pipeline calls scripts/etip_report.py).")]));

const doc = new Document({
  creator: "ETIP", title: "ETIP — Running CI/CD (beginner guide)",
  numbering: { config: [
    { reference: "bl", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 240 } } } }] },
    { reference: "nl", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 240 } } } }] },
  ] },
  styles: { default: { document: { run: { font: "Calibri", size: 21, color: INK } } } },
  sections: [{ properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } }, children: c }],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync("/home/claude/etip/ETIP_Running_CICD_Guide.docx", buf); console.log("wrote ETIP_Running_CICD_Guide.docx"); });
