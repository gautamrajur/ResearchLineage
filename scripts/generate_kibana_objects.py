#!/usr/bin/env python3
"""
Generate Kibana saved objects (NDJSON) for ResearchLineage ELK stack monitoring.

Uses the legacy `visualization` type (aggregation-based) which is fully
compatible with Kibana 9.x saved-objects import.  Lens visualizations cause
HTTP 500 on import in Kibana 9.x.

Output: kibana/researchlineage_kibana.ndjson

Usage:
    python scripts/generate_kibana_objects.py
"""
import json
import os

AIRFLOW_IDX = "rl-idx-airflow"
CLM_IDX = "rl-idx-all"   # combined wildcard for Centralized Log Management
IDX_REF = "kibanaSavedObjectMeta.searchSourceJSON.index"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _search_source(query: str = "", idx_ref: str = IDX_REF) -> str:
    return json.dumps({
        "query": {"language": "kuery", "query": query},
        "filter": [],
        "indexRefName": idx_ref,
    })


def _idx_ref(idx_id: str) -> dict:
    return {"type": "index-pattern", "id": idx_id, "name": IDX_REF}


def _terms_agg(agg_id: str, field: str, size: int = 15,
               metric_ref: str = "1", order: str = "desc") -> dict:
    return {
        "id": agg_id, "enabled": True, "type": "terms", "schema": "segment",
        "params": {
            "field": field, "size": size,
            "order": order, "orderBy": metric_ref,
            "otherBucket": False, "otherBucketLabel": "Other",
            "missingBucket": False, "missingBucketLabel": "Missing",
        },
    }


def _date_histogram_agg(agg_id: str, schema: str = "segment") -> dict:
    return {
        "id": agg_id, "enabled": True,
        "type": "date_histogram", "schema": schema,
        "params": {
            "field": "@timestamp", "interval": "auto",
            "time_zone": "UTC", "drop_partials": False,
            "min_doc_count": 1, "extended_bounds": {},
        },
    }


def _count_agg(agg_id: str = "1") -> dict:
    return {"id": agg_id, "enabled": True, "type": "count",
            "schema": "metric", "params": {}}


def _cardinality_agg(agg_id: str, field: str) -> dict:
    return {"id": agg_id, "enabled": True, "type": "cardinality",
            "schema": "metric", "params": {"field": field}}


def _split_terms_agg(agg_id: str, field: str, size: int = 5) -> dict:
    return {
        "id": agg_id, "enabled": True, "type": "terms", "schema": "group",
        "params": {
            "field": field, "size": size, "order": "desc", "orderBy": "1",
            "otherBucket": False, "otherBucketLabel": "Other",
            "missingBucket": False, "missingBucketLabel": "Missing",
        },
    }


def _xy_axes(y_label: str = "Count", cat_label: str = "") -> tuple:
    cat_axes = [{
        "id": "CategoryAxis-1", "type": "category", "position": "bottom",
        "show": True, "style": {}, "scale": {"type": "linear"},
        "labels": {"show": True, "filter": True, "truncate": 100},
        "title": {"text": cat_label} if cat_label else {},
    }]
    val_axes = [{
        "id": "ValueAxis-1", "name": "LeftAxis-1", "type": "value",
        "position": "left", "show": True, "style": {},
        "scale": {"type": "linear", "mode": "normal"},
        "labels": {"show": True, "rotate": 0, "filter": False, "truncate": 100},
        "title": {"text": y_label},
    }]
    return cat_axes, val_axes


def _series_param(series_type: str, mode: str = "normal",
                  label: str = "Count") -> dict:
    return {
        "show": True, "type": series_type, "mode": mode,
        "data": {"label": label, "id": "1"},
        "drawLinesBetweenPoints": True, "lineWidth": 2,
        "interpolate": "linear", "showCircles": True, "circleSize": 3,
        "valueAxis": "ValueAxis-1",
    }


# ---------------------------------------------------------------------------
# Object builders
# ---------------------------------------------------------------------------

def index_pattern(id: str, title: str, time_field: str = "@timestamp") -> dict:
    return {
        "type": "index-pattern",
        "id": id,
        "attributes": {"title": title, "timeFieldName": time_field},
        "references": [],
    }


