import React from 'react';
import { api } from './api';
import Sidebar from './components/Sidebar';
import MessageBubble from './components/MessageBubble';
import ToolCallCard from './components/ToolCallCard';
import CheckpointList from './components/CheckpointList';
import { ToastProvider, useToast } from './components/Toast';
import './App.css';

export default function App() {
  return (
    <ToastProvider>
      <AppInner />
    </ToastProvider>
  );
}

function AppInner() {
  const toast = useToast();
  const [health, setHealth] = React.useState(null);
  const [threads, setThreads] = React.useState([]);
  const [currentThreadId, setCurrentThreadId] = React.useState(null);
  const [messages, setMessages] = React.useState([]);
  const [pendingToolCalls, setPendingToolCalls] = React.useState(null);
  const [checkpoints, setCheckpoints] = React.useState([]);
  const [currentCheckpointId, setCurrentCheckpointId] = React.useState(null);
  const [input, setInput] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [rightTab, setRightTab] = React.useState('checkpoints');
  const messagesEndRef = React.useRef(null);

  React.useEffect(() => {
    refreshHealth();
    refreshThreads();
  }, []);

  React.useEffect(() => {
    if (currentThreadId) {
      loadThread(currentThreadId);
    }
  }, [currentThreadId]);

  React.useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, pendingToolCalls]);

  async function refreshHealth() {
    try {
      const h = await api.health();
      setHealth(h);
    } catch (e) {
      setHealth({ ok: false, error: e.message });
    }
  }

  async function refreshThreads() {
    try {
      const data = await api.listThreads();
      setThreads(data.threads || []);
    } catch (e) {
      setError(e.message);
    }
  }

  // ★ 仅刷新 checkpoint 列表，不动 messages / pendingToolCalls，
  //   用于 invoke / approve / reject / modify / replay 之后
  async function refreshCheckpointsOnly(threadId) {
    try {
      const cps = await api.listCheckpoints(threadId);
      setCheckpoints(cps.checkpoints || []);
    } catch (e) {
      // 静默失败不影响主流程
    }
  }

  async function loadThread(threadId) {
    try {
      const data = await api.getThread(threadId);
      const state = data.state || {};
      setMessages(state.messages || []);
      setCurrentCheckpointId(state.checkpoint_id);
      const cps = await api.listCheckpoints(threadId);
      setCheckpoints(cps.checkpoints || []);

      // ★ 关键修复：检测当前检查点是否处于"等待人工审批"状态
      //   触发条件：next_nodes 包含 'action' → 助手提议了 tool_call 但尚未决策
      //   修复前：永远把 pendingToolCalls 置 null，导致 action 按钮丢失
      const currentCp = (cps.checkpoints || []).find(
        (c) => c.checkpoint_id === state.checkpoint_id
      );
      const isPendingInterrupt = currentCp?.next_nodes?.includes('action');
      if (isPendingInterrupt) {
        const lastAssistant = [...(state.messages || [])]
          .reverse()
          .find((m) => m.role === 'assistant' && m.tool_calls && m.tool_calls.length);
        setPendingToolCalls(lastAssistant?.tool_calls || []);
      } else {
        setPendingToolCalls(null);
      }

      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleCreate() {
    try {
      const data = await api.createThread('新会话');
      await refreshThreads();
      setCurrentThreadId(data.thread_id);
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleDelete(threadId) {
    if (busy) return;
    setBusy(true);
    setError(null);
    const wasActive = currentThreadId === threadId;
    try {
      await api.deleteThread(threadId);
      // 清理本地状态：被删的是当前激活会话则全部重置
      if (wasActive) {
        setCurrentThreadId(null);
        setMessages([]);
        setPendingToolCalls(null);
        setCheckpoints([]);
        setCurrentCheckpointId(null);
      }
      await refreshThreads();
      toast.success('会话已删除');
    } catch (e) {
      setError(e.message);
      toast.error('删除失败: ' + e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSend() {
    if (!input.trim() || busy) return;
    let threadId = currentThreadId;
    if (!threadId) {
      const data = await api.createThread(input.trim().slice(0, 24));
      threadId = data.thread_id;
      setCurrentThreadId(threadId);
      await refreshThreads();
    } else {
      // 自动更新会话标题（取首条 user message）
      const t = threads.find((x) => x.thread_id === threadId);
      if (t && (t.title === '新会话' || !t.title)) {
        await api.renameThread(threadId, input.trim().slice(0, 24));
        await refreshThreads();
      }
    }

    const userMessage = { role: 'user', content: input.trim() };
    const optimistic = [...messages, userMessage];
    setMessages(optimistic);
    setInput('');
    setBusy(true);
    setError(null);

    try {
      const result = await api.invoke(threadId, [userMessage]);
      // ★ applyResult 已经设置好了 messages / pendingToolCalls / currentCheckpointId
      //   不再调用 loadThread（避免 loadThread 把 pendingToolCalls 改回 null）
      applyResult(result);
      await refreshThreads();
      // 仅刷新 checkpoint 列表与 checkpoint 元数据，不影响当前中断状态
      await refreshCheckpointsOnly(threadId);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function applyResult(result) {
    if (result.messages) setMessages(result.messages);
    setCurrentCheckpointId(result.checkpoint_id);
    if (result.status === 'interrupt') {
      setPendingToolCalls(result.pending_tool_calls || []);
    } else {
      setPendingToolCalls(null);
    }
  }

  async function handleApprove(modifications = []) {
    if (!currentThreadId || busy) return;
    setBusy(true);
    setError(null);
    try {
      // 决策矩阵：根据 modifications[i].modified 决定走哪条分支
      //   modified=false → 分支一【同意】 → POST /approve
      //   modified=true  → 分支三【修改】 → POST /modify
      const hasMod = modifications.some((m) => m.modified);
      const payload = modifications.map(({ id, name, args }) => ({ id, name, args }));
      const result = hasMod
        ? await api.modify(currentThreadId, payload)
        : await api.approve(currentThreadId);
      applyResult(result);
      toast.success(hasMod ? '已使用修改后的参数执行' : '已同意执行');
      await refreshCheckpointsOnly(currentThreadId);
    } catch (e) {
      setError(e.message);
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleReject(toolCallId) {
    if (!currentThreadId || busy) return;
    setBusy(true);
    setError(null);
    try {
      // 【分支二：拒绝】注入拒绝消息并强制 LLM 直接回答
      const result = await api.reject(currentThreadId, '用户拒绝该工具调用');
      applyResult(result);
      toast.warning('已拒绝该工具调用');
      await refreshCheckpointsOnly(currentThreadId);
    } catch (e) {
      setError(e.message);
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleReplay(checkpointId) {
    if (!currentThreadId || busy) return;
    const ok = await toast.confirm({
      kind: 'warning',
      title: '时间回溯',
      message: '从该 checkpoint 重新执行将创建一条新分支，确定吗？',
      confirmText: '回溯',
    });
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.replay(currentThreadId, checkpointId);
      applyResult(result);
      toast.success('已创建新分支');
      await refreshCheckpointsOnly(currentThreadId);
    } catch (e) {
      setError(e.message);
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  function handleKeyDown(e) {
    // ★ 中文输入法组合期间（拼音候选/上屏）按 Enter 不应触发发送：
    //   组合期 keydown 的 e.key 同样是 'Enter'，但此时 React state 里
    //   还是未上屏的拼音/旧文本，直接发送会发出错误内容。
    //   判定方式：isComposing 标记 + keyCode 229（Safari 不设 isComposing）
    if (e.nativeEvent?.isComposing || e.keyCode === 229) return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const hasInterrupt = pendingToolCalls && pendingToolCalls.length > 0;

  return (
    <div className="app-shell">
      <Sidebar
        threads={threads}
        currentId={currentThreadId}
        onSelect={setCurrentThreadId}
        onCreate={handleCreate}
        onDelete={handleDelete}
      />

      <main className="chat-pane">
        <header className="chat-header">
          <div>
            <h1>🤖 Human in the Loop</h1>
            <p className="subtitle">
              基于 LangGraph 思想 + DeepSeek + PostgreSQL 的可审核 Agent
            </p>
          </div>
          <div className="health-badge">
            {health?.ok ? (
              <span className="badge badge-ok">● DeepSeek {health.model}</span>
            ) : (
              <span className="badge badge-err">● 后端未连接</span>
            )}
            {health?.tavily_configured && (
              <span className="badge badge-info">Tavily 已启用</span>
            )}
            <span className="badge badge-info">PostgreSQL</span>
          </div>
        </header>

        {error && <div className="error-banner">⚠ {error}</div>}

        <div className="messages">
          {messages.length === 0 && !currentThreadId && (
            <div className="welcome">
              <h2>👋 你好！</h2>
              <p>这是一个可人工介入的 Agent 演示：</p>
              <ul>
                <li>当 Agent 想要调用工具（如 <code>web_search</code>）时，会暂停等待你的审批</li>
                <li>你可以选择 <strong>同意</strong> / <strong>拒绝</strong> / <strong>修改参数</strong></li>
                <li>右侧面板支持 <strong>时间回溯</strong>，从任意 checkpoint 重新执行</li>
                <li>所有会话、检查点均持久化到 PostgreSQL</li>
              </ul>
            </div>
          )}

          {messages.map((m, i) => (
            <MessageBubble key={m.id || i} message={m} />
          ))}

          {hasInterrupt && (
            <div className="interrupt-panel">
              <div className="interrupt-title">
                ⏸ Agent 请求执行以下工具，请审核：
              </div>
              {pendingToolCalls.map((tc, i) => (
                <ToolCallCard
                  key={tc.id || i}
                  toolCall={tc}
                  index={i}
                  onApprove={handleApprove}
                  onReject={handleReject}
                />
              ))}
            </div>
          )}

          {busy && <div className="thinking">🤖 Agent 思考中…</div>}
          <div ref={messagesEndRef} />
        </div>

        <div className="composer">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              currentThreadId
                ? '输入你的问题，回车发送…'
                : '直接输入问题以创建一个新会话…'
            }
            rows={2}
            disabled={busy || hasInterrupt}
          />
          <button
            className="btn btn-primary"
            onClick={handleSend}
            disabled={busy || hasInterrupt || !input.trim()}
          >
            发送
          </button>
        </div>
      </main>

      <aside className="right-pane">
        <div className="tab-bar">
          <button
            className={`tab ${rightTab === 'checkpoints' ? 'active' : ''}`}
            onClick={() => setRightTab('checkpoints')}
          >
            🕒 Checkpoints
          </button>
          <button
            className={`tab ${rightTab === 'state' ? 'active' : ''}`}
            onClick={() => setRightTab('state')}
          >
            📦 State
          </button>
        </div>

        <div className="tab-content">
          {rightTab === 'checkpoints' && (
            <CheckpointList
              checkpoints={checkpoints}
              currentId={currentCheckpointId}
              onReplay={handleReplay}
            />
          )}
          {rightTab === 'state' && (
            <div className="state-view">
              <h3>当前 AgentState</h3>
              <pre>{JSON.stringify(
                {
                  thread_id: currentThreadId,
                  checkpoint_id: currentCheckpointId,
                  message_count: messages.length,
                  next_nodes: checkpoints.find(
                    (c) => c.checkpoint_id === currentCheckpointId
                  )?.next_nodes,
                },
                null,
                2
              )}</pre>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
