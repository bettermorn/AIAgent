import React, { useState } from 'react'
import { sendFeedback } from '../api.js'

export default function FeedbackForm({ sessionId }) {
  const [score, setScore] = useState(0)
  const [hover, setHover] = useState(0)
  const [comment, setComment] = useState('')
  const [status, setStatus] = useState('idle') // idle | sending | done | error

  const submit = async () => {
    if (score === 0 || status === 'sending') return
    setStatus('sending')
    try {
      await sendFeedback({ session_id: sessionId, score, comment })
      setStatus('done')
    } catch {
      setStatus('error')
    }
  }

  if (status === 'done') {
    return <div className="feedback-done">✅ 感谢您的反馈！</div>
  }

  return (
    <div className="feedback-card">
      <div className="feedback-title">本次服务您还满意吗？</div>
      <div className="stars" onMouseLeave={() => setHover(0)}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            className={`star ${(hover || score) >= n ? 'star-on' : ''}`}
            onClick={() => setScore(n)}
            onMouseEnter={() => setHover(n)}
            aria-label={`${n} 星`}
          >
            ★
          </button>
        ))}
      </div>
      <textarea
        className="feedback-comment"
        placeholder="补充评论（可选）"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        rows={2}
      />
      <button
        className="btn btn-primary btn-sm"
        onClick={submit}
        disabled={score === 0 || status === 'sending'}
      >
        {status === 'sending' ? '提交中…' : '提交反馈'}
      </button>
      {status === 'error' && <div className="feedback-error">提交失败，请重试</div>}
    </div>
  )
}
