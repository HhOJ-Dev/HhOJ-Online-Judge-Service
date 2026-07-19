# -*- coding: utf-8 -*-
"""Java runner: javac 编译，java 运行"""
import os
import subprocess

from .base_runner import BaseRunner


class JavaRunner(BaseRunner):
    SOURCE_NAME = 'Main.java'
    CLASS_NAME = 'Main'

    def compile(self, code: str, sub_dir: str):
        src = os.path.join(sub_dir, self.SOURCE_NAME)
        self.write_file(src, code)
        try:
            r = subprocess.run(
                ['javac', '-encoding', 'UTF-8', src],
                capture_output=True, timeout=30, cwd=sub_dir,
            )
        except subprocess.TimeoutExpired:
            return False, '编译超时（>30s）'
        except Exception as e:
            return False, f'编译器启动失败: {e}'
        if r.returncode != 0:
            err = r.stderr.decode('utf-8', errors='replace')
            return False, err
        # 校验 class 文件存在
        if not os.path.exists(os.path.join(sub_dir, self.CLASS_NAME + '.class')):
            return False, f'编译后未找到 {self.CLASS_NAME}.class，请确保主类名为 {self.CLASS_NAME}'
        return True, ''

    def _build_run_cmd(self, sub_dir: str):
        # Java 内存限制需要特别处理：JVM 自身会占用较多内存
        # 这里仍走 base 的 ulimit -v，但限制值由调用方传入（网站内存限制 * 1024 KB）
        # 注意：ulimit -v 限制虚拟内存，JVM 可能因无法分配元空间而启动失败
        # 如有 JVM 启动失败，可考虑放宽 Java 的内存限制
        return ['java', '-Xss64m', self.CLASS_NAME]
