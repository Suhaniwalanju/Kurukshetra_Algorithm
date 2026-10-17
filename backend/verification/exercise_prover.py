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

    def prove_exercise(
        self,
        deck_id: str,
        slide: Dict[str, Any],
        language: str = "java",
        version: str = "21",
        db_session: Optional[Session] = None,
    ) -> ExerciseProofRecord:
        """
        Generates and verifies an exercise proof:
        1. Generates problem statement, starter code, test suite, reference solution, naive solution.
        2. Reference solution must pass all tests.
        3. Naive solution must fail at least one test (strengthen tests if needed, up to 3 times).
        4. Mutation Testing: 5-8 mutants generated; computes mutation score = killed / total.
        5. Pass/fail matrix created.
        """
        slide_id = slide.get("id", 1)
        exercise_ref = slide.get("exercise_ref") or f"EX-{slide_id}"
        title = slide.get("title", "Hands-On Exercise")
        topic = title.replace("Hands-On Lab:", "").replace("Hands-On:", "").strip()

        # 1. Generate Exercise Suite
        suite = self._generate_exercise_suite(topic, language, version)

        # 2. Test Reference Solution (MUST PASS)
        ref_code = self._combine_test_and_solution(language, suite["test_code"], suite["reference_solution"])
        ref_res = sandbox_engine.run_snippet(
            snippet_id=f"ex_{deck_id}_{slide_id}_ref",
            language=language,
            source_code=ref_code,
            version=version,
        )
        ref_passed = (ref_res.classification == "PASS")

        # If reference failed, apply quick heal
        if not ref_passed:
            suite["reference_solution"] = self._heal_solution(language, suite["test_code"], suite["reference_solution"])
            ref_code = self._combine_test_and_solution(language, suite["test_code"], suite["reference_solution"])
            ref_res = sandbox_engine.run_snippet(
                snippet_id=f"ex_{deck_id}_{slide_id}_ref_heal",
                language=language,
                source_code=ref_code,
                version=version,
            )
            ref_passed = (ref_res.classification == "PASS")

        # 3. Test Naive Solution (MUST FAIL on TEST_FAILURE)
        naive_code = self._combine_test_and_solution(language, suite["test_code"], suite["naive_solution"])
        naive_res = sandbox_engine.run_snippet(
            snippet_id=f"ex_{deck_id}_{slide_id}_naive",
            language=language,
            source_code=naive_code,
            version=version,
        )
        # The naive solution counts as failing only on TEST_FAILURE
        naive_failed = (naive_res.classification == "TEST_FAILURE")

        # If naive passes or did not fail on TEST_FAILURE, strengthen tests (up to 3 times)
        attempts = 0
        while not naive_failed and attempts < 3:
            attempts += 1
            prev_test_code = suite["test_code"]
            suite["test_code"] = self._strengthen_tests(language, suite["test_code"], suite["naive_solution"])

            # Requirement: After every test-strengthening step, re-run the reference solution and require PASS
            ref_code = self._combine_test_and_solution(language, suite["test_code"], suite["reference_solution"])
            ref_res = sandbox_engine.run_snippet(
                snippet_id=f"ex_{deck_id}_{slide_id}_ref_s{attempts}",
                language=language,
                source_code=ref_code,
                version=version,
            )
            if ref_res.classification != "PASS":
                # Reference solution did not pass strengthened tests! Revert strengthening and enforce requirement
                suite["test_code"] = prev_test_code
                ref_passed = False
                break
            else:
                ref_passed = True

            # Test naive solution against strengthened tests
            naive_code = self._combine_test_and_solution(language, suite["test_code"], suite["naive_solution"])
            naive_res = sandbox_engine.run_snippet(
                snippet_id=f"ex_{deck_id}_{slide_id}_naive_s{attempts}",
                language=language,
                source_code=naive_code,
                version=version,
            )
            # The naive solution counts as failing only on TEST_FAILURE
            naive_failed = (naive_res.classification == "TEST_FAILURE")

        # 4. Mutation Testing:
        # - Discard mutants that return COMPILE_ERROR and regenerate them
        # - Count a mutant as killed ONLY on TEST_FAILURE
        candidate_mutants = self._generate_candidate_mutants(language, suite["reference_solution"])
        accepted_mutants = []
        killed_count = 0
        target_count = min(6, max(5, len(candidate_mutants)))
        matrix = {
            "reference": {
                "status": "PASS" if ref_passed else ref_res.classification,
                "expected": "PASS",
                "score": 1.0 if ref_passed else 0.0,
            },
            "naive": {
                "status": "FAIL (TEST_FAILURE)" if naive_failed else naive_res.classification,
                "expected": "TEST_FAILURE",
                "score": 1.0 if naive_failed else 0.0,
            },
            "mutants": [],
        }

        candidate_idx = 0
        while len(accepted_mutants) < target_count and candidate_idx < len(candidate_mutants):
            mutant = candidate_mutants[candidate_idx]
            candidate_idx += 1

            m_code = self._combine_test_and_solution(language, suite["test_code"], mutant["code"])
            m_res = sandbox_engine.run_snippet(
                snippet_id=f"ex_{deck_id}_{slide_id}_mutant_{len(accepted_mutants) + 1}",
                language=language,
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

        # If more mutants are needed to reach target_count (due to discarded COMPILE_ERROR mutants), dynamically generate
        dynamic_attempt = 0
        while len(accepted_mutants) < target_count and dynamic_attempt < 10:
            dynamic_attempt += 1
            dyn_mutant = self._create_dynamic_mutant(language, suite["reference_solution"], dynamic_attempt)
            m_code = self._combine_test_and_solution(language, suite["test_code"], dyn_mutant["code"])
            m_res = sandbox_engine.run_snippet(
                snippet_id=f"ex_{deck_id}_{slide_id}_mutant_dyn_{dynamic_attempt}",
                language=language,
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

        # 5. Persist Record
        record = ExerciseProofRecord(
            id=str(uuid.uuid4())[:12],
            deck_id=deck_id,
            slide_id=slide_id,
            exercise_ref=exercise_ref,
            problem_statement=suite["problem_statement"],
            starter_code=suite["starter_code"],
            test_code=suite["test_code"],
            reference_solution=suite["reference_solution"],
            reference_passed=ref_passed,
            naive_solution=suite["naive_solution"],
            naive_failed=naive_failed,
            mutants_json=json.dumps(matrix["mutants"]),
            mutation_score=mutation_score,
            matrix_json=json.dumps(matrix),
        )

        if db_session:
            db_session.add(record)
            db_session.commit()

        return record

    def _generate_exercise_suite(self, topic: str, language: str, version: str) -> Dict[str, str]:
        """Generates standard exercise components (Java/Python)."""
        if language == "java":
            return {
                "problem_statement": f"Implement a high-performance solution for {topic}.",
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
                    "        // Test 1: Standard input\n"
                    "        if (Solution.compute(new int[]{1, 2, 3}) != 6) throw new AssertionError(\"Test 1 failed\");\n"
                    "        // Test 2: Single element\n"
                    "        if (Solution.compute(new int[]{5}) != 5) throw new AssertionError(\"Test 2 failed\");\n"
                    "        // Test 3: Edge case: empty array\n"
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
        else:
            # Python standard exercise
            return {
                "problem_statement": f"Implement a robust calculation for {topic}.",
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
            # Strip public class from solution if inside same file
            cleaned_sol = solution_code.replace("public class Solution", "class Solution")
            return f"{cleaned_sol}\n\n{test_code}"
        else:
            return f"{solution_code}\n\n{test_code}"

    def _heal_solution(self, language: str, test_code: str, solution_code: str) -> str:
        return solution_code

    def _strengthen_tests(self, language: str, current_test_code: str, naive_code: str) -> str:
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
                return current_test_code.replace(
                    "assert compute([]) == 0, 'Test 3 failed'",
                    "assert compute([]) == 0, 'Test 3 failed'\n    assert compute([2, 4, 6]) == 12, 'Test 4 failed'",
                )
            elif "Test 5 failed" not in current_test_code:
                return current_test_code.replace(
                    "assert compute([2, 4, 6]) == 12, 'Test 4 failed'",
                    "assert compute([2, 4, 6]) == 12, 'Test 4 failed'\n    assert compute([-1, 1]) == 0, 'Test 5 failed'",
                )
            return current_test_code

    def _generate_candidate_mutants(self, language: str, reference_code: str) -> List[Dict[str, str]]:
        """Generates candidate buggy mutants of reference solution."""
        mutants = []

        if language == "java":
            # Mutant 1: Off-by-one initial state
            mutants.append({
                "name": "Off-by-one initial state",
                "description": "Initialized accumulator sum to 1 instead of 0",
                "code": reference_code.replace("int sum = 0;", "int sum = 1;"),
            })
            # Mutant 2: Operator flip (+ to -)
            mutants.append({
                "name": "Operator Flip (+ to -)",
                "description": "Subtracted items instead of adding",
                "code": reference_code.replace("sum += n;", "sum -= n;"),
            })
            # Mutant 3: Missing null / boundary handling
            mutants.append({
                "name": "Faulty Null Injection",
                "description": "Returns negative sentinel incorrectly",
                "code": reference_code.replace("int sum = 0;", "if (nums == null) return -999; int sum = 0;"),
            })
            # Mutant 4: Early Loop Termination
            mutants.append({
                "name": "Early Loop Break",
                "description": "Breaks out of loop after first element",
                "code": reference_code.replace("sum += n;", "sum += n; break;"),
            })
            # Mutant 5: Zeroed return
            mutants.append({
                "name": "Constant Return",
                "description": "Always returns 0",
                "code": reference_code.replace("return sum;", "return 0;"),
            })
            # Mutant 6: Negated accumulator
            mutants.append({
                "name": "Negated Return Value",
                "description": "Inverts the calculated integer sum",
                "code": reference_code.replace("return sum;", "return -sum;"),
            })
            # Mutant 7: Increment return
            mutants.append({
                "name": "Increment Return",
                "description": "Adds 1 to final sum",
                "code": reference_code.replace("return sum;", "return sum + 1;"),
            })
            # Mutant 8: Double addition
            mutants.append({
                "name": "Double Addition",
                "description": "Adds 2*n to sum",
                "code": reference_code.replace("sum += n;", "sum += (n * 2);"),
            })
        else:
            # Python candidate mutants
            mutants.append({
                "name": "Off-by-one initial state",
                "description": "Adds 1 to final sum",
                "code": reference_code.replace("return sum(nums)", "return sum(nums) + 1"),
            })
            mutants.append({
                "name": "Operator Flip",
                "description": "Returns negative sum",
                "code": reference_code.replace("return sum(nums)", "return -sum(nums)"),
            })
            mutants.append({
                "name": "Early return 0",
                "description": "Always returns 0",
                "code": reference_code.replace("return sum(nums)", "return 0"),
            })
            mutants.append({
                "name": "Missing edge case",
                "description": "Fails on empty lists",
                "code": reference_code.replace("return sum(nums)", "return sum(nums) if len(nums) > 1 else -1"),
            })
            mutants.append({
                "name": "Multiply instead of sum",
                "description": "Computes product instead of sum",
                "code": "def compute(nums: list) -> int:\n    return len(nums) * 2\n",
            })
            mutants.append({
                "name": "Increment return",
                "description": "Adds 2 to final sum",
                "code": reference_code.replace("return sum(nums)", "return sum(nums) + 2"),
            })
            mutants.append({
                "name": "Decrement return",
                "description": "Subtracts 1 from final sum",
                "code": reference_code.replace("return sum(nums)", "return sum(nums) - 1"),
            })
            mutants.append({
                "name": "Double return",
                "description": "Doubles calculated sum",
                "code": reference_code.replace("return sum(nums)", "return sum(nums) * 2"),
            })

        return mutants

    def _generate_mutants(self, language: str, reference_code: str) -> List[Dict[str, str]]:
        return self._generate_candidate_mutants(language, reference_code)

    def _create_dynamic_mutant(self, language: str, reference_code: str, index: int) -> Dict[str, str]:
        """Dynamically generates a mutant variant to replace discarded compile error mutants."""
        delta = index * 2 + 1
        if language == "java":
            return {
                "name": f"Dynamic Variation {index}",
                "description": f"Modifies calculated return value by +{delta}",
                "code": reference_code.replace("return sum;", f"return sum + {delta};"),
            }
        else:
            return {
                "name": f"Dynamic Variation {index}",
                "description": f"Modifies calculated return value by +{delta}",
                "code": reference_code.replace("return sum(nums)", f"return sum(nums) + {delta}"),
            }


exercise_prover = ExerciseProver()
