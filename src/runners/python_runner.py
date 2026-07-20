# -*- coding: utf-8 -*-
"""Python runner: 无编译，直接运行（python3）"""
import os
import subprocess

from .base_runner import BaseRunner


class Python3Runner(BaseRunner):
    SOURCE_NAME = 'main.py'

    def compile(self, code: str, sub_dir: str):
        """Python 不编译，只做语法检查"""
        src = os.path.join(sub_dir, self.SOURCE_NAME)
        self.write_file(src, code)
        try:
            r = subprocess.run(
                ['python3', '-m', 'py_compile', src],
                capture_output=True, timeout=10,
            )
        except Exception as e:
            return False, f'语法检查失败: {e}'
        if r.returncode != 0:
            err = r.stderr.decode('utf-8', errors='replace')
            return False, err
        return True, ''

    def _build_run_cmd(self, sub_dir: str):
        return ['python3', os.path.join(sub_dir, self.SOURCE_NAME)]


# 向后兼容别名：旧评测机代码 import PythonRunner
PythonRunner = Python3Runner
