# Copyright (C) 2015-2018 ycmd contributors
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

import logging
import os
import threading
from subprocess import PIPE
from ycmd import responses, utils
from ycmd.completers.language_server import language_server_completer
from ycmd.utils import LOGGER, re


LOGFILE_FORMAT = 'rls_'
RLS_TOOLCHAIN = os.path.abspath(
  os.path.join( os.path.dirname( __file__ ), '..', '..', '..', 'third_party',
                'rls' ) )
RLS_EXECUTABLE = utils.FindExecutable(
  os.path.join( RLS_TOOLCHAIN, 'bin', 'rls' ) )
RLS_VERSION = re.compile( r'^rls (?P<version>.*)$' )


def _GetCommandOutput( command ):
  return utils.ToUnicode(
    utils.SafePopen( command,
                     stdin_windows = PIPE,
                     stdout = PIPE,
                     stderr = PIPE ).communicate()[ 0 ].rstrip() )


def _GetRlsVersion():
  rls_version = _GetCommandOutput( [ RLS_EXECUTABLE, '--version' ] )
  match = RLS_VERSION.match( rls_version )
  if not match:
    LOGGER.error( 'Cannot parse Rust Language Server version: %s', rls_version )
    return None
  return match.group( 'version' )


def ShouldEnableRustCompleter():
  if not RLS_EXECUTABLE:
    LOGGER.error( 'Not using Rust completer: no RLS executable found at %s',
                  RLS_EXECUTABLE )
    return False
  LOGGER.info( 'Using Rust completer' )
  return True


def _FindProjectDir( path ):
  project_path = os.path.dirname( path )
  for folder in utils.PathsToAllParentFolders( path ):
    if os.path.isfile( os.path.join( folder, 'Cargo.toml' ) ):
      project_path = folder
      break

  return project_path


