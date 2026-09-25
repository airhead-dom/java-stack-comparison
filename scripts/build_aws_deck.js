// Builds docs/virtual-threads-technical-aws.pptx from the AWS run.
//
//   NODE_PATH=/tmp/deckbuild/node_modules node scripts/build_aws_deck.js
//
// Every figure here is a median of the two repetitions in results/raw/, as
// reported by results/analysis/aws-run.md. Writes only the -aws file; the
// hand-edited virtual-threads-technical.pptx is never touched.

const pptxgen = require("pptxgenjs");

const OUT = "docs/virtual-threads-technical-aws.pptx";

// Series colours, validated as a set for colour-vision deficiency.
const CURRENT = "0072B2";    // webflux-r2dbc, today
const CANDIDATE = "009E73";  // mvc-virtual, the candidate
const REFERENCE = "D55E00";  // mvc-platform, reference only

const INK = "1F2933", MUTED = "5C6B77", DARK = "1F2933", DARKMID = "3E4C59";
const WHITE = "FFFFFF", CARD = "F2F5F7", RULE = "D9E0E6";
const H = "Cambria", B = "Calibri", M = "Courier New";
const MX = 0.65, CW = 13.3 - MX * 2;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "WebFlux vs Virtual Threads - AWS run";

function titled(s, title, kicker) {
  s.background = { color: WHITE };
  if (kicker) s.addText(kicker.toUpperCase(), {
    x: MX, y: 0.38, w: CW, h: 0.26, isTextBox: true,
    fontFace: B, fontSize: 11, bold: true, color: MUTED, charSpacing: 1.6, margin: 0,
  });
  s.addText(title, {
    x: MX, y: kicker ? 0.66 : 0.5, w: CW, h: 0.8, isTextBox: true,
    fontFace: H, fontSize: 29, bold: true, color: INK, margin: 0,
  });
  return kicker ? 1.55 : 1.4;
}

function chip(s, x, y, color, label, o = {}) {
  s.addShape(pres.ShapeType.ellipse, { x, y: y + 0.045, w: 0.16, h: 0.16, fill: { color } });
  s.addText(label, {
    x: x + 0.26, y, w: o.w || 2.6, h: 0.26, isTextBox: true,
    fontFace: B, fontSize: o.fontSize || 13, bold: !!o.bold, color: o.color || INK, margin: 0,
  });
}

function table(s, head, rows, x, y, colW, opts = {}) {
  const headRow = head.map((t, i) => ({
    text: t, options: { bold: true, align: i ? "right" : "left",
                        color: (opts.headColors && opts.headColors[i]) || INK },
  }));
  const body = rows.map(r => r.map((c, i) => ({
    text: String(c), options: { align: i ? "right" : "left", color: i ? MUTED : INK },
  })));
  s.addTable([headRow, ...body], {
    x, y, w: colW.reduce((a, b) => a + b, 0), colW,
    fontFace: B, fontSize: opts.fontSize || 12, color: INK, rowH: opts.rowH || 0.32,
    border: { type: "solid", color: RULE, pt: 1 }, fill: { color: WHITE },
  });
}

function chartOpts(extra) {
  return Object.assign({
    showLegend: true, legendPos: "b", legendFontFace: B, legendFontSize: 11, legendColor: MUTED,
    catAxisLabelFontFace: B, catAxisLabelFontSize: 12, catAxisLabelColor: INK,
    valAxisLabelFontFace: B, valAxisLabelFontSize: 11, valAxisLabelColor: MUTED,
    catGridLine: { style: "none" }, valGridLine: { color: RULE, size: 1 },
    catAxisLineShow: false, valAxisLineShow: false,
    showValue: true, dataLabelFontFace: B, dataLabelFontSize: 10,
    dataLabelColor: INK, dataLabelPosition: "outEnd",
    barGapWidthPct: 45, barDir: "col",
    chartColors: [CURRENT, CANDIDATE, REFERENCE],
    titleFontFace: B, titleFontSize: 13, titleColor: MUTED, showTitle: true,
  }, extra);
}

/* --------------------------------------------------------------- 1 title */
{
  const s = pres.addSlide();
  s.background = { color: DARK };
  s.addText("WebFlux → Virtual Threads", {
    x: MX, y: 2.2, w: 11, h: 0.95, isTextBox: true,
    fontFace: H, fontSize: 42, bold: true, color: WHITE, margin: 0,
  });
  s.addText("Results from the three-machine AWS run", {
    x: MX, y: 3.2, w: 11, h: 0.5, isTextBox: true,
    fontFace: B, fontSize: 19, color: "B9C4CC", margin: 0,
  });
  s.addText("120 cells · 3 builds × 5 workloads × 4 rates × 2 repetitions", {
    x: MX, y: 4.3, w: 11, h: 0.35, isTextBox: true,
    fontFace: B, fontSize: 14, color: "8896A2", margin: 0,
  });
  s.addText("21 September 2026  ·  OpenJDK 25.0.4  ·  Spring Boot 4.1.1  ·  PostgreSQL 17  ·  k6 v2.2.0", {
    x: MX, y: 6.5, w: CW, h: 0.3, isTextBox: true,
    fontFace: B, fontSize: 12, color: "8896A2", margin: 0,
  });
  s.addNotes("These supersede the laptop numbers. One finding from that run is reversed here, "
    + "and one could not be measured at all.");
}

