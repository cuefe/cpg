# 教程：给 TypeScript 前端补上 `.ets` 适配

## 1. 背景

目标项目是 `Wechat_HarmonyOS`。它的主要业务代码大多在 `.ets` 文件里。

最开始用下面这条命令导出 CPG：

```bash
cpg-neo4j/build/install/cpg-neo4j/bin/cpg-neo4j \
  --no-neo4j \
  --export-json ./results/cpg.example.json \
  --top-level ./Wechat_HarmonyOS \
  --exclusion-patterns node_modules \
  --exclusion-patterns dist \
  --exclusion-patterns build \
  --exclusion-patterns .git \
  ./Wechat_HarmonyOS
```

导出后发现图里只记录了极少数源码文件，基本只有少量 `.ts` 文件，绝大多数 `.ets` 文件没有进入 JSON。

## 2. 根因

根因不是导出命令写错了，而是 **TypeScript 前端默认只接收 `.ts` 和 `.tsx`**。

具体看这两层：

1. 语言前端声明支持的文件后缀

原来 `TypeScriptLanguage.kt` 里是：

```kotlin
override val fileExtensions = listOf("ts", "tsx")
```

这意味着 `.ets` 在收集源码阶段就会被跳过。

2. 解析脚本对文件类型的处理也偏向标准 TypeScript 文件

原来的 `parser.ts` 使用 `createProgram(...)` 去加载输入文件。这条路径对标准 `.ts/.tsx` 没问题，但对 `.ets` 不够直接，也不利于单文件解析。

- `fileExtensions`：允许进入这个语言前端处理的文件后缀列表
- `createProgram`：TypeScript 官方编译接口，偏“项目/编译单元”模式
- `createSourceFile`：TypeScript 官方单文件解析接口，偏“直接把一个文件解析成语法树”

## 3. 适配思路

1. 先让前端在文件收集阶段接受 `.ets`
2. 再让解析脚本把 `.ets` 按 TypeScript 语法类型去解析

## 4. 实际修改

### 4.1 扩展支持的文件后缀

文件：

- `cpg-language-typescript/src/main/kotlin/de/fraunhofer/aisec/cpg/frontends/typescript/TypeScriptLanguage.kt`

修改后：

```kotlin
override val fileExtensions = listOf("ts", "tsx", "ets")
```

这一步的作用很直接：让 `.ets` 不再被前端过滤掉。

### 4.2 调整解析脚本

文件：

- `cpg-language-typescript/src/main/typescript/src/parser.ts`

主要改动有两点：

1. 不再走 `createProgram(...)`
2. 改为按文件后缀选择 `ScriptKind`，然后直接调用 `createSourceFile(...)`

现在的核心逻辑是：

```ts
const extension = path.extname(file).toLowerCase();
const scriptKind =
    extension === '.tsx'
        ? ScriptKind.TSX
        : extension === '.jsx'
          ? ScriptKind.JSX
          : extension === '.js'
            ? ScriptKind.JS
            : ScriptKind.TS;

const source = createSourceFile(file, fs.readFileSync(file, 'utf8'), ScriptTarget.Latest, true, scriptKind);
```

- `ScriptKind`：告诉 TypeScript 解析器“这个文件按什么脚本类型解释”
- `ScriptKind.TS`：按 TypeScript 文件处理
- `ScriptKind.TSX`：按带 JSX 的 TypeScript 文件处理
- `createSourceFile`：直接把单个文件解析成语法树

这里没有单独的 `ETS` 脚本类型，所以当前做法是：

- `.ets` 走 `ScriptKind.TS`

## 5. 重新构建

修改后需要重新生成 TypeScript parser 资源，并重新安装 `cpg-neo4j` CLI：

```bash
./gradlew :cpg-language-typescript:processResources --rerun-tasks
./gradlew :cpg-neo4j:installDist --rerun-tasks
```

第一条命令会重新编译 parser 资源。  
第二条命令会重新生成可执行的 `cpg-neo4j`。

## 6. 验证方式

### 6.1 重新导出 CPG JSON

继续使用原来的导出命令：

```bash
cpg-neo4j/build/install/cpg-neo4j/bin/cpg-neo4j \
  --no-neo4j \
  --export-json ./results/cpg.example.json \
  --top-level ./Wechat_HarmonyOS \
  --exclusion-patterns node_modules \
  --exclusion-patterns dist \
  --exclusion-patterns build \
  --exclusion-patterns .git \
  ./Wechat_HarmonyOS
```

这次导出日志里已经能看到大量 `.ets` 文件被解析。

### 6.2 对比 JSON 里记录到的源码路径

重新统计后，结果是：

- 项目里的源码文件数：`38`
- JSON 里记录到的源码文件数：`38`
- 缺失文件数：`0`