def vis_pie(id: str, title: str, idx_id: str,
            group_field: str, size: int = 10, query: str = "") -> dict:
    vis_state = json.dumps({
        "type": "pie",
        "aggs": [_count_agg(), _terms_agg("2", group_field, size)],
        "params": {
            "type": "pie", "addTooltip": True, "addLegend": True,
            "legendPosition": "right", "isDonut": False,
        },
    })
    return {
        "type": "visualization", "id": id,
        "attributes": {
            "title": title, "visState": vis_state,
            "uiStateJSON": "{}", "description": "",
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source(query)},
        },
        "references": [_idx_ref(idx_id)],
    }


def vis_area(id: str, title: str, idx_id: str, split_field: str | None = None,
             stacked: bool = True, query: str = "", val_label: str = "Count") -> dict:
    cat_axes, val_axes = _xy_axes(y_label=val_label)
    aggs = [_count_agg(), _date_histogram_agg("2")]
    if split_field:
        aggs.append(_split_terms_agg("3", split_field))
    vis_state = json.dumps({
        "type": "area",
        "aggs": aggs,
        "params": {
            "type": "area",
            "grid": {"categoryLines": False},
            "categoryAxes": cat_axes,
            "valueAxes": val_axes,
            "seriesParams": [_series_param(
                "area", "stacked" if stacked else "normal")],
            "addTooltip": True, "addLegend": True,
            "legendPosition": "right", "times": [],
            "addTimeMarker": False,
            "thresholdLine": {"show": False, "value": 10, "width": 1,
                              "style": "full", "color": "#E7664C"},
            "labels": {},
        },
    })
    return {
        "type": "visualization", "id": id,
        "attributes": {
            "title": title, "visState": vis_state,
            "uiStateJSON": "{}", "description": "",
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source(query)},
        },
        "references": [_idx_ref(idx_id)],
    }


def vis_line(id: str, title: str, idx_id: str,
             split_field: str | None = None, query: str = "", val_label: str = "Count") -> dict:
    cat_axes, val_axes = _xy_axes(y_label=val_label)
    aggs = [_count_agg(), _date_histogram_agg("2")]
    if split_field:
        aggs.append(_split_terms_agg("3", split_field, size=3))
    vis_state = json.dumps({
        "type": "line",
        "aggs": aggs,
        "params": {
            "type": "line",
            "grid": {"categoryLines": False},
            "categoryAxes": cat_axes,
            "valueAxes": val_axes,
            "seriesParams": [_series_param("line")],
            "addTooltip": True, "addLegend": True,
            "legendPosition": "right", "times": [],
            "addTimeMarker": False,
            "thresholdLine": {"show": False, "value": 10, "width": 1,
                              "style": "full", "color": "#E7664C"},
            "labels": {},
        },
    })
    return {
        "type": "visualization", "id": id,
        "attributes": {
            "title": title, "visState": vis_state,
            "uiStateJSON": "{}", "description": "",
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source(query)},
        },
        "references": [_idx_ref(idx_id)],
    }


def vis_hbar(id: str, title: str, idx_id: str, field: str,
             size: int = 15, query: str = "",
             cat_label: str = "", val_label: str = "Count") -> dict:
    """Horizontal bar — best for ranked categorical data (loggers, DAGs, tasks)."""
    cat_axes, val_axes = _xy_axes(y_label=val_label, cat_label=cat_label)
    # For horizontal_bar, category axis is on the left
    cat_axes[0]["position"] = "left"
    val_axes[0]["position"] = "bottom"
    vis_state = json.dumps({
        "type": "horizontal_bar",
        "aggs": [_count_agg(), _terms_agg("2", field, size)],
        "params": {
            "type": "histogram",
            "grid": {"categoryLines": False},
            "categoryAxes": cat_axes,
            "valueAxes": val_axes,
            "seriesParams": [_series_param("histogram")],
            "addTooltip": True, "addLegend": False,
            "legendPosition": "right", "times": [],
            "addTimeMarker": False,
            "thresholdLine": {"show": False, "value": 10, "width": 1,
                              "style": "full", "color": "#E7664C"},
            "labels": {"show": False},
        },
    })
    return {
        "type": "visualization", "id": id,
        "attributes": {
            "title": title, "visState": vis_state,
            "uiStateJSON": "{}", "description": "",
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source(query)},
        },
        "references": [_idx_ref(idx_id)],
    }


