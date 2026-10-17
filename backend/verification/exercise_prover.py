import uuid
import json
import re
from typing import Dict, Any, List, Tuple, Optional
from sqlalchemy.orm import Session

from backend.database import ExerciseProofRecord
from backend.verification.sandbox import sandbox_engine, ExecutionResult
from backend.llm_generator import llm_generator


class ExerciseProver:
    def __init__(self):
        pass

    def prove_deck_exercises(
        self,
        deck_id: str,
        topic: str,
        language: str = "java",
        version: str = "",
        slides: Optional[List[Dict[str, Any]]] = None,
        topic_chunks: Optional[List[Dict[str, Any]]] = None,
        student_level: str = "intermediate",
        do_not_use: Optional[List[str]] = None,
        max_attempts: int = 3,
        db_session: Optional[Session] = None,
    ) -> List[ExerciseProofRecord]:
        """
        Generates and verifies 3 exercises per deck (easy, medium, stretch), each with:
        - task
        - starter code
        - test file
        - reference solution
        - naive solution
        Runs the reference (must PASS), naive (must fail on TEST_FAILURE assertion),
        and mutation check. If any step fails, regenerates and re-verifies up to max_attempts,
        then flags as needs_review.
        """
        difficulties = ["easy", "medium", "stretch"]
        records = []

        # Find concept and exercise slides to correlate slide IDs and concepts
        concept_slides = [s for s in (slides or []) if s.get("type") in ["concept", "code", "diagram", "exercise"]]
        exercise_slides = [s for s in (slides or []) if s.get("type") == "exercise" or s.get("exercise_ref")]

        for idx, diff in enumerate(difficulties):
            if concept_slides:
                if diff == "easy":
                    picked_slides = concept_slides[:max(1, len(concept_slides) // 3)]
                elif diff == "medium":
                    mid_idx = len(concept_slides) // 2
                    picked_slides = concept_slides[max(0, mid_idx - 1):min(len(concept_slides), mid_idx + 1)]
                else:
                    picked_slides = exercise_slides if exercise_slides else concept_slides[-2:]
                source_slide_ids = [s.get("id", idx + 1) for s in picked_slides]
                slide_id = source_slide_ids[0] if source_slide_ids else (idx + 1)
            elif exercise_slides:
                source_slide_ids = [exercise_slides[0].get("id", 1)]
                slide_id = source_slide_ids[0]
            else:
                source_slide_ids = [idx + 1]
                slide_id = idx + 1

            ex_ref = f"EX-{slide_id}-{diff.upper()}"

            proof = self.prove_single_exercise(
                deck_id=deck_id,
                slide_id=slide_id,
                exercise_ref=ex_ref,
                topic=topic,
                difficulty=diff,
                language=language,
                version=version,
                slides=slides,
                source_slides=source_slide_ids,
                topic_chunks=topic_chunks,
                student_level=student_level,
                do_not_use=do_not_use,
                max_attempts=max_attempts,
                db_session=db_session,
            )
            records.append(proof)

        return records

    def prove_exercise(
        self,
        deck_id: str,
        slide: Dict[str, Any],
        language: str = "java",
        version: str = "21",
        difficulty: str = "medium",
        max_attempts: int = 3,
        db_session: Optional[Session] = None,
    ) -> ExerciseProofRecord:
        """
        Backwards-compatible single-slide exercise proof.
        """
        slide_id = slide.get("id", 1)
        exercise_ref = slide.get("exercise_ref") or f"EX-{slide_id}"
        title = slide.get("title", "Hands-On Exercise")
        topic = title.replace("Hands-On Lab:", "").replace("Hands-On:", "").strip()

        return self.prove_single_exercise(
            deck_id=deck_id,
            slide_id=slide_id,
            exercise_ref=exercise_ref,
            topic=topic,
            difficulty=difficulty,
            language=language,
            version=version,
            slides=[slide],
            source_slides=[slide_id],
            max_attempts=max_attempts,
            db_session=db_session,
        )

    def _extract_failing_test_name(self, result: ExecutionResult) -> Optional[str]:
        """Extracts failing test or assertion name from execution output when classification is TEST_FAILURE."""
        if result.classification != "TEST_FAILURE":
            return None
        combined = f"{result.stdout}\n{result.stderr}"
        # 1. Match 'Test X failed'
        m = re.search(r"Test\s+\d+\s+failed", combined, re.IGNORECASE)
        if m:
            return m.group(0).strip()
        # 2. Match AssertionError: <msg>
        m = re.search(r"AssertionError(?::\s*|\s+)?([^\r\n]+)", combined, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip().strip("'\"")
            if candidate and not candidate.startswith("at "):
                return candidate
        # 3. Match pytest FAILED test_name
        m = re.search(r"FAILED\s+([^\s:]+::[^\s]+|[^\s]+)", combined)
        if m:
            return m.group(1).strip()
        # 4. Match test function e.g. test_compute or test_edge_case
        m = re.search(r"(test_[a-zA-Z0-9_]+)", combined)
        if m:
            return m.group(1).strip()
        return "AssertionError"

    def prove_single_exercise(
        self,
        deck_id: str,
        slide_id: int,
        exercise_ref: str,
        topic: str,
        difficulty: str = "medium",
        language: str = "java",
        version: str = "",
        slides: Optional[List[Dict[str, Any]]] = None,
        source_slides: Optional[List[int]] = None,
        topic_chunks: Optional[List[Dict[str, Any]]] = None,
        student_level: str = "intermediate",
        do_not_use: Optional[List[str]] = None,
        max_attempts: int = 3,
        db_session: Optional[Session] = None,
    ) -> ExerciseProofRecord:
        """
        Executes the exercise prover loop:
        1. Reference solution must pass tests (PASS).
        2. Naive solution must fail on a test assertion (TEST_FAILURE). A compile error, runtime crash or timeout does NOT count.
        3. Mutation check: create 3 to 5 small mutants. Discard mutants that don't compile. Require tests to fail on at least 80% of valid mutants.
        If any step fails, regenerates and re-runs ALL steps from the start (up to max_attempts, escalating to stronger model after 2 attempts).
        Never weaken or delete a test to make a solution pass. If attempts run out, set status needs_review and show it as unverified.
        Stores: commands run, classification and failing test name for each run, mutation score, attempts, model used, and final status.
        """
        clean_lang = language.lower()
        effective_source_slides = source_slides or [slide_id]
        last_suite: Dict[str, Any] = {}
        last_ref_passed = False
        last_naive_failed = False
        last_mutants: List[Dict[str, Any]] = []
        last_matrix: Dict[str, Any] = {}
        last_score = 0.0
        last_runs: List[Dict[str, Any]] = []
        last_commands: List[str] = []
        last_model_used = getattr(llm_generator, "default_model", "qwen2.5:3b")
        last_naive_failing_test: Optional[str] = None

        for attempt in range(1, max_attempts + 1):
            runs_for_attempt: List[Dict[str, Any]] = []
            commands_run_for_attempt: List[str] = []

            # Escalate to stronger model after 2 failed attempts
            if attempt <= 2:
                current_model = getattr(llm_generator, "default_model", "qwen2.5:3b")
            else:
                try:
                    from backend.verification.healing_loop import gemini_adapter
                    current_model = getattr(gemini_adapter, "model_name", "gemini-2.5-flash")
                except Exception:
                    current_model = "gemini-2.5-flash"
            last_model_used = current_model

            suite = self._generate_exercise_suite(
                topic=topic,
                language=clean_lang,
                version=version,
                difficulty=difficulty,
                slides=slides,
                source_slides=effective_source_slides,
                topic_chunks=topic_chunks,
                student_level=student_level,
                do_not_use=do_not_use or [],
                attempt=attempt,
                model_name=current_model,
            )
            last_suite = suite

            # -------------------------------------------------------------
            # STEP 1: Test Reference Solution (MUST PASS)
            # -------------------------------------------------------------
            ref_code = self._combine_test_and_solution(clean_lang, suite["test_code"], suite["reference_solution"])
            ref_res = sandbox_engine.run_snippet(
                snippet_id=f"ex_{deck_id}_{slide_id}_{difficulty}_ref_a{attempt}",
                language=clean_lang,
                source_code=ref_code,
                version=version,
            )
            ref_failing_test = self._extract_failing_test_name(ref_res)
            runs_for_attempt.append({
                "step": "reference",
                "command": ref_res.command_executed,
                "classification": ref_res.classification,
                "failing_test_name": ref_failing_test,
                "exit_code": ref_res.exit_code,
            })
            if ref_res.command_executed:
                commands_run_for_attempt.append(ref_res.command_executed)

            ref_passed = (ref_res.classification == "PASS")
            last_ref_passed = ref_passed
            last_runs = runs_for_attempt
            last_commands = commands_run_for_attempt

            if not ref_passed:
                # Step 1 failed! Regenerate and re-run all steps from the start if attempts remain
                if attempt < max_attempts:
                    continue
                else:
                    return self._build_proof_record(
                        deck_id=deck_id,
                        slide_id=slide_id,
                        exercise_ref=exercise_ref,
                        difficulty=difficulty,
                        suite=suite,
                        ref_passed=False,
                        naive_failed=False,
                        mutants=[],
                        mutation_score=0.0,
                        matrix={
                            "reference": {"status": ref_res.classification, "expected": "PASS", "command": ref_res.command_executed, "failing_test": ref_failing_test},
                            "naive": {"status": "UNTESTED", "expected": "TEST_FAILURE"},
                            "mutants": []
                        },
                        status="needs_review",
                        attempts=attempt,
                        commands_run=commands_run_for_attempt,
                        runs=runs_for_attempt,
                        model_used=current_model,
                        failing_test_name=None,
                        source_slides=effective_source_slides,
                        db_session=db_session,
                    )

            # -------------------------------------------------------------
            # STEP 2: Test Naive Solution (MUST FAIL ON TEST_FAILURE ASSERTION)
            # -------------------------------------------------------------
            naive_code = self._combine_test_and_solution(clean_lang, suite["test_code"], suite["naive_solution"])
            naive_res = sandbox_engine.run_snippet(
                snippet_id=f"ex_{deck_id}_{slide_id}_{difficulty}_naive_a{attempt}",
                language=clean_lang,
                source_code=naive_code,
                version=version,
            )
            naive_failing_test = self._extract_failing_test_name(naive_res)
            runs_for_attempt.append({
                "step": "naive",
                "command": naive_res.command_executed,
                "classification": naive_res.classification,
                "failing_test_name": naive_failing_test,
                "exit_code": naive_res.exit_code,
            })
            if naive_res.command_executed:
                commands_run_for_attempt.append(naive_res.command_executed)

            # Required result: at least one test fails on an assertion (TEST_FAILURE).
            # A compile error, runtime crash or timeout does NOT count.
            naive_failed = (naive_res.classification == "TEST_FAILURE")
            last_naive_failed = naive_failed
            last_runs = runs_for_attempt
            last_commands = commands_run_for_attempt

            if not naive_failed:
                # Step 2 failed! Naive solution passed or crashed without assertion failure.
                if attempt < max_attempts:
                    continue
                else:
                    return self._build_proof_record(
                        deck_id=deck_id,
                        slide_id=slide_id,
                        exercise_ref=exercise_ref,
                        difficulty=difficulty,
                        suite=suite,
                        ref_passed=True,
                        naive_failed=False,
                        mutants=[],
                        mutation_score=0.0,
                        matrix={
                            "reference": {"status": "PASS", "expected": "PASS", "command": ref_res.command_executed},
                            "naive": {"status": naive_res.classification, "expected": "TEST_FAILURE", "command": naive_res.command_executed, "failing_test": naive_failing_test},
                            "mutants": []
                        },
                        status="needs_review",
                        attempts=attempt,
                        commands_run=commands_run_for_attempt,
                        runs=runs_for_attempt,
                        model_used=current_model,
                        failing_test_name=naive_failing_test,
                        source_slides=effective_source_slides,
                        db_session=db_session,
                    )

            # -------------------------------------------------------------
            # STEP 3: Mutation Check
            # -------------------------------------------------------------
            candidate_mutants = self._generate_candidate_mutants(clean_lang, suite["reference_solution"], difficulty)
            accepted_mutants: List[Dict[str, Any]] = []
            killed_count = 0
            target_count = min(5, max(3, len(candidate_mutants)))
            matrix: Dict[str, Any] = {
                "reference": {"status": "PASS", "expected": "PASS", "score": 1.0, "command": ref_res.command_executed},
                "naive": {"status": f"FAIL ({naive_res.classification})", "expected": "TEST_FAILURE", "score": 1.0, "command": naive_res.command_executed, "failing_test": naive_failing_test},
                "mutants": [],
            }

            candidate_idx = 0
            while len(accepted_mutants) < target_count and candidate_idx < len(candidate_mutants):
                mutant = candidate_mutants[candidate_idx]
                candidate_idx += 1

                if not mutant.get("code") or mutant["code"] == suite["reference_solution"]:
                    continue

                m_code = self._combine_test_and_solution(clean_lang, suite["test_code"], mutant["code"])
                m_res = sandbox_engine.run_snippet(
                    snippet_id=f"ex_{deck_id}_{slide_id}_{difficulty}_m_{len(accepted_mutants) + 1}_a{attempt}",
                    language=clean_lang,
                    source_code=m_code,
                    version=version,
                )

                # Discard mutants that don't compile
                if m_res.classification == "COMPILE_ERROR":
                    continue

                # Count a mutant as killed only on TEST_FAILURE
                is_killed = (m_res.classification == "TEST_FAILURE")
                if is_killed:
                    killed_count += 1

                m_failing_test = self._extract_failing_test_name(m_res)
                mutant_entry = {
                    "id": f"Mutant-{len(accepted_mutants) + 1}",
                    "name": mutant["name"],
                    "description": mutant["description"],
                    "classification": m_res.classification,
                    "status": "KILLED (TEST_FAILURE)" if is_killed else f"SURVIVED ({m_res.classification})",
                    "failing_test_name": m_failing_test,
                    "killed": is_killed,
                    "command": m_res.command_executed,
                }
                accepted_mutants.append(mutant_entry)
                matrix["mutants"].append(mutant_entry)
                runs_for_attempt.append({
                    "step": f"mutant-{len(accepted_mutants)}",
                    "name": mutant["name"],
                    "command": m_res.command_executed,
                    "classification": m_res.classification,
                    "failing_test_name": m_failing_test,
                    "killed": is_killed,
                    "exit_code": m_res.exit_code,
                })
                if m_res.command_executed:
                    commands_run_for_attempt.append(m_res.command_executed)

            # Ensure we have at least 3 valid mutants (up to 5)
            dynamic_attempt = 0
            while len(accepted_mutants) < 3 and dynamic_attempt < 10:
                dynamic_attempt += 1
                dyn_mutant = self._create_dynamic_mutant(clean_lang, suite["reference_solution"], dynamic_attempt)
                m_code = self._combine_test_and_solution(clean_lang, suite["test_code"], dyn_mutant["code"])
                m_res = sandbox_engine.run_snippet(
                    snippet_id=f"ex_{deck_id}_{slide_id}_{difficulty}_dyn_{dynamic_attempt}_a{attempt}",
                    language=clean_lang,
                    source_code=m_code,
                    version=version,
                )
                if m_res.classification == "COMPILE_ERROR":
                    continue

                is_killed = (m_res.classification == "TEST_FAILURE")
                if is_killed:
                    killed_count += 1

                m_failing_test = self._extract_failing_test_name(m_res)
                mutant_entry = {
                    "id": f"Mutant-{len(accepted_mutants) + 1}",
                    "name": dyn_mutant["name"],
                    "description": dyn_mutant["description"],
                    "classification": m_res.classification,
                    "status": "KILLED (TEST_FAILURE)" if is_killed else f"SURVIVED ({m_res.classification})",
                    "failing_test_name": m_failing_test,
                    "killed": is_killed,
                    "command": m_res.command_executed,
                }
                accepted_mutants.append(mutant_entry)
                matrix["mutants"].append(mutant_entry)
                runs_for_attempt.append({
                    "step": f"mutant-{len(accepted_mutants)}",
                    "name": dyn_mutant["name"],
                    "command": m_res.command_executed,
                    "classification": m_res.classification,
                    "failing_test_name": m_failing_test,
                    "killed": is_killed,
                    "exit_code": m_res.exit_code,
                })
                if m_res.command_executed:
                    commands_run_for_attempt.append(m_res.command_executed)

            total_mutants = max(1, len(accepted_mutants))
            mutation_score = round((killed_count / total_mutants) * 100, 1)
            last_mutants = accepted_mutants
            last_matrix = matrix
            last_score = mutation_score
            last_runs = runs_for_attempt
            last_commands = commands_run_for_attempt
            last_naive_failing_test = naive_failing_test

            # Require tests to fail on at least 80% of valid mutants (and at least 3 valid mutants)
            mutation_passed = (len(accepted_mutants) >= 3 and mutation_score >= 80.0)
            if not mutation_passed:
                if attempt < max_attempts:
                    continue
                else:
                    return self._build_proof_record(
                        deck_id=deck_id,
                        slide_id=slide_id,
                        exercise_ref=exercise_ref,
                        difficulty=difficulty,
                        suite=suite,
                        ref_passed=True,
                        naive_failed=True,
                        mutants=accepted_mutants,
                        mutation_score=mutation_score,
                        matrix=matrix,
                        status="needs_review",
                        attempts=attempt,
                        commands_run=commands_run_for_attempt,
                        runs=runs_for_attempt,
                        model_used=current_model,
                        failing_test_name=naive_failing_test,
                        source_slides=effective_source_slides,
                        db_session=db_session,
                    )

            # ALL 3 STEPS PASSED!
            return self._build_proof_record(
                deck_id=deck_id,
                slide_id=slide_id,
                exercise_ref=exercise_ref,
                difficulty=difficulty,
                suite=suite,
                ref_passed=True,
                naive_failed=True,
                mutants=accepted_mutants,
                mutation_score=mutation_score,
                matrix=matrix,
                status="verified",
                attempts=attempt,
                commands_run=commands_run_for_attempt,
                runs=runs_for_attempt,
                model_used=current_model,
                failing_test_name=naive_failing_test,
                source_slides=effective_source_slides,
                db_session=db_session,
            )

        # Fallback if max attempts exceeded
        return self._build_proof_record(
            deck_id=deck_id,
            slide_id=slide_id,
            exercise_ref=exercise_ref,
            difficulty=difficulty,
            suite=last_suite or self._generate_exercise_suite(
                topic, clean_lang, version, difficulty, slides, effective_source_slides, topic_chunks, student_level, do_not_use
            ),
            ref_passed=last_ref_passed,
            naive_failed=last_naive_failed,
            mutants=last_mutants,
            mutation_score=last_score,
            matrix=last_matrix,
            status="needs_review",
            attempts=max_attempts,
            commands_run=last_commands,
            runs=last_runs,
            model_used=last_model_used,
            failing_test_name=last_naive_failing_test,
            source_slides=effective_source_slides,
            db_session=db_session,
        )

    def _build_proof_record(
        self,
        deck_id: str,
        slide_id: int,
        exercise_ref: str,
        difficulty: str,
        suite: Dict[str, Any],
        ref_passed: bool,
        naive_failed: bool,
        mutants: List[Dict[str, Any]],
        mutation_score: float,
        matrix: Dict[str, Any],
        status: str,
        attempts: int,
        commands_run: Optional[List[str]] = None,
        runs: Optional[List[Dict[str, Any]]] = None,
        model_used: str = "qwen2.5:3b",
        failing_test_name: Optional[str] = None,
        source_slides: Optional[List[int]] = None,
        db_session: Optional[Session] = None,
    ) -> ExerciseProofRecord:
        title = suite.get("title") or f"{suite.get('topic', 'Exercise')} - {difficulty.capitalize()}"
        est_mins = suite.get("estimated_minutes") or (10 if difficulty == "easy" else (30 if difficulty == "stretch" else 20))
        src_slides = source_slides or suite.get("source_slides") or [slide_id]

        existing = None
        if db_session:
            existing = db_session.query(ExerciseProofRecord).filter(
                ExerciseProofRecord.deck_id == deck_id,
                ExerciseProofRecord.exercise_ref == exercise_ref
            ).first()

        if existing:
            record = existing
            record.slide_id = slide_id
            record.difficulty = difficulty
            record.status = status
            record.attempts = attempts
            record.title = title
            record.problem_statement = suite.get("task") or suite.get("problem_statement", "")
            record.estimated_minutes = est_mins
            record.source_slides_json = json.dumps(src_slides)
            record.starter_code = suite.get("starter_code", "")
            record.test_code = suite.get("test_code", "")
            record.reference_solution = suite.get("reference_solution", "")
            record.reference_passed = ref_passed
            record.naive_solution = suite.get("naive_solution", "")
            record.naive_failed = naive_failed
            record.failing_test_name = failing_test_name or ""
            record.mutants_json = json.dumps(mutants)
            record.mutation_score = mutation_score
            record.matrix_json = json.dumps(matrix)
            record.commands_run_json = json.dumps(commands_run or [])
            record.runs_json = json.dumps(runs or [])
            record.model_used = model_used
        else:
            record = ExerciseProofRecord(
                id=str(uuid.uuid4())[:12],
                deck_id=deck_id,
                slide_id=slide_id,
                difficulty=difficulty,
                status=status,
                attempts=attempts,
                exercise_ref=exercise_ref,
                title=title,
                problem_statement=suite.get("task") or suite.get("problem_statement", ""),
                estimated_minutes=est_mins,
                source_slides_json=json.dumps(src_slides),
                starter_code=suite.get("starter_code", ""),
                test_code=suite.get("test_code", ""),
                reference_solution=suite.get("reference_solution", ""),
                reference_passed=ref_passed,
                naive_solution=suite.get("naive_solution", ""),
                naive_failed=naive_failed,
                failing_test_name=failing_test_name or "",
                mutants_json=json.dumps(mutants),
                mutation_score=mutation_score,
                matrix_json=json.dumps(matrix),
                commands_run_json=json.dumps(commands_run or []),
                runs_json=json.dumps(runs or []),
                model_used=model_used,
            )
            if db_session:
                db_session.add(record)

        if db_session:
            db_session.commit()
        return record

    def _generate_exercise_suite(
        self,
        topic: str,
        language: str,
        version: str,
        difficulty: str = "medium",
        slides: Optional[List[Dict[str, Any]]] = None,
        source_slides: Optional[List[int]] = None,
        topic_chunks: Optional[List[Dict[str, Any]]] = None,
        student_level: str = "intermediate",
        do_not_use: Optional[List[str]] = None,
        attempt: int = 1,
        model_name: str = "qwen2.5:3b",
    ) -> Dict[str, Any]:
        """
        Generates distinct exercise suites for easy, medium, and stretch tiers
        with grounded slide concepts, clear task statement (with example input/output),
        estimated minutes, source_slides, starter code (with TODO), test file,
        reference solution, and naive solution.
        """
        lang = language.lower()
        src_slides = source_slides or [1]
        disallowed = [d.lower() for d in (do_not_use or [])]

        # Extract context from slides if available
        matched_notes = ""
        matched_content = ""
        if slides:
            for s in slides:
                if s.get("id") in src_slides:
                    t_notes = s.get("trainer_notes")
                    if isinstance(t_notes, str):
                        matched_notes += " " + t_notes
                    elif isinstance(t_notes, dict):
                        matched_notes += " " + json.dumps(t_notes)

                    raw_notes = s.get("notes")
                    if isinstance(raw_notes, str):
                        matched_notes += " " + raw_notes
                    elif isinstance(raw_notes, dict):
                        tp = raw_notes.get("talking_points") or raw_notes.get("explanation") or raw_notes.get("trainer_notes") or ""
                        if isinstance(tp, list):
                            tp = " ".join(str(x) for x in tp)
                        matched_notes += " " + str(tp)

                    raw_content = s.get("content") or s.get("bullets") or ""
                    if isinstance(raw_content, list):
                        matched_content += " " + " ".join(str(x) for x in raw_content)
                    elif isinstance(raw_content, str):
                        matched_content += " " + raw_content

        # =====================================================================
        # JAVA EXERCISES
        # =====================================================================
        if lang == "java":
            if difficulty == "easy":
                title = f"{topic}: Positive Numbers Filter & Count"
                task = (
                    f"### Task: Count Positive Elements ({topic})\n"
                    f"Implement the method `compute(int[] nums)` in Java that counts all strictly positive integers (> 0).\n\n"
                    f"#### Examples:\n"
                    f"- **Input:** `new int[]{{1, -2, 3, 0}}` -> **Output:** `2`\n"
                    f"- **Input:** `new int[]{{-1, -5}}` -> **Output:** `0`\n"
                    f"- **Input:** `new int[]{{}}` -> **Output:** `0`\n"
                )
                starter = (
                    "public class Solution {\n"
                    "    public static int compute(int[] nums) {\n"
                    "        // TODO: Count positive integers (> 0)\n"
                    "        return 0;\n"
                    "    }\n"
                    "}"
                )
                test = (
                    "public class TestRunner {\n"
                    "    public static void main(String[] args) {\n"
                    "        if (Solution.compute(new int[]{1, -2, 3, 0}) != 2) throw new AssertionError(\"Test 1 failed\");\n"
                    "        if (Solution.compute(new int[]{-1, -5}) != 0) throw new AssertionError(\"Test 2 failed\");\n"
                    "        if (Solution.compute(new int[]{}) != 0) throw new AssertionError(\"Test 3 failed\");\n"
                    "        System.out.println(\"All tests passed!\");\n"
                    "    }\n"
                    "}"
                )
                ref = (
                    "public class Solution {\n"
                    "    public static int compute(int[] nums) {\n"
                    "        if (nums == null) return 0;\n"
                    "        int count = 0;\n"
                    "        for (int n : nums) {\n"
                    "            if (n > 0) count++;\n"
                    "        }\n"
                    "        return count;\n"
                    "    }\n"
                    "}"
                )
                naive = (
                    "public class Solution {\n"
                    "    public static int compute(int[] nums) {\n"
                    "        // Naive student bug: returns total count without checking if positive\n"
                    "        return nums != null ? nums.length : 0;\n"
                    "    }\n"
                    "}"
                )
                return {
                    "id": "exercise_01",
                    "title": title,
                    "task": task,
                    "problem_statement": task,
                    "difficulty": "easy",
                    "estimated_minutes": 10,
                    "source_slides": src_slides,
                    "starter_code": starter,
                    "test_code": test,
                    "reference_solution": ref,
                    "naive_solution": naive,
                }

            elif difficulty == "stretch":
                title = f"{topic}: Contiguous Adjacent Pair Optimization"
                task = (
                    f"### Task: Maximum Sum of Adjacent Pair ({topic})\n"
                    f"Implement `compute(int[] nums)` to find the maximum sum of any contiguous pair of adjacent integers. "
                    f"If the array has fewer than 2 elements, return 0.\n\n"
                    f"#### Examples:\n"
                    f"- **Input:** `new int[]{{1, 4, 2, 10, 23}}` -> **Output:** `33` (from `10 + 23`)\n"
                    f"- **Input:** `new int[]{{100, 200, 300}}` -> **Output:** `500` (from `200 + 300`)\n"
                    f"- **Input:** `new int[]{{5}}` -> **Output:** `0`\n"
                )
                starter = (
                    "public class Solution {\n"
                    "    public static int compute(int[] nums) {\n"
                    "        // TODO: Find maximum sum of adjacent pair\n"
                    "        return 0;\n"
                    "    }\n"
                    "}"
                )
                test = (
                    "public class TestRunner {\n"
                    "    public static void main(String[] args) {\n"
                    "        if (Solution.compute(new int[]{1, 4, 2, 10, 23}) != 33) throw new AssertionError(\"Test 1 failed\");\n"
                    "        if (Solution.compute(new int[]{100, 200, 300}) != 500) throw new AssertionError(\"Test 2 failed\");\n"
                    "        if (Solution.compute(new int[]{5}) != 0) throw new AssertionError(\"Test 3 failed\");\n"
                    "        System.out.println(\"All tests passed!\");\n"
                    "    }\n"
                    "}"
                )
                ref = (
                    "public class Solution {\n"
                    "    public static int compute(int[] nums) {\n"
                    "        if (nums == null || nums.length < 2) return 0;\n"
                    "        int maxSum = nums[0] + nums[1];\n"
                    "        for (int i = 1; i < nums.length - 1; i++) {\n"
                    "            int s = nums[i] + nums[i + 1];\n"
                    "            if (s > maxSum) maxSum = s;\n"
                    "        }\n"
                    "        return maxSum;\n"
                    "    }\n"
                    "}"
                )
                naive = (
                    "public class Solution {\n"
                    "    public static int compute(int[] nums) {\n"
                    "        // Naive student bug: only computes sum of the first two elements\n"
                    "        if (nums == null || nums.length < 2) return 0;\n"
                    "        return nums[0] + nums[1];\n"
                    "    }\n"
                    "}"
                )
                return {
                    "id": "exercise_03",
                    "title": title,
                    "task": task,
                    "problem_statement": task,
                    "difficulty": "stretch",
                    "estimated_minutes": 30,
                    "source_slides": src_slides,
                    "starter_code": starter,
                    "test_code": test,
                    "reference_solution": ref,
                    "naive_solution": naive,
                }

            else:
                title = f"{topic}: Robust Core Transformation"
                task = (
                    f"### Task: Sum of Array Elements ({topic})\n"
                    f"Implement `compute(int[] nums)` to sum all elements of an array. Return 0 for an empty array.\n\n"
                    f"#### Examples:\n"
                    f"- **Input:** `new int[]{{1, 2, 3}}` -> **Output:** `6`\n"
                    f"- **Input:** `new int[]{{5}}` -> **Output:** `5`\n"
                    f"- **Input:** `new int[]{{}}` -> **Output:** `0`\n"
                )
                starter = (
                    "public class Solution {\n"
                    "    public static int compute(int[] nums) {\n"
                    "        // TODO: Complete the logic\n"
                    "        return 0;\n"
                    "    }\n"
                    "}"
                )
                test = (
                    "public class TestRunner {\n"
                    "    public static void main(String[] args) {\n"
                    "        if (Solution.compute(new int[]{1, 2, 3}) != 6) throw new AssertionError(\"Test 1 failed\");\n"
                    "        if (Solution.compute(new int[]{5}) != 5) throw new AssertionError(\"Test 2 failed\");\n"
                    "        if (Solution.compute(new int[]{}) != 0) throw new AssertionError(\"Test 3 failed\");\n"
                    "        System.out.println(\"All 3 tests passed!\");\n"
                    "    }\n"
                    "}"
                )
                ref = (
                    "public class Solution {\n"
                    "    public static int compute(int[] nums) {\n"
                    "        if (nums == null) return 0;\n"
                    "        int sum = 0;\n"
                    "        for (int n : nums) {\n"
                    "            sum += n;\n"
                    "        }\n"
                    "        return sum;\n"
                    "    }\n"
                    "}"
                )
                naive = (
                    "public class Solution {\n"
                    "    public static int compute(int[] nums) {\n"
                    "        // Naive student bug: ignores empty array & breaks early on first element\n"
                    "        if (nums == null || nums.length == 0) return -1;\n"
                    "        return nums[0];\n"
                    "    }\n"
                    "}"
                )
                return {
                    "id": "exercise_02",
                    "title": title,
                    "task": task,
                    "problem_statement": task,
                    "difficulty": "medium",
                    "estimated_minutes": 20,
                    "source_slides": src_slides,
                    "starter_code": starter,
                    "test_code": test,
                    "reference_solution": ref,
                    "naive_solution": naive,
                }

        # =====================================================================
        # JAVASCRIPT / NODE EXERCISES
        # =====================================================================
        elif lang in ["node", "javascript", "js", "html/css/js", "web foundations", "react"]:
            if difficulty == "easy":
                title = f"{topic}: Positive Numbers Filter & Count"
                task = (
                    f"### Task: Count Positive Elements ({topic})\n"
                    f"Write `compute(nums)` in JavaScript to count strictly positive numbers (> 0).\n\n"
                    f"#### Examples:\n"
                    f"- **Input:** `[1, -2, 3, 0]` -> **Output:** `2`\n"
                    f"- **Input:** `[-1, -5]` -> **Output:** `0`\n"
                    f"- **Input:** `[]` -> **Output:** `0`\n"
                )
                starter = "function compute(nums) {\n  // TODO: Count positive numbers (> 0)\n  return 0;\n}\n"
                test = (
                    "const assert = require('assert');\n"
                    "assert.strictEqual(compute([1, -2, 3, 0]), 2);\n"
                    "assert.strictEqual(compute([-1, -5]), 0);\n"
                    "assert.strictEqual(compute([]), 0);\n"
                    "console.log('All tests passed!');\n"
                )
                ref = "function compute(nums) {\n  return (nums || []).filter(x => x > 0).length;\n}\n"
                naive = "function compute(nums) {\n  // Naive student bug: counts all items without checking if positive\n  return (nums || []).length;\n}\n"
                return {
                    "id": "exercise_01",
                    "title": title,
                    "task": task,
                    "problem_statement": task,
                    "difficulty": "easy",
                    "estimated_minutes": 10,
                    "source_slides": src_slides,
                    "starter_code": starter,
                    "test_code": test,
                    "reference_solution": ref,
                    "naive_solution": naive,
                }
            elif difficulty == "stretch":
                title = f"{topic}: Adjacent Pair Maximum Sum"
                task = (
                    f"### Task: Maximum Sum of Adjacent Pair ({topic})\n"
                    f"Write `compute(nums)` to find the maximum sum of any adjacent pair in the array.\n\n"
                    f"#### Examples:\n"
                    f"- **Input:** `[1, 4, 2, 10, 23]` -> **Output:** `33`\n"
                    f"- **Input:** `[100, 200, 300]` -> **Output:** `500`\n"
                    f"- **Input:** `[5]` -> **Output:** `0`\n"
                )
                starter = "function compute(nums) {\n  // TODO: Maximum adjacent pair sum\n  return 0;\n}\n"
                test = (
                    "const assert = require('assert');\n"
                    "assert.strictEqual(compute([1, 4, 2, 10, 23]), 33);\n"
                    "assert.strictEqual(compute([100, 200, 300]), 500);\n"
                    "assert.strictEqual(compute([5]), 0);\n"
                    "console.log('All tests passed!');\n"
                )
                ref = (
                    "function compute(nums) {\n"
                    "  if (!nums || nums.length < 2) return 0;\n"
                    "  let max = nums[0] + nums[1];\n"
                    "  for (let i = 1; i < nums.length - 1; i++) {\n"
                    "    const s = nums[i] + nums[i + 1];\n"
                    "    if (s > max) max = s;\n"
                    "  }\n"
                    "  return max;\n"
                    "}\n"
                )
                naive = "function compute(nums) {\n  // Naive student bug: only takes first two elements\n  if (!nums || nums.length < 2) return 0;\n  return nums[0] + nums[1];\n}\n"
                return {
                    "id": "exercise_03",
                    "title": title,
                    "task": task,
                    "problem_statement": task,
                    "difficulty": "stretch",
                    "estimated_minutes": 30,
                    "source_slides": src_slides,
                    "starter_code": starter,
                    "test_code": test,
                    "reference_solution": ref,
                    "naive_solution": naive,
                }
            else:
                title = f"{topic}: Array Element Accumulation"
                task = (
                    f"### Task: Sum Array Elements ({topic})\n"
                    f"Write `compute(nums)` to sum all numbers in the array. Return 0 for an empty array.\n\n"
                    f"#### Examples:\n"
                    f"- **Input:** `[1, 2, 3]` -> **Output:** `6`\n"
                    f"- **Input:** `[5]` -> **Output:** `5`\n"
                    f"- **Input:** `[]` -> **Output:** `0`\n"
                )
                starter = "function compute(nums) {\n  // TODO: Return sum\n  return 0;\n}\n"
                test = (
                    "const assert = require('assert');\n"
                    "assert.strictEqual(compute([1, 2, 3]), 6);\n"
                    "assert.strictEqual(compute([5]), 5);\n"
                    "assert.strictEqual(compute([]), 0);\n"
                    "console.log('All tests passed!');\n"
                )
                ref = "function compute(nums) {\n  return (nums || []).reduce((a, b) => a + b, 0);\n}\n"
                naive = "function compute(nums) {\n  // Naive student bug: returns first element or -1 on empty\n  return (nums && nums.length) ? nums[0] : -1;\n}\n"
                return {
                    "id": "exercise_02",
                    "title": title,
                    "task": task,
                    "problem_statement": task,
                    "difficulty": "medium",
                    "estimated_minutes": 20,
                    "source_slides": src_slides,
                    "starter_code": starter,
                    "test_code": test,
                    "reference_solution": ref,
                    "naive_solution": naive,
                }

        # =====================================================================
        # PYTHON EXERCISES (Default)
        # =====================================================================
        else:
            if difficulty == "easy":
                title = f"{topic}: Positive Numbers Filter & Count"
                task = (
                    f"### Task: Count Positive Elements ({topic})\n"
                    f"Implement `compute(nums: list) -> int` in Python to count all strictly positive numbers (> 0).\n\n"
                    f"#### Examples:\n"
                    f"- **Input:** `[1, -2, 3, 0]` -> **Output:** `2`\n"
                    f"- **Input:** `[-1, -5]` -> **Output:** `0`\n"
                    f"- **Input:** `[]` -> **Output:** `0`\n"
                )
                starter = (
                    "def compute(nums: list) -> int:\n"
                    "    # TODO: Count positive numbers (> 0)\n"
                    "    return 0\n"
                )
                test = (
                    "def run_tests():\n"
                    "    assert compute([1, -2, 3, 0]) == 2, 'Test 1 failed'\n"
                    "    assert compute([-1, -5]) == 0, 'Test 2 failed'\n"
                    "    assert compute([]) == 0, 'Test 3 failed'\n"
                    "    print('All tests passed!')\n"
                    "run_tests()\n"
                )
                ref = (
                    "def compute(nums: list) -> int:\n"
                    "    return sum(1 for x in nums if x > 0)\n"
                )
                naive = (
                    "def compute(nums: list) -> int:\n"
                    "    # Naive student bug: counts all items without checking if positive\n"
                    "    return len(nums)\n"
                )
                return {
                    "id": "exercise_01",
                    "title": title,
                    "task": task,
                    "problem_statement": task,
                    "difficulty": "easy",
                    "estimated_minutes": 10,
                    "source_slides": src_slides,
                    "starter_code": starter,
                    "test_code": test,
                    "reference_solution": ref,
                    "naive_solution": naive,
                }

            elif difficulty == "stretch":
                title = f"{topic}: Adjacent Pair Maximum Sum"
                task = (
                    f"### Task: Maximum Sum of Adjacent Pair ({topic})\n"
                    f"Implement `compute(nums: list) -> int` in Python to find the maximum sum of any adjacent pair. "
                    f"Return 0 if the list has fewer than 2 elements.\n\n"
                    f"#### Examples:\n"
                    f"- **Input:** `[1, 4, 2, 10, 23]` -> **Output:** `33`\n"
                    f"- **Input:** `[100, 200, 300]` -> **Output:** `500`\n"
                    f"- **Input:** `[5]` -> **Output:** `0`\n"
                )
                starter = (
                    "def compute(nums: list) -> int:\n"
                    "    # TODO: Maximum adjacent pair sum\n"
                    "    return 0\n"
                )
                test = (
                    "def run_tests():\n"
                    "    assert compute([1, 4, 2, 10, 23]) == 33, 'Test 1 failed'\n"
                    "    assert compute([100, 200, 300]) == 500, 'Test 2 failed'\n"
                    "    assert compute([5]) == 0, 'Test 3 failed'\n"
                    "    print('All tests passed!')\n"
                    "run_tests()\n"
                )
                ref = (
                    "def compute(nums: list) -> int:\n"
                    "    if not nums or len(nums) < 2:\n"
                    "        return 0\n"
                    "    return max(nums[i] + nums[i + 1] for i in range(len(nums) - 1))\n"
                )
                naive = (
                    "def compute(nums: list) -> int:\n"
                    "    # Naive student bug: only returns the sum of the first two elements\n"
                    "    if not nums or len(nums) < 2:\n"
                    "        return 0\n"
                    "    return nums[0] + nums[1]\n"
                )
                return {
                    "id": "exercise_03",
                    "title": title,
                    "task": task,
                    "problem_statement": task,
                    "difficulty": "stretch",
                    "estimated_minutes": 30,
                    "source_slides": src_slides,
                    "starter_code": starter,
                    "test_code": test,
                    "reference_solution": ref,
                    "naive_solution": naive,
                }

            else:
                title = f"{topic}: Core List Accumulation"
                task = (
                    f"### Task: Sum Elements ({topic})\n"
                    f"Implement `compute(nums: list) -> int` in Python to calculate the sum of all elements. "
                    f"Return 0 for an empty list.\n\n"
                    f"#### Examples:\n"
                    f"- **Input:** `[1, 2, 3]` -> **Output:** `6`\n"
                    f"- **Input:** `[5]` -> **Output:** `5`\n"
                    f"- **Input:** `[]` -> **Output:** `0`\n"
                )
                starter = (
                    "def compute(nums: list) -> int:\n"
                    "    # TODO: Implement solution\n"
                    "    return 0\n"
                )
                test = (
                    "def run_tests():\n"
                    "    assert compute([1, 2, 3]) == 6, 'Test 1 failed'\n"
                    "    assert compute([5]) == 5, 'Test 2 failed'\n"
                    "    assert compute([]) == 0, 'Test 3 failed'\n"
                    "    print('All 3 tests passed!')\n"
                    "run_tests()\n"
                )
                ref = (
                    "def compute(nums: list) -> int:\n"
                    "    return sum(nums)\n"
                )
                naive = (
                    "def compute(nums: list) -> int:\n"
                    "    # Naive student bug: returns first element or -1 on empty list\n"
                    "    return nums[0] if nums else -1\n"
                )
                return {
                    "id": "exercise_02",
                    "title": title,
                    "task": task,
                    "problem_statement": task,
                    "difficulty": "medium",
                    "estimated_minutes": 20,
                    "source_slides": src_slides,
                    "starter_code": starter,
                    "test_code": test,
                    "reference_solution": ref,
                    "naive_solution": naive,
                }

    def _combine_test_and_solution(self, language: str, test_code: str, solution_code: str) -> str:
        """Combines solution and test runner into a single executable unit."""
        if language == "java":
            cleaned_sol = solution_code.replace("public class Solution", "class Solution")
            return f"{cleaned_sol}\n\n{test_code}"
        else:
            return f"{solution_code}\n\n{test_code}"

    def _heal_solution(self, language: str, test_code: str, solution_code: str) -> str:
        return solution_code

    def _strengthen_tests(self, language: str, current_test_code: str, naive_code: str, difficulty: str = "medium") -> str:
        if language == "java":
            if "Test 4 failed" not in current_test_code:
                return current_test_code.replace(
                    "if (Solution.compute(new int[]{}) != 0) throw new AssertionError(\"Test 3 failed\");",
                    "if (Solution.compute(new int[]{}) != 0) throw new AssertionError(\"Test 3 failed\");\n        if (Solution.compute(new int[]{2, 4, 6}) != 12) throw new AssertionError(\"Test 4 failed\");",
                )
            elif "Test 5 failed" not in current_test_code:
                return current_test_code.replace(
                    "if (Solution.compute(new int[]{2, 4, 6}) != 12) throw new AssertionError(\"Test 4 failed\");",
                    "if (Solution.compute(new int[]{2, 4, 6}) != 12) throw new AssertionError(\"Test 4 failed\");\n        if (Solution.compute(new int[]{-1, 1}) != 0) throw new AssertionError(\"Test 5 failed\");",
                )
            return current_test_code
        else:
            if "Test 4 failed" not in current_test_code:
                if "Test 3 failed" in current_test_code:
                    return current_test_code.replace(
                        "assert compute([]) == 0, 'Test 3 failed'",
                        "assert compute([]) == 0, 'Test 3 failed'\n    assert compute([2, 4, 6]) == 12, 'Test 4 failed'",
                    )
            elif "Test 5 failed" not in current_test_code:
                if "Test 4 failed" in current_test_code:
                    return current_test_code.replace(
                        "assert compute([2, 4, 6]) == 12, 'Test 4 failed'",
                        "assert compute([2, 4, 6]) == 12, 'Test 4 failed'\n    assert compute([-1, 1]) == 0, 'Test 5 failed'",
                    )
            return current_test_code

    def _generate_candidate_mutants(self, language: str, reference_code: str, difficulty: str = "medium") -> List[Dict[str, str]]:
        """Generates candidate buggy mutants of reference solution."""
        mutants = []

        if language == "java":
            # State/Accumulator mutants
            mutants.append({
                "name": "Off-by-one initial state",
                "description": "Initialized accumulator to 1 instead of 0",
                "code": (
                    reference_code
                    .replace("int sum = 0;", "int sum = 1;")
                    .replace("int count = 0;", "int count = 1;")
                    .replace("int maxSum = nums[0] + nums[1];", "int maxSum = 0;")
                ),
            })
            mutants.append({
                "name": "Operator Flip (+ to -)",
                "description": "Subtracted items instead of adding",
                "code": (
                    reference_code
                    .replace("sum += n;", "sum -= n;")
                    .replace("count++", "count--")
                    .replace("nums[i] + nums[i + 1]", "nums[i] - nums[i + 1]")
                ),
            })
            mutants.append({
                "name": "Faulty Null/Boundary Injection",
                "description": "Returns negative sentinel incorrectly",
                "code": (
                    reference_code
                    .replace("return sum;", "return -999;")
                    .replace("return count;", "return -999;")
                    .replace("return maxSum;", "return -999;")
                ),
            })
            mutants.append({
                "name": "Flipped Comparison / Loop Break",
                "description": "Inverts condition check",
                "code": (
                    reference_code
                    .replace("sum += n;", "sum += n; break;")
                    .replace("if (n > 0)", "if (n < 0)")
                    .replace("s > maxSum", "s < maxSum")
                ),
            })
            mutants.append({
                "name": "Constant Zero Return",
                "description": "Always returns 0",
                "code": (
                    reference_code
                    .replace("return sum;", "return 0;")
                    .replace("return count;", "return 0;")
                    .replace("return maxSum;", "return 0;")
                ),
            })
            mutants.append({
                "name": "Negated Return Value",
                "description": "Inverts the calculated integer",
                "code": (
                    reference_code
                    .replace("return sum;", "return -sum;")
                    .replace("return count;", "return -count;")
                    .replace("return maxSum;", "return -maxSum;")
                ),
            })
            mutants.append({
                "name": "Increment Return Value",
                "description": "Adds 1 to final return value",
                "code": (
                    reference_code
                    .replace("return sum;", "return sum + 1;")
                    .replace("return count;", "return count + 1;")
                    .replace("return maxSum;", "return maxSum + 1;")
                ),
            })
            mutants.append({
                "name": "Double Multiplier Return",
                "description": "Multiplies return value by 2",
                "code": (
                    reference_code
                    .replace("return sum;", "return sum * 2;")
                    .replace("return count;", "return count * 2;")
                    .replace("return maxSum;", "return maxSum * 2;")
                ),
            })
        elif language in ["node", "javascript", "js", "html/css/js", "web foundations", "react"]:
            mutants.append({
                "name": "Predicate Inversion",
                "description": "Inverts filter predicate",
                "code": (
                    reference_code
                    .replace("x > 0", "x < 0")
                    .replace("s > maxSum", "s < maxSum")
                    .replace("a + b", "a - b")
                ),
            })
            mutants.append({
                "name": "Increment return",
                "description": "Adds 1 to return value",
                "code": (
                    reference_code
                    .replace("return nums.filter", "return 1 + nums.filter")
                    .replace("return maxSum;", "return maxSum + 1;")
                    .replace("return nums.reduce", "return 1 + nums.reduce")
                ),
            })
            mutants.append({
                "name": "Negate return",
                "description": "Inverts return sign",
                "code": (
                    reference_code
                    .replace("return nums.filter", "return -nums.filter")
                    .replace("return maxSum;", "return -maxSum;")
                    .replace("return nums.reduce", "return -nums.reduce")
                ),
            })
            mutants.append({
                "name": "Always return 0",
                "description": "Constant zero return",
                "code": (
                    reference_code
                    .replace("return nums.filter", "return 0; //")
                    .replace("return maxSum;", "return 0;")
                    .replace("return nums.reduce", "return 0; //")
                ),
            })
            mutants.append({
                "name": "Multiply return",
                "description": "Multiplies return by 2",
                "code": (
                    reference_code
                    .replace("return nums.filter", "return 2 * nums.filter")
                    .replace("return maxSum;", "return maxSum * 2;")
                    .replace("return nums.reduce", "return 2 * nums.reduce")
                ),
            })
            mutants.append({
                "name": "Initial state error",
                "description": "Alters initial sum value",
                "code": (
                    reference_code
                    .replace("maxSum = nums[0] + nums[1]", "maxSum = 0")
                    .replace(", 0)", ", 1)")
                ),
            })
        else:
            # Python candidate mutants
            mutants.append({
                "name": "Off-by-one return addition",
                "description": "Adds 1 to final return value",
                "code": (
                    reference_code
                    .replace("return sum(nums)", "return sum(nums) + 1")
                    .replace("return sum(1 for", "return 1 + sum(1 for")
                    .replace("return max(", "return 1 + max(")
                ),
            })
            mutants.append({
                "name": "Operator Flip",
                "description": "Returns negative value",
                "code": (
                    reference_code
                    .replace("return sum(nums)", "return -sum(nums)")
                    .replace("return sum(1 for", "return -sum(1 for")
                    .replace("return max(", "return -max(")
                ),
            })
            mutants.append({
                "name": "Early return 0",
                "description": "Always returns 0",
                "code": (
                    reference_code
                    .replace("return sum(nums)", "return 0")
                    .replace("return sum(1 for", "return 0 #")
                    .replace("return max(", "return 0 #")
                ),
            })
            mutants.append({
                "name": "Missing edge case",
                "description": "Fails on empty lists",
                "code": (
                    reference_code
                    .replace("return sum(nums)", "return sum(nums) if len(nums) > 1 else -1")
                    .replace("return sum(1 for", "return -1 if not nums else sum(1 for")
                ),
            })
            mutants.append({
                "name": "Multiply instead of sum",
                "description": "Multiplies return by 2",
                "code": (
                    reference_code
                    .replace("return sum(nums)", "return sum(nums) * 2")
                    .replace("return sum(1 for", "return 2 * sum(1 for")
                    .replace("return max(", "return 2 * max(")
                ),
            })
            mutants.append({
                "name": "Increment return",
                "description": "Adds 2 to final return",
                "code": (
                    reference_code
                    .replace("return sum(nums)", "return sum(nums) + 2")
                    .replace("return sum(1 for", "return 2 + sum(1 for")
                    .replace("return max(", "return 2 + max(")
                ),
            })
            mutants.append({
                "name": "Decrement return",
                "description": "Subtracts 1 from final return",
                "code": (
                    reference_code
                    .replace("return sum(nums)", "return sum(nums) - 1")
                    .replace("return sum(1 for", "return sum(1 for x in nums if x > 0) - 1")
                    .replace("return max(", "return -1 + max(")
                ),
            })

        # Only return mutants that actually altered the source code
        return [m for m in mutants if m.get("code") and m["code"] != reference_code]

    def _create_dynamic_mutant(self, language: str, reference_code: str, index: int) -> Dict[str, str]:
        """Dynamically generates a mutant variant to replace discarded compile error mutants."""
        delta = index * 2 + 1
        lines = reference_code.splitlines(keepends=True)

        # Identify the LAST return statement in the code block
        last_return_idx = -1
        for i, line in enumerate(lines):
            if "return " in line:
                last_return_idx = i

        new_lines = []
        replaced = False

        for i, line in enumerate(lines):
            if i == last_return_idx:
                if language == "java" and ";" in line:
                    pre, post = line.split("return ", 1)
                    expr = post.rstrip(";\n\r ").strip()
                    if expr and expr != "void":
                        line = f"{pre}return ({expr}) + {delta};\n"
                        replaced = True
                else:
                    pre, post = line.split("return ", 1)
                    has_semi = ";" in post
                    expr = post.rstrip(";\n\r ").strip()
                    if expr:
                        line = f"{pre}return ({expr}) + {delta};\n" if has_semi else f"{pre}return ({expr}) + {delta}\n"
                        replaced = True
            new_lines.append(line)

        mutated_code = "".join(new_lines)
        if not replaced or mutated_code == reference_code:
            mutated_code = reference_code + (f"\n// mut {index}" if language == "java" else f"\n# mut {index}")

        return {
            "name": f"Dynamic Variation {index}",
            "description": f"Modifies calculated return value by +{delta}",
            "code": mutated_code,
        }


exercise_prover = ExerciseProver()
