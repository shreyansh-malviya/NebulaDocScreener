"""Print a legal synthetic passport MRZ (valid + tampered) — no real documents needed.
Run from backend/:  python -m tools.gen_synthetic_mrz
"""
from app.core import mrz


def main() -> None:
    v = mrz.sample_passport(tampered=False)
    t = mrz.sample_passport(tampered=True)
    print("=== VALID synthetic passport (all check digits correct) ===")
    print(v["line1"])
    print(v["line2"])
    print("valid:", mrz.parse_mrz([v["line1"], v["line2"]])["valid"])
    print()
    print("=== TAMPERED (DOB edited in MRZ, check digit not updated) ===")
    print(t["line1"])
    print(t["line2"])
    p = mrz.parse_mrz([t["line1"], t["line2"]])
    print("valid:", p["valid"], "| checks:", p["checks"])


if __name__ == "__main__":
    main()
