# -*- coding: utf-8 -*-
"""Pascal runner: fpc 编译，直接运行"""
import os
import subprocess

from .base_runner import BaseRunner


class PascalRunner(BaseRunner):
    SOURCE_NAME = 'main.pas'
    BINARY_NAME = 'main'

    def compile(self, code: str, sub_dir: str):
        src = os.path.join(sub_dir, self.SOURCE_NAME)
        self.write_file(src, code)
        out = os.path.join(sub_dir, self.BINARY_NAME)
        try:
            r = subprocess.run(
                ['fpc', '-Mobjfpc', '-O2', '-v0', '-o' + out, src],
                capture_output=True, timeout=30, cwd=sub_dir,
            )
        except subprocess.TimeoutExpired:
            return False, '编译超时（>30s）'
        except Exception as e:
            return False, f'编译器启动失败: {e}'
        if r.returncode != 0:
            err = r.stderr.decode('utf-8', errors='replace')
            return False, err
        return True, ''

    def _build_run_cmd(self, sub_dir: str):
        return [os.path.join(sub_dir, self.BINARY_NAME)]
