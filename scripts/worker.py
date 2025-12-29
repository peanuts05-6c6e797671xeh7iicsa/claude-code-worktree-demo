#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import tempfile
from pathlib import Path
from string import Template


class Worker:
    def __init__(self, queue_dir, max_attempts=5):
        self.queue_dir = Path(queue_dir)
        self.max_attempts = max_attempts
        self.pool = self.queue_dir / "pool"
        self.inprogress = self.queue_dir / "inprogress"
        self.done = self.queue_dir / "done"
        self.failed = self.queue_dir / "failed"

    def claim_job(self):
        for job_file in sorted(self.pool.glob("*.json")):
            target = self.inprogress / job_file.name
            try:
                job_file.rename(target)
                return target
            except OSError:
                continue
        return None

    def finish_job(self, job_path, success):
        dest_dir = self.done if success else self.failed
        dest_dir.mkdir(parents=True, exist_ok=True)
        job_path.rename(dest_dir / job_path.name)

    def run(self, prompt_template_path):
        prompt_template = Path(prompt_template_path).read_text()

        while True:
            job_path = self.claim_job()
            if not job_path:
                print("No more jobs in pool")
                break

            print(f"Processing: {job_path.name}")
            job = json.loads(job_path.read_text())

            success = self.process_job(job, prompt_template)
            self.finish_job(job_path, success)

            status = "done" if success else "failed"
            print(f"  -> {status}")

    def process_job(self, job, prompt_template):
        customer_id = job["customer_id"]
        branch = f"job/{customer_id}"
        success = False

        self.git("checkout", "main")
        self.git("checkout", "-B", branch)

        try:
            success = self.run_agent_loop(job, prompt_template)
            if success:
                self.git("add", f"extractors/{customer_id}.yaml", f"previews/{customer_id}.txt")
                self.git("commit", "-m", f"Add extractor for {customer_id}")
        finally:
            self.git("checkout", "main")
            if not success:
                self.git("branch", "-D", branch)
            self.git("reset", "--hard")
            self.git("clean", "-fd")

        return success

    def run_agent_loop(self, job, prompt_template):
        prompt = self.build_prompt(job, prompt_template)

        for attempt in range(1, self.max_attempts + 1):
            print(f"  Attempt {attempt}/{self.max_attempts}")

            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                f.write(prompt)
                prompt_file = f.name

            try:
                subprocess.run(
                    ["claude", "-p", prompt_file, "--allowedTools", "Bash,Read,Write"],
                    timeout=300,
                )
            except subprocess.TimeoutExpired:
                print("  Timeout")
                continue
            finally:
                os.unlink(prompt_file)

            # Claude が PDCA でファイル作成・テスト済み、結果を検証するだけ (とても簡易。むしろなくても良いかも)
            if self.validate_result(job):
                return True

        return False

    def build_prompt(self, job, template):
        customer_id = job["customer_id"]
        fixture_dir = Path("fixtures") / customer_id
        fixture_paths = "\n  ".join(str(p) for p in sorted(fixture_dir.glob("*.txt")))

        return Template(template).safe_substitute(
            customer_id=customer_id,
            fixture_paths=fixture_paths,
            extract_command=f"python scripts/extract.py {customer_id}",
        )

    def validate_result(self, job):
        customer_id = job["customer_id"]
        preview_path = Path("previews") / f"{customer_id}.txt"

        if not preview_path.exists():
            return False

        content = preview_path.read_text().strip()
        return bool(content)

    def git(self, *args):
        subprocess.run(["git"] + list(args), capture_output=True)


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <queue_dir> <prompt_template>", file=sys.stderr)
        sys.exit(1)

    queue_dir = sys.argv[1]
    prompt_template = sys.argv[2]
    max_attempts = int(os.environ.get("MAX_ATTEMPTS", "5"))

    worker = Worker(queue_dir, max_attempts)
    worker.run(prompt_template)


if __name__ == "__main__":
    main()
