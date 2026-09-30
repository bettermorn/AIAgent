'use strict';

const { nanoid } = require('nanoid');
const deepseek = require('./deepseek');
const { TOOL_DEFINITIONS, callTool } = require('./tools');
const store = require('./db/store');

const SYSTEM_PROMPT = `你是一名智能研究助手，可以使用搜索工具获取最新信息。
- 每次最多只发起一次搜索调用，严禁在同一轮并行发起多个搜索；
- 搜索时把需求合并成一个完整的查询关键词（例如同时要中英文信息就只用一条查询）；
- 只有在确实需要新信息时才搜索；
- 如果一轮搜索结果不够，可以等结果返回后在下一轮再发起一次新的搜索；
- 当工具结果返回后，请基于真实数据给出简洁、清晰的最终回答。`;

class Agent {
  constructor() {
    this.systemPrompt = SYSTEM_PROMPT;
  }

  /**
   * 运行 Agent 直到遇到中断（需要人工审批）或结束。
   */
  async invoke(threadId, inputMessages = []) {
    const state = await store.getCurrentState(threadId);
    if (!state) {
      await store.renameThread(threadId, deriveTitle(inputMessages) || '新会话');
    }

    let messages = state ? state.messages : [];
    messages = mergeMessages(messages, normalizeInputMessages(inputMessages));

    const lastCp = await getLastCheckpoint(threadId);
    let parentId = lastCp ? lastCp.checkpoint_id : null;
    let step = lastCp ? lastCp.step + 1 : 0;

    parentId = await store.saveCheckpoint(threadId, {
      parentId,
      step: step++,
      nextNodes: ['llm'],
      messages,
      scratch: state ? state.scratch : null,
      lnode: state ? state.lnode : null,
      count: state ? state.count : 0,
    });

    const aiMessage = await this.callLLM(messages);
    messages = mergeMessages(messages, [aiMessage]);

    const hasAction = (aiMessage.tool_calls || []).length > 0;

    if (!hasAction) {
      const cpId = await store.saveCheckpoint(threadId, {
        parentId,
        step: step++,
        nextNodes: [],
        messages,
      });
      return { status: 'end', checkpoint_id: cpId, messages };
    }

    const cpId = await store.saveCheckpoint(threadId, {
      parentId,
      step: step++,
      nextNodes: ['action'],
      messages,
    });

    return {
      status: 'interrupt',
      checkpoint_id: cpId,
      pending_tool_calls: aiMessage.tool_calls,
      messages,
    };
  }

  /**
   * ============================================================
   *  三大分支入口（Human-in-the-Loop 决策点）
   * ============================================================
   *  每个分支会在 PostgreSQL 的 checkpoint 上记录 decision 标签，
   *  从而在 UI 上形成清晰的分支树（approve / reject / modify）。
   * ============================================================
   */

  /**
   * 分支一：【同意执行】按 Assistant 提议的参数直接调用工具。
   * 等价于 LangGraph 中的 `graph.stream(None, thread)`。
   */
  async approve(threadId, note = '') {
    return this._continueWithDecision(threadId, {
      decision: 'approve',
      decisionNote: note,
    });
  }

  /**
   * 分支二：【拒绝执行】不调用工具，向模型注入"拒绝"消息并强制基于已有信息回答。
   * 对应 LangGraph 中的 `update_state(as_node=...)` 注入拒绝指令。
   */
  async reject(threadId, reason = '') {
    const state = await store.getCurrentState(threadId);
    if (!state) throw new Error('thread 不存在');

    const lastCheckpoint = await getCheckpointById(state.checkpoint_id);

    // 注入一条 human 消息告知模型被拒绝
    const rejection = {
      id: nanoid(),
      role: 'user',
      content: `（人工拒绝执行该工具调用）${reason ? '\n原因: ' + reason : ''}\n请直接基于已有信息作答，不要再调用工具。`,
    };
    let messages = mergeMessages(state.messages, [rejection]);

    let parentId = lastCheckpoint ? lastCheckpoint.checkpoint_id : null;
    let step = lastCheckpoint ? lastCheckpoint.step + 1 : 0;

    // ★ 这一步就是分支点，decision = 'reject'
    parentId = await store.saveCheckpoint(threadId, {
      parentId,
      step: step++,
      nextNodes: ['llm'],
      messages,
      decision: 'reject',
      decisionNote: reason || null,
    });

    const aiMessage = await this.callLLM(messages, {
      disableTools: true,
      directive:
        '【重要】用户拒绝了工具调用。请只针对当前最后的问题直接作答，' +
        '禁止重复或复述对话历史中已经出现过的回答内容。回答保持简洁。',
    });
    // ★ 把"拒绝"标签固化到本次 assistant 回复上，UI 上能立刻分辨
    aiMessage.decision = 'reject';
    messages = mergeMessages(messages, [aiMessage]);

    const cpId = await store.saveCheckpoint(threadId, {
      parentId,
      step: step++,
      nextNodes: [],
      messages,
    });
    return {
      status: 'end',
      decision: 'reject',
      checkpoint_id: cpId,
      messages,
    };
  }

