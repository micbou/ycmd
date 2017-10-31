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

from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
# Not installing aliases from python-future; it's unreliable and slow.
from builtins import *  # noqa

from hamcrest import ( assert_that,
                       contains,
                       contains_inanyorder,
                       equal_to,
                       has_entries,
                       has_entry )
from mock import patch
from pprint import pformat
import requests
import time

from ycmd import handlers
from ycmd.tests.rust import PathToTestFile, SharedYcmd
from ycmd.tests.test_utils import ( BuildRequest,
                                    ChunkMatcher,
                                    ErrorMatcher,
                                    LocationMatcher )
from ycmd.utils import ReadFile


RESPONSE_TIMEOUT = 5


def RunTest( app, test, contents = None ):
  if not contents:
    contents = ReadFile( test[ 'request' ][ 'filepath' ] )

  def CombineRequest( request, data ):
    kw = request
    request.update( data )
    return BuildRequest( **kw )

  # Because we aren't testing this command, we *always* ignore errors. This
  # is mainly because we (may) want to test scenarios where the completer
  # throws an exception and the easiest way to do that is to throw from
  # within the FlagsForFile function.
  app.post_json( '/event_notification',
                 CombineRequest( test[ 'request' ], {
                                 'event_name': 'FileReadyToParse',
                                 'contents': contents,
                                 'filetype': 'rust',
                                 } ),
                 expect_errors = True )

  # We keep trying to run the command until RLS finishes to parse the file or
  # the timeout is reached.
  expiration = time.time() + RESPONSE_TIMEOUT

  while True:
    # We also ignore errors here, but then we check the response code
    # ourself. This is to allow testing of requests returning errors.
    response = app.post_json(
      '/run_completer_command',
      CombineRequest( test[ 'request' ], {
        'completer_target': 'filetype_default',
        'contents': contents,
        'filetype': 'rust',
        'command_arguments': ( [ test[ 'request' ][ 'command' ] ]
                               + test[ 'request' ].get( 'arguments', [] ) )
      } ),
      expect_errors = True
    )

    try:
      assert_that( response.status_code,
                   equal_to( test[ 'expect' ][ 'response' ] ) )
      assert_that( response.json, test[ 'expect' ][ 'data' ] )
      return
    except AssertionError:
      if time.time() > expiration:
        print( 'completer response: {0}'.format( pformat( response.json ) ) )
        raise
      time.sleep( 0.5 )


@SharedYcmd
def Subcommands_DefinedSubcommands_test( app ):
  subcommands_data = BuildRequest( completer_target = 'rust' )

  assert_that( app.post_json( '/defined_subcommands', subcommands_data ).json,
               contains_inanyorder( 'Format',
                                    'GetDoc',
                                    'GetType',
                                    'GoTo',
                                    'GoToDeclaration',
                                    'GoToDefinition',
                                    'GoToReferences',
                                    'RefactorRename',
                                    'RestartServer' ) )


def Subcommands_ServerNotReady_test():
  filepath = PathToTestFile( 'common', 'src', 'main.rs' )

  completer = handlers._server_state.GetFiletypeCompleter( [ 'rust' ] )

  @SharedYcmd
  @patch.object( completer, 'ServerIsReady', return_value = False )
  def Test( app, cmd, arguments, *args ):
    RunTest( app, {
      'description': 'Subcommand ' + cmd + ' handles server not ready',
      'request': {
        'command': cmd,
        'line_num': 1,
        'column_num': 1,
        'filepath': filepath,
        'arguments': arguments,
      },
      'expect': {
        'response': requests.codes.internal_server_error,
        'data': ErrorMatcher( RuntimeError,
                              'Server is initializing. Please wait.' ),
      }
    } )

  yield Test, 'Format', []
  yield Test, 'GetType', []
  yield Test, 'GetDoc', []
  yield Test, 'GoTo', []
  yield Test, 'GoToDeclaration', []
  yield Test, 'GoToDefinition', []
  yield Test, 'GoToReferences', []
  yield Test, 'RefactorRename', [ 'test' ]


