import resource


def make_preexec(memory_limit_kb):
    """Create a preexec_fn that sets memory limit via ulimit."""
    if not memory_limit_kb or memory_limit_kb <= 0:
        return None

    def preexec():
        limit_bytes = memory_limit_kb * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))

    return preexec
