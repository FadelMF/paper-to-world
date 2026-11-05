"""Kernel confinement without root: Landlock (files, TCP) and seccomp (sockets), applied to a child before exec.

Landlock (Linux 5.13+, TCP rules from ABI 4 / Linux 6.7) lets an unprivileged process give up access to
everything but the paths it names, and TCP connections to all but the ports it names. A Landlock domain also
cannot read or trace processes outside it, so /proc/<server pid>/environ stays closed. seccomp then refuses
creating network sockets (TCP and UDP alike) unless the profile needs the network, and io_uring, which could
bypass the socket rule. Both last for the process and everything it starts, and cannot be undone.
"""

import ctypes
import os
import platform

LANDLOCK_CREATE_RULESET, LANDLOCK_ADD_RULE, LANDLOCK_RESTRICT_SELF = 444, 445, 446
RULE_PATH_BENEATH, RULE_NET_PORT = 1, 2
FS_EXECUTE, FS_WRITE_FILE, FS_READ_FILE, FS_READ_DIR = 1 << 0, 1 << 1, 1 << 2, 1 << 3
FS_ALL_V1 = (1 << 13) - 1
NET_BIND_TCP, NET_CONNECT_TCP = 1 << 0, 1 << 1
READ = FS_EXECUTE | FS_READ_FILE | FS_READ_DIR
LIST = FS_READ_DIR  # see names in a folder (and its subfolders), not read files
WRITE = -1  # everything Landlock handles: read, write, create, remove
FILE_ONLY = FS_EXECUTE | FS_WRITE_FILE | FS_READ_FILE | (1 << 14)  # rights a rule on a single file may carry
PR_SET_NO_NEW_PRIVS, PR_SET_SECCOMP, SECCOMP_MODE_FILTER = 38, 22, 2

libc = ctypes.CDLL(None, use_errno=True)


class RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64), ("handled_access_net", ctypes.c_uint64)]


class PathBeneathAttr(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


class NetPortAttr(ctypes.Structure):
    _fields_ = [("allowed_access", ctypes.c_uint64), ("port", ctypes.c_uint64)]


class SockFilter(ctypes.Structure):
    _fields_ = [("code", ctypes.c_uint16), ("jt", ctypes.c_uint8), ("jf", ctypes.c_uint8), ("k", ctypes.c_uint32)]


class SockFprog(ctypes.Structure):
    _fields_ = [("len", ctypes.c_uint16), ("filter", ctypes.POINTER(SockFilter))]


def landlock_abi():
    if platform.machine() not in ("x86_64", "aarch64"):
        return 0
    abi = libc.syscall(LANDLOCK_CREATE_RULESET, None, ctypes.c_size_t(0), ctypes.c_uint32(1))
    return max(abi, 0)


def available():
    """Landlock with TCP rules (ABI 4) on x86_64, where the seccomp filter below is written for."""
    return platform.machine() == "x86_64" and landlock_abi() >= 4


def check(result, what):
    if result < 0:
        raise OSError(ctypes.get_errno(), f"{what}: {os.strerror(ctypes.get_errno())}")
    return result


def landlock(rules, tcp_ports=()):
    """Allow only `rules`, (path, access) pairs using READ, LIST or WRITE, and TCP connections to `tcp_ports`."""
    abi = landlock_abi()
    handled_fs = (1 << (14 if abi < 3 else 15)) - 1 if abi >= 2 else FS_ALL_V1
    attr = RulesetAttr(handled_fs, NET_BIND_TCP | NET_CONNECT_TCP)
    ruleset = check(libc.syscall(LANDLOCK_CREATE_RULESET, ctypes.byref(attr), ctypes.c_size_t(ctypes.sizeof(attr)), ctypes.c_uint32(0)), "landlock ruleset")
    try:
        for path, access in rules:
            if not os.path.exists(path):
                continue
            fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                allowed = (handled_fs if access == WRITE else access) & (handled_fs if os.path.isdir(path) else FILE_ONLY)
                rule = PathBeneathAttr(allowed, fd)
                check(libc.syscall(LANDLOCK_ADD_RULE, ruleset, RULE_PATH_BENEATH, ctypes.byref(rule), ctypes.c_uint32(0)), f"landlock rule {path}")
            finally:
                os.close(fd)
        for port in tcp_ports:
            rule = NetPortAttr(NET_CONNECT_TCP, port)
            check(libc.syscall(LANDLOCK_ADD_RULE, ruleset, RULE_NET_PORT, ctypes.byref(rule), ctypes.c_uint32(0)), f"landlock port {port}")
        check(libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0), "no_new_privs")
        check(libc.syscall(LANDLOCK_RESTRICT_SELF, ruleset, ctypes.c_uint32(0)), "landlock restrict")
    finally:
        os.close(ruleset)


def seccomp(allow_inet):
    """Refuse io_uring always, and sockets other than AF_UNIX (plus AF_INET/AF_INET6 when `allow_inet`).
    Classic BPF over seccomp_data: arch at offset 4, syscall number at 0, first argument at 16 (x86_64)."""
    LD, JEQ, RET = 0x20, 0x15, 0x06
    ALLOW, DENY = 0x7FFF0000, 0x00050000 | 1  # SECCOMP_RET_ERRNO | EPERM
    X86_64, IO_URING_SETUP, SOCKET, AF_UNIX, AF_INET, AF_INET6 = 0xC000003E, 425, 41, 1, 2, 10
    if allow_inet:
        program = [
            (LD, 0, 0, 4),
            (JEQ, 0, 8, X86_64),
            (LD, 0, 0, 0),
            (JEQ, 5, 0, IO_URING_SETUP),
            (JEQ, 0, 5, SOCKET),
            (LD, 0, 0, 16),
            (JEQ, 3, 0, AF_UNIX),
            (JEQ, 2, 0, AF_INET),
            (JEQ, 1, 0, AF_INET6),
            (RET, 0, 0, DENY),
            (RET, 0, 0, ALLOW),
        ]
    else:
        program = [
            (LD, 0, 0, 4),
            (JEQ, 0, 6, X86_64),
            (LD, 0, 0, 0),
            (JEQ, 3, 0, IO_URING_SETUP),
            (JEQ, 0, 3, SOCKET),
            (LD, 0, 0, 16),
            (JEQ, 1, 0, AF_UNIX),
            (RET, 0, 0, DENY),
            (RET, 0, 0, ALLOW),
        ]
    filters = (SockFilter * len(program))(*[SockFilter(*instruction) for instruction in program])
    fprog = SockFprog(len(program), filters)
    check(libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0), "no_new_privs")
    check(libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.byref(fprog), 0, 0), "seccomp")


def confine(rules, tcp_ports=()):
    """For subprocess preexec_fn: Landlock, then seccomp (network sockets only when TCP ports are allowed)."""
    landlock(rules, tcp_ports)
    seccomp(allow_inet=bool(tcp_ports))
