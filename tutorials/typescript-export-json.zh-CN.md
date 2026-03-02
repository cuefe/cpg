# 教程：分析 TypeScript 项目并导出 CPG（JSON）

本教程介绍如何使用本仓库提供的 `cpg-neo4j` 命令行工具（CLI），对一个 **TypeScript/TSX** 项目进行解析，并将生成的 **Code Property Graph (CPG)** 导出为 **JSON 文件**（不需要 Neo4j）。

适用场景：
- 你希望把源码转换成 CPG，方便后续做离线处理/二次分析/导入其他系统。
- 你不想先搭 Neo4j，只想先拿到结构化的图数据（`nodes`/`edges`）。

> 说明：TypeScript/JavaScript 前端目前属于实验性支持，适合用于代码理解、研究与原型验证；对大型项目建议先小范围试跑并逐步扩大。

---

## 0. 前置条件

1) **JDK 21**

`cpg-neo4j` 运行与构建都需要 Java 21（本仓库 Gradle Toolchain 也使用 21）。

2) **网络访问（用于构建时下载依赖）**

首次构建时 Gradle 会下载依赖；TypeScript 前端会在构建过程中下载 Deno 并编译一个 parser 可执行文件。

3) （推荐）你有一个明确的项目根目录

例如：`/path/to/your-ts-project`，通常包含 `package.json`、`tsconfig.json` 等。

---

## 1. 在 CPG 仓库里启用 TypeScript 前端

在仓库根目录下，准备 `gradle.properties`（它控制哪些语言前端会参与构建）：

```bash
cp gradle.properties.example gradle.properties
```

然后编辑 `gradle.properties`，确保至少包含：

```properties
enableTypeScriptFrontend=true
```

为了减少构建时间，你可以把不需要的前端关掉，例如：

```properties
enableJavaFrontend=false
enableCXXFrontend=false
enableGoFrontend=false
enablePythonFrontend=false
enableLLVMFrontend=false
enableRubyFrontend=false
enableJVMFrontend=false
enableINIFrontend=false
enableMCPModule=false
```

也可以运行交互式脚本来生成/修改 `gradle.properties`：

```bash
./configure_frontends.sh
```

---

## 2. 构建 `cpg-neo4j` CLI

在仓库根目录执行：

```bash
./gradlew :cpg-neo4j:installDist
```

成功后，会生成可执行脚本：

- `cpg-neo4j/build/install/cpg-neo4j/bin/cpg-neo4j`

---

## 3. 分析 TypeScript 项目并导出 JSON

### 3.1 推荐的最小命令（导出 JSON，不连接 Neo4j）

将 `/path/to/your-ts-project` 替换为你的项目路径：

```bash
cpg-neo4j/build/install/cpg-neo4j/bin/cpg-neo4j \
  --no-neo4j \
  --export-json /tmp/cpg.json \
  --top-level /path/to/your-ts-project \
  --exclusion-patterns node_modules \
  --exclusion-patterns dist \
  --exclusion-patterns build \
  --exclusion-patterns .git \
  /path/to/your-ts-project
```

说明：
- `--no-neo4j`：不推送到 Neo4j（方案 A 的关键）。
- `--export-json ...`：把 CPG 保存到 JSON 文件。
- `--top-level ...`：显式指定项目根目录，便于项目结构归一化。
- `--exclusion-patterns ...`：避免扫描 `node_modules`/构建产物目录；否则项目一大就会非常慢，甚至爆内存。
- 最后的路径参数（`/path/to/your-ts-project`）：指定要分析的路径；可以是目录或文件列表。

### 3.2 先试跑（更快）：关闭默认 passes

如果你只想先确认“能跑通并生成图”，可以先不跑默认 passes：

```bash
cpg-neo4j/build/install/cpg-neo4j/bin/cpg-neo4j \
  --no-neo4j \
  --no-default-passes \
  --export-json /tmp/cpg.json \
  --top-level /path/to/your-ts-project \
  --exclusion-patterns node_modules \
  --exclusion-patterns dist \
  --exclusion-patterns build \
  --exclusion-patterns .git \
  /path/to/your-ts-project
```

之后再去掉 `--no-default-passes`，获得更完整的语义信息（例如 DFG / EOG 等）。

---

## 4. 输出 JSON 是什么样的？

导出的 JSON 文件结构是：

```json
{
  "nodes": [...],
  "edges": [...]
}
```

你可以把它理解为：
- `nodes`：图的节点列表（包含节点类型与属性）。
- `edges`：图的边列表（包含边类型与起止节点等）。

图 schema 的说明可参考 `cpg-neo4j/README.md` 以及项目文档（Graph schema/specs）。

---

## 5. 常见问题与排查建议

### 5.1 很慢/文件数量爆炸

99% 的情况是把 `node_modules`、打包产物、缓存目录也扫进去了。

建议至少排除：
- `node_modules`
- `dist` / `build` / `out`
- `coverage`
- `.next`（Next.js）
- `.turbo`（Turborepo）
- `.git`

使用方式就是重复加 `--exclusion-patterns <pattern>`。

### 5.2 解析到非 TS/TSX 文件怎么办？

TypeScript 前端默认会处理 `.ts` / `.tsx`。
如果你的仓库是混合项目（包含很多非 TS 文件），不需要额外操作：不支持的文件一般会被跳过或由其他前端处理（如果你启用了它们）。

最重要的仍然是 **限制扫描范围** 与 **排除大目录**。

### 5.3 需要更多语义/跨文件效果不理想

TypeScript 前端属于实验性支持；对大型工程的跨文件语义还需要依赖 passes 与推断能力。

建议步骤：
1) 先在一个小子目录试跑（例如只传 `src/`）。
2) 再逐步扩大到整个仓库。
3) 去掉 `--no-default-passes`，让默认 passes 跑起来。

---

## 6. 下一步（可选）

- 如果你之后想在 Neo4j 里可视化/用 Cypher 查询：把 `--no-neo4j` 去掉，并按 `cpg-neo4j/README.md` 启动 Neo4j（带 APOC）。
- 如果你想在代码里直接使用 CPG（而不是 CLI）：参考根目录的 `README.md` / `README.zh-CN.md` 的 “As Library / 作为库使用”。

