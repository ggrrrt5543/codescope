# Security model

CodeScope v1.0.0 is a **local development utility, not a hardened multi-tenant sandbox**.

- Source programs are not executed. Python is parsed and analyzed; C++ uses syntax-only compilation; Java and C# compilation can create temporary bytecode/assemblies, which are never run.
- Filenames are plain ASCII basenames, extension-checked, case-insensitively unique. No archive extraction, uploaded projects, build scripts, packages or user-supplied compiler flags.
- Java annotation processing is disabled. C# uses a generated project with no NuGet sources and no uploaded MSBuild files; third-party analyzers are disabled.
- Requests: 12 files, 256 KB / 6000 lines each, 1 MB combined source, 1.5 MB HTTP body. Two worker slots; 18 seconds per tool, 85 seconds per request. Linux/macOS workers limit CPU and file descriptors. Temporary disk usage is not capped on the host; use a bounded container tmpfs for untrusted inputs. Process groups are terminated on timeout on POSIX. Windows does not provide equivalent process-tree isolation here.
- App binds to loopback, accepts localhost/127.0.0.1 hosts, rejects cross-origin POST requests and does not enable CORS. It has **no authentication**. Do not expose it to the Internet or a shared LAN.
- The UI keeps source in memory, not localStorage. Only the theme preference is stored. Reports omit full source, but diagnostic messages may quote fragments of it. Treat reports as potentially sensitive.
- Temporary source folders are removed after analysis. Compiler/SDK caches can remain in tool-specific directories. No telemetry is added by CodeScope; external tools may have their own policies. Pyright may need a one-time Node runtime setup if Node.js is missing. Install Node.js first for predictable offline analysis.
- Compilers/parsers are complex native programs and may have vulnerabilities. Includes can read accessible host files; generated code and diagnostics may expose environment details. **Do not analyze untrusted submissions directly on the host.**

## Recommended container boundary

Build the full-toolchain image, then run without host mounts or network:

```sh
docker build -t codescope:1.0.0 .
docker run --rm -p 127.0.0.1:8765:8765 --network bridge \
  --memory 2g --cpus 2 --pids-limit 128 --cap-drop ALL \
  --security-opt no-new-privileges --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=512m codescope:1.0.0
```

The loopback port mapping requires networking; the default bridge **still allows outbound traffic**. For hostile code, use a dedicated VM or isolated host and deny container egress at the firewall. `--network none` prevents browser access to this server, so it is not a substitute in the command above. Do not mount personal directories or secrets. A container reduces risk but does not prove isolation.

Report vulnerabilities privately using the maintainer contact options in the GitHub profile; do not publish live credentials in an issue. No private reporting channel has been configured by this repository automatically.