/* -------------------------------------------------------- 2 architecture */
{
  const s = pres.addSlide();
  const y0 = titled(s, "How the test machines were arranged", "Test architecture");

  const boxW = 3.5, gap = 0.85, top = y0 + 0.15;
  const boxes = [
    { c: MUTED, t: "Load generator", sub: "k6", lines: ["Offers a fixed rate whether", "or not the system keeps up", "Never the bottleneck"] },
    { c: CANDIDATE, t: "System under test", sub: "c7i.large · 2 vCPU · 4 GB", lines: ["One build at a time on :8080", "-Xmx1g, G1, pool of 20", "The only thing measured"] },
    { c: CURRENT, t: "Backend", sub: "PostgreSQL 17 + stub", lines: ["Database on its own CPUs", "Stub returns after 200 ms", "Never competes with the app"] },
  ];
  boxes.forEach((bx, i) => {
    const x = MX + i * (boxW + gap);
    s.addShape(pres.ShapeType.roundRect, {
      x, y: top, w: boxW, h: 2.5, fill: { color: CARD }, rectRadius: 0.08, line: { color: CARD },
    });
    s.addShape(pres.ShapeType.ellipse, { x: x + 0.3, y: top + 0.28, w: 0.3, h: 0.3, fill: { color: bx.c } });
    s.addText(bx.t, {
      x: x + 0.3, y: top + 0.7, w: boxW - 0.6, h: 0.32, isTextBox: true,
      fontFace: H, fontSize: 17, bold: true, color: INK, margin: 0,
    });
    s.addText(bx.sub, {
      x: x + 0.3, y: top + 1.03, w: boxW - 0.6, h: 0.28, isTextBox: true,
      fontFace: M, fontSize: 11, color: MUTED, margin: 0,
    });
    s.addText(bx.lines.map((t, j) => ({ text: t, options: { breakLine: j < bx.lines.length - 1 } })), {
      x: x + 0.3, y: top + 1.38, w: boxW - 0.55, h: 1.0, isTextBox: true,
      fontFace: B, fontSize: 12, color: MUTED, margin: 0,
    });
    if (i < 2) {
      s.addText("→", {
        x: x + boxW + 0.08, y: top + 0.95, w: gap - 0.16, h: 0.4, isTextBox: true,
        fontFace: B, fontSize: 22, color: RULE, align: "center", margin: 0,
      });
    }
  });

  s.addText("Why each separation matters", {
    x: MX, y: top + 2.85, w: CW, h: 0.32, isTextBox: true,
    fontFace: B, fontSize: 15, bold: true, color: INK, margin: 0,
  });
  const reasons = [
    ["Generator on its own machine", "On the laptop run it competed with the application for CPU and the same cell gave different answers between attempts."],
    ["Database on its own machine", "A database sharing the application's cores makes every result a measurement of the machine rather than the stack."],
    ["One availability zone", "Cross-zone adds latency with real variance. Availability is irrelevant here; consistency is everything."],
    ["Only 2 vCPU under test", "Deliberately small. A thread model only shows itself when something is scarce."],
  ];
  reasons.forEach((r, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = MX + col * 6.2, y = top + 3.25 + row * 0.85;
    s.addText(r[0], {
      x, y, w: 5.8, h: 0.28, isTextBox: true,
      fontFace: B, fontSize: 13, bold: true, color: INK, margin: 0,
    });
    s.addText(r[1], {
      x, y: y + 0.28, w: 5.8, h: 0.52, isTextBox: true,
      fontFace: B, fontSize: 12, color: MUTED, margin: 0,
    });
  });
  s.addText("The system under test is a c7i.large: 2 vCPU, x86_64, 4 GB. Compute-optimised and "
    + "non-burstable, so it cannot be throttled mid-run the way a t-family instance can. Its telemetry "
    + "agrees independently — system_cpu_count reports 2, heap max 1 GB, OpenJDK 25.0.4 on Ubuntu, "
    + "pool of 20 on both the JDBC and R2DBC sides.", {
    x: MX, y: top + 4.98, w: CW, h: 0.6, isTextBox: true,
    fontFace: B, fontSize: 12, color: MUTED, margin: 0,
  });
  s.addNotes("CPU is the binding resource on this box, not memory: a 1 GB heap plus metaspace, code cache "
    + "and thread stacks sits comfortably inside 4 GB even for the platform-thread build running ~290 "
    + "threads. Nothing in the run was memory-constrained. The load generator and backend specs were not "
    + "recorded; only the system under test is characterised here, which is the one that matters.");
}

