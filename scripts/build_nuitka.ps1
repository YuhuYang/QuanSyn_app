$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DefaultPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PythonExe = if ($env:QUANSYN_PYTHON) { $env:QUANSYN_PYTHON } else { $DefaultPython }
$OutDir = "D:\develop_package\qsstudio_package"
$SitePackages = Join-Path $ProjectRoot ".venv\Lib\site-packages"
$SklearnLibsDir = Join-Path $SitePackages "sklearn\.libs"

if (-not (Test-Path $PythonExe)) {
  throw "Python executable not found: $PythonExe. Create .venv first or set QUANSYN_PYTHON."
}

Set-Location $ProjectRoot

& $PythonExe -m pip install -U nuitka ordered-set zstandard

& $PythonExe -m nuitka run_desktop.py `
  --standalone `
  --windows-console-mode=disable `
  --enable-plugin=pyqt6 `
  --follow-imports `
  --windows-icon-from-ico="quansyn_desktop/assets/quansyn_icon.ico" `
  --include-data-dir=quansyn_desktop/assets=quansyn_desktop/assets `
  --include-package-data=qtawesome `
  --include-package-data=emoji `
  --include-package=networkit `
  --include-package=networkit.gephi `
  --include-package=networkit.profiling `
  --include-package=sklearn `
  --include-package=joblib `
  --include-package=threadpoolctl `
  --include-data-dir="$SklearnLibsDir=sklearn/.libs" `
  --include-data-files="$SklearnLibsDir\vcomp140.dll=vcomp140.dll" `
  --include-package=tqdm `
  --include-package=google.protobuf `
  --include-package=packaging `
  --include-module=pdb `
  --include-module=site `
  --include-module=cProfile `
  --include-module=profile `
  --include-module=pstats `
  --include-package=http `
  --include-package=html `
  --include-package=xml `
  --include-package=email `
  --include-package=urllib `
  --include-package=multiprocessing `
  --include-package=concurrent `
  --include-package=sqlite3 `
  --nofollow-import-to=spacy `
  --nofollow-import-to=stanza `
  --nofollow-import-to=torch `
  --nofollow-import-to=spacy_pkuseg `
  --nofollow-import-to=pingouin `
  --nofollow-import-to=statsmodels `
  --nofollow-import-to=sympy `
  --nofollow-import-to=mpmath `
  --nofollow-import-to=xarray `
  --nofollow-import-to=seaborn `
  --nofollow-import-to=patsy `
  --no-deployment-flag=excluded-module-usage `
  --output-dir="$OutDir" `
  --output-filename="QuanSyn Studio" `
  --remove-output `
  --assume-yes-for-downloads `
  --lto=no `
  --jobs=4

Write-Host "Build completed."
Write-Host "EXE: $OutDir\\run_desktop.dist\\QuanSyn Studio.exe"
