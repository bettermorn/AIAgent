# PE、CE、HE和LE

## 演进顺序

```mermaid
timeline
    title AI 应用工程范式的演进
    单轮调用 : Prompt Engineering
             : 设计更好的任务指令
    知识增强 : Context Engineering
             : 引入检索、记忆、状态和工具结果
    系统化运行 : Harness Engineering
              : 增加权限、验证、监控和安全护栏
    自主执行 : Loop Engineering
             : 让模型计划、行动、观察、修正并完成任务
    生产级智能系统 : 四者结合
                  : 稳定、可控、可评估、可持续运行
```

## 四者的总体关系

```mermaid
flowchart TB
    U["用户目标 / 业务目标"]

    PE["Prompt Engineering
提示词工程
如何向模型表达任务"]
    CE["Context Engineering
上下文工程
为模型准备什么信息"]
    HE["Harness Engineering
运行支架工程
如何约束、调度和保护模型"]
    LE["Loop Engineering
循环工程
如何执行、检查、修正和迭代"]

    M["基础模型 / Agent Model"]
    O["输出结果"]
    E["外部环境
工具、数据库、API、文件、用户"]

    U --> PE
    U --> CE
    U --> HE
    U --> LE

    PE --> M
    CE --> M
    HE --> M
    M --> O

    HE --> E
    E --> CE
    O --> LE
    LE --> M
    LE --> E

    O --> V["评估与验证"]
    V -->|"不合格：修正任务、上下文或策略"| LE
    V -->|"合格"| F["最终结果 / 业务动作"]
```







## 核心区别

```mermaid
mindmap
  root((AI 工程))
    Prompt Engineering
      指令
      角色
      示例
      输出格式
      行为约束
    Context Engineering
      检索
      记忆
      对话历史
      工具结果
      状态
      权限过滤
    Harness Engineering
      工具
      权限
      安全
      验证
      监控
      持久化
      人工审批
    Loop Engineering
      计划
      执行
      观察
      评估
      重试
      修正
      停止条件
```

**Prompt Engineering 解决“怎么告诉模型”，Context Engineering 解决“给模型看什么”，Harness Engineering 解决“如何让模型安全可靠地工作”，Loop Engineering 解决“如何让模型通过多轮反馈把复杂任务真正做完”。**


## 四者在一个完整 AI Agent 中如何协同
```mermaid
flowchart TB
    U["用户目标"]

    subgraph L1["Prompt Engineering"]
        P1["任务指令"]
        P2["角色设定"]
        P3["输出格式"]
        P4["行为约束"]
        P1 --> P["Prompt 模板"]
        P2 --> P
        P3 --> P
        P4 --> P
    end

    subgraph L2["Context Engineering"]
        C1["用户问题"]
        C2["历史对话"]
        C3["检索信息"]
        C4["工具结果"]
        C5["任务状态"]
        C6["权限与规则"]
        C1 --> C["Context 构建"]
        C2 --> C
        C3 --> C
        C4 --> C
        C5 --> C
        C6 --> C
    end

    subgraph L3["Harness Engineering"]
        H1["工具注册"]
        H2["权限控制"]
        H3["状态管理"]
        H4["输出验证"]
        H5["安全防护"]
        H6["日志与监控"]
        H["Agent Harness"]
        H1 --> H
        H2 --> H
        H3 --> H
        H4 --> H
        H5 --> H
        H6 --> H
    end

    subgraph L4["Loop Engineering"]
        L["计划"]
        A["行动"]
        O["观察"]
        E["评估"]
        D["决定继续、重试或结束"]
        L --> A --> O --> E --> D
        D -->|"继续/修正"| L
    end

    U --> P
    U --> C
    U --> L

    P --> M["大模型"]
    C --> M
    H <--> M
    M --> L
    L --> H
    H --> C

    D -->|"成功"| R["最终答案或业务动作"]
```



# PE Prompt Engineering

## 完整的Prompt

```mermaid
flowchart LR
    R["角色
你是谁"]
    T["任务
要做什么"]
    C["约束
不能做什么"]
    I["输入
处理什么内容"]
    E["示例
希望怎样做"]
    F["格式
应该怎样输出"]

    R --> P["Prompt"]
    T --> P
    C --> P
    I --> P
    E --> P
    F --> P

    P --> M["大模型"]
    M --> O["输出"]
```

## 2. Prompt Engineering 的作用边界

Prompt 可以改善：

- 任务理解
- 输出格式
- 语气和风格
- 角色定位
- 推理步骤的组织方式
- 对异常情况的处理说明
- 工具调用规则

但 Prompt 不能彻底解决：

- 缺少事实资料
- 模型没有访问数据库的能力
- 工具权限不合理
- 上下文过长或污染
- 任务本身缺少验证机制
- 模型输出无法被系统检查

因此，复杂 AI 系统不能只依赖 Prompt。



# CE Context Engineering

```mermaid
flowchart TB
    Q["当前用户问题"]

    SYS["系统规则"]
    HIST["对话历史"]
    MEM["长期记忆"]
    RET["检索结果"]
    TOOL["工具返回结果"]
    STATE["任务状态"]
    PROFILE["用户与权限信息"]
    EXAMPLE["示例与规范"]

    SYS --> C["上下文构建器"]
    HIST --> C
    MEM --> C
    RET --> C
    TOOL --> C
    STATE --> C
    PROFILE --> C
    EXAMPLE --> C
    Q --> C

    C --> CTX["经过筛选、排序、压缩后的 Context"]
    CTX --> M["大模型"]
    M --> A["模型输出"]
```
典型流程

