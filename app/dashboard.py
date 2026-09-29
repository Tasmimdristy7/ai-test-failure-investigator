from __future__ import annotations

import json
import html
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

from investigator.clustering import cluster_failures
from investigator.fingerprints import fingerprint_failure, normalize_failure_text

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "artifacts"
SERVICE_COLORS = ["#177E89", "#BF4E30", "#367C54", "#D49A24", "#6457A6"]

st.set_page_config(
    page_title="Failure Intelligence",
    page_icon="FI",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """
    <style>
      [data-testid="stAppViewContainer"] { background: #f4f5f1; }
    [data-testid="stAppViewBlockContainer"], .block-container { padding-top: 1.25rem !important; padding-bottom: 2rem; }
      [data-testid="stHeader"] { background: transparent; }
      [data-testid="stSidebar"] { background: #e9ede7; }
      [data-testid="stMetric"] { border-bottom: 1px solid #cbd2ca; padding: 8px 0 12px; }
      [data-testid="stMetricLabel"] { color: #4c5a52; }
    [data-testid="stMetricValue"], [data-testid="stMarkdownContainer"],
    [data-testid="stCaptionContainer"] { color: #18251e; }
    h1 { color: #18251e; font-size: 2rem !important; line-height: 1.2 !important; margin: 0.2rem 0 0.45rem !important; }
    h2, h3 { color: #18251e; }
      code { color: #245e53; }
    </style>
    """,
    unsafe_allow_html=True,
)


def read_report(path: Optional[Path]) -> Dict[str, Any]:
    if path is None:
        return {"failures": [], "test_count": 0, "failure_count": 0}
    return json.loads(path.read_text(encoding="utf-8"))


def format_timestamp(value: Optional[str]) -> str:
    if not value:
        return "Timestamp unavailable"
    return value.replace("T", " ").replace("Z", " UTC")


st.sidebar.title("Failure Investigator")
artifact_files = sorted(
    ARTIFACT_DIR.glob("*.json"),
    key=lambda path: path.stat().st_mtime,
    reverse=True,
) if ARTIFACT_DIR.exists() else []
artifact_paths = {path.name: path for path in artifact_files}
artifact_names = list(artifact_paths)
default_artifact_index = artifact_names.index("failures.json") if "failures.json" in artifact_names else 0
selected_name = st.sidebar.selectbox(
    "Run artifact",
    options=artifact_names,
    index=default_artifact_index if artifact_paths else None,
    placeholder="Choose a run artifact",
)
threshold = st.sidebar.slider(
    "Similarity threshold",
    min_value=0.10,
    max_value=0.90,
    value=0.35,
    step=0.05,
    help="Lower values merge more wording variants, but can combine unrelated failures.",
)
demo_report_override = st.session_state.pop("dashboard_report_override", None)
selected_path = artifact_paths.get(selected_name) if selected_name else None
try:
    if demo_report_override is not None:
        report = demo_report_override
    else:
        report = read_report(selected_path)
except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
    st.error("Could not read this report: {}".format(error))
    st.stop()

failures: List[Dict[str, Any]] = report.get("failures", [])
if not isinstance(failures, list):
    st.error("The selected report must contain a list named 'failures'.")
    st.stop()

test_count = int(report.get("test_count", len(failures)))
failure_count = int(report.get("failure_count", len(failures)))
passed_count = max(0, test_count - failure_count)
fingerprints = [
    fingerprint_failure(
        failure.get("error_message", ""),
        failure.get("stack_trace", ""),
        endpoint=failure.get("endpoint"),
        status=failure.get("http_status"),
    )
    for failure in failures
]
unique_signatures = len({fingerprint.key() for fingerprint in fingerprints})
candidate_pairs = len(failures) * (len(failures) - 1) // 2
clusters = cluster_failures(failures, similarity_threshold=threshold)
independent_issues = len(clusters)
failure_rate = failure_count / test_count if test_count else 0.0

st.title("AI Test Failure Investigator")
st.subheader("See how the investigation works")
components.html(
    (ROOT / "app" / "static" / "workflow.html").read_text(encoding="utf-8"),
    height=1250,
    scrolling=True,
)

