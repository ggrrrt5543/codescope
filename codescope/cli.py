import argparse
import json
from pathlib import Path

from . import __version__


def main():
    parser = argparse.ArgumentParser(description="CodeScope — локальная статическая проверка кода")
    parser.add_argument("--version", action="version", version=__version__)
    subcommands = parser.add_subparsers(dest="command")
    serve = subcommands.add_parser("serve", help="Запустить локальное веб-приложение")
    serve.add_argument("--port", type=int, default=8765)
    check = subcommands.add_parser("check", help="Проверить исходные файлы и вывести JSON-отчёт")
    check.add_argument("--language", required=True, choices=["python", "cpp", "csharp", "java"])
    check.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    if args.command == "check":
        from pydantic import ValidationError
        from .models import AnalysisRequest
        from .app import analyze_isolated
        from fastapi import HTTPException
        try:
            payload = AnalysisRequest(language=args.language, files=[{"name": p.name, "content": p.read_text(encoding="utf-8")} for p in args.files])
            report = analyze_isolated(payload)
        except (OSError, UnicodeError, ValidationError, HTTPException) as exc:
            parser.exit(2, f"Проверка не выполнена: {getattr(exc, 'detail', str(exc))}\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(2 if report["coverage"] == "partial" else 1 if report["summary"]["error"] else 0)
    if args.command not in (None, "serve"):
        parser.error("Неизвестная команда")
    import uvicorn
    print("CodeScope: http://127.0.0.1:%s — для остановки нажми Ctrl+C" % getattr(args, "port", 8765))
    uvicorn.run("codescope.app:app", host="127.0.0.1", port=getattr(args, "port", 8765))


if __name__ == "__main__":
    main()