def vis_vbar(id: str, title: str, idx_id: str, field: str,
             size: int = 20, metric_agg: dict | None = None,
             query: str = "",
             cat_label: str = "", val_label: str = "Count") -> dict:
    """Vertical bar — for task IDs, depth buckets, etc."""
    cat_axes, val_axes = _xy_axes(y_label=val_label, cat_label=cat_label)
    agg_metric = metric_agg if metric_agg is not None else _count_agg()
    terms = _terms_agg("2", field, size, metric_ref=agg_metric["id"])
    vis_state = json.dumps({
        "type": "histogram",
        "aggs": [agg_metric, terms],
        "params": {
            "type": "histogram",
            "grid": {"categoryLines": False},
            "categoryAxes": cat_axes,
            "valueAxes": val_axes,
            "seriesParams": [_series_param("histogram")],
            "addTooltip": True, "addLegend": False,
            "legendPosition": "right", "times": [],
            "addTimeMarker": False,
            "thresholdLine": {"show": False, "value": 10, "width": 1,
                              "style": "full", "color": "#E7664C"},
            "labels": {"show": False},
        },
    })
    return {
        "type": "visualization", "id": id,
        "attributes": {
            "title": title, "visState": vis_state,
            "uiStateJSON": "{}", "description": "",
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source(query)},
        },
        "references": [_idx_ref(idx_id)],
    }


def vis_metric(id: str, title: str, idx_id: str,
               label: str = "Count", query: str = "") -> dict:
    vis_state = json.dumps({
        "type": "metric",
        "aggs": [{"id": "1", "enabled": True, "type": "count",
                  "schema": "metric", "params": {}}],
        "params": {
            "addTooltip": True, "addLegend": False, "type": "metric",
            "metric": {
                "percentageMode": False, "useRanges": False,
                "colorSchema": "Green to Red",
                "metricColorMode": "None",
                "colorsRange": [{"from": 0, "to": 10000}],
                "labels": {"show": True}, "invertColors": False,
                "style": {"bgFill": "#000", "bgColor": False,
                          "labelColor": False, "subText": label,
                          "fontSize": 60},
            },
        },
    })
    return {
        "type": "visualization", "id": id,
        "attributes": {
            "title": title, "visState": vis_state,
            "uiStateJSON": "{}", "description": "",
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source(query)},
        },
        "references": [_idx_ref(idx_id)],
    }


def saved_search(id: str, title: str, idx_id: str, query_str: str = "",
                 columns: list | None = None, description: str = "") -> dict:
    if columns is None:
        columns = ["@timestamp", "level", "logger", "message", "paper_id"]
    search_source = json.dumps({
        "highlightAll": True, "version": True,
        "query": {"language": "kuery", "query": query_str},
        "filter": [], "indexRefName": IDX_REF,
    })
    return {
        "type": "search", "id": id,
        "attributes": {
            "title": title, "description": description,
            "columns": columns, "sort": [["@timestamp", "desc"]],
            "kibanaSavedObjectMeta": {"searchSourceJSON": search_source},
        },
        "references": [_idx_ref(idx_id)],
    }


def _panel(panel_id: str, obj_type: str,
           x: int, y: int, w: int, h: int) -> dict:
    return {
        "version": "9.3.3",
        "type": obj_type,
        "gridData": {"x": x, "y": y, "w": w, "h": h, "i": panel_id},
        "panelIndex": panel_id,
        "embeddableConfig": {"enhancements": {}},
        "panelRefName": panel_id,
    }


def dashboard(id: str, title: str, description: str,
              panels: list, references: list) -> dict:
    return {
        "type": "dashboard", "id": id,
        "attributes": {
            "title": title, "description": description,
            "panelsJSON": json.dumps(panels),
            "optionsJSON": json.dumps({
                "hidePanelTitles": False, "useMargins": True,
                "syncColors": False, "syncCursor": True,
                "syncTooltips": False,
            }),
            "timeRestore": False, "version": 1,
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps({
                    "query": {"language": "kuery", "query": ""}, "filter": []
                })
            },
        },
        "references": references,
    }


