-- 海上风电场运维智能体 PostgreSQL 数据模型
-- 业务关系库 + 知识图谱(关系型建模, 递归CTE多跳查询) + 实时/历史双时序库 + 文档/向量检索 + 审计(WORM)
-- =========================== 基础主数据 ===========================
CREATE TABLE IF NOT EXISTS wind_farms (
    id SERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    capacity_mw DOUBLE PRECISION,
    meta JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,                       -- operator/engineer/approver/knowledge_admin/admin/system
    farms TEXT[] NOT NULL DEFAULT '{}',       -- ABAC: 可访问风场, '*' 表示全部
    quals TEXT[] NOT NULL DEFAULT '{}',       -- 资质: offshore/climb/hv_electric/...
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 资产台账(EAM): 风场-风机-子系统-部件-传感器 五级 + 升压站/海缆/测风塔
CREATE TABLE IF NOT EXISTS assets (
    id SERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,                       -- turbine/substation/cable/mast/subsystem/component/sensor
    farm_id INT REFERENCES wind_farms(id),
    parent_code TEXT,
    comp_type TEXT,                           -- 部件/传感器标准类型 如 gearbox
    model TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    props JSONB NOT NULL DEFAULT '{}',
    install_date DATE,
    status TEXT NOT NULL DEFAULT 'running',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS assets_farm_type ON assets(farm_id, type);
CREATE INDEX IF NOT EXISTS assets_parent ON assets(parent_code);

CREATE TABLE IF NOT EXISTS sensor_catalog (
    sensor_type TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    unit TEXT NOT NULL,
    comp_type TEXT,                           -- 所属部件类型
    asset_kind TEXT NOT NULL DEFAULT 'turbine',
    sample_hz DOUBLE PRECISION NOT NULL DEFAULT 1,
    nominal DOUBLE PRECISION,
    lo DOUBLE PRECISION,
    hi DOUBLE PRECISION
);

-- =========================== 双时序库 ===========================
-- 实时库(热数据, 原始采样)
CREATE TABLE IF NOT EXISTS ts_realtime (
    asset_code TEXT NOT NULL,
    sensor_type TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    quality SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (asset_code, sensor_type, ts)
);
CREATE INDEX IF NOT EXISTS ts_realtime_ts ON ts_realtime(ts);
-- 历史库(冷数据, 降采样聚合, 长期归档)
CREATE TABLE IF NOT EXISTS ts_history (
    asset_code TEXT NOT NULL,
    sensor_type TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,                  -- 聚合桶起点(1分钟)
    value DOUBLE PRECISION NOT NULL,          -- 均值
    vmin DOUBLE PRECISION,
    vmax DOUBLE PRECISION,
    n INT NOT NULL DEFAULT 1,
    PRIMARY KEY (asset_code, sensor_type, ts)
);
CREATE INDEX IF NOT EXISTS ts_history_ts ON ts_history(ts);

-- 多源监测数据索引(视频/红外热像/声学/结构应变); 文件落对象存储, 元数据在此
CREATE TABLE IF NOT EXISTS monitoring_media (
    id SERIAL PRIMARY KEY,
    farm_id INT REFERENCES wind_farms(id),
    asset_code TEXT NOT NULL,
    kind TEXT NOT NULL,                       -- video/infrared/acoustic/strain
    object_key TEXT,
    sha256 TEXT,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    summary TEXT,
    meta JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS media_asset ON monitoring_media(asset_code, kind, ts DESC);

-- 海洋气象 / AIS
CREATE TABLE IF NOT EXISTS weather_forecast (
    farm_id INT REFERENCES wind_farms(id),
    ts TIMESTAMPTZ NOT NULL,
    wind_speed DOUBLE PRECISION,
    wave_height DOUBLE PRECISION,
    visibility_km DOUBLE PRECISION,
    PRIMARY KEY (farm_id, ts)
);
CREATE TABLE IF NOT EXISTS ais_vessels (
    mmsi TEXT PRIMARY KEY,
    farm_id INT REFERENCES wind_farms(id),
    name TEXT,
    ship_type TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    sog DOUBLE PRECISION,
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =========================== 告警 / 规则 ===========================
CREATE TABLE IF NOT EXISTS rules (
    id SERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    asset_kind TEXT NOT NULL DEFAULT 'turbine',
    sensor_type TEXT NOT NULL,
    comp_type TEXT,
    fault_key TEXT NOT NULL,                  -- 标准故障概念
    direction TEXT NOT NULL DEFAULT 'high',   -- high: 超过阈值告警 / low: 低于阈值告警
    l1 DOUBLE PRECISION NOT NULL,
    l2 DOUBLE PRECISION NOT NULL,
    l3 DOUBLE PRECISION NOT NULL,
    window_s INT NOT NULL DEFAULT 300,        -- 取窗口内均值判断, 抑制抖动
    doc_no TEXT,
    doc_section TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    version TEXT NOT NULL DEFAULT 'v1'
);

CREATE TABLE IF NOT EXISTS alarms (
    id SERIAL PRIMARY KEY,
    farm_id INT REFERENCES wind_farms(id),
    asset_code TEXT NOT NULL,
    comp_code TEXT,
    sensor_type TEXT,
    rule_code TEXT,
    fault_key TEXT NOT NULL,
    title TEXT NOT NULL,
    level INT NOT NULL,                       -- 预警级别: 1关注 2告警 3严重 (数字越大越严重)
    value DOUBLE PRECISION,
    threshold DOUBLE PRECISION,
    status TEXT NOT NULL DEFAULT 'open',      -- open/acknowledged/closed
    raised_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    acked_at TIMESTAMPTZ,
    acked_by TEXT,
    closed_at TIMESTAMPTZ,
    task_id UUID,
    wo_id INT,
    source TEXT NOT NULL DEFAULT 'monitor',
    detail JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS alarms_open ON alarms(status, asset_code);
CREATE INDEX IF NOT EXISTS alarms_time ON alarms(raised_at DESC);

-- =========================== 知识图谱(关系型建模) ===========================
CREATE TABLE IF NOT EXISTS kg_entities (
    id SERIAL PRIMARY KEY,
    type TEXT NOT NULL,
    key TEXT NOT NULL,                        -- 业务唯一键(设备编码/标准概念)
    name TEXT NOT NULL,
    props JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',    -- candidate/active/deprecated
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (type, key)
);
CREATE INDEX IF NOT EXISTS kg_entities_key ON kg_entities(key);

CREATE TABLE IF NOT EXISTS kg_relations (
    id SERIAL PRIMARY KEY,
    src INT NOT NULL REFERENCES kg_entities(id),
    rel TEXT NOT NULL,
    dst INT NOT NULL REFERENCES kg_entities(id),
    props JSONB NOT NULL DEFAULT '{}',
    valid_from TIMESTAMPTZ,
    valid_to TIMESTAMPTZ,
    source_type TEXT,                         -- document/workorder/expert/ledger
    source_id TEXT,
    source_locator TEXT,
    version TEXT,
    extract_model TEXT,
    reviewer TEXT,
    review_time TIMESTAMPTZ,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    status TEXT NOT NULL DEFAULT 'active',    -- candidate/active/deprecated
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS kg_rel_src ON kg_relations(src, rel);
CREATE INDEX IF NOT EXISTS kg_rel_dst ON kg_relations(dst, rel);
CREATE INDEX IF NOT EXISTS kg_rel_source ON kg_relations(source_type, source_id);

-- 知识候选区: 抽取结果 + 五层校验结果 + 审核状态
CREATE TABLE IF NOT EXISTS knowledge_candidates (
    id SERIAL PRIMARY KEY,
    batch_id TEXT,
    source_type TEXT,
    source_id TEXT,
    source_locator TEXT,
    payload JSONB NOT NULL,                   -- 规范化后的结构化抽取结果
    raw_text TEXT,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    validation JSONB NOT NULL DEFAULT '{}',
    needs_expert BOOLEAN NOT NULL DEFAULT FALSE,
    risk_reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending/approved/rejected/auto_rejected/activated
    extract_model TEXT,
    reviewer TEXT,
    review_time TIMESTAMPTZ,
    review_comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS kc_status ON knowledge_candidates(status);

CREATE TABLE IF NOT EXISTS term_dictionary (
    id SERIAL PRIMARY KEY,
    category TEXT NOT NULL,                   -- fault/component/action/symptom/cause
    std_key TEXT NOT NULL,
    std_name TEXT NOT NULL,
    synonyms TEXT[] NOT NULL DEFAULT '{}',
    UNIQUE (category, std_key)
);

CREATE TABLE IF NOT EXISTS term_stats (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    method TEXT NOT NULL,                     -- exact/synonym/fuzzy/llm/unmatched
    term TEXT NOT NULL,
    std_key TEXT
);

-- =========================== 文档与检索 ===========================
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    doc_no TEXT NOT NULL,
    title TEXT NOT NULL,
    doc_type TEXT NOT NULL,                   -- regulation/manual/report/drawing/safety
    version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',    -- active/deprecated
    farm_id INT REFERENCES wind_farms(id),
    model TEXT,
    content_sha256 TEXT NOT NULL,
    object_key TEXT,
    effective_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (doc_no, version)
);
CREATE TABLE IF NOT EXISTS doc_chunks (
    id SERIAL PRIMARY KEY,
    doc_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page INT NOT NULL DEFAULT 1,
    section TEXT,
    text TEXT NOT NULL,
    vec REAL[]                                 -- 哈希n-gram向量(见 services/embedding.py)
);
CREATE INDEX IF NOT EXISTS doc_chunks_doc ON doc_chunks(doc_id);

-- =========================== 资源 ===========================
CREATE TABLE IF NOT EXISTS spare_parts (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    comp_type TEXT,
    stock INT NOT NULL DEFAULT 0,
    reserved INT NOT NULL DEFAULT 0,
    location TEXT,
    lead_days INT NOT NULL DEFAULT 7,
    farm_id INT REFERENCES wind_farms(id),
    UNIQUE (farm_id, code)
);
CREATE TABLE IF NOT EXISTS personnel (
    id SERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    quals TEXT[] NOT NULL DEFAULT '{}',
    cert_expire DATE,
    status TEXT NOT NULL DEFAULT 'available',
    farm_id INT REFERENCES wind_farms(id)
);
CREATE TABLE IF NOT EXISTS vessels (
    id SERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    vtype TEXT NOT NULL,                      -- CTV/SOV
    capacity INT NOT NULL DEFAULT 12,
    max_wave DOUBLE PRECISION NOT NULL DEFAULT 1.5,
    max_wind DOUBLE PRECISION NOT NULL DEFAULT 12,
    status TEXT NOT NULL DEFAULT 'available',
    farm_id INT REFERENCES wind_farms(id)
);
CREATE TABLE IF NOT EXISTS trip_plans (
    id SERIAL PRIMARY KEY,
    farm_id INT REFERENCES wind_farms(id),
    vessel_code TEXT,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    turbines TEXT[] NOT NULL DEFAULT '{}',
    wo_ids INT[] NOT NULL DEFAULT '{}',
    crew TEXT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'suggested', -- suggested/confirmed/done/cancelled
    cross_farm BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS work_permits (
    id SERIAL PRIMARY KEY,
    permit_no TEXT UNIQUE NOT NULL,
    wo_id INT,
    kind TEXT NOT NULL,                       -- climb/offshore/hv/hot_work
    status TEXT NOT NULL DEFAULT 'requested', -- requested/issued/closed
    holder TEXT,
    second_signer TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =========================== 工单 ===========================
CREATE TABLE IF NOT EXISTS work_orders (
    id SERIAL PRIMARY KEY,
    wo_no TEXT UNIQUE NOT NULL,
    farm_id INT REFERENCES wind_farms(id),
    asset_code TEXT NOT NULL,
    comp_code TEXT,
    wo_type TEXT NOT NULL,                    -- emergency/normal/routine
    status TEXT NOT NULL,                     -- draft/pending_approval/approved/dispatched/in_progress/closed/rejected/cancelled
    warning_level INT,
    risk_level TEXT,                          -- L0..L4
    title TEXT NOT NULL,
    description TEXT,
    fault_key TEXT,
    causes JSONB NOT NULL DEFAULT '[]',
    actions JSONB NOT NULL DEFAULT '[]',
    parts JSONB NOT NULL DEFAULT '[]',
    crew JSONB NOT NULL DEFAULT '[]',
    vessel TEXT,
    window_start TIMESTAMPTZ,
    window_end TIMESTAMPTZ,
    safety JSONB NOT NULL DEFAULT '{}',
    evidence JSONB NOT NULL DEFAULT '[]',
    features JSONB NOT NULL DEFAULT '{}',     -- 诊断时的传感器状态快照(供改进Agent训练/评估)
    alarm_id INT,
    task_id UUID,
    source TEXT NOT NULL DEFAULT 'agent',     -- agent/manual/history/periodic
    auto_generated BOOLEAN NOT NULL DEFAULT FALSE,
    auto_dispatched BOOLEAN NOT NULL DEFAULT FALSE,
    alarm_time TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    submitted_at TIMESTAMPTZ,
    approved_at TIMESTAMPTZ,
    dispatched_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    response_minutes DOUBLE PRECISION,
    repair_minutes DOUBLE PRECISION,
    result TEXT,
    root_cause TEXT,
    root_cause_key TEXT,
    actual_actions JSONB NOT NULL DEFAULT '[]',
    effective BOOLEAN,
    kg_synced BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS wo_status ON work_orders(status);
CREATE INDEX IF NOT EXISTS wo_asset ON work_orders(asset_code);
CREATE INDEX IF NOT EXISTS wo_fault ON work_orders(fault_key);
CREATE TABLE IF NOT EXISTS work_order_events (
    id BIGSERIAL PRIMARY KEY,
    wo_id INT NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor TEXT,
    event TEXT NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS periodic_plans (
    id SERIAL PRIMARY KEY,
    farm_id INT REFERENCES wind_farms(id),
    asset_code TEXT NOT NULL,
    title TEXT NOT NULL,
    cycle_days INT NOT NULL,
    standard TEXT NOT NULL DEFAULT 'GB/T 32128',
    last_done DATE,
    next_due DATE NOT NULL
);

-- =========================== Agent 运行 / 安全 / 审计 ===========================
CREATE TABLE IF NOT EXISTS agent_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    query TEXT NOT NULL,
    requester TEXT NOT NULL,
    role TEXT,
    farm_code TEXT,
    status TEXT NOT NULL DEFAULT 'Received',
    risk_level TEXT,
    intent JSONB NOT NULL DEFAULT '{}',
    plan JSONB NOT NULL DEFAULT '{}',
    state JSONB NOT NULL DEFAULT '{}',
    result JSONB NOT NULL DEFAULT '{}',
    error TEXT,
    tokens INT NOT NULL DEFAULT 0,
    tool_calls INT NOT NULL DEFAULT 0,
    steps INT NOT NULL DEFAULT 0,
    models JSONB NOT NULL DEFAULT '[]',
    alarm_id INT,
    wo_id INT,
    paused BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS agent_tasks_status ON agent_tasks(status, created_at DESC);
CREATE TABLE IF NOT EXISTS agent_events (
    id BIGSERIAL PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
    seq INT NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    agent TEXT,
    type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS agent_events_task ON agent_events(task_id, seq);
CREATE TABLE IF NOT EXISTS agent_checkpoints (
    task_id UUID NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
    step INT NOT NULL,
    node TEXT NOT NULL,
    state JSONB NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (task_id, step)
);
CREATE TABLE IF NOT EXISTS approvals (
    id SERIAL PRIMARY KEY,
    task_id UUID,
    wo_id INT,
    level TEXT NOT NULL,                      -- L1/L2/L3
    stage INT NOT NULL DEFAULT 1,             -- L3 双人确认: stage 1/2
    required_role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending/approved/rejected/modified
    approver TEXT,
    comment TEXT,
    modifications JSONB,
    permit_no TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    task_id UUID,
    trace_id TEXT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}',
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_task ON audit_log(task_id);

-- WORM: 审计表禁止 UPDATE/DELETE
CREATE OR REPLACE FUNCTION audit_worm_guard() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is WORM: % not allowed', TG_OP;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS audit_worm ON audit_log;
CREATE TRIGGER audit_worm BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_worm_guard();

-- =========================== 模型治理 / 改进 / 反馈 / 报表 ===========================
CREATE TABLE IF NOT EXISTS model_registry (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'shadow',    -- shadow/active/retired/rejected
    params JSONB NOT NULL DEFAULT '{}',
    metrics JSONB NOT NULL DEFAULT '{}',
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    promoted_at TIMESTAMPTZ,
    UNIQUE (name, version)
);
CREATE TABLE IF NOT EXISTS eval_golden (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    scenario JSONB NOT NULL,                  -- {fault_key, sensors:{type:{value,..}}, expected_cause}
    expected_cause TEXT NOT NULL,
    fault_key TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eval_runs (
    id SERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_name TEXT,
    model_version TEXT,
    n INT,
    top1 DOUBLE PRECISION,
    top3 DOUBLE PRECISION,
    detail JSONB NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS rca_reports (
    id SERIAL PRIMARY KEY,
    wo_id INT,
    asset_code TEXT,
    fault_key TEXT,
    root_cause TEXT,
    analysis JSONB NOT NULL DEFAULT '{}',
    recommendations JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS feedback (
    id SERIAL PRIMARY KEY,
    task_id UUID,
    wo_id INT,
    username TEXT,
    rating INT,
    correct BOOLEAN,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reports (
    id SERIAL PRIMARY KEY,
    farm_id INT REFERENCES wind_farms(id),
    period TEXT NOT NULL,                     -- monthly/quarterly/yearly
    period_key TEXT NOT NULL,                 -- 2026-10 / 2026-Q3 / 2026
    kpis JSONB NOT NULL DEFAULT '{}',
    narrative TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (farm_id, period, period_key)
);
CREATE TABLE IF NOT EXISTS strategies (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content JSONB NOT NULL,
    farms TEXT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'draft',     -- draft/published
    created_by TEXT,
    published_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    farm_id INT,
    channel TEXT NOT NULL DEFAULT 'web',
    level TEXT NOT NULL DEFAULT 'info',
    title TEXT NOT NULL,
    body TEXT,
    ref_type TEXT,
    ref_id TEXT,
    target_role TEXT,
    read BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS notif_time ON notifications(ts DESC);
CREATE TABLE IF NOT EXISTS job_runs (
    id BIGSERIAL PRIMARY KEY,
    job TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    ok BOOLEAN NOT NULL DEFAULT TRUE,
    detail JSONB NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS edge_ingest_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    node TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    rows INT NOT NULL,
    checksum TEXT NOT NULL,
    priority INT NOT NULL DEFAULT 0,
    UNIQUE (node, batch_id)
);

-- 故障注入(仿真器使用, 便于联调与演示)
CREATE TABLE IF NOT EXISTS sim_faults (
    id SERIAL PRIMARY KEY,
    asset_code TEXT NOT NULL,
    scenario TEXT NOT NULL,                   -- 场景key, 见 edge/simulator.py
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ramp_minutes DOUBLE PRECISION NOT NULL DEFAULT 20,
    active BOOLEAN NOT NULL DEFAULT TRUE
);
