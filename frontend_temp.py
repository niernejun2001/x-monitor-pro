def get_html_template():
    return r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>X Monitor Pro | Cyber Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #09090b;
            --card-bg: #18181b;
            --card-border: 1px solid #27272a;
            --primary: #06b6d4; /* Cyan 500 */
            --primary-dim: rgba(6, 182, 212, 0.1);
            --accent: #f43f5e; /* Rose 500 */
            --success: #10b981; /* Emerald 500 */
            --text-main: #e4e4e7;
            --text-muted: #a1a1aa;
            --font-main: 'Inter', sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-main);
            font-family: var(--font-main);
            margin: 0;
            padding: 20px;
            min-height: 100vh;
        }

        .container { max-width: 1400px; margin: 0 auto; }

        /* Header */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #27272a;
        }

        h1 {
            font-size: 24px;
            font-weight: 800;
            letter-spacing: -0.5px;
            margin: 0;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .logo-icon {
            width: 32px;
            height: 32px;
            background: var(--text-main);
            color: var(--bg-color);
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 900;
            font-size: 18px;
        }

        .version-tag {
            font-size: 11px;
            background: var(--primary-dim);
            color: var(--primary);
            padding: 4px 8px;
            border-radius: 99px;
            margin-left: 10px;
            font-family: var(--font-mono);
            border: 1px solid rgba(6, 182, 212, 0.3);
        }

        /* Status Indicator */
        .status-badge {
            font-family: var(--font-mono);
            font-size: 12px;
            padding: 6px 12px;
            border-radius: 99px;
            background: #27272a;
            border: 1px solid #3f3f46;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.3s ease;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #71717a;
            box-shadow: 0 0 0 0 rgba(255,255,255,0.2);
            transition: all 0.3s;
        }

        .status-active {
            border-color: rgba(16, 185, 129, 0.5);
            background: rgba(16, 185, 129, 0.1);
        }

        .status-active .status-dot {
            background: var(--success);
            box-shadow: 0 0 10px var(--success);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }

        /* Layout */
        .grid {
            display: grid;
            grid-template-columns: 360px 1fr;
            gap: 24px;
        }

        @media (max-width: 1000px) {
            .grid { grid-template-columns: 1fr; }
        }

        /* Cards */
        .card {
            background: var(--card-bg);
            border: var(--card-border);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid #27272a;
        }

        h3 {
            margin: 0;
            font-size: 14px;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        /* Inputs & Controls */
        input[type="text"] {
            width: 100%;
            background: #27272a;
            border: 1px solid #3f3f46;
            color: #fff;
            padding: 10px 12px;
            border-radius: 6px;
            font-family: var(--font-mono);
            font-size: 13px;
            transition: 0.2s;
            box-sizing: border-box;
        }

        input[type="text"]:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 2px var(--primary-dim);
        }

        .btn-group {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }

        button {
            cursor: pointer;
            border: none;
            padding: 10px 16px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 13px;
            transition: all 0.2s;
            font-family: var(--font-main);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }

        button:disabled { opacity: 0.5; cursor: not-allowed; }

        .btn-primary {
            background: var(--primary);
            color: #000;
        }
        .btn-primary:hover:not(:disabled) { filter: brightness(1.1); }

        .btn-danger {
            background: var(--accent);
            color: #fff;
        }
        .btn-danger:hover:not(:disabled) { filter: brightness(1.1); }

        .btn-ghost {
            background: #27272a;
            color: var(--text-muted);
            border: 1px solid #3f3f46;
        }
        .btn-ghost:hover { background: #3f3f46; color: #fff; }

        .btn-small { padding: 6px 12px; font-size: 12px; }

        /* Switch */
        .switch-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: #27272a;
            padding: 12px;
            border-radius: 6px;
            margin-top: 15px;
            border: 1px solid #3f3f46;
        }

        .switch { position: relative; display: inline-block; width: 36px; height: 20px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #52525b; transition: .3s; border-radius: 20px; }
        .slider:before { position: absolute; content: ""; height: 16px; width: 16px; left: 2px; bottom: 2px; background-color: white; transition: .3s; border-radius: 50%; }
        input:checked + .slider { background-color: var(--primary); }
        input:checked + .slider:before { transform: translateX(16px); }

        /* Task List */
        .task-item {
            background: #27272a;
            border-left: 3px solid var(--text-muted);
            padding: 12px;
            margin-bottom: 8px;
            border-radius: 4px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: 0.2s;
        }
        .task-item:hover { transform: translateX(2px); border-left-color: var(--primary); }
        .task-url { font-family: var(--font-mono); font-size: 12px; color: #fff; margin-bottom: 4px; }
        .task-meta { font-size: 11px; color: var(--text-muted); }

        /* Table */
        .table-container {
            border: 1px solid #27272a;
            border-radius: 8px;
            overflow: hidden;
            height: 500px;
            overflow-y: auto;
            background: #18181b;
        }

        table { width: 100%; border-collapse: collapse; font-size: 13px; }

        th {
            background: #27272a;
            color: var(--text-muted);
            padding: 12px 16px;
            text-align: left;
            font-weight: 600;
            position: sticky;
            top: 0;
            font-size: 11px;
            text-transform: uppercase;
        }

        td {
            padding: 12px 16px;
            border-bottom: 1px solid #27272a;
            color: var(--text-main);
            vertical-align: top;
        }

        tr:hover td { background: #27272a; }

        .handle-link { color: var(--primary); text-decoration: none; font-weight: 600; }
        .handle-link:hover { text-decoration: underline; }

        .tag { padding: 2px 8px; border-radius: 99px; font-size: 10px; font-weight: bold; text-transform: uppercase; font-family: var(--font-mono); }
        .tag-notify { background: rgba(16, 185, 129, 0.1); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.2); }
        .tag-tweet { background: rgba(6, 182, 212, 0.1); color: var(--primary); border: 1px solid rgba(6, 182, 212, 0.2); }

        /* Log Box */
        .log-box {
            background: #09090b;
            border: 1px solid #27272a;
            border-radius: 8px;
            height: 200px;
            overflow-y: auto;
            padding: 16px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            color: #a1a1aa;
            margin-top: 24px;
        }

        .log-line { margin-bottom: 6px; display: flex; gap: 10px; line-height: 1.4; }
        .log-time { color: #52525b; min-width: 70px; }
        .log-success { color: var(--success); }
        .log-warn { color: #fbbf24; }
        .log-error { color: var(--accent); }
        .log-debug { color: #52525b; }

        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #3f3f46; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #52525b; }

        .row-enter { animation: fadeIn 0.3s ease-out; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div style="display:flex; align-items:center; gap:15px">
                <div class="logo-icon">X</div>
                <h1>Monitor Pro <span class="version-tag">V11.2 ULTRA</span></h1>
            </div>
            <div id="statusIndicator" class="status-badge">
                <div class="status-dot"></div>
                <span id="statusText">系统待机</span>
            </div>
        </header>

        <div class="grid">
            <!-- Sidebar -->
            <div>
                <div class="card">
                    <div class="card-header"><h3>⚙️ 控制台</h3></div>

                    <div style="margin-bottom: 20px;">
                        <label style="font-size:12px; color:var(--text-muted); display:block; margin-bottom:8px">AUTH TOKEN</label>
                        <input type="text" id="token" placeholder="粘贴 Token..." style="font-family:monospace">
                    </div>

                    <div class="btn-group">
                        <button class="btn-primary" id="startBtn" onclick="toggle(true)" style="flex:1">
                            ▶ 启动监控
                        </button>
                        <button class="btn-danger" id="stopBtn" onclick="toggle(false)" disabled style="width: 100px;">
                            ⏹ 停止
                        </button>
                    </div>

                    <div class="switch-row">
                        <span style="font-size:13px; font-weight:600">📬 通知实时监控</span>
                        <label class="switch">
                            <input type="checkbox" id="notifCheckbox" onchange="toggleNotificationMonitoring()">
                            <span class="slider"></span>
                        </label>
                    </div>

                    <div style="margin-top: 15px; padding: 15px; background: #27272a; border-radius: 6px; border:1px solid #3f3f46">
                        <div style="margin-bottom: 8px; font-size: 11px; font-weight:bold; color: var(--text-muted); text-transform:uppercase">委派账户 (Delegated)</div>
                        <div style="display: flex; gap: 8px;">
                            <input type="text" id="delegatedAccount" placeholder="@username" style="font-size: 12px; padding: 8px;">
                            <button class="btn-ghost btn-small" onclick="saveDelegatedAccount()">保存</button>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <h3>🎯 监控任务</h3>
                    </div>
                    <div style="display: flex; gap: 8px; margin-bottom: 15px;">
                        <input type="text" id="newUrl" placeholder="输入推文链接...">
                        <button class="btn-ghost" onclick="addTask()">+</button>
                    </div>
                    <div id="taskList" style="max-height: 350px; overflow-y: auto; padding-right: 2px;"></div>
                </div>
            </div>

            <!-- Main Content -->
            <div>
                <div class="card" style="height: calc(100vh - 140px); display: flex; flex-direction: column; margin-bottom: 0;">
                    <div class="card-header">
                        <h3>📊 捕获数据流</h3>
                        <div style="display: flex; gap: 10px;">
                            <button class="btn-ghost btn-small" onclick="clearResults()">清空记录</button>
                            <button class="btn-ghost btn-small" onclick="clearBlocklist()">重置黑名单</button>
                        </div>
                    </div>

                    <div class="table-container" style="flex:1;">
                        <table id="resultTable">
                            <thead>
                                <tr>
                                    <th width="80">TIME</th>
                                    <th width="140">USER</th>
                                    <th>CONTENT</th>
                                    <th width="80">SRC</th>
                                    <th width="80">OPT</th>
                                </tr>
                            </thead>
                            <tbody id="tableBody"></tbody>
                        </table>
                    </div>

                    <div class="log-box" id="logBox">
                        <div class="log-line"><span class="log-time">[SYSTEM]</span><span class="log-info">Dashboard ready.</span></div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <script>
        window.onload = () => fetch('/api/state').then(r=>r.json()).then(d=>{
            document.getElementById('token').value = d.token;
            document.getElementById('notifCheckbox').checked = d.notification_monitoring || false;
            document.getElementById('delegatedAccount').value = d.delegated_account || '';
            renderTasks(d.tasks);
            if(d.is_running) setStatus(true);
            if(d.pending && d.pending.length > 0) d.pending.forEach(item => addRow(item, false));
        });

        function setStatus(run) {
            document.getElementById('startBtn').disabled = run;
            document.getElementById('stopBtn').disabled = !run;
            document.getElementById('token').disabled = run;
            const badge = document.getElementById('statusIndicator');
            const txt = document.getElementById('statusText');
            if(run) {
                badge.classList.add('status-active');
                txt.innerText = "系统运行中";
                txt.style.color = "var(--success)";
            } else {
                badge.classList.remove('status-active');
                txt.innerText = "系统已停止";
                txt.style.color = "#a1a1aa";
            }
        }

        function renderTasks(t) {
            const div = document.getElementById('taskList');
            div.innerHTML = t.map(x => `
                <div class="task-item">
                    <div style="overflow:hidden">
                        <div class="task-url" title="${x.url}">${x.url.split('status/')[1] || x.url.substring(0,25)+'...'}</div>
                        <div class="task-meta">⏱ ${x.last_check}</div>
                    </div>
                    <button class="btn-ghost btn-small" onclick="delTask('${x.url}')" style="color:#ef4444; border:none; background:transparent">✕</button>
                </div>`).join('');
        }

        function addTask() {
            const u = document.getElementById('newUrl').value;
            if(!u) return;
            fetch('/api/task/add', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:u})})
                .then(r=>r.json()).then(d=>{ renderTasks(d.tasks); document.getElementById('newUrl').value=''; });
        }
        function delTask(u) {
            fetch('/api/task/remove', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:u})})
                .then(r=>r.json()).then(d=>renderTasks(d.tasks));
        }
        function toggle(s) {
            const t = document.getElementById('token').value;
            if(s && !t) return alert('缺少 Token');
            fetch(s?'/api/start':'/api/stop', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({token:t})})
                .then(r=>r.json()).then(d => { if(d.status=='ok') setStatus(s); });
        }

        function toggleNotificationMonitoring() {
            const enabled = document.getElementById('notifCheckbox').checked;
            fetch('/api/toggle_notification', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled:enabled})})
                .then(r=>r.json()).then(d => { if(d.status === 'ok') console.log('Notify state:', d.notification_monitoring); });
        }

        function saveDelegatedAccount() {
            const account = document.getElementById('delegatedAccount').value.trim();
            fetch('/api/set_delegated_account', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({account:account})})
                .then(r=>r.json()).then(d => { if(d.status === 'ok') alert('✅ 账户设置已保存'); });
        }

        function markDone(handle, btn) {
            const rows = document.querySelectorAll(`tr[data-handle="${handle}"]`);
            rows.forEach(r => r.style.opacity = '0.3');
            fetch('/api/mark_done', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({handle:handle})})
                .then(r=>r.json()).then(d => { if(d.status === 'ok') setTimeout(() => rows.forEach(r => r.remove()), 300); });
        }

        function clearResults() {
            if(!confirm('确定要清空所有捕获结果吗？')) return;
            fetch('/api/clear_results', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({})})
                .then(r=>r.json()).then(d => { if(d.status === 'ok') document.getElementById('tableBody').innerHTML = ''; });
        }

        function clearBlocklist() {
            if(!confirm('确定要清空黑名单吗？')) return;
            fetch('/api/clear_blocklist', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({})})
                .then(r=>r.json()).then(d => { if(d.status === 'ok') alert('✅ 黑名单已重置'); });
        }

        function addRow(i, animate=true) {
            if(document.querySelector(`tr[data-key="${i.key}"]`)) return;
            if(document.querySelector(`tr[data-handle="${i.handle}"]`) && document.querySelector(`tr[data-handle="${i.handle}"]`).style.opacity == '0.3') return;

            const tr = document.createElement('tr');
            if(animate) tr.className = 'row-enter';
            tr.setAttribute('data-handle', i.handle);
            tr.setAttribute('data-key', i.key);

            const sourceTag = i.source === '通知页面' ? '<span class="tag tag-notify">NOTIFY</span>' : '<span class="tag tag-tweet">TWEET</span>';

            tr.innerHTML = `
                <td style="color:var(--text-muted); font-family:var(--font-mono)">${i.time}</td>
                <td><a href="https://x.com/${i.handle.replace('@','')}" target="_blank" class="handle-link">${i.handle}</a></td>
                <td style="color:#d4d4d8">${i.content}</td>
                <td>${sourceTag}</td>
                <td><button class="btn-primary btn-small" onclick="markDone('${i.handle}', this)">OK</button></td>
            `;
            document.getElementById('tableBody').prepend(tr);
        }

        setInterval(() => {
            fetch('/api/updates').then(r=>r.json()).then(d => {
                const box = document.getElementById('logBox');
                if(d.logs.length > 0) {
                    d.logs.forEach(l => {
                        const c = l.level=='error'?'log-error':(l.level=='warn'?'log-warn':(l.level=='success'?'log-success':'log-info'));
                        if(l.level == 'debug') return;
                        const className = c;
                        box.innerHTML = `<div class="log-line ${className}"><span class="log-time">[${new Date().toLocaleTimeString().split(' ')[0]}]</span><span>${l.msg}</span></div>` + box.innerHTML;
                    });
                    while(box.children.length > 100) box.lastElementChild.remove();
                }

                d.new_items.forEach(i => addRow(i, true));
                if(d.tasks) renderTasks(d.tasks);
            });
        }, 1000);
    </script>
</body>
</html>
    """