/* ------------------------------------------------------------ 3 builds */
{
  const s = pres.addSlide();
  const y0 = titled(s, "Three builds, one variable each", "What was built");
  const rows = [
    ["webflux-r2dbc", "Current stack. Netty, Spring Data R2DBC, r2dbc-postgresql, WebClient.", CURRENT],
    ["mvc-virtual", "Candidate. Tomcat, Spring Data JDBC, JDBC driver, RestClient, virtual threads on.", CANDIDATE],
    ["mvc-platform", "Reference. Byte-identical to mvc-virtual; virtual threads off.", REFERENCE],
  ];
  rows.forEach((r, i) => {
    const y = y0 + 0.25 + i * 1.15;
    chip(s, MX, y, r[2], r[0], { bold: true, w: 3.0, fontSize: 15 });
    s.addText(r[1], {
      x: MX + 3.4, y, w: CW - 3.4, h: 0.75, isTextBox: true,
      fontFace: B, fontSize: 14, color: MUTED, margin: 0,
    });
  });
  s.addText("mvc-virtual and mvc-platform share a byte-identical dependency list and controller, verified "
    + "with diff. The entire difference between them is three lines of YAML, so any gap is the thread model "
    + "and nothing else.", {
    x: MX, y: y0 + 3.9, w: CW, h: 0.8, isTextBox: true,
    fontFace: B, fontSize: 14, color: INK, margin: 0,
  });
}

/* --------------------------------------------------------- 4 workloads */
{
  const s = pres.addSlide();
  const y0 = titled(s, "Five workloads, each isolating one constraint", "Workload design");
  table(s,
    ["Endpoint", "Work", "Conn. held", "Latency", "What constrains it"],
    [
      ["/nodb", "Constant response", "—", "~0.1 ms", "nothing on this ladder"],
      ["/db", "One indexed query", "< 1 ms", "~0.5 ms", "nothing on this ladder"],
      ["/db-heavy", "Aggregate + 20 rows, padded", "11.96 ms", "~13 ms", "pool, ~1,670 rps"],
      ["/db-slow", "Query + pg_sleep(0.1)", "101.8 ms", "~100 ms", "pool, ~197 rps"],
      ["/api", "One 200 ms upstream call", "—", "~200 ms", "threads, ~1,000 rps"],
    ],
    MX, y0, [1.7, 3.5, 1.9, 1.7, 3.2], { rowH: 0.4, fontSize: 13 });

  s.addText("/api is the decisive workload. It touches no database, so nothing the connection pool does can "
    + "explain what happens there — each request simply holds a thread for 200 ms.", {
    x: MX, y: y0 + 2.6, w: CW, h: 0.6, isTextBox: true,
    fontFace: B, fontSize: 14, color: INK, margin: 0,
  });
  s.addText("Two knees moved from the figures the ladder was designed around. /db-heavy was planned at "
    + "~1,387 rps from a locally measured 14.4 ms hold; on AWS the hold is 11.96 ms, putting the knee at "
    + "~1,670 — which is where the data actually breaks. /db and /nodb never bind at any rate tested, so "
    + "they serve as controls rather than measurements.", {
    x: MX, y: y0 + 3.3, w: CW, h: 1.1, isTextBox: true,
    fontFace: B, fontSize: 13, color: MUTED, margin: 0,
  });
}

/* ------------------------------------------------------------ 5 sizing */
{
  const s = pres.addSlide();
  const y0 = titled(s, "Sizing the experiment", "Method");
  s.addText("Connection pool", {
    x: MX, y: y0, w: 5.8, h: 0.32, isTextBox: true,
    fontFace: B, fontSize: 16, bold: true, color: INK, margin: 0,
  });
  s.addText(
    "ceiling = pool size / hold time\n\n"
    + "/db-heavy  20 / 0.012 s = 1,670 rps\n"
    + "/db-slow   20 / 0.102 s =   197 rps\n"
    + "/db        20 / 0.000x s = no limit", {
    x: MX, y: y0 + 0.42, w: 5.8, h: 1.7, isTextBox: true,
    fontFace: M, fontSize: 13, color: INK, margin: 0, lineSpacingMultiple: 1.25,
  });
  const x2 = MX + 6.2;
  s.addText("Requests in flight", {
    x: x2, y: y0, w: 5.8, h: 0.32, isTextBox: true,
    fontFace: B, fontSize: 16, bold: true, color: INK, margin: 0,
  });
  s.addText(
    "in flight = rate x latency\n\n"
    + "/api    500 x 0.20 s =  100\n"
    + "/api  1,000 x 0.20 s =  200\n"
    + "/api  1,500 x 0.20 s =  300", {
    x: x2, y: y0 + 0.42, w: 5.8, h: 1.7, isTextBox: true,
    fontFace: M, fontSize: 13, color: INK, margin: 0, lineSpacingMultiple: 1.25,
  });
  s.addText("Tomcat's default is 200 threads. That is why /api at 1,000 rps is the edge and the database "
    + "workloads are not — they never put enough requests in flight for the thread model to matter.", {
    x: MX, y: y0 + 2.35, w: CW, h: 0.6, isTextBox: true,
    fontFace: B, fontSize: 14, color: INK, margin: 0,
  });
  s.addText("Load was offered open-model at a fixed arrival rate, 60 s warmup discarded and 60 s measured. "
    + "A closed-loop generator slows down when the system does, which hides the saturation behaviour being "
    + "measured. Cells where the generator itself could not sustain the rate are excluded — 15 of 120.", {
    x: MX, y: y0 + 3.05, w: CW, h: 0.9, isTextBox: true,
    fontFace: B, fontSize: 13, color: MUTED, margin: 0,
  });
}

