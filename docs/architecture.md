# Architecture / v1.0.0

Browser (vanilla HTML/CSS/JS) → loopback FastAPI → bounded subprocess worker → language adapters → unified JSON → interactive findings / HTML export.

The browser sends one language and up to 12 UTF-8 source files. No ZIP/project imports. API validates names, extensions and size before starting a worker. Each analysis has a temporary directory, fixed argument lists and time limits. Compiler output is normalized to `file, line, column, severity, rule, tool, message, help`.

Python AST and Tree-sitter parse syntax. Ruff checks names and common mistakes, Bandit flags potential Python security risks, Pyright checks inferred/annotated types. G++ uses C++17 syntax-only checks; Cppcheck adds static findings. Javac compiles with annotation processing disabled. Roslyn compiles a generated offline .NET 8 project (library or executable target, based on top-level statements; output is never run). Dependencies from the user's projects are not restored.

`coverage=completed` means all configured tools finished, **not** that every property of the program was checked. `partial` means at least one tool was unavailable, failed or timed out. Results are capped at 400 findings and marked truncated if necessary. Independent tools can report the same underlying bug separately.

GitHub Pages contains static demonstration fixtures for the built-in examples. It is not an API endpoint and never presents fixture reports as fresh analysis of edited code. The same assets are served in the local app.

Design references supplied by the maintainer: frontend-slides (typographic composition and restraint; no presentation-specific 16:9 rules applied to the app), Frontend-Design-SKILLS-for-AI (technical/mono product UI, hierarchy and accessible states), beautify-github-profile (README navigation, badges and project cards). Their code/art assets were not copied into CodeScope.
