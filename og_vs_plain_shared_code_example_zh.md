# OG 与 Plain 找到同一段代码的示例

### 示例任务
- 任务：`matplotlib__matplotlib-18869`
- 两个流程最终都找到的同一段目标代码：
  - `lib/matplotlib/__init__.py`
  - `__getattr__(name)`
  - 其中处理 `if name == "__version__":` 的代码块

### 两边最终找到的代码
OG 和 Plain 最后都收敛到了同一个实现位置：

```python
lib/matplotlib/__init__.py

def __getattr__(name):
    if name == "__version__":
        ...
```

### OG 流程
```text
问题
  -> search_code("__version__ matplotlib version")
  -> 第一条命中直接返回 lib/matplotlib/__init__.py 中的精确 snippet
  -> 少量补充读取
  -> 对同一个文件调用 mcp__og-memory__edit_file
  -> 完成 patch
```

代码片段阶段的工具序列：
- `mcp__og-memory__search_code`
- `Read`
- `Read`
- `Glob`
- `Read`
- `mcp__og-memory__edit_file`

### Plain 流程
```text
问题
  -> find matplotlib __init__.py
  -> grep "__version__"
  -> read lib/matplotlib/__init__.py
  -> 更多 grep/bash 探索
  -> 在同一个文件上 Edit
  -> 完成 patch
```

代码片段阶段的工具序列：
- `Grep`
- `Read`
- `Grep`
- `Bash`
- `Bash`
- `Bash`
- `Bash`
- `Read`
- `Bash`
- `Bash`
- `Bash`
- `Edit`

### 代码片段阶段对比
这个对比只看“第一次找到代码”到“第一次编辑同一个目标 snippet”这段过程。

| 模式 | 估算阶段成本 (USD) | Input Tokens | Output Tokens | Cache Read Tokens | Cache Write Tokens | Turns |
|---|---:|---:|---:|---:|---:|---:|
| OG | `$0.0543` | `44` | `6` | `224,494` | `54,605` | `6` |
| Plain | `$0.0814` | `84` | `31` | `540,556` | `22,499` | `12` |
| 差值 `(OG-Plain)` | `$-0.0271` | `-40` | `-25` | `-316,062` | `+32,106` | `-6` |

说明：
- 这里的阶段成本是估算值。
- 因为 Claude 只对整次任务记录精确的 `total_cost_usd`，不会对每个中间阶段单独记账。

### 结论
- 两种方法都找到了同一段代码。
- OG 找到 snippet 的路径更直接。
- Plain 也能找到，但需要更长的 grep/find/read 链路。
- 在这个共享示例里，OG 在“找 snippet + 编辑 snippet”阶段使用了更少的 turns 和更少的 tokens。