/* ----------------------------------------------------------- 6 latency */
{
  const s = pres.addSlide();
  const y0 = titled(s, "Latency: the two candidates are almost identical", "Results");
  table(s,
    ["Workload", "Requests", "WebFlux", "Virtual threads", "Platform threads"],
    [
      ["/nodb @ 2,000 rps", "120,000", "0.1 ms", "0.1 ms", "0.1 ms"],
      ["/db @ 2,000 rps", "120,000", "0.5 ms", "0.5 ms", "0.4 ms"],
      ["/db-heavy @ 1,000 rps", "60,000", "12.7 ms", "12.4 ms", "12.4 ms"],
      ["/api @ 500 rps", "30,000", "200.9 ms", "200.9 ms", "200.9 ms"],
      ["/api @ 1,000 rps", "60,000", "200.6 ms", "200.6 ms", "668.0 ms"],
      ["/api @ 1,500 rps", "90,000", "200.5 ms", "200.6 ms", "1,000 ms · 100 %"],
      ["/api @ 2,000 rps", "120,000", "200.5 ms", "200.6 ms", "709.7 ms · 100 %"],
    ],
    MX, y0, [3.0, 1.6, 2.4, 2.5, 2.5],
    { rowH: 0.38, fontSize: 13, headColors: [INK, INK, CURRENT, CANDIDATE, REFERENCE] });
  s.addText("Median p50 of two repetitions. Requests is the measured 60-second window, offered rate x 60. "
    + "Where the error rate is high the figure is floored by the 1,000 ms client timeout, so it is a lower "
    + "bound on how bad it was — read the error rate first.", {
    x: MX, y: y0 + 3.2, w: CW, h: 0.55, isTextBox: true,
    fontFace: B, fontSize: 13, italic: true, color: MUTED, margin: 0,
  });
  s.addText("WebFlux and virtual threads are within 0.1 ms of each other on every workload and every rate "
    + "tested. Nothing in the latency data distinguishes them.", {
    x: MX, y: y0 + 3.85, w: CW, h: 0.6, isTextBox: true,
    fontFace: B, fontSize: 14, color: INK, margin: 0,
  });
}

/* ------------------------------------------------------- 7 /api ceiling */
{
  const s = pres.addSlide();
  const y0 = titled(s, "The thread ceiling: a knee, then a cliff", "Results · /api");
  s.addChart(pres.ChartType.bar, [
    { name: "WebFlux", labels: ["500 rps · 30k req", "1,000 rps · 60k req", "1,500 rps · 90k req", "2,000 rps · 120k req"], values: [200.9, 200.6, 200.5, 200.5] },
    { name: "Virtual threads", labels: ["500 rps · 30k req", "1,000 rps · 60k req", "1,500 rps · 90k req", "2,000 rps · 120k req"], values: [200.9, 200.6, 200.6, 200.6] },
    { name: "Platform threads", labels: ["500 rps · 30k req", "1,000 rps · 60k req", "1,500 rps · 90k req", "2,000 rps · 120k req"], values: [200.9, 668.0, 1000.0, 709.7] },
  ], chartOpts({
    x: MX, y: y0, w: 7.5, h: 4.3,
    title: "Median response time (ms) by offered rate",
  }));
  s.addText("Platform threads: 0 % errors at 1,000 rps, 100 % at 1,500", {
    x: MX + 7.9, y: y0 + 0.05, w: 4.1, h: 0.6, isTextBox: true,
    fontFace: H, fontSize: 17, bold: true, color: INK, margin: 0,
  });
  s.addText("At 1,000 rps the queue fills but does not overflow inside the one-second timeout — a p50 of "
    + "668 ms with every request still succeeding. At 1,500 it overflows and nothing gets through.", {
    x: MX + 7.9, y: y0 + 0.75, w: 4.1, h: 1.3, isTextBox: true,
    fontFace: B, fontSize: 13, color: MUTED, margin: 0,
  });
  s.addText("The application was never slow", {
    x: MX + 7.9, y: y0 + 2.15, w: 4.1, h: 0.32, isTextBox: true,
    fontFace: B, fontSize: 14, bold: true, color: INK, margin: 0,
  });
  s.addText("At 1,500 rps the server completed 127,256 requests at a 202 ms mean and logged zero "
    + "exceptions, while k6 recorded 100 % failure and time-blocked-before-sending reached 834 ms at p95. "
    + "The requests were sitting in the accept queue, never reaching the application. 200 threads at "
    + "200 ms each caps throughput at 1,000 rps; the surplus simply accumulated.", {
    x: MX + 7.9, y: y0 + 2.5, w: 4.1, h: 1.8, isTextBox: true,
    fontFace: B, fontSize: 13, color: MUTED, margin: 0,
  });
  s.addText("At 1,500 rps that is all 90,000 requests failing, not a tail — platform threads returned "
    + "nothing usable for a full minute.", {
    x: MX, y: y0 + 4.4, w: 7.5, h: 0.45, isTextBox: true,
    fontFace: B, fontSize: 12, italic: true, color: MUTED, margin: 0,
  });
  s.addNotes("The 2,000 rps platform-thread cell is marked invalid: the generator dropped iterations "
    + "against an already-failing server, so its p50 of 709.7 ms understates the load.");
}

