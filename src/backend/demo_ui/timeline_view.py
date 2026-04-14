"""
app.py - ResearchLineage Streamlit UI

Run:
    streamlit run app.py

Expects all pipeline modules in the same directory:
    pipeline.py, semantic_scholar.py, text_extraction.py,
    gemini_analysis.py, data_export.py, config.py, prompts/
"""

import streamlit as st
import json
import os
import re
import time
import threading
import queue
from pathlib import Path

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ResearchLineage",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.stApp { background: #0f1117; }
.paper-card {
    background: #1a1d27; border: 1px solid #2e3354;
    border-radius: 12px; padding: 20px 24px; margin-bottom: 6px;
}
.paper-card:hover { border-color: #6c63ff; }
.badge-revolutionary { background:#3d1212; color:#f87171; border:1px solid #ef4444; border-radius:6px; padding:2px 10px; font-size:12px; font-weight:600; }
.badge-major         { background:#2d1a08; color:#fb923c; border:1px solid #f97316; border-radius:6px; padding:2px 10px; font-size:12px; font-weight:600; }
.badge-moderate      { background:#2a2208; color:#facc15; border:1px solid #eab308; border-radius:6px; padding:2px 10px; font-size:12px; font-weight:600; }
.badge-minor         { background:#1e2233; color:#94a3b8; border:1px solid #475569; border-radius:6px; padding:2px 10px; font-size:12px; font-weight:600; }
.pill-full       { background:#0f291a; color:#4ade80; border:1px solid #22c55e; border-radius:20px; padding:2px 10px; font-size:11px; }
.pill-abstract   { background:#1e1a08; color:#fbbf24; border:1px solid #d97706; border-radius:20px; padding:2px 10px; font-size:11px; }
.pill-foundation { background:#1a1430; color:#a78bfa; border:1px solid #7c3aed; border-radius:20px; padding:2px 10px; font-size:11px; }
.connector { text-align:center; color:#3b4268; font-size:22px; margin:0; line-height:1; }
.year-chip { background:#22263a; color:#94a3b8; border-radius:6px; padding:2px 10px; font-size:13px; font-weight:600; display:inline-block; }
.log-box {
    background:#0d0f16; border:1px solid #2e3354; border-radius:8px;
    padding:12px 16px; font-family:'Courier New',monospace; font-size:12px;
    color:#7c85a2; max-height:200px; overflow-y:auto; line-height:1.8;
}
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)


# ── Pipeline imports ──────────────────────────────────────────────────────────
try:
    from pipeline import build_timeline
    from data_export import save_timeline_json, count_training_examples, build_timeline_response
    from config import MAX_DEPTH, GEMINI_API_KEY, TIMELINE_OUTPUT_DIR
    PIPELINE_AVAILABLE = True
except ImportError as e:
    PIPELINE_AVAILABLE = False
    IMPORT_ERROR = str(e)

BREAKTHROUGH_ICONS = {"revolutionary": "🔥", "major": "⚡", "moderate": "💡", "minor": "○"}


# ── Text file saving ──────────────────────────────────────────────────────────
def safe_name(text, max_len=60):
    text = re.sub(r'[^\w\s-]', '', str(text))
    text = re.sub(r'\s+', '_', text.strip())
    return text[:max_len] or "unknown"


def save_paper_texts(timeline_steps):
    """
    Save each paper's extracted text to its own .txt file.
    Uses target_text already in pipeline steps — no extra API calls.

    outputs/timelines/<Seed_Paper_Title>/
        01_<year>_<Title>.txt   ← oldest / foundational
        ...
        0N_<year>_<Title>.txt   ← seed paper
        _manifest.json
    """
    if not timeline_steps:
        return None, None

    seed = timeline_steps[0]["target_paper"]
    folder_name = f"{safe_name(seed.get('title','unknown'))}_{seed.get('paperId','')[:8]}"
    folder_path = Path(TIMELINE_OUTPUT_DIR) / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)

    ordered = list(reversed(timeline_steps))   # oldest → newest
    manifest = []

    for i, step in enumerate(ordered, 1):
        paper   = step["target_paper"]
        text    = step.get("target_text", "")
        if not text.strip():
            continue

        title  = paper.get("title", "unknown")
        year   = paper.get("year", "unknown")
        fname  = f"{i:02d}_{year}_{safe_name(title, 40)}.txt"
        fpath  = folder_path / fname

        with open(fpath, "w", encoding="utf-8") as f:
            f.write(text)

        manifest.append({
            "position": i,
            "file": fname,
            "paper_id": paper.get("paperId"),
            "title": title,
            "year": year,
            "source_type": step["target_source_type"],
            "is_foundational": step["is_foundational"],
            "chars": len(text),
        })

    with open(folder_path / "_manifest.json", "w", encoding="utf-8") as f:
        json.dump({"seed": seed.get("title"), "papers": manifest}, f, indent=2)

    return folder_path, manifest


# ── Session state ─────────────────────────────────────────────────────────────
for k, v in {
    "timeline": None, "running": False, "logs": [],
    "error": None, "paper_input": "",
    "save_folder": None, "save_manifest": None,
    "from_cache": False,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Log capture ───────────────────────────────────────────────────────────────
class LogCapture:
    def __init__(self, log_list):
        self._l = log_list
    def info(self, msg):
        self._l.append(str(msg))
    def __call__(self, msg):
        self.info(msg)


# ── Pipeline thread ───────────────────────────────────────────────────────────
def run_pipeline_thread(paper_id, depth, result_q, log_list):
    import config as cfg
    orig = cfg.logger
    cfg.logger = LogCapture(log_list)

    import pipeline
    import semantic_scholar
    import text_extraction
    import gemini_analysis
    import data_export
    for mod in [pipeline, semantic_scholar, text_extraction, gemini_analysis, data_export]:
        mod.print = cfg.logger.info

    try:
        timeline, from_cache = build_timeline(paper_id, max_depth=depth)
        result_q.put(("success", timeline, from_cache))
    except Exception as e:
        result_q.put(("error", str(e), False))
    finally:
        cfg.logger = orig


# ── Header ────────────────────────────────────────────────────────────────────
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown("## 🔬 ResearchLineage")
    st.markdown("<p style='color:#7c85a2;margin-top:-12px;font-size:14px;'>Trace the intellectual ancestry of any research paper</p>", unsafe_allow_html=True)
with c2:
    if PIPELINE_AVAILABLE:
        st.metric("Training Examples", f"{count_training_examples():,}")
st.divider()

if not PIPELINE_AVAILABLE:
    st.error(f"❌ Pipeline modules not found: `{IMPORT_ERROR}`")
    st.stop()

if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
    st.warning("⚠️  Gemini API key not set in config.py")


# ── Input row ─────────────────────────────────────────────────────────────────
ci, cd, cb = st.columns([4, 1, 1])
with ci:
    paper_input = st.text_input(
        "paper", label_visibility="collapsed",
        placeholder="arXiv ID or URL — e.g. 1706.03762",
        value=st.session_state.paper_input,
        disabled=st.session_state.running,
    )
with cd:
    depth = st.selectbox("depth", [2,3,4,5,6], index=1,
                         label_visibility="collapsed",
                         disabled=st.session_state.running)
with cb:
    run_btn = st.button(
        "⏳ Running..." if st.session_state.running else "🚀 Trace Lineage",
        use_container_width=True, type="primary",
        disabled=st.session_state.running or not paper_input.strip(),
    )


# ── Kick off pipeline ─────────────────────────────────────────────────────────
if run_btn and paper_input.strip() and not st.session_state.running:
    st.session_state.update({
        "paper_input": paper_input.strip(),
        "running": True,
        "timeline": None,
        "logs": [],
        "error": None,
        "save_folder": None,
        "save_manifest": None,
        "from_cache": False,
        "start_time": time.time(),
        "elapsed_time": None,
    })
    q = queue.Queue()
    t = threading.Thread(
        target=run_pipeline_thread,
        args=(paper_input.strip(), depth, q, st.session_state.logs),
        daemon=True,
    )
    t.start()
    st.session_state._q = q
    st.session_state._t = t
    st.rerun()


# ── Poll thread ───────────────────────────────────────────────────────────────
if st.session_state.running:
    q = st.session_state.get("_q")
    t = st.session_state.get("_t")

    prog_ph = st.empty()
    log_ph  = st.empty()

    with prog_ph.container():
        st.info("🔄 Pipeline running — this may take a few minutes...")
        st.progress(0.0, text="Fetching paper and tracing lineage...")

    with log_ph.container():
        logs = st.session_state.logs
        if logs:
            st.markdown(
                "<div class='log-box' id='log-box'>" +
                "<br>".join(f"<span style='color:#4ade80'>▸</span> {l}" for l in logs[-30:]) +
                "</div>"
                "<script>var el=document.getElementById('log-box');if(el)el.scrollTop=el.scrollHeight;</script>",
                unsafe_allow_html=True
            )

    done = (q and not q.empty()) or (t and not t.is_alive())
    if done:
        st.session_state.running = False
        prog_ph.empty(); log_ph.empty()
        if q and not q.empty():
            status, result, from_cache = q.get()
            if status == "success" and result:
                start = st.session_state.get("start_time")
                elapsed = (time.time() - start) if start else None
                st.session_state.elapsed_time = elapsed
                try:
                    # Build canonical API response dict (enriches secondary influences internally)
                    response = build_timeline_response(result, from_cache, elapsed)
                    st.session_state.timeline = response
                    st.session_state.from_cache = from_cache
                    # Save timeline JSON + paper text files
                    save_timeline_json(result)
                    folder, manifest = save_paper_texts(result)
                    st.session_state.save_folder = str(folder) if folder else None
                    st.session_state.save_manifest = manifest
                except Exception as _post_err:
                    st.session_state.error = f"Post-processing error: {_post_err}"
            else:
                st.session_state.error = result if status == "error" else "Pipeline returned no results."
        st.rerun()
    else:
        time.sleep(1.5)
        st.rerun()


# ── Error ─────────────────────────────────────────────────────────────────────
if st.session_state.error and not st.session_state.running:
    st.error(f"❌ {st.session_state.error}")


# ══════════════════════════════════════════════════════════════════════════════
# TIMELINE VIEW
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.timeline and not st.session_state.running:
    resp  = st.session_state.timeline   # API response dict
    chain = resp["chain"]               # oldest → newest

    # ── Cache badge ──
    if resp.get("from_cache"):
        st.info("⚡ Results served from cache")

    # ── Summary metrics ──
    yr    = resp.get("year_range", {})
    span  = yr.get("span")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Seed Paper",      (resp["seed_paper"].get("title","?")[:28] + "..."))
    m2.metric("Papers in Chain", resp["total_papers"])
    m3.metric("Time Span",       f"{span} yrs" if isinstance(span, int) else "—")
    m4.metric("Year Range",      f"{yr.get('start','?')} → {yr.get('end','?')}")
    elapsed = resp.get("elapsed_time")
    m5.metric("⏱ Total Time",   f"{elapsed:.1f}s" if elapsed else "—")

    # ── Saved files info ──
    if st.session_state.save_folder and st.session_state.save_manifest:
        manifest = st.session_state.save_manifest
        full_count = sum(1 for p in manifest if p["source_type"] != "ABSTRACT_ONLY")
        abs_count  = sum(1 for p in manifest if p["source_type"] == "ABSTRACT_ONLY")
        st.success(
            f"💾 Paper texts saved → `{st.session_state.save_folder}`  "
            f"·  {full_count} full text  ·  {abs_count} abstract only"
        )
        with st.expander("📂 Saved files", expanded=False):
            for p in manifest:
                src_icon = "📋" if p["source_type"] == "ABSTRACT_ONLY" else "📄"
                found_tag = " 🏛" if p["is_foundational"] else ""
                st.markdown(
                    f"`{p['file']}`  {src_icon} **{p['source_type']}**"
                    f"  ·  {p['chars']:,} chars{found_tag}"
                )

    st.divider()

    # ── Tabs ──
    tab_timeline, tab_raw = st.tabs(["📅 Timeline View", "🗂 Raw JSON"])

    # ════════════════════════
    # Timeline tab
    # ════════════════════════
    with tab_timeline:
        st.markdown("##### Research Lineage &nbsp;·&nbsp; oldest → newest")
        st.markdown("")

        for i, entry in enumerate(chain):
            paper   = entry["paper"]
            ta      = entry["analysis"]
            comp    = entry["comparison"]
            bt      = (ta.get("breakthrough_level") or "minor").lower()
            icon    = BREAKTHROUGH_ICONS.get(bt, "○")
            source  = entry["source_type"]
            is_f    = entry["is_foundational"]

            pill = (
                "<span class='pill-foundation'>🏛 Foundation</span>" if is_f
                else "<span class='pill-abstract'>◐ Abstract Only</span>" if source == "ABSTRACT_ONLY"
                else "<span class='pill-full'>● Full Text</span>"
            )
            badge = f"<span class='badge-{bt}'>{icon} {bt.upper()}</span>"
            cites = f"{paper.get('citation_count',0):,} citations" if paper.get("citation_count") else ""

            # Card HTML
            st.markdown(f"""
            <div class='paper-card'>
                <div style='display:flex;justify-content:space-between;align-items:flex-start;gap:12px;'>
                    <div style='flex:1;'>
                        <span class='year-chip'>{paper.get('year','?')}</span>&nbsp;&nbsp;
                        {badge}&nbsp;&nbsp;{pill}
                        <h4 style='margin:10px 0 6px 0;font-size:16px;font-weight:600;'>
                            {paper.get('title','Unknown')}
                        </h4>
                    </div>
                    <div style='color:#7c85a2;font-size:12px;white-space:nowrap;'>{cites}</div>
                </div>
                <p style='color:#94a3b8;font-size:13px;margin:6px 0 0 0;'>
                    📌 <b>Key Innovation:</b> {ta.get('key_innovation','—')}
                </p>
            </div>
            """, unsafe_allow_html=True)

            # Expandable detail
            with st.expander("Show details", expanded=False):
                d1, d2 = st.columns(2)
                with d1:
                    st.markdown("**Problem Addressed**")
                    st.write(ta.get("problem_addressed", "—"))
                    st.markdown("**Core Method**")
                    st.write(ta.get("core_method", "—"))
                with d2:
                    st.markdown("**ELI5**")
                    st.write(ta.get("explanation_eli5", "—"))
                    st.markdown("**Intuitive Explanation**")
                    st.write(ta.get("explanation_intuitive", "—"))

                if ta.get("explanation_technical"):
                    st.markdown("**Technical Explanation**")
                    st.write(ta.get("explanation_technical"))

                if comp:
                    st.markdown("---")
                    st.markdown("**📈 How the next paper improved on this one**")
                    cc1, cc2 = st.columns(2)
                    with cc1:
                        st.markdown("*What was improved*")
                        st.write(comp.get("what_was_improved", "—"))
                        st.markdown("*Why it matters*")
                        st.write(comp.get("why_it_matters", "—"))
                    with cc2:
                        st.markdown("*How it was improved*")
                        st.write(comp.get("how_it_was_improved", "—"))
                        st.markdown("*Problem solved from predecessor*")
                        st.write(comp.get("problem_solved_from_predecessor", "—"))

                sec = entry.get("secondary_influences", [])
                if sec:
                    st.markdown("---")
                    st.markdown("**🔗 Secondary Influences**")
                    for inf in sec:
                        if isinstance(inf, dict):
                            contrib = inf.get("contribution", "")
                            title   = inf.get("title", "")
                            year    = inf.get("year", "")
                            pid     = inf.get("paper_id", "")
                            label   = f"{title} ({year})" if title else (pid[:20] + "..." if pid else "Unknown")
                            st.markdown(f"- **{label}** — {contrib}")
                        else:
                            st.markdown(f"- {inf}")

                if paper.get("abstract"):
                    st.markdown("---")
                    st.markdown("**Abstract**")
                    ab = paper["abstract"]
                    st.caption(ab[:800] + ("..." if len(ab) > 800 else ""))

            # Connector arrow (not after last card)
            if i < len(chain) - 1:
                st.markdown("<div class='connector'>↓</div>", unsafe_allow_html=True)

    # ════════════════════════
    # Raw JSON tab
    # ════════════════════════
    with tab_raw:
        st.download_button(
            "⬇️ Download JSON",
            data=json.dumps(resp, indent=2),
            file_name=f"lineage_{resp['seed_paper'].get('paper_id','output')}.json",
            mime="application/json",
        )
        st.json(resp, expanded=False)


# ── Empty state ───────────────────────────────────────────────────────────────
elif not st.session_state.running and not st.session_state.error:
    st.markdown("""
    <div style='text-align:center;padding:60px 0;color:#3b4268;'>
        <div style='font-size:56px;margin-bottom:16px;'>🔬</div>
        <div style='font-size:18px;font-weight:600;color:#475569;'>
            Enter a paper ID above to trace its research lineage
        </div>
        <div style='font-size:13px;color:#3b4268;margin-top:8px;'>
            Supports arXiv IDs, arXiv URLs, or Semantic Scholar paper IDs
        </div>
        <div style='margin-top:28px;display:flex;gap:16px;justify-content:center;flex-wrap:wrap;'>
            <code style='background:#1a1d27;padding:6px 16px;border-radius:8px;color:#6c63ff;font-size:13px;'>1706.03762 — Attention Is All You Need</code>
            <code style='background:#1a1d27;padding:6px 16px;border-radius:8px;color:#6c63ff;font-size:13px;'>1512.03385 — ResNet</code>
            <code style='background:#1a1d27;padding:6px 16px;border-radius:8px;color:#6c63ff;font-size:13px;'>1406.2661 — GANs</code>
        </div>
    </div>
    """, unsafe_allow_html=True)