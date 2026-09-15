# 本科软件工程课程关系图

涵盖主要课程模块及其先修/支撑关系


```mermaid
graph TD
    %% ===== 数学与基础 =====
    A1[高等数学\nCalculus]
    A2[线性代数\nLinear Algebra]
    A3[概率论与数理统计\nProbability & Statistics]
    A4[离散数学\nDiscrete Mathematics]

    %% ===== 计算机基础 =====
    B1[计算机导论\nIntro to CS]
    B2[C/C++ 程序设计\nC/C++ Programming]
    B3[数字逻辑\nDigital Logic]
    B4[计算机组成原理\nComputer Organization]
    B5[汇编语言\nAssembly Language]

    %% ===== 核心专业课 =====
    C1[数据结构\nData Structures]
    C2[算法设计与分析\nAlgorithms]
    C3[操作系统\nOperating Systems]
    C4[计算机网络\nComputer Networks]
    C5[数据库系统\nDatabase Systems]
    C6[编译原理\nCompiler Principles]

    %% ===== 软件工程核心 =====
    D1[面向对象程序设计\nOOP / Java]
    D2[软件工程导论\nSoftware Engineering]
    D3[需求工程\nRequirements Engineering]
    D4[软件体系结构\nSoftware Architecture]
    D5[设计模式\nDesign Patterns]
    D6[软件测试\nSoftware Testing]
    D7[软件项目管理\nProject Management]
    D8[软件质量保证\nSoftware Quality Assurance]

    %% ===== 应用与进阶 =====
    E1[Web 应用开发\nWeb Development]
    E2[移动应用开发\nMobile Development]
    E3[人机交互\nHuman-Computer Interaction]
    E4[云计算与分布式系统\nCloud & Distributed Systems]
    E5[信息安全\nInformation Security]
    E6[机器学习基础\nMachine Learning Basics]

    %% ===== 综合实践 =====
    F1[软件工程实训\nSE Practicum]
    F2[毕业设计 / 课程设计\nCapstone Project]

    %% ===== 关系连线 =====

    %% 数学基础支撑
    A1 --> A3
    A1 --> A2
    A2 --> C2
    A3 --> C2
    A3 --> E6
    A4 --> C1
    A4 --> C2
    A4 --> C6

    %% 计算机基础链
    B1 --> B2
    B2 --> C1
    B2 --> D1
    B3 --> B4
    B4 --> B5
    B4 --> C3
    B5 --> C3

    %% 核心专业课依赖
    C1 --> C2
    C1 --> C3
    C1 --> C5
    C1 --> C6
    C2 --> C6
    C3 --> C4
    C3 --> C5
    C3 --> E4
    C4 --> C5
    C4 --> E1
    C4 --> E4
    C4 --> E5

    %% 面向对象 → 软件工程主线
    D1 --> D2
    D1 --> D5
    D1 --> E1
    D1 --> E2
    C1 --> D1
    C5 --> D2
    D2 --> D3
    D2 --> D4
    D2 --> D6
    D2 --> D7
    D3 --> D4
    D4 --> D5
    D5 --> D6
    D6 --> D8
    D7 --> D8

    %% 应用层依赖
    D4 --> E4
    D5 --> E1
    D5 --> E2
    C4 --> E5
    C5 --> E1
    A2 --> E6
    A3 --> E6
    C2 --> E6
    D2 --> E3

    %% 综合实践汇聚
    D2 --> F1
    D3 --> F1
    D4 --> F1
    D6 --> F1
    D7 --> F1
    E1 --> F1
    F1 --> F2
    D8 --> F2
    E3 --> F2
    E4 --> F2
    E5 --> F2
    E6 --> F2
```



**图的结构说明：**

| 层次 | 内容 |
|------|------|
| 数学与基础（A） | 支撑算法、概率、离散推理等所有后续课程的底座 |
| 计算机基础（B） | 从编程入门到硬件原理，建立机器层面认知 |
| 核心专业课（C） | 数据结构、算法、OS、网络、数据库、编译，构成专业骨架 |
| 软件工程核心（D） | OOP → 软件工程方法论 → 架构/模式/测试/质量/管理的完整链条 |
| 应用与进阶（E） | Web、移动、HCI、云、安全、ML，各有独立技术栈但依赖核心课 |
| 综合实践（F） | 实训和毕设汇聚上层所有课程，是输出验证节点 |

几条关键先修链值得注意：
- **离散数学 → 数据结构 → 算法** 是理论主干
- **C/C++ → OOP → 软件工程导论 → 架构/模式/测试** 是工程主干
- **计算机网络 → Web开发 / 云计算 / 信息安全** 是应用主干
