"""
ui.py

The DRIFTLY dashboard, built with NiceGUI. Visual identity: a dark blue
storm sky - the metaphor is literal. A calm, operational source is a quiet
night sky with the odd distant flicker; a degraded or failing source fills
the sky with black cloud and frequent lightning. "Catch the change before
it breaks the pipeline" is not just a tagline here, it is what the
background is doing at all times.

No icon library, no stock imagery, no emoji - every visual element here is
hand-built CSS/SVG.
"""
from __future__ import annotations

import datetime as dt

from nicegui import ui

import services
from models import IngestionEvent, IngestionRun, Job, QuarantinedRecord, Source

# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------
STYLE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root{
  --bg-top:#04060c;
  --bg-mid:#0a1330;
  --bg-bottom:#0d1c40;
  --surface:#0f1730cc;
  --surface-solid:#101a36;
  --surface-2:#141f42;
  --border:#26325c;
  --text-primary:#eef2ff;
  --text-secondary:#93a2c9;
  --text-faint:#5c6a94;
  --accent:#8ec9ff;
  --accent-bright:#f2f8ff;
  --accent-dim:#3f6fb0;
  --success:#3ddc97;
  --warning:#ffcc66;
  --error:#ff6b7a;
  --radius:10px;
  --font-display:'Space Grotesk', sans-serif;
  --font-body:'Inter', sans-serif;
  --font-mono:'JetBrains Mono', monospace;
}

*{ box-sizing:border-box; }

body{
  margin:0;
  background: linear-gradient(180deg, var(--bg-top) 0%, var(--bg-mid) 55%, var(--bg-bottom) 100%) !important;
  color: var(--text-primary);
  font-family: var(--font-body);
  min-height:100vh;
}

.nicegui-content{ padding:0 !important; }

/* ---------------- storm background ---------------- */
.storm-sky{
  position:fixed; inset:0; z-index:-1; overflow:hidden; pointer-events:none;
}
.cloud{
  position:absolute; border-radius:50%;
  background: radial-gradient(circle, rgba(4,6,12,0.95) 0%, rgba(4,6,12,0) 70%);
  filter: blur(6px);
  opacity:0.55;
  transition: opacity 1.2s ease;
}
.cloud-a{ width:900px; height:420px; top:-120px; left:-200px; animation: driftA 90s linear infinite; }
.cloud-b{ width:700px; height:360px; top:60px; right:-260px; animation: driftB 120s linear infinite; }
.cloud-c{ width:1100px; height:500px; bottom:-260px; left:20%; animation: driftC 150s linear infinite; opacity:0.4;}
@keyframes driftA{ 0%{transform:translateX(0);} 50%{transform:translateX(120px);} 100%{transform:translateX(0);} }
@keyframes driftB{ 0%{transform:translateX(0);} 50%{transform:translateX(-140px);} 100%{transform:translateX(0);} }
@keyframes driftC{ 0%{transform:translateX(0);} 50%{transform:translateX(90px);} 100%{transform:translateX(0);} }

.bolt{ position:absolute; width:90px; opacity:0; filter: drop-shadow(0 0 14px var(--accent)); }
.bolt path{ fill: var(--accent-bright); }
.bolt-1{ top:6%; left:18%; animation: flash 9s ease-in-out infinite; animation-delay:1.2s; }
.bolt-2{ top:10%; right:22%; width:70px; animation: flash 13s ease-in-out infinite; animation-delay:5s; }
@keyframes flash{
  0%, 92%, 100% { opacity:0; }
  93% { opacity:0.9; }
  94% { opacity:0.1; }
  95% { opacity:0.8; }
  97% { opacity:0; }
}

/* status-driven storm intensity */
body.storm-degraded .cloud{ opacity:0.75; }
body.storm-degraded .bolt-1{ animation-duration:4.5s; }
body.storm-degraded .bolt-2{ animation-duration:6s; }