  /**
   * 分支三：【修改参数后执行】编辑 Assistant 提议的 tool_calls 后再调用。
   * 对应 LangGraph 中的 `graph.update_state(...)` 改写 tool_calls。
   */
  async modifyAndApprove(threadId, modifications = [], note = '') {
    const state = await store.getCurrentState(threadId);
    if (!state) throw new Error('thread 不存在');

    const lastCheckpoint = await getCheckpointById(state.checkpoint_id);
    if (!lastCheckpoint || !lastCheckpoint.next_nodes.includes('action')) {
      throw new Error('当前没有待修改的 tool_call');
    }

    const messages = [...state.messages];
    const idx = messages
      .map((m, i) => ({ m, i }))
      .reverse()
      .find(({ m }) => m.role === 'assistant' && m.tool_calls && m.tool_calls.length)?.i;
    if (idx === undefined) throw new Error('未找到待修改的 assistant 消息');

    // 应用修改：name / args 都允许改。
    // ★ 被修改的 assistant 消息分配新的 msg_id（而不是覆盖原消息），
    //   这样历史 checkpoint 的快照仍保留"原始提议的参数"，
    //   回溯到审批节点时看到的是当时真正的提议内容。
    const updated = messages.map((m, i) => {
      if (i !== idx) return m;
      let changed = false;
      const newToolCalls = (m.tool_calls || []).map((tc) => {
        const mod = modifications.find((x) => x.id === tc.id);
        if (!mod) return tc;
        changed = true;
        return {
          ...tc,
          name: mod.name || tc.name,
          args: mod.args !== undefined ? mod.args : tc.args,
        };
      });
      if (!changed) return m;
      return { ...m, id: nanoid(), tool_calls: newToolCalls };
    });

    let parentId = lastCheckpoint.checkpoint_id;
    let step = lastCheckpoint.step + 1;

    // ★ 这一步是分支点：decision = 'modify'
    const modifiedArgsDesc = modifications
      .map((m) => `${m.name || ''}(${JSON.stringify(m.args)})`)
      .join('; ');
    parentId = await store.saveCheckpoint(threadId, {
      parentId,
      step: step++,
      nextNodes: ['action'],
      messages: updated,
      decision: 'modify',
      decisionNote: note || modifiedArgsDesc,
    });

    // 之后按修改后的参数继续走工具 → LLM 流程
    // ★ 传入修改后的参数描述，让 LLM 只回答修改后的问题
    const result = await this._runActionAndLlm(
      threadId,
      parentId,
      step,
      'modify',
      modifiedArgsDesc
    );
    return { ...result, decision: 'modify' };
  }

  /* ============================================================
   *  以下为内部辅助方法
   * ============================================================ */

  /** approve 的核心实现：执行工具 + 再次调用 LLM，并在起始 checkpoint 标 approve */
  async _continueWithDecision(threadId, opts) {
    const state = await store.getCurrentState(threadId);
    if (!state) throw new Error('thread 不存在');

    const lastCheckpoint = await getCheckpointById(state.checkpoint_id);
    if (!lastCheckpoint || !lastCheckpoint.next_nodes.includes('action')) {
      return {
        status: 'end',
        decision: opts.decision,
        messages: state.messages,
      };
    }

    const lastAssistant = [...state.messages]
      .reverse()
      .find((m) => m.role === 'assistant' && m.tool_calls && m.tool_calls.length);
    if (!lastAssistant) {
      return {
        status: 'end',
        decision: opts.decision,
        messages: state.messages,
      };
    }

    // 先在分支点打个 decision=approve 的 checkpoint（即使消息没变）
    // 这样 UI 上就能看到「✅ 同意」这条分支标签
    let parentId = lastCheckpoint.checkpoint_id;
    let step = lastCheckpoint.step + 1;
    parentId = await store.saveCheckpoint(threadId, {
      parentId,
      step: step++,
      nextNodes: ['action'],
      messages: state.messages,
      decision: opts.decision,
      decisionNote: opts.decisionNote || null,
    });

    return this._runActionAndLlm(threadId, parentId, step, opts.decision);
  }

