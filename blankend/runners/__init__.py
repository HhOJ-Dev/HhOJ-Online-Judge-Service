from runners.cpp_runner import CppRunner
from runners.c_runner import CRunner
from runners.csharp_runner import CSharpRunner
from runners.python_runner import PythonRunner
from runners.java_runner import JavaRunner
from runners.pascal_runner import PascalRunner

LANGUAGE_ALIASES = {
    'cpp': 'cpp14_o2',
    'cpp11': 'cpp11',
    'cpp11_o2': 'cpp11_o2',
    'cpp14': 'cpp14',
    'cpp14_o2': 'cpp14_o2',
    'cpp17': 'cpp17',
    'cpp17_o2': 'cpp17_o2',
    'cpp23': 'cpp23',
    'cpp23_o2': 'cpp23_o2',
    'c': 'c',
    'python': 'python3',
    'python3': 'python3',
    'java': 'java',
    'csharp': 'csharp',
    'pascal': 'pascal',
}

def get_runner(language):
    lang = LANGUAGE_ALIASES.get(language, language)

    if lang.startswith('cpp'):
        std_map = {
            'cpp11': 'c++11',
            'cpp11_o2': 'c++11',
            'cpp14': 'c++14',
            'cpp14_o2': 'c++14',
            'cpp17': 'c++17',
            'cpp17_o2': 'c++17',
            'cpp23': 'c++23',
            'cpp23_o2': 'c++23',
        }
        std = std_map.get(lang, 'c++17')
        o2 = lang.endswith('_o2')
        return CppRunner(std=std, o2=o2)

    if lang == 'c':
        return CRunner()

    if lang == 'python3':
        return PythonRunner()

    if lang == 'java':
        return JavaRunner()

    if lang == 'csharp':
        return CSharpRunner()

    if lang == 'pascal':
        return PascalRunner()

    raise ValueError(f'Unsupported language: {language}')