body.storm-severe .cloud{ opacity:0.92; filter: blur(4px); }
body.storm-severe .bolt-1{ animation-duration:2.2s; }
body.storm-severe .bolt-2{ animation-duration:2.8s; }
body.storm-severe .bolt path{ fill:#fff; }

body.storm-recovering .cloud{ opacity:0.5; transition: opacity 3s ease; }
body.storm-recovering .bolt-1{ animation-duration:6s; }

body.storm-easter .bolt{ animation-duration:0.6s !important; opacity:0.9 !important; }

/* ---------------- layout ---------------- */
.shell{ max-width:1180px; margin:0 auto; padding:48px 24px 96px; }
.hero{ padding:40px 0 28px; border-bottom:1px solid var(--border); margin-bottom:32px; }
.wordmark{ font-family:var(--font-display); font-weight:700; font-size:44px; letter-spacing:-0.02em; margin:0; }
.tagline{ font-family:var(--font-display); font-size:17px; color:var(--accent); margin:6px 0 4px; }
.supporting{ color:var(--text-secondary); font-size:14px; margin:0 0 20px; }

.status-badge{
  display:inline-flex; align-items:center; gap:10px;
  padding:9px 16px; border-radius:999px; border:1px solid var(--border);
  background: var(--surface); font-family:var(--font-mono); font-size:12.5px; letter-spacing:0.06em;
}
.status-dot{ width:8px; height:8px; border-radius:50%; background:var(--text-faint); }
.status-OPERATIONAL .status-dot{ background:var(--success); box-shadow:0 0 8px var(--success); }
.status-DEGRADED .status-dot{ background:var(--warning); box-shadow:0 0 8px var(--warning); }
.status-RECOVERING .status-dot{ background:var(--accent); box-shadow:0 0 8px var(--accent); }
.status-SOURCE_UNAVAILABLE .status-dot, .status-UNAVAILABLE .status-dot{ background:var(--error); box-shadow:0 0 8px var(--error); }
.status-IDLE .status-dot{ background:var(--text-faint); }
.status-detail{ color:var(--text-secondary); font-family:var(--font-body); font-size:13px; margin-top:10px; }

.section-label{
  font-family:var(--font-mono); text-transform:uppercase; letter-spacing:0.14em; font-size:12px;
  color:var(--text-faint); margin:40px 0 14px;
}

.panel{
  background: var(--surface); border:1px solid var(--border); border-radius: var(--radius);
  padding:20px; backdrop-filter: blur(6px);
}

.metrics-grid{ display:grid; grid-template-columns:repeat(4, 1fr); gap:14px; }
.metric-card{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:16px 18px; }
.metric-value{ font-family:var(--font-mono); font-size:26px; font-weight:600; }
.metric-label{ color:var(--text-secondary); font-size:12.5px; margin-top:4px; }

.pipeline{ display:flex; align-items:center; gap:6px; overflow-x:auto; padding:6px 2px; }
.stage{
  flex:1; min-width:112px; text-align:center; padding:14px 8px; border-radius:8px;
  border:1px solid var(--border); background:var(--surface-2); font-family:var(--font-mono); font-size:11.5px;
  letter-spacing:0.05em; color:var(--text-secondary);
}
.stage.success{ border-color:var(--success); color:var(--success); }
.stage.warning{ border-color:var(--warning); color:var(--warning); }
.stage.error{ border-color:var(--error); color:var(--error); }
.stage-arrow{ color:var(--text-faint); font-family:var(--font-mono); }

.timeline{ display:flex; flex-direction:column; gap:0; }
.event-row{ display:flex; gap:16px; padding:12px 0; border-bottom:1px solid var(--border); }
.event-row:last-child{ border-bottom:none; }
.event-time{ font-family:var(--font-mono); font-size:12px; color:var(--text-faint); min-width:150px; }
.event-type{ font-family:var(--font-mono); font-size:12px; padding:2px 8px; border-radius:4px; height:fit-content; }
.event-type.INFO{ background:#16324a; color:var(--accent); }
.event-type.WARNING{ background:#3a3212; color:var(--warning); }
.event-type.ERROR{ background:#3a1620; color:var(--error); }
.event-message{ color:var(--text-secondary); font-size:13.5px; }

.job-row{ display:flex; justify-content:space-between; gap:16px; padding:14px 0; border-bottom:1px solid var(--border); }
.job-row:last-child{ border-bottom:none; }
.job-title{ font-weight:600; font-size:14.5px; }
.job-meta{ color:var(--text-secondary); font-size:12.5px; margin-top:2px; }
.job-source{ font-family:var(--font-mono); font-size:11px; color:var(--text-faint); white-space:nowrap; }

.empty-state{ color:var(--text-secondary); font-size:13.5px; padding:24px 4px; }

.chaos-grid{ display:grid; grid-template-columns:repeat(4, 1fr); gap:12px; margin-top:14px; }
.chaos-btn{
  background:var(--surface-2) !important; border:1px solid var(--border) !important; color:var(--text-primary) !important;
  font-family:var(--font-mono) !important; font-size:11.5px !important; letter-spacing:0.05em !important;
  border-radius:8px !important; padding:14px 10px !important; text-transform:none !important; width:100%;
}
.chaos-btn:hover{ border-color:var(--accent) !important; color:var(--accent) !important; }
.chaos-result{ margin-top:16px; font-family:var(--font-mono); font-size:12.5px; color:var(--text-secondary); white-space:pre-line; }

.source-health{ display:grid; grid-template-columns:repeat(2,1fr); gap:12px; font-size:13px; }
.source-health div span.k{ color:var(--text-faint); display:block; font-size:11.5px; margin-bottom:2px; }
.source-health div span.v{ font-family:var(--font-mono); }

.run-btn{
  background: linear-gradient(180deg, #244a86, #16305c) !important; color:#eef2ff !important;
  border:1px solid var(--accent-dim) !important; font-family:var(--font-mono) !important;
  letter-spacing:0.05em !important; text-transform:none !important; border-radius:8px !important;
}

.footer-note{ margin-top:56px; color:var(--text-faint); font-size:12px; font-family:var(--font-mono); }

/* easter egg overlay */
.egg-overlay{
  position:fixed; inset:0; z-index:999; display:none; align-items:center; justify-content:center;
  background: rgba(4,6,12,0.86); backdrop-filter: blur(4px);
}
.egg-overlay.active{ display:flex; }
.egg-box{
  font-family:var(--font-mono); color:var(--accent-bright); font-size:15px; line-height:1.9;
  border:1px solid var(--accent-dim); padding:26px 32px; border-radius:10px; background:var(--surface-solid);
  box-shadow:0 0 40px rgba(142,201,255,0.25);
}
.egg-title{ color:var(--accent); font-weight:700; letter-spacing:0.06em; margin-bottom:10px; }

@media (max-width: 900px){
  .metrics-grid{ grid-template-columns:repeat(2,1fr); }
  .chaos-grid{ grid-template-columns:repeat(2,1fr); }
}
@media (max-width: 600px){
  .shell{ padding:28px 16px 64px; }
  .wordmark{ font-size:32px; }
  .metrics-grid{ grid-template-columns:1fr 1fr; gap:10px; }
  .metric-value{ font-size:20px; }
  .pipeline{ flex-wrap:wrap; }
  .stage{ min-width:88px; }
  .chaos-grid{ grid-template-columns:1fr 1fr; }
  .source-health{ grid-template-columns:1fr; }
  .event-time{ min-width:110px; }
}
"""

BACKGROUND_HTML = """
<div class="storm-sky" id="storm-sky">
  <div class="cloud cloud-a"></div>
  <div class="cloud cloud-b"></div>
  <div class="cloud cloud-c"></div>
  <svg class="bolt bolt-1" viewBox="0 0 100 200" xmlns="http://www.w3.org/2000/svg">
    <path d="M55 0 L20 110 L48 110 L35 200 L85 90 L55 90 Z"/>
  </svg>
  <svg class="bolt bolt-2" viewBox="0 0 100 200" xmlns="http://www.w3.org/2000/svg">
    <path d="M60 0 L25 100 L50 100 L30 200 L90 80 L58 80 Z"/>
  </svg>
</div>
<div class="egg-overlay" id="egg-overlay">
  <div class="egg-box">
    <div class="egg-title">YOU FOUND THE DRIFT.</div>
    <div id="egg-lines"></div>
  </div>
</div>
<script>
(function(){
  const sequence = ["ArrowUp","ArrowUp","ArrowDown","ArrowDown","ArrowLeft","ArrowRight","ArrowLeft","ArrowRight","b","a"];
  let progress = 0;
  window.addEventListener('keydown', function(e){
    const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    if (key === sequence[progress]) {
      progress++;
      if (progress === sequence.length) {
        progress = 0;
        triggerEasterEgg();
      }
    } else {
      progress = (key === sequence[0]) ? 1 : 0;
    }
  });

  function triggerEasterEgg(){
    const overlay = document.getElementById('egg-overlay');
    const lines = document.getElementById('egg-lines');
    const script = ["source stable", "anomaly detected", "easter_egg = true", "nice catch."];
    lines.innerHTML = "";
    document.body.classList.add('storm-easter');
    overlay.classList.add('active');
    script.forEach(function(line, i){
      setTimeout(function(){
        const div = document.createElement('div');
        div.textContent = "> " + line;
        lines.appendChild(div);
      }, i * 450);
    });
    setTimeout(function(){
      overlay.classList.remove('active');
      document.body.classList.remove('storm-easter');
    }, script.length * 450 + 2200);
  }
})();
</script>
"""

STATUS_TO_STORM_CLASS = {
    "OPERATIONAL": "storm-calm",
    "IDLE": "storm-calm",
    "DEGRADED": "storm-degraded",
    "RECOVERING": "storm-recovering",
    "SOURCE UNAVAILABLE": "storm-severe",
    "UNAVAILABLE": "storm-severe",
}


def _fmt_dt(value: dt.datetime | None) -> str:
    if value is None:
        return "--"
    return value.strftime("%Y-%m-%d %H:%M:%S UTC")


def _fmt_secs(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.2f}s"


def _apply_storm_class(state: str) -> None:
    css_class = STATUS_TO_STORM_CLASS.get(state, "storm-calm")
    ui.run_javascript(f"document.body.className = '{css_class}';")


# ---------------------------------------------------------------------------
# Refreshable sections
# ---------------------------------------------------------------------------
@ui.refreshable
def status_section() -> None:
    status = services.get_system_status()
    badge_class = status.state.replace(" ", "_")
    with ui.element("div"):
        ui.html(
            f'<div class="status-badge status-{badge_class}">'
            f'<span class="status-dot"></span>{status.state}</div>'
        )
        ui.html(f'<div class="status-detail">{status.detail}</div>')
    _apply_storm_class(status.state)


@ui.refreshable
def metrics_section() -> None:
    m = services.get_metrics()
    cards = [
        ("Total Jobs", m["total_jobs"]),
        ("Successful Runs", m["successful_runs"]),
        ("Failed / Degraded Runs", m["failed_runs"]),
        ("Duplicates Skipped", m["duplicates"]),
        ("Quarantined Records", m["quarantined"]),
        ("Records Stored", m["records_stored"]),
        ("Last Successful Ingestion", _fmt_dt(m["last_success_at"])),
        ("Avg Ingestion Duration", _fmt_secs(m["avg_duration_seconds"])),
    ]
    with ui.element("div").classes("metrics-grid"):
        for label, value in cards:
            with ui.element("div").classes("metric-card"):
                ui.html(f'<div class="metric-value">{value}</div>')
                ui.html(f'<div class="metric-label">{label}</div>')

    if m["successful_runs"] == 0 and m["failed_runs"] == 0:
        ui.html('<div class="empty-state">No ingestion runs yet. Run an ingestion to begin building source history.</div>')


PIPELINE_STAGES = ["SOURCE", "FETCH", "DETECT", "VALIDATE", "NORMALIZE", "DEDUPLICATE", "STORE"]


@ui.refreshable
def pipeline_section() -> None:
    runs = services.list_runs(limit=1)
    last = runs[0] if runs else None

    def stage_class(stage: str) -> str:
        if last is None:
            return ""
        if last.status == "SUCCESS":
            return "success"
        if last.status in ("DEGRADED",) and stage in ("DETECT", "SOURCE"):
            return "warning"
        if last.status == "FAILED" and stage in ("SOURCE", "FETCH"):
            return "error"
        return "success" if last.status == "SUCCESS" else ""

    with ui.element("div").classes("pipeline"):
        for i, stage in enumerate(PIPELINE_STAGES):
            cls = stage_class(stage)
            ui.html(f'<div class="stage {cls}">{stage}</div>')
            if i < len(PIPELINE_STAGES) - 1:
                ui.html('<div class="stage-arrow">&rarr;</div>')


@ui.refreshable
def source_health_section() -> None:
    source: Source | None = services.get_source_health()
    if source is None:
        ui.html('<div class="empty-state">No source configured.</div>')
        return
    fields = [
        ("Source", source.name),
        ("Status", source.status),
        ("Last Successful Run", _fmt_dt(source.last_success)),
        ("Last Failure", _fmt_dt(source.last_failure)),
        ("Latency", _fmt_secs(source.last_latency)),
        ("Consecutive Failures", source.consecutive_failures),
    ]
    with ui.element("div").classes("source-health"):
        for k, v in fields:
            ui.html(f'<div><span class="k">{k}</span><span class="v">{v}</span></div>')


@ui.refreshable
def timeline_section() -> None:
    events: list[IngestionEvent] = services.list_events(limit=15)
    if not events:
        ui.html('<div class="empty-state">No events yet. Run an ingestion or a Chaos Lab simulation to populate the timeline.</div>')
        return
    with ui.element("div").classes("timeline"):
        for ev in events:
            ui.html(
                f'<div class="event-row">'
                f'<div class="event-time">{_fmt_dt(ev.created_at)}</div>'
                f'<div class="event-type {ev.severity}">{ev.event_type}</div>'
                f'<div class="event-message">{ev.message}</div>'
                f'</div>'
            )


@ui.refreshable
def activity_section(filter_value: dict) -> None:
    events: list[IngestionEvent] = services.list_events(severity=filter_value.get("severity") or None, limit=60)
    if not events:
        ui.html('<div class="empty-state">No matching events.</div>')
        return
    with ui.element("div").classes("timeline"):
        for ev in events:
            ui.html(
                f'<div class="event-row">'
                f'<div class="event-time">{_fmt_dt(ev.created_at)}</div>'
                f'<div class="event-type {ev.severity}">{ev.event_type}</div>'
                f'<div class="event-message">{ev.message}</div>'
                f'</div>'
            )


@ui.refreshable
def jobs_section(filter_value: dict) -> None:
    jobs: list[Job] = services.list_jobs(search=filter_value.get("search") or None, source=None, limit=100)
    if not jobs:
        ui.html('<div class="empty-state">No jobs ingested yet. Run an ingestion to populate this list.</div>')
        return
    with ui.element("div"):
        for job in jobs:
            ui.html(
                f'<div class="job-row">'
                f'<div><div class="job-title">{job.title}</div>'
                f'<div class="job-meta">{job.company} &middot; {job.location} &middot; '
                f'{_fmt_dt(job.published_at) if job.published_at else "date unknown"}</div></div>'
                f'<div class="job-source">{job.source}</div>'
                f'</div>'
            )


@ui.refreshable
def quarantine_section() -> None:
    rows: list[QuarantinedRecord] = services.list_quarantine(limit=10)
    if not rows:
        ui.html('<div class="empty-state">Nothing quarantined. Validation and schema checks have not rejected any records.</div>')
        return
    with ui.element("div").classes("timeline"):
        for r in rows:
            ui.html(
                f'<div class="event-row">'
                f'<div class="event-time">{_fmt_dt(r.created_at)}</div>'
                f'<div class="event-type WARNING">QUARANTINED</div>'
                f'<div class="event-message">{r.reason}</div>'
                f'</div>'
            )


chaos_result_state = {"text": ""}


@ui.refreshable
def chaos_result_section() -> None:
    if chaos_result_state["text"]:
        ui.html(f'<div class="chaos-result">{chaos_result_state["text"]}</div>')


def refresh_all() -> None:
    status_section.refresh()
    metrics_section.refresh()
    pipeline_section.refresh()
    source_health_section.refresh()
    timeline_section.refresh()
    quarantine_section.refresh()


def run_ingestion_clicked() -> None:
    outcome = services.trigger_ingestion()
    chaos_result_state["text"] = (
        f"Manual ingestion finished: {outcome.status}\n"
        f"received={outcome.records_received} valid={outcome.records_valid} "
        f"stored={outcome.records_stored} duplicate={outcome.records_duplicate} "
        f"quarantined={outcome.records_failed}"
    )
    ui.notify(f"Ingestion {outcome.status.lower()}", color="primary")
    refresh_all()
    chaos_result_section.refresh()


def make_chaos_handler(fn, label: str):
    def handler() -> None:
        outcome = fn()
        chaos_result_state["text"] = f"{label} -> run status: {outcome.status} (run #{outcome.run_id})"
        ui.notify(label, color="warning")
        refresh_all()
        chaos_result_section.refresh()

    return handler


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def build_dashboard() -> None:
    import chaos as chaos_mod

    ui.add_head_html(f"<style>{STYLE_CSS}</style>")
    ui.add_body_html(BACKGROUND_HTML)

    with ui.element("div").classes("shell"):
        # Hero
        with ui.element("div").classes("hero"):
            ui.html('<div class="wordmark">DRIFTLY</div>')
            ui.html('<div class="tagline">Catch the change before it breaks the pipeline.</div>')
            ui.html('<div class="supporting">Reliable job-data ingestion for a changing web.</div>')
            status_section()

        # System status / manual run
        with ui.row().classes("items-center").style("gap:16px; margin-bottom:8px;"):
            ui.button("Run ingestion", on_click=run_ingestion_clicked).props("unelevated no-caps").classes("run-btn")
            ui.label("Manually trigger the pipeline described below.").style(
                "color:var(--text-secondary); font-size:12.5px;"
            )

        ui.html('<div class="section-label">Metrics</div>')
        with ui.element("div").classes("panel"):
            metrics_section()

        ui.html('<div class="section-label">Pipeline</div>')
        with ui.element("div").classes("panel"):
            pipeline_section()

        ui.html('<div class="section-label">Source Health</div>')
        with ui.element("div").classes("panel"):
            source_health_section()

        ui.html('<div class="section-label">Recovery Timeline</div>')
        with ui.element("div").classes("panel"):
            timeline_section()

        ui.html('<div class="section-label">Quarantine</div>')
        with ui.element("div").classes("panel"):
            quarantine_section()

        # Jobs
        ui.html('<div class="section-label">Jobs</div>')
        job_filter = {"search": ""}
        with ui.element("div").classes("panel"):
            with ui.row().style("margin-bottom:14px; width:100%;"):
                search_input = ui.input(placeholder="Search title or company").style("flex:1;")

                def on_search(e=None) -> None:
                    job_filter["search"] = search_input.value
                    jobs_section.refresh(job_filter)

                search_input.on("keydown.enter", on_search)
                ui.button("Search", on_click=on_search).props("unelevated no-caps").classes("run-btn")
            jobs_section(job_filter)

        # Activity
        ui.html('<div class="section-label">Activity</div>')
        activity_filter = {"severity": ""}
        with ui.element("div").classes("panel"):
            with ui.row().style("margin-bottom:14px; gap:8px;"):
                def make_sev_handler(sev: str):
                    def handler() -> None:
                        activity_filter["severity"] = sev
                        activity_section.refresh(activity_filter)

                    return handler

                for sev_label, sev_value in [("All", ""), ("Info", "INFO"), ("Warning", "WARNING"), ("Error", "ERROR")]:
                    ui.button(sev_label, on_click=make_sev_handler(sev_value)).props(
                        "unelevated no-caps"
                    ).classes("chaos-btn").style("width:auto; padding:8px 14px !important;")
            activity_section(activity_filter)

        # Chaos Lab
        ui.html('<div class="section-label">Chaos Lab</div>')
        with ui.element("div").classes("panel"):
            ui.html(
                '<div style="color:var(--text-secondary); font-size:13.5px;">'
                "Controlled failure simulation for testing DRIFTLY's recovery behavior. "
                "Each button drives the real ingestion pipeline against a fake, in-process "
                "source - nothing here ever touches an external service."
                "</div>"
            )
            with ui.element("div").classes("chaos-grid"):
                ui.button(
                    "SIMULATE RATE LIMIT",
                    on_click=make_chaos_handler(chaos_mod.simulate_rate_limit, "Rate limit simulated"),
                ).props("unelevated no-caps").classes("chaos-btn")
                ui.button(
                    "SIMULATE EMPTY RESPONSE",
                    on_click=make_chaos_handler(chaos_mod.simulate_empty_response, "Empty response simulated"),
                ).props("unelevated no-caps").classes("chaos-btn")
                ui.button(
                    "SIMULATE SOURCE FAILURE",
                    on_click=make_chaos_handler(chaos_mod.simulate_source_failure, "Source failure simulated"),
                ).props("unelevated no-caps").classes("chaos-btn")
                ui.button(
                    "SIMULATE SCHEMA DRIFT",
                    on_click=make_chaos_handler(chaos_mod.simulate_schema_drift, "Schema drift simulated"),
                ).props("unelevated no-caps").classes("chaos-btn")
            chaos_result_section()

        ui.html(
            '<div class="footer-note">DRIFTLY &middot; single-process Python app &middot; '
            "no fabricated metrics, testimonials, or uptime claims - every number above comes from SQLite.</div>"
        )


def register_pages() -> None:
    @ui.page("/")
    def index() -> None:
        build_dashboard()
