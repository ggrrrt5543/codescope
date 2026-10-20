import shutil
from pathlib import Path

import pytest

from codescope.engine import Analyzer, analyze
from codescope.models import AnalysisRequest


def request(language, name, content):
    return AnalysisRequest(language=language, files=[{"name": name, "content": content}])


@pytest.mark.parametrize("language,name,source", [
    ("python", "main.py", "if True\n    print(1)"),
    ("cpp", "main.cpp", "int main( { return 0; }"),
    ("csharp", "Example.cs", "public class Example { public int M( { return 1; } }"),
    ("java", "Main.java", "public class Main { int f( { return 1; } }"),
])
def test_syntax_errors_have_locations(language, name, source, tmp_path):
    engine = Analyzer(request(language, name, source), tmp_path)
    engine.syntax()
    assert engine.findings
    assert all(finding.line >= 1 and finding.column >= 1 and finding.file == name for finding in engine.findings)


@pytest.mark.parametrize("language,name,source", [
    ("python", "main.py", "answer: int = 42\nprint(answer)\n"),
    ("cpp", "main.cpp", 'int main() { return 0; }\n'),
    ("csharp", "Example.cs", "public class Example { public int Count() { return 5; } }"),
    ("java", "Main.java", "public class Main { public static void main(String[] args) {} }"),
])
def test_valid_syntax_is_not_reported_as_broken(language, name, source, tmp_path):
    engine = Analyzer(request(language, name, source), tmp_path)
    engine.syntax()
    assert not engine.findings


@pytest.mark.parametrize("language,name,source,tool,binary", [
    ("python", "main.py", 'age = input("Age: ")\nprint(age + 5)\n', "Pyright", "pyright"),
    ("cpp", "main.cpp", 'int main() { int count = "five"; return count; }', "G++", "g++"),
    ("csharp", "Example.cs", 'public class Example { public int Count() { return "five"; } }', "Roslyn / .NET 8", "dotnet"),
    ("java", "Main.java", 'public class Main { int count = "five"; }', "Javac", "javac"),
])
def test_semantic_type_errors_are_detected(language, name, source, tool, binary):
    import sys
    if not (shutil.which(binary) or (Path(sys.executable).parent / binary).exists()):
        pytest.skip(f"{binary} is not installed")
    report = analyze(request(language, name, source))
    assert any(finding["tool"] == tool and finding["severity"] == "error" for finding in report["findings"]), str(report["tools"])
    assert any(run["name"] == tool and run["status"] == "completed" for run in report["tools"])


def test_missing_tools_produce_partial_coverage(monkeypatch):
    monkeypatch.setattr(Analyzer, "run", lambda self, name, command, accepted=(0, 1): self.tools.append(__import__('codescope.models', fromlist=['ToolRun']).ToolRun(name=name, status="unavailable")))
    report = analyze(request("java", "Main.java", "public class Main {}"))
    assert report["coverage"] == "partial"
    assert report["summary"]["error"] == 0


def test_source_is_not_executed(tmp_path):
    marker = tmp_path / "should-not-exist"
    analyze(request("python", "main.py", f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\nraise SystemExit(9)\n"))
    assert not marker.exists()


def test_unicode_error_column_is_character_based(tmp_path):
    engine = Analyzer(request("java", "Main.java", 'class Main { String текст = "ok"; @@@ }'), tmp_path)
    engine.syntax()
    assert engine.findings
    assert all(finding.column <= 50 for finding in engine.findings)


def test_csharp_top_level_program_is_not_misclassified_as_library():
    if not shutil.which("dotnet"):
        pytest.skip("dotnet is not installed")
    report = analyze(request("csharp", "Program.cs", 'System.Console.WriteLine("Hello");'))
    assert report["summary"]["error"] == 0
    assert report["coverage"] == "completed"
