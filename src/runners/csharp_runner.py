# -*- coding: utf-8 -*-
"""
C# runner: mono mcs 编译，mono 运行
=====================================
依赖：mono-devel（提供 mcs 编译器和 mono 运行时）
  - Ubuntu 安装：sudo apt-get install -y mono-devel
  - 验证：mcs --version && mono --version

主类要求：C# 代码顶层定义一个含 Main 静态方法的类即可，
         类名不限定（用 mcs 默认的 main.exe 入口）
"""
import os
import subprocess

from .base_runner import BaseRunner


class CSharpRunner(BaseRunner):
    SOURCE_NAME = 'main.cs'
    ASSEMBLY_NAME = 'main.exe'

    def compile(self, code: str, sub_dir: str):
        src = os.path.join(sub_dir, self.SOURCE_NAME)
        self.write_file(src, code)
        out = os.path.join(sub_dir, self.ASSEMBLY_NAME)
        # -warnaserror- 把警告不当错误；-optimize+ 开启优化
        try:
            r = subprocess.run(
                ['mcs', '-warnaserror-', '-optimize+', '-out:' + out, src],
                capture_output=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            return False, '编译超时（>30s）'
        except FileNotFoundError:
            return False, '未安装 mono 编译器（mcs），请联系管理员安装 mono-devel'
        except Exception as e:
            return False, f'编译器启动失败: {e}'
        if r.returncode != 0:
            err = r.stderr.decode('utf-8', errors='replace')
            return False, err
        if not os.path.exists(out):
            return False, '编译后未找到 main.exe'
        return True, ''

    def _build_run_cmd(self, sub_dir: str):
        # mono 运行 .NET 程序集
        return ['mono', os.path.join(sub_dir, self.ASSEMBLY_NAME)]
