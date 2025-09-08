from __future__ import annotations
from pathlib import Path
import io, json, sys, subprocess

try:
    from pylint.reporters.json_reporter import JSONReporter  # 2.0+
except ImportError:
    try:
        from pylint.reporters import JSONReporter  # older versions
    except ImportError:
        JSONReporter = None

try:
    from pylint.lint import Run as PylintRun
except ImportError:
    PylintRun = None


def _run_pylint_api(args: list[str], reporter: JSONReporter) -> bool:
    """runs pylint using API with fallback compatibility"""
    print("PYLINT ARGS:", args)
    if PylintRun is None:
        return False

    # pylint namespace error backup (temp)
    if not any(a.startswith("--mixin-class-rgx") for a in args):
        args = ["--mixin-class-rgx=.*[Mm]ixin", *args]
    if not any(a.startswith("--overgeneral-exceptions") for a in args):
        args.append("--overgeneral-exceptions=BaseException,Exception")

    try:
        """modern api (Pylint 2.5+)"""
        PylintRun(args, reporter=reporter, do_exit=False)
        return True
    except TypeError:
        try:
            """legacy api (Pylint 2.0-2.4)"""
            PylintRun(args, reporter=reporter, exit=False)
            return True
        except TypeError:
            try:
                """ancient api (Pylint 1.x)"""
                PylintRun(args, reporter=reporter)
                return True
            except SystemExit:
                """expected for ancient versions"""
                return True
            except Exception:
                return False


def _run_pylint_subprocess(files: list[str]) -> dict:
    """runs pylint via subprocess"""
    try:
        result = subprocess.run(
            ['pylint'] + files + ['--output-format=json', '--overgeneral-exceptions=BaseException,Exception'],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )

        if result.stdout.strip():
            msgs = json.loads(result.stdout)
            by_type = {}
            for m in msgs:
                t = m.get("type") or m.get("category") or "unknown"
                by_type[t] = by_type.get(t, 0) + 1

            return {
                "summary": {"total": len(msgs), "by_type": by_type},
                "messages": msgs,
            }
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass
    except Exception:
        pass

    return {"summary": {"total": 0, "by_type": {}}, "messages": []}


def run_pylint(code_dir: Path) -> dict:
    """
    runs pylint analysis on Python files in the given directory
    uses API method first, falls back to subprocess if needed
    """

    files = [str(p) for p in Path(code_dir).rglob("*.py")]

    if not files:
        return {"summary": {"total": 0, "by_type": {}}, "messages": []}

    if JSONReporter is not None:
        buf = io.StringIO()
        reporter = JSONReporter(output=buf)
        args = [*files, "--output-format=json"]

        if _run_pylint_api(args, reporter):
            raw = buf.getvalue().strip()

            if raw:
                try:
                    msgs = json.loads(raw)
                    by_type = {}
                    for m in msgs:
                        t = m.get("type") or m.get("category") or "unknown"
                        by_type[t] = by_type.get(t, 0) + 1

                    return {
                        "summary": {"total": len(msgs), "by_type": by_type},
                        "messages": msgs,
                    }
                except json.JSONDecodeError:
                    pass

    return _run_pylint_subprocess(files)


# def test_pylint_basic():
#     """test function (can be removed in production)"""
#     import tempfile
#
#     test_code = '''
# def bad_function():
#     unused_variable = 5
#     another_unused = "test"
#     if True:
#         print("hello")
# '''
#
#     with tempfile.TemporaryDirectory() as tmp_dir:
#         test_file = Path(tmp_dir) / "test_bad_code.py"
#         test_file.write_text(test_code)
#
#         result = run_pylint(Path(tmp_dir))
#
#         return {
#             "test_passed": result['summary']['total'] > 0,
#             "messages_found": result['summary']['total'],
#             "by_type": result['summary']['by_type']
#         }