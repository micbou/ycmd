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
import re
import threading
import time
from subprocess import STDOUT, PIPE
from ycmd import responses, utils
from ycmd.completers.language_server import language_server_completer
from collections import deque


_logger = logging.getLogger( __name__ )

LOGFILE_FORMAT = 'rls_'
TOOLCHAIN_CHANNEL = 'nightly'
TOOLCHAIN_DATE = '2018-02-15'
TOOLCHAIN = '{channel}-{date}'.format( channel = TOOLCHAIN_CHANNEL,
                                       date = TOOLCHAIN_DATE )
RUSTUP_TOOLCHAIN_REGEX = re.compile( r'^(?P<toolchain>[\w-]+)' )
RUSTUP_VERSION = re.compile( r'^rustup (?P<version>.*)$' )
RLS_VERSION = re.compile( r'^rls-preview (?P<version>.*)$' )


def _GetCommandOutput( command ):
  return utils.ToUnicode(
    utils.SafePopen( command,
                     stdin_windows = PIPE,
                     stdout = PIPE,
                     stderr = PIPE ).communicate()[ 0 ].rstrip() )


class RustCompleter( language_server_completer.LanguageServerCompleter ):
  def __init__( self, user_options ):
    super( RustCompleter, self ).__init__( user_options )

    self._server_keep_logfiles = user_options[ 'server_keep_logfiles' ]

    # Used to ensure that starting/stopping of the server is synchronized
    self._server_state_mutex = threading.RLock()
    self._server_starting = threading.Event()
    self._server_handle = None
    self._server_logfile = None
    self._server_started = False
    self._server_status = None

    self._toolchain = None
    self._rustup = None
    self._rustup_version = None
    self._rls = None
    self._rls_version = None

    self._notification_queue = deque()

    self._connection = None


  def SupportedFiletypes( self ):
    return [ 'rust' ]


  def GetSubcommandsMap( self ):
    return {
      # Handled by base class
      'FixIt': (
        lambda self, request_data, args: self.GetCodeActions( request_data,
                                                              args )
      ),
      'Format': (
        lambda self, request_data, args: self.Format( request_data )
       ),
      'GoToDeclaration': (
        lambda self, request_data, args: self.GoToDeclaration( request_data )
      ),
      'GoTo': (
        lambda self, request_data, args: self.GoToDeclaration( request_data )
      ),
      'GoToDefinition': (
        lambda self, request_data, args: self.GoToDeclaration( request_data )
      ),
      'GoToReferences': (
        lambda self, request_data, args: self.GoToReferences( request_data )
      ),
      'RefactorRename': (
        lambda self, request_data, args: self.RefactorRename( request_data,
                                                              args )
      ),

      # Handled by us
      'RestartServer': (
        lambda self, request_data, args: self._RestartServer( request_data )
      ),
      'StopServer': (
        lambda self, request_data, args: self._StopServer()
      ),
      'GetDoc': (
        lambda self, request_data, args: self.GetDoc( request_data )
      ),
      'GetType': (
        lambda self, request_data, args: self.GetType( request_data )
      )
    }


  def GetConnection( self ):
    return self._connection


  def OnFileReadyToParse( self, request_data ):
    self._StartServer( request_data )

    return super( RustCompleter, self ).OnFileReadyToParse( request_data )


  def _FindRustup( self ):
    for path in [ 'rustup', os.path.expanduser( '~/.cargo/bin/rustup' ) ]:
      rustup = utils.FindExecutable( path )
      if rustup:
        return rustup

    self._Notify( "Could not find rustup. Install it by following the "
                  "instructions on https://www.rustup.rs/ then "
                  "run the 'RestartServer' subcommand." )
    return None


  def _GetToolchainFullName( self, rustup ):
    toolchains = _GetCommandOutput( [ rustup, 'toolchain', 'list' ] )
    for line in toolchains.splitlines():
      match = RUSTUP_TOOLCHAIN_REGEX.search( line )
      if not match:
        _logger.error( "Cannot parse '{line}' as a toolchain "
                       "in rustup output.".format( line = line ) )
        continue

      toolchain = match.group( 'toolchain' )
      if TOOLCHAIN_CHANNEL in toolchain and TOOLCHAIN_DATE in toolchain:
        return toolchain
    return None


  def _GetRustupAndToolchain( self ):
    rustup = self._FindRustup()
    if not rustup:
      return None, None

    toolchain = self._GetToolchainFullName( rustup )
    if toolchain:
      return rustup, toolchain

    result = self._RunCommandAndNotify( [ rustup, 'toolchain', 'install',
                                          TOOLCHAIN ] )
    if not result:
      self._Notify( 'Failed to install toolchain {toolchain}.'.format(
        toolchain = TOOLCHAIN ) )
      return rustup, None

    toolchain = self._GetToolchainFullName( rustup )
    if toolchain:
      return rustup, toolchain

    self._Notify( 'Failed to get toolchain {toolchain}.'.format(
      toolchain = TOOLCHAIN ) )
    return rustup, None


  def _GetRustupVersion( self, rustup ):
    rustup_version = _GetCommandOutput( [ rustup, '--version' ] )
    match = RUSTUP_VERSION.match( rustup_version )
    if match:
      return match.group( 'version' )
    self._Notify( 'Cannot parse rustup version.' )
    return None


  def _GetRlsVersion( self, rls ):
    rls_version = _GetCommandOutput( [ rls, '--version' ] )
    match = RLS_VERSION.match( rls_version )
    if match:
      return match.group( 'version' )
    self._Notify( 'Cannot parse Rust Language Server version.' )
    return None


  def _FindRls( self ):
    rustup, toolchain = self._GetRustupAndToolchain()
    if not rustup or not toolchain:
      return None

    self._rustup = rustup
    self._rustup_version = self._GetRustupVersion( self._rustup )
    self._toolchain = toolchain

    toolchain_dir = _GetCommandOutput(
      [ rustup, 'run', toolchain, 'rustc', '--print', 'sysroot' ] )
    rls = os.path.join( toolchain_dir, 'bin', 'rls' )

    if not utils.FindExecutable( rls ):
      self._InstallRls( rustup, toolchain )

    rls = utils.FindExecutable( rls )
    if rls:
      self._rls = rls
      self._rls_version = self._GetRlsVersion( rls )
    return rls


  def _InstallRls( self, rustup, toolchain ):
    result = self._RunCommandAndNotify( [ rustup, 'self', 'update' ] )
    if not result:
      self._Notify( 'Failed to update rustup.' )
      return

    result = self._RunCommandAndNotify( [ rustup, 'update', toolchain ] )
    if not result:
      self._Notify( 'Failed to update toolchain {toolchain}.'.format(
        toolchain = toolchain ) )
      return

    for component in [ 'rls-preview', 'rust-analysis', 'rust-src' ]:
      result = self._RunCommandAndNotify( [
        rustup, 'component', 'add', component, '--toolchain', toolchain ] )
      if not result:
        self._Notify( 'Failed to update component {component}.'.format(
          component = component ) )
        return

    message = ( 'Rust Language Server for toolchain {toolchain} '
                'installed.'.format( toolchain = toolchain ) )
    self._Notify( message, level = 'info' )


  def DebugInfo( self, request_data ):
    return responses.BuildDebugInfoResponse(
      name = 'Rust',
      servers = [
        responses.DebugInfoServer(
          name = 'Rust Language Server',
          handle = self._server_handle,
          executable = self._rls,
          logfiles = [
            self._server_logfile
          ],
          extras = [
            responses.DebugInfoItem( 'status', self._server_status ),
            responses.DebugInfoItem( 'version', self._rls_version ),
          ]
        )
      ],
      items = [
        responses.DebugInfoItem( 'Rustup path', self._rustup ),
        responses.DebugInfoItem( 'Rustup version', self._rustup_version ),
        responses.DebugInfoItem( 'Toolchain', self._toolchain )
      ]
    )


  def Shutdown( self ):
    self._StopServer()


  def ServerIsHealthy( self ):
    return self._ServerIsRunning()


  def ServerIsReady( self ):
    return ( self.ServerIsHealthy() and
             super( RustCompleter, self ).ServerIsReady() )


  def _ServerIsRunning( self ):
    return utils.ProcessIsRunning( self._server_handle )


  def _RestartServer( self, request_data ):
    with self._server_state_mutex:
      self._StopServer()
      self._StartServer( request_data )


  def _StartServer( self, request_data ):
    with self._server_state_mutex:
      if self._server_starting.is_set():
        raise RuntimeError( 'Already starting server.' )

      self._server_starting.set()

    thread = threading.Thread( target = self._StartServerInThread,
                               args = ( request_data, ) )
    thread.daemon = True
    thread.start()


  def _StartServerInThread( self, request_data ):
    try:
      if self._server_started:
        return

      self._server_started = True

      rls = self._FindRls()
      if not rls:
        return

      _logger.info( 'Starting Rust Language Server...' )

      self._server_logfile = utils.CreateLogfile( LOGFILE_FORMAT )

      env = os.environ.copy()
      if _logger.isEnabledFor( logging.DEBUG ):
        utils.SetEnviron( env, 'RUST_LOG', 'rls::server=trace' )
        utils.SetEnviron( env, 'RUST_BACKTRACE', '1' )

      # RLS may use the wrong standard library if the active toolchain is not
      # the same as the one the server is running on. Set the active toolchain
      # through the RUSTUP_TOOLCHAIN environment variable.
      utils.SetEnviron( env, 'RUSTUP_TOOLCHAIN', self._toolchain )

      with utils.OpenForStdHandle( self._server_logfile ) as stderr:
        self._server_handle = utils.SafePopen( rls,
                                               stdin = PIPE,
                                               stdout = PIPE,
                                               stderr = stderr,
                                               env = env )

      if not self._ServerIsRunning():
        self._Notify( 'Rust Language Server failed to start.' )
        return

      _logger.info( 'Rust Language Server started.' )

      self._connection = (
        language_server_completer.StandardIOLanguageServerConnection(
          self._server_handle.stdin,
          self._server_handle.stdout,
          self.GetDefaultRequestHandler(),
          self.GetDefaultNotificationHandler() )
      )

      self._connection.start()

      try:
        self._connection.AwaitServerConnection()
      except language_server_completer.LanguageServerConnectionTimeout:
        self._Notify( 'Rust Language Server failed to start, or did not '
                      'connect successfully.' )
        self._StopServer()
        return

      self.SendInitialize( request_data )
    finally:
      self._server_starting.clear()


  def _StopServer( self ):
    with self._server_state_mutex:
      _logger.info( 'Shutting down Rust Language Server...' )
      # We don't use utils.CloseStandardStreams, because the stdin/out is
      # connected to our server connector. Just close stderr.
      #
      # The other streams are closed by the LanguageServerConnection when we
      # call Close.
      if self._server_handle and self._server_handle.stderr:
        self._server_handle.stderr.close()

      # Tell the connection to expect the server to disconnect.
      if self._connection:
        self._connection.Stop()

      if not self._ServerIsRunning():
        _logger.info( 'Rust Language Server not running' )
        self._CleanUp()
        return

      _logger.info( 'Stopping Rust Language Server with PID {0}'.format(
         self._server_handle.pid ) )

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

        _logger.info( 'Rust Language server stopped' )
      except Exception:
        _logger.exception( 'Error while stopping Rust Language Server' )
        # We leave the process running. Hopefully it will eventually die of its
        # own accord.

      # Tidy up our internal state, even if the completer server didn't close
      # down cleanly.
      self._CleanUp()


  def _CleanUp( self ):
    self._server_handle = None
    self._server_started = False
    self._server_status = None
    self._connection = None
    self.ServerReset()
    if not self._server_keep_logfiles:
      if self._server_logfile:
        utils.RemoveIfExists( self._server_logfile )
        self._server_logfile = None


  def _ShouldResolveCompletionItems( self ):
    # FIXME: RLS tells us that it can resolve a completion but it doesn't
    # follow the protocol since it returns a list containing one completion
    # instead of the completion item directly. In addition, it doesn't return
    # any additional information so there is no point to resolve a completion.
    return False


  def HandleNotificationInPollThread( self, notification ):
    # FIXME: the build status is currently displayed in the debug info. We
    # should notify the client about it through a special status/progress
    # message.
    if notification[ 'method' ] == 'rustDocument/beginBuild':
      self._server_status = 'building'
      return

    if notification[ 'method' ] == 'rustDocument/diagnosticsEnd':
      self._server_status = 'ready'
      return

    super( RustCompleter, self ).HandleNotificationInPollThread( notification )


  def _Notify( self, message, level = 'error' ):
    getattr( _logger, level )( message )
    self._notification_queue.append(
      responses.BuildDisplayMessageResponse( message ) )


  def _RunCommandAndNotify( self, command ):
    handle = utils.SafePopen( command, stdout = PIPE, stderr = STDOUT )
    for line in handle.stdout:
      message = utils.ToUnicode( line.strip() )
      if message:
        self._Notify( message, level = 'debug' )

    handle.communicate()
    return handle.returncode == 0


  def PollForMessagesInner( self, request_data, timeout ):
    expiration = time.time() + timeout
    while True:
      if time.time() > expiration:
        return True

      # If there are messages pending in the queue, return them immediately
      messages = self._GetPendingMessages( request_data )
      if messages:
        return messages

      try:
        return [ self._notification_queue.popleft() ]
      except IndexError:
        time.sleep( 0.1 )


  def GetType( self, request_data ):
    hover_response = self.GetHoverResponse( request_data )

    # RLS returns a list that may contain the following elements:
    # - a documentation string;
    # - a documentation url;
    # - [{language:rust, value:<type info>}].

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