st.divider()
st.markdown("### Turn repeated test failures into focused investigations.")
st.write(
    "This project runs automated tests against a deliberately buggy e-commerce app, "
    "captures the failures, and groups similar errors so an engineer can investigate "
    "a few likely causes instead of reading every failed test separately."
)
intro_columns = st.columns(3, gap="large")
with intro_columns[0]:
    st.markdown("**01 · The application**")
    st.write("A FastAPI storefront covering login, product search, cart, checkout, orders, and profile, with 9 active intentional defects and one fixed defect.")
with intro_columns[1]:
    st.markdown("**02 · The investigator**")
    st.write("Pytest captures structured evidence. Normalization removes changing IDs and timestamps; text similarity groups related failures.")
with intro_columns[2]:
    st.markdown("**03 · The outcome**")
    st.write("Review likely causes, affected tests, and supporting evidence. The baseline demo expects 50 tests → 28 failures → 3 groups of 15, 8, and 5.")
st.info(
    "This is a controlled testing experiment: failures are intentional. "
    "The investigator uses deterministic fingerprints and TF-IDF/cosine similarity, "
    "not a generative AI model. Groups suggest where to investigate; they do not prove or repair a root cause."
)
with st.expander("Explore the full project: coverage, architecture, and current scope"):
    st.markdown("#### What is tested")
    st.dataframe(pd.DataFrame([
        {"Test layer": "Baseline demo", "Executions": 50, "Expected failures": 28, "Purpose": "Checkout crashes, expired tokens, and incorrect cart totals"},
        {"Test layer": "API contracts", "Executions": 100, "Expected failures": 11, "Purpose": "Endpoint behavior and response contracts"},
        {"Test layer": "Integration workflows", "Executions": 20, "Expected failures": 0, "Purpose": "Login → search → cart → checkout → order history"},
        {"Test layer": "Browser UI", "Executions": 5, "Expected failures": 1, "Purpose": "Real browser journeys, including a broken checkout locator"},
        {"Test layer": "Phase 1 scenarios", "Executions": 10, "Expected failures": 6, "Purpose": "Additional discount, authorization, latency, schema, and retry defects"},
    ]), hide_index=True, width="stretch")
    st.caption("These are expected counts for separate suites, not the measured results of the selected report. The demo button runs only the 50-case baseline.")
    st.markdown("#### How the parts fit together")
    st.write("FastAPI app + storefront → Pytest / Playwright tests → JSON failure reports → fingerprinting + similarity clustering → this Streamlit dashboard.")
    st.write("GitHub Actions validates expected test outcomes and uploads reports and browser evidence. Docker packages the application for local runs.")
    scope_columns = st.columns(2)
    with scope_columns[0]:
        st.markdown("**Implemented**")
        st.write("Reproducible defects, API/integration/browser tests, structured failure capture, similarity clustering, saved-report selection, and evidence inspection.")
    with scope_columns[1]:
        st.markdown("**Planned / limitations**")
        st.write("Persistent run history and PostgreSQL are later milestones. Application data is in memory. Cluster labels are heuristics; fixes still require an engineer.")
    st.markdown("#### Read the results")
    st.write("A failure is one unsuccessful test. A fingerprint keeps stable error features. A cluster groups related failures into one investigation. Lowering the sidebar threshold allows more wording variants to join; exact fingerprints remain grouped.")