/* ------------------------------------------------------ 8 db-heavy flip */
{
  const s = pres.addSlide();
  const y0 = titled(s, "On the realistic database workload, reactive is the slower option",
                    "Results · /db-heavy");
  s.addChart(pres.ChartType.bar, [
    { name: "WebFlux", labels: ["500 rps · 30k req", "1,000 rps · 60k req", "1,500 rps · 90k req"], values: [13.4, 15.9, 313.0] },
    { name: "Virtual threads", labels: ["500 rps · 30k req", "1,000 rps · 60k req", "1,500 rps · 90k req"], values: [13.1, 12.8, 19.7] },
    { name: "Platform threads", labels: ["500 rps · 30k req", "1,000 rps · 60k req", "1,500 rps · 90k req"], values: [13.1, 12.8, 14.8] },
  ], chartOpts({
    x: MX, y: y0, w: 7.5, h: 4.3,
    title: "95th percentile response time (ms) by offered rate",
  }));
  s.addText("At 1,500 rps", {
    x: MX + 7.9, y: y0 + 0.05, w: 4.1, h: 0.32, isTextBox: true,
    fontFace: H, fontSize: 18, bold: true, color: INK, margin: 0,
  });
  table(s, ["", "p95", "p99", "cores"],
    [["WebFlux", "313.0", "409.3", "0.613"],
     ["Virtual threads", "19.7", "33.2", "0.233"],
     ["Platform threads", "14.8", "28.7", "0.211"]],
    MX + 7.9, y0 + 0.5, [1.65, 0.8, 0.8, 0.85], { rowH: 0.34, fontSize: 12 });
  s.addText("Reactive is roughly 16× slower at p95 here and uses 2.6× the CPU for the same query. At "
    + "2,000 rps it fails 58–61 % of requests and the generator can no longer sustain the rate; virtual "
    + "threads fail 92 % but keep serving.", {
    x: MX + 7.9, y: y0 + 2.2, w: 4.1, h: 1.3, isTextBox: true,
    fontFace: B, fontSize: 13, color: MUTED, margin: 0,
  });
  s.addText("In absolute terms at 1,500 rps: of 90,000 requests, 4,500 were slower than 313 ms on "
    + "reactive and 900 were slower than 409 ms. On virtual threads the same cuts fall at 19.7 ms and "
    + "33.2 ms. Nothing failed on either — this is entirely tail latency.", {
    x: MX + 7.9, y: y0 + 3.4, w: 4.1, h: 1.25, isTextBox: true,
    fontFace: B, fontSize: 12, color: INK, margin: 0,
  });
  s.addText("This reverses the laptop finding, where reactive used about 30 % less CPU across the board. "
    + "That advantage holds only where there is no database in the path.", {
    x: MX + 7.9, y: y0 + 3.5, w: 4.1, h: 0.8, isTextBox: true,
    fontFace: B, fontSize: 13, color: INK, margin: 0,
  });
}

