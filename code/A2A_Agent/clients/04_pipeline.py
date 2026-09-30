"""
04 - 复杂管道示例
Pipeline Pattern

工作流：
Collect → Classify → [Parallel Processing] → Merge → Summarize → Translate → Output

构建可复用的 Agent 协作管道
"""
import asyncio
import uuid
import httpx
from a2a.client.legacy import A2AClient
from a2a.types import Message, Part, TextPart, Role, SendMessageRequest, MessageSendParams
from typing import List, Dict, Any
import time


def _build_text_message(text: str) -> SendMessageRequest:
    message = Message(
        message_id=str(uuid.uuid4()),
        role=Role.user,
        parts=[Part(root=TextPart(text=text))],
    )
    return SendMessageRequest(id=str(uuid.uuid4()), params=MessageSendParams(message=message))


async def _send_and_extract(client: A2AClient, req: SendMessageRequest) -> str:
    resp = await client.send_message(req)
    txt = ""
    result = getattr(resp.root, 'result', None)
    if result and hasattr(result, 'message'):
        msg_obj = getattr(result, 'message')
    else:
        msg_obj = result or getattr(resp, 'message', None)
    if msg_obj and hasattr(msg_obj, 'parts'):
        for part in msg_obj.parts:
            if hasattr(part.root, 'text'):
                txt = part.root.text
    return txt


class AgentPipeline:
    """Agent 协作管道"""

    def __init__(self, httpx_client: httpx.AsyncClient):
        self.agents: dict[str, A2AClient] = {}
        self.execution_log: list[dict[str, Any]] = []
        self.httpx_client = httpx_client

    async def add_agent(self, name: str, url: str):
        """添加 Agent 到管道"""
        self.agents[name] = A2AClient(httpx_client=self.httpx_client, url=url)
        print(f"  ✅ {name} Agent 已加入管道")

    async def execute_step(self, agent_name: str, message: str, description: str | None = None) -> str:
        """执行管道步骤"""
        if agent_name not in self.agents:
            raise ValueError(f"Agent {agent_name} 不存在")

        desc = description or f"执行 {agent_name}"
        print(f"\n🔄 {desc}...")

        start_time = time.time()

        req = _build_text_message(message)
        result = await _send_and_extract(self.agents[agent_name], req)
        
        elapsed = time.time() - start_time
        
        # 记录执行日志
        self.execution_log.append({
            "agent": agent_name,
            "description": desc,
            "input_length": len(message),
            "output_length": len(result),
            "elapsed_time": elapsed
        })
        
        print(f"  ✅ 完成 ({len(result)} 字符, {elapsed:.2f}秒)")
        
        return result
    
    async def execute_parallel(self, tasks: List[Dict[str, Any]], description: str | None = None) -> List[str]:
        """并行执行多个步骤。
        简化: 直接为每个任务创建消费协程, 而不是先收集生成器再逐个迭代。"""
        desc = description or "并行执行任务"
        print(f"\n🔄 {desc}...")
        print(f"  📊 任务数量: {len(tasks)}")
        
        start_time = time.time()
        
        # 创建消费任务 (真正并行处理事件流)
        async def _run_single(agent_name: str, message: str) -> str:
            if agent_name not in self.agents:
                raise ValueError(f"Agent {agent_name} 不存在")
            req = _build_text_message(message)
            return await _send_and_extract(self.agents[agent_name], req)

        async_tasks = [asyncio.create_task(_run_single(t['agent'], t['message'])) for t in tasks]
        outputs = await asyncio.gather(*async_tasks)
        
        elapsed = time.time() - start_time
        
        # 记录执行日志
        self.execution_log.append({
            "operation": "parallel_execution",
            "description": desc,
            "task_count": len(tasks),
            "elapsed_time": elapsed
        })
        
        print(f"  ✅ 所有任务完成 ({elapsed:.2f}秒)")
        
        return outputs
    
    def print_execution_log(self):
        """打印执行日志"""
        print("\n" + "="*80)
        print("📊 管道执行日志")
        print("="*80)
        
        total_time = 0
        for i, log in enumerate(self.execution_log, 1):
            if 'agent' in log:
                print(f"\n{i}. {log['description']}")
                print(f"   Agent: {log['agent']}")
                print(f"   输入: {log['input_length']} 字符")
                print(f"   输出: {log['output_length']} 字符")
                print(f"   耗时: {log['elapsed_time']:.2f} 秒")
                total_time += log['elapsed_time']
            else:
                print(f"\n{i}. {log['description']}")
                print(f"   任务数: {log['task_count']}")
                print(f"   耗时: {log['elapsed_time']:.2f} 秒")
                total_time += log['elapsed_time']
        
        print(f"\n{'='*80}")
        print(f"总耗时: {total_time:.2f} 秒")
        print(f"{'='*80}")


