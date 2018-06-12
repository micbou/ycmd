#!/usr/bin/env python

# Passing an environment variable containing unicode literals to a subprocess
# on Windows and Python2 raises a TypeError. Since there is no unicode
# string in this script, we don't import unicode_literals to avoid the issue.
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
# Not installing aliases from python-future; it's unreliable and slow.
from builtins import *  # noqa

import platform
import os
import subprocess
import os.path as p
import sys

DIR_OF_THIS_SCRIPT = p.dirname( p.abspath( __file__ ) )
DIR_OF_THIRD_PARTY = p.join( DIR_OF_THIS_SCRIPT, 'third_party' )

python_path = []
for folder in os.listdir( DIR_OF_THIRD_PARTY ):
  # We skip python-future because it needs to be inserted in sys.path AFTER
  # the standard library imports but we can't do that with PYTHONPATH because
  # the std lib paths are always appended to PYTHONPATH. We do it correctly in
  # prod in ycmd/utils.py because we have access to the right sys.path.
  # So for dev, we rely on python-future being installed correctly with
  #   pip install -r test_requirements.txt
  #
  # Pip knows how to install this correctly so that it doesn't matter where in
  # sys.path the path is.
  if folder == 'python-future':
    continue
  if folder == 'cregex':
    folder = p.join( folder, 'regex_{}'.format( sys.version_info[ 0 ] ) )
  python_path.append( p.abspath( p.join( DIR_OF_THIRD_PARTY, folder ) ) )
if os.environ.get( 'PYTHONPATH' ) is not None:
  python_path.append( os.environ['PYTHONPATH'] )
os.environ[ 'PYTHONPATH' ] = os.pathsep.join( python_path )

sys.path.insert( 1, p.abspath( p.join( DIR_OF_THIRD_PARTY, 'argparse' ) ) )

import argparse


def RunFlake8():
  print( 'Running flake8' )
  subprocess.check_call( [
    sys.executable, '-m', 'flake8', p.join( DIR_OF_THIS_SCRIPT, 'ycmd' )
  ] )


COMPLETERS = {
  'cfamily': {
    'build': [ '--clang-completer' ],
    'test': [ '--exclude-dir=ycmd/tests/clang' ],
    'aliases': [ 'c', 'cpp', 'c++', 'objc', 'clang', ]
  },
  'cs': {
    'build': [ '--cs-completer' ],
    'test': [ '--exclude-dir=ycmd/tests/cs' ],
    'aliases': [ 'omnisharp', 'csharp', 'c#' ]
  },
  'javascript': {
    'build': [ '--js-completer' ],
    'test': [ '--exclude-dir=ycmd/tests/javascript',
              '--exclude-dir=ycmd/tests/tern' ],
    'aliases': [ 'js', 'tern' ]
  },
  'go': {
    'build': [ '--go-completer' ],
    'test': [ '--exclude-dir=ycmd/tests/go' ],
    'aliases': [ 'gocode' ]
  },
  'rust': {
    'build': [ '--rust-completer' ],
    'test': [ '--exclude-dir=ycmd/tests/rust' ],
    'aliases': [ 'racer', 'racerd', ]
  },
  'typescript': {
    'build': [],
    'test': [ '--exclude-dir=ycmd/tests/typescript' ],
    'aliases': []
  },
  'python': {
    'build': [],
    'test': [ '--exclude-dir=ycmd/tests/python' ],
    'aliases': [ 'jedi', 'jedihttp', ]
  },
  'java': {
    'build': [ '--java-completer' ],
    'test': [ '--exclude-dir=ycmd/tests/java' ],
    'aliases': [ 'jdt' ],
  },
}


def CompleterType( value ):
  value = value.lower()
  if value in COMPLETERS:
    return value
  else:
    aliases_to_completer = dict( ( i, k ) for k, v in COMPLETERS.items()
                                 for i in v[ 'aliases' ] )
    if value in aliases_to_completer:
      return aliases_to_completer[ value ]
    else:
      raise argparse.ArgumentTypeError(
        '{0} is not a valid completer - should be one of {1}'.format(
          value, COMPLETERS.keys() ) )


