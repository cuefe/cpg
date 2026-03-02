# Code Property Graph（代码属性图）
[![Actions Status](https://github.com/Fraunhofer-AISEC/cpg/actions/workflows/build.yml/badge.svg?branch=main)](https://github.com/Fraunhofer-AISEC/cpg/actions)
 [![codecov](https://codecov.io/gh/Fraunhofer-AISEC/cpg/graph/badge.svg?token=XBXZZOQIID)](https://codecov.io/gh/Fraunhofer-AISEC/cpg)

> 本文档是 `README.md` 的简体中文翻译；如有差异，以英文原文为准。

一个用于从源代码中提取 *代码属性图*（Code Property Graph, CPG）的简单库。它支持在图构建完成后进行多轮（pass）处理，以在构建完成后继续扩展分析能力。目前支持 C/C++（C17）、Java（Java 13），并对 Golang、Python 与 TypeScript 提供实验性支持。此外，它支持 [LLVM IR](http://llvm.org/docs/LangRef.html)，因此理论上也支持所有通过 LLVM 编译的语言。

## 这是什么？

代码属性图（CPG）是一种用于表示源代码的结构：它以“带标签的有向多重图”的形式组织代码信息。你可以把它理解为一个有向图，其中每个节点与每条边都带有一组（可能为空的）键值对（_properties_）。这种表示方式可以被多种图数据库支持，例如 Neptune、Cosmos、Neo4j、Titan 和 Apache Tinkergraph，并可用于将程序的源代码以可搜索的数据结构形式存储起来。因此，代码属性图允许你使用已有的图查询语言（例如 Cypher、NQL、SQL 或 Gremlin）来手动浏览源代码中的关键部分，或自动发现“有趣”的模式。

本库使用 [Eclipse CDT](https://www.eclipse.org/cdt/) 来解析 C/C++ 源代码，并使用 [JavaParser](https://javaparser.org/) 来解析 Java。与编译器 AST 生成器不同，这两者都是“宽容（forgiving）”的解析器，能够处理不完整甚至在语义上不正确的源代码。这使得即使无法编译（例如缺少依赖或存在轻微语法错误）也能对源代码进行分析。此外，本库通过 [javacpp](https://github.com/bytedeco/javacpp) 项目调用 [LLVM](https://llvm.org) 来解析 LLVM IR。请注意，LLVM IR 解析器并不“宽容”，也就是说 LLVM IR 代码至少需要被 LLVM 认为是有效的。所需的本地（native）库由 javacpp 项目为大多数平台提供。

## 规范（Specifications）

为了在形式化方面改进本库，我们为核心概念编写了若干规范。目前包括：
* [Dataflow Graph](https://fraunhofer-aisec.github.io/cpg/CPG/specs/dfg/)
* [Evaluation Order Graph](https://fraunhofer-aisec.github.io/cpg/CPG/specs/eog/)
* [Graph Model in neo4j](https://fraunhofer-aisec.github.io/cpg/CPG/specs/graph/)
* [Language and Language Frontend](https://fraunhofer-aisec.github.io/cpg/CPG/impl/language/)

我们会在未来逐步补充更多规范。

## 使用（Usage）

要从源码构建项目，你需要在本地生成一个 `gradle.properties` 文件。
该文件也用于启用/禁用受支持的编程语言。
我们在 [这里](./gradle.properties.example) 提供了一个示例文件——只需把它复制到 cpg 项目目录下并命名为 `gradle.properties`。
除了手动生成或编辑 `gradle.properties` 文件外，你也可以使用 `configure_frontends.sh` 脚本，它会为你修改 properties 并设置要支持的编程语言。

### 用于可视化

为了更直观地熟悉图结构本身，你可以使用子项目 [cpg-neo4j](./cpg-neo4j)。它使用本库为一组用户提供的代码文件生成 CPG，并将图持久化到 [Neo4j](https://neo4j.com/) 图数据库中。这样做的好处是，你可以借助 Neo4j 的可视化工具 [Neo4j Browser](https://neo4j.com/developer/neo4j-browser/) 以图形化方式查看 CPG 的节点与边，而不是查看它们在 Java 中的对象表示。

请确保你的 Neo4j 服务器启用了 [APOC](https://neo4j.com/labs/apoc/) 插件。它在批量创建节点与关系时会被用到。

例如使用 docker：
```
docker run -p 7474:7474 -p 7687:7687 -d -e NEO4J_AUTH=neo4j/password -e NEO4JLABS_PLUGINS='["apoc"]' neo4j:5
```

### 作为库使用

最新版本会发布到 Maven Central，可以作为普通依赖使用（Maven 或 Gradle 均可）。

```kotlin
dependencies {
    val cpgVersion = "9.0.2"

    // use the 'cpg-core' module
    implementation("de.fraunhofer.aisec", "cpg-core", cpgVersion)

    // and then add the needed extra modules, such as Go and Python
    implementation("de.fraunhofer.aisec", "cpg-language-go", cpgVersion)
    implementation("de.fraunhofer.aisec", "cpg-language-python", cpgVersion)
}
```

对于 `cpg-language-cxx` 模块，还需要一些额外步骤。由于 Eclipse CDT 并未发布到 Maven Central，需要添加一个采用自定义布局的仓库来找到已发布的 CDT 文件。例如使用 Gradle 的 Kotlin 语法：
```kotlin
repositories {
    // This is only needed for the C++ language frontend
    ivy {
        setUrl("https://download.eclipse.org/tools/cdt/releases/")
        metadataSources {
            artifact()
        }

        patternLayout {
            artifact("[organisation].[module]_[revision].[ext]")
        }
    }
}
```

请注意：`cpg` 模块包含所有可选特性，体积可能非常大（尤其包含 LLVM 支持时）。如果你不需要 LLVM，建议只使用 `cpg-core` 再加上需要的扩展模块（例如 `cpg-language-go`）。未来我们也会把更多可选功能拆分到独立模块中。

#### 开发版本构建

对于 `main` 分支上的每次构建，都会在 [GitHub Packages](https://github.com/orgs/Fraunhofer-AISEC/packages?repo_name=cpg) 中发布一个版本号为 `main-SNAPSHOT` 的制品（artifact）。此外，带有 `publish-to-github-packages` 标签的特定 PR 也会发布到那里。这在你想测试尚未进入 main 的重要特性时很有用。版本号会对应 PR 编号，例如 `1954-SNAPSHOT`。  

如需使用 GitHub Gradle Registry，请参考：https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-gradle-registry#using-a-published-package

### 配置（Configuration）

本库的行为可以通过多种方式配置。其中大部分配置由 `TranslationConfiguration` 与 `InferenceConfiguration` 完成。

#### TranslationConfiguration

`TranslationConfiguration` 用于配置翻译（translation）的各项行为。例如：选择要使用的语言/语言前端与 passes、决定哪些信息需要推断（infer）、包含哪些文件等。该配置通过 builder 模式进行设置。

#### InferenceConfiguration

类 `InferenceConfiguration` 可用于在 passes 识别到缺失节点时影响其行为。当前可以启用的标志（flags）有多项，其中最重要的是：

* `inferRecords`：启用对缺失的 record 声明（即 class 与 struct）的推断
* `inferDfgForUnresolvedCalls`：当被调用函数不在分析的源代码中时，为方法调用添加 DFG 边以表示所有潜在的数据流

默认仅开启 `inferDfgForUnresolvedCalls`。

可通过 builder 模式完成配置，并在 `TranslationConfiguration` 中使用，如下所示：
```kt
val inferenceConfig = InferenceConfiguration
    .builder()
    .inferRecords(true)
    .inferDfgForUnresolvedCalls(true)
    .build()

val translationConfig = TranslationConfiguration
    .builder()
    .inferenceConfiguration(inferenceConfig)
    .build()
```

## 开发（Development）
本节介绍各语言的支持情况、当前成熟度，以及如何使用和开发它们。

### 语言支持（Language Support）
不同语言的维护程度不同，表格中将使用以下状态标记：
- `maintained`：基本功能完备，且 bug 会被优先修复
- `incubating`：正在积极开发中，以达到功能完备为目标
- `experimental`：已有可工作的原型，例如为研究课题提供支持，但未来发展不确定
- `discontinued`：不再积极开发或维护，但仍保留以便社区 fork 并自行适配
  
当前各语言状态如下：

| 语言                      | 模块                                  | 分支                                                                    | 状态           |
|--------------------------|---------------------------------------|-------------------------------------------------------------------------|----------------|
| Java（源码）              | cpg-language-java                     | [main](https://github.com/Fraunhofer-AISEC/cpg)                         | `maintained`   |
| C++                      | cpg-language-cxx                      | [main](https://github.com/Fraunhofer-AISEC/cpg)                         | `maintained`   |
| Python                   | cpg-language-python                   | [main](https://github.com/Fraunhofer-AISEC/cpg)                         | `maintained`   |
| Go                       | cpg-language-go                       | [main](https://github.com/Fraunhofer-AISEC/cpg)                         | `maintained`   |
| INI                      | cpg-language-ini                      | [main](https://github.com/Fraunhofer-AISEC/cpg)                         | `maintained`   |
| JVM（字节码）             | cpg-language-jvm                      | [main](https://github.com/Fraunhofer-AISEC/cpg)                         | `incubating`   |
| LLVM                     | cpg-language-llvm                     | [main](https://github.com/Fraunhofer-AISEC/cpg)                         | `incubating`   |
| TypeScript/JavaScript    | cpg-language-typescript               | [main](https://github.com/Fraunhofer-AISEC/cpg)                         | `experimental` |
| Ruby                     | cpg-language-ruby                     | [main](https://github.com/Fraunhofer-AISEC/cpg)                         | `experimental` |
| {OpenQASM,Python-Qiskit} | cpg-language-{openqasm,python-qiskit} | [quantum-cpg](https://github.com/Fraunhofer-AISEC/cpg/tree/quantum-cpg) | `experimental` |

需要注意的是，多种语言都可以编译为 LLVM IR，因此可以通过 `cpg-language-llvm` 模块进行分析（见 [7]）。这包括但不限于 Rust、Swift、Objective-C 和 Haskell（更多信息请参考 https://llvm.org/）。

### 语言与配置（Languages and Configuration）
`cpg-core` 包含图节点（graph nodes）以及与语言无关的 passes，用于为 cpg-AST 添加语义信息。各语言在独立的 Gradle 子模块中开发。
要包含所需的语言子模块，只需在本地 `gradle.properties` 文件中将对应属性设置为 `true`，例如 `enableGoFrontend=true`。
我们在 [这里](./gradle.properties.example) 提供了一个示例文件，其中所有语言都已开启。
除了手动编辑 `gradle.properties` 文件外，你也可以使用 `configure_frontends.sh` 脚本，它会为你修改 properties 并完成设置。有些语言需要额外安装软件才能运行，下面会分别说明。

#### Golang

对于 Golang，会使用额外的本地代码 [libgoast](https://github.com/Fraunhofer-AISEC/libgoast) 来访问 Go 的 `ast` 包。Gradle 在构建期间会自动下载该库的最新版本。目前仅支持 Linux 和 macOS。

#### Python

你需要安装 [jep](https://github.com/ninia/jep/)。它可以安装为系统级依赖，或安装在虚拟环境中。你的 jep 版本必须与 CPG 使用的版本匹配（参见 [version catalog](./gradle/libs.versions.toml)）。
目前仅支持 Python 3.{10,11,12,13,14,15}。

##### 系统级安装

请按照以下说明操作：https://github.com/ninia/jep/wiki/Getting-Started#installing-jep

##### 虚拟环境安装

- `python3 -m venv ~/.virtualenvs/cpg`
- `source ~/.virtualenvs/cpg/bin/activate`
- `pip3 install jep`

通过 `JepSingleton`，CPG 库会在 Linux 和 OS X 上查找一些常见路径。`JepSingleton` 会优先使用名为 `cpg` 的 virtualenv；你可以通过环境变量 `CPG_PYTHON_VIRTUALENV` 调整这一行为。

#### TypeScript

TypeScript 解析所需的 TypeScript 代码位于 `cpg-language-typescript` 子模块的 `src/main/nodejs` 目录中。Gradle 会自动构建该脚本。打包后的脚本会被放入 jar 的 resources 中，开箱即用。

#### MCP

[Model Context Protocol](https://modelcontextprotocol.io/docs/getting-started/intro) 功能通过可选模块 `cpg-mcp` 提供。可通过 `gradle.properties` 中的 `enableMCPModule` 进行启用/禁用。

### 代码风格（Code Style）

我们使用 [Google Java Style](https://github.com/google/google-java-format) 作为代码格式化规范。请为你的 IDE 安装合适的插件，例如 [google-java-format IntelliJ 插件](https://plugins.jetbrains.com/plugin/8527-google-java-format) 或 [google-java-format Eclipse 插件](https://github.com/google/google-java-format/releases/download/google-java-format-1.6/google-java-format-eclipse-plugin_1.6.0.jar)。

### 在 IntelliJ 中集成（Integration into IntelliJ）

整体上比较直接，但建议进行以下三项设置：

* 启用 Gradle “auto-import”
* 启用 google-java-format
* 将 Gradle 的 spotlessApply 挂到 “before build”（在 IDEA 2019.1 之后可能已不再需要）

### Git Hooks

你可以使用 `style/pre-commit` 中的 hook 来检查格式化错误：
```
cp style/pre-commit .git/hooks
```

## 贡献者（Contributors）

以下作者为本项目做出了贡献：

<a href="https://github.com/Fraunhofer-AISEC/cpg/graphs/contributors"><img src="https://contrib.rocks/image?repo=Fraunhofer-AISEC/cpg" /></a>

## 贡献指南（Contributing）

在接受外部贡献之前，你需要签署我们的 [CLA](https://cla-assistant.io/Fraunhofer-AISEC/cpg)。当你开启第一个 Pull Request 时，我们的 CLA 助手会检查你是否已经签署。

## 延伸阅读（Further reading）

完整论文列表见 [这里](https://fraunhofer-aisec.github.io/cpg/#publications)

我们在 arXiv 上发布了一篇关于 CPG 的简要介绍：

[1] Konrad Weiss, Christian Banse. A Language-Independent Analysis Platform for Source Code. https://arxiv.org/abs/2203.08424

该 CPG 的早期版本曾被用于分析 iOS 应用的 ARM 二进制文件：

[2] Julian Schütte, Dennis Titze. _liOS: Lifting iOS Apps for Fun and Profit._ Proceedings of the ESORICS International Workshop on Secure Internet of Things (SIoT), Luxembourg, 2019. https://arxiv.org/abs/2003.12901

关于将代码属性图用于静态分析的早期论文：

[3] Yamaguchi et al. - Modeling and Discovering Vulnerabilities with Code Property Graphs. https://www.sec.cs.tu-bs.de/pubs/2014-ieeesp.pdf

[4] 是由上述论文作者开发的另一个不相关但类似的项目，开源软件 Joern [5] 使用它来分析 C/C++ 代码。虽然 [4] 给出了数据结构的规范与实现，但本项目包含多种 _语言前端_（目前包含 C/C++ 与 Java，Python 等仍在完善中），并且支持通过配置 _Passes_ 来构建满足特定分析需求的自定义图：

[4] https://github.com/ShiftLeftSecurity/codepropertygraph

[5] https://github.com/ShiftLeftSecurity/joern/

为支持更多使用场景而对 CPG 做的扩展：

[6] Christian Banse, Immanuel Kunz, Angelika Schneider and Konrad Weiss. Cloud Property Graph: Connecting Cloud Security Assessments with Static Code Analysis.  IEEE CLOUD 2021. https://doi.org/10.1109/CLOUD53861.2021.00014

[7] Alexander Küchler, Christian Banse. Representing LLVM-IR in a Code Property Graph. 25th Information Security Conference (ISC). Bali, Indonesia. 2022

[8] Maximilian Kaul, Alexander Küchler, Christian Banse. A Uniform Representation of Classical and Quantum Source Code for Static Code Analysis. IEEE International Conference on Quantum Computing and Engineering (QCE). Bellevue, WA, USA. 2023

