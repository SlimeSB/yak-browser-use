"""Unit tests for _check_safe_imports (AST safety check)."""

from engine.runner_preset import _check_safe_imports


def test_legal_imports_pass():
    assert _check_safe_imports("import json\nimport re\n") is None
    assert _check_safe_imports("from PIL import Image\n") is None
    assert _check_safe_imports("import ddddocr\n") is None


def test_import_os_blocked():
    result = _check_safe_imports("import os\n")
    assert result is not None
    assert "os" in result


def test_from_subprocess_blocked():
    result = _check_safe_imports("from subprocess import run\n")
    assert result is not None
    assert "subprocess" in result


def test_import_os_path_blocked():
    result = _check_safe_imports("import os.path\n")
    assert result is not None
    assert "os" in result


def test_import_sys_blocked():
    assert _check_safe_imports("import sys\n") is not None


def test_import_shutil_blocked():
    assert _check_safe_imports("import shutil\n") is not None


def test_import_socket_blocked():
    assert _check_safe_imports("import socket\n") is not None


def test_import_ctypes_blocked():
    assert _check_safe_imports("import ctypes\n") is not None


def test_import_signal_blocked():
    assert _check_safe_imports("import signal\n") is not None


def test_import_multiprocessing_blocked():
    assert _check_safe_imports("import multiprocessing\n") is not None


def test_import_threading_blocked():
    assert _check_safe_imports("import threading\n") is not None


def test_import_importlib_blocked():
    assert _check_safe_imports("import importlib\n") is not None


def test_syntax_error_detected():
    result = _check_safe_imports("def foo(\n")
    assert result is not None
    assert "语法错误" in result


def test_mixed_imports():
    code = """import json
import os
from PIL import Image
"""
    result = _check_safe_imports(code)
    assert result is not None
    assert "os" in result


def test_empty_code():
    assert _check_safe_imports("") is None


def test_no_imports():
    assert _check_safe_imports("x = 1\ny = 2\n") is None


def test_exec_call_blocked():
    result = _check_safe_imports('exec("import os")')
    assert result is not None
    assert "exec()" in result


def test_eval_call_blocked():
    result = _check_safe_imports('eval("__import__(\'os\')")')
    assert result is not None
    assert "eval()" in result


def test_dunder_import_call_blocked():
    result = _check_safe_imports('__import__("os")')
    assert result is not None
    assert "__import__()" in result


def test_compile_call_blocked():
    result = _check_safe_imports('compile("import os", "", "exec")')
    assert result is not None
    assert "compile()" in result


def test_open_call_blocked():
    result = _check_safe_imports('open("/etc/passwd")')
    assert result is not None
    assert "open()" in result


def test_breakpoint_call_blocked():
    result = _check_safe_imports("breakpoint()")
    assert result is not None
    assert "breakpoint()" in result


def test_import_builtins_blocked():
    result = _check_safe_imports("import builtins\n")
    assert result is not None
    assert "builtins" in result


def test_relative_import_blocked():
    result = _check_safe_imports("from . import os\n")
    assert result is not None
    assert "相对导入" in result


def test_relative_from_blocked():
    result = _check_safe_imports("from .helpers import foo\n")
    assert result is not None
    assert "相对导入" in result
