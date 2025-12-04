// State
let currentStopJobId = null;
let expandedJobs = new Set();
let jobsData = [];
let statusFilter = 'all';
let selectedMode = 'normal';

// Operators
const operators = {
    '013': { name: 'Grameenphone', color: '#00a651' },
    '017': { name: 'Grameenphone', color: '#00a651' },
    '014': { name: 'Banglalink', color: '#f7941d' },
    '019': { name: 'Banglalink', color: '#f7941d' },
    '015': { name: 'Teletalk', color: '#00529b' },
    '016': { name: 'Robi', color: '#e42313' },
    '018': { name: 'Robi/Airtel', color: '#e42313' }
};

// Load Stats
async function loadStats() {
    try {
        const res = await fetch('/api/stats');
        const data = await res.json();

        document.getElementById('totalSent').textContent = data.total_sent_today;
        document.getElementById('totalSuccess').textContent = data.total_success_today;
        document.getElementById('totalFail').textContent = data.total_fail_today;
        document.getElementById('navActive').textContent = data.running_jobs;
        document.getElementById('navApis').textContent = data.total_apis;

        // Update visitors and uptime
        document.getElementById('totalVisitors').textContent = data.total_visitors || 0;
        document.getElementById('serverUptime').textContent = data.uptime || '0m';

        updateMonitor();
    } catch (err) {
        console.error('Stats error:', err);
    }
}

// Update Monitor
function updateMonitor() {
    const running = jobsData.filter(j => j.status === 'running');
    const status = document.getElementById('monitorStatus');
    const fill = document.getElementById('progressFill');

    if (running.length === 0) {
        status.textContent = 'Standby';
        status.className = 'status-badge';
        fill.style.width = '0%';
        document.getElementById('requestCount').textContent = '0';
        document.getElementById('progressPercent').textContent = '0%';
        document.getElementById('timeLeft').textContent = '--:--';
        document.getElementById('currentApi').textContent = '-';
        return;
    }

    const job = running[0];
    const total = job.total_rounds * 60;
    const elapsed = total - job.time_remaining;
    const percent = Math.min(100, Math.round((elapsed / total) * 100));

    status.textContent = 'Running';
    status.className = 'status-badge active';
    fill.style.width = percent + '%';

    document.getElementById('requestCount').textContent = job.total_success + job.total_fail;
    document.getElementById('progressPercent').textContent = percent + '%';
    document.getElementById('timeLeft').textContent = formatTime(job.time_remaining);

    // Get current API
    fetch(`/api/jobs/${job.id}/logs`)
        .then(r => r.json())
        .then(logs => {
            if (logs.length > 0) {
                document.getElementById('currentApi').textContent = logs[logs.length - 1].target_name;
            }
        }).catch(() => { });
}

// Format time
function formatTime(sec) {
    if (sec <= 0) return '0:00';
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
}

