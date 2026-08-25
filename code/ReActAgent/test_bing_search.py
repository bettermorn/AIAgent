import os

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    BingGroundingTool,
    BingGroundingSearchToolParameters,
    BingGroundingSearchConfiguration,
)


BING_CONNECTION_NAME = "Search"


def create_agent(project):
    """
    创建支持 Bing Grounding 的 Agent。
    """

    bing_connection = project.connections.get(BING_CONNECTION_NAME)

    agent = project.agents.create_version(
        agent_name="MyChineseSearchAgent",

        definition=PromptAgentDefinition(
            model="qwen--qwen36-27b",

            instructions="""
你是一名支持中文的智能搜索助手。

请遵循以下要求：

1. 用户可以使用中文提问。
2. 对于天气、新闻、日期、价格、股票、体育、旅游、实时信息和最新信息等问题，必须使用 Bing Grounding 搜索。
3. 必要时，可以将中文问题转换成适合搜索的中文、英文或中英文组合查询。
4. 搜索完成后，必须使用中文回答。
5. 回答应尽量准确、简洁，并优先使用最新的搜索结果。
6. 如果搜索结果中有来源，请在回答中列出相关来源。
""",

            tools=[
                BingGroundingTool(
                    bing_grounding=BingGroundingSearchToolParameters(
                        search_configurations=[
                            BingGroundingSearchConfiguration(
                                project_connection_id=bing_connection.id
                            )
                        ]
                    )
                )
            ],
        ),

        description="支持中文交互搜索的 Bing Grounding Agent",
    )

    print(
        f"Agent created "
        f"(id: {agent.id}, name: {agent.name}, version: {agent.version})"
    )

    return agent


def search_with_agent(openai_client, agent, user_question):
    """
    使用 Agent 搜索一次用户问题，并以流式方式输出结果。
    """

    prompt = f"""
请使用 Bing Grounding 搜索下面的问题，并用中文回答。
如果问题涉及实时信息，必须以搜索结果为准。
请在回答末尾列出相关来源。

用户问题：
{user_question}
"""

    citations = []

    try:
        stream_response = openai_client.responses.create(
            stream=True,

            # 强制调用 Bing Grounding
            tool_choice="required",

            input=prompt,

            extra_body={
                "agent_reference": {
                    "name": agent.name,
                    "type": "agent_reference",
                }
            },
        )

        print("\n助手：", end="", flush=True)

        for event in stream_response:

            # 输出模型生成的文本
            if event.type == "response.output_text.delta":
                print(event.delta, end="", flush=True)

            elif event.type == "response.output_text.done":
                print()

            # 提取搜索结果引用
            elif event.type == "response.output_item.done":
                if event.item.type != "message":
                    continue

                item = event.item

                if not item.content:
                    continue

                for content in item.content:
                    if content.type != "output_text":
                        continue

                    annotations = getattr(content, "annotations", None)

                    if not annotations:
                        continue

                    for annotation in annotations:
                        if annotation.type == "url_citation":
                            url = getattr(annotation, "url", None)

                            if url and url not in citations:
                                citations.append(url)

            elif event.type == "response.completed":
                print("\n搜索完成。")

        if citations:
            print("\n来源：")

            for index, url in enumerate(citations, start=1):
                print(f"{index}. {url}")

        print("-" * 60)

    except Exception as error:
        print(f"\n搜索失败：{error}")
        print("-" * 60)


def interactive_loop(openai_client, agent):
    """
    进入交互式输入循环。
    """

    print("\n中文 Bing 搜索助手已启动。")
    print("请输入搜索内容。")
    print("输入 quit、exit、q 或 退出，可以结束程序。")

    while True:
        try:
            user_question = input("\n请输入问题：").strip()

        except KeyboardInterrupt:
            print("\n\n程序已退出。")
            break

        except EOFError:
            print("\n\n程序已退出。")
            break

        if not user_question:
            print("请输入有效的问题。")
            continue

        if user_question.lower() in {
            "quit",
            "exit",
            "q",
            "退出",
            "结束",
        }:
            print("程序已退出。")
            break

        search_with_agent(
            openai_client=openai_client,
            agent=agent,
            user_question=user_question,
        )


def main():
    """
    程序主入口。
    """

    # 加载环境变量
    load_dotenv("config.env")

    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")

    if not project_endpoint:
        raise ValueError(
            "未找到 AZURE_AI_PROJECT_ENDPOINT，"
            "请检查 config.env 文件。"
        )

    # 创建 Azure AI Project 客户端
    project = AIProjectClient(
        endpoint=project_endpoint,
        credential=DefaultAzureCredential(),
    )

    # 获取 OpenAI 客户端
    openai_client = project.get_openai_client()

    # 创建 Agent
    agent = create_agent(project)

    # 启动交互式搜索
    interactive_loop(
        openai_client=openai_client,
        agent=agent,
    )


if __name__ == "__main__":
    main()
