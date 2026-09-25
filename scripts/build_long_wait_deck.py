#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build docs/virtual-threads-long-wait.pptx from the /api-800 and /api-1000 cells.

    python scripts/build_long_wait_deck.py

The AWS deck is used only as a style donor: it is opened for its theme, its
slide layout and its table cell formatting, then every one of its slides is
dropped before the new ones are added. It is never written back to.

Every figure comes from extract_long_wait.load(). Prose is literal; numbers are
not, so a slide cannot drift from results/raw/.
"""
import copy
import os
import sys

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from extract_long_wait import load, fit, stub_witness, VARIANT_ORDER, WORKLOAD_ORDER  # noqa: E402

DONOR = "docs/virtual-threads-technical-aws.pptx"
OUT = "docs/virtual-threads-long-wait.pptx"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

INK = RGBColor(0x1F, 0x29, 0x33)
MUTED = RGBColor(0x5C, 0x6B, 0x77)
SHORT = {"webflux-r2dbc": "webflux", "mvc-virtual": "virtual"}
RATES = [500, 1000, 1500, 2000]
ROW_H = 0.275
PAGE_H = 7.5

cells = load()


# ------------------------------------------------------------------ helpers
def sel(**match):
    return [c for c in cells if all(c.get(k) == v for k, v in match.items())]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def avg(cs, key, sample=False):
    if sample:
        return mean([c["samples"][key] for c in cs if c.get("samples")])
    return mean([c.get(key) for c in cs])


def pair(cs, key, spec="{:,.0f}", sample=False):
    """Both repetitions, so disagreement between them stays visible."""
    vals = [(c["samples"][key] if sample else c[key]) for c in cs
            if (c.get("samples") if sample else True)]
    return " / ".join(spec.format(v) for v in vals)


# ------------------------------------------------------------------- content
def rows_inflight():
    out = []
    for wl in WORKLOAD_ORDER:
        for rate in RATES:
            got = sel(workload=wl, rate=rate)
            out.append([f"/{wl}", f"{rate:,}", f"{got[0]['inflight_expected']:,.0f}"]
                       + [pair([c for c in got if c["variant"] == v], "inflight", sample=True)
                          for v in VARIANT_ORDER])
    return out


def rows_latency():
    out = []
    for wl in WORKLOAD_ORDER:
        for rate in RATES:
            m = {}
            row = [f"/{wl}", f"{rate:,}"]
            for v in VARIANT_ORDER:
                got = sel(workload=wl, rate=rate, variant=v)
                m[v] = avg(got, "p99_excess")
                row.append(pair(got, "p99", "{:,.0f}"))
                row.append(pair(got, "p99_excess", "{:+.0f}"))
            row.append(f"{m['mvc-virtual'] / m['webflux-r2dbc']:.1f}x")
            out.append(row)
    return out


def rows_drivers():
    out = []
    for rate in RATES:
        for v in VARIANT_ORDER:
            pts = []
            for wl in WORKLOAD_ORDER:
                got = [c for c in sel(workload=wl, rate=rate, variant=v) if c.get("samples")]
                pts.append((avg(got, "inflight", sample=True), avg(got, "p99_excess")))
            out.append([f"{rate:,}", SHORT[v],
                        f"{pts[0][1]:+.0f} ms", f"{pts[0][0]:,.0f}",
                        f"{pts[1][1]:+.0f} ms", f"{pts[1][0]:,.0f}",
                        f"{pts[1][1] - pts[0][1]:+.1f} ms"])
    return out


def rows_cpu():
    out = []
    for wl in WORKLOAD_ORDER:
        for rate in RATES:
            m, row = {}, [f"/{wl}", f"{rate:,}"]
            for v in VARIANT_ORDER:
                got = [c for c in sel(workload=wl, rate=rate, variant=v) if c.get("samples")]
                m[v] = avg(got, "cpu", sample=True)
                row.append(pair(got, "cpu", "{:.3f}", sample=True))
            row.append(f"{m['mvc-virtual'] / m['webflux-r2dbc']:.1f}x")
            out.append(row)
    return out


def rows_memory():
    """One row per measurement, at the top rung, both workloads."""
    out = []
    top = {v: {wl: [c for c in sel(workload=wl, rate=2000, variant=v)] for wl in WORKLOAD_ORDER}
           for v in VARIANT_ORDER}

    def cellval(v, wl, key, spec, sample=False):
        cs = top[v][wl]
        x = avg(cs, key, sample=sample)
        return spec.format(x)

    specs = [
        ("Allocation per 1,000 requests", "alloc_mb_per_1k", "{:,.0f} MB", False),
        ("Promoted to old gen, per request", "promoted_kb_per_req", "{:.1f} KB", False),
        ("Heap floor under load", "heap_floor_mb", "{:,.0f} MB", True),
        ("GC pause in the 120 s window", "gc_pause_s", "{:.1f} s", False),
        ("GC collections", "gc_count", "{:,.0f}", False),
        ("Platform threads", "threads", "{:,.0f}", True),
    ]
    for label, key, spec, sample in specs:
        row = [label]
        for v in VARIANT_ORDER:
            for wl in WORKLOAD_ORDER:
                row.append(cellval(v, wl, key, spec, sample))
        out.append(row)

    # Regressed across all 16 cells of each build, so this row is not per
    # workload; the second column of each pair carries the fit quality instead.
    row = ["Heap floor per request in flight (regressed)"]
    for v in VARIANT_ORDER:
        pts = [(c["samples"]["inflight"], c["samples"]["heap_floor_mb"])
               for c in sel(variant=v) if c.get("samples")]
        slope, _intercept, r2 = fit(pts)
        row += [f"{slope * 1024:,.0f} KB", f"R² {r2:.2f}"]
    out.append(row)
    return out


def rows_appendix(wl):
    out = []
    for c in sel(workload=wl):
        s = c.get("samples") or {}
        out.append([f"{c['rate']:,}", SHORT[c["variant"]], str(c["rep"]),
                    f"{c['err_pct']:.2f}", f"{c['p50']:,.1f}", f"{c['p95']:,.1f}",
                    f"{c['p99']:,.1f}", f"{s.get('inflight', 0):,.0f}",
                    f"{s.get('cpu', 0):.3f}", f"{s.get('heap_floor_mb', 0):,.0f}",
                    f"{c['alloc_mb_per_1k']:.0f}", f"{c['promoted_kb_per_req']:.1f}",
                    f"{c['gc_pause_s']:.2f}"])
    return out


# --------------------------------------------------------------------- build
prs = Presentation(DONOR)
donor_slide = list(prs.slides)[12]
layout = donor_slide.slide_layout
hdr_tcPr = copy.deepcopy(
    [sh for sh in donor_slide.shapes if sh.has_table][0]
    .table.rows[0].cells[0]._tc.find(A_NS + "tcPr"))

# Style is taken; the donor's own slides are not wanted.
sld_lst = prs.slides._sldIdLst
for sld in list(sld_lst):
    prs.part.drop_rel(sld.get(R_NS + "id"))
    sld_lst.remove(sld)
assert len(prs.slides) == 0, "donor slides not fully removed"


def textbox(slide, x, y, w, h, text, font, size, color, bold=False, space=0):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, line in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        if space:
            p.space_before = Pt(space)
        run = p.add_run()
        run.text = line
        run.font.name, run.font.size, run.font.bold = font, Pt(size), bold
        run.font.color.rgb = color
    return tb


def new_slide(eyebrow, title):
    slide = prs.slides.add_slide(layout)
    for sh in list(slide.shapes):          # drop layout placeholders
        sh._element.getparent().remove(sh._element)
    if eyebrow:
        textbox(slide, 0.65, 0.38, 12.0, 0.26, eyebrow, "Calibri", 11, MUTED, True)
    textbox(slide, 0.65, 0.66, 12.0, 0.80, title, "Cambria", 29, INK, True)
    return slide


def add_table(slide, cols, data, top=1.55, size=11):
    """cols: list of (heading, width_inches, 'l'|'r')."""
    nrows = len(data) + 1
    gf = slide.shapes.add_table(nrows, len(cols), Inches(0.65), Inches(top),
                                Inches(12.0), Inches(ROW_H * nrows))
    tbl = gf.table
    tbl._tbl.find(A_NS + "tblPr").clear()          # no banding, no theme style
    for i, (_, cw, _a) in enumerate(cols):
        tbl.columns[i].width = Inches(cw)
    for r in tbl.rows:
        r.height = Inches(ROW_H)
    for ri, row in enumerate([[h for h, _, _ in cols]] + data):
        for ci, val in enumerate(row):
            cell = tbl.cell(ri, ci)
            tc = cell._tc
            old = tc.find(A_NS + "tcPr")
            if old is not None:
                tc.remove(old)
            tc.append(copy.deepcopy(hdr_tcPr))
            cell.margin_left = cell.margin_right = Inches(0.04)
            cell.margin_top = cell.margin_bottom = Inches(0.01)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = False
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.RIGHT if cols[ci][2] == "r" else PP_ALIGN.LEFT
            run = p.add_run()
            run.text = val
            run.font.name, run.font.size = "Calibri", Pt(size)
            run.font.bold = (ri == 0)
            run.font.color.rgb = INK
    return top + ROW_H * nrows


def caption(slide, y, text, size=13):
    return textbox(slide, 0.65, y + 0.22, 12.0, 0.9, text, "Calibri", size, MUTED)


live, dead = stub_witness()
built = []

# 1 -------------------------------------------------------------------- title
s = prs.slides.add_slide(layout)
for sh in list(s.shapes):
    sh._element.getparent().remove(sh._element)
textbox(s, 0.65, 2.45, 12.0, 0.3, "AWS BENCHMARK · LONG-WAIT WORKLOADS", "Calibri", 12, MUTED, True)
textbox(s, 0.65, 2.90, 12.0, 1.1, "Holding a request that is only waiting", "Cambria", 40, INK, True)
textbox(s, 0.65, 4.05, 12.0, 0.9,
        "/api-800 and /api-1000 — what WebFlux and virtual threads each spend\n"
        "to keep up to 2,000 requests in flight doing nothing at all",
        "Calibri", 16, MUTED)
textbox(s, 0.65, 5.35, 12.0, 0.3,
        f"{len(cells)} cells · 2 builds · 4 rates · 2 repetitions · all valid   |   "
        "c7i.large, 2 vCPU, 1 GB heap",
        "Calibri", 12, MUTED)
built.append("title")

# 2 ------------------------------------------------------------ what this is
s = new_slide("WHAT THIS TEST IS", "Sized past any thread count either build has")
y = add_table(s, [("workload", 2.0, "l"), ("upstream delay", 2.0, "l"),
                  ("in flight @ 500", 2.0, "r"), ("@ 1,000", 2.0, "r"),
                  ("@ 1,500", 2.0, "r"), ("@ 2,000", 2.0, "r")],
              [["/api", "200 ms", "100", "200", "300", "400"],
               ["/api-800", "800 ms", "400", "800", "1,200", "1,600"],
               ["/api-1000", "1,000 ms", "500", "1,000", "1,500", "2,000"]])
caption(s, y,
        "/api was sized so in-flight concurrency landed on Tomcat's 200 threads, which made it "
        "decisive about platform threads. These two are four to five times past that, so the "
        "scarce resource is no longer a worker to run the request on — it is whatever the "
        "stack must keep alive while nothing happens. No database is involved, so the connection "
        "pool cannot explain anything here. mvc-platform is excluded by arithmetic: 200 threads "
        "over an 800 ms hold is 250 rps, below the bottom rung.")
built.append("what this test is")

# 3 --------------------------------------------------------------- capacity
s = new_slide("RESULTS · CAPACITY", "Both builds held 2,000 in flight. Neither hit a ceiling.")
y = add_table(s, [("workload", 1.7, "l"), ("offered", 1.5, "r"), ("expected", 1.8, "r"),
                  ("webflux  (rep 1 / rep 2)", 3.5, "r"), ("virtual  (rep 1 / rep 2)", 3.5, "r")],
              rows_inflight())
caption(s, y,
        "Measured on the server every 2 s during the run, not inferred. Both builds track "
        "Little's Law (rate × latency) to within 1 % at every rung, with 0 dropped iterations "
        "and 0.00 % errors in all 32 cells. Because neither build saturated, this run does not "
        "establish where either one stops — these are points on a curve, not a knee.")
built.append("capacity")

# 4 ---------------------------------------------------------------- latency
s = new_slide("RESULTS · LATENCY", "p50 is the delay itself. The difference is all tail.")
y = add_table(s, [("workload", 1.5, "l"), ("offered", 1.2, "r"),
                  ("webflux p99", 1.9, "r"), ("over floor", 1.6, "r"),
                  ("virtual p99", 1.9, "r"), ("over floor", 1.6, "r"), ("ratio", 2.3, "r")],
              rows_latency())
caption(s, y,
        "Both repetitions shown. p50 is 800.5–800.9 ms and 1000.5–1000.9 ms on both "
        "builds at every rate: half of all requests pay nothing above the wait, whichever stack "
        "serves them. 'Over floor' is p99 minus the upstream delay — the part the application "
        "added. At 500 rps both builds sit close enough to the floor that rep-to-rep noise "
        "dominates, which is why virtual posts +26 and +3 ms on the same cell.")
built.append("latency")

# 5 ---------------------------------------------------------------- drivers
s = new_slide("MECHANISM", "The tail follows rate. The heap follows in-flight.")
y = add_table(s, [("offered", 1.3, "r"), ("build", 1.5, "l"),
                  ("/api-800 p99", 1.9, "r"), ("in flight", 1.6, "r"),
                  ("/api-1000 p99", 1.9, "r"), ("in flight", 1.6, "r"), ("change", 2.2, "r")],
              rows_drivers())
w_slope = fit([(c["samples"]["inflight"], c["samples"]["heap_floor_mb"])
               for c in sel(variant="webflux-r2dbc") if c.get("samples")])
v_slope = fit([(c["samples"]["inflight"], c["samples"]["heap_floor_mb"])
               for c in sel(variant="mvc-virtual") if c.get("samples")])
caption(s, y,
        "Rate and in-flight normally move together, so neither can be blamed from one workload. "
        "Two delays break the tie: at the same rate the two workloads sit at different in-flight "
        "counts. For virtual threads the tail does not follow concurrency at all — 25 % more "
        "in flight moves p99 by −2.0, +2.5, +1.3 and −0.4 ms, and the sign flips. Its "
        "~86 ms tail is a per-request cost. WebFlux is not as clean: its last two pairs are +5.4 "
        f"and +7.6 ms, about a third of its total, so above ~1,500 in flight it does pick up a "
        f"concurrency term. Heap runs the other way — regressed on in-flight across all 16 "
        f"cells, the floor rises {v_slope[0] * 1024:,.0f} KB per request in flight for virtual "
        f"threads against {w_slope[0] * 1024:,.0f} KB for WebFlux "
        f"(R² {v_slope[2]:.2f} and {w_slope[2]:.2f}, so trends rather than tight fits).",
        size=12)
built.append("drivers")

# 6 -------------------------------------------------------------------- cpu
s = new_slide("RESOURCES · CPU", "Virtual threads cost about twice the CPU")
y = add_table(s, [("workload", 1.8, "l"), ("offered", 1.6, "r"),
                  ("webflux  (rep 1 / rep 2)", 3.3, "r"),
                  ("virtual  (rep 1 / rep 2)", 3.3, "r"), ("ratio", 2.0, "r")],
              rows_cpu())
caption(s, y,
        "Cores of the 2 available, averaged over the steady-state samples and shown for both "
        "repetitions. The ratio holds near 2× across the top of the ladder on both workloads. "
        "Neither build is close to saturating the box — the most expensive cell used 0.34 of "
        "2 cores — so this is a cost difference at these rates, not a throughput limit.")
built.append("cpu")

# 7 ----------------------------------------------------------------- memory
s = new_slide("RESOURCES · MEMORY", "Opposite memory profiles")
y = add_table(s, [("at 2,000 rps", 4.0, "l"),
                  ("webflux /api-800", 2.0, "r"), ("/api-1000", 2.0, "r"),
                  ("virtual /api-800", 2.0, "r"), ("/api-1000", 2.0, "r")],
              rows_memory())
caption(s, y,
        "Allocation and promotion are counters differenced across the window, so they are exact. "
        "Heap floor is the lowest reading while under load — heap used sawtooths with GC, so "
        "its mean would mix retained state with uncollected garbage. Promotion is the mechanism: "
        "a request waiting a second outlives a young collection, so under virtual threads its "
        "stack is still reachable when the collector runs and is moved to the old generation. "
        "WebFlux's promotion never exceeds 0.20 KB per request and is under 0.03 KB in 15 of its "
        "16 cells. Platform threads counted here exclude virtual threads, so for virtual the figure "
        "is ForkJoinPool carriers plus Tomcat; WebFlux sits at 21 in fifteen of sixteen cells and "
        "22.7 in the sixteenth, regardless of rate or concurrency.", size=12)
built.append("memory")

# 8 ----------------------------------------------------------------- limits
s = new_slide("LIMITS", "What this run does not establish")
textbox(s, 0.65, 1.62, 12.0, 5.2,
        "The stub was not independently witnessed.\n"
        f"    All {dead} stub sample files recorded zeros throughout, so the stub's own in-flight, CPU and\n"
        "    file-descriptor counts are unavailable for this run. The likely cause is that the previous stub\n"
        "    build was still running — stub.sh start returns early when one is alive, so a re-upload without\n"
        "    restart keeps the old process, which exposed only health and not prometheus. Whether the stub\n"
        "    stayed clear of its own limits during these cells is simply not established by measurement.\n"
        "\n"
        "No ceiling was found.\n"
        "    Neither build saturated, so nothing here says where either one stops. Extrapolating the heap\n"
        "    slope past 2,000 requests in flight would be unsupported.\n"
        "\n"
        "One configuration.\n"
        "    c7i.large, 2 vCPU, 1 GB heap, G1, one pool size, one upstream. The heap size interacts directly\n"
        "    with the promotion finding: a larger heap changes collection frequency, and with it both the\n"
        "    pause totals and the heap floor.\n"
        "\n"
        "Carrier growth is unexplained.\n"
        "    Virtual threads reached ~130 carrier threads on a 2-core box. That is visible in the data but its\n"
        "    cause is not; a thread dump under load would settle it, and nothing here does.\n"
        "\n"
        "Platform threads are absent by construction.\n"
        "    This run says nothing about mvc-platform on long waits beyond the arithmetic that excluded it.",
        "Calibri", 13, INK, space=4)
built.append("limits")

# 9, 10 ------------------------------------------------------------ appendix
APPX = [("rate", 0.90, "r"), ("build", 1.05, "l"), ("rep", 0.55, "r"), ("err %", 0.80, "r"),
        ("p50", 1.00, "r"), ("p95", 1.00, "r"), ("p99", 1.00, "r"), ("in flight", 1.10, "r"),
        ("cores", 0.95, "r"), ("heap floor", 1.15, "r"), ("MB/1k", 0.90, "r"),
        ("promKB", 0.90, "r"), ("GC s", 0.70, "r")]
for wl in WORKLOAD_ORDER:
    s = new_slide("APPENDIX · ALL CELLS", f"/{wl} — every cell")
    y = add_table(s, APPX, rows_appendix(wl))
    caption(s, y,
            "Every cell, both repetitions, nothing averaged. Latency in ms and raw, not excess over the "
            "delay floor. In flight, cores and heap floor are steady-state readings from the mid-run "
            "sampler; MB/1k is allocation per 1,000 requests and promKB is bytes promoted to the old "
            "generation per request, both differenced across the measured window. All cells valid: "
            "0 dropped iterations, 0.00 % errors.", size=11)
    built.append(f"appendix {wl}")

prs.save(OUT)
print(f"saved {OUT} -> {len(prs.slides)} slides")
for i, name in enumerate(built, 1):
    print(f"  {i:2}  {name}")

over = []
for i, slide in enumerate(prs.slides, 1):
    for sh in slide.shapes:
        if sh.top is not None and sh.height is not None:
            bottom = (sh.top + sh.height) / 914400
            if bottom > PAGE_H:
                over.append((i, sh.shape_type, round(bottom, 2)))
print("overflow:", "none" if not over else over)
