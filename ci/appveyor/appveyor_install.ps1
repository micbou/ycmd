#
# Git configuration
#

# Since we are caching target folder in racerd submodule and git cannot clone
# a submodule in a non-empty folder, we move out the cached folder and move it
# back after cloning submodules.
$racerd_target = "$env:APPVEYOR_BUILD_FOLDER\third_party\racerd\target"
$racerd_temp = "$env:APPVEYOR_BUILD_FOLDER\racerd_target"
If (Test-Path -Path $racerd_target) {
  Move-Item $racerd_target $racerd_temp
}

Invoke-Expression "git submodule update --init --recursive"

if (Test-Path -Path $racerd_temp) {
  Move-Item $racerd_temp $racerd_target
}

#
# Python configuration
#

If ($env:arch -eq 32) {
  $python_path = "C:\Python$env:python"
} Else {
  $python_path = "C:\Python$env:python-x64"
}

$env:PATH = "$python_path;$python_path\Scripts;$env:PATH"
Invoke-Expression "python --version"

$pip_installer = "get-pip.py"
$pip_url = "https://bootstrap.pypa.io/$pip_installer"
Start-FileDownload $pip_url
Invoke-Expression "python $pip_installer"
Invoke-Expression "pip install -r test_requirements.txt"

#
# TypeScript configuration
#

Invoke-Expression "npm install -g typescript"

#
# Rust configuration
#

$rust_installer = "rust-1.12.0-x86_64-pc-windows-msvc.msi"
$rust_url = "https://static.rust-lang.org/dist/$rust_installer"
$rust_path = "$env:APPVEYOR_BUILD_FOLDER\$rust_installer"
Start-FileDownload $rust_url
Start-Process "msiexec.exe" `
  -ArgumentList "/i $rust_installer /qn INSTALLDIR_MACHINE=C:\Rust" -Wait

$env:PATH = "C:\Rust\bin;$env:PATH"

Invoke-Expression "rustc -Vv"
Invoke-Expression "cargo -V"