  /**
   * 内部：执行工具 → 再次 LLM → 写 checkpoint。
   * @param decisionTag  'approve' | 'modify' | undefined
   * @param modifiedArgs modify 分支时传：本次实际执行的（修改后）参数描述
   */
  async _runActionAndLlm(threadId, parentId, step, decisionTag, modifiedArgsDesc) {
    const state = await store.getCurrentState(threadId);
    const lastAssistant = [...state.messages]
      .reverse()
      .find((m) => m.role === 'assistant' && m.tool_calls && m.tool_calls.length);

    const toolMessages = [];
    for (const tc of lastAssistant.tool_calls) {
      const content = await callTool(tc.name, tc.args);
      toolMessages.push({
        id: nanoid(),
        role: 'tool',
        name: tc.name,
        tool_call_id: tc.id,
        content,
      });
    }

    let messages = mergeMessages(state.messages, toolMessages);

    // ★ modify 分支：在对话流中显式注入一条 user 消息（与 reject 分支同款模式）。
    //   单靠隐藏的 system 指令压不住上下文里"原始问题"的主流语义，
    //   必须让"回答修改后的查询"成为对话的最新指令，并持久化到 checkpoint。
    if (decisionTag === 'modify') {
      const modification = {
        id: nanoid(),
        role: 'user',
        content:
          `（人工将工具参数修改为：${modifiedArgsDesc || '见上方工具调用'}，并已执行）\n` +
          `请只根据上面这次工具返回的结果，回答修改后的查询，` +
          `不要回答、复述或总结修改参数之前的旧问题及其相关内容。`,
      };
      messages = mergeMessages(messages, [modification]);
    }

    parentId = await store.saveCheckpoint(threadId, {
      parentId,
      step: step++,
      nextNodes: ['llm'],
      messages,
    });

    // ★ modify 分支：附加隐藏 system 指令，双保险
    let directive;
    if (decisionTag === 'modify') {
      directive =
        `【重要】用户修改了工具调用参数后重新执行。实际执行的参数是：${modifiedArgsDesc || '（见上方工具调用）'}。\n` +
        `请只针对修改后的查询/参数给出回答，严格遵循以下要求：\n` +
        `1. 只回答修改后的问题，禁止重复或复述此前已经给出过的回答内容；\n` +
        `2. 禁止提及或回答修改参数之前的旧问题；\n` +
        `3. 不要解释修改过程本身，直接给出基于本次工具结果的新回答；\n` +
        `4. 回答保持简洁。`;
    }

    const aiMessage = await this.callLLM(messages, { directive });
    // ★ 把决策标签挂到 assistant 消息上，UI 即可看到「✅ 同意 / ✏️ 修改」
    if (decisionTag) aiMessage.decision = decisionTag;
    messages = mergeMessages(messages, [aiMessage]);

    const hasAction = (aiMessage.tool_calls || []).length > 0;
    const cpId = await store.saveCheckpoint(threadId, {
      parentId,
      step: step++,
      nextNodes: hasAction ? ['action'] : [],
      messages,
    });

    return {
      status: hasAction ? 'interrupt' : 'end',
      decision: decisionTag,
      checkpoint_id: cpId,
      pending_tool_calls: hasAction ? aiMessage.tool_calls : null,
      messages,
    };
  }

