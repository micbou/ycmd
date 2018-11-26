if defined YCM_PACKAGE (
  python -m venv venv
  venv\Scripts\pip.exe install pyinstaller
  venv\Scripts\pyinstaller.exe package.spec
  7z a ycmd-windows-%ARCH%.zip %APPVEYOR_BUILD_FOLDER%\dist\ycmd
  appveyor PushArtifact ycmd-windows-%ARCH%.zip -DeploymentName ycmd

  :: Get the ycmd version
  for /F "delims=" %%i in (
      'python -c "from ycmd import __version__; print(__version__)"') do (
    set YCMD_VERSION=%%i
  )
)
