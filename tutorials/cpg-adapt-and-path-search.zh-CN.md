**ArkTS 适配**

在处理源码文件时，先插入一层 ArkUI 专用分支。遇到 `struct HomePage` 这种页面文件，顺着顶层节点重新组装页面结构：

- `struct HomePage` 组装成组件节点
- `@State isStart: boolean = false` 组装成字段节点
- `requestPermissions(): void { ... }` 这种“签名节点 + 方法体”组装成方法节点
- `getGeolocation = (...) => { ... }` 这种“字段 + 箭头函数”组装成方法节点
- `void { ... }` 包裹的方法体会被重新抽成正常代码块
- `if (...) { ... }` 会进入图，不会把分支里的调用丢掉

例子：

```ts
onPageShow() {
  this.init();
  this.requestPermissions();
}

requestPermissions(): void {
  let atManager = abilityAccessCtrl.createAtManager();
  atManager.requestPermissionsFromUser(...).then((data) => {
    if (...) return;
    LocationUtil.geolocationOn(this.getGeolocation);
  });
}

getGeolocation = (...) => {
  geoLocationManager.getAddressesFromLocation(...);
}
```

补完以后，CPG 里会出现这些节点：

```json
{
  "nodes": [
    { "id": 101, "labels": ["Function"], "name": "onPageShow", "line": 93 },
    { "id": 201, "labels": ["Function"], "name": "requestPermissions", "line": 146 },
    { "id": 202, "labels": ["Call"], "name": "createAtManager", "line": 147 },
    { "id": 203, "labels": ["Call"], "name": "requestPermissionsFromUser", "line": 149 },
    { "id": 204, "labels": ["IfElse"], "line": 150 },
    { "id": 205, "labels": ["Call"], "name": "geolocationOn", "line": 161 },
    { "id": 206, "labels": ["Function"], "name": "getGeolocation", "line": 66 },
    { "id": 207, "labels": ["Call"], "name": "getAddressesFromLocation", "line": 84 }
  ]
}
```

没有这层适配时，`requestPermissions(): void` 和 `getGeolocation = (...) => {}` 这两类节点很容易缺失，后面的链就断了。

**解析 CPG 和找路径**

生成 `cpg.json` 以后，后端会把原始节点和边整理成内部图。节点保留文件、行号、代码、名字；边保留 `AST`、`INVOKES`、`EOG`、`DFG`、`PDG`。然后再补一类本地调用边 `LOCAL_INVOKES`，专门连这种关系：

```ts
LocationUtil.geolocationOn(this.getGeolocation)
```

也就是把 `geolocationOn(this.getGeolocation)` 连到 `getGeolocation`。

对上面这段代码，内部邻接关系如下：

```json
{
  "101": [{ "type": "INVOKES", "endNode": 201 }],
  "201": [
    { "type": "AST", "endNode": 202 },
    { "type": "AST", "endNode": 203 },
    { "type": "AST", "endNode": 205 }
  ],
  "203": [{ "type": "AST", "endNode": 204 }],
  "205": [{ "type": "LOCAL_INVOKES", "endNode": 206 }],
  "206": [{ "type": "AST", "endNode": 207 }]
}
```

然后把已有分析识别出来的点对应到图上：

- `source = onPageShow`
- `sink = getAddressesFromLocation`

对应锚点就是：

```text
sourceAnchor = 101
sinkAnchor = 207
```

接着做广度优先搜索。搜索时维护：

- 队列
- 已访问集合
- 父节点表

并且对每个节点的**所有后继边**都处理。边会按这个优先级排序后全部入队：

```text
DFG > PDG > EOG > INVOKES > LOCAL_INVOKES > AST
```

在这条链上，搜索过程是：

```text
初始队列: [101]

取出 101
加入后继: 201
队列: [201]

取出 201
它有多个后继: 202, 203, 205
全部入队
队列: [202, 203, 205]

取出 202
不是目标

取出 203
加入后继: 204
队列: [205, 204]

取出 205
加入后继: 206
队列: [204, 206]

取出 204
不是目标

取出 206
加入后继: 207
队列: [207]

取出 207
命中目标，停止
```

这个搜索本身得到的主路径是：

```text
onPageShow
-> requestPermissions
-> geolocationOn(this.getGeolocation)
-> getGeolocation
-> getAddressesFromLocation
```

搜索时还有这些限制：

- 最大深度 `120`