async def main():
    print("\n" + "="*80)
    print("示例 4: 复杂管道 - 完整的 Agent 协作工作流")
    print("="*80)
    
    httpx_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

    try:
        # 创建管道 (共享 httpx client)
        pipeline = AgentPipeline(httpx_client=httpx_client)
        
        # 步骤 1: 初始化管道
        print("\n📡 步骤 1: 初始化 Agent 管道...")
        
        await pipeline.add_agent("collector", "http://localhost:8001")
        await pipeline.add_agent("classifier", "http://localhost:8004")
        await pipeline.add_agent("summarizer", "http://localhost:8002")
        await pipeline.add_agent("translator", "http://localhost:8003")
        
        input("\n按 Enter 开始执行管道...")
        
        # 步骤 2: 并行收集多个主题的信息
        print("\n" + "="*80)
        print("管道执行开始")
        print("="*80)
        
        topics = ["集成电路","工业软件","生物医药"]
        parallel_tasks = [
            {"agent": "collector", "message": f"收集关于 {topic} 的信息，限制 2 条"}
            for topic in topics
        ]
        
        news_list = await pipeline.execute_parallel(
            parallel_tasks,
            description=f"并行收集 {len(topics)} 个主题的信息"
        )
        
        # 步骤 3: 合并信息
        all_news = "\n\n=== 分隔线 ===\n\n".join(news_list)
        print(f"\n✅ 信息合并完成 (总计 {len(all_news)} 字符)")
        
        # 步骤 4: 分类
        classification = await pipeline.execute_step(
            "classifier",
            f"对以下内容分类：\n\n{all_news}",
            "信息内容分类"
        )
        
        # 步骤 5: 生成摘要
        summary = await pipeline.execute_step(
            "summarizer",
            f"对以下信息生成详细摘要：\n\n{all_news}",
            "生成信息摘要"
        )
        
        # 步骤 6: 翻译
        translation = await pipeline.execute_step(
            "translator",
            f"将以下摘要翻译成英文：\n\n{summary}",
            "翻译成英文"
        )
        
        # 打印执行日志
        pipeline.print_execution_log()
        
        # 最终结果
        print("\n" + "="*80)
        print("🎉 管道执行完成！")
        print("="*80)
        
        print("\n📄 管道输出结果:")
        print("="*80)
        print("\n## 分类结果")
        print(classification[:200] + "..." if len(classification) > 200 else classification)
        
        print("\n## 中文摘要")
        print(summary[:300] + "..." if len(summary) > 300 else summary)
        
        print("\n## 英文翻译")
        print(translation)
        print("="*80)
        
    except Exception as e:  # noqa: BLE001
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await httpx_client.aclose()


def print_summary():
    """打印知识点总结"""
    print("\n📚 知识点总结")
    print("="*80)
    print("\n✅ 管道模式的特点:")
    print("   1. 封装复杂工作流")
    print("   2. 可复用组件")
    print("   3. 清晰的执行顺序")
    print("   4. 易于维护和扩展")
    
    print("\n✅ 适用场景:")
    print("   - 企业级应用")
    print("   - 数据处理流水线")
    print("   - 自动化工作流")
    print("   - ETL 系统")
    
    print("\n✅ 设计要点:")
    print("   - 模块化设计")
    print("   - 错误处理")
    print("   - 日志记录")
    print("   - 性能监控")
    
    print("\n✅ 优点:")
    print("   - 高度可复用")
    print("   - 易于测试")
    print("   - 便于监控")
    print("   - 灵活组合")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    print("\n🎓 这是一个教学示例")
    print("💡 学习如何构建可复用的 Agent 协作管道\n")
    
    try:
        asyncio.run(main())
        print_summary()
        
        print("\n🎯 恭喜!")
        print("="*80)
        print("你已经掌握了 Agent 协作的核心模式:")
        print("  ✅ 串行协作")
        print("  ✅ 并行协作")
        print("  ✅ 条件路由")
        print("  ✅ 管道模式")
        print("\n现在你可以构建复杂的多 Agent 应用了!")
        print("="*80 + "\n")
    
    except KeyboardInterrupt:
        print("\n\n👋 示例已取消")