# ---------------------------------------------------------------------------
# Build all saved objects
# ---------------------------------------------------------------------------

objects: list[dict] = []

# ── Index Patterns ──────────────────────────────────────────────────────────
objects.append(index_pattern(AIRFLOW_IDX, "researchlineage-airflow-*"))
objects.append(index_pattern(CLM_IDX, "researchlineage-*"))  # combined: app + airflow

# ===========================================================================
# Centralized Log Management — new index pattern + visualizations + dashboard
# All objects use the rl-idx-all (researchlineage-*) combined index unless
# a source-specific breakdown is explicitly needed.
# ===========================================================================

# ── CLM Viz 1: Total Log Count (Metric — all sources) ────────────────────
objects.append(vis_metric(
    "rl-viz-clm-total", "[RL] Total Log Count",
    CLM_IDX, label="Total Logs",
))

# ── CLM Viz 2: Error Count Across All Sources (Metric) ───────────────────
objects.append(vis_metric(
    "rl-viz-clm-errors", "[RL] Total Errors (All Sources)",
    CLM_IDX, label="Errors",
    query='level: "ERROR"',
))

# ── CLM Viz 3: Warning Count Across All Sources (Metric) ─────────────────
objects.append(vis_metric(
    "rl-viz-clm-warnings", "[RL] Total Warnings (All Sources)",
    CLM_IDX, label="Warnings",
    query='level: "WARNING"',
))

# ── CLM Viz 4: Log Count by Source — App vs Airflow (Pie) ────────────────
objects.append(vis_pie(
    "rl-viz-clm-source", "[RL] Logs by Source (App vs Airflow)",
    CLM_IDX, "log_type.keyword", size=5,
))

# ── CLM Viz 5: All Log Volume Over Time split by Source (Area) ───────────
objects.append(vis_area(
    "rl-viz-clm-volume", "[RL] All Log Volume by Source",
    CLM_IDX, split_field="log_type.keyword", stacked=True,
    val_label="Log Count",
))

# ── CLM Viz 6: Log Level Distribution Across All Sources (Pie) ───────────
objects.append(vis_pie(
    "rl-viz-clm-level", "[RL] Log Level Distribution (All Sources)",
    CLM_IDX, "level.keyword", size=10,
))

# ── CLM Viz 7: Error & Warning Timeline Across All Sources (Line) ────────
objects.append(vis_line(
    "rl-viz-clm-err-timeline", "[RL] Error & Warning Timeline (All Sources)",
    CLM_IDX, split_field="level.keyword",
    query='level: "ERROR" or level: "WARNING"',
    val_label="Events",
))

# ── CLM Viz 8: Top Loggers / Modules Across All Sources (Horizontal Bar) ─
objects.append(vis_hbar(
    "rl-viz-clm-loggers", "[RL] Top Loggers (All Sources)",
    CLM_IDX, "logger.keyword", size=15,
    cat_label="Logger / Component", val_label="Log Count",
))

# ── CLM Viz 9: Log Volume by DAG — from app JSON logs (Horizontal Bar) ───
objects.append(vis_hbar(
    "rl-viz-clm-dags", "[RL] Log Volume by DAG (All Sources)",
    CLM_IDX, "dag_id.keyword", size=10,
    query="dag_id: *",
    cat_label="DAG ID", val_label="Log Count",
))

# ── CLM Viz 10: Task Execution Activity — by task_id (Vertical Bar) ──────
objects.append(vis_vbar(
    "rl-viz-clm-tasks", "[RL] Task Execution Activity (All Sources)",
    CLM_IDX, "task_id.keyword", size=20,
    query="task_id: *",
    cat_label="Task ID", val_label="Log Count",
))

# ── CLM Viz 11: Airflow Raw Task Log Timeline (Area — airflow index) ──────
objects.append(vis_area(
    "rl-viz-clm-airflow", "[RL] Airflow Raw Task Logs Timeline",
    AIRFLOW_IDX, stacked=False,
    val_label="Log Count",
))

