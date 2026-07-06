# MCP 模型上下文协议介绍

## 什么是 MCP

MCP（Model Context Protocol，模型上下文协议）是 Anthropic 提出的开放协议，旨在标准化大模型应用与外部数据源、工具之间的连接方式。它定义了统一的通信协议，使任意 MCP 客户端（如 Claude Desktop）能够与任意 MCP Server 交互，获取上下文信息或调用工具。

## MCP 核心概念

- MCP Server：暴露资源（Resources）、提示（Prompts）、工具（Tools）的服务端。
- MCP Client：连接 Server 并消费其能力的客户端，如 Claude Desktop、IDE 插件。
- Transport：通信传输层，支持 stdio（标准输入输出）与 SSE（Server-Sent Events）两种模式。

## MCP 三大能力

1. Resources（资源）：暴露可读取的数据，如文件内容、数据库记录。
2. Prompts（提示）：预定义的提示模板，供用户快速调用。
3. Tools（工具）：可被模型调用的函数，如检索、查询、计算。

## MCP vs 传统 Function Calling

传统 Function Calling 由应用层定义工具，工具与具体应用强耦合。MCP 将工具能力下沉到独立 Server，实现工具的复用与解耦：一个 MCP Server 可同时服务多个客户端，一个客户端也可连接多个 Server，形成工具生态。

## 典型应用场景

- 知识库检索：MCP Server 封装 RAG 检索能力，LLM 客户端按需调用。
- 数据库查询：MCP Server 暴露 SQL 查询工具。
- 文件系统操作：MCP Server 提供文件读写能力。
- API 集成：MCP Server 封装第三方 API，统一调用方式。