/* ------------------------------------------------------- 8b the choke */
{
  const s = pres.addSlide();
  const y0 = titled(s, "Where each stack chokes, and how differently", "Results · /db-heavy @ 2,000 rps");
  table(s,
    ["", "Errors", "Client p50", "Server mean", "Pool waiting", "CPU"],
    [
      ["webflux-r2dbc", "61 %", "937 ms", "555 ms", "0", "0.50"],
      ["mvc-virtual", "92 %", "999 ms", "4,952 ms", "5,889", "1.28"],
      ["mvc-platform", "100 %", "1,000 ms", "124 ms", "175", "0.41"],
    ],
    MX, y0, [2.9, 1.5, 1.9, 2.0, 2.0, 1.7],
    { rowH: 0.42, fontSize: 13, headColors: [INK, INK, INK, INK, INK, INK] });

  s.addText("The server-mean column is the one to read twice", {
    x: MX, y: y0 + 1.9, w: CW, h: 0.34, isTextBox: true,
    fontFace: B, fontSize: 16, bold: true, color: INK, margin: 0,
  });
  s.addText("Platform threads had the fastest application of the three — 124 ms per request — precisely "
    + "because its 200-thread limit refused work it could not finish. Virtual threads removed that limit, "
    + "admitted everything, queued 5,889 requests on a 20-connection pool and spent 4.9 seconds per "
    + "request on work the client had already abandoned at one second.", {
    x: MX, y: y0 + 2.3, w: CW, h: 0.95, isTextBox: true,
    fontFace: B, fontSize: 14, color: MUTED, margin: 0,
  });

  const cards = [
    [REFERENCE, "Platform threads", "Bounded admission", "200 threads cap what enters. The queue forms outside the application, which stays healthy. Clients time out at the door."],
    [CANDIDATE, "Virtual threads", "Unbounded admission", "Nothing caps entry. Requests queue on the connection pool instead, and the application does seconds of work nobody is waiting for."],
    [CURRENT, "WebFlux", "Cancellation propagates", "When the client gives up, the reactive chain aborts the in-flight work. Least wasted effort of the three."],
  ];
  const cw2 = 3.75, gp = 0.37;
  cards.forEach((c, i) => {
    const x = MX + i * (cw2 + gp);
    s.addShape(pres.ShapeType.roundRect, {
      x, y: y0 + 3.4, w: cw2, h: 1.75, fill: { color: CARD }, rectRadius: 0.08, line: { color: CARD },
    });
    chip(s, x + 0.3, y0 + 3.6, c[0], c[1], { bold: true, w: 3.1, fontSize: 13 });
    s.addText(c[2], {
      x: x + 0.56, y: y0 + 3.88, w: cw2 - 0.8, h: 0.28, isTextBox: true,
      fontFace: B, fontSize: 12, bold: true, color: c[0], margin: 0,
    });
    s.addText(c[3], {
      x: x + 0.3, y: y0 + 4.18, w: cw2 - 0.6, h: 0.9, isTextBox: true,
      fontFace: B, fontSize: 11, color: MUTED, margin: 0,
    });
  });
  s.addNotes("Both webflux cells and one mvc-virtual cell at this rate are marked invalid: the generator "
    + "dropped iterations against an already-failing server, so their error rates understate the load. "
    + "The mechanism each one shows is unaffected.");
}

/* -------------------------------------------------- 8c what failed, why */
{
  const s = pres.addSlide();
  const y0 = titled(s, "What actually failed, and why", "Results · error causes");
  table(s,
    ["Workload · rate", "Variant", "Errors", "Server 5xx", "Waiting on pool", "Cause"],
    [
      ["/api @ 1,500", "mvc-platform", "100 %", "0", "0", "client timeout, accept queue"],
      ["/db-heavy @ 2,000", "mvc-platform", "100 %", "0", "175", "client timeout, accept queue"],
      ["/db-heavy @ 2,000", "webflux-r2dbc", "61 %", "0", "0", "client timeout, server too slow"],
      ["/db-heavy @ 2,000", "mvc-virtual", "92 %", "17,399", "5,889", "CannotGetJdbcConnectionException"],
      ["/db-slow @ 1,500", "mvc-platform", "100 %", "0", "179", "client timeout, accept queue"],
      ["/db-slow @ 1,500", "webflux-r2dbc", "100 %", "165,159", "0", "AbortedException"],
      ["/db-slow @ 1,500", "mvc-virtual", "99 %", "80,170", "7,826", "CannotGetJdbcConnectionException"],
    ],
    MX, y0, [2.7, 2.3, 1.2, 1.6, 1.9, 2.3],
    { rowH: 0.34, fontSize: 12 });

  s.addText("Three signatures, consistent across every failing cell", {
    x: MX, y: y0 + 2.95, w: CW, h: 0.34, isTextBox: true,
    fontFace: B, fontSize: 16, bold: true, color: INK, margin: 0,
  });
  const sigs = [
    [REFERENCE, "mvc-platform", "No server-side exception anywhere, ever. The application never saw the request. Pool waiting stays bounded at 0–179 because only 200 threads can be in flight."],
    [CANDIDATE, "mvc-virtual", "CannotGetJdbcConnectionException — pool acquire timing out. Pool waiting reaches 4,294–7,826: admission is unbounded, so the queue moves to the database."],
    [CURRENT, "webflux-r2dbc", "AbortedException and TransientDataAccessResourceException — the client disconnected and the reactive chain cancelled the work. Pool waiting is always 0."],
  ];
  sigs.forEach((sg, i) => {
    const y = y0 + 3.4 + i * 0.76;
    chip(s, MX, y, sg[0], sg[1], { bold: true, w: 2.6, fontSize: 13 });
    s.addText(sg[2], {
      x: MX + 2.9, y, w: CW - 2.9, h: 0.68, isTextBox: true,
      fontFace: B, fontSize: 12, color: MUTED, margin: 0,
    });
  });
}

