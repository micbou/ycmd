# Copyright (C) 2011-2012 Stephen Sugden <me@stephensugden.com>
#                         Google Inc.
#                         Stanislav Golovanov <stgolovanov@gmail.com>
#               2017      ycmd contributors
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

from ycmd.utils import ToBytes, ToUnicode, ProcessIsRunning, urljoin
from ycmd.completers.completer import Completer
from ycmd.completers.python.settings import PythonSettings
from ycmd import responses, utils, hmac_utils
from tempfile import NamedTemporaryFile

from base64 import b64encode
from future.utils import itervalues, native
import json
import logging
import requests
import threading
import sys
import os


HMAC_SECRET_LENGTH = 16
JEDIHTTP_HMAC_HEADER = 'x-jedihttp-hmac'
BINARY_NOT_FOUND_MESSAGE = ( 'The specified python interpreter {0} ' +
                             'was not found. Did you specify it correctly?' )
LOGFILE_FORMAT = 'jedihttp_{port}_{std}_'
PATH_TO_JEDIHTTP = os.path.abspath(
  os.path.join( os.path.dirname( __file__ ), '..', '..', '..',
                'third_party', 'JediHTTP', 'jedihttp.py' ) )


class JediCompleter( Completer ):
  """
  A Completer that uses the Jedi engine HTTP wrapper JediHTTP.
  https://jedi.readthedocs.org/en/latest/
  https://github.com/vheon/JediHTTP
  """

  def __init__( self, user_options ):
    super( JediCompleter, self ).__init__( user_options )
    self._project_lock = threading.Lock()
    self._completer_per_project_root = dict()
    self._logger = logging.getLogger( __name__ )
    self._python_settings = PythonSettings()


  def SupportedFiletypes( self ):
    """ Just python """
    return [ 'python' ]


  def Shutdown( self ):
    for completer in itervalues( self._completer_per_project_root ):
      completer.StopServer()


  def _ProjectSubcommand( self, request_data, method,
                          no_request_data = False, **kwargs ):
    completer = self._GetProjectCompleter( request_data )
    if not no_request_data:
      kwargs[ 'request_data' ] = request_data
    return getattr( completer, method )( **kwargs )


  def GetSubcommandsMap( self ):
    return {
      'GoToDefinition' : ( lambda self, request_data, args:
         self._GetProjectCompleter( request_data ).GoToDefinition(
             request_data ) ),
      'GoToDeclaration': ( lambda self, request_data, args:
         self._GetProjectCompleter( request_data ).GoToDeclaration(
             request_data ) ),
      'GoTo'           : ( lambda self, request_data, args:
         self._GetProjectCompleter( request_data ).GoTo( request_data ) ),
      'GetDoc'         : ( lambda self, request_data, args:
         self._GetProjectCompleter( request_data ).GetDoc( request_data ) ),
      'GoToReferences' : ( lambda self, request_data, args:
         self._GetProjectCompleter( request_data ).GoToReferences(
             request_data ) ),
      'StopServer'     : ( lambda self, request_data, args:
         self._GetProjectCompleter( request_data ).StopServer() ),
      'RestartServer'  : ( lambda self, request_data, args:
         self._GetProjectCompleter( request_data ).RestartServer( *args ) ),
    }


  def _GetProjectCompleter( self, request_data ):
    """Get the project completer or create a new one if it does not already
    exist. Use a lock to avoid creating the same project completer multiple
    times."""
    filepath = request_data[ 'filepath' ]
    client_data = request_data.get( 'extra_conf_data' )
    project_root = self._python_settings.GetProjectRootForFile( filepath )
    settings = self._python_settings.SettingsForFile(
        filepath,
        client_data = client_data )

    with self._project_lock:
      try:
        return self._completer_per_project_root[ project_root ]
      except KeyError:
        completer = JediProjectCompleter( project_root,
                                          settings,
                                          self.user_options )
        self._completer_per_project_root[ project_root ] = completer
        return completer


  def _GetExtraData( self, completion ):
    location = {}
    if completion[ 'module_path' ]:
      location[ 'filepath' ] = completion[ 'module_path' ]
    if completion[ 'line' ]:
      location[ 'line_num' ] = completion[ 'line' ]
    if completion[ 'column' ]:
      location[ 'column_num' ] = completion[ 'column' ] + 1

    if location:
      extra_data = {}
      extra_data[ 'location' ] = location
      return extra_data
    return None


  def ComputeCandidatesInner( self, request_data ):
    completer = self._GetProjectCompleter( request_data )
    return [ responses.BuildCompletionData(
                completion[ 'name' ],
                completion[ 'description' ],
                completion[ 'docstring' ],
                extra_data = self._GetExtraData( completion ) )
             for completion in completer._JediCompletions( request_data ) ]


  def OnFileReadyToParse( self, request_data ):
    self._GetProjectCompleter( request_data )


  def ServerIsHealthy( self ):
    """Check if all JediHTTP servers are healthy."""
    completers = itervalues( self._completer_per_project_root )
    return all( completer.ServerIsHealthy() for completer in completers
                if completer.ServerIsRunning() )


  def DebugInfo( self, request_data ):
    with self._project_lock:
      return responses.BuildDebugInfoResponse(
        name = 'Python',
        servers = [ completer.DebugInfo() for completer in
                    itervalues( self._completer_per_project_root ) ] )


