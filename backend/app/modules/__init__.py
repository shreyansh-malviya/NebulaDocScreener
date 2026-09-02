"""Pipeline modules. Each is a pure async function `inputs -> Evidence fragment`.

Real now:  m1_ocr (MRZ-text path), m2_validation, supervisor (template narrative).
Stubbed:   m3_tamper, m4_face, m5_chip, liveness — return clearly-labelled STUB
           fragments that contribute NO signal (they abstain), so nothing is faked.
"""