@SharedYcmd
def Subcommands_Format_WholeFile_test( app ):
  filepath = PathToTestFile( 'common', 'src', 'main.rs' )

  RunTest( app, {
    'description': 'Formatting is applied on the whole file',
    'request': {
      'command': 'Format',
      'filepath': filepath,
      'options': {
        'tab_size': 2,
        'insert_spaces': True
      }
    },
    'expect': {
      'response': requests.codes.ok,
      'data': has_entries( {
        'fixits': contains( has_entries( {
          'chunks': contains(
            ChunkMatcher( 'mod test;\n'
                          '\n'
                          'use test::*;\n'
                          '\n'
                          'fn unformatted_function(param: bool) -> bool {\n'
                          '  return param;\n'
                          '}\n'
                          '\n'
                          'fn main() {\n'
                          '  create_universe();\n'
                          '  build_\n'
                          '}\n',
                          LocationMatcher( filepath,  1, 1 ),
                          LocationMatcher( filepath, 13, 1 ) ),
          )
        } ) )
      } )
    }
  } )


@SharedYcmd
def Subcommands_Format_Range_test( app ):
  filepath = PathToTestFile( 'common', 'src', 'main.rs' )

  RunTest( app, {
    'description': 'Formatting is applied on some part of the file',
    'request': {
      'command': 'Format',
      'filepath': filepath,
      'range': {
        'start': {
          'line_num': 5,
          'column_num': 1,
        },
        'end': {
          'line_num': 6,
          'column_num': 17
        }
      },
      'options': {
        'tab_size': 4,
        'insert_spaces': False
      }
    },
    'expect': {
      'response': requests.codes.ok,
      'data': has_entries( {
        'fixits': contains( has_entries( {
          'chunks': contains(
            ChunkMatcher( 'mod test;\n'
                          '\n'
                          'use test::*;\n'
                          '\n'
                          'fn unformatted_function(param: bool) -> bool {\n'
                          '\treturn param;\n'
                          '}\n'
                          '\n'
                          'fn main()\n'
                          '{\n'
                          '    create_universe( );\n'
                          '    build_\n'
                          '}\n',
                          LocationMatcher( filepath,  1, 1 ),
                          LocationMatcher( filepath, 13, 1 ) ),
          )
        } ) )
      } )
    }
  } )


@SharedYcmd
def Subcommands_GetDoc_NoDocumentation_test( app ):
  RunTest( app, {
    'description': 'GetDoc on a function with no documentation '
                   'raises an error',
    'request': {
      'command': 'GetDoc',
      'line_num': 5,
      'column_num': 11,
      'filepath': PathToTestFile( 'common', 'src', 'test.rs' ),
    },
    'expect': {
      'response': requests.codes.internal_server_error,
      'data': ErrorMatcher( RuntimeError,
                            'No documentation available for current context.' )
    }
  } )


@SharedYcmd
def Subcommands_GetDoc_Function_test( app ):
  RunTest( app, {
    'description': 'GetDoc on a function returns its documentation',
    'request': {
      'command': 'GetDoc',
      'line_num': 3,
      'column_num': 8,
      'filepath': PathToTestFile( 'common', 'src', 'test.rs' ),
    },
    'expect': {
      'response': requests.codes.ok,
      'data': has_entry( 'detailed_info',
                         'Be careful when using that function' ),
    }
  } )


@SharedYcmd
def Subcommands_GetType_UnknownType_test( app ):
  RunTest( app, {
    'description': 'GetType on a unknown type raises an error',
    'request': {
      'command': 'GetType',
      'line_num': 3,
      'column_num': 4,
      'filepath': PathToTestFile( 'common', 'src', 'test.rs' ),
    },
    'expect': {
      'response': requests.codes.internal_server_error,
      'data': ErrorMatcher( RuntimeError, 'Unknown type.' )
    }
  } )


