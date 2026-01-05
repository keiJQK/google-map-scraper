import traceback, logging, linecache
from datetime import datetime
from pathlib import Path

from . import global_vars as gv 

# ----- I/O -----
def save_csv(filepath, df, mode="w", header=True) -> None:
    write_header = header if mode == "w" else not filepath.exists()
    df.to_csv(filepath, index=False, mode=mode, header=write_header, encoding="utf-8")

def load_html(filepath:Path) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()
        return html

def save_html(filepath:Path, material:list|str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        if type(material) is list:
            for m in material:
                f.write(m)
                print(f"[Saved] {filepath}\n")
        else:
            f.write(material)
            print(f"[Saved] {filepath}\n")

# ----- LOG -----
def setup_logger(fn, logger_name, flag_propa=False):
    log_path = gv.LOG_DIR / f"{fn}.log"
    log_path.parent.mkdir(exist_ok=True)
    log_path.write_text("", encoding="utf-8")

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = flag_propa 
    logger.handlers.clear()
    
    fh = logging.FileHandler(log_path, encoding="utf-8", mode="a")
    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    log_print(logger, msg=f"Start: {logger_name}")
    return logger

def logging_error(logger, src_dir, e):
    content = []
    now = datetime.now().strftime("%H:%M:%S.%f")[:-4]
    tb = traceback.extract_tb(e.__traceback__)

    content.append(f"Type : {type(e).__name__}")
    content.append(f"{e}\n")

    i = 1
    for j, frame in enumerate(tb, start=1):
        if src_dir in Path(frame.filename).resolve().parents:
            content.append(f"---- Traceback Frame {i} ----")
            content.append(f"File : {Path(frame.filename)}:{frame.lineno}")
            content.append(f"Func : {frame.name}()")

            if j == len(tb):
                code_line = linecache.getline(frame.filename, frame.lineno).strip()
                content.append(f"Code : {code_line}\n")
            i += 1

    for ctx in content:
        logger.error(ctx)
        print(now, ctx)

def log_print(logger, msg, **kwargs):
    now = datetime.now().strftime("%H:%M:%S.%f")[:-4]   # hh:mm:ss.xx
    print(now, msg)
    logger.info(msg)
    for name, val in kwargs.items():
        print(now, f"[{name}]", val)
        logger.info(f"[{name}] {val}")


