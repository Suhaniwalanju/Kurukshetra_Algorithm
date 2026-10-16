# Verification and Self-Healing Code Audit (VERIFICATION_AUDIT.md)

This audit inspects the active verification, sandbox execution, deprecation checking, self-healing, exercise proof, compliance QA, and reporting subsystem in the codebase. Every item quotes the exact source file and line number(s) and documents the actual value and execution behavior in the code.

---

## 1. Snippet Extraction & Persistence

### 1.1 JSON Slide Traversal & Block Extraction
- **File & Line**: [`backend/verification/extractor.py:42-49`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/extractor.py#L42-L49)
- **Actual Value / Code**:
  ```python
  for s_idx, slide in enumerate(slides):
      slide_id = slide.get("id", s_idx + 1)
      slide_type = slide.get("type", "concept")
      title = slide.get("title", "")
      code_obj = slide.get("code")

      if not code_obj or not isinstance(code_obj, dict):
          continue
  ```
- **Behavior**: Traverses the `slides` list. Skips any slide where `code` is null, missing, or not a dict. Extracts `source`, `language`, `version`, and `expected_output` from `slide["code"]`.

### 1.2 Snippet Identifier Assignment
- **File & Line**: [`backend/verification/extractor.py:68`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/extractor.py#L68)
- **Actual Value / Code**:
  ```python
  snippet_id = f"snip_{deck_id}_{slide_id}_{len(extracted) + 1}"
  ```
- **Behavior**: Assigns a deterministic identifier incorporating `deck_id`, `slide_id`, and the 1-based sequential extraction index.

### 1.3 Database Storage & Status Initialization
- **File & Line**: [`backend/verification/extractor.py:70-88`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/extractor.py#L70-L88)
- **Actual Value / Code**:
  ```python
  record = SnippetRecord(
      id=snippet_id,
      deck_id=deck_id,
      slide_id=slide_id,
      snippet_type=snippet_type,
      language=lang,
      version=version,
      source_code=source,
      expected_output=expected_output,
      status="pending",
      attempts_count=1,
  )
  if db_session:
      record = db_session.merge(record)
  ...
  if db_session:
      db_session.commit()
  ```
- **Behavior**: Instantiates and merges `SnippetRecord` into the SQLAlchemy session with initial `status="pending"` and `attempts_count=1`, then commits to SQLite/Postgres.

---

## 2. Sandbox Execution Engine (Docker & Process Isolation)

### 2.1 Pinned Image Configuration
- **File & Line**: [`backend/verification/sandbox.py:14`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L14) and [`docker/images.yaml:1-24`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/docker/images.yaml#L1-L24)
- **Actual Value / Code**:
  ```yaml
  images:
    java:
      image: "eclipse-temurin:21-jdk-alpine"
      pinned_version: "21.0.2"
    spring:
      image: "studio-runtime-java:21"
      pinned_version: "3.2.3"
    python:
      image: "python:3.12-slim"
      pinned_version: "3.12.2"
    node:
      image: "node:20-alpine"
      pinned_version: "20.11.1"
  ```
- **Behavior**: Loads `/docker/images.yaml` mapping runtime languages (`java`, `spring`, `python`, `node`) to explicit Docker tags.

### 2.2 Docker Isolation Flags & Resource Limits
- **File & Line**: [`backend/verification/sandbox.py:394-402`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L394-L402)
- **Actual Value / Code**:
  ```python
  docker_cmd = [
      self.docker_path, "run", "--rm",
      "--network", "none",
      "--memory", "512m",
      "--cpus", "1.0",
      "-v", f"{tmpdir}:/app:rw",
      "-w", "/app",
      image_name,
  ]
  ```
- **Behavior**: Invokes `docker run` with `--rm`, `--network none`, `--memory 512m`, `--cpus 1.0`, mounting an ephemeral temp directory to `/app:rw`.
- **Base Runner Docker Configuration**:
  - **File & Line**: [`backend/runtimes/base.py:177-194`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/runtimes/base.py#L177-L194)
  - **Actual Value / Code**:
    ```python
    docker_cmd = [
        self.docker_path,
        "run",
        "--rm",
        f"--network={network}",
        "--memory=512m",
        "--cpus=1.0",
        "--pids-limit=100",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "-v",
        f"{tmpdir}:/workspace:rw",
        "-w",
        "/workspace",
        "--user",
        "1001:1001",
    ]
    ```
  - **Behavior**: In plugin tracks, enforces `--read-only`, `--pids-limit=100`, `--tmpfs /tmp:rw,noexec,nosuid,size=64m`, and non-root execution (`--user 1001:1001`).

### 2.3 Execution Timeout Containment
- **File & Line**: [`backend/verification/sandbox.py:176`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L176) and [`backend/verification/sandbox.py:426-429`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L426-L429)
- **Actual Value / Code**:
  ```python
  timeout_sec: int = 20
  ...
  except subprocess.TimeoutExpired:
      result.timed_out = True
      result.exit_code = 124
      result.stderr = f"[Sandbox Timeout: Container exceeded {timeout_sec}s limit]"
  ```
- **Local Fallback Process Timeout Containment**:
  - **File & Line**: [`backend/verification/sandbox.py:275-280`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L275-L280) and [`backend/verification/sandbox.py:306-309`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L306-L309)
  - **Actual Value / Code**:
    ```python
    except subprocess.TimeoutExpired:
        result.timed_out = True
        result.exit_code = 124
        result.stderr = f"[Sandbox Timeout: Process exceeded {timeout_sec}s limit and was safely killed (contained)]"
    ```
  - **Behavior**: Subprocess enforces 20s timeout limit; raises `TimeoutExpired`, sets `exit_code=124`, `timed_out=True`, and terminates process execution.

### 2.4 Worker Pool Parallel Execution
- **File & Line**: [`backend/verification/sandbox.py:446-473`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L446-L473) and [`backend/verification/coordinator.py:140-141`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/coordinator.py#L140-L141)
- **Actual Value / Code**:
  ```python
  with ThreadPoolExecutor(max_workers=min(4, max(1, len(snip_items)))) as executor:
      run_pairs = list(executor.map(_run_one, snip_items))
  ```
- **Behavior**: Runs snippet executions concurrently using `ThreadPoolExecutor` capped at 4 worker threads.

### 2.5 Health Check Endpoint
- **File & Line**: [`backend/verification/sandbox.py:148-163`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L148-L163) and [`backend/main.py:279-284`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/main.py#L279-L284)
- **Actual Value / Code**:
  ```python
  @app.get("/api/docker/health")
  def docker_health():
      sandbox_engine.prewarm()
      health_data = sandbox_engine.get_health()
      return health_data
  ```
- **Behavior**: Exposes `GET /api/docker/health` returning `docker_available`, `docker_daemon_running`, `sandbox_mode`, `prewarmed`, `supported_images`, and `configured_limits`.

---

## 3. Automatic Code Wrapping

### 3.1 Java Class / Fragment Wrapping
- **File & Line**: [`backend/verification/sandbox.py:53-84`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L53-L84)
- **Actual Value / Code**:
  ```python
  class_match = re.search(r'public\s+class\s+([A-Za-z0-9_]+)', cleaned)
  if class_match:
      class_name = class_match.group(1)
      imports = (
          "import java.util.*;\n"
          "import java.util.stream.*;\n"
          "import java.time.*;\n"
          "import java.io.*;\n"
          "import java.util.concurrent.*;\n"
      )
      wrapped = f"{imports}\n{cleaned}"
      return wrapped, f"{class_name}.java"
  else:
      wrapped = (
          "import java.util.*;\n"
          ...
          "public class Main {\n"
          "    public static void main(String[] args) throws Exception {\n"
          f"        {cleaned}\n"
          "    }\n"
          "}\n"
      )
      return wrapped, "Main.java"
  ```
- **Behavior**: If source defines `public class <Name>`, appends standard utility imports and returns `<Name>.java`. If it is a bare fragment, wraps it inside `public class Main { public static void main(String[] args) throws Exception { ... } }` and returns `Main.java`.

### 3.2 Python Network Isolation Guard
- **File & Line**: [`backend/verification/sandbox.py:88-96`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L88-L96)
- **Actual Value / Code**:
  ```python
  network_guard = (
      "# Studio isolated sandbox --network none guard\n"
      "import socket, sys\n"
      "def _blocked_connect(*args, **kwargs):\n"
      "    raise PermissionError('[Network Access Denied: --network none enforced]')\n"
      "socket.socket.connect = _blocked_connect\n"
  )
  wrapped = f"{network_guard}\n{cleaned}\n"
  return wrapped, "main.py"
  ```
- **Behavior**: Prepends monkey-patch redirecting `socket.socket.connect` to raise `PermissionError('[Network Access Denied: --network none enforced]')` to simulate `--network none` in local process mode.

### 3.3 Node.js Network Isolation Guard
- **File & Line**: [`backend/verification/sandbox.py:98-108`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L98-L108)
- **Actual Value / Code**:
  ```python
  network_guard = (
      "// Studio isolated sandbox --network none guard\n"
      "const net = require('net');\n"
      "const originalConnect = net.Socket.prototype.connect;\n"
      "net.Socket.prototype.connect = function() {\n"
      "    throw new Error('[Network Access Denied: --network none enforced]');\n"
      "};\n"
  )
  wrapped = f"{network_guard}\n{cleaned}\n"
  return wrapped, "main.js"
  ```
- **Behavior**: Overrides `net.Socket.prototype.connect` to throw an error on outbound network access.

---

## 4. Execution Data Capture

### 4.1 Captured Metrics and Artifacts
- **File & Line**: [`backend/verification/sandbox.py:18-35`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L18-L35)
- **Actual Value / Code**:
  ```python
  @dataclass
  class ExecutionResult:
      snippet_id: str
      language: str
      version: str
      source_code: str
      wrapped_code: str
      command_executed: str
      exit_code: int = 0
      stdout: str = ""
      stderr: str = ""
      compiler_output: str = ""
      duration_ms: float = 0.0
      timed_out: bool = False
      network_blocked: bool = False
      deprecation_level: str = "none"  # "none", "warning", "removal"
      deprecation_details: str = ""
      sandbox_backend: str = "docker"  # "docker" or "isolated_process"
  ```
- **Behavior**: Captures `exit_code`, `stdout`, `stderr`, `compiler_output`, `duration_ms` (via `time.time()`), `command_executed`, `timed_out`, `network_blocked`, and `deprecation_level`.

### 4.2 Output Truncation
- **File & Line**: [`backend/runtimes/base.py:13`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/runtimes/base.py#L13) and [`backend/runtimes/base.py:144-149`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/runtimes/base.py#L144-L149)
- **Actual Value / Code**:
  ```python
  OUTPUT_SIZE_CAP_BYTES = 64 * 1024  # 64 KB output cap
  ...
  def _truncate_output(self, text: str) -> str:
      if len(text.encode("utf-8", errors="ignore")) > OUTPUT_SIZE_CAP_BYTES:
          truncated = text.encode("utf-8")[:OUTPUT_SIZE_CAP_BYTES].decode("utf-8", errors="ignore")
          return truncated + "\n... [Output truncated at 64KB cap]"
      return text
  ```
- **Behavior**: Caps console output at 64KB per execution to prevent memory overflow.

---

## 5. Deprecation Checking

### 5.1 Java Compiler Flags
- **File & Line**: [`backend/verification/sandbox.py:253`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L253) and [`backend/verification/sandbox.py:405`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L405)
- **Actual Value / Code**:
  ```python
  javac_cmd = ["javac", "-Xlint:deprecation,removal", "-encoding", "UTF-8", main_file]
  ...
  docker_cmd.extend(["sh", "-c", f"javac -Xlint:deprecation,removal {main_file} && java Main"])
  ```
- **Behavior**: Executes `javac` with `-Xlint:deprecation,removal`.

### 5.2 Java Deprecation Parsing
- **File & Line**: [`backend/verification/sandbox.py:434-444`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L434-L444)
- **Actual Value / Code**:
  ```python
  def _check_java_deprecation(self, result: ExecutionResult, compiler_out: str):
      if not compiler_out:
          return
      if "has been deprecated and marked for removal" in compiler_out:
          result.deprecation_level = "removal"
          result.deprecation_details = compiler_out
      elif "has been deprecated" in compiler_out or "[deprecation]" in compiler_out:
          result.deprecation_level = "warning"
          result.deprecation_details = compiler_out
  ```
- **Behavior**: Inspects compiler output; marks `removal` if "has been deprecated and marked for removal" is present; marks `warning` if "[deprecation]" or "has been deprecated" is present.

### 5.3 Python Deprecation Warning Enforcement
- **File & Line**: [`backend/verification/sandbox.py:313`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L313) and [`backend/verification/sandbox.py:407`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L407)
- **Actual Value / Code**:
  ```python
  result.command_executed = f"python3 -W error::DeprecationWarning {main_file}"
  ...
  docker_cmd.extend(["python3", "-W", "error::DeprecationWarning", main_file])
  ```
- **Behavior**: Executes Python with `-W error::DeprecationWarning` turning deprecation warnings into fatal exceptions.

### 5.4 Removal Deprecation Handling as Failure
- **File & Line**: [`backend/verification/output_injector.py:53-62`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/output_injector.py#L53-L62)
- **Actual Value / Code**:
  ```python
  if exec_result.exit_code == 0:
      if exec_result.deprecation_level == "removal":
          snippet.status = "failed"
          note += " (Failed: Deprecation marked for removal)"
      else:
          snippet.status = "verified"
  else:
      snippet.status = "failed"
  ```
- **Behavior**: Even if `exit_code == 0`, if `deprecation_level == "removal"`, the snippet status is forced to `failed`.

---

## 6. Real Output Injection

### 6.1 Output Mismatch Detection
- **File & Line**: [`backend/verification/output_injector.py:36-50`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/output_injector.py#L36-L50)
- **Actual Value / Code**:
  ```python
  def clean_val(v: str) -> str:
      v_clean = v.replace("Expected Output:", "").replace("Output:", "").replace("Result:", "").strip()
      return " ".join(v_clean.split())

  norm_expected = clean_val(expected)
  norm_actual = clean_val(actual)

  mismatch = False
  note = "Output matched expected output"

  if actual and norm_expected != norm_actual:
      mismatch = True
      note = f"Output Mismatch: Expected '{expected}' vs Actual '{actual}'"

  snippet.mismatch_detected = mismatch
  ```
- **Behavior**: Normalizes whitespace and prefixes ("Expected Output:", "Result:"); if normalized strings differ, sets `snippet.mismatch_detected = True` and records comparison note.

### 6.2 Injection of Actual Output into Slide
- **File & Line**: [`backend/verification/output_injector.py:64-73`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/output_injector.py#L64-L73)
- **Actual Value / Code**:
  ```python
  for slide in slides:
      if slide.get("id") == snippet.slide_id:
          if slide.get("code"):
              if actual:
                  slide["code"]["expected_output"] = actual
              elif exec_result.exit_code == 0:
                  slide["code"]["expected_output"] = "Execution successful"
          break
  ```
- **Behavior**: Overwrites `slide["code"]["expected_output"]` in memory with the actual captured `stdout`.

---

## 7. Self-Healing Loop

### 7.1 Maximum Attempts Limit
- **File & Line**: [`backend/verification/healing_loop.py:27`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/healing_loop.py#L27) and [`backend/verification/healing_loop.py:42`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/healing_loop.py#L42)
- **Actual Value / Code**:
  ```python
  max_attempts: int = 4
  ...
  for attempt in range(1, max_attempts + 1):
      snippet.attempts_count = attempt + 1
  ```
- **Behavior**: Loops up to 4 attempts (`range(1, 5)`).

### 7.2 LLM Fix Prompt Structure
- **File & Line**: [`backend/verification/healing_loop.py:128-140`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/healing_loop.py#L128-L140)
- **Actual Value / Code**:
  ```python
  system_prompt = (
      "You are an expert compiler and software debugger. Fix the provided code snippet so that it compiles and "
      "executes cleanly with 0 errors. Return ONLY the raw corrected code with NO markdown code blocks, NO explanations."
  )
  user_prompt = f"""Language: {language} (Version: {version})
  Original Code:
  {source_code}

  Error Log:
  {error_log}

  Fix all syntax errors, missing imports, unhandled exceptions, or deprecation removals.
  Return ONLY the corrected runnable code snippet (maximum 12 lines):"""
  ```
- **Behavior**: Sends the language, pinned version, original code, and exact compiler/runtime error log to Ollama (`llm_generator._call_ollama`).

### 7.3 Unified Diff Generation
- **File & Line**: [`backend/verification/healing_loop.py:196-208`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/healing_loop.py#L196-L208)
- **Actual Value / Code**:
  ```python
  def _compute_diff(self, old_code: str, new_code: str, snippet_id: str, attempt: int) -> str:
      old_lines = [l + "\n" for l in old_code.split("\n")]
      new_lines = [l + "\n" for l in new_code.split("\n")]
      diff_lines = list(
          difflib.unified_diff(
              old_lines,
              new_lines,
              fromfile=f"before_attempt_{attempt}_{snippet_id}.code",
              tofile=f"after_attempt_{attempt}_{snippet_id}.code",
          )
      )
      return "".join(diff_lines)
  ```
- **Behavior**: Computes a standard unified diff string using Python's `difflib.unified_diff` comparing before and after code for each healing attempt.

### 7.4 Healing Log Record Persistence
- **File & Line**: [`backend/verification/healing_loop.py:68-83`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/healing_loop.py#L68-L83)
- **Actual Value / Code**:
  ```python
  log_rec = HealingLogRecord(
      id=str(uuid.uuid4())[:12],
      snippet_id=snippet.id,
      deck_id=snippet.deck_id,
      attempt_number=attempt,
      error_type="compile_or_runtime_error" if new_result.exit_code != 0 else "deprecation_removal",
      error_log=last_error,
      original_code=current_code,
      fixed_code=fixed_code,
      diff=diff_text,
      success=is_success,
  )
  healing_logs.append(log_rec)
  if db_session:
      db_session.add(log_rec)
      db_session.commit()
  ```
- **Behavior**: Records each attempt in the `healing_logs` database table with attempt number, error log, original code, fixed code, diff text, and boolean success.

### 7.5 Status on Success vs Exhaustion
- **File & Line**: [`backend/verification/healing_loop.py:87`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/healing_loop.py#L87) and [`backend/verification/healing_loop.py:113`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/healing_loop.py#L113)
- **Actual Value / Code**:
  ```python
  if is_success:
      snippet.status = "auto_healed"
  ...
  # Failed after max_attempts
  snippet.status = "needs_review"
  ```
- **Behavior**: On successful compilation/execution, status becomes `"auto_healed"`. If all 4 attempts fail, status becomes `"needs_review"`.

### 7.6 Post-Healing Slide Re-Layout
- **File & Line**: [`backend/verification/healing_loop.py:101`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/healing_loop.py#L101) and [`backend/verification/healing_loop.py:210-227`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/healing_loop.py#L210-L227)
- **Actual Value / Code**:
  ```python
  self._re_layout_slide(slide, config, professor_name)
  ...
  def _re_layout_slide(self, slide_dict: Dict[str, Any], config: TemplateLayoutConfig, professor_name: str):
      slide_obj = Slide(...)
      plan = layout_engine.layout_single_slide(slide_obj, config, professor_name)
      if plan.violations:
          print(f"Slide {slide_obj.id} post-healing layout warning: {plan.violations}")
  ```
- **Behavior**: When code is modified by healing, re-invokes `layout_engine.layout_single_slide` on that slide to recompute bounding boxes and verify safe-zone containment.

### 7.7 Heuristic Fallback
- **File & Line**: [`backend/verification/healing_loop.py:185-194`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/healing_loop.py#L185-L194)
- **Actual Value / Code**:
  ```python
  def _heuristic_fix(self, language: str, source: str, error_log: str) -> str:
      fixed = source
      err_lower = error_log.lower()
      if "';' expected" in error_log or "expected ';'" in err_lower or "semicolon" in err_lower or ("java" in language.lower() and not source.strip().endswith((";", "}"))):
          lines = [l + ";" if l.strip() and not l.strip().endswith((";", "{", "}", ":")) else l for l in fixed.split("\n")]
          fixed = "\n".join(lines)
      if "cannot find symbol" in error_log and "println" in source and "System.out.println" not in source:
          fixed = fixed.replace("println", "System.out.println")
      return fixed
  ```
- **Behavior**: Deterministic syntax healer fixing missing semicolons or bare `println` to `System.out.println` if LLM is unavailable or returns unparseable output.

---

## 8. Exercise Prover & Mutation Testing

### 8.1 Reference Solution Pass Enforcement
- **File & Line**: [`backend/verification/exercise_prover.py:40-48`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/exercise_prover.py#L40-L48)
- **Actual Value / Code**:
  ```python
  ref_code = self._combine_test_and_solution(language, suite["test_code"], suite["reference_solution"])
  ref_res = sandbox_engine.run_snippet(
      snippet_id=f"ex_{deck_id}_{slide_id}_ref",
      language=language,
      source_code=ref_code,
      version=version,
  )
  ref_passed = ref_res.exit_code == 0
  ```
- **Behavior**: Compiles and runs `reference_solution` with `test_code`; asserts `exit_code == 0`.

### 8.2 Naive Solution Failure Enforcement & Test Strengthening
- **File & Line**: [`backend/verification/exercise_prover.py:62-84`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/exercise_prover.py#L62-L84)
- **Actual Value / Code**:
  ```python
  naive_code = self._combine_test_and_solution(language, suite["test_code"], suite["naive_solution"])
  naive_res = sandbox_engine.run_snippet(...)
  naive_failed = naive_res.exit_code != 0

  attempts = 0
  while not naive_failed and attempts < 3:
      attempts += 1
      suite["test_code"] = self._strengthen_tests(language, suite["test_code"], suite["naive_solution"])
      naive_code = self._combine_test_and_solution(language, suite["test_code"], suite["naive_solution"])
      naive_res = sandbox_engine.run_snippet(...)
      naive_failed = naive_res.exit_code != 0
  ```
- **Behavior**: Executes `naive_solution` against the test suite; if naive passes (`exit_code == 0`), strengthens test suite assertions up to 3 times until naive fails (`exit_code != 0`).

### 8.3 Mutant Generation & Mutation Score
- **File & Line**: [`backend/verification/exercise_prover.py:86-117`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/exercise_prover.py#L86-L117) and [`backend/verification/exercise_prover.py:237-289`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/exercise_prover.py#L237-L289)
- **Actual Value / Code**:
  ```python
  mutants = self._generate_mutants(language, suite["reference_solution"])
  ...
  # 6 distinct mutants generated:
  # 1. Off-by-one initial state (sum = 1)
  # 2. Operator flip (sum -= n)
  # 3. Faulty null injection (nums == null return -999)
  # 4. Early loop break
  # 5. Constant return (return 0)
  # 6. Negated return value (return -sum)
  ...
  for idx, mutant in enumerate(mutants):
      ...
      is_killed = m_res.exit_code != 0
      if is_killed:
          killed_count += 1
  ...
  total_mutants = max(1, len(mutants))
  mutation_score = round((killed_count / total_mutants) * 100, 1)
  ```
- **Behavior**: Generates 6 syntactically altered mutants of the reference solution; runs each against the test suite; increments `killed_count` when tests fail; computes `mutation_score = (killed_count / total_mutants) * 100`.

### 8.4 Pass/Fail Matrix Generation
- **File & Line**: [`backend/verification/exercise_prover.py:89-114`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/exercise_prover.py#L89-L114)
- **Actual Value / Code**:
  ```python
  matrix = {
      "reference": {"status": "PASS" if ref_passed else "FAIL", "expected": "PASS", "score": 1.0 if ref_passed else 0.0},
      "naive": {"status": "FAIL" if naive_failed else "PASS", "expected": "FAIL", "score": 1.0 if naive_failed else 0.0},
      "mutants": [
          {
              "id": f"Mutant-{idx + 1}",
              "name": mutant["name"],
              "description": mutant["description"],
              "status": "KILLED (FAIL)" if is_killed else "SURVIVED (PASS)",
              "killed": is_killed,
          }
      ],
  }
  ```
- **Behavior**: Constructs JSON object containing pass/fail statuses for Reference, Naive, and all Mutants, serialized to `matrix_json` on `ExerciseProofRecord`.

---

## 9. Non-Code Content Reviewer

### 9.1 Bullet Limit Enforcement ($\le 5$ Bullets)
- **File & Line**: [`backend/verification/content_reviewer.py:40-51`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/content_reviewer.py#L40-L51)
- **Actual Value / Code**:
  ```python
  if len(bullets) > 5:
      findings.append({
          "slide_id": s_id,
          "slide_title": title,
          "type": "bullet_count_overflow",
          "severity": "low",
          "message": f"Slide has {len(bullets)} bullets (limit: 5). Auto-trimmed.",
          "auto_fixed": True,
      })
      slide["bullets"] = bullets[:5]
      bullets = slide["bullets"]
      auto_fixed_count += 1
  ```
- **Behavior**: If bullets count exceeds 5, logs a `low` severity finding with `auto_fixed=True` and slices `slide["bullets"] = bullets[:5]`.

### 9.2 Word Limit Enforcement ($\le 8$ Words per Bullet)
- **File & Line**: [`backend/verification/content_reviewer.py:53-66`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/content_reviewer.py#L53-L66)
- **Actual Value / Code**:
  ```python
  for b_idx, bullet in enumerate(bullets):
      words = bullet.strip().split()
      if len(words) > 8:
          trimmed = " ".join(words[:8])
          findings.append({
              "slide_id": s_id,
              "slide_title": title,
              "type": "bullet_word_limit",
              "severity": "low",
              "message": f"Bullet '{bullet}' exceeded 8 words ({len(words)} words). Trimmed to '{trimmed}'.",
              "auto_fixed": True,
          })
          slide["bullets"][b_idx] = trimmed
          auto_fixed_count += 1
  ```
- **Behavior**: If any bullet contains more than 8 words, trims it to the first 8 words and records `auto_fixed=True`.

### 9.3 Code Consistency & Pinned Version Factual Check
- **File & Line**: [`backend/verification/content_reviewer.py:68-92`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/content_reviewer.py#L68-L92)
- **Actual Value / Code**:
  ```python
  if code_src:
      if "VirtualThread" in code_src and "thread pool" in " ".join(bullets).lower():
          findings.append({
              "type": "code_text_inconsistency",
              "severity": "medium",
              ...
          })
  ...
  if "java" in tech.lower() and version in ["21", "21-jdk"]:
      if "applet" in combined_text or "security manager" in combined_text:
          findings.append({
              "type": "deprecated_concept_claimed",
              "severity": "high",
              ...
          })
  ```
- **Behavior**: Flags inconsistencies (e.g. Virtual Threads vs Thread Pools) as `medium` severity, and claims of deprecated APIs (e.g. Java Applets/Security Manager in Java 21) as `high` severity.

---

## 10. Template Compliance QA

### 10.1 Minimum Font Size Check
- **File & Line**: [`backend/verification/template_qa.py:44-55`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/template_qa.py#L44-L55) and [`backend/layout_engine.py:32-33`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/layout_engine.py#L32-L33)
- **Actual Value / Code**:
  ```python
  BODY_FONT_MIN = 24
  CODE_FONT_MIN = 18
  ...
  if slide.type != "cover" and body_font < BODY_FONT_MIN:
      violations.append(f"Body font size ({body_font}pt) below minimum allowed ({BODY_FONT_MIN}pt)")
      slide_passed = False

  if slide.code and code_font < CODE_FONT_MIN:
      violations.append(f"Code font size ({code_font}pt) below minimum allowed ({CODE_FONT_MIN}pt)")
      slide_passed = False
  ```
- **Behavior**: Asserts body text is at least 24pt and code is at least 18pt (downscaling allows down to 14pt in layout engine if lines overflow).

### 10.2 Bounding Box Intersections & Gutter
- **File & Line**: [`backend/verification/template_qa.py:57-64`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/template_qa.py#L57-L64) and [`backend/layout_engine.py:31`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/layout_engine.py#L31)
- **Actual Value / Code**:
  ```python
  MIN_GUTTER_PX = 19  # ~0.2 inches at 96 DPI
  ...
  boxes = plan.elements
  for i in range(len(boxes)):
      for j in range(i + 1, len(boxes)):
          b1 = boxes[i]
          b2 = boxes[j]
          if b1.intersects(b2, gutter=MIN_GUTTER_PX):
              violations.append(f"Overlap between {b1.id_str} and {b2.id_str} (gutter < {MIN_GUTTER_PX}px)")
              slide_passed = False
  ```
- **Behavior**: Tests all pairs of element boxes for intersection with minimum 19px (0.2 inch) gutter separation.

### 10.3 Safe Zone Containment
- **File & Line**: [`backend/verification/template_qa.py:66-80`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/template_qa.py#L66-L80)
- **Actual Value / Code**:
  ```python
  for b in boxes:
      if b.element_type == "title" and not b.is_inside(config.title_zone):
          violations.append("Title box extends outside Title Zone")
      elif b.element_type == "presented_by" and not b.is_inside(config.presented_by_zone):
          violations.append("Presented By box extends outside Presented By Zone")
      elif b.element_type == "footer" and not b.is_inside(config.footer_zone):
          violations.append("Footer extends outside Footer Zone")
      elif b.element_type in ["bullets", "code", "diagram"]:
          if b.bottom > config.content_zone.bottom + 5:
              violations.append(...)
  ```
- **Behavior**: Validates that all boxes reside strictly within designated template zones (`title_zone`, `presented_by_zone`, `footer_zone`, `content_zone`).

### 10.4 "Presented By" on Cover Slide Only
- **File & Line**: [`backend/verification/template_qa.py:82-87`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/template_qa.py#L82-L87)
- **Actual Value / Code**:
  ```python
  if slide.type == "cover":
      has_pres = any(b.element_type == "presented_by" for b in boxes)
      if not has_pres:
          violations.append("Cover slide is missing 'Presented By' author attribution box")
          slide_passed = False
  ```
- **Behavior**: Asserts that `presented_by` box is present on the cover slide. Stripped from content and closing slides.

### 10.5 Failure Annotated Image
- **File & Line**: [`backend/verification/template_qa.py:115-134`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/template_qa.py#L115-L134)
- **Actual Value / Code**:
  ```python
  def _annotate_failure(self, orig_path: str, boxes: List[ElementBox], violations: List[str], output_path: str):
      ...
      for b in boxes:
          draw.rectangle([b.left, b.top, b.right, b.bottom], outline=(239, 68, 68, 255), width=4)
      draw.rectangle([0, 0, img.width, 40], fill=(239, 68, 68, 220))
      banner_text = f"QA FAILED: {violations[0] if violations else 'Layout boundary breach'}"
      draw.text((20, 10), banner_text, fill=(255, 255, 255, 255))
      ...
  ```
- **Behavior**: When QA detects layout violations, opens the slide PNG, draws red 4px boundary boxes and a top red alert banner, saving `slide_{id}_qa_failed.png`.

---

## 11. Verification Badge & Reports

### 11.1 Footer Verification Badge
- **File & Line**: [`backend/verification/coordinator.py:221-224`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/coordinator.py#L221-L224)
- **Actual Value / Code**:
  ```python
  date_str = datetime.now().strftime("%Y-%m-%d")
  badge_text = f"Verified ✔ Ran on {tech} {version} · {date_str}"
  for s in slides_data:
      s["verification_badge"] = badge_text
  ```
- **PPTX Builder Implementation**: [`backend/pptx_builder.py:341-353`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/pptx_builder.py#L341-L353)
- **Slide Renderer Implementation**: [`backend/slide_renderer.py:175-185`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/slide_renderer.py#L175-L185)
- **Behavior**: Renders emerald/slate badge pill `Verified ✔ Ran on <tech> <version> · <YYYY-MM-DD>` inside the footer zone without collision.

### 11.2 Verification Report Generation (HTML & PDF)
- **HTML Generator**: [`backend/verification/report_generator.py:34-211`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/report_generator.py#L34-L211)
  - Produces standalone HTML report with summary cards (Total, Verified, Auto-Healed, Needs Review, Mutation Score, Compliance), per-slide execution details, command strings, stderr, and before/after unified diffs.
- **PDF Generator**: [`backend/verification/report_generator.py:213-397`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/report_generator.py#L213-L397)
  - Uses `reportlab.platypus` (`SimpleDocTemplate`, `Table`, `Paragraph`, `colors`) to compile official PDF report.

---

## 12. Verification API Endpoints

### 12.1 POST /api/decks/{deck_id}/verify
- **File & Line**: [`backend/main.py:287-308`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/main.py#L287-L308)
- **Behavior**: Triggers background task invoking `verification_coordinator.verify_deck(deck_id, session)`.

### 12.2 GET /api/decks/{deck_id}/verify/stream (SSE)
- **File & Line**: [`backend/main.py:311-339`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/main.py#L311-L339)
- **Behavior**: Returns `StreamingResponse` with `text/event-stream` yielding JSON progress events (`start`, `extracting`, `executing`, `healing`, `proving_exercise`, `reviewing_content`, `template_qa`, `generating_reports`, `completed`).

### 12.3 GET /api/decks/{deck_id}/report
- **File & Line**: [`backend/main.py:342-384`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/main.py#L342-L384)
- **Behavior**: Returns comprehensive verification JSON payload with all snippets, runs, healing logs, exercise proofs, and content reviews.

### 12.4 GET /api/decks/{deck_id}/report/html & /pdf
- **File & Line**: [`backend/main.py:386-413`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/main.py#L386-L413)
- **Behavior**: Returns `FileResponse` for `verification_report.html` and `verification_report.pdf`.

---

## 13. Audit Summary Table

| Requirement / Component | File & Line | Status | Actual Value / Implementation |
| :--- | :--- | :--- | :--- |
| **Snippet Extraction** | [`backend/verification/extractor.py:26-90`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/extractor.py#L26-L90) | IMPLEMENTED | Traverses `slides` JSON; creates `SnippetRecord` with `status="pending"`, assigns `snip_{deck_id}_{slide_id}_{idx}` |
| **Docker Images YAML** | [`docker/images.yaml:1-24`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/docker/images.yaml#L1-L24) | IMPLEMENTED | Pinned configs for `java`, `spring`, `python`, `node` |
| **Sandbox Network None** | [`backend/verification/sandbox.py:396`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L396) | IMPLEMENTED | `--network none` in Docker; socket connect monkey-patch in local fallback |
| **Sandbox Timeout** | [`backend/verification/sandbox.py:176`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L176) | IMPLEMENTED | `timeout_sec: int = 20`, kills runaway processes with `exit_code = 124` |
| **Memory & CPU Limits** | [`backend/verification/sandbox.py:397-398`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L397-L398) | IMPLEMENTED | `--memory 512m`, `--cpus 1.0` |
| **Read-Only Root FS** | [`backend/runtimes/base.py:185-187`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/runtimes/base.py#L185-L187) | IMPLEMENTED | `--read-only`, `--tmpfs /tmp:rw,noexec,nosuid,size=64m` |
| **Non-Root Runner** | [`backend/runtimes/base.py:193`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/runtimes/base.py#L193) | IMPLEMENTED | `--user 1001:1001` |
| **Java Code Wrapper** | [`backend/verification/sandbox.py:48-84`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L48-L84) | IMPLEMENTED | Detects existing class or wraps in `public class Main { public static void main(String[] args)... }` |
| **Output Truncation** | [`backend/runtimes/base.py:13`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/runtimes/base.py#L13) | IMPLEMENTED | 64 KB cap via `_truncate_output` |
| **Real Output Injection** | [`backend/verification/output_injector.py:63-73`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/output_injector.py#L63-L73) | IMPLEMENTED | Replaces `slide["code"]["expected_output"]` with captured stdout |
| **Deprecation Java** | [`backend/verification/sandbox.py:253`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L253) | IMPLEMENTED | `javac -Xlint:deprecation,removal` |
| **Deprecation Python** | [`backend/verification/sandbox.py:313`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/sandbox.py#L313) | IMPLEMENTED | `python3 -W error::DeprecationWarning` |
| **Removal Deprecation Fatal** | [`backend/verification/output_injector.py:54-56`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/output_injector.py#L54-L56) | IMPLEMENTED | Marks `snippet.status = "failed"` if `deprecation_level == "removal"` |
| **Self-Healing Loop** | [`backend/verification/healing_loop.py:42-117`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/healing_loop.py#L42-L117) | IMPLEMENTED | Max 4 attempts, calls LLM, re-verifies in sandbox, marks `needs_review` on failure |
| **Unified Diff Logging** | [`backend/verification/healing_loop.py:196-208`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/healing_loop.py#L196-L208) | IMPLEMENTED | `difflib.unified_diff` saved in `HealingLogRecord.diff` |
| **Post-Healing Re-Layout** | [`backend/verification/healing_loop.py:101`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/healing_loop.py#L101) | IMPLEMENTED | Calls `layout_engine.layout_single_slide` on modified slide |
| **Exercise Prover** | [`backend/verification/exercise_prover.py:23-141`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/exercise_prover.py#L23-L141) | IMPLEMENTED | Reference passes, naive fails, up to 3 test strengthening retries |
| **Mutation Testing** | [`backend/verification/exercise_prover.py:86-117`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/exercise_prover.py#L86-L117) | IMPLEMENTED | 6 buggy mutants; computes `(killed / total) * 100` |
| **Non-Code Content Review** | [`backend/verification/content_reviewer.py:21-109`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/content_reviewer.py#L21-L109) | IMPLEMENTED | Auto-trims bullets $> 5$ or words $> 8$; checks code consistency |
| **Template Collision QA** | [`backend/verification/template_qa.py:57-64`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/template_qa.py#L57-L64) | IMPLEMENTED | Bounding-box intersection test with 19px (0.2") gutter |
| **Annotated Failure PNG** | [`backend/verification/template_qa.py:115-134`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/template_qa.py#L115-L134) | IMPLEMENTED | Draws red boxes and alert banner on failed slide image |
| **Verification Badge** | [`backend/verification/coordinator.py:221-224`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/verification/coordinator.py#L221-L224) | IMPLEMENTED | `Verified ✔ Ran on <tech> <version> · <YYYY-MM-DD>` rendered in footer |
| **HTML Report Download** | [`backend/main.py:386-399`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/main.py#L386-L399) | IMPLEMENTED | `GET /api/decks/{deck_id}/report/html` |
| **PDF Report Download** | [`backend/main.py:401-414`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/main.py#L401-L414) | IMPLEMENTED | `GET /api/decks/{deck_id}/report/pdf` (ReportLab) |
| **Realtime SSE Stream** | [`backend/main.py:311-339`](file:///c:/Users/SAMRUDDHI%20KHADE/OneDrive%20-%20Vidyalankar%20Institute%20of%20Technology/Desktop/Kurukshetra_dpu/backend/main.py#L311-L339) | IMPLEMENTED | `GET /api/decks/{deck_id}/verify/stream` |