class RustCompleter( language_server_completer.LanguageServerCompleter ):
  def __init__( self, user_options ):
    super( RustCompleter, self ).__init__( user_options )

    self._server_keep_logfiles = user_options[ 'server_keep_logfiles' ]

    # Used to ensure that starting/stopping of the server is synchronized.
    # Guards _connection and _server_handle.
    self._server_state_mutex = threading.RLock()
    self._server_handle = None
    self._server_logfile = None
    self._server_started = False
    self._server_progress = {}

    self._connection = None


  def _Reset( self ):
    with self._server_state_mutex:
      self._server_handle = None
      self._server_started = False
      self._server_progress = {}
      self._connection = None
      self.ServerReset()
      if not self._server_keep_logfiles:
        if self._server_logfile:
          utils.RemoveIfExists( self._server_logfile )
          self._server_logfile = None


  def Language( self ):
    return 'rust'


  def SupportedFiletypes( self ):
    return [ 'rust' ]


  def GetCustomSubcommands( self ):
    return {
      'GetDoc': (
        lambda self, request_data, args: self.GetDoc( request_data )
      ),
      'GetType': (
        lambda self, request_data, args: self.GetType( request_data )
      ),
      'RestartServer': (
        lambda self, request_data, args: self._RestartServer( request_data )
      )
    }


  def GetConnection( self ):
    return self._connection


  def DebugInfo( self, request_data ):
    with self._server_state_mutex:
      status = ( ', '.join( [ progress for progress in self._server_progress ] )
                 or 'ready' )
      return responses.BuildDebugInfoResponse(
        name = 'Rust',
        servers = [
          responses.DebugInfoServer(
            name = 'Rust Language Server',
            handle = self._server_handle,
            executable = RLS_EXECUTABLE,
            logfiles = [ self._server_logfile ],
            extras = self.CommonDebugItems() + [
              responses.DebugInfoItem( 'Build Status', status ),
              responses.DebugInfoItem( 'Version', _GetRlsVersion() )
            ]
          )
        ]
      )


  def ServerIsHealthy( self ):
    return self._ServerIsRunning()


  def ServerIsReady( self ):
    return ( self.ServerIsHealthy() and
             super( RustCompleter, self ).ServerIsReady() )


  def _ServerIsRunning( self ):
    return utils.ProcessIsRunning( self._server_handle )


  def _RestartServer( self, request_data ):
    with self._server_state_mutex:
      self.Shutdown()
      self._StartAndInitializeServer( request_data )


  def _GetProjectDirectory( self, *args, **kwargs ):
    return self._rust_project_directory


  def StartServer( self, request_data ):
    with self._server_state_mutex:
      LOGGER.info( 'Starting Rust Language Server...' )

      self._rust_project_directory = _FindProjectDir(
          request_data[ 'filepath' ] )

      self._server_logfile = utils.CreateLogfile( LOGFILE_FORMAT )

      env = os.environ.copy()
      if LOGGER.isEnabledFor( logging.DEBUG ):
        utils.SetEnviron( env, 'RUST_LOG', 'rls=trace' )
        utils.SetEnviron( env, 'RUST_BACKTRACE', '1' )

      # RLS may use the wrong standard library if the active toolchain is not
      # the same as the one the server is running on. Set the active toolchain
      # through the RUSTUP_TOOLCHAIN environment variable.
      # TODO: is this still relevant?
      utils.SetEnviron( env, 'RUSTUP_TOOLCHAIN', RLS_TOOLCHAIN )

      with utils.OpenForStdHandle( self._server_logfile ) as stderr:
        self._server_handle = utils.SafePopen( RLS_EXECUTABLE,
                                               stdin = PIPE,
                                               stdout = PIPE,
                                               stderr = stderr,
                                               env = env )

      self._connection = (
        language_server_completer.StandardIOLanguageServerConnection(
          self._server_handle.stdin,
          self._server_handle.stdout,
          self.GetDefaultNotificationHandler() )
      )

      self._connection.start()

      try:
        self._connection.AwaitServerConnection()
      except language_server_completer.LanguageServerConnectionTimeout:
        LOGGER.error( 'Rust Language Server failed to start, or did not '
                       'connect successfully.' )
        self.Shutdown()
        return False

    LOGGER.info( 'Rust Language Server started' )

    return True


  def Shutdown( self ):
    with self._server_state_mutex:
      LOGGER.info( 'Shutting down Rust Language Server...' )

      # Tell the connection to expect the server to disconnect.
      if self._connection:
        self._connection.Stop()

      if not self._ServerIsRunning():
        LOGGER.info( 'Rust Language Server not running' )
        self._Reset()
        return

      LOGGER.info( 'Stopping Rust Language Server with PID %s',
                   self._server_handle.pid )

      try:
        self.ShutdownServer()

        # By this point, the server should have shut down and terminated. To
        # ensure that isn't blocked, we close all of our connections and wait
        # for the process to exit.
        #
        # If, after a small delay, the server has not shut down we do NOT kill
        # it; we expect that it will shut itself down eventually. This is
        # predominantly due to strange process behaviour on Windows.
        if self._connection:
          self._connection.Close()

        utils.WaitUntilProcessIsTerminated( self._server_handle,
                                            timeout = 15 )

        LOGGER.info( 'Rust Language server stopped' )
      except Exception:
        LOGGER.exception( 'Error while stopping Rust Language Server' )
        # We leave the process running. Hopefully it will eventually die of its
        # own accord.

      # Tidy up our internal state, even if the completer server didn't close
      # down cleanly.
      self._Reset()


  def _ShouldResolveCompletionItems( self ):
    # RLS tells us that it can resolve a completion but there is no point since
    # no additional information is returned.
    return False


  def HandleNotificationInPollThread( self, notification ):
    # FIXME: the indexing and building status is currently displayed in the
    # debug info. We should notify the client about it through a special
    # status/progress message.
    if notification[ 'method' ] == 'window/progress':
      params = notification[ 'params' ]
      progress_id = params[ 'id' ]
      if 'done' in params:
        self._server_progress.pop( progress_id, None )
        return
      message = params[ 'title' ].lower()
      if 'message' in params:
        message += ' ' + params[ 'message' ]
      self._server_progress[ progress_id ] = message
      return

    super( RustCompleter, self ).HandleNotificationInPollThread( notification )


  def GetType( self, request_data ):
    hover_response = self.GetHoverResponse( request_data )

    for item in hover_response:
      if isinstance( item, dict ) and 'value' in item:
        return responses.BuildDisplayMessageResponse( item[ 'value' ] )

    raise RuntimeError( 'Unknown type.' )


  def GetDoc( self, request_data ):
    hover_response = self.GetHoverResponse( request_data )

    # RLS returns a list that may contain the following elements:
    # - a documentation string;
    # - a documentation url;
    # - [{language:rust, value:<type info>}].

    documentation = '\n'.join(
      [ item.strip() for item in hover_response if isinstance( item, str ) ] )

    if not documentation:
      raise RuntimeError( 'No documentation available for current context.' )

    return responses.BuildDetailedInfoResponse( documentation )


  def HandleServerCommand( self, request_data, command ):
    return None # pragma: no cover
