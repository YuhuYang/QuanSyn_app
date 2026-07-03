# QuanSyn Studio Desktop (PyQt6)

## Run

```powershell
pip install -r requirements-desktop.txt
python run_desktop.py
```

## Updated UI

- VSCode-like shell style (menu/toolbar/sidebar/workspace), with no rounded container split between sidebar and work area.
- File menu:
  - `Import Treebank` (single file)
  - `Import Treebanks` (folder batch import)
  - `Save Depval Result`
- Left icon sidebar modules:
  - `converter`, `depval`, `lingnet`, `lawfitter`
  - Tooltip text appears on hover.

## Converter

- Supports format conversion across `conllu`, `conll`, `mcdt`, `pmt`.
- Includes sentence-level corpus browser with pagination.

## Depval

- Region A:
  - Multi treebank selector (defaults to all imported if none selected)
  - Level selector: `dep`, `sent`, `text`, `distribution`, `pvp`, `all`
  - Metric selector auto-switch by level
  - `pvp` is a dedicated level with:
    - selector 1: `pos` / `deprel`
    - selector 2: multi-select labels from imported treebanks
- Region B:
  - Result tab pages by level with nested sub-tabs:
    - dep: per-treebank word-level table (`id, form, lemma, upos, deprel, head, selected metrics`)
    - sent: per-treebank sentence-level table (`sent id + selected metrics`)
    - text: table with `treebank + selected metrics`
    - distribution: metric sub-tabs, each with `distribution + probability`
    - pvp: label sub-tabs, each has `作支配词时 / 作从属词时` tables (`label + probability`)
  - Table + visualization in side-by-side layout
  - Plotting rules:
    - Select one column: frequency / probability / rank-frequency
    - Select two columns: distribution of column A on column B
    - Chart type: bar / line / scatter
    - `Clear-All: ON` clears canvas before each draw (default)
    - `Clear-All: OFF` overlays new plots on existing axes and keeps axis ranges
  - Basic plotting with `seaborn` (`bar/line/scatter`) for current tab

## Real Compute

- Depval now uses real `quansyn.depval.DepValAnalyzer` computation (not mock values).
- Level mapping:
  - `dep`: `calculate_dep_metrics` then aggregated by mean
  - `sent`: `calculate_sent_metrics` then aggregated by mean
  - `text`: `calculate_text_metrics` direct scalar values
  - `distribution`: `calculate_distributions` + optional `calculate_pvp`
