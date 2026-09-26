import React from 'react'

const SUGGESTIONS = [
  '你们的服务时间是什么？',
  '我无法登录账号，请帮我创建一个工单',
  '发票要如何开具？',
  '哪种服务套餐提供7*24小时优先支持？',
  '哪种情况需要30分钟内响应？',
  '哪种服务套餐提供私有化部署？',
  '账号如何设置才是安全的？',
  '投诉处理流程是怎样的？',
  '如何联系客户支持？',
  '数据如何导出并删除？',
  '如何实现第三方集成？',
  '什么情况下能退款？',
  '非工作日提供服务吗？',
  '哪种订阅方式享受优惠？',
  '系统支持哪些平台？',
  '系统遇到问题如何排查？',
  '如何重置密码',
]

export default function ChatInput({ value, onChange, onSend, disabled, onSuggest }) {
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      onSend()
    }
  }

  return (
    <div className="input-area">
      <div className="suggestions">
        {SUGGESTIONS.map((s) => (
          <button key={s} type="button" className="chip" onClick={() => onSuggest(s)}>
            {s}
          </button>
        ))}
      </div>
      <div className="input-row">
        <textarea
          className="chat-input"
          placeholder="请输入您的问题，Enter 发送（Shift+Enter 换行）"
          value={value}
          rows={1}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
        />
        <button
          type="button"
          className="btn btn-primary btn-send"
          onClick={onSend}
          disabled={disabled || !value.trim()}
        >
          发送
        </button>
      </div>
    </div>
  )
}
