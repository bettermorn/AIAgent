import { useState } from 'react'
import { analyzeGap } from '../api.js'

const STATUS_LABEL = {
  conformant: { text: '已满足', cls: 'status-ok' },
  partial: { text: '部分满足', cls: 'status-warn' },
  gap: { text: '差距', cls: 'status-bad' },
  unknown: { text: '信息不足', cls: 'status-muted' },
}

const EMPTY_FACT = {
  company_name: '',
  business_type: '',
  data_types: '',
  processing_purposes: '',
  data_subjects: '',
  retention_period: '',
  third_party_sharing: false,
  cross_border_transfer: false,
  security_measures: '',
}

export default function GapPage({ meta }) {
  const [fact, setFact] = useState(EMPTY_FACT)
  const [policies, setPolicies] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  const policyOptions = meta?.policies || []

  const set = (key, value) => setFact((f) => ({ ...f, [key]: value }))
  const setList = (key, value) => set(key, value.split(/[,，、\s]+/).filter(Boolean))

  const togglePolicy = (id) => {
    setPolicies((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))
  }

  const submit = async (e) => {
    e?.preventDefault()
    setLoading(true)
    setError('')
    try {
      const payload = { fact: { ...fact } }
      if (policies.length) payload.policies = policies
      setResult(await analyzeGap(payload))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <section className="card">
        <h2>企业合规事实</h2>
        <p className="hint">填写企业的数据处理现状，系统将对照 GDPR / CCPA 政策控制措施评估合规差距。</p>
        <form onSubmit={submit}>
          <div className="grid-2">
            <div className="field">
              <label>公司名称</label>
              <input className="input" value={fact.company_name}
                onChange={(e) => set('company_name', e.target.value)}
                placeholder="示例科技公司" />
            </div>
            <div className="field">
              <label>业务类型</label>
              <input className="input" value={fact.business_type}
                onChange={(e) => set('business_type', e.target.value)}
                placeholder="SaaS 软件服务" />
            </div>
            <div className="field">
              <label>数据类型（逗号分隔）</label>
              <input className="input" value={fact.data_types}
                onChange={(e) => setList('data_types', e.target.value)}
                placeholder="用户个人信息, 支付信息" />
            </div>
            <div className="field">
              <label>处理目的（逗号分隔）</label>
              <input className="input" value={fact.processing_purposes}
                onChange={(e) => setList('processing_purposes', e.target.value)}
                placeholder="服务提供, 产品改进" />
            </div>
            <div className="field">
              <label>数据主体（逗号分隔）</label>
              <input className="input" value={fact.data_subjects}
                onChange={(e) => setList('data_subjects', e.target.value)}
                placeholder="欧盟居民, 加州居民" />
            </div>
            <div className="field">
              <label>数据保留期限</label>
              <input className="input" value={fact.retention_period}
                onChange={(e) => set('retention_period', e.target.value)}
                placeholder="24个月" />
            </div>
            <div className="field field-full">
              <label>安全措施（逗号分隔）</label>
              <input className="input" value={fact.security_measures}
                onChange={(e) => setList('security_measures', e.target.value)}
                placeholder="加密, 访问控制, 定期审计" />
            </div>
          </div>
          <div className="form-row">
            <label className="check">
              <input type="checkbox" checked={fact.third_party_sharing}
                onChange={(e) => set('third_party_sharing', e.target.checked)} />
              存在第三方共享
            </label>
            <label className="check">
              <input type="checkbox" checked={fact.cross_border_transfer}
                onChange={(e) => set('cross_border_transfer', e.target.checked)} />
              存在跨境传输
            </label>
          </div>
          {policyOptions.length > 0 && (
            <div className="field">
              <label>评估政策（不选则评估全部）</label>
              <div className="chips">
                {policyOptions.map((p) => (
                  <button type="button" key={p.id}
                    className={`chip ${policies.includes(p.id) ? 'chip-on' : ''}`}
                    onClick={() => togglePolicy(p.id)}>
                    {p.title}
                  </button>
                ))}
              </div>
            </div>
          )}
          <button className="btn btn-primary" disabled={loading}>
            {loading ? '分析中…' : '开始差距分析'}
          </button>
        </form>
        {error && <div className="alert alert-error">{error}</div>}
      </section>

      {loading && <div className="card skeleton-card">DeepSeek 正在逐条评估控制措施，请稍候…</div>}

      {result && !loading && (
        <section className="card">
          <div className="result-header">
            <h2>差距分析结果</h2>
            <div className="summary-badges">
              <span className="badge status-bad">差距 {result.summary.gaps}</span>
              <span className="badge status-warn">部分 {result.summary.partial}</span>
              <span className="badge status-ok">满足 {result.summary.conformant}</span>
              <span className="badge status-muted">未知 {result.summary.unknown}</span>
            </div>
          </div>
          <div className="gap-list">
            {result.gaps.map((g) => {
              const s = STATUS_LABEL[g.status] || STATUS_LABEL.unknown
              return (
                <div className="gap-item" key={g.control_id}>
                  <div className="gap-head">
                    <span className={`status ${s.cls}`}>{s.text}</span>
                    <strong>{g.control_id}</strong>
                    <span className={`risk risk-${g.risk}`}>风险：{g.risk}</span>
                  </div>
                  <p className="gap-req">{g.requirement}</p>
                  {g.explanation && <p className="gap-explain">{g.explanation}</p>}
                  {g.recommendation && (
                    <p className="gap-recommend">建议：{g.recommendation}</p>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}
    </div>
  )
}