  /**
   * 时间回溯：基于历史 checkpoint 的【快照】重新创建分支。
   *
   * 分支语义按 checkpoint.next_nodes 决定（这是 LangGraph 的 node 语义）：
   *   - ['action']  → 该节点曾等待人工审批 → 恢复中断状态，
   *                   前端重新显示「同意 / 拒绝 / 修改」三个按钮
   *   - ['llm']     → 该节点待执行 LLM → 用快照消息重新调用 LLM
   *   - []          → 已结束的节点 → 仅恢复该时刻的状态
   */
  async replayFrom(threadId, checkpointId) {
    const cp = await store.getCheckpoint(checkpointId);
    if (!cp) throw new Error('checkpoint 不存在');
    if (cp.thread_id !== threadId) throw new Error('checkpoint 不属于该会话');

    const messages = cp.messages;
    let parentId = cp.checkpoint_id;
    let step = cp.step + 1;

    // ── 情况 A：回到"等待人工审批"的节点 ─────────────────────
    // 恢复 interrupt 状态，UI 重新弹出同意/拒绝/修改面板
    if (cp.next_nodes.includes('action')) {
      const lastAssistant = [...messages]
        .reverse()
        .find((m) => m.role === 'assistant' && m.tool_calls && m.tool_calls.length);
      if (lastAssistant) {
        const cpId = await store.saveCheckpoint(threadId, {
          parentId,
          step: step++,
          nextNodes: ['action'],
          messages,
          scratch: cp.scratch,
          decisionNote: '时间回溯：恢复到待审批状态',
        });
        return {
          status: 'interrupt',
          checkpoint_id: cpId,
          messages,
          pending_tool_calls: lastAssistant.tool_calls,
        };
      }
    }

    // ── 情况 B：回到"待执行 LLM"的节点 ───────────────────────
    // 用快照消息重新调用 LLM（可能再次提议工具 → 再次中断）
    if (cp.next_nodes.includes('llm') || messages.length > 0) {
      parentId = await store.saveCheckpoint(threadId, {
        parentId,
        step: step++,
        nextNodes: ['llm'],
        messages,
        scratch: cp.scratch,
        decisionNote: '时间回溯：重新执行 LLM',
      });

      const ai = await this.callLLM(messages, {
        directive:
          '【重要】这是一次时间回溯后的重新生成。请只针对当前最后的问题/工具结果作答，' +
          '禁止重复或复述对话历史中已经出现过的回答内容。回答保持简洁。',
      });
      const merged = mergeMessages(messages, [ai]);
      const hasAction = (ai.tool_calls || []).length > 0;
      const cpId = await store.saveCheckpoint(threadId, {
        parentId,
        step: step++,
        nextNodes: hasAction ? ['action'] : [],
        messages: merged,
      });
      return {
        status: hasAction ? 'interrupt' : 'end',
        checkpoint_id: cpId,
        messages: merged,
        pending_tool_calls: hasAction ? ai.tool_calls : null,
      };
    }

    // ── 情况 C：空会话 / 已结束 ──────────────────────────────
    const cpId = await store.saveCheckpoint(threadId, {
      parentId,
      step: step++,
      nextNodes: [],
      messages,
      scratch: cp.scratch,
    });
    return { status: 'end', checkpoint_id: cpId, messages };
  }

  /* ---------------------- LLM ---------------------- */

  async callLLM(messages, opts = {}) {
    const sysMessages = [{ role: 'system', content: this.systemPrompt }];
    // ★ 追加一次性指令（如"只回答修改后的问题"），不落库、只影响本次生成
    if (opts.directive) {
      sysMessages.push({ role: 'system', content: opts.directive });
    }
    const sanitized = sanitizeMessagesForLLM(messages);
    const allMessages = [...sysMessages, ...sanitized];
    const resp = await deepseek.chat({
      messages: allMessages,
      tools: opts.disableTools ? undefined : TOOL_DEFINITIONS,
    });
    // ★ 硬性限制：无论模型返回多少个 tool_calls，只保留第一个。
    //   （模型偶尔会并行提议多次搜索；只保留 1 个保证每次审批只处理 1 次调用）
    const toolCalls = (resp.tool_calls || []).slice(0, 1);
    return {
      id: nanoid(),
      role: 'assistant',
      content: resp.content,
      // 思考模式的推理内容，随消息保存，重放/回溯时必须传回
      reasoning_content: resp.reasoning_content || '',
      tool_calls: toolCalls,
    };
  }

  /* ============================================================
   *  向后兼容：保留旧 API 名称
   * ============================================================ */
  continue(threadId) {
    return this.approve(threadId);
  }
  modifyAndContinue(threadId, modifications) {
    return this.modifyAndApprove(threadId, modifications);
  }
}

/* ============================================================
 * 工具函数
 * ============================================================ */

/**
 * 把 messages 处理成对 DeepSeek/OpenAI 合法可发的形式：
 *   - 任何 assistant.tool_calls 必须紧跟对应的 tool 消息
 *   - 缺失应答的 tool_call 必须从 assistant 上摘掉
 *   - 孤立（前面没有 assistant 引用）的 tool 消息也要删掉
 *   - 思考模式下，assistant.tool_calls 缺少 reasoning_content 时
 *     必须整轮降级为纯文本（见第 4 步）
 *
 * 这是 LangGraph `RemoveMessage` 的等价操作：调 LLM 时不修改 DB，
 * 只在内存里修正，避免 DeepSeek 抛
 *   "An assistant message with 'tool_calls' must be followed by tool messages..."
 *   "The `reasoning_content` in the thinking mode must be passed back to the API."
 */
