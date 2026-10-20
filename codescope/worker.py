import json
import os
import sys


def main():
    if os.name == "posix":
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (75, 75))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    from .engine import analyze
    from .models import AnalysisRequest
    request = AnalysisRequest.model_validate_json(sys.stdin.read(2_000_001))
    print(json.dumps(analyze(request), ensure_ascii=False))


if __name__ == "__main__":
    main()
