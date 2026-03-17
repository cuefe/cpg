# 教程：用 TaintMini 分析已有的 CPG JSON

这篇文档说明如何用 `scripts/taintmini_cpg.py` 分析一个**已经导出的 CPG JSON**，并输出接近 TaintMini 的污点流结果。

## 1. 怎么运行

最小命令：

```bash
python3 scripts/taintmini_cpg.py \
  -i results/cpg.example.json \
  -o /tmp/taintmini-cpg-out
```

带 benchmark：

```bash
python3 scripts/taintmini_cpg.py \
  -i results/cpg.example.json \
  -o /tmp/taintmini-cpg-out \
  -b
```

带过滤配置：

```bash
python3 scripts/taintmini_cpg.py \
  -i results/cpg.example.json \
  -o /tmp/taintmini-cpg-out \
  -c /path/to/config.json
```

入口和核心逻辑现在都在 [taintmini_cpg.py](/home/cuefe/cpg/scripts/taintmini_cpg.py)。

## 2. 输入参数

- `-i / --input`
  输入路径。可以是单个 CPG JSON，或者一个索引文件。索引文件里每行是一个 JSON 路径。
- `-o / --output`
  输出目录。会生成 `<输入文件名>-result.csv`。
- `-c / --config`
  过滤配置，格式与原版 TaintMini 一样：
  ```json
  { "sources": [...], "sinks": [...] }
  ```
  这里是**字符串精确匹配**，不是正则。
- `-j / --jobs`
  并发数。
- `-b / --bench`
  额外生成 `<输入文件名>-bench.csv`。

## 3. 输入文件要求

输入必须是一个顶层包含 `nodes` 和 `edges` 的 JSON：

```json
{
  "nodes": [...],
  "edges": [...]
}
```

这里的几个英文：

- `nodes`：节点，也就是图上的点
- `edges`：边，也就是点和点之间的关系
- `DFG`：`Data Flow Graph`，数据流边，表示“值从哪里流到哪里”
- `AST`：`Abstract Syntax Tree`，语法树边，表示语法父子关系
- `REFERS_TO`：引用指向哪个声明
- `INITIALIZER`：变量的初始值
- `ARGUMENTS`：调用的参数

## 4. 它怎么处理已有的 CPG JSON

1. 读取 `nodes` 和 `edges`
2. 找出所有 `Function` 节点，作为方法候选
3. 按源码文件路径给函数分组，形成 `page_name`
4. 找出函数里的 `Reference` 节点，也就是变量使用点
5. 判断这个引用是不是某个调用参数里的数据流节点，如果是，就把那个调用当成 `sink`
6. 沿 `DFG + REFERS_TO + INITIALIZER` 反向找来源，把找到的文本记成 `source`

## 5. 输出怎么看

主输出文件是：

```text
<basename>-result.csv
```

表头固定为：

```text
page_name | page_method | ident | source | sink
```

含义：

- `page_name`
  页面分组名或文件分组名
- `page_method`
  方法名
- `ident`
  变量名
- `source`
  来源
- `sink`
  去向调用

示例：

```text
OpenHarmonyTestRunner | onRun | cmd | cmd = 'aa start -d 0 -a TestAbility' + ' -b ' + abilityDelegatorArguments.bundleName | UNKNOWN.executeShellCommand
```

意思是：

“在 `OpenHarmonyTestRunner` 的 `onRun` 方法里，变量 `cmd` 的值最终流到了 `executeShellCommand`。”

如果加了 `-b`，还会生成：

```text
<basename>-bench.csv
```

表头是：

```text
page|start|end
```

## 6. `page_name` 和 `page_method` 是什么

- `page_name`
  这条流属于哪个页面分组或文件分组。
  如果源码路径里有 `pages/...`，就取 `pages/` 后面的相对路径；否则退化成文件名。
- `page_method`
  这条流发生在哪个函数或方法里，例如 `onRun`、`onPrepare`。

所以在下面这条结果里：

```text
OpenHarmonyTestRunner | onRun | cmd | ... | UNKNOWN.executeShellCommand
```

可以直接理解成：

- 文件分组：`OpenHarmonyTestRunner`
- 方法：`onRun`
- 变量：`cmd`
- 去向：`executeShellCommand`