```mermaid
flowchart LR
    A["原始信息源
文档、数据库、对话、工具"]
    B["检索与过滤"]
    C["权限检查"]
    D["排序与去重"]
    E["摘要与压缩"]
    F["上下文组装"]
    G["模型调用"]

    A --> B --> C --> D --> E --> F --> G
```

Context Engineering 负责：

- 从知识库中检索哪些文档
- 是否过滤掉过期文档
- 是否只保留用户有权限访问的资料
- 如何把长文档切片
- 如何给检索结果排序
- 是否压缩历史对话
- 是否保留上一步工具调用结果
- 如何避免把无关资料塞给模型



# HE Harness Engineering

```mermaid
flowchart TB
    M["大模型"]

    H["AI Harness
Agent 运行支架"]

    T["工具系统
搜索、代码执行、数据库、API"]
    P["权限系统
用户权限、工具权限、数据权限"]
    S["状态与记忆
任务状态、会话状态、检查点"]
    G["安全护栏
内容安全、提示注入防护、数据脱敏"]
    V["输出验证
Schema、规则、事实校验"]
    R["路由与调度
模型选择、任务分解、重试"]
    O["观测系统
日志、Tracing、指标、成本"]

    H --> T
    H --> P
    H --> S
    H --> G
    H --> V
    H --> R
    H --> O

    H <--> M
    T <--> M
```

案例：一个自动执行数据库查询的 AI 系统

```mermaid
flowchart LR
    Q["用户请求"]
    M["模型生成 SQL"]
    P["SQL 解析与权限检查"]
    S["安全策略检查"]
    H["人工审批
高风险操作时触发"]
    E["执行数据库查询"]
    V["结果验证与脱敏"]
    O["返回结果"]

    Q --> M --> P --> S
    S -->|"低风险"| E
    S -->|"高风险"| H -->|"批准"| E
    E --> V --> O
```

负责：

- 给模型提供工具
- 约束模型能做什么
- 控制模型如何调用工具
- 管理权限
- 保存状态
- 验证输出
- 处理异常
- 限制成本和执行时间
- 监控运行过程
- 必要时请求人工确认


# LE Loop Engineering
如何设计模型与环境之间的反复交互，使模型能够逐步完成复杂任务，而不是只生成一次答案。

```mermaid
flowchart LR
    G["目标 Goal"]
    P["计划 Plan"]
    A["行动 Act
调用工具或执行步骤"]
    O["观察 Observe
读取工具和环境结果"]
    R["反思/判断 Reflect"]
    V["验证 Verify"]
    F["完成 Finish"]

    G --> P --> A --> O --> R
    R -->|"继续执行"| P
    R --> V
    V -->|"不合格"| P
    V -->|"合格"| F
```

案例：生成一份市场研究报告

```mermaid
flowchart TB
    A["确定研究问题"]
    B["制定研究计划"]
    C["搜索资料"]
    D["提取数据"]
    E["交叉验证"]
    F["发现缺口"]
    G["补充搜索"]
    H["撰写报告"]
    I["事实检查"]
    J["交付报告"]

    A --> B --> C --> D --> E
    E -->|"资料不足或冲突"| F --> G --> D
    E -->|"资料充分"| H --> I
    I -->|"发现错误"| C
    I -->|"检查通过"| J
```

# 四者的质量评价指标

## Prompt Engineering 指标

- 指令遵循率
- 输出格式正确率
- 任务完成率
- 风格一致性
- 幻觉率
- 对异常输入的鲁棒性

## Context Engineering 指标

- 检索召回率
- 上下文相关性
- 上下文压缩率
- 上下文污染率
- 长上下文利用效率
- 权限过滤准确率
- 信息时效性

## Harness Engineering 指标

- 工具调用成功率
- 权限违规率
- 输出验证通过率
- 任务可恢复性
- 平均延迟
- Token 成本
- 安全事件数量
- 日志和追踪完整度

## Loop Engineering 指标

- 任务最终成功率
- 平均循环次数
- 重试率
- 无效循环率
- 单次任务成本
- 任务完成时间
- 失败后恢复成功率
- 人工介入比例
- 自动停止准确率

# 一个具体例子：AI 编程助手
## Prompt Engineering

告诉模型：

```text
你是一名资深 Python 工程师。
请修改代码，并说明修改原因。
输出必须包含：
1. 修改后的代码
2. 测试方法
3. 可能的风险
```

## Context Engineering

为模型提供：

- 当前项目目录结构
- 相关源代码
- 测试代码
- 依赖文件
- Git 历史
- 编码规范
- 当前报错日志
- 用户拥有的文件权限

## Harness Engineering

为模型提供：

- 文件读取工具
- 代码编辑工具
- 测试执行工具
- Git 工具
- 沙箱环境
- 文件修改权限
- 命令执行白名单
- 修改前后的 Diff
- 代码安全检查

## Loop Engineering

执行流程：

```mermaid
flowchart LR
    A["理解需求"]
    B["检查代码"]
    C["制定修改计划"]
    D["修改代码"]
    E["运行测试"]
    F["分析失败原因"]
    G["提交 Diff"]
    H["请求用户确认"]

    A --> B --> C --> D --> E
    E -->|"测试失败"| F --> C
    E -->|"测试通过"| G --> H
```

这个系统的能力并不是由某一个 Prompt 单独产生的，而是四类工程共同作用的结果。

