"""
Visual Dashboard Module

Generates and serves a visual dashboard for workflow monitoring.
"""

import json
import http.server
import socketserver
import threading
import webbrowser
import secrets
from pathlib import Path
from datetime import datetime
from typing import Optional

from .engine import WorkflowEngine
from .analytics import WorkflowAnalytics

# CSRF token for dashboard protection (generated per server instance)
_CSRF_TOKEN: Optional[str] = None

def _get_csrf_token() -> str:
    """Get or generate CSRF token for this server instance."""
    global _CSRF_TOKEN
    if _CSRF_TOKEN is None:
        _CSRF_TOKEN = secrets.token_urlsafe(32)
    return _CSRF_TOKEN


DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Workflow Dashboard</title>
    <style>
        :root {
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --bg-tertiary: #334155;
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --accent-blue: #3b82f6;
            --accent-green: #22c55e;
            --accent-yellow: #eab308;
            --accent-red: #ef4444;
            --accent-purple: #a855f7;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--bg-tertiary);
        }
        
        h1 {
            font-size: 1.5rem;
            font-weight: 600;
        }
        
        .status-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.875rem;
            font-weight: 500;
        }
        
        .status-active { background: var(--accent-blue); }
        .status-completed { background: var(--accent-green); }
        .status-abandoned { background: var(--accent-red); }
        .status-paused { background: var(--accent-yellow); color: #000; }
        
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        
        @media (max-width: 768px) {
            .grid { grid-template-columns: 1fr; }
        }
        
        .card {
            background: var(--bg-secondary);
            border-radius: 12px;
            padding: 20px;
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        
        .card-title {
            font-size: 1rem;
            font-weight: 600;
            color: var(--text-secondary);
        }
        
        .phase-indicator {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 20px;
        }
        
        .phase-step {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .phase-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: var(--bg-tertiary);
        }
        
        .phase-dot.completed { background: var(--accent-green); }
        .phase-dot.active { background: var(--accent-blue); animation: pulse 2s infinite; }
        .phase-dot.pending { background: var(--bg-tertiary); }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .phase-line {
            flex: 1;
            height: 2px;
            background: var(--bg-tertiary);
        }
        
        .phase-line.completed { background: var(--accent-green); }
        
        .checklist {
            list-style: none;
        }
        
        .checklist-item {
            display: flex;
            align-items: flex-start;
            gap: 12px;
            padding: 12px 0;
            border-bottom: 1px solid var(--bg-tertiary);
        }
        
        .checklist-item:last-child {
            border-bottom: none;
        }
        
        .check-icon {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            flex-shrink: 0;
            margin-top: 2px;
        }
        
        .check-completed { background: var(--accent-green); }
        .check-skipped { background: var(--accent-yellow); color: #000; }
        .check-pending { border: 2px solid var(--bg-tertiary); }
        .check-failed { background: var(--accent-red); }
        .check-progress { background: var(--accent-blue); }
        
        .item-content {
            flex: 1;
        }
        
        .item-name {
            font-weight: 500;
            margin-bottom: 4px;
        }
        
        .item-meta {
            font-size: 0.875rem;
            color: var(--text-secondary);
        }
        
        .required-badge {
            font-size: 0.75rem;
            color: var(--accent-red);
            margin-left: 8px;
        }
        
        .timeline {
            max-height: 400px;
            overflow-y: auto;
        }
        
        .timeline-item {
            display: flex;
            gap: 12px;
            padding: 10px 0;
            border-left: 2px solid var(--bg-tertiary);
            padding-left: 15px;
            margin-left: 6px;
        }
        
        .timeline-time {
            font-size: 0.75rem;
            color: var(--text-secondary);
            min-width: 50px;
        }
        
        .timeline-event {
            font-size: 0.875rem;
        }
        
        .blockers {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid var(--accent-red);
            border-radius: 8px;
            padding: 15px;
            margin-top: 15px;
        }
        
        .blockers-title {
            color: var(--accent-red);
            font-weight: 600;
            margin-bottom: 10px;
        }
        
        .blocker-item {
            font-size: 0.875rem;
            padding: 5px 0;
        }
        
        .ready-badge {
            background: rgba(34, 197, 94, 0.1);
            border: 1px solid var(--accent-green);
            border-radius: 8px;
            padding: 15px;
            margin-top: 15px;
            text-align: center;
            color: var(--accent-green);
            font-weight: 600;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }
        
        @media (max-width: 768px) {
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
        }
        
        .stat-card {
            background: var(--bg-tertiary);
            border-radius: 8px;
            padding: 15px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 1.5rem;
            font-weight: 700;
            margin-bottom: 5px;
        }
        
        .stat-label {
            font-size: 0.75rem;
            color: var(--text-secondary);
            text-transform: uppercase;
        }
        
        .refresh-btn {
            background: var(--accent-blue);
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.875rem;
        }
        
        .refresh-btn:hover {
            opacity: 0.9;
        }
        
        .no-workflow {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-secondary);
        }
        
        .no-workflow h2 {
            margin-bottom: 10px;
        }
        
        .task-description {
            font-size: 1.25rem;
            margin-bottom: 20px;
            padding: 15px;
            background: var(--bg-tertiary);
            border-radius: 8px;
            border-left: 4px solid var(--accent-blue);
        }
        
        .approve-btn {
            background: var(--accent-green);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1rem;
            font-weight: 600;
            width: 100%;
            margin-top: 15px;
        }
        
        .approve-btn:hover {
            opacity: 0.9;
        }
        
        .approve-btn:disabled {
            background: var(--bg-tertiary);
            cursor: not-allowed;
        }
    </style>
</head>
<body>
    <div class="container">
        <div id="app">
            <div class="no-workflow">
                <h2>Loading...</h2>
                <p>Fetching workflow status</p>
            </div>
        </div>
    </div>
    
    <script>
        // Dashboard state
        let currentData = null;
        
        // Fetch data from the server
        async function fetchData() {
            try {
                const response = await fetch('/api/status');
                currentData = await response.json();
                render();
            } catch (error) {
                console.error('Failed to fetch data:', error);
            }
        }
        
        // Approve current phase
        async function approvePhase() {
            try {
                // Fetch CSRF token first
                const tokenResponse = await fetch('/api/csrf-token');
                const tokenData = await tokenResponse.json();

                const response = await fetch('/api/approve', {
                    method: 'POST',
                    headers: {
                        'X-CSRF-Token': tokenData.token
                    }
                });
                const result = await response.json();
                if (result.success) {
                    fetchData();
                } else {
                    alert('Failed to approve: ' + result.message);
                }
            } catch (error) {
                console.error('Failed to approve:', error);
            }
        }
        
        // Render the dashboard
        function render() {
            const app = document.getElementById('app');
            
            if (!currentData || currentData.status === 'no_active_workflow') {
                app.innerHTML = `
                    <div class="no-workflow">
                        <h2>No Active Workflow</h2>
                        <p>Start a workflow using: <code>orchestrator start "Your task description"</code></p>
                    </div>
                `;
                return;
            }
            
            const data = currentData;
            const statusClass = 'status-' + data.status;
            
            // Build phase indicator - use phases from API if available, otherwise use current phase
            const phases = data.phases || [{id: data.current_phase.id, name: data.current_phase.name, is_current: true}];
            const currentPhaseIndex = phases.findIndex(p => p.is_current);
            
            let phaseIndicatorHtml = '<div class="phase-indicator">';
            phases.forEach((phase, i) => {
                const dotClass = phase.status === 'completed' ? 'completed' : 
                                 phase.is_current ? 'active' : 'pending';
                const phaseName = phase.name || phase.id;
                phaseIndicatorHtml += `
                    <div class="phase-step">
                        <div class="phase-dot ${dotClass}"></div>
                        <span style="font-size: 0.75rem; color: var(--text-secondary)">${phaseName}</span>
                    </div>
                `;
                if (i < phases.length - 1) {
                    const lineClass = i < currentPhaseIndex ? 'completed' : '';
                    phaseIndicatorHtml += `<div class="phase-line ${lineClass}"></div>`;
                }
            });
            phaseIndicatorHtml += '</div>';
            
            // Build checklist
            let checklistHtml = '<ul class="checklist">';
            data.checklist.forEach(item => {
                let iconClass = 'check-pending';
                let icon = '';
                
                if (item.status === 'completed') {
                    iconClass = 'check-completed';
                    icon = '✓';
                } else if (item.status === 'skipped') {
                    iconClass = 'check-skipped';
                    icon = '⊘';
                } else if (item.status === 'in_progress') {
                    iconClass = 'check-progress';
                    icon = '●';
                } else if (item.status === 'failed') {
                    iconClass = 'check-failed';
                    icon = '✗';
                }
                
                const requiredBadge = item.required ? '<span class="required-badge">required</span>' : '';
                const skipReason = item.skip_reason ? `<div class="item-meta">Skipped: ${item.skip_reason}</div>` : '';
                
                checklistHtml += `
                    <li class="checklist-item">
                        <div class="check-icon ${iconClass}">${icon}</div>
                        <div class="item-content">
                            <div class="item-name">${item.name}${requiredBadge}</div>
                            ${skipReason}
                        </div>
                    </li>
                `;
            });
            checklistHtml += '</ul>';
            
            // Build blockers or ready message
            let statusHtml = '';
            if (data.can_advance) {
                statusHtml = '<div class="ready-badge">✓ Ready to advance to next phase</div>';
            } else if (data.blockers && data.blockers.length > 0) {
                statusHtml = `
                    <div class="blockers">
                        <div class="blockers-title">Blockers</div>
                        ${data.blockers.map(b => `<div class="blocker-item">• ${b}</div>`).join('')}
                    </div>
                `;
            }
            
            // Check if human approval is needed
            const needsApproval = data.blockers && data.blockers.some(b => b.includes('human approval'));
            const approveBtn = needsApproval ? 
                '<button class="approve-btn" onclick="approvePhase()">Approve Phase</button>' : '';
            
            // Calculate stats
            const completed = data.checklist.filter(i => i.status === 'completed').length;
            const skipped = data.checklist.filter(i => i.status === 'skipped').length;
            const pending = data.checklist.filter(i => i.status === 'pending').length;
            const failed = data.checklist.filter(i => i.status === 'failed').length;
            
            app.innerHTML = `
                <header>
                    <h1>Workflow Dashboard</h1>
                    <div>
                        <span class="status-badge ${statusClass}">${data.status}</span>
                        <button class="refresh-btn" onclick="fetchData()" style="margin-left: 10px">Refresh</button>
                    </div>
                </header>
                
                <div class="task-description">
                    <strong>Task:</strong> ${data.task}
                    ${data.project ? `<br><span style="color: var(--text-secondary)">Project: ${data.project}</span>` : ''}
                </div>
                
                ${phaseIndicatorHtml}
                
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value" style="color: var(--accent-green)">${completed}</div>
                        <div class="stat-label">Completed</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" style="color: var(--accent-yellow)">${skipped}</div>
                        <div class="stat-label">Skipped</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" style="color: var(--text-secondary)">${pending}</div>
                        <div class="stat-label">Pending</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" style="color: var(--accent-red)">${failed}</div>
                        <div class="stat-label">Failed</div>
                    </div>
                </div>
                
                <div class="grid">
                    <div class="card">
                        <div class="card-header">
                            <span class="card-title">Current Phase: ${data.current_phase.name}</span>
                            <span style="color: var(--text-secondary)">${data.current_phase.progress}</span>
                        </div>
                        ${checklistHtml}
                        ${statusHtml}
                        ${approveBtn}
                    </div>
                    
                    <div class="card">
                        <div class="card-header">
                            <span class="card-title">Activity Timeline</span>
                        </div>
                        <div class="timeline" id="timeline">
                            <p style="color: var(--text-secondary); text-align: center; padding: 20px;">
                                Timeline updates on refresh
                            </p>
                        </div>
                    </div>
                </div>
                
                <div style="margin-top: 20px; text-align: center; color: var(--text-secondary); font-size: 0.875rem;">
                    Workflow ID: ${data.workflow_id} | Last updated: ${data.updated_at}
                </div>
            `;
        }
        
        // Initial fetch
        fetchData();
        
        // Auto-refresh every 5 seconds
        setInterval(fetchData, 5000);
    </script>
</body>
</html>
'''


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler for the dashboard."""
    
    def __init__(self, *args, engine: WorkflowEngine, **kwargs):
        self.engine = engine
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())
        
        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            # Reload state to get latest
            self.engine.load_state()
            if self.engine.state:
                yaml_path = self.engine.working_dir / "workflow.yaml"
                if yaml_path.exists():
                    self.engine.load_workflow_def(str(yaml_path))

            status = self.engine.get_status()
            self.wfile.write(json.dumps(status, default=str).encode())

        elif self.path == '/api/csrf-token':
            # Provide CSRF token for JavaScript
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"token": _get_csrf_token()}).encode())

        else:
            self.send_error(404)
    
    def do_POST(self):
        if self.path == '/api/approve':
            # CSRF protection - require valid token in header
            csrf_token = self.headers.get('X-CSRF-Token', '')
            if csrf_token != _get_csrf_token():
                self.send_response(403)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": False,
                    "message": "Invalid or missing CSRF token"
                }).encode())
                return

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            # Reload state
            self.engine.load_state()
            if self.engine.state:
                yaml_path = self.engine.working_dir / "workflow.yaml"
                if yaml_path.exists():
                    self.engine.load_workflow_def(str(yaml_path))

            success, message = self.engine.approve_phase()
            self.wfile.write(json.dumps({
                "success": success,
                "message": message
            }).encode())

        else:
            self.send_error(404)
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass


def create_handler(engine: WorkflowEngine):
    """Create a handler class with the engine bound."""
    def handler(*args, **kwargs):
        return DashboardHandler(*args, engine=engine, **kwargs)
    return handler


def start_dashboard(working_dir: str = ".", port: int = 8080, open_browser: bool = True):
    """Start the dashboard server."""
    engine = WorkflowEngine(working_dir)
    engine.load_state()
    
    if engine.state:
        yaml_path = Path(working_dir) / "workflow.yaml"
        if yaml_path.exists():
            engine.load_workflow_def(str(yaml_path))
    
    handler = create_handler(engine)
    
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        url = f"http://localhost:{port}"
        print(f"Dashboard running at {url}")
        print("Press Ctrl+C to stop")
        
        if open_browser:
            webbrowser.open(url)
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDashboard stopped")


def generate_static_dashboard(working_dir: str = ".") -> str:
    """Generate a static HTML dashboard file."""
    engine = WorkflowEngine(working_dir)
    engine.load_state()
    
    if engine.state:
        yaml_path = Path(working_dir) / "workflow.yaml"
        if yaml_path.exists():
            engine.load_workflow_def(str(yaml_path))
    
    status = engine.get_status()
    
    # Embed the current status into the HTML
    html = DASHBOARD_HTML.replace(
        "fetchData();",
        f"currentData = {json.dumps(status, default=str)}; render();"
    )
    
    return html


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    working_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    start_dashboard(working_dir, port)
