#!/usr/bin/env python

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from base64 import b64encode
from tempfile import NamedTemporaryFile
import argparse
import hashlib
import hmac
import json
import os
import os.path as p
import socket
import subprocess
import sys
import time

DIR_OF_THIS_SCRIPT = p.dirname( p.abspath( __file__ ) )
DIR_OF_THIRD_PARTY = p.join( DIR_OF_THIS_SCRIPT, 'third_party' )


def GetStandardLibraryIndexInSysPath():
  for index, path in enumerate( sys.path ):
    if p.isfile( p.join( path, 'os.py' ) ):
      return index
  raise RuntimeError( 'Could not find standard library path in Python path.' )


sys.path.insert( 0, p.join( DIR_OF_THIRD_PARTY, 'requests' ) )
sys.path.insert( GetStandardLibraryIndexInSysPath() + 1,
                 p.join( DIR_OF_THIRD_PARTY, 'python-future', 'src' ) )

# Not installing aliases from python-future; it's unreliable and slow.
from builtins import *  # noqa
from future.utils import PY2, native
import requests


if PY2:
  from urlparse import urlparse, urljoin
else:
  from urllib.parse import urlparse, urljoin

HEADERS = { 'content-type': 'application/json' }
HMAC_HEADER = 'x-ycm-hmac'
HMAC_SECRET_LENGTH = 16
YCMD_PATH = p.join( DIR_OF_THIS_SCRIPT, 'ycmd' )
LOGFILE_FORMAT = 'server_{port}_{std}_'
CONNECT_TIMEOUT = 0.001
READ_TIMEOUT = 30


# Returns a unicode type; either the new python-future str type or the real
# unicode type. The difference shouldn't matter.
def ToUnicode( value ):
  if not value:
    return str()
  if isinstance( value, str ):
    return value
  if isinstance( value, bytes ):
    # All incoming text should be utf8
    return str( value, 'utf8' )
  return str( value )


# Consistently returns the new bytes() type from python-future. Assumes incoming
# strings are either UTF-8 or unicode (which is converted to UTF-8).
def ToBytes( value ):
  if not value:
    return bytes()

  # This is tricky. On py2, the bytes type from builtins (from python-future) is
  # a subclass of str. So all of the following are true:
  #   isinstance(str(), bytes)
  #   isinstance(bytes(), str)
  # But they don't behave the same in one important aspect: iterating over a
  # bytes instance yields ints, while iterating over a (raw, py2) str yields
  # chars. We want consistent behavior so we force the use of bytes().
  if type( value ) == bytes:
    return value

  # This is meant to catch Python 2's native str type.
  if isinstance( value, bytes ):
    return bytes( value, encoding = 'utf8' )

  if isinstance( value, str ):
    # On py2, with `from builtins import *` imported, the following is true:
    #
    #   bytes(str(u'abc'), 'utf8') == b"b'abc'"
    #
    # Obviously this is a bug in python-future. So we work around it. Also filed
    # upstream at: https://github.com/PythonCharmers/python-future/issues/193
    # We can't just return value.encode( 'utf8' ) on both py2 & py3 because on
    # py2 that *sometimes* returns the built-in str type instead of the newbytes
    # type from python-future.
    if PY2:
      return bytes( value.encode( 'utf8' ), encoding = 'utf8' )
    else:
      return bytes( value, encoding = 'utf8' )

  # This is meant to catch `int` and similar non-string/bytes types.
  return ToBytes( str( value ) )


def CreateHmac( content, hmac_secret ):
  # Note that py2's str type passes this check (and that's ok)
  if not isinstance( content, bytes ):
    raise TypeError( 'content was not of bytes type; you have a bug!' )
  if not isinstance( hmac_secret, bytes ):
    raise TypeError( 'hmac_secret was not of bytes type; you have a bug!' )

  return bytes( hmac.new( hmac_secret,
                          msg = content,
                          digestmod = hashlib.sha256 ).digest() )


def CreateRequestHmac( method, path, body, hmac_secret ):
  # Note that py2's str type passes this check (and that's ok)
  if not isinstance( body, bytes ):
    raise TypeError( 'body was not of bytes type; you have a bug!' )
  if not isinstance( hmac_secret, bytes ):
    raise TypeError( 'hmac_secret was not of bytes type; you have a bug!' )
  if not isinstance( method, bytes ):
    raise TypeError( 'method was not of bytes type; you have a bug!' )
  if not isinstance( path, bytes ):
    raise TypeError( 'path was not of bytes type; you have a bug!' )

  method_hmac = CreateHmac( method, hmac_secret )
  path_hmac = CreateHmac( path, hmac_secret )
  body_hmac = CreateHmac( body, hmac_secret )

  joined_hmac_input = bytes().join( ( method_hmac, path_hmac, body_hmac ) )
  return CreateHmac( joined_hmac_input, hmac_secret )