class JediProjectCompleter( object ):
  def __init__( self, project_root, settings, user_options ):
    self._server_lock = threading.RLock()
    self._jedihttp_port = None
    self._jedihttp_phandle = None
    self._logger = logging.getLogger( __name__ )
    self._logfile_stdout = None
    self._logfile_stderr = None
    self._hmac_secret = ''
    self._project_root = project_root
    self._settings = settings
    self._python_binary_path = user_options[ 'python_binary_path' ]
    self._keep_logfiles = user_options[ 'server_keep_logfiles' ]
    self._interpreter_path = self._GetPythonInterpreter()

    self.StartServer()


  def _GetPythonInterpreter( self, interpreter_path = None ):
    def _FindPythonInterpreter( interpreter_path ):
      resolved_path = utils.FindExecutable( os.path.expanduser(
        os.path.expandvars( interpreter_path ) ) )
      if resolved_path:
        return os.path.normpath( resolved_path )
      message = BINARY_NOT_FOUND_MESSAGE.format( interpreter_path )
      self._logger.error( message )
      raise RuntimeError( message )

    if interpreter_path:
      return _FindPythonInterpreter( interpreter_path )

    interpreter_path = self._settings.get( 'interpreter_path' )
    if interpreter_path:
      return _FindPythonInterpreter( interpreter_path )

    interpreter_path = self._python_binary_path
    if interpreter_path:
      return _FindPythonInterpreter( interpreter_path )

    return sys.executable


  def _GenerateHmacSecret( self ):
    return os.urandom( HMAC_SECRET_LENGTH )


  def _GetLoggingLevel( self ):
    # Tests are run with the NOTSET logging level but JediHTTP only accepts the
    # predefined levels above (DEBUG, INFO, WARNING, etc.).
    log_level = max( self._logger.getEffectiveLevel(), logging.DEBUG )
    return logging.getLevelName( log_level ).lower()


  def StartServer( self ):
    with self._server_lock:
      self._logger.info( 'Starting JediHTTP server' )
      self._jedihttp_port = utils.GetUnusedLocalhostPort()
      self._jedihttp_host = ToBytes( 'http://127.0.0.1:{0}'.format(
        self._jedihttp_port ) )
      self._logger.info( 'using port {0}'.format( self._jedihttp_port ) )
      self._hmac_secret = self._GenerateHmacSecret()

      # JediHTTP will delete the secret_file after it's done reading it
      with NamedTemporaryFile( delete = False, mode = 'w+' ) as hmac_file:
        json.dump( { 'hmac_secret': ToUnicode(
                        b64encode( self._hmac_secret ) ) },
                   hmac_file )
        command = [ self._interpreter_path,
                    PATH_TO_JEDIHTTP,
                    '--port', str( self._jedihttp_port ),
                    '--log', self._GetLoggingLevel(),
                    '--hmac-file-secret', hmac_file.name ]

      self._logfile_stdout = utils.CreateLogfile(
          LOGFILE_FORMAT.format( port = self._jedihttp_port, std = 'stdout' ) )
      self._logfile_stderr = utils.CreateLogfile(
          LOGFILE_FORMAT.format( port = self._jedihttp_port, std = 'stderr' ) )

      with utils.OpenForStdHandle( self._logfile_stdout ) as logout:
        with utils.OpenForStdHandle( self._logfile_stderr ) as logerr:
          self._jedihttp_phandle = utils.SafePopen( command,
                                                    stdout = logout,
                                                    stderr = logerr )


  def StopServer( self ):
    with self._server_lock:
      if self.ServerIsRunning():
        self._logger.info( 'Stopping JediHTTP server with PID {0}'.format(
                               self._jedihttp_phandle.pid ) )
        self._jedihttp_phandle.terminate()
        try:
          utils.WaitUntilProcessIsTerminated( self._jedihttp_phandle,
                                              timeout = 5 )
          self._logger.info( 'JediHTTP server stopped' )
        except RuntimeError:
          self._logger.exception( 'Error while stopping JediHTTP server' )

      self._CleanUp()


  def RestartServer( self, interpreter_path = None ):
    """ Restart the JediHTTP Server. """
    with self._server_lock:
      self.StopServer()
      self._interpreter_path = self._GetPythonInterpreter( interpreter_path )
      self.StartServer()


  def _CleanUp( self ):
    self._jedihttp_phandle = None
    self._jedihttp_port = None
    if not self._keep_logfiles:
      if self._logfile_stdout:
        utils.RemoveIfExists( self._logfile_stdout )
        self._logfile_stdout = None
      if self._logfile_stderr:
        utils.RemoveIfExists( self._logfile_stderr )
        self._logfile_stderr = None


  def ServerIsHealthy( self ):
    """
    Check if JediHTTP is alive AND ready to serve requests.
    """
    if not self.ServerIsRunning():
      self._logger.debug( 'JediHTTP not running.' )
      return False
    try:
      return bool( self._GetResponse( '/ready' ) )
    except requests.exceptions.ConnectionError as e:
      self._logger.exception( e )
      return False


  def ServerIsRunning( self ):
    """
    Check if JediHTTP is alive. That doesn't necessarily mean it's ready to
    serve requests; that's checked by ServerIsHealthy.
    """
    with self._server_lock:
      return ( bool( self._jedihttp_port ) and
               ProcessIsRunning( self._jedihttp_phandle ) )


  def _GetResponse( self, handler, parameters = {} ):
    """POST JSON data to JediHTTP server and return JSON response."""
    handler = ToBytes( handler )
    url = urljoin( self._jedihttp_host, handler )
    body = ToBytes( json.dumps( parameters ) ) if parameters else bytes()
    extra_headers = self._ExtraHeaders( handler, body )

    self._logger.debug( 'Making JediHTTP request: %s %s %s %s', 'POST', url,
                        extra_headers, body )

    response = requests.request( native( bytes( b'POST' ) ),
                                 native( url ),
                                 data = body,
                                 headers = extra_headers )

    response.raise_for_status()
    return response.json()


  def _ExtraHeaders( self, handler, body ):
    hmac = hmac_utils.CreateRequestHmac( bytes( b'POST' ),
                                         handler,
                                         body,
                                         self._hmac_secret )

    extra_headers = { 'content-type': 'application/json' }
    extra_headers[ JEDIHTTP_HMAC_HEADER ] = b64encode( hmac )
    return extra_headers


  def _TranslateRequestForJediHTTP( self, request_data ):
    if not request_data:
      return {}

    path = request_data[ 'filepath' ]
    source = request_data[ 'file_data' ][ path ][ 'contents' ]
    line = request_data[ 'line_num' ]
    # JediHTTP (as Jedi itself) expects columns to start at 0, not 1, and for
    # them to be unicode codepoint offsets.
    col = request_data[ 'start_codepoint' ] - 1

    return {
      'source': source,
      'line': line,
      'col': col,
      'source_path': path
    }


  def _JediCompletions( self, request_data ):
    request = self._TranslateRequestForJediHTTP( request_data )
    return self._GetResponse( '/completions', request )[ 'completions' ]


  def GoToDefinition( self, request_data ):
    definitions = self._GetDefinitionsList( '/gotodefinition',
                                            request_data )
    if not definitions:
      raise RuntimeError( 'Can\'t jump to definition.' )
    return self._BuildGoToResponse( definitions )


  def GoToDeclaration( self, request_data ):
    definitions = self._GetDefinitionsList( '/gotoassignment',
                                            request_data )
    if not definitions:
      raise RuntimeError( 'Can\'t jump to declaration.' )
    return self._BuildGoToResponse( definitions )


  def GoTo( self, request_data ):
    try:
      return self.GoToDefinition( request_data )
    except Exception as e:
      self._logger.exception( e )
      pass

    try:
      return self.GoToDeclaration( request_data )
    except Exception as e:
      self._logger.exception( e )
      raise RuntimeError( 'Can\'t jump to definition or declaration.' )


  def GetDoc( self, request_data ):
    try:
      definitions = self._GetDefinitionsList( '/gotodefinition',
                                              request_data )
      return self._BuildDetailedInfoResponse( definitions )
    except Exception as e:
      self._logger.exception( e )
      raise RuntimeError( 'Can\'t find a definition.' )


  def GoToReferences( self, request_data ):
    definitions = self._GetDefinitionsList( '/usages', request_data )
    if not definitions:
      raise RuntimeError( 'Can\'t find references.' )
    return self._BuildGoToResponse( definitions )


  def _GetDefinitionsList( self, handler, request_data ):
    try:
      request = self._TranslateRequestForJediHTTP( request_data )
      response = self._GetResponse( handler, request )
      return response[ 'definitions' ]
    except Exception as e:
      self._logger.exception( e )
      raise RuntimeError( 'Cannot follow nothing. '
                          'Put your cursor on a valid name.' )


  def _BuildGoToResponse( self, definition_list ):
    if len( definition_list ) == 1:
      definition = definition_list[ 0 ]
      if definition[ 'in_builtin_module' ]:
        if definition[ 'is_keyword' ]:
          raise RuntimeError( 'Cannot get the definition of Python keywords.' )
        else:
          raise RuntimeError( 'Builtin modules cannot be displayed.' )
      else:
        return responses.BuildGoToResponse( definition[ 'module_path' ],
                                            definition[ 'line' ],
                                            definition[ 'column' ] + 1 )
    else:
      # multiple definitions
      defs = []
      for definition in definition_list:
        if definition[ 'in_builtin_module' ]:
          defs.append( responses.BuildDescriptionOnlyGoToResponse(
                       'Builtin ' + definition[ 'description' ] ) )
        else:
          defs.append(
            responses.BuildGoToResponse( definition[ 'module_path' ],
                                         definition[ 'line' ],
                                         definition[ 'column' ] + 1,
                                         definition[ 'description' ] ) )
      return defs


  def _BuildDetailedInfoResponse( self, definition_list ):
    docs = [ definition[ 'docstring' ] for definition in definition_list ]
    return responses.BuildDetailedInfoResponse( '\n---\n'.join( docs ) )


  def DebugInfo( self ):
    with self._server_lock:
      python_interpreter_item = responses.DebugInfoItem(
        key = 'Python interpreter',
        value = self._interpreter_path )

      project_root_item = responses.DebugInfoItem(
        key = 'Project root',
        value = self._project_root )

      return responses.DebugInfoServer(
        name = 'JediHTTP',
        handle = self._jedihttp_phandle,
        executable = PATH_TO_JEDIHTTP,
        address = '127.0.0.1',
        port = self._jedihttp_port,
        logfiles = [ self._logfile_stdout, self._logfile_stderr ],
        extras = [ python_interpreter_item, project_root_item ] )
