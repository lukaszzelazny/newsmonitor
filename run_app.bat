@echo off
set MODE=%1

if "%MODE%"=="" (
    echo "Running ticker API by default. Use 'run_app.bat import_xtb [file_path]' to import transactions."
    python -m analize.ticker_api
    goto:eof
)

if "%MODE%"=="import_xtb" (
    set FILE_PATH=%2
    if "%FILE_PATH%"=="" (
        echo "Error: File path is required for import_xtb mode."
        echo "Usage: run_app.bat import_xtb [path_to_your_file.xlsx]"
        goto:eof
    )
    echo "Running XTB transaction import..."
    python main.py --mode import_xtb --file "%FILE_PATH%"
    goto:eof
)

if "%MODE%"=="analyze" (
    set PORTFOLIO_NAME=%2
    if not "%PORTFOLIO_NAME%"=="" (
        echo "Analyzing portfolio: %PORTFOLIO_NAME%"
        python main.py --mode analyze --portfolio "%PORTFOLIO_NAME%"
    ) else (
        echo "Analyzing all portfolios..."
        python main.py --mode analyze
    )
    goto:eof
)
