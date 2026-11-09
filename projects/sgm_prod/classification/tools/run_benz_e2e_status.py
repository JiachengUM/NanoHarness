from __future__ import annotations

import argparse
import datetime as dt
import shlex
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_ASSET_DIR = Path("projects/sgm_prod/classification/assets/benz")
DEFAULT_REPORT_ROOT = Path("projects/sgm_prod/classification/reports/benz_e2e_status")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the BENZ router status checks end-to-end: exact assets, "
            "rule-only baseline, and exact-off/LLM-on evaluation."
        )
    )
    parser.add_argument(
        "--asset-dir",
        type=Path,
        default=DEFAULT_ASSET_DIR,
        help="Router asset profile directory. Defaults to the BENZ profile.",
    )
    parser.add_argument(
        "--domain",
        choices=("all", "benz", "byd"),
        default="benz",
        help="Domain filter for rule-only and LLM evaluations.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        help="Output directory. Defaults to reports/benz_e2e_status/<timestamp>.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Concurrent requests for the LLM end-to-end evaluator.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional LLM evaluator case limit. Default 0 means all cases.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=200,
        help="LLM evaluator progress print interval. Use 0 to disable.",
    )
    parser.add_argument(
        "--print-failures",
        type=int,
        default=30,
        help="Number of LLM evaluator failures printed in terminal output.",
    )
    parser.add_argument(
        "--skip-exact",
        action="store_true",
        help="Skip exact asset health check.",
    )
    parser.add_argument(
        "--skip-rule-only",
        action="store_true",
        help="Skip exact-off/LLM-off rule baseline.",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip exact-off/LLM-on end-to-end evaluation.",
    )
    args = parser.parse_args()

    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    if args.progress_every < 0:
        parser.error("--progress-every must be >= 0")
    if args.print_failures < 0:
        parser.error("--print-failures must be >= 0")
    return args


def _resolve_from_repo(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _display_cmd(cmd: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def _run(cmd: list[str], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n==> {_display_cmd(cmd)}")
    print(f"    log: {log_path}")
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            cmd,
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            log_file.write(line)
        return_code = process.wait()
    if return_code != 0:
        raise SystemExit(f"command failed with exit code {return_code}: {_display_cmd(cmd)}")


def _write_manifest(path: Path, *, asset_dir: Path, args: argparse.Namespace) -> None:
    path.write_text(
        "\n".join(
            [
                f"created_at={dt.datetime.now().isoformat(timespec='seconds')}",
                f"repo_root={REPO_ROOT}",
                f"asset_dir={asset_dir}",
                f"domain={args.domain}",
                f"concurrency={args.concurrency}",
                f"limit={args.limit}",
                f"progress_every={args.progress_every}",
                f"print_failures={args.print_failures}",
                f"skip_exact={args.skip_exact}",
                f"skip_rule_only={args.skip_rule_only}",
                f"skip_llm={args.skip_llm}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    args = _parse_args()
    asset_dir = _resolve_from_repo(args.asset_dir)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = _resolve_from_repo(args.report_dir or DEFAULT_REPORT_ROOT / timestamp)
    report_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(report_dir / "manifest.txt", asset_dir=asset_dir, args=args)

    if not args.skip_exact:
        _run(
            [
                sys.executable,
                "-m",
                "projects.sgm_prod.classification.tools.evaluate_router_assets",
                "--asset-dir",
                str(asset_dir),
            ],
            report_dir / "exact_assets.log",
        )

    if not args.skip_rule_only:
        _run(
            [
                sys.executable,
                "-m",
                "projects.sgm_prod.classification.tools.evaluate_router_rules",
                "--asset-dir",
                str(asset_dir),
                "--domain",
                args.domain,
            ],
            report_dir / "rule_only.log",
        )

    if not args.skip_llm:
        _run(
            [
                sys.executable,
                "-m",
                "projects.sgm_prod.classification.tools.evaluate_router_e2e_llm",
                "--asset-dir",
                str(asset_dir),
                "--domain",
                args.domain,
                "--concurrency",
                str(args.concurrency),
                "--limit",
                str(args.limit),
                "--progress-every",
                str(args.progress_every),
                "--print-failures",
                str(args.print_failures),
                "--output-csv",
                str(report_dir / "e2e_llm_predictions.csv"),
                "--failures-csv",
                str(report_dir / "e2e_llm_failures.csv"),
                "--report-txt",
                str(report_dir / "e2e_llm_report.txt"),
            ],
            report_dir / "e2e_llm.log",
        )

    print(f"\nreports written to: {report_dir}")


if __name__ == "__main__":
    main()
