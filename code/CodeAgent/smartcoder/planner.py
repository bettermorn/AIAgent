import json
from .llm import suggest_plan_with_llm, API_KEY, MODEL

def parse_instruction_to_plan(instruction: str, analysis_summary: str = "") -> list[dict]:
    """生成代码修改计划。"""
    if API_KEY and analysis_summary:
        print(f"(正在使用 DeepSeek 模型 {MODEL} 生成计划...)")
        llm_response = suggest_plan_with_llm(instruction, analysis_summary)
        if llm_response and "changes" in llm_response:
            steps = []
            for change in llm_response["changes"]:
                steps.append({
                    "action": "edit",
                    "args": {
                        "file": change["file"],
                        "old": change["code_before"],
                        "new": change["code_after"]
                    },
                    "explain": change["description"]
                })
            return steps

    # 当LLM不可用时的提示和后备方案
    if not API_KEY:
        print("\n⚠️  警告: 未配置 DEEPSEEK_API_KEY")
        print("💡 提示: 请在项目根目录创建 config.env 文件（参考 config.env.example）:")
        print("   DEEPSEEK_API_KEY=your-api-key-here")
        print("   或设置环境变量: export DEEPSEEK_API_KEY='your-api-key-here'")
        print("   然后重新运行命令\n")
    else:
        print("(正在使用基础分析生成计划...)")

    # 简单后备方案
    return [{"action": "noop", "args": {}, "explain": "此操作需要LLM来理解和生成代码更改。"}]

def render_plan_markdown(steps: list[dict]) -> str:
    plan_type = f"LLM ({MODEL})" if API_KEY else "确定性"
    lines = [f"# 编辑计划 ({plan_type})", ""]
    if not steps:
        lines.append("未为此指令生成步骤。")
    else:
        for i, st in enumerate(steps, 1):
            lines.append(f"### 步骤 {i}: {st['action']}")
            lines.append(f"- 原因: {st['explain']}")
            if st.get("args"):
                lines.append(f"- 参数: `{json.dumps(st['args'])}`")
            lines.append("")
    return "\n".join(lines)
