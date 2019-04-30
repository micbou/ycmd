:: Add Python to PATH
set "PATH=C:\Python;C:\Python\Scripts;%PATH%"
:: Add the MSBuild executable to PATH
set "PATH=%MSBUILD_PATH%;%PATH%"
:: Add the Cargo executable to PATH
set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"

python run_tests.py
