# -*- coding: utf-8 -*-
"""
C++ runner: g++ 编译，支持多标准 + O2 优化
=====================================
构造参数：
  std : 编译标准字符串，如 'c++11' 'c++14' 'c++23'
  o2  : 是否开启 -O2 优化
"""
import os
import subprocess

from .base_runner import BaseRunner


class CppRunner(BaseRunner):
    SOURCE_NAME = 'main.cpp'
    BINARY_NAME = 'main'

    def __init__(self, work_dir: str, std: str = 'c++17', o2: bool = True):
        super().__init__(work_dir)
        self.std = std
        self.o2 = o2

    def compile(self, code: str, sub_dir: str):
        src = os.path.join(sub_dir, self.SOURCE_NAME)
        self.write_file(src, code)
        out = os.path.join(sub_dir, self.BINARY_NAME)
        cmd = ['g++', '-std=' + self.std, '-w']
        if self.o2:
            cmd.append('-O2')
        cmd += ['-o', out, src]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            return False, '编译超时（>30s），可能存在无限递归或模板爆炸'
        except Exception as e:
            return False, f'编译器启动失败: {e}'
        if r.returncode != 0:
            err = r.stderr.decode('utf-8', errors='replace')
            return False, err
        return True, ''

    def _build_run_cmd(self, sub_dir: str):
        return [os.path.join(sub_dir, self.BINARY_NAME)]
