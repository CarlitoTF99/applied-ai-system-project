"""
Regenerate the execution evidence in evidence/ (offline only; never calls the Gemini API).

    python -m scripts.capture_evidence

Each command runs in a fresh subprocess with the current Python interpreter, and its combined stdout
and stderr are saved to evidence/<name>.txt, with the command line at the top. evidence/09_llm_run.txt
is a saved copy of real logged Gemini runs and is left untouched.
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = ROOT / "evidence"
TIMEOUT_SECONDS = 600
PROFILE_BANNER = "#" * 54 + "\nPROFILE:"

# (file name, arguments after "python", command shown in the file)
COMMANDS = [
    ("01_chill_study", ["-m", "src.agent", "something chill for studying on a rainy night", "--offline", "--verbose"],
     'python -m src.agent "something chill for studying on a rainy night" --offline --verbose'),
    ("02_gym", ["-m", "src.agent", "hype songs for the gym", "--offline"],
     'python -m src.agent "hype songs for the gym" --offline'),
    ("03_kpop_repair", ["-m", "src.agent", "k-pop for a party", "--offline", "--verbose"],
     'python -m src.agent "k-pop for a party" --offline --verbose'),
    ("04_guardrail_empty", ["-m", "src.agent", "", "--offline"],
     'python -m src.agent "" --offline'),
    ("05_guardrail_offtopic", ["-m", "src.agent", "what's the weather tomorrow", "--offline"],
     'python -m src.agent "what\'s the weather tomorrow" --offline'),
    ("06_original_cli", ["-m", "src.main", "--table", "--diverse"],
     "python -m src.main --table --diverse"),
    ("07_eval", ["-m", "eval.run_eval"],
     "python -m eval.run_eval"),
    ("08_pytest", ["-m", "pytest", "-q"],
     "pytest -q"),
]


def first_profile_only(output: str) -> str:
    """Keep the header and the first profile of src.main's output; note how many were trimmed."""
    total = output.count(PROFILE_BANNER)
    second = output.find(PROFILE_BANNER, output.find(PROFILE_BANNER) + 1)
    if second == -1:
        return output
    return output[:second].rstrip() + f"\n\n[trimmed: first of {total} profiles shown; run the command to see all]\n"


POST_PROCESS = {"06_original_cli": first_profile_only}


def run(args):
    """Run one command offline; return (exit code, combined output with LF line endings)."""
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, *args], cwd=ROOT, env=env, timeout=TIMEOUT_SECONDS,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    text = proc.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")
    return proc.returncode, text


def main() -> int:
    EVIDENCE_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    for name, args, shown in COMMANDS:
        code, output = run(args)
        output = POST_PROCESS.get(name, lambda text: text)(output)
        header = (f"$ {shown}\n"
                  f"# captured {stamp} by `python -m scripts.capture_evidence` (offline, no API calls)\n"
                  f"# exit code: {code}\n\n")
        path = EVIDENCE_DIR / f"{name}.txt"
        path.write_text(header + output.rstrip() + "\n", encoding="utf-8", newline="\n")
        print(f"{path.relative_to(ROOT)}  (exit {code}, {len(output.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
