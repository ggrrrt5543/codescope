import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from tree_sitter import Language, Parser
import tree_sitter_c_sharp
import tree_sitter_cpp
import tree_sitter_java

from . import __version__
from .models import AnalysisRequest, Finding, ToolRun

TIMEOUT = 18
MAX_FINDINGS = 400
GRAMMARS = {"cpp": tree_sitter_cpp, "csharp": tree_sitter_c_sharp, "java": tree_sitter_java}
HELP = {
    "syntax": "Проверьте синтаксис рядом с указанной позицией: скобки, разделители и отступы.",
    "ruff": "Проверьте имя и область видимости переменной; удалите неиспользуемый код. Код правила можно найти в документации Ruff.",
    "bandit": "Это потенциальный риск, а не доказанная уязвимость. Проверьте источник данных и замените опасный вызов безопасным API.",
    "pyright": "Сопоставьте ожидаемый и фактический типы. Добавьте проверку или явное преобразование, если оно соответствует задаче.",
    "compiler": "Проверьте типы, объявления и зависимости. Для внешних библиотек может потребоваться полное окружение проекта.",
}


class Analyzer:
    def __init__(self, request: AnalysisRequest, root: Path):
        self.request = request
        self.root = root
        self.findings: list[Finding] = []
        self.tools: list[ToolRun] = []
        self.output_truncated = False
        self.last_returncode = 0
        for source in request.files:
            (root / source.name).write_text(source.content, encoding="utf-8")

    def add(self, **values):
        if len(self.findings) < MAX_FINDINGS:
            self.findings.append(Finding(**values))
        else:
            self.output_truncated = True

    def run(self, name, command, accepted=(0, 1)):
        local_binary = Path(sys.executable).parent / (command[0] + (".exe" if os.name == "nt" else ""))
        executable = str(local_binary) if local_binary.is_file() else shutil.which(command[0])
        if not executable:
            self.tools.append(ToolRun(name=name, status="unavailable", detail=f"Не установлен {command[0]}"))
            return None
        command = [executable, *command[1:]]
        env = {**os.environ, "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""), "NO_COLOR": "1", "PYTHONIOENCODING": "utf-8",
               "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
               "DOTNET_CLI_HOME": str(self.root / ".dotnet-home")}
        try:
            with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
                process = subprocess.Popen(command, cwd=self.root, stdout=stdout, stderr=stderr, env=env,
                                           start_new_session=(os.name == "posix"))
                try:
                    process.wait(timeout=TIMEOUT)
                except subprocess.TimeoutExpired:
                    if os.name == "posix":
                        import signal
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                    process.wait()
                    self.tools.append(ToolRun(name=name, status="timeout", detail="Превышен лимит 18 секунд"))
                    return None
                stdout.seek(0)
                stderr.seek(0)
                out = stdout.read(2_000_000).decode("utf-8", errors="replace")
                err = stderr.read(2_000_000).decode("utf-8", errors="replace")
            self.last_returncode = process.returncode
            status = "completed" if process.returncode in accepted else "failed"
            detail = "" if status == "completed" else (err or out or f"Process exited with code {process.returncode}")[-1200:].replace(str(self.root), "<workspace>")
            self.tools.append(ToolRun(name=name, status=status, detail=detail))
            return (out, err) if status == "completed" else None
        except OSError as exc:
            self.tools.append(ToolRun(name=name, status="failed", detail=str(exc)[:300]))
            return None

    def syntax(self):
        for source in self.request.files:
            if self.request.language == "python":
                try:
                    ast.parse(source.content, filename=source.name)
                except (SyntaxError, ValueError) as exc:
                    self.add(file=source.name, line=max(1, getattr(exc, "lineno", 1) or 1),
                             column=max(1, getattr(exc, "offset", 1) or 1), severity="error",
                             rule="syntax", tool="Python AST", message=str(exc), help=HELP["syntax"])
                continue
            parser = Parser(Language(GRAMMARS[self.request.language].language()))
            tree = parser.parse(source.content.encode("utf-8"))
            stack = [tree.root_node]
            while stack:
                node = stack.pop()
                if node.is_error or node.is_missing:
                    line, byte_column = node.start_point
                    line_bytes = source.content.encode().split(b"\n")[line]
                    column = len(line_bytes[:byte_column].decode("utf-8", errors="replace")) + 1
                    self.add(file=source.name, line=line + 1, column=column, severity="error",
                             rule="missing-token" if node.is_missing else "syntax", tool="Tree-sitter",
                             message=f"Ожидается {node.type}" if node.is_missing else "Не удалось разобрать фрагмент кода",
                             help=HELP["syntax"])
                    continue
                stack.extend(reversed(node.children))
        name = "Python AST" if self.request.language == "python" else "Tree-sitter"
        self.tools.append(ToolRun(name=name, status="completed", detail="Разбор синтаксиса без выполнения кода"))

    def python(self):
        names = [source.name for source in self.request.files]
        output = self.run("Ruff", ["ruff", "check", "--isolated", "--output-format", "json", "--select", "E4,E7,E9,F,B", *names])
        if output:
            for entry in json.loads(output[0]):
                self.add(file=Path(entry["filename"]).name, line=entry["location"]["row"],
                         column=entry["location"]["column"], severity="error" if entry["code"] in {"F821", "F822", "F823"} else "warning",
                         rule=entry["code"], tool="Ruff", message=entry["message"], help=HELP["ruff"])
        output = self.run("Bandit", ["bandit", "-q", "-f", "json", "--ignore-nosec", *names])
        if output:
            for entry in json.loads(output[0]).get("results", []):
                self.add(file=Path(entry["filename"]).name, line=entry["line_number"],
                         column=entry.get("col_offset", 0) + 1, severity="warning",
                         rule=entry["test_id"], tool="Bandit", message=entry["issue_text"], help=HELP["bandit"])
        config = {"include": names, "typeCheckingMode": "basic", "pythonVersion": "3.10",
                  "autoSearchPaths": False, "useLibraryCodeForTypes": False}
        (self.root / "pyrightconfig.json").write_text(json.dumps(config))
        output = self.run("Pyright", ["pyright", "--outputjson", "--project", "pyrightconfig.json"])
        if output:
            for entry in json.loads(output[0]).get("generalDiagnostics", []):
                location = entry["range"]["start"]
                self.add(file=Path(entry["file"]).name, line=location["line"] + 1,
                         column=location["character"] + 1, severity=entry["severity"] if entry["severity"] != "information" else "info",
                         rule=entry.get("rule", "type"), tool="Pyright", message=entry["message"], help=HELP["pyright"])

    def cpp(self):
        names = [source.name for source in self.request.files]
        output = self.run("G++", ["g++", "-std=c++17", "-fsyntax-only", "-Wall", "-Wextra", "-fmax-errors=30", "-fdiagnostics-color=never", *names])
        if output:
            self.compiler_messages("G++", output[1])
        output = self.run("Cppcheck", ["cppcheck", "--xml", "--xml-version=2", "--enable=warning,style,performance,portability", "--std=c++17", "--max-configs=4", *names])
        if output:
            for entry in ET.fromstring(output[1]).findall(".//error"):
                location = entry.find("location")
                if location is not None and Path(location.get("file", "")).name in names:
                    self.add(file=Path(location.get("file")).name, line=max(1, int(location.get("line", "1"))),
                             column=max(1, int(location.get("column", "1"))), severity="warning",
                             rule=entry.get("id", "cppcheck"), tool="Cppcheck", message=entry.get("msg", ""), help=HELP["compiler"])

    def compiler_messages(self, tool, text):
        import re
        names = {source.name for source in self.request.files}
        pattern = re.compile(r"^(.*?):(\d+)(?::(\d+))?:\s*(fatal error|error|warning|note):\s*(.*)$")
        for raw in text.splitlines():
            match = pattern.match(raw)
            if not match or Path(match[1]).name not in names:
                continue
            level = "error" if "error" in match[4] else "info" if match[4] == "note" else "warning"
            self.add(file=Path(match[1]).name, line=int(match[2]), column=int(match[3] or 1),
                     severity=level, rule="compiler", tool=tool, message=match[5], help=HELP["compiler"])

    def java(self):
        output = self.run("Javac", ["javac", "-proc:none", "-encoding", "UTF-8", "-Xlint:all", "-d", str(self.root / "classes"), *[source.name for source in self.request.files]])
        if output:
            self.compiler_messages("Javac", output[1])

    def csharp(self):
        import re
        parser = Parser(Language(tree_sitter_c_sharp.language()))
        has_top_level = any(
            node.type == "global_statement"
            for source in self.request.files
            for node in parser.parse(source.content.encode()).root_node.children
        )
        output_type = "Exe" if has_top_level else "Library"
        binary = shutil.which("dotnet")
        if not binary:
            self.tools.append(ToolRun(name="Roslyn / .NET 8", status="unavailable", detail="Не установлен .NET SDK 8"))
            return
        dotnet_root = Path(binary).resolve().parent
        compilers = list((dotnet_root / "sdk").glob("8.0.*/Roslyn/bincore/csc.dll"))
        references = list((dotnet_root / "packs" / "Microsoft.NETCore.App.Ref").glob("8.0.*/ref/net8.0"))
        if not compilers or not references:
            self.tools.append(ToolRun(name="Roslyn / .NET 8", status="unavailable", detail="Нужен полный .NET SDK 8 с эталонными сборками net8.0"))
            return
        def version_key(path):
            return tuple(int(part) for part in re.search(r"8\.0\.(\d+)", str(path)).group(0).split("."))
        compiler = max(compilers, key=version_key)
        reference_folder = max(references, key=version_key)
        response_file = self.root / "references.rsp"
        response_file.write_text("\n".join(f'-reference:"{file}"' for file in sorted(reference_folder.glob("*.dll"))), encoding="utf-8")
        usings = self.root / "CodeScope.GlobalUsings.g.cs"
        usings.write_text("\n".join(f"global using {name};" for name in ["System", "System.Collections.Generic", "System.IO", "System.Linq", "System.Net.Http", "System.Threading", "System.Threading.Tasks"]), encoding="utf-8")
        output = self.run("Roslyn / .NET 8", ["dotnet", "exec", str(compiler), "-nologo", "-noconfig", "-nostdlib+", "-utf8output", "-nullable:enable", "-langversion:12.0", "-target:" + output_type.lower(), "-out:" + str(self.root / "Analysis.dll"), "@" + str(response_file), str(usings), *[source.name for source in self.request.files]], accepted=(0, 1))
        if not output:
            return
        matched = set()
        for match in re.finditer(r"([^\r\n/\\]+\.cs)\((\d+),(\d+)\): (error|warning) (CS\d+): (.*?)(?: \[.*?\])?$", output[0], re.M):
            key = match.groups()
            if key in matched:
                continue
            matched.add(key)
            self.add(file=match[1], line=int(match[2]), column=int(match[3]), severity=match[4],
                     rule=match[5], tool="Roslyn / .NET 8", message=match[6], help=HELP["compiler"])
        if not matched and (self.last_returncode != 0 or "error " in output[0] or "error " in output[1]):
            self.tools[-1] = ToolRun(name="Roslyn / .NET 8", status="failed", detail=(output[0] or output[1])[-1200:].replace(str(self.root), "<workspace>"))


def analyze(request: AnalysisRequest) -> dict:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="codescope-") as folder:
        engine = Analyzer(request, Path(folder))
        engine.syntax()
        getattr(engine, request.language)()
        severity_order = {"error": 0, "warning": 1, "info": 2}
        findings = sorted(engine.findings, key=lambda f: (severity_order[f.severity], f.file, f.line, f.column))
        return {"version": __version__, "language": request.language,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "duration_ms": round((time.monotonic() - started) * 1000),
                "files": [source.name for source in request.files],
                "findings": [finding.model_dump() for finding in findings],
                "tools": [tool.model_dump() for tool in engine.tools],
                "coverage": "partial" if any(tool.status != "completed" for tool in engine.tools) else "completed",
                "truncated": engine.output_truncated,
                "summary": {level: sum(f.severity == level for f in findings) for level in severity_order},
                "notice": "Статический анализ не доказывает правильность программы. Код пользователя не запускается; компиляторы могут создавать временные файлы. Внешние зависимости не устанавливаются."}
