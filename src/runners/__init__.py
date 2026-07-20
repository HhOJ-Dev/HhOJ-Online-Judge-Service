#!/usr/bin/env python3
from typing import Optional

from .base import Runner
from .c_runner import CRunner
from .cpp_runner import CppRunner
from .csharp_runner import CSharpRunner
from .python_runner import PythonRunner

LANGUAGE_CONFIG = {
    "c": {
        "class": CRunner,
        "source_file": "Answer.c",
    },
    "c#": {
        "class": CSharpRunner,
        "source_file": "Answer.cs",
    },
    "c++11": {
        "class": CppRunner,
        "source_file": "Answer.cpp",
        "version": "c++11",
        "optimize": False,
    },
    "c++11(o2)": {
        "class": CppRunner,
        "source_file": "Answer.cpp",
        "version": "c++11",
        "optimize": True,
    },
    "c++14": {
        "class": CppRunner,
        "source_file": "Answer.cpp",
        "version": "c++14",
        "optimize": False,
    },
    "c++14(o2)": {
        "class": CppRunner,
        "source_file": "Answer.cpp",
        "version": "c++14",
        "optimize": True,
    },
    "c++23": {
        "class": CppRunner,
        "source_file": "Answer.cpp",
        "version": "c++23",
        "optimize": False,
    },
    "c++23(o2)": {
        "class": CppRunner,
        "source_file": "Answer.cpp",
        "version": "c++23",
        "optimize": True,
    },
    "python3": {
        "class": PythonRunner,
        "source_file": "Answer.py",
    },
    "python 3": {
        "class": PythonRunner,
        "source_file": "Answer.py",
    },
}

def create_runner(language: str, source_file: Optional[str] = None,
                  time_limit: float = 2.0, memory_limit: int = 262144) -> Runner:
    language = language.lower().strip()

    if language not in LANGUAGE_CONFIG:
        raise ValueError(f"Unsupported language: {language}. Supported languages: {list(LANGUAGE_CONFIG.keys())}")

    config = LANGUAGE_CONFIG[language]
    runner_class = config["class"]

    kwargs = {
        "time_limit": time_limit,
        "memory_limit": memory_limit,
    }

    if source_file:
        kwargs["source_file"] = source_file
    else:
        kwargs["source_file"] = config["source_file"]

    if "version" in config:
        kwargs["version"] = config["version"]
    if "optimize" in config:
        kwargs["optimize"] = config["optimize"]

    return runner_class(**kwargs)

def get_supported_languages() -> list:
    return list(LANGUAGE_CONFIG.keys())