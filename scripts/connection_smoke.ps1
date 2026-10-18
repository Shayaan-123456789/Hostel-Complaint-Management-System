# Safe Windows preflight: no SQL DML and no secrets printed.
# Run from the directory containing manage.py, after activating .venv.
param([string]$Python = "python")
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
Write-Host "Step 1/3: Python architecture and registered ODBC sources"
& $Python -c "import struct, pyodbc; print('Python:', struct.calcsize('P')*8, 'bit'); print('Oracle drivers:', [d for d in pyodbc.drivers() if 'oracle' in d.lower()]); print('ODBC sources:', pyodbc.dataSources())"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Step 2/3: Django system checks"
& $Python manage.py check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Step 3/3: Oracle schema and permission checks (read only)"
& $Python manage.py check_oracle
exit $LASTEXITCODE
