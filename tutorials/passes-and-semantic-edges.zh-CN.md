# 概念速查：Pass 是什么？EOG/DFG/CDG/PDG 边表示什么？

本页解释在 CPG（Code Property Graph）里经常出现的两个概念：

- **Pass**：图构建后的“语义补全阶段”
- **EOG / DFG / CDG / PDG**：几类常见的“语义边”（不是 AST 结构边）

面向读者：使用 `cpg-neo4j` 导出 JSON（`--export-json`）或推送 Neo4j 时，想理解输出里这些术语是什么意思、为什么有时会“没有这些边”。

---

## 1. Pass 是什么意思？

可以把 CPG 的构建分成两步：

1) **语言前端（frontend）解析**：把源码解析成基础图（通常至少包含 AST 结构、节点的 `code`、位置、基本类型/符号占位等）。
2) **运行一系列 Pass**：在基础图之上继续做“语义补全/图增强”，例如：
   - 符号解析（把 `foo()` 解析到哪个函数定义）
   - 类型解析/传播（让表达式/变量有更可信的类型信息）
   - 建立数据流、执行顺序、控制依赖等语义边（`DFG/EOG/CDG/PDG`）

### 1.1 默认 Pass（default passes）

大多数情况下你会启用“默认 Pass 集合”，它会让输出的图更完整，但也更慢、更耗内存。

如果你使用 `cpg-neo4j` CLI：
- **不加** `--no-default-passes`：会注册并运行默认 passes（更“全”）
- **加了** `--no-default-passes`：不会注册默认 passes（更“快”，但语义边可能缺失）

> 经验法则：  
> 只想先验证“能跑通/路径没选错” → 先加 `--no-default-passes`。  
> 需要做数据流/控制流相关分析 → 不要加它，或至少要手动启用相关 passes。

### 1.2 为什么我导出的 JSON 里没有 EOG/DFG/CDG/PDG？

最常见原因就是：你用了 `--no-default-passes`，或者你只跑了很少的 pass。

这类边基本都依赖后续分析阶段生成；只靠“前端解析”通常拿不到完整的 EOG/DFG/CDG/PDG。

---

## 2. 这些边到底是什么？

在导出的 JSON 里，通常能看到：

```json
{
  "nodes": [...],
  "edges": [
    { "type": "EOG", "startNode": 1, "endNode": 2, "properties": {...} },
    { "type": "DFG", "startNode": 3, "endNode": 4, "properties": {...} }
  ]
}
```

这里的 `edges[].type` 就是“关系类型”，比如 `EOG`、`DFG`、`CDG`、`PDG`。

下面按用途解释它们。

---

## 3. EOG：Evaluation Order Graph（求值/执行顺序图）

**一句话**：`EOG` 边表示“程序执行/表达式求值的先后顺序路径”。

直观理解：
- AST 是“语法树”（谁包含谁）
- EOG 是“从哪里执行到哪里”（更像控制流/执行路径）

`EOG` 边常见属性（取决于具体节点/边）：
- `branch`：分支信息，通常表示该边走的是 `true/false` 分支（例如 `if (cond)`）
- `unreachable`：是否通向不可达代码

例子（TypeScript）：

```ts
if (cond) {
  a();
} else {
  b();
}
c();
```

可以把 EOG 理解成“可能的执行路径”，常见会出现类似的顺序关系：
- 条件求值节点 `cond` → `a()`（`branch=true`）
- 条件求值节点 `cond` → `b()`（`branch=false`）
- `a()` → `c()`、`b()` → `c()`（两条路径在 `c()` 处汇合）

**适合做什么**：
- 近似“控制流”的遍历、路径分析
- 判断某条语句是否可能在另一条之后执行

---

## 4. DFG：Data Flow Graph（数据流图）

**一句话**：`DFG` 边表示“值从哪里流到哪里”（数据依赖/值传递）。

直观例子（TypeScript）：

```ts
const y = x + 1;
return y;
```

你可以把 DFG 想象成：
- `x` 的值会流入 `x + 1`
- `x + 1` 的结果会流入 `y`
- `y` 的值会流入 `return y`

`DFG` 的一个关键概念是 **granularity（粒度）**：
- 有些数据流是“整个对象”层面（FULL）
- 有些是“字段/下标”层面（例如对象的某个字段、数组某个索引）

**适合做什么**：
- 污点分析 / 数据流追踪（source → sink）
- 切片（某个变量/表达式的来源与影响范围）

---

## 5. CDG：Control Dependence Graph（控制依赖图）

**一句话**：`CDG` 边表示“某节点的执行受哪个条件/控制点支配”。

直观例子：

```ts
if (y > 10) {
  doSomething();
}
```

`doSomething()` 是否会执行，依赖于条件 `(y > 10)`。  
CDG 就是把这种“执行是否发生”的依赖关系显式表示出来。

**适合做什么**：
- 分析哪些语句受哪些条件影响（例如安全检查是否支配了敏感调用）
- 程序切片（带控制依赖的切片）

---

## 6. PDG：Program Dependence Graph（程序依赖图）

**一句话**：`PDG` 是把 **数据依赖（DFG）** + **控制依赖（CDG）** 合并在一个视图里。

在很多研究和工具里，PDG 用来支持：
- 统一的“依赖图”遍历（不用分别看 DFG 和 CDG）
- 更完整的程序切片

**你在导出 JSON 里可能看到的现象**：
- 同样的 `startNode -> endNode` 依赖关系，可能既出现在 `DFG`，也会出现在 `PDG`。  
  这通常代表 “PDG 视图复用了 DFG/CDG 的边”，不是你重复导出了两份代码。

---

## 7. 怎么在导出的 JSON 里快速确认这些边“有没有生成”？

最实用的方式：统计边类型出现次数（用 `jq`）。

```bash
jq -r '.edges[].type' /tmp/cpg.json | sort | uniq -c | sort -nr | head
```

常见解读：
- 只看到 `AST`、`SCOPE`、`TYPE`、`LANGUAGE` 等基础关系 → 可能没跑默认 passes（或分析范围很小）
- 看到 `EOG` / `DFG` / `CDG` / `PDG` → 说明对应语义图边基本已经跑出来了（质量取决于语言前端与 passes 成熟度）
