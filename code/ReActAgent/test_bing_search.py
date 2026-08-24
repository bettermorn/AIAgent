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

# Format: "https://resource_name.ai.azure.com/api/projects/project_name"

load_dotenv("config.env")

PROJECT_ENDPOINT = os.getenv("AZURE_AI_PROJECT_ENDPOINT")


BING_CONNECTION_NAME = "Search"

# Create clients to call Foundry API
project = AIProjectClient(
    endpoint=PROJECT_ENDPOINT,
    credential=DefaultAzureCredential(),
)
openai = project.get_openai_client()

# Get connection ID from connection name
bing_connection = project.connections.get(BING_CONNECTION_NAME)


agent = project.agents.create_version(
    agent_name="MyAgent",
    definition=PromptAgentDefinition(
        model="qwen--qwen36-27b",
        instructions="You are a helpful assistant.",
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
    description="You are a helpful agent.",
)
print(f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})")

stream_response = openai.responses.create(
    stream=True,
    tool_choice="required",
    input="What is today's date and weather in Seattle?",
    extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
)

for event in stream_response:
    if event.type == "response.created":
        print(f"Follow-up response created with ID: {event.response.id}")
    elif event.type == "response.output_text.delta":
        print(f"Delta: {event.delta}")
    elif event.type == "response.output_text.done":
        print(f"\nFollow-up response done!")
    elif event.type == "response.output_item.done":
        if event.item.type == "message":
            item = event.item
            if item.content[-1].type == "output_text":
                text_content = item.content[-1]
                for annotation in text_content.annotations:
                    if annotation.type == "url_citation":
                        print(f"URL Citation: {annotation.url}")
    elif event.type == "response.completed":
        print(f"\nFollow-up completed!")
        print(f"Full response: {event.response.output_text}")