# ── CLM Saved Search: All Logs Stream (all sources, all levels) ───────────
objects.append(saved_search(
    "rl-search-clm-all", "[RL] All Logs Stream",
    CLM_IDX,
    query_str="",
    columns=["@timestamp", "log_type", "level", "logger", "message",
             "dag_id", "task_id", "paper_id"],
    description="All logs across app scripts, Airflow DAGs, and tasks — combined live stream",
))

# ── Dashboard 3: Centralized Log Management ───────────────────────────────
#
#  Row 1 (y=0,  h=8):  [Total 12w]  [Errors 12w]  [Warnings 12w]  [Source Pie 12w]
#  Row 2 (y=8,  h=14): [Volume by Source 32w]  [Level Pie 16w]
#  Row 3 (y=22, h=14): [Error Timeline 32w]  [Top Loggers 16w]
#  Row 4 (y=36, h=14): [DAGs hbar 24w]  [Tasks vbar 24w]
#  Row 5 (y=50, h=14): [Airflow Raw Timeline 48w]
#  Row 6 (y=64, h=22): [All Logs Table 48w]

clm_panels = [
    _panel("q01", "visualization",  0,  0, 12,  8),  # total metric
    _panel("q02", "visualization", 12,  0, 12,  8),  # errors metric
    _panel("q03", "visualization", 24,  0, 12,  8),  # warnings metric
    _panel("q04", "visualization", 36,  0, 12,  8),  # source pie
    _panel("q05", "visualization",  0,  8, 32, 14),  # volume by source
    _panel("q06", "visualization", 32,  8, 16, 14),  # level pie all sources
    _panel("q07", "visualization",  0, 22, 32, 14),  # error timeline all sources
    _panel("q08", "visualization", 32, 22, 16, 14),  # top loggers all sources
    _panel("q09", "visualization",  0, 36, 24, 14),  # DAGs
    _panel("q10", "visualization", 24, 36, 24, 14),  # tasks
    _panel("q11", "visualization",  0, 50, 48, 14),  # airflow raw timeline
    _panel("q12", "search",         0, 64, 48, 22),  # all logs live stream
]
clm_refs = [
    {"type": "visualization", "id": "rl-viz-clm-total",        "name": "q01"},
    {"type": "visualization", "id": "rl-viz-clm-errors",       "name": "q02"},
    {"type": "visualization", "id": "rl-viz-clm-warnings",     "name": "q03"},
    {"type": "visualization", "id": "rl-viz-clm-source",       "name": "q04"},
    {"type": "visualization", "id": "rl-viz-clm-volume",       "name": "q05"},
    {"type": "visualization", "id": "rl-viz-clm-level",        "name": "q06"},
    {"type": "visualization", "id": "rl-viz-clm-err-timeline", "name": "q07"},
    {"type": "visualization", "id": "rl-viz-clm-loggers",      "name": "q08"},
    {"type": "visualization", "id": "rl-viz-clm-dags",         "name": "q09"},
    {"type": "visualization", "id": "rl-viz-clm-tasks",        "name": "q10"},
    {"type": "visualization", "id": "rl-viz-clm-airflow",      "name": "q11"},
    {"type": "search",        "id": "rl-search-clm-all",       "name": "q12"},
]
objects.append(dashboard(
    "rl-dash-logs", "[RL] Centralized Log Management",
    "All ResearchLineage logs in one place — app scripts, Airflow DAGs, "
    "and individual pipeline tasks. Filter by source, level, logger, or DAG.",
    clm_panels, clm_refs,
))

# ---------------------------------------------------------------------------
# Write NDJSON
# ---------------------------------------------------------------------------

out_dir = os.path.join(os.path.dirname(__file__), "..", "kibana")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "researchlineage_kibana.ndjson")

with open(out_path, "w") as fh:
    for obj in objects:
        fh.write(json.dumps(obj, separators=(",", ":")) + "\n")

print(f"Wrote {len(objects)} objects → {os.path.abspath(out_path)}")
for obj in objects:
    print(f"  {obj['type']:16s}  {obj['id']}")
