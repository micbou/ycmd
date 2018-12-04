# Copyright (C) 2016 ycmd contributors
#
# This file is part of ycmd.
#
# ycmd is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ycmd is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ycmd.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
# Not installing aliases from python-future; it's unreliable and slow.
from builtins import *  # noqa

import functools
import os
import contextlib
import json

from hamcrest import ( assert_that )
from nose.tools import eq_


from ycmd.utils import ToUnicode
from ycmd.tests.test_utils import ( BuildRequest,
                                    ClearCompletionsCache,
                                    CombineRequest,
                                    IsolatedApp,
                                    SetUpApp,
                                    StopCompleterServer,
                                    WaitUntilCompleterServerReady )
from ycmd.utils import ReadFile

shared_app = None


def PathToTestFile( *args ):
  dir_of_current_script = os.path.dirname( os.path.abspath( __file__ ) )
  return os.path.join( dir_of_current_script, 'testdata', *args )


def setUpPackage():
  """Initializes the ycmd server as a WebTest application that will be shared
  by all tests using the SharedYcmd decorator in this package. Additional
  configuration that is common to these tests, like starting a semantic
  subserver, should be done here."""
  global shared_app

  user_options_with_clangd = { 'use_clangd': True }
  shared_app = SetUpApp( user_options_with_clangd )


def tearDownPackage():
  global shared_app

  StopCompleterServer( shared_app, 'cpp', '' )


def SharedYcmd( test ):
  """Defines a decorator to be attached to tests of this package. This decorator
  passes the shared ycmd application as a parameter.

  Do NOT attach it to test generators but directly to the yielded tests."""
  global shared_app

  @functools.wraps( test )
  def Wrapper( *args, **kwargs ):
    ClearCompletionsCache()
    return test( shared_app, *args, **kwargs )
  return Wrapper


def IsolatedYcmd( custom_options = {} ):
  """Defines a decorator to be attached to tests of this package. This decorator
  passes a unique ycmd application as a parameter. It should be used on tests
  that change the server state in a irreversible way (ex: a semantic subserver
  is stopped or restarted) or expect a clean state (ex: no semantic subserver
  started, no .ycm_extra_conf.py loaded, etc). Use the optional parameter
  |custom_options| to give additional options and/or override the default ones.

  Do NOT attach it to test generators but directly to the yielded tests.

  Example usage:

    from ycmd.tests.clang import IsolatedYcmd

    @IsolatedYcmd( { 'auto_trigger': 0 } )
    def CustomAutoTrigger_test( app ):
      ...
  """
  def Decorator( test ):
    @functools.wraps( test )
    def Wrapper( *args, **kwargs ):
      custom_options.update( { 'use_clangd': True } )
      with IsolatedApp( custom_options ) as app:
        test( app, *args, **kwargs )
        app.post_json( '/run_completer_command',
                        BuildRequest( completer_target = 'cpp',
                                      command_arguments = [ 'StopServer' ] ) )
    return Wrapper
  return Decorator


@contextlib.contextmanager
def TemporaryClangProject( tmp_dir, compile_commands ):
  """Context manager to create a compilation database in a directory and delete
  it when the test completes. |tmp_dir| is the directory in which to create the
  database file (typically used in conjunction with |TemporaryTestDir|) and
  |compile_commands| is a python object representing the compilation database.

  e.g.:
    with TemporaryTestDir() as tmp_dir:
      database = [
        {
          'directory': os.path.join( tmp_dir, dir ),
          'command': compiler_invocation,
          'file': os.path.join( tmp_dir, dir, filename )
        },
        ...
      ]
      with TemporaryClangProject( tmp_dir, database ):
        <test here>

  The context manager does not yield anything.
  """
  path = os.path.join( tmp_dir, 'compile_commands.json' )

  with open( path, 'w' ) as f:
    f.write( ToUnicode( json.dumps( compile_commands, indent=2 ) ) )

  try:
    yield
  finally:
    os.remove( path )


def RunAfterInitialized( app, test ):
  request = test[ 'request' ]
  contents = ( request[ 'contents' ] if 'contents' in request else
               ReadFile( request[ 'filepath' ] ) )
  response = app.post_json( '/event_notification',
                 CombineRequest( request, {
                   'event_name': 'FileReadyToParse',
                   'contents': contents,
                 } ),
                 expect_errors = True )
  WaitUntilCompleterServerReady( app, 'cpp' )

  if 'route' in test:
    expect_errors = 'expect' in test
    response = app.post_json( test[ 'route' ],
                              CombineRequest( request, {
                                'contents': contents
                              } ),
                              expect_errors = expect_errors )

  if 'expect' in test:
    eq_( response.status_code, test[ 'expect' ][ 'response' ] )
    assert_that( response.json, test[ 'expect' ][ 'data' ] )
  return response.json
