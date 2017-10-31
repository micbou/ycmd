# Copyright (C) 2018 ycmd contributors
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

from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
# Not installing aliases from python-future; it's unreliable and slow.
from builtins import *  # noqa

import psutil
import time
import threading
from hamcrest import assert_that, contains, has_entry
from mock import patch

from ycmd import handlers
from ycmd.tests.rust import ( PathToTestFile,
                              IsolatedYcmd,
                              StartRustCompleterServerInDirectory )
from ycmd.tests.test_utils import ( BuildRequest,
                                    MockProcessTerminationTimingOut,
                                    WaitUntilCompleterServerReady )


def AssertRustCompleterServerIsRunning( app, is_running ):
  request_data = BuildRequest( filetype = 'rust' )
  assert_that( app.post_json( '/debug_info', request_data ).json,
               has_entry(
                 'completer',
                 has_entry( 'servers', contains(
                   has_entry( 'is_running', is_running )
                 ) )
               ) )


@IsolatedYcmd
def ServerManagement_RestartServer_test( app ):
  filepath = PathToTestFile( 'common', 'src', 'main.rs' )
  StartRustCompleterServerInDirectory( app, filepath )

  AssertRustCompleterServerIsRunning( app, True )

  app.post_json(
    '/run_completer_command',
    BuildRequest(
      filepath = filepath,
      filetype = 'rust',
      command_arguments = [ 'RestartServer' ],
    ),
  )

  WaitUntilCompleterServerReady( app, 'rust' )

  AssertRustCompleterServerIsRunning( app, True )


@IsolatedYcmd
@patch( 'shutil.rmtree', side_effect = OSError )
@patch( 'ycmd.utils.WaitUntilProcessIsTerminated',
        MockProcessTerminationTimingOut )
def ServerManagement_CloseServer_Unclean_test( app, *args ):
  StartRustCompleterServerInDirectory( app, PathToTestFile( 'common', 'src' ) )

  app.post_json(
    '/run_completer_command',
    BuildRequest(
      filetype = 'rust',
      command_arguments = [ 'StopServer' ]
    )
  )

  request_data = BuildRequest( filetype = 'rust' )
  assert_that( app.post_json( '/debug_info', request_data ).json,
               has_entry(
                 'completer',
                 has_entry( 'servers', contains(
                   has_entry( 'is_running', False )
                 ) )
               ) )


@IsolatedYcmd
def ServerManagement_StopServerTwice_test( app ):
  StartRustCompleterServerInDirectory( app, PathToTestFile( 'common', 'src' ) )

  app.post_json(
    '/run_completer_command',
    BuildRequest(
      filetype = 'rust',
      command_arguments = [ 'StopServer' ],
    ),
  )

  AssertRustCompleterServerIsRunning( app, False )

  # Stopping a stopped server is a no-op
  app.post_json(
    '/run_completer_command',
    BuildRequest(
      filetype = 'rust',
      command_arguments = [ 'StopServer' ],
    ),
  )

  AssertRustCompleterServerIsRunning( app, False )


@IsolatedYcmd
def ServerManagement_ServerDies_test( app ):
  StartRustCompleterServerInDirectory( app, PathToTestFile( 'common', 'src' ) )

  request_data = BuildRequest( filetype = 'rust' )
  debug_info = app.post_json( '/debug_info', request_data ).json
  print( 'Debug info: {0}'.format( debug_info ) )
  pid = debug_info[ 'completer' ][ 'servers' ][ 0 ][ 'pid' ]
  print( 'pid: {0}'.format( pid ) )
  process = psutil.Process( pid )
  process.terminate()

  for tries in range( 0, 10 ):
    request_data = BuildRequest( filetype = 'rust' )
    debug_info = app.post_json( '/debug_info', request_data ).json
    if not debug_info[ 'completer' ][ 'servers' ][ 0 ][ 'is_running' ]:
      break

    time.sleep( 0.5 )

  AssertRustCompleterServerIsRunning( app, False )


@IsolatedYcmd
def ServerManagement_ServerDiesWhileShuttingDown_test( app ):
  StartRustCompleterServerInDirectory( app, PathToTestFile( 'common', 'src' ) )

  request_data = BuildRequest( filetype = 'rust' )
  debug_info = app.post_json( '/debug_info', request_data ).json
  print( 'Debug info: {0}'.format( debug_info ) )
  pid = debug_info[ 'completer' ][ 'servers' ][ 0 ][ 'pid' ]
  print( 'pid: {0}'.format( pid ) )
  process = psutil.Process( pid )


  def StopServerInAnotherThread():
    app.post_json(
      '/run_completer_command',
      BuildRequest(
        filetype = 'rust',
        command_arguments = [ 'StopServer' ],
      ),
    )

  completer = handlers._server_state.GetFiletypeCompleter( [ 'rust' ] )

  # In this test we mock out the sending method so that we don't actually send
  # the shutdown request. We then assisted-suicide the downstream server, which
  # causes the shutdown request to be aborted. This is interpreted by the
  # shutdown code as a successful shutdown. We need to do the shutdown and
  # terminate in parallel as the post_json is a blocking call.
  with patch.object( completer.GetConnection(), 'WriteData' ):
    stop_server_task = threading.Thread( target=StopServerInAnotherThread )
    stop_server_task.start()
    process.terminate()
    stop_server_task.join()

  AssertRustCompleterServerIsRunning( app, False )


@IsolatedYcmd
def ServerManagement_ConnectionRaisesWhileShuttingDown_test( app ):
  StartRustCompleterServerInDirectory( app, PathToTestFile( 'common', 'src' ) )

  request_data = BuildRequest( filetype = 'rust' )
  debug_info = app.post_json( '/debug_info', request_data ).json
  print( 'Debug info: {0}'.format( debug_info ) )
  pid = debug_info[ 'completer' ][ 'servers' ][ 0 ][ 'pid' ]
  print( 'pid: {0}'.format( pid ) )
  process = psutil.Process( pid )

  completer = handlers._server_state.GetFiletypeCompleter( [ 'rust' ] )

  # In this test we mock out the GetResponse method, which is used to send the
  # shutdown request. This means we only send the exit notification. It's
  # possible that the server won't like this, but it seems reasonable for it to
  # actually exit at that point.
  with patch.object( completer.GetConnection(),
                     'GetResponse',
                     side_effect = RuntimeError ):
    app.post_json(
      '/run_completer_command',
      BuildRequest(
        filetype = 'rust',
        command_arguments = [ 'StopServer' ],
      ),
    )

  AssertRustCompleterServerIsRunning( app, False )

  if process.is_running():
    process.terminate()
    raise AssertionError( 'RLS process is still running after exit handler' )
