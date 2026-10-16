## General Design Guidelines

### 1. Core Principles

When designing and implementing code, **define the input and output contracts of each component before implementing its individual functionality**.

Keep component-specific logic independent while standardizing data exchange formats between functions, modules, and architectural layers wherever practical.

The goal is to make data flows predictable and improve implementation efficiency, maintainability, and extensibility.

### 2. Standardize Input and Output Interfaces

- Functions serving similar purposes should use consistent return types and data structures.
- Choose appropriate structures, such as `dict`, `list`, or data classes, based on their intended use.
- Define the basic return structure before implementing individual features.
- Represent feature-specific information by adding appropriate keys or fields to the shared structure.
- Avoid unnecessarily changing the meaning or type of existing fields.
- Design interfaces so that callers do not need to handle inconsistent return formats for equivalent operations.

### 3. Establish Common Return Paths

Whenever practical, provide a shared return path for operations of the same kind.

For example, operations that return results to external callers may use a standardized response structure:

```python
{
    "ok": True,
    "data": {},
    "error": None
}
```

- `ok`: Indicates whether the operation succeeded.
- `data`: Contains the operation result.
- `error`: Contains error information.

Do not enforce this exact structure on every function. Define appropriate shared contracts based on the responsibilities of each component.

### 4. Separate Component-Specific Logic from Shared Logic

Each function should primarily focus on its own responsibility.

When multiple functions require the same supporting operations, consolidate them into shared functions where appropriate.

Examples include:

- Formatting return values
- Retrieving and aggregating state
- Validating inputs and outputs
- Handling errors
- Logging

For example, when multiple operations return the same type of application state, implement a shared state-building function and have those operations return their results through it.

### 5. Maintain Clear Data Flows

During design, explicitly identify how data moves between functions, modules, and architectural layers.

```text
Caller
    ↓
Component-specific operation
    ↓
Shared result-building function
    ↓
Standardized return value
    ↓
Caller
```

- Prefer consistent data flows for operations of the same kind.
- Avoid introducing separate return paths without a clear reason.
- Do not force operations through shared functions when doing so provides no meaningful benefit.

### 6. Extensibility and Compatibility

- When adding new features, prioritize reusing existing shared interfaces.
- When additional information is required, prefer extending existing structures with new fields.
- Before making changes that affect existing callers, identify and review their dependencies.
- Avoid unnecessary abstraction when standardization would increase complexity.

### 7. Implementation Workflow

When designing a new feature or module, follow this sequence whenever practical:

1. Define the component's responsibilities and scope.
2. Identify its callers and dependencies.
3. Define input and output types and their basic structures.
4. Separate shared operations from component-specific logic.
5. Implement shared data exchange mechanisms.
6. Implement individual operations and connect them to the shared interfaces.
7. Verify that return structures and data flows remain consistent.

### 8. Scope and Exceptions

These principles apply broadly to APIs, databases, file processing, web scraping, UI integration, and other forms of communication between modules.

However, **standardization should primarily target boundaries between components, modules, and architectural layers—not every internal function**.

Internal helper functions may use whatever types and return values best suit their responsibilities.

Do not introduce abstractions solely for the sake of standardization. Prioritize readability, predictability, and maintainability.

## Coding Conventions

Preserve the existing repository style and keep functions focused on one task.

### Responsibilities and Execution

- Keep the workflow clear enough to explain using function names alone.
- Prioritize an easy-to-follow execution flow over splitting code into more files or classes.
- Avoid abstractions or shared components introduced only for possible future extensions.
- Reuse existing monitoring logic and utilities.
- Keep `__init__` focused on constructing state. Run startup operations through explicit method calls.
- Make it clear where errors originate and where they are handled.
- Implement only the explicitly requested features.

### Internal Module Imports

Import repository-internal modules rather than importing their functions,
classes, or constants directly. Access these members through the module alias,
including in type hints, so their source remains visible at the point of use.

```python
from .. import response as resp
from .. import browser as br
from .search import collect as ser_clct

value = resp.array_value(payload, 64)
browser = br.Browser()
result = ser_clct.collect_search(browser, query)
```

Use the following aliases consistently for these modules when present:

| Module | Alias |
|---|---|
| `utils` | `ut` |
| `browser` | `br` |
| `response` | `resp` |
| `context` | `ctx` |
| `collect` | `clct` |
| `extract` | `extr` |
| `geocoding` | `geo` |
| `search.collect` | `ser_clct` |
| `search.parser` | `ser_par` |
| `place.collect` | `plc_clct` |
| `place.parser` | `plc_par` |

- Use lowercase aliases. For new modules, prefer recognizable abbreviations
  of 2–4 characters per component, separated by underscores when needed.
- Use the same alias for the same module across files whenever practical.
- If an alias conflicts with an existing local variable, use a recognizable
  alternative, such as `ctxt` for `context`. Avoid unrelated variable renaming.
- Update affected mock targets when changing imports, keeping test behavior
  unchanged.
- This rule applies to repository-internal modules. Standard-library and
  third-party imports may retain their existing style.
- Apply this convention to new or otherwise relevant code. Do not expand a
  limited task into a repository-wide import rewrite unless requested.

### Function Ordering

Place the workflow function, such as `run_update()`, near the top after imports
and module configuration. Group each public/helper function with the private
functions that directly support it:

```text
run_update
↓
public/helper function A
↓
private helpers supporting A
↓
public/helper function B
↓
private helpers supporting B
```

Do not place all public functions first and all private functions afterward.
Keep shared helpers near the relevant group without duplicating them.

### Signatures, Types, and Names

Keep function definitions and calls compact, using one line for arguments when
practical. Expand them when needed for readability.

Use type hints consistently, including explicit return types. Existing JSON
processing uses dictionaries and lists; do not impose DTOs or dataclasses without
a concrete benefit. Choose names that describe the actual responsibility, and
use underscore-prefixed names for internal helpers.

### Docstrings

Every new or modified function should begin with a short English docstring whose
first sentence starts with `To + verb`. Leave one blank line immediately after
the docstring.

```python
def load_rules(path: Path) -> dict:
    """To load existing rule metadata and contents."""

    ...
```

Describe actual behavior, including side effects or important assumptions when
useful. Do not describe a returned value when the function only writes a file.

## Change Policy

Make the smallest coherent change needed for the user's request. Avoid unrelated
refactoring, renaming, dependencies, or reorganizing working modules solely for
uniformity. Preserve backward compatibility when practical.

Inspect existing callers and utilities before changing interfaces. Preserve the
JSON contracts and checkpoint/recovery behavior when changing the workflow.
Do not rewrite existing functions solely to make every file conform to these
conventions when the request is limited to another task.

Keep external interpreter and entry-point configuration in the owning services,
and viewer data paths in the existing path configuration. Inspect configured
paths and date-folder selection before a live run; do not assume the configured
date is automatically today's date. Do not hardcode secrets into source files.

### Test Integrity

- Treat approved tests as established behavioral contracts.
- Do not modify, delete, rename, skip, or weaken approved tests without explicit user approval.
- When existing tests fail, investigate and fix the implementation first.
- Add new tests for new features without altering approved tests.
- Use Git commits and tags to track approved test baselines.
- If an approved test requires modification, explain the reason and request approval before proceeding.
- 