/* ---------------------------------------------------------- 9 resources */
{
  const s = pres.addSlide();
  const y0 = titled(s, "Resource use, and how it was measured", "Results");
  table(s,
    ["Workload · rate", "WebFlux", "Virtual threads", "Platform threads"],
    [
      ["/nodb @ 2,000", "0.119", "0.123", "0.123"],
      ["/db @ 2,000", "0.352", "0.287", "0.157"],
      ["/db-heavy @ 1,500", "0.613", "0.233", "0.211"],
      ["/api @ 1,000", "0.256", "0.301", "0.241"],
      ["/api @ 2,000", "0.356", "0.560", "0.326"],
      ["Live threads", "21", "20 – 79", "215 – 288"],
    ],
    MX, y0, [3.3, 2.5, 2.6, 2.7],
    { rowH: 0.38, fontSize: 13, headColors: [INK, CURRENT, CANDIDATE, REFERENCE] });
  s.addText("CPU cores consumed per wall-second, median of two repetitions. The machine has 2, so 0.560 "
    + "is 28 % of the box.", {
    x: MX, y: y0 + 2.85, w: CW, h: 0.4, isTextBox: true,
    fontFace: B, fontSize: 13, italic: true, color: MUTED, margin: 0,
  });
  s.addText("Reactive is cheapest where there is no database and most expensive where there is. On /api it "
    + "uses 36 % less CPU than virtual threads; on /db-heavy it uses 2.6× more. Thread count is not a proxy "
    + "for cost — platform threads run ten times as many as reactive while using less CPU than either.", {
    x: MX, y: y0 + 3.3, w: CW, h: 0.9, isTextBox: true,
    fontFace: B, fontSize: 14, color: INK, margin: 0,
  });
  s.addText("Memory was not usefully measured. One heap sample per cell, taken at the end of the window, "
    + "ranged 52–972 MB across otherwise comparable cells — it sawtooths with GC. Nothing here tests the "
    + "laptop run's memory finding either way.", {
    x: MX, y: y0 + 4.25, w: CW, h: 0.7, isTextBox: true,
    fontFace: B, fontSize: 13, color: MUTED, margin: 0,
  });
}

/* ------------------------------------------------------------ 10 db-slow */
{
  const s = pres.addSlide();
  const y0 = titled(s, "/db-slow measures the database, not the stacks", "Results · a caveat");
  s.addText("Every cell failed, in all three builds, at every rate. That is by construction, not a finding.", {
    x: MX, y: y0, w: CW, h: 0.35, isTextBox: true,
    fontFace: B, fontSize: 15, bold: true, color: INK, margin: 0,
  });
  s.addText(
    "pg_sleep(0.1)  ->  100 ms connection hold\n"
    + "ceiling = 20 connections / 0.1 s = 200 rps\n"
    + "lowest rate on the ladder        = 500 rps    (2.5x over)", {
    x: MX, y: y0 + 0.5, w: 7.3, h: 1.0, isTextBox: true,
    fontFace: M, fontSize: 12, color: INK, margin: 0, lineSpacingMultiple: 1.25,
  });
  s.addText("And the ceiling falls as you push harder", {
    x: MX, y: y0 + 1.65, w: 7.3, h: 0.3, isTextBox: true,
    fontFace: B, fontSize: 14, bold: true, color: INK, margin: 0,
  });
  table(s, ["Offered", "Measured hold", "Effective ceiling", "Errors"],
    [["500 rps", "101.8 ms", "197 rps", "99.1 %"],
     ["1,000 rps", "127.6 ms", "157 rps", "99.0 %"],
     ["1,500 rps", "151.4 ms", "132 rps", "98.9 %"],
     ["2,000 rps", "160.5 ms", "125 rps", "99.4 %"]],
    MX, y0 + 2.0, [1.7, 1.9, 1.9, 1.5], { rowH: 0.32, fontSize: 12 });
  s.addText("pg_sleep is a fixed 100 ms, so the extra 60 ms is contention inside PostgreSQL once far more "
    + "sessions are queued against it than the pool can serve. Overload makes the bottleneck narrower.", {
    x: MX, y: y0 + 3.75, w: 7.3, h: 0.7, isTextBox: true,
    fontFace: B, fontSize: 13, color: MUTED, margin: 0,
  });

  s.addText("What this tells us, and what it does not", {
    x: MX + 7.7, y: y0, w: 4.3, h: 0.32, isTextBox: true,
    fontFace: B, fontSize: 15, bold: true, color: INK, margin: 0,
  });
  s.addText("These numbers are a property of the pool size, the query duration, the database's CPU and its "
    + "configuration — not of the three stacks. Change any one of those and the whole picture moves. A "
    + "larger pool, a faster query or a bigger database would each shift the ceiling somewhere else "
    + "entirely.", {
    x: MX + 7.7, y: y0 + 0.42, w: 4.3, h: 1.6, isTextBox: true,
    fontFace: B, fontSize: 13, color: MUTED, margin: 0,
  });
  s.addText("What it does show is how each stack behaves once it is past capacity, and they differ "
    + "completely:", {
    x: MX + 7.7, y: y0 + 2.05, w: 4.3, h: 0.55, isTextBox: true,
    fontFace: B, fontSize: 13, color: INK, margin: 0,
  });
  const shapes = [
    [REFERENCE, "Platform threads", "refuse work at the accept queue, 0.056 cores — almost idle"],
    [CANDIDATE, "Virtual threads", "admit it, exhaust the pool, 511k connection failures at 1.18 cores"],
    [CURRENT, "WebFlux", "admit it, 633k driver failures at 1.62 cores"],
  ];
  shapes.forEach((sh, i) => {
    const y = y0 + 2.7 + i * 0.75;
    chip(s, MX + 7.7, y, sh[0], sh[1], { bold: true, w: 4.0, fontSize: 13 });
    s.addText(sh[2], {
      x: MX + 7.96, y: y + 0.26, w: 4.0, h: 0.48, isTextBox: true,
      fontFace: B, fontSize: 12, color: MUTED, margin: 0,
    });
  });
  s.addNotes("If this workload is to say anything about the candidates, it needs its own ladder below the "
    + "ceiling - 50 to 300 rps - or a pool sized for the rates being offered. As run, it is a "
    + "demonstration of failure modes.");
}

