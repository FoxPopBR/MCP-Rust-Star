import logging
from logging.handlers import RotatingFileHandler
import os
from functools import wraps
import traceback
import sys
import inspect
import asyncio


class WinCompatRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler compatível com Windows.

    No Windows, o rename do arquivo falha com PermissionError (WinError 32)
    quando outro processo ainda mantém o arquivo aberto. Este handler captura
    esse erro e continua logando no arquivo atual sem travar o servidor.
    """

    def doRollover(self):
        try:
            super().doRollover()
        except PermissionError:
            # Arquivo bloqueado por outra instância no Windows — ignora rotação
            pass
        except OSError:
            pass

    def emit(self, record):
        try:
            super().emit(record)
        except PermissionError:
            pass
        except Exception:
            self.handleError(record)


class CustomLogger:
    def __init__(self, name='RustStarMCP', log_file='logs/mcp_error.log', level=logging.DEBUG, console_log=True, file_log=True, logger_filename='logger.py', include_logger_in_traceback=False):
        self.log_file = os.path.abspath(log_file)
        self.logger = logging.getLogger(name)
        self.level = level
        self.logger_filename = logger_filename
        self.include_logger_in_traceback = include_logger_in_traceback
        self.logger.setLevel(self.level)
        self.logger.propagate = False
        if not self.logger.handlers:
            self.setup_logger(console_log, file_log)

    def setup_logger(self, console_log, file_log):
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
        if file_log:
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
            file_handler = WinCompatRotatingFileHandler(
                self.log_file, maxBytes=10*1024*1024, backupCount=5,
                encoding='utf-8', delay=True
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(self.level)
            self.logger.addHandler(file_handler)
        if console_log:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setFormatter(formatter)
            console_handler.setLevel(self.level)
            self.logger.addHandler(console_handler)

    def get_stacklevel(self):
        stack = inspect.stack()
        stacklevel = 1
        for frame_info in stack[1:]:
            module_name = frame_info.frame.f_globals.get('__name__', '')
            if module_name != __name__:
                break
            stacklevel += 1
        return stacklevel

    def log_here(self, level, msg, *args, **kwargs):
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        if 'stacklevel' in kwargs:
            kwargs['stacklevel'] += 1
        else:
            kwargs['stacklevel'] = self.get_stacklevel()
        log_method(msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        self.log_here('debug', msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self.log_here('info', msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self.log_here('warning', msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self.log_here('error', msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self.log_here('critical', msg, *args, **kwargs)

    def log_exception(self, func):
        if asyncio.iscoroutinefunction(func) or inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    self.error_with_traceback(e, func.__name__)
                    raise
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    self.error_with_traceback(e, func.__name__)
                    raise
            return sync_wrapper

    def error_with_traceback(self, exception, function_name):
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.extract_tb(exc_traceback)
        if not self.include_logger_in_traceback:
            filtered_tb = [entry for entry in tb if entry.filename.split(os.sep)[-1] != self.logger_filename]
        else:
            filtered_tb = tb
        formatted_tb = traceback.format_list(filtered_tb)
        formatted_error = "Traceback (most recent call last):\n" + "".join(formatted_tb) + f"{exc_type.__name__}: {exc_value}"
        self.logger.error(f"Exception in function '{function_name}':\n{formatted_error}", exc_info=False, stacklevel=self.get_stacklevel())


logger = CustomLogger(name='RustStarMCP')
