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
            raise ValueError("Use a plain ASCII filename, without folders or spaces")
        if name.startswith((".", "-")) or PurePosixPath(name).name != name:
            raise ValueError("Hidden files, options and paths are not accepted")
        return name

    @field_validator("content")
    @classmethod
    def bounded_source(cls, content: str) -> str:
        if "\x00" in content or len(content.encode("utf-8")) > MAX_FILE_BYTES or len(content.splitlines()) > 6000:
            raise ValueError("Source must be UTF-8 text, at most 256 KB / 6000 lines, without NUL bytes")
        return content


class AnalysisRequest(BaseModel):
    language: Language
    files: list[SourceFile] = Field(min_length=1, max_length=MAX_FILES)

    @model_validator(mode="after")
    def validate_project(self):
        names = [source.name.lower() for source in self.files]
        if len(set(names)) != len(names):
            raise ValueError("Duplicate filenames are not accepted")
        if sum(len(source.content.encode()) for source in self.files) > MAX_TOTAL_BYTES:
            raise ValueError("Combined source must not exceed 1 MB")
        if any(PurePosixPath(source.name).suffix not in EXTENSIONS[self.language] for source in self.files):
            raise ValueError("File extension does not match the selected language")
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