def ParseArguments():
  parser = argparse.ArgumentParser()
  group = parser.add_mutually_exclusive_group()
  group.add_argument( '--no-clang-completer', action = 'store_true',
                       help = argparse.SUPPRESS ) # deprecated
  group.add_argument( '--no-completers', nargs ='*', type = CompleterType,
                       help = 'Do not build or test with listed semantic '
                       'completion engine(s). Valid values: {0}'.format(
                        COMPLETERS.keys()) )
  group.add_argument( '--completers', nargs ='*', type = CompleterType,
                       help = 'Only build and test with listed semantic '
                       'completion engine(s). Valid values: {0}'.format(
                        COMPLETERS.keys()) )
  parser.add_argument( '--skip-build', action = 'store_true',
                       help = 'Do not build ycmd before testing.' )
  parser.add_argument( '--msvc', type = int, choices = [ 14, 15 ],
                       default = 15, help = 'Choose the Microsoft Visual '
                       'Studio version (default: %(default)s).' )
  parser.add_argument( '--coverage', action = 'store_true',
                       help = 'Enable coverage report (requires coverage pkg)' )
  parser.add_argument( '--no-flake8', action = 'store_true',
                       help = 'Disable flake8 run.' )
  parser.add_argument( '--dump-path', action = 'store_true',
                       help = 'Dump the PYTHONPATH required to run tests '
                              'manually, then exit.' )
  parser.add_argument( '--no-retry', action = 'store_true',
                       help = 'Disable retry of flaky tests' )
  parser.add_argument( '--runs', type = int, default = 1,
                       help = 'Number of test runs.' )

  parsed_args, nosetests_args = parser.parse_known_args()

  parsed_args.completers = FixupCompleters( parsed_args )

  if 'COVERAGE' in os.environ:
    parsed_args.coverage = ( os.environ[ 'COVERAGE' ] == 'true' )

  return parsed_args, nosetests_args


def FixupCompleters( parsed_args ):
  completers = set( COMPLETERS.keys() )
  if parsed_args.completers is not None:
    completers = set( parsed_args.completers )
  elif parsed_args.no_completers is not None:
    completers = completers.difference( parsed_args.no_completers )
  elif parsed_args.no_clang_completer:
    print( 'WARNING: The "--no-clang-completer" flag is deprecated. '
           'Please use "--no-completers cfamily" instead.' )
    completers.discard( 'cfamily' )

  if 'USE_CLANG_COMPLETER' in os.environ:
    if os.environ[ 'USE_CLANG_COMPLETER' ] == 'false':
      completers.discard( 'cfamily' )
    else:
      completers.add( 'cfamily' )

  return list( completers )


def BuildYcmdLibs( args ):
  if not args.skip_build:
    if 'EXTRA_CMAKE_ARGS' in os.environ:
      os.environ[ 'EXTRA_CMAKE_ARGS' ] += ' -DUSE_DEV_FLAGS=ON'
    else:
      os.environ[ 'EXTRA_CMAKE_ARGS' ] = '-DUSE_DEV_FLAGS=ON'

    build_cmd = [
      sys.executable,
      p.join( DIR_OF_THIS_SCRIPT, 'build.py' ),
      '--core-tests',
      '--quiet',
    ]

    for key in COMPLETERS:
      if key in args.completers:
        build_cmd.extend( COMPLETERS[ key ][ 'build' ] )

    if args.msvc:
      build_cmd.extend( [ '--msvc', str( args.msvc ) ] )

    if args.coverage:
      # In order to generate coverage data for C++, we use gcov. This requires
      # some files generated when building (*.gcno), so we store the build
      # output in a known directory, which is then used by the CI infrastructure
      # to generate the c++ coverage information.
      build_cmd.extend( [ '--enable-coverage', '--build-dir', '.build' ] )

    subprocess.check_call( build_cmd )


def NoseTests( parsed_args, extra_nosetests_args ):
  # Always passing --with-id to nosetests enables non-surprising usage of
  # its --failed flag.
  # By default, nose does not include files starting with a underscore in its
  # report but we want __main__.py to be included. Only ignore files starting
  # with a dot and setup.py.
  nosetests_args = [ '-v', '--with-id', '--ignore-files=(^\.|^setup\.py$)' ]

  for key in COMPLETERS:
    if key not in parsed_args.completers:
      nosetests_args.extend( COMPLETERS[ key ][ 'test' ] )

  if parsed_args.coverage:
    # We need to exclude the ycmd/tests/python/testdata directory since it
    # contains Python files and its base name starts with "test".
    nosetests_args += [ '--exclude-dir=ycmd/tests/python/testdata',
                        '--with-coverage',
                        '--cover-erase',
                        '--cover-package=ycmd',
                        '--cover-html',
                        '--cover-inclusive' ]

  if extra_nosetests_args:
    nosetests_args.extend( extra_nosetests_args )
  else:
    nosetests_args.append( p.join( DIR_OF_THIS_SCRIPT, 'ycmd' ) )

  env = os.environ.copy()

  if parsed_args.no_retry:
    # Useful for _writing_ tests
    env[ 'YCM_TEST_NO_RETRY' ] = '1'

  for number in range( 1, parsed_args.runs + 1 ):
    sys.stdout.write(
      'Run {number}/{total}\n'.format( number = number,
                                       total = parsed_args.runs ) )
    sys.stdout.flush()
    subprocess.check_call( [ sys.executable, '-m', 'nose' ] + nosetests_args,
                           env = env )


def Main():
  parsed_args, nosetests_args = ParseArguments()
  if parsed_args.dump_path:
    print( os.environ[ 'PYTHONPATH' ] )
    sys.exit()
  print( 'Running tests on Python', platform.python_version() )
  if not parsed_args.no_flake8:
    RunFlake8()
  BuildYcmdLibs( parsed_args )
  NoseTests( parsed_args, nosetests_args )


if __name__ == "__main__":
  Main()
