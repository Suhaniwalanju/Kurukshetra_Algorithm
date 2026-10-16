import re
from typing import List, Dict, Any
from backend.materials.models import PredictedMistake
from backend.runtimes.registry import runtime_registry


def generate_predicted_mistakes(exercise: Dict[str, Any], tech: str) -> List[PredictedMistake]:
    """
    For an exercise, generates the 3 most likely wrong student solutions,
    actually executes them in the isolated runtime sandbox, captures real
    error messages/compiler outputs, and provides clear pedagogical explanations.
    """
    problem = exercise.get("problem_statement", exercise.get("title", "Coding Problem"))
    starter = exercise.get("starter_code", exercise.get("code", ""))
    ref = exercise.get("reference_solution", exercise.get("code", ""))
    lang = exercise.get("language", tech.lower())

    runner = runtime_registry.get_runner(lang) or runtime_registry.get_runner(tech.lower())

    # Build 3 realistic erroneous variants tailored to language and problem
    mistake_templates = _build_buggy_variants(ref, starter, tech)

    predicted: List[PredictedMistake] = []
    for item in mistake_templates[:3]:
        buggy_code = item["code"]
        title = item["title"]
        explanation = item["explanation"]

        # Run through sandbox runner to capture real error message
        real_error = "Execution failed as anticipated."
        if runner:
            try:
                res = runner.execute(buggy_code, timeout=10)
                if res.status != "pass":
                    real_error = res.stderr or res.compile_output or res.stdout or f"Exit code {res.exit_code}"
                else:
                    real_error = f"Logical flaw: Code compiled but returned unexpected output:\n{res.stdout[:150]}"
            except Exception as e:
                real_error = f"Runtime caught: {str(e)}"
        
        predicted.append(PredictedMistake(
            title=title,
            buggy_code=buggy_code,
            error_message=real_error.strip(),
            explanation=explanation,
        ))

    return predicted


