"""Arm capability predicates keeping E11 (A) and PRA (B-G) unchanged while isolating H1-H5 and R."""

from typing import Literal

PraArm = Literal["A", "B", "C", "D", "E", "F", "G", "H1", "H2", "H3", "H4", "H5", "R"]
VALID_PRA_ARMS = frozenset({"A", "B", "C", "D", "E", "F", "G", "H1", "H2", "H3", "H4", "H5", "R"})
V9_ARMS = frozenset({"H1", "H2", "H3", "H4", "H5", "R"})


def has_profile_arm(arm: str) -> bool:
    return arm in {"B", "G"} or arm in V9_ARMS


def has_graph_arm(arm: str) -> bool:
    return arm in {"C", "G"} or arm in V9_ARMS


def has_pairwise_arm(arm: str) -> bool:
    return arm in {"D", "G"} or arm in V9_ARMS


def has_gap_arm(arm: str) -> bool:
    return arm in {"E", "G"} or arm in V9_ARMS


def has_compiler_arm(arm: str) -> bool:
    return arm in {"F", "G"} or arm in V9_ARMS


def has_full_pra(arm: str) -> bool:
    return arm == "G" or arm in V9_ARMS


def has_h1(arm: str) -> bool:
    return arm in {"H1", "R"}


def has_h2(arm: str) -> bool:
    return arm in {"H2", "R"}


def has_h3(arm: str) -> bool:
    return arm in {"H3", "R"}


def has_h4(arm: str) -> bool:
    return arm in {"H4", "R"}


def has_h5(arm: str) -> bool:
    return arm in {"H5", "R"}
