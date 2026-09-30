import re
from langchain_deepseek import ChatDeepSeek
from .config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL

# 路由需要确定性，temperature 设为 0
llm_router = ChatDeepSeek(model=DEEPSEEK_MODEL, api_key=DEEPSEEK_API_KEY, temperature=0)

VALID_NPCS = ["村长", "铁匠", "药师"]

# 关键词兜底规则（LLM路由失败时使用）
KEYWORD_RULES = {
    "铁匠": [
        "剑", "刀", "武器", "兵器", "打造", "锻造", "修理", "装备", "盔甲", "甲胄",
        "铁", "锤", "盾", "弓", "箭", "符文剑", "战斗", "攻击力",
    ],
    "药师": [
        "药", "伤", "治疗", "草药", "病", "疼", "痛", "健康", "治愈", "绷带",
        "包扎", "中毒", "感冒", "发烧", "恢复", "药膏", "医师", "医疗",
    ],
}


def _parse_npc(text: str):
    """从模型输出中鲁棒地提取NPC名字。

    处理这些情况：
    - "铁匠"            -> 铁匠
    - "铁匠。" / "铁匠." -> 铁匠
    - ""铁匠""          -> 铁匠
    - "我选择铁匠"       -> 铁匠
    - "村长：好的"       -> 村长
    """
    if not text:
        return None
    text = text.strip()

    # 1. 去掉标点、空白、引号后做精确匹配
    cleaned = re.sub(r'[\s。．.，,！!？?：:；;、"\'''`【】\[\]（）()]+', '', text)
    if cleaned in VALID_NPCS:
        return cleaned

    # 2. 模型输出包含说明文字时，检查是否包含某个NPC名字
    #    （按名字长度优先检查，避免"村长"在句子里被意外优先匹配）
    for npc in VALID_NPCS:
        if npc in text:
            return npc

    return None


def _keyword_route(user_input: str) -> str:
    """基于关键词的兜底路由"""
    for npc, keywords in KEYWORD_RULES.items():
        if any(kw in user_input for kw in keywords):
            return npc
    return "村长"  # 一般性问题默认村长


def route_node(state):
    """用LLM决定分配给哪个NPC，失败时用关键词规则兜底"""
    user_input = state["input"]
    chat_history = state.get("chat_history", [])

    system_prompt = """你是一个游戏调度器，负责把玩家的话分配给最合适的NPC。

可选的NPC：
- 村长：负责村庄管理、历史故事、传说、人物介绍、一般建议和闲聊
- 铁匠：负责武器装备、打造修理、战斗相关
- 药师：负责治疗、草药、健康相关

规则：
1. 只能选择一个NPC，必须严格判断玩家问题的领域
2. 只输出NPC的名字（村长、铁匠、药师三个词之一），不要输出任何其他文字、标点或解释
3. 对话历史中，assistant消息以"[NPC名]"开头表示上一个回答的NPC。如果玩家在延续该NPC的话题，就继续选择同一个NPC
4. 武器、装备、打造类问题必须选铁匠；伤病、药品、治疗类问题必须选药师；只有与上述无关时才选村长
5. 不要因为不确定就总选村长

示例：
玩家说"我需要买武器" -> 铁匠
玩家说"这把剑多少钱" -> 铁匠
玩家说"怎么修理盔甲" -> 铁匠
玩家说"我受伤了" -> 药师
玩家说"有什么药能治感冒" -> 药师
玩家说"这里有什么NPC" -> 村长
玩家说"你好" -> 村长
玩家说"讲讲村子的历史" -> 村长"""

    # 构建包含历史的消息
    messages = [{"role": "system", "content": system_prompt}]

    # 添加最近的对话历史（最多5轮）
    if chat_history:
        recent_history = chat_history[-10:]
        messages.extend(recent_history)

    messages.append({"role": "user", "content": user_input})

    # 先尝试LLM路由
    chosen_npc = None
    try:
        resp = llm_router.invoke(messages)
        chosen_npc = _parse_npc(resp.content)
    except Exception:
        chosen_npc = None

    # LLM路由失败时，用关键词规则兜底
    if chosen_npc is None:
        chosen_npc = _keyword_route(user_input)

    return {"npc_targets": [chosen_npc]}
