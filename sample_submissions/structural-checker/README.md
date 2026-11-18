# structural-checker

A PLE harness sample that combines a model tool-use loop with an offline
limited-scope steel beam checker. It is a complete *entry template*; it is not
a complete structural design system and does not establish that a structure is
safe.

## What the harness does

- Implements the PLE WebSocket serve protocol using the bundled `taskbridge.py`.
- Provides `bash`, `read_file`, and `write_file` tools for task-container work.
- Provides `check_steel_beam`, which reads a YAML input from the task container,
  runs the local calculator in the harness container, and writes a JSON report
  back to the requested task-container path.
- Uses the Google-sponsored Gemini model declared in `submission.yaml`.

The model must first inspect the task evidence and create the structured YAML
input using verified values. It must not infer missing steel properties,
combination factors, or project deflection limits. If required information is
missing, the harness prompt directs it to report that limitation rather than
invent values.

## Checker scope

The checker supports prismatic, simply supported beams with downward
full-span constant UDL and downward interior point loads. It calculates
first-order elastic actions, cross-section bending and shear resistance for
user-classified Class 1–3 sections, and elastic vertical deflection against a
project-provided SLS limit. Load-combination factors are explicit input values;
the checker does not derive combinations from EN 1990 or select National
Annex parameters.

It does not check section classification, lateral-torsional buckling,
adequacy of restraints, shear buckling, connections, global stability,
vibration, fatigue, fire, or other omitted design requirements. Reports remain
`partial` when supported calculations pass, and return `not_assessed` for
checks outside scope. A qualified engineer must determine the governing
standards and verify the inputs, assumptions, and results.

The implementation and limitations are documented in
[`structural_checks/README.md`](structural_checks/README.md). The example YAML
there is illustrative only; its values and factors are not design
recommendations.

## Run locally

From this directory, after installing the requirements:

```bash
python -m pip install -r requirements.txt
python -m structural_checks structural_checks/examples/simply_supported_beam.yaml
```

For the PLE kit, copy this directory into its own Git repository outside the
benchmark clone, then follow the benchmark repository's quick start and kit
instructions. The entry needs a local model proxy configuration to run the
Google-sponsored model. Run `eval/run.py` from the benchmark repository to
produce the task artifacts; this sample does not include pre-generated
artifacts.

Run the included checker tests from this directory with:

```bash
python -m unittest discover -s tests -v
```
