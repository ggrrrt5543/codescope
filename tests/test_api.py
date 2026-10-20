import pytest
from fastapi.testclient import TestClient

from codescope.app import app
from codescope.models import AnalysisRequest

client = TestClient(app, base_url="http://localhost")
VALID = {"language": "python", "files": [{"name": "main.py", "content": "print(missing_name)\n"}]}


def test_api_returns_normalized_report():
    response = client.post("/api/analyze", json=VALID)
    assert response.status_code == 200
    report = response.json()
    assert report["version"] == "1.0.0"
    assert report["summary"]["error"] >= 1
    assert any(f["rule"] == "F821" and f["line"] == 1 for f in report["findings"])
    assert "content" not in report


@pytest.mark.parametrize("name", ["../secret.py", "/tmp/code.py", ".hidden.py", "--config.py", "code.py;id", "файл.py"])
def test_path_and_option_injection_rejected(name):
    response = client.post("/api/analyze", json={"language": "python", "files": [{"name": name, "content": "print(1)"}]})
    assert response.status_code == 422


def test_cross_origin_post_blocked():
    response = client.post("/api/analyze", json=VALID, headers={"Origin": "https://unrelated.example"})
    assert response.status_code == 403


def test_untrusted_host_blocked():
    response = client.get("/api/health", headers={"Host": "unrelated.example"})
    assert response.status_code == 400


def test_oversize_body_rejected():
    response = client.post("/api/analyze", content=b" " * 1_500_001, headers={"Content-Type": "application/json"})
    assert response.status_code == 413


@pytest.mark.parametrize("payload", [
    {"language": "ruby", "files": VALID["files"]},
    {"language": "python", "files": []},
    {"language": "python", "files": [{"name": "main.java", "content": "print(1)"}]},
    {"language": "python", "files": [{"name": "main.py", "content": "a" * 256001}]},
    {"language": "python", "files": [{"name": "main.py", "content": "\n" * 6001}]},
    {"language": "python", "files": [{"name": "main.py", "content": "a\x00b"}]},
    {"language": "python", "files": [{"name": "main.py", "content": "1"}, {"name": "MAIN.py", "content": "2"}]},
])
def test_invalid_requests_rejected(payload):
    with pytest.raises(ValueError):
        AnalysisRequest.model_validate(payload)


def test_bad_json_rejected_without_traceback():
    response = client.post("/api/analyze", content="{broken", headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert "traceback" not in response.text.lower()


def test_html_is_local_and_security_headers_present():
    response = client.get("/")
    assert response.status_code == 200
    assert "CodeScope" in response.text
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


@pytest.mark.parametrize("language,name,source,binary", [
    ("cpp", "main.cpp", 'int main() { int n = "bad"; return n; }', "g++"),
    ("csharp", "Example.cs", 'public class Example { public int M() { return "bad"; } }', "dotnet"),
    ("java", "Main.java", 'public class Main { int n = "bad"; }', "javac"),
])
def test_native_type_errors_survive_worker_limits(language, name, source, binary):
    import shutil
    if not shutil.which(binary):
        pytest.skip(f"{binary} is not installed")
    response = client.post("/api/analyze", json={"language": language, "files": [{"name": name, "content": source}]})
    assert response.status_code == 200
    assert response.json()["summary"]["error"] >= 1
