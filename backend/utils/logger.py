import logging
import sys

def get_logger(name: str = "cctv"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
        h.setFormatter(logging.Formatter(fmt))
        logger.addHandler(h)
    logger.setLevel(logging.INFO)
    return logger