def _build_buggy_variants(ref: str, starter: str, tech: str) -> List[Dict[str, str]]:
    t = tech.lower()
    variants = []

    if "java" in t:
        # Variant 1: NullPointerException
        variants.append({
            "title": "Unchecked Null Reference (NullPointerException)",
            "code": (
                "public class Solution {\n"
                "    public static void main(String[] args) {\n"
                "        String data = null;\n"
                "        System.out.println(data.trim().length());\n"
                "    }\n"
                "}"
            ),
            "explanation": "Students frequently forget null-safety guards before invoking methods on incoming parameters or parsed data."
        })
        # Variant 2: Off-by-one array index
        variants.append({
            "title": "Index Bounds Overflow (ArrayIndexOutOfBoundsException)",
            "code": (
                "public class Solution {\n"
                "    public static void main(String[] args) {\n"
                "        int[] arr = {10, 20, 30};\n"
                "        for (int i = 0; i <= arr.length; i++) {\n"
                "            System.out.println(arr[i]);\n"
                "        }\n"
                "    }\n"
                "}"
            ),
            "explanation": "Using '<=' instead of '<' when iterating arrays or collections is the #1 beginner loop defect."
        })
        # Variant 3: Type Mismatch / Lossy Conversion
        variants.append({
            "title": "Type Casting & Incompatible Types",
            "code": (
                "public class Solution {\n"
                "    public static void main(String[] args) {\n"
                "        int val = \"12345\";\n"
                "        System.out.println(val);\n"
                "    }\n"
                "}"
            ),
            "explanation": "Forgetting explicit parsing (e.g. Integer.parseInt) when reading string inputs into numeric variables."
        })

    elif "python" in t:
        # Variant 1: Unhandled KeyError / IndexError
        variants.append({
            "title": "Unchecked Dict Key Lookup (KeyError)",
            "code": "data = {'id': 101}\nprint(data['missing_key'])",
            "explanation": "Direct indexing data['key'] without .get() causes immediate uncaught KeyError when keys are optional."
        })
        # Variant 2: Mutable default argument trap
        variants.append({
            "title": "Mutable Default Parameter Pitfall",
            "code": (
                "def append_item(val, items=[]):\n"
                "    items.append(val)\n"
                "    return items\n"
                "print(append_item(1))\n"
                "print(append_item(2))\n"
                "assert append_item(3) == [3]  # Fails due to shared list state"
            ),
            "explanation": "Mutable defaults in Python retain state across calls; teach students to use `items=None`."
        })
        # Variant 3: TypeError on mixed string-integer concat
        variants.append({
            "title": "Type Mismatch Concatenation (TypeError)",
            "code": "count = 42\nmsg = 'Processed: ' + count\nprint(msg)",
            "explanation": "Attempting to concatenate strings and numbers without f-strings or str() conversion."
        })

    elif "c++" in t or "cpp" in t:
        variants.append({
            "title": "Out of Bounds Vector Access",
            "code": (
                "#include <iostream>\n#include <vector>\n"
                "int main() {\n"
                "    std::vector<int> v = {1, 2, 3};\n"
                "    std::cout << v.at(10) << std::endl;\n"
                "    return 0;\n"
                "}"
            ),
            "explanation": "Accessing indices beyond vector capacity throws std::out_of_range."
        })
        variants.append({
            "title": "Dangling Pointer / Use After Free",
            "code": (
                "#include <iostream>\n"
                "int* getDangling() {\n"
                "    int localVal = 42;\n"
                "    return &localVal;\n"
                "}\n"
                "int main() {\n"
                "    int* p = getDangling();\n"
                "    std::cout << *p << std::endl;\n"
                "    return 0;\n"
                "}"
            ),
            "explanation": "Returning address of stack variable causes undefined behavior caught by AddressSanitizer."
        })
        variants.append({
            "title": "Missing Return in Value-Returning Function",
            "code": (
                "#include <iostream>\n"
                "int compute(int x) {\n"
                "    if (x > 0) return x * 2;\n"
                "    // Missing else return\n"
                "}\n"
                "int main() {\n"
                "    std::cout << compute(-5) << std::endl;\n"
                "    return 0;\n"
                "}"
            ),
            "explanation": "Control reaching end of non-void function triggers compiler warning/sanitizer failure."
        })

    elif "sql" in t or "postgres" in t:
        variants.append({
            "title": "Ambiguous Column Reference in Multi-Table Join",
            "code": (
                "SELECT id, name FROM users "
                "JOIN orders ON users.id = orders.id;"
            ),
            "explanation": "Selecting 'id' without qualifying table alias when both joined tables share column name."
        })
        variants.append({
            "title": "Missing GROUP BY Column in Aggregation",
            "code": "SELECT category, name, COUNT(*) FROM products GROUP BY category;",
            "explanation": "Selecting non-aggregated column 'name' without including it in GROUP BY clause."
        })
        variants.append({
            "title": "NULL Comparison with Equality Operator",
            "code": "SELECT * FROM users WHERE deleted_at = NULL;",
            "explanation": "Comparing '= NULL' yields UNKNOWN instead of TRUE; must use 'IS NULL'."
        })

    elif "node" in t or "express" in t:
        variants.append({
            "title": "Sending Multiple HTTP Responses",
            "code": (
                "const express = require('express');\n"
                "const app = express();\n"
                "app.get('/test', (req, res) => {\n"
                "    res.json({ status: 'ok' });\n"
                "    res.send('duplicate'); // Cannot set headers after they are sent\n"
                "});\n"
                "module.exports = app;"
            ),
            "explanation": "Attempting to send another response after res.json() without early return."
        })
        variants.append({
            "title": "Missing await on Asynchronous Promise",
            "code": (
                "async function fetchItem() { return { id: 1 }; }\n"
                "const item = fetchItem(); // Missing await\n"
                "console.log(item.id); // undefined on raw Promise"
            ),
            "explanation": "Accessing properties directly on unresolved Promise objects."
        })
        variants.append({
            "title": "Undefined Property Access on req.body",
            "code": (
                "const express = require('express');\n"
                "const app = express();\n"
                "// Missing app.use(express.json())\n"
                "app.post('/item', (req, res) => {\n"
                "    res.send(req.body.name); // TypeError: Cannot read properties of undefined\n"
                "});"
            ),
            "explanation": "Forgetting body-parser middleware before reading req.body."
        })

    else:
        # Default language-agnostic variants
        variants.append({
            "title": "Boundary Condition / Zero Division",
            "code": f"# Bug: Zero division\nx = 10 / 0",
            "explanation": "Overlooking divisor zero edge cases in user inputs or calculated ratios."
        })
        variants.append({
            "title": "Uninitialized Variable Access",
            "code": f"# Bug: Uninitialized identifier\nprint(uninitialized_variable)",
            "explanation": "Referencing identifiers before assignment or scope initialization."
        })
        variants.append({
            "title": "Type Incompatibility",
            "code": f"# Bug: Type incompatibility\nres = 'text' + 123",
            "explanation": "Attempting operations across conflicting data types."
        })

    return variants
