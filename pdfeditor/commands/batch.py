"""`pdfedit batch`: run any single-file command on every PDF in a folder, in parallel.

    pdfedit batch FOLDER COMMAND [COMMAND ARGS...]
    pdfedit batch --out-dir done --jobs 4 scans/ rotate 90 --pages even

Batch options go BEFORE the folder; everything after COMMAND is passed to it unchanged.
Each file runs in its own process (true parallelism, and one bad PDF can't crash the rest).
"""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import typer

from ..cli import _fail, app

# Commands that take several inputs or no single PDF can't be batched per file.
NOT_BATCHABLE = {"batch", "merge", "from-images"}
# How each command names its output when --out-dir is given: (flag, kind)
OUTPUT_FLAG = {
    "split": ("-d", "dir"),
    "to-images": ("-d", "dir"),
    "to-text": ("-o", ".txt"),
    "info": (None, None),
}


def _command_names() -> set[str]:
    import typer.main

    return set(typer.main.get_command(app).commands)  # type: ignore[attr-defined]


def _argv_for(pdf: Path, command: str, args: list[str], out_dir: Path | None) -> list[str]:
    argv = [command, str(pdf), *args]
    if out_dir is not None:
        flag, kind = OUTPUT_FLAG.get(command, ("-o", ".pdf"))
        if flag:
            target = out_dir / pdf.stem if kind == "dir" else out_dir / f"{pdf.stem}{kind}"
            argv += [flag, str(target)]
    return argv


def _run(argv: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pdfeditor.cli", *argv],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True,
                               "allow_interspersed_args": False})
def batch(
    ctx: typer.Context,
    folder: Path = typer.Argument(..., help="Folder of PDFs."),
    command: str = typer.Argument(..., help="Command to run on each PDF, e.g. rotate, compress, watermark."),
    out_dir: Optional[Path] = typer.Option(None, "--out-dir", "-O",
                                           help="Put all outputs here (default: next to each input)."),
    jobs: int = typer.Option(0, "--jobs", "-j", help="Parallel workers (default: number of CPU cores)."),
    recursive: bool = typer.Option(False, "--recursive", "-R", help="Include PDFs in subfolders."),
) -> None:
    """Run a command on every PDF in a folder, in parallel. Batch options go before FOLDER."""
    if not folder.is_dir():
        _fail(f"not a folder: {folder}")
    if command in NOT_BATCHABLE:
        _fail(f"'{command}' can't be run per file")
    if command not in _command_names():
        _fail(f"unknown command '{command}'. See `pdfedit --help`.")
    args = list(ctx.args)
    if out_dir is None and any(a in ("-o", "--out", "-d", "--out-dir") for a in args):
        _fail("use batch's own --out-dir (before the folder) instead of -o/-d, "
              "so files don't overwrite each other")

    pattern = "**/*.pdf" if recursive else "*.pdf"
    pdfs = sorted((p for p in folder.glob(pattern) if p.is_file()), key=lambda p: str(p).lower())
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        # don't re-process our own outputs if out_dir is inside the folder
        pdfs = [p for p in pdfs if out_dir.resolve() not in p.resolve().parents]
    if not pdfs:
        _fail(f"no PDFs in {folder}")

    workers = jobs if jobs > 0 else min(len(pdfs), os.cpu_count() or 2)
    typer.echo(f"Running '{command}' on {len(pdfs)} PDFs with {workers} workers...")

    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run, _argv_for(p, command, args, out_dir)): p for p in pdfs}
        for fut in as_completed(futures):
            pdf = futures[fut]
            code, output = fut.result()
            ok = code == 0
            if not ok:
                failed.append(pdf.name)
            typer.secho(f"{'OK  ' if ok else 'FAIL'} {pdf.name}", fg=typer.colors.GREEN if ok else typer.colors.RED)
            if not ok or command == "info":
                for line in output.splitlines():
                    typer.echo(f"     {line}")

    done = len(pdfs) - len(failed)
    typer.secho(f"\n{done}/{len(pdfs)} succeeded", bold=True,
                fg=typer.colors.GREEN if not failed else typer.colors.YELLOW)
    if failed:
        raise typer.Exit(2)
