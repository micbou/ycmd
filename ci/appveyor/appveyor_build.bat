set msvc=%APPVEYOR_BUILD_WORKER_IMAGE:~-4%
if %msvc% == 2013 (
  set msvc=12
) else if %msvc% == 2015 (
  set msvc=14
) else if %msvc% == 2017 (
  set msvc=15
)

python run_tests.py --msvc %msvc% --completers cs -- ycmd/tests/shutdown_test.py:Shutdown_test.WaitForCsServer_test