st.divider()
st.subheader("Investigate a test run")
st.write("Start with the demo, or choose a saved report in the sidebar. Follow the pipeline below, then select a cluster to inspect its evidence.")
run_label = selected_name or "No report selected"
st.caption("{}  ·  {}  ·  Commit {}".format(
    run_label,
    format_timestamp(report.get("timestamp")),
    str(report.get("commit", "unknown"))[:12],
))
run_demo = st.button("Run 50-test demo", type="primary")
if run_demo:
    workflow_steps = []
    result_output = ""
    try:
        with st.status("Running failure investigation workflow", expanded=True) as workflow:
            workflow.write("**1 · Execute** Run the 50-case pytest benchmark with its three injected defects.")
            environment = os.environ.copy()
            environment["PYTEST_ADDOPTS"] = "--tb=no"
            result = subprocess.run(
                [sys.executable, str(ROOT / "run_demo.py")],
                cwd=str(ROOT),
                env=environment,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            result_output = (result.stdout + "\n" + result.stderr)[-4000:]
            if result.returncode != 0:
                raise RuntimeError("Benchmark runner failed. See captured output.")

            fresh_report = read_report(ARTIFACT_DIR / "failures.json")
            fresh_failures = fresh_report["failures"]
            workflow_steps.append({
                "stage": "Execute tests",
                "evidence": "{} tests: {} passed, {} failed".format(
                    fresh_report["test_count"],
                    fresh_report["test_count"] - fresh_report["failure_count"],
                    fresh_report["failure_count"],
                ),
            })
            workflow.write("**2 · Capture** Saved `{}` with {} structured failure records.".format(
                (ARTIFACT_DIR / "failures.json").relative_to(ROOT),
                fresh_report["failure_count"],
            ))
            workflow_steps.append({
                "stage": "Capture artifact",
                "evidence": "{} structured records in artifacts/failures.json".format(fresh_report["failure_count"]),
            })

            fresh_fingerprints = [
                fingerprint_failure(
                    failure.get("error_message", ""),
                    failure.get("stack_trace", ""),
                    endpoint=failure.get("endpoint"),
                    status=failure.get("http_status"),
                )
                for failure in fresh_failures
            ]
            signature_count = len({item.key() for item in fresh_fingerprints})
            workflow.write("**3 · Normalize** Reduced {} failure records to {} stable fingerprints.".format(
                len(fresh_failures), signature_count
            ))
            workflow_steps.append({
                "stage": "Normalize fingerprints",
                "evidence": "{} failures reduced to {} unique signatures".format(len(fresh_failures), signature_count),
            })

            fresh_clusters = cluster_failures(fresh_failures, similarity_threshold=threshold)
            pair_count = len(fresh_failures) * (len(fresh_failures) - 1) // 2
            workflow.write("**4 · Compare** TF-IDF/cosine scored {:,} candidate pairs at a {:.0%} threshold.".format(
                pair_count, threshold
            ))
            workflow_steps.append({
                "stage": "Compare failures",
                "evidence": "TF-IDF/cosine compared {:,} pairs at {:.0%}".format(pair_count, threshold),
            })
            cluster_summary = ", ".join(
                "{} ({})".format(cluster["fingerprint"]["service"], cluster["count"])
                for cluster in fresh_clusters
            )
            workflow.write("**5 · Group causes** Found {} clusters: {}.".format(
                len(fresh_clusters), cluster_summary
            ))
            workflow_steps.append({
                "stage": "Group root causes",
                "evidence": "{} clusters: {}".format(len(fresh_clusters), cluster_summary),
            })
            workflow.update(label="Workflow completed: 50 tests → 28 failures → 3 clusters", state="complete")
            fresh_report["workflow"] = {
                "returncode": 0,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "similarity_threshold": threshold,
                "steps": workflow_steps,
            }
            (ARTIFACT_DIR / "failures.json").write_text(
                json.dumps(fresh_report, indent=2),
                encoding="utf-8",
            )
            st.session_state["demo_run_result"] = {
                "returncode": 0,
                "output": result_output,
                "steps": workflow_steps,
            }
            st.session_state["dashboard_report_override"] = fresh_report
    except (OSError, RuntimeError, subprocess.TimeoutExpired, KeyError, ValueError) as error:
        st.session_state["demo_run_result"] = {
            "returncode": 1,
            "output": result_output + "\n" + str(error),
            "steps": workflow_steps,
        }
    st.rerun()

st.subheader("From test run to likely causes")
if test_count:
    st.write("This report contains **{} tests**, with **{} failures** grouped into **{} likely issues** at the current threshold. Start with the largest group, then inspect its error and affected tests.".format(test_count, failure_count, independent_issues))
else:
    st.info("No test results loaded yet. Run the demo or select a saved report to populate the investigation.")
cluster_nodes = "".join(
        "<div class='cause-node'><span class='cause-count'>{count}</span>"
        "<strong>{summary}</strong><small>{endpoint} · HTTP {status}</small></div>".format(
                count=cluster["count"],
                summary=html.escape(cluster["summary"]),
                endpoint=html.escape(cluster["fingerprint"]["endpoint"]),
                status=html.escape(str(cluster["fingerprint"]["status"])),
        )
        for cluster in clusters
)
flowchart = """
<style>
    .workflow-flow {{ color: #18251e; font-family: sans-serif; }}
    .flow-main {{ display: grid; grid-template-columns: minmax(86px, 1fr) 19px minmax(86px, 1fr) 19px minmax(86px, 1fr) 19px minmax(86px, 1fr) 19px minmax(86px, 1fr) 19px minmax(86px, 1fr); align-items: stretch; gap: 4px; }}
    .flow-node {{ min-width: 0; background: #fff; border: 1px solid #cbd2ca; border-top: 3px solid #177e89; padding: 11px 10px; min-height: 128px; }}
    .flow-node.test {{ border-top-color: #465c69; }}
    .flow-node.capture {{ border-top-color: #bf4e30; }}
    .flow-node.normalize {{ border-top-color: #d49a24; }}
    .flow-node.compare {{ border-top-color: #6457a6; }}
    .flow-node.cluster {{ border-top-color: #367c54; }}
    .flow-node.system {{ border-top-color: #465c69; }}
    .flow-kicker {{ display: block; color: #59635d; font-size: 10px; font-weight: 700; text-transform: uppercase; }}
    .flow-value {{ display: block; margin: 10px 0 5px; color: #18251e; font-size: 21px; font-weight: 700; line-height: 1.15; overflow-wrap: anywhere; }}
    .flow-detail {{ display: block; color: #59635d; font-size: 11px; line-height: 1.4; overflow-wrap: anywhere; }}
    .flow-arrow {{ align-self: center; color: #177e89; font-size: 23px; font-weight: 700; text-align: center; }}
    .flow-outcomes {{ display: flex; gap: 5px; margin-top: 9px; flex-wrap: wrap; }}
    .flow-outcomes span {{ font-size: 10px; font-weight: 700; padding: 3px 5px; }}
    .flow-pass {{ color: #286448; background: #e4efe8; }}
    .flow-fail {{ color: #963e2a; background: #f6e8e3; }}
    .flow-branch {{ width: 1px; height: 24px; margin: 0 auto; border-left: 1px solid #84968a; }}
    .flow-branch-label {{ margin: 0 0 8px; color: #59635d; font-size: 11px; font-weight: 700; text-align: center; text-transform: uppercase; }}
    .cause-nodes {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
    .cause-node {{ display: grid; grid-template-columns: 38px minmax(0, 1fr); column-gap: 8px; align-items: center; background: #fff; border: 1px solid #cbd2ca; padding: 10px; }}
    .cause-count {{ grid-row: span 2; color: #177e89; font-size: 24px; font-weight: 700; text-align: center; }}
    .cause-node strong {{ font-size: 12px; line-height: 1.3; }}
    .cause-node small {{ color: #59635d; font-size: 10px; overflow-wrap: anywhere; }}
    .dashboard-node {{ max-width: 520px; margin: 0 auto; display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 8px; align-items: center; background: #e6f0eb; border: 1px solid #abc5b6; padding: 10px 14px; }}
    .dashboard-symbol {{ color: #286448; font-size: 24px; font-weight: 700; text-align: center; }}
    .dashboard-node strong {{ display: block; font-size: 13px; }}
    .dashboard-node small {{ display: block; margin-top: 2px; color: #59635d; font-size: 11px; line-height: 1.4; }}
    .flow-footer {{ margin-top: 10px; color: #59635d; font-size: 11px; text-align: center; }}
    @media (max-width: 760px) {{ .flow-main {{ grid-template-columns: minmax(0, 1fr); gap: 3px; }} .flow-node {{ min-height: auto; }} .flow-arrow {{ transform: rotate(90deg); height: 20px; }} .cause-nodes {{ grid-template-columns: minmax(0, 1fr); }} }}
</style>
<div class="workflow-flow">
    <div class="flow-main">
        <div class="flow-node system"><span class="flow-kicker">01 · System under test</span><span class="flow-value">E-commerce app</span><span class="flow-detail">FastAPI storefront and API with 9 active reproducible defects.</span></div>
        <span class="flow-arrow">→</span>
        <div class="flow-node test"><span class="flow-kicker">02 · Test run</span><span class="flow-value">{test_count} cases</span><span class="flow-detail">Pytest checks API and app behavior.</span></div>
        <span class="flow-arrow">→</span>
        <div class="flow-node"><span class="flow-kicker">03 · Outcomes</span><span class="flow-value">{failure_count} fail</span><span class="flow-detail">Healthy and failing cases separate here.</span><div class="flow-outcomes"><span class="flow-pass">{passed_count} PASS</span><span class="flow-fail">{failure_count} FAIL</span></div></div>
        <span class="flow-arrow">→</span>
        <div class="flow-node capture"><span class="flow-kicker">04 · Failure collector</span><span class="flow-value">{failure_count} records</span><span class="flow-detail">JSON keeps errors, traces, endpoint and run metadata.</span></div>
        <span class="flow-arrow">→</span>
        <div class="flow-node normalize"><span class="flow-kicker">05 · Normalize</span><span class="flow-value">{signature_count} signatures</span><span class="flow-detail">Strip timestamps, IDs and noise; retain stable error features.</span></div>
        <span class="flow-arrow">→</span>
        <div class="flow-node compare"><span class="flow-kicker">06 · TF-IDF + cosine</span><span class="flow-value">{pair_count:,} pairs</span><span class="flow-detail">Similarity threshold {threshold:.0%}; compare within endpoint/status.</span></div>
    </div>
    <div class="flow-branch"></div>
    <p class="flow-branch-label">07 · Similar failures join into likely root causes</p>
    <div class="cause-nodes">{cluster_nodes}</div>
    <div class="flow-branch"></div>
    <div class="dashboard-node"><span class="dashboard-symbol">↗</span><span><strong>08 · Investigator dashboard</strong><small>Run totals · cluster summary · pair scores · representative error · stack trace and browser evidence</small></span></div>
    <div class="flow-footer">{cluster_count} clusters · {failure_count} individual failures reduced to {cluster_count} investigations</div>
</div>
""".format(
        test_count=test_count,
        passed_count=passed_count,
        failure_count=failure_count,
        signature_count=unique_signatures,
        pair_count=candidate_pairs,
        threshold=threshold,
        cluster_nodes=cluster_nodes,
        cluster_count=independent_issues,
)
with st.expander("Show the full flowchart for this report"):
    st.markdown(flowchart, unsafe_allow_html=True)
demo_result = st.session_state.get("demo_run_result")
workflow_result = demo_result or report.get("workflow")
if workflow_result:
    workflow_succeeded = workflow_result.get("returncode", 0) == 0
    if workflow_succeeded:
        st.success("Verified benchmark · 50 tests · 28 failures · 3 clusters")
    else:
        st.error("Benchmark did not match the expected result.")
    with st.status(
        "Latest workflow run: {}".format("verified" if workflow_succeeded else "failed"),
        state="complete" if workflow_succeeded else "error",
        expanded=False,
    ) as workflow:
        for index, step in enumerate(workflow_result.get("steps", []), start=1):
            workflow.write("**{} · {}**  {}".format(index, step["stage"], step["evidence"]))
    if demo_result and demo_result.get("output"):
        with st.expander("Show raw pytest and cluster output"):
            st.code(demo_result["output"], language="text")

st.caption(
    "Error text is normalized before TF-IDF/cosine comparison. "
    "Only matching service, endpoint, and HTTP status can be joined; "
    "the current similarity threshold is {:.0%}.".format(threshold)
)

st.divider()
metric_columns = st.columns(5)
metric_columns[0].metric("Tests", "{:,}".format(test_count))
metric_columns[1].metric("Passed", "{:,}".format(passed_count))
metric_columns[2].metric("Failed", "{:,}".format(failure_count), "{:.1%} failure rate".format(failure_rate))
metric_columns[3].metric("Likely issues", "{}".format(independent_issues))
metric_columns[4].metric("Run outcome", "Failures found" if failure_count else ("Passed" if test_count else "No data"))

st.divider()
left, right = st.columns([1.3, 1], gap="large")
with left:
    st.subheader("Failure clusters")
    if clusters:
        chart_rows = []
        for number, cluster in enumerate(clusters, start=1):
            chart_rows.append({
                "Cluster": "{:02d}  {}".format(number, cluster["summary"]),
                "Failures": cluster["count"],
                "Service": cluster["fingerprint"]["service"],
            })
        chart_data = pd.DataFrame(chart_rows)
        chart = px.bar(
            chart_data,
            x="Failures",
            y="Cluster",
            color="Service",
            orientation="h",
            text="Failures",
            color_discrete_sequence=SERVICE_COLORS,
        )
        chart.update_layout(
            height=max(260, 64 * len(chart_rows)),
            margin=dict(l=0, r=18, t=12, b=8),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="Affected tests",
            yaxis_title="",
            legend_title="Service",
        )
        chart.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(chart)
    else:
        st.info("No failures in this run.")

with right:
    st.subheader("Cluster inventory")
    if clusters:
        inventory = pd.DataFrame([
            {
                "Issue": cluster["summary"],
                "Tests": cluster["count"],
                "Endpoint": cluster["fingerprint"]["endpoint"],
                "Status": cluster["fingerprint"]["status"],
                "Similarity": "{:.0%}".format(cluster["similarity"]),
            }
            for cluster in clusters
        ])
        st.dataframe(inventory, hide_index=True, width="stretch")
    else:
        st.write("No clusters to review.")

if clusters:
    st.divider()
    st.subheader("Cluster evidence")
    cluster_choices = [
        "{:02d}  {}  ·  {} tests".format(index, cluster["summary"], cluster["count"])
        for index, cluster in enumerate(clusters, start=1)
    ]
    selected_index = st.selectbox(
        "Inspect cluster",
        options=range(len(clusters)),
        format_func=lambda index: cluster_choices[index],
        label_visibility="collapsed",
    )
    selected_cluster = clusters[selected_index]
    fingerprint = selected_cluster["fingerprint"]
    details = st.columns(4)
    details[0].metric("Service", fingerprint["service"])
    details[1].metric("Endpoint", fingerprint["endpoint"])
    details[2].metric("HTTP status", fingerprint["status"])
    details[3].metric("Mean similarity", "{:.0%}".format(selected_cluster["similarity"]))

    matching_failures = [
        failure for failure in failures
        if failure.get("test_name", "unknown") in set(selected_cluster["tests"])
    ]
    if matching_failures:
        representative = matching_failures[0]
        st.markdown("**Representative failure: raw → normalized → fingerprint**")
        raw_trace = representative.get("stack_trace", "")
        raw_text = "\n".join([
            "test={}".format(representative.get("test_name", "unknown")),
            "timestamp={}".format(representative.get("timestamp", "unknown")),
            "endpoint={}".format(representative.get("endpoint", "unknown")),
            "http_status={}".format(representative.get("http_status", "unknown")),
            "error={}".format(representative.get("error_message", "No error message recorded")),
            "trace={}".format(raw_trace[-900:]),
        ])
        normalized_text = normalize_failure_text(raw_text)
        raw_column, normalized_column = st.columns(2, gap="medium")
        with raw_column:
            st.caption("Captured error")
            st.code(raw_text, language="text")
        with normalized_column:
            st.caption("Normalized error")
            st.code(normalized_text, language="text")
        st.code(
            "service={service} | endpoint={endpoint} | status={status} | exception={exception}".format(**fingerprint),
            language="text",
        )
        comparison_examples = selected_cluster.get("comparison_examples", [])
        if comparison_examples:
            st.markdown("**Actual TF-IDF cosine comparisons**")
            comparison_rows = [
                {
                    "Failure A": pair["test_a"],
                    "Failure B": pair["test_b"],
                    "Cosine similarity": pair["score"],
                    "At/above threshold": pair["score"] >= threshold,
                }
                for pair in comparison_examples
            ]
            st.dataframe(pd.DataFrame(comparison_rows), hide_index=True, width="stretch")
        evidence_rows = [
            {
                "Test": failure.get("test_name", "unknown"),
                "Status": failure.get("http_status", "unknown"),
                "Duration (s)": round(float(failure.get("duration", 0) or 0), 3),
                "Bug": failure.get("bug_id") or "",
            }
            for failure in matching_failures
        ]
        st.dataframe(pd.DataFrame(evidence_rows), hide_index=True, width="stretch")
        with st.expander("Stack trace and captured artifacts"):
            st.code(representative.get("stack_trace", "No stack trace recorded"), language="text")
            artifact_columns = st.columns(3)
            artifact_columns[0].write("Screenshot: {}".format(representative.get("screenshot") or "not captured"))
            artifact_columns[1].write("Trace: {}".format(representative.get("trace") or "not captured"))
            artifact_columns[2].write("Network errors: {}".format(len(representative.get("network_errors", []))))