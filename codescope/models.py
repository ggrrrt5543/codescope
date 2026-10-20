from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Language = Literal["python", "cpp", "csharp", "java"]
MAX_FILES = 12
MAX_FILE_BYTES = 256_000
MAX_TOTAL_BYTES = 1_000_000
EXTENSIONS = {"python": {".py"}, "cpp": {".cpp", ".cc", ".cxx", ".h", ".hpp"},
              "csharp": {".cs"}, "java": {".java"}}


class SourceFile(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    content: str = Field(max_length=MAX_FILE_BYTES)

    @field_validator("name")
    @classmethod
    def safe_name(cls, name: str) -> str:
        if not name.isascii() or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for c in name):
            raise ValueError("Используй простое имя файла латиницей, без папок и пробелов")
        if name.startswith((".", "-")) or PurePosixPath(name).name != name:
            raise ValueError("Скрытые файлы, параметры и пути не принимаются")
        return name

    @field_validator("content")
    @classmethod
    def bounded_source(cls, content: str) -> str:
        if "\x00" in content or len(content.encode("utf-8")) > MAX_FILE_BYTES or len(content.splitlines()) > 6000:
            raise ValueError("Нужен текст UTF-8: до 256 КБ / 6000 строк, без нулевых байтов")
        return content


class AnalysisRequest(BaseModel):
    language: Language
    files: list[SourceFile] = Field(min_length=1, max_length=MAX_FILES)

    @model_validator(mode="after")
    def validate_project(self):
        names = [source.name.lower() for source in self.files]
        if len(set(names)) != len(names):
            raise ValueError("Имена файлов не должны повторяться")
        if sum(len(source.content.encode()) for source in self.files) > MAX_TOTAL_BYTES:
            raise ValueError("Суммарный размер исходников не должен превышать 1 МБ")
        if any(PurePosixPath(source.name).suffix not in EXTENSIONS[self.language] for source in self.files):
            raise ValueError("Расширение файла не соответствует выбранному языку")
        return self


class Finding(BaseModel):
    file: str
    line: int = Field(ge=1)
    column: int = Field(default=1, ge=1)
    severity: Literal["error", "warning", "info"]
    rule: str
    tool: str
    message: str
    help: str


class ToolRun(BaseModel):
    name: str
    status: Literal["completed", "unavailable", "failed", "timeout"]
    detail: str = ""