def GetUnusedLocalhostPort():
  sock = socket.socket()
  # This tells the OS to give us any free port in the range [1024 - 65535]
  sock.bind( ( '', 0 ) )
  port = sock.getsockname()[ 1 ]
  sock.close()
  return port


class YcmdClient( object ):

  def __init__( self, logs ):
    self._logs = logs
    self._location = None
    self._port = None
    self._hmac_secret = None
    self._options_dict = {}
    self._popen_handle = None


  def Start( self ):
    self._hmac_secret = os.urandom( HMAC_SECRET_LENGTH )
    self._options_dict[ 'hmac_secret' ] = ToUnicode(
      b64encode( self._hmac_secret ) )

    # The temp options file is deleted by ycmd during startup
    with NamedTemporaryFile( mode = 'w+', delete = False ) as options_file:
      json.dump( self._options_dict, options_file )
      options_file.flush()
      self._port = GetUnusedLocalhostPort()
      self._location = 'http://127.0.0.1:' + str( self._port )

      ycmd_args = [
        sys.executable,
        YCMD_PATH,
        '--port={0}'.format( self._port ),
        '--options_file={0}'.format( options_file.name ),
        '--log=debug'
      ]

      redirection = subprocess.PIPE if self._logs else None

      tic = time.time()
      self._popen_handle = subprocess.Popen( ycmd_args,
                                             stdout = redirection,
                                             stderr = redirection )
      self._WaitUntilReady()
      return time.time() - tic


  def _IsReady( self ):
    response = self.GetRequest( 'ready' )
    response.raise_for_status()
    return response.json()


  def _WaitUntilReady( self, timeout = 10 ):
    expiration = time.time() + timeout
    while True:
      try:
        if time.time() > expiration:
          raise RuntimeError( 'Waited for ycmd to be ready for {0} seconds, '
                              'aborting.'.format( timeout ) )

        if self._IsReady():
          return
      except requests.exceptions.ConnectionError:
        pass
      finally:
        time.sleep( 0.001 )


  def GetRequest( self, handler, params = None ):
    return self._Request( 'GET', handler, params = params )


  def PostRequest( self, handler, data = None ):
    return self._Request( 'POST', handler, data = data )


  def _Request( self, method, handler, data = None, params = None ):
    request_uri = native( ToBytes( urljoin( self._location, handler ) ) )
    data = ToBytes( json.dumps( data ) if data else None )
    headers = self._ExtraHeaders( method,
                                  request_uri,
                                  data )
    response = requests.request( method,
                                 request_uri,
                                 headers = headers,
                                 data = data,
                                 params = params,
                                 timeout = ( CONNECT_TIMEOUT, READ_TIMEOUT ) )
    return response


  def _ExtraHeaders( self, method, request_uri, request_body = None ):
    if not request_body:
      request_body = bytes( b'' )
    headers = dict( HEADERS )
    headers[ HMAC_HEADER ] = b64encode(
        CreateRequestHmac( ToBytes( method ),
                           ToBytes( urlparse( request_uri ).path ),
                           request_body,
                           self._hmac_secret ) )
    return headers


def RemoveBytecode():
  for root, dirs, files in os.walk( YCMD_PATH ):
    for name in files:
      _, extension = p.splitext( name )
      if extension == '.pyc':
        os.remove( p.join( root, name ) )


def ParseArguments():
  parser = argparse.ArgumentParser()
  parser.add_argument( '--logs', action = 'store_false',
                       help = 'Display ycmd logs.' )
  parser.add_argument( '--runs', type = int, default = 10,
                       help = 'Number of runs.' )
  return parser.parse_args()


if __name__ == '__main__':
  args = ParseArguments()
  ycmd_client = YcmdClient( args.logs )

  # Warmup
  ycmd_client.Start()
  ycmd_client.PostRequest( 'shutdown' )

  startup_times = []
  for _ in range( args.runs ):
    RemoveBytecode()
    startup_times.append( ycmd_client.Start() )
    ycmd_client.PostRequest( 'shutdown' )
  average_startup_time_without_bytecode = int(
      sum( startup_times ) * 1000 / args.runs )

  startup_times = []
  for _ in range( args.runs ):
    startup_times.append( ycmd_client.Start() )
    ycmd_client.PostRequest( 'shutdown' )
  average_startup_time_with_bytecode = int(
      sum( startup_times ) * 1000 / args.runs )

  print( 'Average startup time on {0} runs:\n'
         '  without bytecode: {1}ms\n'
         '  with bytecode:    {2}ms'.format(
             args.runs,
             average_startup_time_without_bytecode,
             average_startup_time_with_bytecode ) )
