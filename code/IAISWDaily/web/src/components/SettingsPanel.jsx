import React, { useEffect, useState } from 'react';
import { api } from '../api.js';

export default function SettingsPanel({ channels, notify }) {
  const [settings, setSettings] = useState(null);
  const [schedule, setSchedule] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .settings()
      .then((res) => {
        setSettings(res.settings);
        setSchedule(res.schedule?.cron || '');
      })
      .catch(() => setSettings(null));
  }, []);

  if (!settings) return <div className="panel"><p className="muted">加载中…</p></div>;

  const save = async () => {
    setSaving(true);
    try {
      const res = await api.saveSettings(settings);
      setSchedule(res.schedule?.cron);
      notify('配置已保存，定时任务已更新', 'success');
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const toggleChannel = (key) => {
    setSettings((s) => ({
      ...s,
      channels: s.channels.includes(key)
        ? s.channels.filter((c) => c !== key)
        : [...s.channels, key],
    }));
  };

  return (
    <div className="panel">
      <section className="card">
        <h3>检索渠道</h3>
        <div className="chips">
          {channels.map((c) => (
            <button
              key={c.key}
              className={settings.channels.includes(c.key) ? 'chip active' : 'chip'}
              onClick={() => toggleChannel(c.key)}
            >
              {c.label}
            </button>
          ))}
        </div>
      </section>

      <section className="card">
        <h3>中文关键词（用于微信公众号 / B站 / 中文资讯）</h3>
        <KeywordEditor
          values={settings.keywordsZh}
          onChange={(keywordsZh) => setSettings((s) => ({ ...s, keywordsZh }))}
        />
      </section>

      <section className="card">
        <h3>英文关键词（用于国际/国外网站）</h3>
        <KeywordEditor
          values={settings.keywordsEn}
          onChange={(keywordsEn) => setSettings((s) => ({ ...s, keywordsEn }))}
        />
      </section>

      <section className="card">
        <h3>调度与采集参数</h3>
        <div className="grid">
          <label>
            Cron 表达式
            <input
              value={settings.cron}
              onChange={(e) => setSettings((s) => ({ ...s, cron: e.target.value }))}
              placeholder="0 8 * * *"
            />
          </label>
          <label>
            时区
            <input
              value={settings.timezone}
              onChange={(e) => setSettings((s) => ({ ...s, timezone: e.target.value }))}
            />
          </label>
          <label>
            时间窗口（天）
            <input
              type="number"
              min="1"
              max="30"
              value={settings.windowDays}
              onChange={(e) => setSettings((s) => ({ ...s, windowDays: Number(e.target.value) }))}
            />
          </label>
          <label>
            每个关键词条数
            <input
              type="number"
              min="1"
              max="20"
              value={settings.perKeywordLimit}
              onChange={(e) =>
                setSettings((s) => ({ ...s, perKeywordLimit: Number(e.target.value) }))
              }
            />
          </label>
        </div>
        <p className="muted">当前生效的定时任务：{schedule || '-'}（每天 8:00 对应 "0 8 * * *"）</p>
      </section>

      <div className="actions">
        <button className="primary" onClick={save} disabled={saving}>
          {saving ? '保存中…' : '保存配置'}
        </button>
      </div>
    </div>
  );
}

function KeywordEditor({ values, onChange }) {
  const [draft, setDraft] = useState('');

  const add = () => {
    const v = draft.trim();
    if (!v || values.includes(v)) return setDraft('');
    onChange([...values, v]);
    setDraft('');
  };

  return (
    <div>
      <div className="chips">
        {values.map((k) => (
          <span className="chip with-del" key={k}>
            {k}
            <button onClick={() => onChange(values.filter((x) => x !== k))}>×</button>
          </span>
        ))}
      </div>
      <div className="row">
        <input
          value={draft}
          placeholder="输入关键词后回车添加"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && add()}
        />
        <button onClick={add}>添加</button>
      </div>
    </div>
  );
}
