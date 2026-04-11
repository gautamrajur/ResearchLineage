"""
demo_ui/app.py — ResearchLineage Combined Demo UI

Calls the backend REST API (POST /analyze) and renders both views:
  Tab 1: Evolution Timeline  — linear ancestry chain traced by Gemini
  Tab 2: Predecessor/Successor Tree — bidirectional D3.js tree

Run:
    pip install streamlit httpx
    streamlit run src/backend/demo_ui/app.py

The API URL defaults to http://localhost:8000. Change it in the sidebar
if the backend is running elsewhere (e.g. a deployed container).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import json
import httpx
import streamlit as st
import streamlit.components.v1 as components

from tree_viz import get_tree_html

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ResearchLineage",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed",
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
#MainMenu, footer { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stSidebar"] { display: none; }
[data-testid="collapsedControl"] { display: none; }
.block-container { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)

BREAKTHROUGH_ICONS = {"revolutionary": "🔥", "major": "⚡", "moderate": "💡", "minor": "○"}

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in {"result": None, "error": None}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("## 🔬 ResearchLineage")
st.markdown("<p style='color:#7c85a2;margin-top:-12px;font-size:14px;'>Trace the intellectual ancestry of any research paper</p>", unsafe_allow_html=True)
st.divider()

# ── Center input + controls ───────────────────────────────────────────────────
_, center_col, _ = st.columns([1, 2, 1])
with center_col:
    api_url = st.text_input("API URL", value="http://localhost:8000", help="Backend API base URL")

    paper_id = st.text_input(
        "Paper ID",
        placeholder="e.g. 1706.03762 or ARXIV:1706.03762",
        label_visibility="collapsed",
        help="arXiv ID, arXiv URL, or Semantic Scholar paper ID",
    )

    st.markdown("**Evolution Timeline**")
    max_depth_evolution = st.slider("Max depth (timeline)", 2, 6, 4, help="How many steps back Gemini traces")

    st.markdown("**Predecessor/Successor Tree**")
    max_depth_tree = st.slider("Max depth (tree)", 1, 3, 2)
    max_children   = st.slider("Max children per node", 3, 10, 5)
    window_years   = st.slider("Citation window (years)", 1, 5, 3, help="Years after publication to look for descendants")

    analyze_btn = st.button(
        "🚀 Analyze",
        use_container_width=True,
        type="primary",
        disabled=not paper_id.strip(),
    )
st.divider()

# ── API call ──────────────────────────────────────────────────────────────────
if analyze_btn and paper_id.strip():
    st.session_state.result = None
    st.session_state.error  = None

    payload = {
        "paper_id":             paper_id.strip(),
        "max_depth_evolution":  max_depth_evolution,
        "max_depth_tree":       max_depth_tree,
        "max_children":         max_children,
        "window_years":         window_years,
    }

    with st.spinner("⏳ Analyzing paper... this may take several minutes for fresh results"):
        try:
            resp = httpx.post(
                f"{api_url.rstrip('/')}/analyze",
                json=payload,
                timeout=600.0,
            )
            if resp.status_code == 200:
                st.session_state.result = resp.json()
            elif resp.status_code == 404:
                st.session_state.error = f"Paper not found: {paper_id}"
            else:
                st.session_state.error = f"API error {resp.status_code}: {resp.text[:300]}"
        except httpx.ConnectError:
            st.session_state.error = f"Cannot connect to API at {api_url}. Is the backend running?"
        except httpx.TimeoutException:
            st.session_state.error = "Request timed out (600s). Try reducing depth or check backend logs."
        except Exception as e:
            st.session_state.error = str(e)

# ── Error ─────────────────────────────────────────────────────────────────────
if st.session_state.error:
    st.error(f"❌ {st.session_state.error}")

# ── Results ───────────────────────────────────────────────────────────────────
if st.session_state.result:
    result   = st.session_state.result
    timeline = result.get("timeline")
    tree     = result.get("tree")
    elapsed  = result.get("elapsed", {})

    # Summary metrics row
    m1, m2, m3, m4, m5 = st.columns(5)
    if timeline:
        yr   = timeline.get("year_range", {})
        span = yr.get("span")
        m1.metric("Seed Paper",      (timeline["seed_paper"].get("title", "?")[:28] + "..."))
        m2.metric("Papers in Chain", timeline.get("total_papers", "—"))
        m3.metric("Time Span",       f"{span} yrs" if isinstance(span, int) else "—")
        m4.metric("Year Range",      f"{yr.get('start','?')} → {yr.get('end','?')}")
    m5.metric("Total Elapsed", f"{elapsed.get('total_sec', 0):.1f}s")

    if timeline and timeline.get("from_cache"):
        st.info("⚡ Results served from cache")

    st.divider()

    # Tabs
    tab_timeline, tab_tree, tab_raw = st.tabs(["📅 Evolution Timeline", "🌳 Predecessor/Successor Tree", "🗂 Raw JSON"])

    # ════════════════════════════════════════
    # Tab 1 — Evolution Timeline
    # ════════════════════════════════════════
    with tab_timeline:
        if not timeline:
            st.warning("Timeline not available for this paper.")
        else:
            chain = timeline.get("chain", [])
            st.markdown(f"##### Research Lineage &nbsp;·&nbsp; oldest → newest &nbsp;·&nbsp; {len(chain)} papers &nbsp;·&nbsp; _{elapsed.get('evolution_sec', 0):.1f}s_")
            st.markdown("")

            for i, entry in enumerate(chain):
                paper  = entry["paper"]
                ta     = entry["analysis"]
                comp   = entry["comparison"]
                bt     = (ta.get("breakthrough_level") or "minor").lower()
                icon   = BREAKTHROUGH_ICONS.get(bt, "○")
                source = entry["source_type"]
                is_f   = entry["is_foundational"]

                pill = (
                    "<span class='pill-foundation'>🏛 Foundation</span>" if is_f
                    else "<span class='pill-abstract'>◐ Abstract Only</span>" if source == "ABSTRACT_ONLY"
                    else "<span class='pill-full'>● Full Text</span>"
                )
                badge = f"<span class='badge-{bt}'>{icon} {bt.upper()}</span>"
                cites = f"{paper.get('citation_count', 0):,} citations" if paper.get("citation_count") else ""

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
                                label = f"{inf.get('title','')} ({inf.get('year','')})" if inf.get('title') else inf.get('paper_id','')[:20]
                                st.markdown(f"- **{label}** — {inf.get('contribution','')}")
                            else:
                                st.markdown(f"- {inf}")

                    if paper.get("abstract"):
                        st.markdown("---")
                        st.markdown("**Abstract**")
                        ab = paper["abstract"]
                        st.caption(ab[:800] + ("..." if len(ab) > 800 else ""))

                if i < len(chain) - 1:
                    st.markdown("<div class='connector'>↓</div>", unsafe_allow_html=True)

    # ════════════════════════════════════════
    # Tab 2 — Predecessor/Successor Tree
    # ════════════════════════════════════════
    with tab_tree:
        if not tree:
            st.warning("Tree not available for this paper.")
        else:
            st.markdown(f"##### Bidirectional Research Tree &nbsp;·&nbsp; _{elapsed.get('tree_sec', 0):.1f}s_")
            st.caption("Blue = ancestors (papers this paper cited) · Red = target · Green = descendants (papers that cited this)")
            tree_html = get_tree_html(tree)
            components.html(tree_html, height=950, scrolling=True)

    # ════════════════════════════════════════
    # Tab 3 — Raw JSON
    # ════════════════════════════════════════
    with tab_raw:
        seed_id = result.get("paper_id", "output").replace(":", "_").replace("/", "_")
        st.download_button(
            "⬇️ Download full JSON",
            data=json.dumps(result, indent=2),
            file_name=f"researchlineage_{seed_id}.json",
            mime="application/json",
        )
        st.json(result, expanded=False)

# ── Empty state ───────────────────────────────────────────────────────────────
elif not st.session_state.error:
    st.markdown("""
    <div style='text-align:center;padding:60px 0;color:#3b4268;'>
        <div style='font-size:56px;margin-bottom:16px;'>🔬</div>
        <div style='font-size:18px;font-weight:600;color:#475569;'>
            Enter a paper ID above and click Analyze
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
