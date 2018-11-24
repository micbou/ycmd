import sys


def OnWindows():
  return sys.platform == 'win32'


def Exe( executable ):
  return executable + ( '.exe' if OnWindows() else '' )


block_cipher = None

a = Analysis(
  [ 'ycmd/__main__.py' ],
  pathex = [
    'ycmd',
    'third_party/bottle',
    'third_party/cregex/regex_3',
    'third_party/frozendict',
    'third_party/jedi',
    'third_party/parso',
    'third_party/requests',
    'third_party/waitress'
  ],
  binaries = [],
  datas = [
    ( 'clang_includes',        'clang_includes' ),
    ( 'COPYING.txt',           '.' ),
    ( 'CORE_VERSION',          '.' ),
    ( 'default_settings.json', '.' ),
    # YCM dependencies
    # TODO: remove them.
    ( 'ycmd/completers/completer.py',       'ycm_deps/ycmd/completers' ),
    ( 'ycmd/completers/completer_utils.py', 'ycm_deps/ycmd/completers' ),
    ( 'ycmd/hmac_utils.py',                 'ycm_deps/ycmd' ),
    ( 'ycmd/identifier_utils.py',           'ycm_deps/ycmd' ),
    ( 'ycmd/request_wrap.py',               'ycm_deps/ycmd' ),
    ( 'ycmd/request_validation.py',         'ycm_deps/ycmd' ),
    ( 'ycmd/responses.py',                  'ycm_deps/ycmd' ),
    ( 'ycmd/utils.py',                      'ycm_deps/ycmd' ),
    # C#
    ( 'third_party/OmniSharpServer/OmniSharp/bin/Release',
      'third_party/OmniSharpServer/OmniSharp/bin/Release' ),
    # Go
    ( Exe( 'third_party/go/src/github.com/mdempsky/gocode/gocode' ),
      'third_party/go/src/github.com/mdempsky/gocode' ),
    ( Exe( 'third_party/go/src/github.com/rogpeppe/godef/godef' ),
      'third_party/go/src/github.com/rogpeppe/godef' ),
    # Java
    ( 'third_party/eclipse.jdt.ls/target/repository',
      'third_party/eclipse.jdt.ls/target/repository' ),
    # JavaScript and TypeScript
    ( 'third_party/tsserver', 'third_party/tsserver' ),
    # Python
    ( 'third_party/jedi/jedi', 'jedi' ),
    ( 'third_party/parso/parso', 'parso' ),
    # Rust
    ( Exe( 'third_party/racerd/target/release/racerd' ),
      'third_party/racerd/target/release' )
  ],
  hiddenimports = [
    'ycmd.completers.c.hook',
    'ycmd.completers.cpp.hook',
    'ycmd.completers.cs.hook',
    'ycmd.completers.cuda.hook',
    'ycmd.completers.go.hook',
    'ycmd.completers.java.hook',
    'ycmd.completers.javascript.hook',
    'ycmd.completers.objc.hook',
    'ycmd.completers.objcpp.hook',
    'ycmd.completers.python.hook',
    'ycmd.completers.rust.hook',
    'ycmd.completers.typescript.hook'
  ],
  hookspath = [],
  runtime_hooks = [],
  excludes = [],
  win_no_prefer_redirects = False,
  win_private_assemblies = False,
  cipher = block_cipher,
  noarchive = False )
pyz = PYZ( a.pure, a.zipped_data, cipher = block_cipher )
exe = EXE( pyz,
           a.scripts,
           [],
           exclude_binaries = True,
           name = 'ycmd',
           debug = False,
           bootloader_ignore_signals = False,
           strip = False,
           upx = True,
           console = True )
coll = COLLECT( exe,
                a.binaries,
                a.zipfiles,
                a.datas,
                strip = False,
                upx = True,
                name = 'ycmd' )
