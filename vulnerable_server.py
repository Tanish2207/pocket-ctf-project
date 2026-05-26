#!/usr/bin/env python3
"""VJTI IntraNet Monitor — Internal diagnostic tool.
WARNING: Intentionally vulnerable for CTF training.
"""
import html
import os
from datetime import datetime

from flask import Flask, request

app = Flask(__name__)

# ── Shared CSS ────────────────────────────────────────────────────────────────
_CSS = """
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;display:flex;min-height:100vh;font-size:14px}
.sidebar{width:230px;background:#161b22;border-right:1px solid #30363d;display:flex;flex-direction:column;flex-shrink:0}
.brand{padding:18px 20px;border-bottom:1px solid #30363d}
.brand-name{font-size:13px;font-weight:600;color:#58a6ff}
.brand-sub{font-size:11px;color:#8b949e;margin-top:2px}
.status-chip{display:inline-flex;align-items:center;gap:5px;background:#0d2119;border:1px solid #1a4731;border-radius:20px;padding:3px 10px;font-size:10px;color:#3fb950;margin-top:8px}
.dot{width:6px;height:6px;border-radius:50%;background:#3fb950;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
nav{padding:12px 0;flex:1}
.nav-section{padding:6px 16px 4px;font-size:10px;color:#484f58;text-transform:uppercase;letter-spacing:.8px}
nav a{display:flex;align-items:center;gap:10px;padding:8px 20px;color:#8b949e;text-decoration:none;font-size:13px;transition:all .15s}
nav a:hover{background:#21262d;color:#c9d1d9}
nav a.active{background:#21262d;color:#f0f6fc;border-right:2px solid #58a6ff}
.sidebar-footer{padding:14px 20px;border-top:1px solid #30363d;font-size:10px;color:#484f58}
.main{flex:1;overflow-y:auto}
.topbar{background:#161b22;border-bottom:1px solid #30363d;padding:12px 28px;display:flex;align-items:center;justify-content:space-between}
.page-title{font-size:15px;font-weight:600;color:#f0f6fc}
.breadcrumb{font-size:11px;color:#8b949e;margin-top:2px}
.topbar-meta{font-size:11px;color:#8b949e;text-align:right}
.content{padding:24px 28px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px 22px;margin-bottom:20px}
.card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.card-title{font-size:13px;font-weight:600;color:#f0f6fc}
.card-badge{font-size:10px;padding:2px 8px;border-radius:20px;background:#1f6feb22;border:1px solid #1f6feb66;color:#58a6ff}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:20px}
.stat-card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px 18px}
.stat-label{font-size:11px;color:#8b949e;margin-bottom:6px}
.stat-value{font-size:22px;font-weight:700;color:#f0f6fc}
.stat-value.green{color:#3fb950}.stat-value.blue{color:#58a6ff}.stat-value.yellow{color:#d29922}
label{display:block;font-size:11px;color:#8b949e;margin-bottom:6px}
.input-row{display:flex;gap:10px;align-items:flex-end}
input[type=text]{flex:1;background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:8px 12px;border-radius:6px;font-family:'Courier New',monospace;font-size:13px;outline:none;transition:border-color .15s}
input[type=text]:focus{border-color:#58a6ff}
.btn{background:#238636;color:#fff;border:none;padding:9px 20px;border-radius:6px;cursor:pointer;font-size:13px;white-space:nowrap;transition:background .15s}
.btn:hover{background:#2ea043}
.btn-link{display:inline-block;text-decoration:none}
.terminal{background:#010409;border:1px solid #30363d;border-radius:6px;padding:16px;font-family:'Courier New',monospace;font-size:12px;color:#3fb950;white-space:pre-wrap;word-break:break-all;min-height:80px;margin-top:16px;line-height:1.6}
.terminal.empty{color:#484f58;font-style:italic}
.activity{width:100%;border-collapse:collapse;font-size:12px}
.activity th{text-align:left;color:#484f58;font-weight:500;padding:6px 10px;border-bottom:1px solid #21262d}
.activity td{padding:7px 10px;border-bottom:1px solid #21262d;color:#8b949e}
.activity td:first-child{color:#c9d1d9;font-family:monospace}
.tag{font-size:10px;padding:1px 7px;border-radius:20px}
.tag-green{background:#0d2119;color:#3fb950;border:1px solid #1a4731}
.tag-blue{background:#0c1d3a;color:#58a6ff;border:1px solid #1f3d7a}
.tag-red{background:#2d0f0f;color:#f85149;border:1px solid #5a1a1a}
</style>
"""


def _sidebar(active: str) -> str:
    links = [
        ("home",   "/",           "⊞", "Dashboard"),
        ("ping",   "/ping-tool",  "⟳", "Network Ping"),
        ("health", "/health",     "♥", "System Health"),
        ("logs",   "/logs",       "≡", "Log Viewer"),
    ]
    items = ""
    for k, href, icon, label in links:
        cls = ' class="active"' if k == active else ""
        items += (
            f'<a href="{href}"{cls}>'
            f'<span style="width:16px;text-align:center">{icon}</span>{label}</a>\n'
        )
    return f"""
<div class="sidebar">
  <div class="brand">
    <div class="brand-name">⬡ VJTI IntraNet Monitor</div>
    <div class="brand-sub">Internal Systems · VJTI Mumbai</div>
    <div class="status-chip"><span class="dot"></span> ALL SYSTEMS OPERATIONAL</div>
  </div>
  <nav>
    <div class="nav-section">Diagnostics</div>
    {items}
  </nav>
  <div class="sidebar-footer">VJTI-INTRANET v2.4.1 &nbsp;·&nbsp; Internal Use Only</div>
</div>"""


