# Copyright (C) 2016-2017 ycmd contributors
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

from hamcrest import ( assert_that, contains, contains_inanyorder, has_entry,
                       has_entries, has_item, instance_of )

from ycmd.tests.python import IsolatedYcmd, PathToTestFile, SharedYcmd
from ycmd.tests.test_utils import BuildRequest, StopCompleterServer


@SharedYcmd
def DebugInfo_NoProject_test( app ):
  request_data = BuildRequest( filetype = 'python' )
  assert_that(
    app.post_json( '/debug_info', request_data ).json,
    has_entry( 'completer', has_entries( {
      'name': 'Python',
      'servers': contains( has_entries( {
        'name': 'JediHTTP',
        'is_running': instance_of( bool ),
        'executable': instance_of( str ),
        'pid': instance_of( int ),
        'address': instance_of( str ),
        'port': instance_of( int ),
        'logfiles': contains( instance_of( str ),
                              instance_of( str ) ),
        'extras': contains(
          has_entries( {
            'key': 'Python interpreter',
            'value': instance_of( str )
          } ),
          has_entries( {
            'key': 'Project root',
            'value': None
          } )
        )
      } ) ),
    } ) )
  )


@IsolatedYcmd()
def DebugInfo_MultipleProjects_test( app ):
  filepaths = [
    PathToTestFile( 'extra_conf_project', 'package', 'module', 'file.py' ),
    PathToTestFile( 'setup_project', 'package', 'module', 'file.py' )
  ]
  app.post_json(
      '/load_extra_conf_file',
      { 'filepath': PathToTestFile( 'extra_conf_project',
                                    '.ycm_extra_conf.py' ) } )

  try:
    for filepath in filepaths:
      event_notification_request = BuildRequest(
          filetype = 'python',
          filepath = filepath,
          event_name = 'FileReadyToParse' )
      app.post_json( '/event_notification', event_notification_request )

    debug_info = app.post_json( '/debug_info',
                                BuildRequest( filetype = 'python' ) ).json
  finally:
    for filepath in filepaths:
      StopCompleterServer( app, 'python', filepath )

  servers = debug_info[ 'completer' ][ 'servers' ]
  assert_that(
    servers,
    contains_inanyorder(
      has_entries( {
        'is_running': True,
        'extras': has_item(
          has_entries( {
            'key': 'Project root',
            'value': PathToTestFile( 'extra_conf_project' )
          } )
        )
      } ),
      has_entries( {
        'is_running': True,
        'extras': has_item(
          has_entries( {
            'key': 'Project root',
            'value': PathToTestFile( 'setup_project' )
          } )
        )
      } )
    )
  )
