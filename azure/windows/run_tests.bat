:: Add the Python, MSBuild, Cargo, and Go executables to PATH.
set "PATH=C:\Python;C:\Python\Scripts;%PATH%"
set "PATH=%MSBUILD_PATH%;%PATH%"
set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
set "PATH=C:\Go\bin;%PATH%"

:: Prevent the already installed version of Go to conflict with ours.
set GOROOT=

python run_tests.py --msvc %MSVC% --runs 100 ycmd\tests\clangd\get_completions_test.py:GetCompletions_ClangCLDriverFlag_IncludeStatementCandidate_test
