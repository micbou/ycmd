# Copyright (C) 2017 ycmd contributors
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


_logger = logging.getLogger( __name__ )


PHP_LANGUAGE_SERVER = os.path.abspath(
  os.path.join( os.path.dirname( __file__ ), '..', '..', '..', 'third_party',
                'php_runtime', 'vendor', 'felixfbecker', 'language-server',
                'bin', 'php-language-server.php' ) )
PHP_EXECUTABLE = utils.FindExecutable( 'php' )


def ShouldEnablePhpCompleter():
  _logger.info( 'Looking for PHP Language Server.' )
  if not PHP_EXECUTABLE:
    _logger.warning( 'Not enabling PHP completion: could not find PHP.' )
    return False

  if not os.path.exists( PHP_LANGUAGE_SERVER ):
    _logger.warning( 'Not using PHP completion: PHP Language Server not '
                     'installed.' )
    return False

  return True


class PhpCompleter( language_server_completer.LanguageServerCompleter ):
  def __init__( self, user_options ):
    super( PhpCompleter, self ).__init__( user_options )

    self._server_keep_logfiles = user_options[ 'server_keep_logfiles' ]
    # Used to ensure that starting/stopping of the server is synchronized
    self._server_state_mutex = threading.RLock()
    self._server_handle = None
    self._server_stdout = None
    self._server_stderr = None
    self._server_port = None

    self._connection = None
    self._StartServer()


  def SupportedFiletypes( self ):
    return [ 'php' ]


  def GetSubcommandsMap( self ):
    return {
      # Handled by base class
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
      'FixIt': (
        lambda self, request_data, args: self.CodeAction( request_data,
                                                          args )
      ),
      'RefactorRename': (
        lambda self, request_data, args: self.Rename( request_data, args )
      ),

      # Handled by us
      'RestartServer': (
        lambda self, request_data, args: self._RestartServer( request_data )
      ),
      'StopServer': (
        lambda self, request_data, args: self._StopServer()
      )
      # TODO
      # 'GetDoc': (
      #   lambda self, request_data, args: self.GetDoc( request_data )
      # ),
      # 'GetType': (
      #   lambda self, request_data, args: self.GetType( request_data )
      # ),
    }


  def GetConnection( self ):
    return self._connection


  def DebugInfo( self, request_data ):
    extras = [
      responses.DebugInfoItem( 'PHP executable', PHP_EXECUTABLE )
    ]

    return responses.BuildDebugInfoResponse(
      name = 'PHP',
      servers = [
        responses.DebugInfoServer(
          name = 'PHP Language Server',
          handle = self._server_handle,
          executable = PHP_LANGUAGE_SERVER,
          address = '127.0.0.1',
          port = self._server_port,
          logfiles = [
            self._server_stdout,
            self._server_stderr
          ],
          extras = extras
        )
      ] )


  def Shutdown( self ):
    self._StopServer()


  def ServerIsHealthy( self ):
    return self._ServerIsRunning()


  def ServerIsReady( self ):
    return ( self.ServerIsHealthy() and
             super( PhpCompleter, self ).ServerIsReady() )


  def _ServerIsRunning( self ):
    return utils.ProcessIsRunning( self._server_handle )


  def _RestartServer( self, request_data ):
    with self._server_state_mutex:
      self._StopServer()
      self._StartServer()


  def _StartServer( self ):
    with self._server_state_mutex:
      _logger.info( 'Starting PHP Language Server..' )
      self._server_port = utils.GetUnusedLocalhostPort()

      command = [
        PHP_EXECUTABLE,
        PHP_LANGUAGE_SERVER,
        '--tcp={0}:{1}'.format( '127.0.0.1', self._server_port )
      ]

      _logger.debug( 'Starting PHP Language Server with the following command: '
                     '{0}'.format( ' '.join( command ) ) )

      LOGFILE_FORMAT = 'php_language_server_{port}_{std}_'

      self._server_stdout = utils.CreateLogfile(
          LOGFILE_FORMAT.format( port = self._server_port, std = 'stdout' ) )
      self._server_stderr = utils.CreateLogfile(
          LOGFILE_FORMAT.format( port = self._server_port, std = 'stderr' ) )

      with utils.OpenForStdHandle( self._server_stdout ) as stdout:
        with utils.OpenForStdHandle( self._server_stderr ) as stderr:
          self._server_handle = utils.SafePopen( command,
                                                 stdout = stdout,
                                                 stderr = stderr )

      if not self._ServerIsRunning():
        _logger.error( 'PHP Language Server failed to start' )
        return

      _logger.info( 'PHP Language Server started' )

      self._connection = (
        language_server_completer.TCPSingleStreamServer(
          self._server_port,
          self.GetDefaultNotificationHandler() )
      )

      self._connection.start()

      try:
        self._connection.AwaitServerConnection()
      except language_server_completer.LanguageServerConnectionTimeout:
        _logger.warn( 'PHP Language Server failed to start, or did not connect '
                      'successfully' )
        self._StopServer()
        return

    self.SendInitialise()


  def _StopServer( self ):
    with self._server_state_mutex:
      # Tell the connection to expect the server to disconnect.
      if self._connection:
        self._connection.stop()

      # Tell the server to exit using the shutdown request.
      if self._ServerIsRunning():
        _logger.info( 'Stopping PHP Language Server with PID {0}'.format(
                          self._server_handle.pid ) )

        self.ShutdownServer()

        try:
          utils.WaitUntilProcessIsTerminated( self._server_handle,
                                              timeout = 5 )

          if self._connection:
            self._connection.join()

          _logger.info( 'PHP Language Server stopped' )
        except Exception:
          _logger.exception( 'Error while stopping PHP Language Server' )

      self._CleanUp()


  def _CleanUp( self ):
    self._server_handle = None
    self._server_port = None
    self._connection = None
    self.ServerReset()
    if not self._server_keep_logfiles:
      if self._server_stdout:
        utils.RemoveIfExists( self._server_stdout )
        self._server_stdout = None
      if self._server_stderr:
        utils.RemoveIfExists( self._server_stderr )
        self._server_stderr = None


  def HandleServerCommand( self, request_data, command ):
    return None