@SharedYcmd
def Subcommands_GetType_Function_test( app ):
  RunTest( app, {
    'description': 'GetType on a function returns its type',
    'request': {
      'command': 'GetType',
      'line_num': 3,
      'column_num': 22,
      'filepath': PathToTestFile( 'common', 'src', 'test.rs' ),
    },
    'expect': {
      'response': requests.codes.ok,
      'data': has_entry( 'message', 'pub fn create_universe()' ),
    }
  } )


@SharedYcmd
def RunGoToTest( app, description, filepath, line, col, cmd, goto_response ):
  RunTest( app, {
    'description': description,
    'request': {
      'command': cmd,
      'line_num': line,
      'column_num': col,
      'filepath': filepath
    },
    'expect': {
      'response': requests.codes.ok,
      'data': goto_response,
    }
  } )


def Subcommands_GoTo_test():
  goto_response = has_entries( {
    'line_num': 3,
    'column_num': 8,
    'filepath': PathToTestFile( 'common', 'src', 'test.rs' ),
  } )

  for command in [ 'GoTo', 'GoToDefinition', 'GoToDeclaration' ]:
    yield ( RunGoToTest, 'GoTo works for function',
            PathToTestFile( 'common', 'src', 'main.rs' ),
            10, 12, command, goto_response )


@SharedYcmd
def Subcommands_GoToReferences_test( app ):
  main_filepath = PathToTestFile( 'common', 'src', 'main.rs' )
  test_filepath = PathToTestFile( 'common', 'src', 'test.rs' )

  RunTest( app, {
    'description': 'GoToReferences on a function returns all its references',
    'request': {
      'command': 'GoToReferences',
      'line_num': 10,
      'column_num': 10,
      'filepath': main_filepath
    },
    'expect': {
      'response': requests.codes.ok,
      'data': contains_inanyorder(
        has_entries( {
          'filepath': main_filepath,
          'line_num': 10,
          'column_num': 5,
          'description': '    create_universe( );'
        } ),
        has_entries( {
          'filepath': test_filepath,
          'line_num': 3,
          'column_num': 8,
          'description': 'pub fn create_universe() {}'
        } )
      )
    }
  } )


@SharedYcmd
def Subcommands_RefactorRename_Works_test( app ):
  main_filepath = PathToTestFile( 'common', 'src', 'main.rs' )
  test_filepath = PathToTestFile( 'common', 'src', 'test.rs' )

  RunTest( app, {
    'description': 'RefactorRename on a function renames all its occurences',
    'request': {
      'command': 'RefactorRename',
      'arguments': [ 'update_universe' ],
      'line_num': 10,
      'column_num': 16,
      'filepath': main_filepath
    },
    'expect': {
      'response': requests.codes.ok,
      'data': has_entries( {
        'fixits': contains( has_entries( {
          'text': '',
          'chunks': contains(
            ChunkMatcher( 'update_universe',
                          LocationMatcher( main_filepath, 10,  5 ),
                          LocationMatcher( main_filepath, 10, 20 ) ),
            ChunkMatcher( 'update_universe',
                          LocationMatcher( test_filepath,  3,  8 ),
                          LocationMatcher( test_filepath,  3, 23 ) ),
          )
        } ) )
      } )
    }
  } )


@SharedYcmd
def Subcommands_RefactorRename_Invalid_test( app ):
  RunTest( app, {
    'description': 'RefactorRename raises an error when cursor is invalid',
    'request': {
      'command': 'RefactorRename',
      'arguments': [ 'update_universe' ],
      'line_num': 15,
      'column_num': 7,
      'filepath': PathToTestFile( 'common', 'src', 'main.rs' )
    },
    'expect': {
      'response': requests.codes.internal_server_error,
      'data': ErrorMatcher( RuntimeError, 'Cannot rename under cursor.' )
    }
  } )
