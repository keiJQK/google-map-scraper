import os
import sys
import json
import logging
import datetime
import subprocess
import shutil

from typing import Any, Callable, Literal, ParamSpec, TypeVar
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
SRC_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
CSV_DIR = DATA_DIR / "csv"
HTML_DIR = DATA_DIR / "html"
CONFIG_DIR = PROJECT_ROOT / "config"
RUNTIME_DIR = PROJECT_ROOT / "runtime"
LOG_DIR = PROJECT_ROOT / "logs"
NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
NOMINATIM_USER_AGENT = os.environ.get("NOMINATIM_USER_AGENT", "google-map-cdp/1.0 (regional search)")
NOMINATIM_CACHE_PATH = Path(os.environ.get("NOMINATIM_CACHE_PATH", str(DATA_DIR / "cache" / "nominatim.sqlite3")))

P = ParamSpec("P")
R = TypeVar("R")

# wrapper
def debugger(logger: logging.Logger, name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """To decorate a function with exception logging."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        """To wrap the supplied callable with exception handling."""

        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            """To call the wrapped function and log failures."""

            try:
                return func(*args, **kwargs)
            except Exception as e:
                logging_error(logger, SRC_DIR, e)
                raise RuntimeError(f"Look at log file '{LOG_DIR / name}.log'")
        return wrapper
    return decorator


# I/O
def load_file(path: str | Path, file_type: Literal["str", "json"]) -> Any:
    if isinstance(path, str):
        path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Not found file: '{path}'")

    with open(path, 'r', encoding='utf-8-sig') as f:
        if file_type == "str":
            return f.read()
        elif file_type == "json":
            return json.load(f)

def save_file(
    path: str | Path, 
    obj: Any, 
    file_type: Literal["str", "json"], 
    mode: Literal["w", "a"] = "w"
    ) -> None:
    with open(path, mode, encoding="utf-8-sig") as f:
        if file_type == "str":
            f.write(obj)
        elif file_type == "json":
            json.dump(obj, f, ensure_ascii=False, indent=2)

# Log  
def get_logger(logger_name: str) -> logging.Logger:
    """To configure file logging once and return the named logger."""

    logger = logging.getLogger(logger_name)
    log_path = (LOG_DIR / f"{logger_name}.log").resolve()
    if any(
        isinstance(handler, logging.FileHandler)
        and Path(handler.baseFilename).resolve() == log_path
        for handler in logger.handlers
    ):
        return logger

    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n{'='*40}\nSTART: {datetime.datetime.now()}\n")

    logger.setLevel(logging.INFO)
    logger.propagate = False 

    fh = logging.FileHandler(log_path, encoding="utf-8", mode="a")
    fh.setLevel(logging.INFO) 
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    
    return logger


def log_print(logger: logging.Logger, func_name: str, **kwarg: Any) -> None:
    """To log a formatted message with additional values."""

    content = _output_content(func_name, **kwarg)
    logger.info("\n".join(content))

def _output_content(func_name: str, **kwarg: Any) -> list[str]:
    """To format a message and its additional values as log lines."""

    content = [f"\n🔹 [func_name] {func_name}"]
    for k, v in kwarg.items():
        content.append(f"🔸 [{k}] {v}")
    content.append("-"*15)
    return content


def logging_error(logger: logging.Logger, src_dir: Path, e: Exception) -> None:
    """To log an exception without masking it when the console cannot display Unicode."""
    if isinstance(src_dir, str):
        src_dir = Path(src_dir)

    content = _error_content(src_dir, e)

    logger.error("\n".join(content))
    message = "\n".join(content)
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(message.encode(encoding, errors="replace").decode(encoding))

def _error_content(src_dir: Path, e: Exception) -> list[str]:
    """To format exception details and frames within the source directory."""

    import linecache
    import traceback
    content = []
    tb = traceback.extract_tb(e.__traceback__)
    content.append("⬇️ ⬇️ ⬇️  ERROR ⬇️ ⬇️ ⬇️")

    i = 1
    for _, frame in enumerate(tb, start=1):
        if src_dir in Path(frame.filename).resolve().parents:
            code_line = linecache.getline(frame.filename, frame.lineno).strip()
            content.append(f"---- Traceback Frame {i} ----")
            content.append(f"🔸 File : {Path(frame.filename)}:{frame.lineno}")
            content.append(f"🔸 Func : {frame.name}()")
            content.append(f"🔸 Code : {code_line}\n")
            i += 1

    content.append(f"💥 Type : {type(e).__name__}")
    content.append(f"💥 Msg  : \n{e}")
    return content



