from functools import wraps

from .logger_utils import logger


def time_it(func):
    import time

    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        logger.debug("{} took {:.3f} seconds", func.__name__, end - start)
        return result

    return wrapper