def _page(active: str, title: str, breadcrumb: str, body: str) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IntraNet Monitor — VJTI</title>{_CSS}</head>
<body>
{_sidebar(active)}
<div class="main">
  <div class="topbar">
    <div>
      <div class="page-title">{title}</div>
      <div class="breadcrumb">{breadcrumb}</div>
    </div>
    <div class="topbar-meta">Refreshed: {now}<br>Session: admin@vjti.ac.in</div>
  </div>
  <div class="content">{body}</div>
</div>
</body></html>"""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    body = """
    <div class="stats">
      <div class="stat-card"><div class="stat-label">Services Online</div><div class="stat-value green">7 / 7</div></div>
      <div class="stat-card"><div class="stat-label">Active Connections</div><div class="stat-value blue">142</div></div>
      <div class="stat-card"><div class="stat-label">Alerts (24 h)</div><div class="stat-value yellow">3</div></div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Recent Diagnostic Activity</span><span class="card-badge">LIVE</span></div>
      <table class="activity">
        <thead><tr><th>Timestamp</th><th>Host</th><th>Tool</th><th>Status</th></tr></thead>
        <tbody>
          <tr><td>2025-04-29 06:58:12</td><td>192.168.1.10</td><td>Network Ping</td><td><span class="tag tag-green">OK</span></td></tr>
          <tr><td>2025-04-29 06:45:03</td><td>db-server-01</td><td>Network Ping</td><td><span class="tag tag-green">OK</span></td></tr>
          <tr><td>2025-04-29 06:30:44</td><td>192.168.1.55</td><td>Network Ping</td><td><span class="tag tag-red">TIMEOUT</span></td></tr>
          <tr><td>2025-04-29 06:15:21</td><td>gateway.vjti.ac.in</td><td>System Health</td><td><span class="tag tag-green">OK</span></td></tr>
          <tr><td>2025-04-29 06:00:09</td><td>mail-server</td><td>Network Ping</td><td><span class="tag tag-blue">SLOW</span></td></tr>
        </tbody>
      </table>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Quick Actions</span></div>
      <p style="font-size:12px;color:#8b949e;margin-bottom:14px">
        Use the <strong style="color:#c9d1d9">Network Ping</strong> tool to verify host reachability from the intranet backbone.
      </p>
      <a href="/ping-tool" class="btn btn-link">Open Network Ping →</a>
    </div>"""
    return _page("home", "Dashboard", "IntraNet Monitor › Dashboard", body)


@app.route("/ping-tool")
def ping_tool():
    host = request.args.get("host", "").strip()
    if host:
        # !! INTENTIONALLY VULNERABLE — unsanitised shell injection !!
        raw = os.popen(f"ping -c1 -W1 {host} 2>&1").read()
        out = f'<div class="terminal">{html.escape(raw)}</div>'
    else:
        out = '<div class="terminal empty">No output yet. Enter a host above and click Ping.</div>'

    body = f"""
    <div class="card">
      <div class="card-header">
        <span class="card-title">Network Ping Diagnostic</span>
        <span class="card-badge">ICMP</span>
      </div>
      <p style="font-size:12px;color:#8b949e;margin-bottom:16px">
        Enter a hostname or IP address to verify reachability via ICMP ping.
        Results are returned directly from the server.
      </p>
      <form method="GET" action="/ping-tool">
        <label for="host">Host / IP Address</label>
        <div class="input-row">
          <input type="text" id="host" name="host" value="{html.escape(host)}"
                 placeholder="e.g. 192.168.1.1 or gateway.vjti.ac.in" autocomplete="off">
          <button type="submit" class="btn">⟳ Ping Host</button>
        </div>
      </form>
      {out}
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Usage Notes</span></div>
      <p style="font-size:12px;color:#8b949e;line-height:1.7">
        Runs <code style="color:#c9d1d9">ping -c1</code> from the server against the supplied target.
        For bulk connectivity checks contact <code style="color:#c9d1d9">noc@vjti.ac.in</code>.
      </p>
    </div>"""
    return _page("ping", "Network Ping", "IntraNet Monitor › Network Ping", body)


@app.route("/health")
def health():
    raw = html.escape(
        os.popen("uptime 2>&1; echo '---'; df -h / 2>&1; echo '---'; free -m 2>&1").read()
    )
    body = f"""
    <div class="card">
      <div class="card-header">
        <span class="card-title">System Health Report</span><span class="card-badge">LIVE</span>
      </div>
      <p style="font-size:12px;color:#8b949e;margin-bottom:14px">
        Live snapshot of server uptime, disk usage, and memory.
      </p>
      <div class="terminal">{raw}</div>
    </div>"""
    return _page("health", "System Health", "IntraNet Monitor › System Health", body)


@app.route("/logs")
def logs():
    raw = html.escape(
        os.popen(
            "tail -25 /var/log/syslog 2>/dev/null "
            "|| tail -25 /var/log/kern.log 2>/dev/null "
            "|| echo 'No system logs available.'"
        ).read()
    )
    body = f"""
    <div class="card">
      <div class="card-header">
        <span class="card-title">System Log Viewer</span><span class="card-badge">TAIL -25</span>
      </div>
      <p style="font-size:12px;color:#8b949e;margin-bottom:14px">
        Last 25 lines from <code style="color:#c9d1d9">/var/log/syslog</code>.
      </p>
      <div class="terminal">{raw}</div>
    </div>"""
    return _page("logs", "Log Viewer", "IntraNet Monitor › Log Viewer", body)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
