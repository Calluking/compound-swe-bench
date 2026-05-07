# Shared Code Retrieval Example: OG vs Plain

### Example task
- Task: `matplotlib__matplotlib-18869`
- Shared target found by both runs:
  - `lib/matplotlib/__init__.py`
  - `__getattr__(name)`
  - the `if name == "__version__":` block

### What both runs found
Both OG and Plain eventually converged on the same implementation site:

```python
lib/matplotlib/__init__.py

def __getattr__(name):
    if name == "__version__":
        ...
```

### OG flow
```text
Issue
  -> search_code("__version__ matplotlib version")
  -> top hit returns exact snippet in lib/matplotlib/__init__.py
  -> small follow-up reads
  -> mcp__og-memory__edit_file on the same file
  -> patch applied
```

Tool sequence in the code-snippet phase:
- `mcp__og-memory__search_code`
- `Read`
- `Read`
- `Glob`
- `Read`
- `mcp__og-memory__edit_file`

### Plain flow
```text
Issue
  -> find matplotlib __init__.py
  -> grep "__version__"
  -> read lib/matplotlib/__init__.py
  -> more grep/bash exploration
  -> Edit on the same file
  -> patch applied
```

Tool sequence in the code-snippet phase:
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

### Snippet-process comparison
This comparison isolates only the path from first code retrieval to first edit of the shared target snippet.

| Mode | Approx Phase Cost (USD) | Input Tokens | Output Tokens | Cache Read Tokens | Cache Write Tokens | Turns |
|---|---:|---:|---:|---:|---:|---:|
| OG | `$0.0543` | `44` | `6` | `224,494` | `54,605` | `6` |
| Plain | `$0.0814` | `84` | `31` | `540,556` | `22,499` | `12` |
| Delta `(OG-Plain)` | `$-0.0271` | `-40` | `-25` | `-316,062` | `+32,106` | `-6` |

Note:
- The phase cost is estimated from the token share of the full run, because Claude records exact `total_cost_usd` only for the whole task, not for each sub-phase.

### Interpretation
- Both approaches found the same code.
- OG found the snippet more directly.
- Plain also found it, but through a longer grep/find/read path.
- In this shared example, OG used fewer turns and fewer tokens in the snippet-finding/editing phase.
