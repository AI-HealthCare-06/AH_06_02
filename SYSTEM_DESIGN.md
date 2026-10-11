# SYSTEM_DESIGN

Core system design rules for this project.
Precedence on any conflict: project tool configs (`pyproject.toml`, ruff/mypy
settings) > this document > Google Python Style Guide > PEP 8.

## 1. Python Version & Typing

- Target **Python 3.13+**.
- Use modern native typing syntax:
  - Built-in generics (PEP 585): `list[int]`, `dict[str, float]`
    — never `typing.List`, `typing.Dict`, etc.
  - Union syntax (PEP 604): `int | None`, `str | bytes`
    — never `typing.Optional`, `typing.Union`.
  - Native generics and type aliases (PEP 695):
    `def first[T](items: list[T]) -> T: ...`, `type UserId = int`
    — never `TypeVar`, `Generic`, `TypeAlias`.
- Importing from `typing` is allowed ONLY for names with no built-in
  equivalent: `Any`, `Protocol`, `Literal`, `TypedDict`, `cast`,
  `TYPE_CHECKING`, and similar. (This keeps the `TYPE_CHECKING` rule in
  AGENTS.md valid.)
- Annotate parameters and return types of all public functions and methods.

## 2. Code Style

- Primary guide: **Google Python Style Guide**
  (<https://google.github.io/styleguide/pyguide.html>).
  Where it is silent, **PEP 8** (<https://peps.python.org/pep-0008/>) applies.
- Mechanical style is enforced by tools, not prose. Before every commit run:
  - `uv run ruff format .`
  - `uv run ruff check --fix .`
  Code that passes these tools is correctly styled; do not hand-enforce
  formatting rules beyond them.

## 3. Object-Oriented Design

- Model the domain with classes that own both their data and the behavior on
  that data; keep internal state non-public (`_name`) unless callers need it.
- Depend on interfaces at boundaries: define a `Protocol` (or ABC) where a
  layer consumes a capability it does not implement.
- Prefer composition over inheritance. Inherit only for a genuine is-a
  relationship where the subclass is fully substitutable for the base
  (Liskov). Never inherit merely to reuse code.
- Do not introduce an abstraction (base class, interface, factory) until at
  least two concrete implementations need it.

## 4. Architecture (Clean Architecture)

We follow **Clean Architecture** (Robert C. Martin, *Clean Architecture: A
Craftsman's Guide to Software Structure and Design*, 2017). Its single
overriding constraint is the **Dependency Rule**: source code dependencies
must point only inward, toward higher-level policies. Nothing in an inner
circle may know anything about an outer circle.

Circles, from inner to outer (Martin's schematic):

```
Entities → Use Cases → Interface Adapters → Frameworks & Drivers
(inner)                                              (outer)
   ↑ all source-code dependencies point this way (inward) ↑
```

- **Entities** — enterprise/domain business rules. Pure logic; import no
  framework, no I/O, nothing from outer circles. Testable with plain unit
  tests.
- **Use Cases** — application-specific business rules orchestrating
  entities. Define the boundary interfaces (`Protocol`/ABC) for anything
  outward they need.
- **Interface Adapters** — controllers, presenters, gateways converting data
  between use-case format and external format (DB, web, UI).
- **Frameworks & Drivers** — DB, web framework, UI, devices. Details, kept
  at the outermost circle.

Crossing boundaries uses the Dependency Inversion Principle: the inner
circle owns the interface, the outer circle implements it — never the
reverse. Data crossing a boundary is simple structures, never rows/ORM
objects from the outer circle.

Martin is explicit that the four circles are schematic — there is no rule
requiring exactly four; the Dependency Rule always applies no matter how
many you have. Accordingly, the physical layout (package names, number of
layers, one package vs. many) is decided per project; compliance is judged
by import direction, not folder names. A small project may collapse circles
as long as the Dependency Rule holds.

### This project (phase 1)

Three layers, collapsed per the paragraph above:

```
app/apis/v1/      routers        — HTTP in/out only
app/services/     business rules — orchestration, policy
app/repositories/ queries        — Tortoise access
app/models/       table defs     — Tortoise models
```

- Import direction only: `apis` → `services` → `repositories` → `models`.
  Never the reverse. A router must not query the DB directly; a service must
  not know about `Request`/`Response`.
- Phase 1 passes Tortoise model objects across the service boundary. Martin's
  rule says simple structures only, and we accept that gap knowingly: the
  schema is frozen by the team's table spec and the deadline is 2026-11-05.
  Converting every boundary to DTOs is phase 2. Response DTOs in `app/dtos/`
  already cover the outermost boundary, so nothing leaks past HTTP.
- `ai_worker` is a separate process at the outermost circle. `app` never
  imports it. Shared contract values are copied into
  `app/services/model_artifact.py` and kept in sync by a test.

Anti-over-engineering rules (equally binding):

- Do not create a separate layer, package, or file for a role that would
  contain only pass-through code.
- Group cohesive classes in one module; do not create one file per class.
- Do not add design patterns, generic frameworks, or configuration layers
  for hypothetical future needs (YAGNI). Add them when a second concrete
  use case exists.
