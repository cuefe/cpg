# 把 CPG 融入 OH-Senstive-Flow 现有流程

## 1. 思路

只保留两个模式：

- `heuristic`
  - 完全走当前流程
- `cpg`
  - 保留现有 `source` / `sink` 识别
  - 每次分析都从源码重新生成 CPG
  - 用 CPG 生成调用图和 `source -> sink` 路径
  - 再转换成当前项目的 `dataflows.json`

## 2. `cpg` 模式下的流程

1. 扫描 App 源码
2. 识别 `sources`
3. 识别 `sinks`
4. 调用 `cpg-neo4j`，从这次源码生成 `cpg.json`
5. 把现有 `source` / `sink` 映射到 CPG 节点
6. 用 CPG 构建内部调用图
7. 从内部调用图抽取 `source -> sink` 路径
8. 把路径转换成当前 `dataflows.json`
9. 后续页面聚合、隐私报告继续按原流程执行

## 3. 生成 CPG

```bash
lib/cpg/cpg-neo4j/build/install/cpg-neo4j/bin/cpg-neo4j \
  --no-neo4j \
  --export-json <outputDir>/cpg.json \
  --top-level <appRoot> \
  --exclusion-patterns node_modules \
  --exclusion-patterns oh_modules \
  --exclusion-patterns hvigor \
  --exclusion-patterns dist \
  --exclusion-patterns build \
  --exclusion-patterns .git \
  <appRoot>
```

把 `cpg.json` 存到本次运行目录里，作为中间产物。
