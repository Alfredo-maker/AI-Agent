# Structural beam checks (prototype)

This offline Python library and CLI performs limited checks for a prismatic,
simply supported steel beam under downward, full-span constant UDLs and
downward point loads. It is a prototype and **does not provide design approval
or a complete structural integrity assessment**.

## Run

From the repository root:

```powershell
py -m structural_checks structural_checks\examples\simply_supported_beam.yaml
py -m structural_checks structural_checks\examples\simply_supported_beam.yaml --output beam-report.json
```

The sample is deliberately illustrative: its factors, section properties, and
deflection limit are not design recommendations. Replace them with verified
project inputs.

## Inputs and calculation scope

- Units are metres for span/point-load position, kN and kN/m for loads, MPa for
  strengths/modulus, and mm-based section properties.
- The section class, major-axis `Iy`, shear area `Av`, and applicable elastic or
  plastic section modulus must come from verified section data and design
  classification. Class 4 is rejected.
- `fy_mpa`, `gamma_m0`, and `e_mpa` are explicit inputs. Select strength for the
  product and thickness. Select partial factors for the governing National
  Annex; this tool supplies no jurisdictional default.
- Every ULS/SLS combination and every load-case factor must be supplied by the
  user. The tool does not derive combinations from EN 1990/EN 1991.
- Each SLS combination requires a project-specific `deflection_limit_mm`.
- Point loads must be strictly inside the span. Self-weight is not added
  automatically; include it in a load case if applicable.

The checker calculates elastic beam actions, cross-section bending resistance
for Classes 1–3, plastic shear resistance, bending-shear threshold handling,
and elastic vertical deflection. A ULS combination with shear above 50% of
plastic shear resistance is marked `not_assessed` for bending-shear interaction
instead of being reported as a pass.

## Important omissions

The report deliberately returns `partial` when computed checks pass. Among
other omissions, this prototype does not check lateral-torsional buckling,
restraint design, shear buckling under EN 1993-1-5, section classification,
global/frame stability, connections, fatigue, fire, vibration, or load
combinations. These omissions must be resolved separately by a qualified
engineer using the applicable standards and National Annex.

The report references EN 1993-1-1:2005 clauses as a traceability aid. Confirm
that this edition and the attached source are applicable and current for the
project. Verify equations, section properties, combinations, assumptions, and
results independently before any engineering use.

## PLE integration

This package is bundled by the parent `structural-checker` sample entry. See
that entry's README for its WebSocket harness, model configuration, and PLE
local-run instructions. The calculation package itself has no network access
or model credentials.
