"""Create the finite policy and analysis plan before measuring any version.

Retrospective pilot: the author and assistant already know both historical bugs.
This file is a frozen analysis plan, not a claim of prospective preregistration.
"""
import hashlib
import json
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def policy(old_scheme, old_port, new_scheme, new_port, same_host):
    if not same_host:
        return False, "HOST_CHANGE"
    if old_scheme == "https" and new_scheme == "http":
        return False, "HTTPS_DOWNGRADE"
    defaults = {"http": 80, "https": 443}
    old_effective = defaults[old_scheme] if old_port is None else old_port
    new_effective = defaults[new_scheme] if new_port is None else new_port
    if old_scheme == new_scheme:
        if old_effective != new_effective:
            return False, "PORT_CHANGE"
        if old_port != new_port:
            return True, "DEFAULT_PORT_EQUIVALENCE"
        return True, "SAME_ORIGIN"
    if old_effective == 80 and new_effective == 443:
        return True, "HTTP_HTTPS_COMPATIBILITY"
    return False, "OTHER_UPGRADE"


def main():
    out = ROOT / "inputs"
    out.mkdir(exist_ok=True)
    if (out / "protocol.json").exists():
        raise SystemExit("Frozen inputs already exist; refusing to replace them.")
    cases = []
    for index, (os, op, ns, np, same) in enumerate(product(
        ("http", "https"), (None, 80, 443, 8080, 8443),
        ("http", "https"), (None, 80, 443, 8080, 8443), (True, False)
    )):
        old = "%s://a.example.test%s/start" % (os, "" if op is None else ":%d" % op)
        new = "%s://%s%s/target" % (
            ns, "a.example.test" if same else "b.example.test",
            "" if np is None else ":%d" % np,
        )
        retain, requirement = policy(os, op, ns, np, same)
        cases.append(dict(id="C%03d" % index, old=old, new=new,
                          expected_retain=retain, requirement=requirement))
    case_bytes = (json.dumps(cases, indent=2, sort_keys=True) + "\n").encode()
    (out / "cases.json").write_bytes(case_bytes)
    protocol = {
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "design": "retrospective single-component proof of concept",
        "cases_sha256": hashlib.sha256(case_bytes).hexdigest(),
        "domain": {"schemes": ["http", "https"], "ports": [None,80,443,8080,8443],
                   "destination_host": ["same", "different"], "cases": len(cases)},
        "reference": "2.20.1", "historical": ["2.19.1", "2.20.0"],
        "policy_basis": [
            "RFC 7235 section 2.2: protection-space scheme and authority",
            "RFC 7230 section 2.7.3: default-port normalization",
            "Requests 2.20.0/2.20.1 release notes: downgrade stripping/default-port retention",
            "Requests documented-in-source HTTP-to-HTTPS compatibility exception; library-specific, not RFC rule",
        ],
        "normative_status": "analyst-defined finite interpretation; not maintainer approval or universal verification",
        "execution": "real Requests Session.get with an in-memory HTTPAdapter; no network I/O",
        "mutation_target": "Requests 2.20.1 SessionRedirectMixin.should_strip_auth",
        "core_mutation_operators": ["comparison inversion", "and/or exchange", "not deletion",
            "boolean literal inversion", "port integer +1", "http/https literal exchange",
            "whole condition negation", "return replacement by True or False"],
        "sensitivity_operator": "delete one if statement, including its body",
        "mutant_denominator": "all structurally distinct, executable mutants killed by the complete finite domain; survivor and error counts also reported",
        "selection": {
            "objective": "minimum number of distinct finite-domain test rows, exact MILP",
            "criteria": ["reference branch arcs", "core killed mutants", "branch arcs + core killed mutants",
                         "branch arcs + core mutants + seven policy-category IDs",
                         "branch arcs + core and if-deletion mutants"],
            "human_cost": "not measured; test-row count is an explicit size objective, not review or maintenance effort",
            "tie_rule": "secondary minimization of case-ID sum at the minimum cardinality",
            "evaluation": "after freezing reductions: historical failures retained, requirement/category coverage, finite-row omissions",
            "optimal_solution_sensitivity": "test feasibility of omitting each historical failure class at the fixed minimum size; historical outcomes used only for evaluation",
        },
        "claims_excluded": ["AI generation effects", "prospective unknown-bug discovery", "population statistics",
                            "human review-time improvement", "synergy of inflation and density", "TDEM reproduction"],
    }
    (out / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n", encoding="utf-8")
    print("Frozen %d cases; sha256=%s" % (len(cases), protocol["cases_sha256"]))


if __name__ == "__main__":
    main()
