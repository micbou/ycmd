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

from __future__ import print_function
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import division
# Not installing aliases from python-future; it's unreliable and slow.
from builtins import *  # noqa

from future.utils import iterkeys
from hamcrest import assert_that, contains, contains_inanyorder, has_entries
from pprint import pformat
import json

from ycmd.tests.rust import PathToTestFile, SharedYcmd
from ycmd.tests.test_utils import ( LocationMatcher,
                                    PollForMessages,
                                    PollForMessagesTimeoutException,
                                    RangeMatcher,
                                    WaitForDiagnosticsToBeReady )
from ycmd.utils import ReadFile


MAIN_FILEPATH = PathToTestFile( 'common', 'src', 'main.rs' )
DIAG_MATCHERS_PER_FILE = {
  MAIN_FILEPATH: contains_inanyorder(
    has_entries( {
      'kind': 'ERROR',
      'text': 'cannot find value `build_` in this scope\n\n'
              'not found in this scope',
      'location': LocationMatcher( MAIN_FILEPATH, 11, 5 ),
      'location_extent': RangeMatcher( MAIN_FILEPATH, ( 11, 5 ), ( 11, 11 ) ),
      'ranges': contains( RangeMatcher( MAIN_FILEPATH,
                                        ( 11, 5 ),
                                        ( 11, 11 ) ) ),
      'fixit_available': False
    } )
  )
}


@SharedYcmd
def Diagnostics_FileReadyToParse_test( app ):
  filepath = PathToTestFile( 'common', 'src', 'main.rs' )
  contents = ReadFile( filepath )

  # It can take a while for the diagnostics to be ready.
  results = WaitForDiagnosticsToBeReady( app, filepath, contents, 'rust' )
  print( 'completer response: {0}'.format( pformat( results ) ) )

  assert_that( results, DIAG_MATCHERS_PER_FILE[ filepath ] )


@SharedYcmd
def Diagnostics_Poll_test( app ):
  filepath = PathToTestFile( 'common', 'src', 'main.rs' )
  contents = ReadFile( filepath )

  # Poll until we receive _all_ the diags asynchronously.
  to_see = sorted( iterkeys( DIAG_MATCHERS_PER_FILE ) )
  seen = dict()

  try:
    for message in PollForMessages( app,
                                    { 'filepath': filepath,
                                      'contents': contents,
                                      'filetype': 'rust' } ):
      print( 'Message {0}'.format( pformat( message ) ) )
      if 'diagnostics' in message:
        seen[ message[ 'filepath' ] ] = True
        if message[ 'filepath' ] not in DIAG_MATCHERS_PER_FILE:
          raise AssertionError(
            'Received diagnostics for unexpected file {0}. '
            'Only expected {1}'.format( message[ 'filepath' ], to_see ) )
        assert_that( message, has_entries( {
          'diagnostics': DIAG_MATCHERS_PER_FILE[ message[ 'filepath' ] ],
          'filepath': message[ 'filepath' ]
        } ) )

      if sorted( iterkeys( seen ) ) == to_see:
        break

      # Eventually PollForMessages will throw a timeout exception and we'll fail
      # if we don't see all of the expected diags.
  except PollForMessagesTimeoutException as e:
    raise AssertionError(
      str( e ) +
      'Timed out waiting for full set of diagnostics. '
      'Expected to see diags for {0}, but only saw {1}.'.format(
        json.dumps( to_see, indent=2 ),
        json.dumps( sorted( iterkeys( seen ) ), indent=2 ) ) )
