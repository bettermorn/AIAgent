-- 工业智能 / 工业软件 信息搜索智能体 数据库结构

CREATE TABLE IF NOT EXISTS articles (
  id            BIGSERIAL PRIMARY KEY,
  url           TEXT NOT NULL UNIQUE,
  title         TEXT NOT NULL,
  source        TEXT,                       -- 站点名称，如 微信公众号 / B站 / IEEE Spectrum
  channel       TEXT NOT NULL,              -- 渠道：wechat | bilibili | international | news
  language      TEXT DEFAULT 'zh',
  snippet       TEXT,                       -- 原始摘要
  summary       TEXT,                       -- DeepSeek 生成的中文摘要
  category      TEXT,                       -- DeepSeek 归类：工业智能 / 工业软件 / 政策标准 / ...
  tags          TEXT[] DEFAULT '{}',
  score         NUMERIC(4,1),               -- 重要性评分 0-10
  relevant      BOOLEAN NOT NULL DEFAULT true, -- 是否与工业智能/工业软件相关（模型判定）
  published_at  TIMESTAMPTZ,
  collected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  keyword       TEXT,
  run_id        TEXT
);

CREATE INDEX IF NOT EXISTS idx_articles_collected_at ON articles (collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_channel ON articles (channel);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles (published_at DESC);

-- 每次采集任务
CREATE TABLE IF NOT EXISTS runs (
  id              TEXT PRIMARY KEY,
  status          TEXT NOT NULL,            -- running | success | failed
  started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at     TIMESTAMPTZ,
  channels        TEXT[] DEFAULT '{}',
  keywords        TEXT[] DEFAULT '{}',
  collected_count INTEGER DEFAULT 0,
  inserted_count  INTEGER DEFAULT 0,
  error           TEXT
);

-- 每日日报
CREATE TABLE IF NOT EXISTS reports (
  report_date   DATE PRIMARY KEY,
  title         TEXT NOT NULL,
  overview      TEXT,                       -- 总体综述
  highlights    JSONB DEFAULT '[]',         -- 重点信息 [{title, why, url, source}]
  trends        JSONB DEFAULT '[]',         -- 趋势洞察 [string]
  by_channel    JSONB DEFAULT '{}',         -- 渠道统计
  article_count INTEGER DEFAULT 0,
  run_id        TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 系统配置（关键词、调度表达式等，可在前端修改）
CREATE TABLE IF NOT EXISTS settings (
  key        TEXT PRIMARY KEY,
  value      JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