// Format date
function formatDate(str) {
    return new Date(str).toLocaleString('en-US', {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
}

// Phone validation
function validatePhone(phone) {
    const icon = document.getElementById('phoneIcon');
    const hint = document.getElementById('operatorHint');

    if (phone.length < 3) {
        icon.textContent = '';
        hint.textContent = '';
        return;
    }

    const op = operators[phone.substring(0, 3)];

    if (phone.length === 11 && op) {
        icon.textContent = '✓';
        icon.style.color = 'var(--green)';
        hint.textContent = op.name;
        hint.style.color = op.color;
    } else if (phone.length === 11) {
        icon.textContent = '?';
        icon.style.color = '#f97316';
        hint.textContent = 'Unknown';
    } else if (phone.length > 11) {
        icon.textContent = '✗';
        icon.style.color = 'var(--red)';
        hint.textContent = 'Too long';
    } else {
        icon.textContent = '';
        hint.textContent = op ? op.name + '...' : '';
    }
}

// Load jobs
async function loadJobs() {
    try {
        const res = await fetch('/api/jobs');
        let jobs = await res.json();

        if (statusFilter !== 'all') {
            jobs = jobs.filter(j => j.status === statusFilter);
        }

        const list = document.getElementById('jobsList');

        if (jobs.length === 0) {
            list.innerHTML = '<div class="empty-state"><div class="empty-icon">🎯</div><p>No attacks yet</p></div>';
            jobsData = [];
            return;
        }

        const oldIds = jobsData.map(j => j.id);
        const newIds = jobs.map(j => j.id);
        const needsRender = oldIds.length !== newIds.length || !oldIds.every((id, i) => id === newIds[i]);

        if (needsRender) {
            list.innerHTML = jobs.map(createJobHTML).join('');
            expandedJobs.forEach(id => loadLogs(id));
        } else {
            jobs.forEach(updateJob);
        }

        jobsData = jobs;
    } catch (err) {
        console.error('Jobs error:', err);
    }
}

// Create job HTML
function createJobHTML(job) {
    const expanded = expandedJobs.has(job.id);
    return `
        <div class="job-item" data-id="${job.id}">
            <div class="job-header" onclick="toggle(${job.id})">
                <div class="job-main">
                    <span class="job-icon">${job.status === 'running' ? '🔥' : job.status === 'completed' ? '✅' : '⏹️'}</span>
                    <div>
                        <div class="job-phone">${job.masked_phone}</div>
                        <div class="job-meta">${job.added_by} • ${formatDate(job.start_time)}</div>
                    </div>
                </div>
                <div class="job-right">
                    <div class="job-stats-inline">
                        <span class="success" data-s="${job.id}">✓${job.total_success}</span>
                        <span class="fail" data-f="${job.id}">✗${job.total_fail}</span>
                    </div>
                    <span class="job-status ${job.status}">${job.status}</span>
                    ${job.status === 'running' ? `<button class="job-btn stop" onclick="event.stopPropagation();showModal(${job.id})">Stop</button>` : ''}
                    <button class="job-btn" onclick="event.stopPropagation();toggle(${job.id})">▼</button>
                </div>
            </div>
            <div class="job-details ${expanded ? 'expanded' : ''}" id="d-${job.id}">
                <div class="job-details-content" id="l-${job.id}"></div>
            </div>
        </div>
    `;
}

// Update job in place
function updateJob(job) {
    const s = document.querySelector(`[data-s="${job.id}"]`);
    const f = document.querySelector(`[data-f="${job.id}"]`);
    if (s) s.textContent = '✓' + job.total_success;
    if (f) f.textContent = '✗' + job.total_fail;
    if (expandedJobs.has(job.id)) loadLogs(job.id);
}

// Load logs
async function loadLogs(id) {
    try {
        const res = await fetch(`/api/jobs/${id}/logs`);
        const logs = await res.json();
        const el = document.getElementById(`l-${id}`);
        if (!el) return;

        if (logs.length === 0) {
            el.innerHTML = '<div class="empty-state"><p>Waiting...</p></div>';
            return;
        }

        el.innerHTML = logs.map(l => `
            <div class="api-chip">
                <span>${l.target_name}</span>
                <span class="stats"><span>✓${l.success_count}</span><span>✗${l.fail_count}</span></span>
            </div>
        `).join('');
    } catch (err) { }
}

// Toggle expand
function toggle(id) {
    const el = document.getElementById(`d-${id}`);
    if (!el) return;

    if (expandedJobs.has(id)) {
        expandedJobs.delete(id);
        el.classList.remove('expanded');
    } else {
        expandedJobs.add(id);
        el.classList.add('expanded');
        loadLogs(id);
    }
}

// Load APIs
async function loadApis() {
    try {
        const res = await fetch('/api/targets');
        const apis = await res.json();

        document.getElementById('apiCount').textContent = apis.length + ' Ready';
        document.getElementById('apiGrid').innerHTML = apis.map(a => `
            <div class="api-item">
                <span class="api-dot"></span>
                <span>${a.name}</span>
            </div>
        `).join('');
    } catch (err) { }
}

// Mode buttons
document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        selectedMode = btn.dataset.mode;
    });
});

// Phone input
document.getElementById('phone').addEventListener('input', e => validatePhone(e.target.value));

// Filter
document.getElementById('statusFilter').addEventListener('change', e => {
    statusFilter = e.target.value;
    jobsData = [];
    loadJobs();
});

// Form submit
document.getElementById('jobForm').addEventListener('submit', async e => {
    e.preventDefault();

    const phone = document.getElementById('phone').value.trim();
    const addedBy = document.getElementById('addedBy').value.trim() || 'Anonymous';
    const password = document.getElementById('password').value;
    const duration = parseInt(document.getElementById('duration').value) || 5;
    const unit = document.getElementById('durationUnit').value;

    if (!phone || !password) {
        alert('Phone and password required!');
        return;
    }

    let mins = duration;
    if (unit === 'hours') mins = duration * 60;
    else if (unit === 'days') mins = duration * 1440;

    try {
        const res = await fetch('/api/jobs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone, added_by: addedBy, password, duration_minutes: mins, attack_mode: selectedMode })
        });

        const data = await res.json();
        if (data.error) { alert(data.error); return; }

        document.getElementById('phone').value = '';
        document.getElementById('password').value = '';
        document.getElementById('phoneIcon').textContent = '';
        document.getElementById('operatorHint').textContent = '';

        jobsData = [];
        loadJobs();
        loadStats();
    } catch (err) {
        alert('Error: ' + err.message);
    }
});

// Modal
function showModal(id) {
    currentStopJobId = id;
    document.getElementById('stopModal').classList.remove('hidden');
    document.getElementById('stopPassword').focus();
}

function closeModal() {
    document.getElementById('stopModal').classList.add('hidden');
    document.getElementById('stopPassword').value = '';
    currentStopJobId = null;
}

async function confirmStop() {
    const pw = document.getElementById('stopPassword').value;
    if (!pw) { alert('Password required!'); return; }

    try {
        const res = await fetch(`/api/jobs/${currentStopJobId}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: pw })
        });

        const data = await res.json();
        if (data.error) { alert(data.error); return; }

        closeModal();
        jobsData = [];
        loadJobs();
        loadStats();
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

// Keyboard
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
    if (e.key === 'Enter' && currentStopJobId) confirmStop();
});

// Init
loadStats();
loadJobs();
loadApis();

// Auto refresh
setInterval(() => {
    loadStats();
    loadJobs();
}, 2000);
