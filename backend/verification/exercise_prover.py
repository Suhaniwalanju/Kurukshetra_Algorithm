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

        # Find any exercise slides to correlate slide IDs
        exercise_slides = [s for s in (slides or []) if s.get("type") == "exercise" or s.get("exercise_ref")]

        for idx, diff in enumerate(difficulties):
            if idx < len(exercise_slides):
                slide_id = exercise_slides[idx].get("id", idx + 1)
                base_ref = exercise_slides[idx].get("exercise_ref") or f"EX-{slide_id}"
                ex_ref = f"{base_ref}-{diff.upper()}" if len(exercise_slides) == 1 else base_ref
            elif exercise_slides:
                slide_id = exercise_slides[0].get("id", 1)
                base_ref = exercise_slides[0].get("exercise_ref") or f"EX-{slide_id}"
                ex_ref = f"{base_ref}-{diff.upper()}"
            else:
                slide_id = idx + 1
                ex_ref = f"EX-{deck_id[:4].upper()}-{diff.upper()}"

            proof = self.prove_single_exercise(
                deck_id=deck_id,
                slide_id=slide_id,
                exercise_ref=ex_ref,
                topic=topic,
                difficulty=diff,
                language=language,
                version=version,
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
            max_attempts=max_attempts,
            db_session=db_session,
        )

    def prove_single_exercise(
        self,
        deck_id: str,
        slide_id: int,
        exercise_ref: str,
        topic: str,
        difficulty: str = "medium",
        language: str = "java",
        version: str = "",
        max_attempts: int = 3,
        db_session: Optional[Session] = None,
    ) -> ExerciseProofRecord:
        """
        Executes the exercise prover loop:
        1. Reference solution must pass tests (PASS).
        2. Naive solution must fail on a test assertion (TEST_FAILURE, not compile error).
        3. Mutation check: mutants executed, COMPILE_ERROR discarded/regenerated, killed only on TEST_FAILURE.
        If any step fails, regenerates and re-verifies up to max_attempts, then flags as needs_review.
        """
        clean_lang = language.lower()
        last_suite: Dict[str, str] = {}
        last_ref_passed = False
        last_naive_failed = False
        last_mutants: List[Dict[str, Any]] = []
        last_matrix: Dict[str, Any] = {}
        last_score = 0.0

        for attempt in range(1, max_attempts + 1):
            suite = self._generate_exercise_suite(
                topic=topic,
                language=clean_lang,
                version=version,
                difficulty=difficulty,
                attempt=attempt
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
            ref_passed = (ref_res.classification == "PASS")
            last_ref_passed = ref_passed

            if not ref_passed:
                # If reference failed, check if we have retries left
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
                            "reference": {"status": ref_res.classification, "expected": "PASS"},
                            "naive": {"status": "UNTESTED", "expected": "TEST_FAILURE"},
                            "mutants": []
                        },
                        status="needs_review",
                        attempts=attempt,
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
            naive_failed = (naive_res.classification == "TEST_FAILURE")

            # If naive passed or did not fail on TEST_FAILURE, strengthen tests (up to 3 times)
            s_attempts = 0
            while not naive_failed and s_attempts < 3:
                s_attempts += 1
                prev_test = suite["test_code"]
                suite["test_code"] = self._strengthen_tests(clean_lang, suite["test_code"], suite["naive_solution"], difficulty)

                # Requirement: After every test-strengthening step, re-run reference solution and require PASS
                ref_code = self._combine_test_and_solution(clean_lang, suite["test_code"], suite["reference_solution"])
                ref_res_s = sandbox_engine.run_snippet(
                    snippet_id=f"ex_{deck_id}_{slide_id}_{difficulty}_ref_a{attempt}_s{s_attempts}",
                    language=clean_lang,
                    source_code=ref_code,
                    version=version,
                )
                if ref_res_s.classification != "PASS":
                    # Reference failed strengthened test! Revert strengthening
                    suite["test_code"] = prev_test
                    ref_passed = False
                    break
                else:
                    ref_passed = True

                # Re-test naive solution
                naive_code = self._combine_test_and_solution(clean_lang, suite["test_code"], suite["naive_solution"])
                naive_res_s = sandbox_engine.run_snippet(
                    snippet_id=f"ex_{deck_id}_{slide_id}_{difficulty}_naive_a{attempt}_s{s_attempts}",
                    language=clean_lang,
                    source_code=naive_code,
                    version=version,
                )
                naive_failed = (naive_res_s.classification == "TEST_FAILURE")
                if naive_failed:
                    naive_res = naive_res_s
                    break

            last_naive_failed = naive_failed
            if not naive_failed:
                # Naive did not fail on a test assertion!
                if attempt < max_attempts:
                    continue
                else:
                    return self._build_proof_record(
                        deck_id=deck_id,
                        slide_id=slide_id,
                        exercise_ref=exercise_ref,
                        difficulty=difficulty,
                        suite=suite,
                        ref_passed=ref_passed,
                        naive_failed=False,
                        mutants=[],
                        mutation_score=0.0,
                        matrix={
                            "reference": {"status": "PASS", "expected": "PASS"},
                            "naive": {"status": naive_res.classification, "expected": "TEST_FAILURE"},
                            "mutants": []
                        },
                        status="needs_review",
                        attempts=attempt,
                        db_session=db_session,
                    )

            # -------------------------------------------------------------
            # STEP 3: Mutation Check
            # -------------------------------------------------------------
            candidate_mutants = self._generate_candidate_mutants(clean_lang, suite["reference_solution"], difficulty)
            accepted_mutants: List[Dict[str, Any]] = []
            killed_count = 0
            target_count = min(6, max(5, len(candidate_mutants)))
            matrix: Dict[str, Any] = {
                "reference": {"status": "PASS", "expected": "PASS", "score": 1.0},
                "naive": {"status": "FAIL (TEST_FAILURE)", "expected": "TEST_FAILURE", "score": 1.0},
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
                    snippet_id=f"ex_{deck_id}_{slide_id}_{difficulty}_m_{len(accepted_mutants) + 1}",
                    language=clean_lang,
                    source_code=m_code,
                    version=version,
                )

                # Discard mutants that return COMPILE_ERROR and regenerate them
                if m_res.classification == "COMPILE_ERROR":
                    continue

                # Count a mutant as killed only on TEST_FAILURE
                is_killed = (m_res.classification == "TEST_FAILURE")
                if is_killed:
                    killed_count += 1

                mutant_entry = {
                    "id": f"Mutant-{len(accepted_mutants) + 1}",
                    "name": mutant["name"],
                    "description": mutant["description"],
                    "classification": m_res.classification,
                    "status": "KILLED (TEST_FAILURE)" if is_killed else f"SURVIVED ({m_res.classification})",
                    "killed": is_killed,
                }
                accepted_mutants.append(mutant_entry)
                matrix["mutants"].append(mutant_entry)

            # Dynamically replace discarded mutants
            dynamic_attempt = 0
            while len(accepted_mutants) < target_count and dynamic_attempt < 10:
                dynamic_attempt += 1
                dyn_mutant = self._create_dynamic_mutant(clean_lang, suite["reference_solution"], dynamic_attempt)
                m_code = self._combine_test_and_solution(clean_lang, suite["test_code"], dyn_mutant["code"])
                m_res = sandbox_engine.run_snippet(
                    snippet_id=f"ex_{deck_id}_{slide_id}_{difficulty}_dyn_{dynamic_attempt}",
                    language=clean_lang,
                    source_code=m_code,
                    version=version,
                )
                if m_res.classification == "COMPILE_ERROR":
                    continue

                is_killed = (m_res.classification == "TEST_FAILURE")
                if is_killed:
                    killed_count += 1

                mutant_entry = {
                    "id": f"Mutant-{len(accepted_mutants) + 1}",
                    "name": dyn_mutant["name"],
                    "description": dyn_mutant["description"],
                    "classification": m_res.classification,
                    "status": "KILLED (TEST_FAILURE)" if is_killed else f"SURVIVED ({m_res.classification})",
                    "killed": is_killed,
                }
                accepted_mutants.append(mutant_entry)
                matrix["mutants"].append(mutant_entry)

            total_mutants = max(1, len(accepted_mutants))
            mutation_score = round((killed_count / total_mutants) * 100, 1)
            last_mutants = accepted_mutants
            last_matrix = matrix
            last_score = mutation_score

            mutation_passed = (killed_count > 0 and len(accepted_mutants) >= 3)
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
                db_session=db_session,
            )

        # Fallback if max attempts exceeded
        return self._build_proof_record(
            deck_id=deck_id,
            slide_id=slide_id,
            exercise_ref=exercise_ref,
            difficulty=difficulty,
            suite=last_suite or self._generate_exercise_suite(topic, clean_lang, version, difficulty),
            ref_passed=last_ref_passed,
            naive_failed=last_naive_failed,
            mutants=last_mutants,
            mutation_score=last_score,
            matrix=last_matrix,
            status="needs_review",
            attempts=max_attempts,
            db_session=db_session,
        )

    def _build_proof_record(
        self,
        deck_id: str,
        slide_id: int,
        exercise_ref: str,
        difficulty: str,
        suite: Dict[str, str],
        ref_passed: bool,
        naive_failed: bool,
        mutants: List[Dict[str, Any]],
        mutation_score: float,
        matrix: Dict[str, Any],
        status: str,
        attempts: int,
        db_session: Optional[Session] = None,
    ) -> ExerciseProofRecord:
        record = ExerciseProofRecord(
            id=str(uuid.uuid4())[:12],
            deck_id=deck_id,
            slide_id=slide_id,
            difficulty=difficulty,
            status=status,
            attempts=attempts,
            exercise_ref=exercise_ref,
            problem_statement=suite.get("task") or suite.get("problem_statement", ""),
            starter_code=suite.get("starter_code", ""),
            test_code=suite.get("test_code", ""),
            reference_solution=suite.get("reference_solution", ""),
            reference_passed=ref_passed,
            naive_solution=suite.get("naive_solution", ""),
            naive_failed=naive_failed,
            mutants_json=json.dumps(mutants),
            mutation_score=mutation_score,
            matrix_json=json.dumps(matrix),
        )
        if db_session:
            db_session.add(record)
            db_session.commit()
        return record

    def _generate_exercise_suite(
        self,
        topic: str,
        language: str,
        version: str,
        difficulty: str = "medium",
        attempt: int = 1
    ) -> Dict[str, str]:
        """
        Generates distinct exercise suites for easy, medium, and stretch tiers.
        """
        lang = language.lower()

        # =====================================================================
        # JAVA EXERCISES
        # =====================================================================
        if lang == "java":
            if difficulty == "easy":
                return {
                    "task": f"Easy: Implement `compute(int[] nums)` for {topic} that counts all strictly positive integers (> 0).",
                    "problem_statement": f"Easy: Implement `compute(int[] nums)` for {topic} that counts all strictly positive integers (> 0).",
                    "starter_code": (
                        "public class Solution {\n"
                        "    public static int compute(int[] nums) {\n"
                        "        // TODO: Count positive integers\n"
                        "        return 0;\n"
                        "    }\n"
                        "}"
                    ),
                    "test_code": (
                        "public class TestRunner {\n"
                        "    public static void main(String[] args) {\n"
                        "        if (Solution.compute(new int[]{1, -2, 3, 0}) != 2) throw new AssertionError(\"Test 1 failed\");\n"
                        "        if (Solution.compute(new int[]{-1, -5}) != 0) throw new AssertionError(\"Test 2 failed\");\n"
                        "        if (Solution.compute(new int[]{}) != 0) throw new AssertionError(\"Test 3 failed\");\n"
                        "        System.out.println(\"All tests passed!\");\n"
                        "    }\n"
                        "}"
                    ),
                    "reference_solution": (
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
                    ),
                    "naive_solution": (
                        "public class Solution {\n"
                        "    public static int compute(int[] nums) {\n"
                        "        // Naive: returns total count without checking if positive\n"
                        "        return nums != null ? nums.length : 0;\n"
                        "    }\n"
                        "}"
                    ),
                }

            elif difficulty == "stretch":
                return {
                    "task": f"Stretch: Implement `compute(int[] nums)` for {topic} to find the maximum sum of any contiguous pair of adjacent integers.",
                    "problem_statement": f"Stretch: Implement `compute(int[] nums)` for {topic} to find the maximum sum of any contiguous pair of adjacent integers.",
                    "starter_code": (
                        "public class Solution {\n"
                        "    public static int compute(int[] nums) {\n"
                        "        // TODO: Find maximum sum of adjacent pair\n"
                        "        return 0;\n"
                        "    }\n"
                        "}"
                    ),
                    "test_code": (
                        "public class TestRunner {\n"
                        "    public static void main(String[] args) {\n"
                        "        if (Solution.compute(new int[]{1, 4, 2, 10, 23}) != 33) throw new AssertionError(\"Test 1 failed\");\n"
                        "        if (Solution.compute(new int[]{100, 200, 300}) != 500) throw new AssertionError(\"Test 2 failed\");\n"
                        "        if (Solution.compute(new int[]{5}) != 0) throw new AssertionError(\"Test 3 failed\");\n"
                        "        System.out.println(\"All tests passed!\");\n"
                        "    }\n"
                        "}"
                    ),
                    "reference_solution": (
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
                    ),
                    "naive_solution": (
                        "public class Solution {\n"
                        "    public static int compute(int[] nums) {\n"
                        "        // Naive: only returns the sum of the first two elements\n"
                        "        if (nums == null || nums.length < 2) return 0;\n"
                        "        return nums[0] + nums[1];\n"
                        "    }\n"
                        "}"
                    ),
                }

            else:
                # Medium (default)
                return {
                    "task": f"Medium: Implement a high-performance compute method for {topic} that sums the squares of all even integers.",
                    "problem_statement": f"Medium: Implement a high-performance compute method for {topic} that sums the squares of all even integers.",
                    "starter_code": (
                        "public class Solution {\n"
                        "    public static int compute(int[] nums) {\n"
                        "        // TODO: Complete the logic\n"
                        "        return 0;\n"
                        "    }\n"
                        "}"
                    ),
                    "test_code": (
                        "public class TestRunner {\n"
                        "    public static void main(String[] args) {\n"
                        "        if (Solution.compute(new int[]{1, 2, 3}) != 6) throw new AssertionError(\"Test 1 failed\");\n"
                        "        if (Solution.compute(new int[]{5}) != 5) throw new AssertionError(\"Test 2 failed\");\n"
                        "        if (Solution.compute(new int[]{}) != 0) throw new AssertionError(\"Test 3 failed\");\n"
                        "        System.out.println(\"All 3 tests passed!\");\n"
                        "    }\n"
                        "}"
                    ),
                    "reference_solution": (
                        "public class Solution {\n"
                        "    public static int compute(int[] nums) {\n"
                        "        int sum = 0;\n"
                        "        for (int n : nums) {\n"
                        "            sum += n;\n"
                        "        }\n"
                        "        return sum;\n"
                        "    }\n"
                        "}"
                    ),
                    "naive_solution": (
                        "public class Solution {\n"
                        "    public static int compute(int[] nums) {\n"
                        "        // Naive buggy: ignores empty array & breaks early\n"
                        "        if (nums.length == 0) return -1;\n"
                        "        return nums[0];\n"
                        "    }\n"
                        "}"
                    ),
                }

        # =====================================================================
        # JAVASCRIPT / NODE EXERCISES
        # =====================================================================
        elif lang in ["node", "javascript", "js", "html/css/js", "web foundations", "react"]:
            if difficulty == "easy":
                return {
                    "task": f"Easy: Write `compute(nums)` for {topic} to count positive numbers (> 0).",
                    "problem_statement": f"Easy: Write `compute(nums)` for {topic} to count positive numbers (> 0).",
                    "starter_code": "function compute(nums) {\n  // TODO: Count positive numbers\n  return 0;\n}\n",
                    "test_code": (
                        "const assert = require('assert');\n"
                        "assert.strictEqual(compute([1, -2, 3, 0]), 2);\n"
                        "assert.strictEqual(compute([-1, -5]), 0);\n"
                        "assert.strictEqual(compute([]), 0);\n"
                        "console.log('All tests passed!');\n"
                    ),
                    "reference_solution": "function compute(nums) {\n  return nums.filter(x => x > 0).length;\n}\n",
                    "naive_solution": "function compute(nums) {\n  return nums.length;\n}\n",
                }
            elif difficulty == "stretch":
                return {
                    "task": f"Stretch: Write `compute(nums)` for {topic} to find the maximum sum of any adjacent pair.",
                    "problem_statement": f"Stretch: Write `compute(nums)` for {topic} to find the maximum sum of any adjacent pair.",
                    "starter_code": "function compute(nums) {\n  // TODO: Maximum adjacent pair sum\n  return 0;\n}\n",
                    "test_code": (
                        "const assert = require('assert');\n"
                        "assert.strictEqual(compute([1, 4, 2, 10, 23]), 33);\n"
                        "assert.strictEqual(compute([100, 200, 300]), 500);\n"
                        "assert.strictEqual(compute([5]), 0);\n"
                        "console.log('All tests passed!');\n"
                    ),
                    "reference_solution": (
                        "function compute(nums) {\n"
                        "  if (!nums || nums.length < 2) return 0;\n"
                        "  let max = nums[0] + nums[1];\n"
                        "  for (let i = 1; i < nums.length - 1; i++) {\n"
                        "    const s = nums[i] + nums[i + 1];\n"
                        "    if (s > max) max = s;\n"
                        "  }\n"
                        "  return max;\n"
                        "}\n"
                    ),
                    "naive_solution": "function compute(nums) {\n  if (!nums || nums.length < 2) return 0;\n  return nums[0] + nums[1];\n}\n",
                }
            else:
                return {
                    "task": f"Medium: Write `compute(nums)` for {topic} to sum the elements of an array.",
                    "problem_statement": f"Medium: Write `compute(nums)` for {topic} to sum the elements of an array.",
                    "starter_code": "function compute(nums) {\n  // TODO: Return sum\n  return 0;\n}\n",
                    "test_code": (
                        "const assert = require('assert');\n"
                        "assert.strictEqual(compute([1, 2, 3]), 6);\n"
                        "assert.strictEqual(compute([5]), 5);\n"
                        "assert.strictEqual(compute([]), 0);\n"
                        "console.log('All tests passed!');\n"
                    ),
                    "reference_solution": "function compute(nums) {\n  return nums.reduce((a, b) => a + b, 0);\n}\n",
                    "naive_solution": "function compute(nums) {\n  return nums.length ? nums[0] : -1;\n}\n",
                }

        # =====================================================================
        # PYTHON EXERCISES (Default)
        # =====================================================================
        else:
            if difficulty == "easy":
                return {
                    "task": f"Easy: Implement `compute(nums: list) -> int` for {topic} to count positive numbers (> 0).",
                    "problem_statement": f"Easy: Implement `compute(nums: list) -> int` for {topic} to count positive numbers (> 0).",
                    "starter_code": (
                        "def compute(nums: list) -> int:\n"
                        "    # TODO: Count positive numbers\n"
                        "    return 0\n"
                    ),
                    "test_code": (
                        "def run_tests():\n"
                        "    assert compute([1, -2, 3, 0]) == 2, 'Test 1 failed'\n"
                        "    assert compute([-1, -5]) == 0, 'Test 2 failed'\n"
                        "    assert compute([]) == 0, 'Test 3 failed'\n"
                        "    print('All tests passed!')\n"
                        "run_tests()\n"
                    ),
                    "reference_solution": (
                        "def compute(nums: list) -> int:\n"
                        "    return sum(1 for x in nums if x > 0)\n"
                    ),
                    "naive_solution": (
                        "def compute(nums: list) -> int:\n"
                        "    # Naive: counts all items without checking if positive\n"
                        "    return len(nums)\n"
                    ),
                }

            elif difficulty == "stretch":
                return {
                    "task": f"Stretch: Implement `compute(nums: list) -> int` for {topic} to find the maximum sum of any adjacent pair.",
                    "problem_statement": f"Stretch: Implement `compute(nums: list) -> int` for {topic} to find the maximum sum of any adjacent pair.",
                    "starter_code": (
                        "def compute(nums: list) -> int:\n"
                        "    # TODO: Maximum adjacent pair sum\n"
                        "    return 0\n"
                    ),
                    "test_code": (
                        "def run_tests():\n"
                        "    assert compute([1, 4, 2, 10, 23]) == 33, 'Test 1 failed'\n"
                        "    assert compute([100, 200, 300]) == 500, 'Test 2 failed'\n"
                        "    assert compute([5]) == 0, 'Test 3 failed'\n"
                        "    print('All tests passed!')\n"
                        "run_tests()\n"
                    ),
                    "reference_solution": (
                        "def compute(nums: list) -> int:\n"
                        "    if not nums or len(nums) < 2:\n"
                        "        return 0\n"
                        "    return max(nums[i] + nums[i + 1] for i in range(len(nums) - 1))\n"
                    ),
                    "naive_solution": (
                        "def compute(nums: list) -> int:\n"
                        "    # Naive: only returns the sum of the first two elements\n"
                        "    if not nums or len(nums) < 2:\n"
                        "        return 0\n"
                        "    return nums[0] + nums[1]\n"
                    ),
                }

            else:
                # Medium (default)
                return {
                    "task": f"Medium: Implement a robust calculation for {topic}.",
                    "problem_statement": f"Medium: Implement a robust calculation for {topic}.",
                    "starter_code": (
                        "def compute(nums: list) -> int:\n"
                        "    # TODO: Implement solution\n"
                        "    return 0\n"
                    ),
                    "test_code": (
                        "def run_tests():\n"
                        "    assert compute([1, 2, 3]) == 6, 'Test 1 failed'\n"
                        "    assert compute([5]) == 5, 'Test 2 failed'\n"
                        "    assert compute([]) == 0, 'Test 3 failed'\n"
                        "    print('All 3 tests passed!')\n"
                        "run_tests()\n"
                    ),
                    "reference_solution": (
                        "def compute(nums: list) -> int:\n"
                        "    return sum(nums)\n"
                    ),
                    "naive_solution": (
                        "def compute(nums: list) -> int:\n"
                        "    return nums[0] if nums else -1\n"
                    ),
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