/* --------------------------------------------------------- 11 ecosystem */
{
  const s = pres.addSlide();
  const y0 = titled(s, "Ecosystem: what changes with the driver", "Migration");
  table(s,
    ["", "WebFlux + R2DBC (today)", "MVC + virtual threads"],
    [
      ["PostgreSQL driver", "r2dbc-postgresql 1.1.2", "postgresql 42.7.13"],
      ["Connection pool", "R2DBC Pool", "HikariCP"],
      ["ORM", "none available", "Hibernate / Spring Data JPA"],
      ["Query APIs", "DatabaseClient", "JdbcClient, JdbcTemplate, JPA"],
      ["Transactions", "reactive, context-bound", "@Transactional, thread-bound"],
      ["Migrations", "Flyway needs a JDBC driver anyway", "Flyway natively"],
      ["Tracing context", "Reactor Context, plumbed explicitly", "ThreadLocal / MDC works"],
      ["Stack traces", "reactor internals", "our own classes"],
    ],
    MX, y0, [3.1, 4.5, 4.4], { rowH: 0.38, fontSize: 13, headColors: [INK, CURRENT, CANDIDATE] });
  s.addText("A reactive service already ships a JDBC driver for schema migrations, so moving does not add a "
    + "dependency there — it removes the second one.", {
    x: MX, y: y0 + 3.7, w: CW, h: 0.5, isTextBox: true,
    fontFace: B, fontSize: 13, italic: true, color: MUTED, margin: 0,
  });
}

/* ------------------------------------------------------------ 12 closing */
{
  const s = pres.addSlide();
  s.background = { color: DARK };
  s.addText("WHERE THIS LEAVES US", {
    x: MX, y: 0.55, w: CW, h: 0.3, isTextBox: true,
    fontFace: B, fontSize: 12, bold: true, color: "8896A2", charSpacing: 1.8, margin: 0,
  });
  s.addText("Virtual threads are a credible replacement. The open question is cost, not capability.", {
    x: MX, y: 0.95, w: 11.6, h: 1.0, isTextBox: true,
    fontFace: H, fontSize: 28, bold: true, color: WHITE, margin: 0,
  });
  [["Capability", "Matched WebFlux on latency at every rate on every workload tested, within 0.1 ms.", CANDIDATE],
   ["CPU", "36 % more on /api, where there is no database. 2.6× less on /db-heavy, where there is. The direction depends on the workload.", "E8B4A0"],
   ["Memory", "Not measured usefully in this run. One heap sample per cell, ranging 52–972 MB. The laptop run's memory finding is neither confirmed nor refuted.", "E8B4A0"],
   ["Engineering", "Ordinary code, real stack traces, working debuggers, a mature driver, a larger hiring pool.", CANDIDATE],
  ].forEach((p, i) => {
    const y = 2.15 + i * 1.12;
    s.addText(p[0], {
      x: MX, y, w: 2.5, h: 0.34, isTextBox: true,
      fontFace: B, fontSize: 16, bold: true, color: p[2], margin: 0,
    });
    s.addText(p[1], {
      x: MX + 2.7, y, w: 9.2, h: 0.9, isTextBox: true,
      fontFace: B, fontSize: 14, color: "C9D3DB", margin: 0,
    });
  });
  s.addText("Two repetitions per cell in a single session. Differences of the size seen on /db-heavy and "
    + "/api are safe to act on; smaller ones are not.", {
    x: MX, y: 6.45, w: CW, h: 0.4, isTextBox: true,
    fontFace: B, fontSize: 13, italic: true, color: "8896A2", margin: 0,
  });
}

pres.writeFile({ fileName: OUT }).then(f => console.log("written:", f));