function sanitizeMessagesForLLM(messages) {
  // 1. 收集所有 tool 消息应答过的 tool_call_id
  const answeredIds = new Set();
  for (const m of messages) {
    if (m && m.role === 'tool' && m.tool_call_id) {
      answeredIds.add(m.tool_call_id);
    }
  }

  // 2. 对每条 assistant 消息，过滤掉未被应答的 tool_calls
  const cleaned = messages.map((m) => {
    if (!m || m.role !== 'assistant' || !m.tool_calls || !m.tool_calls.length) {
      return m;
    }
    const remaining = m.tool_calls.filter((tc) => tc && answeredIds.has(tc.id));
    if (remaining.length === m.tool_calls.length) return m;
    // 深拷贝避免污染原始对象
    return { ...m, tool_calls: remaining };
  });

  // 3. 删掉孤立 tool 消息（找不到对应 assistant.tool_calls 的）
  const validToolIds = new Set();
  for (const m of cleaned) {
    if (m && m.role === 'assistant' && m.tool_calls) {
      for (const tc of m.tool_calls) if (tc && tc.id) validToolIds.add(tc.id);
    }
  }
  const kept = cleaned.filter((m) => {
    if (m && m.role === 'tool') return validToolIds.has(m.tool_call_id);
    return true;
  });

  // 4. 思考模式兜底：assistant.tool_calls 若缺少 reasoning_content，
  //    DeepSeek 会拒绝整个请求。典型场景：
  //      a) reasoning_content 落库之前保存的旧会话（时间回溯会重放这些历史）
  //      b) 模型某些轮次未返回思考内容
  //    降级方案：把该轮工具调用改写成纯文本 user/assistant 消息，
  //    语义信息不丢，但不再依赖 reasoning_content。
  const degradedIds = new Set();
  for (const m of kept) {
    if (
      m &&
      m.role === 'assistant' &&
      m.tool_calls &&
      m.tool_calls.length &&
      !m.reasoning_content
    ) {
      for (const tc of m.tool_calls) {
        if (tc && tc.id) degradedIds.add(tc.id);
      }
    }
  }
  if (degradedIds.size === 0) return kept;

  return kept
    .map((m) => {
      // 4a. assistant：摘掉缺 reasoning_content 的 tool_calls，改写成文字描述
      if (
        m &&
        m.role === 'assistant' &&
        m.tool_calls &&
        m.tool_calls.some((tc) => degradedIds.has(tc.id))
      ) {
        const desc = m.tool_calls
          .filter((tc) => degradedIds.has(tc.id))
          .map((tc) => `${tc.name}(${JSON.stringify(tc.args || {})})`)
          .join('; ');
        return {
          ...m,
          tool_calls: m.tool_calls.filter((tc) => !degradedIds.has(tc.id)),
          content: m.content && m.content.trim()
            ? m.content
            : `（此前调用了工具：${desc}）`,
        };
      }
      // 4b. 对应的 tool 应答：转成 user 消息保留结果内容
      if (m && m.role === 'tool' && degradedIds.has(m.tool_call_id)) {
        return {
          id: m.id,
          role: 'user',
          content: `[工具 ${m.name || ''} 返回结果]\n${m.content || ''}`,
        };
      }
      return m;
    })
    .filter((m) => {
      // 4c. 清理既无内容又无 tool_calls 的空 assistant 消息
      if (
        m.role === 'assistant' &&
        (!m.content || !m.content.trim()) &&
        (!m.tool_calls || m.tool_calls.length === 0)
      ) {
        return false;
      }
      return true;
    });
}

function normalizeInputMessages(input) {
  return input.map((m) => {
    if (m.role) return { id: m.id || nanoid(), ...m };
    if (m.type === 'human') {
      return { id: m.id || nanoid(), role: 'user', content: m.content };
    }
    if (m.type === 'ai') {
      return {
        id: m.id || nanoid(),
        role: 'assistant',
        content: m.content,
        tool_calls: m.tool_calls,
      };
    }
    if (m.type === 'system') {
      return { id: m.id || nanoid(), role: 'system', content: m.content };
    }
    return {
      id: m.id || nanoid(),
      role: 'user',
      content: String(m.content || ''),
    };
  });
}

function mergeMessages(left, right) {
  const result = [...left];
  for (const m of right) {
    const i = result.findIndex((x) => x.id === m.id);
    if (i >= 0) result[i] = m;
    else result.push(m);
  }
  return result;
}

function deriveTitle(messages) {
  for (const m of messages) {
    if ((m.role === 'user' || m.type === 'human') && m.content) {
      return String(m.content).slice(0, 24);
    }
  }
  return null;
}

async function getLastCheckpoint(threadId) {
  const list = await store.listCheckpoints(threadId);
  return list[0] || null;
}

async function getCheckpointById(cpId) {
  if (!cpId) return null;
  return store.getCheckpoint(cpId);
}

module.exports = { Agent };
