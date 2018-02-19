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
import requests

from mock import patch
from hamcrest import assert_that, contains, has_entry, starts_with
from ycmd.tests.rust import ( PathToTestFile,
                              IsolatedYcmd,
                              StartRustCompleterServerInDirectory )
from ycmd.tests.test_utils import ( BuildRequest,
                                    ErrorMatcher,
                                    PollForMessages,
                                    StartCompleterServer,
                                    WaitUntilCompleterServerReady )
from ycmd import utils
from ycmd.utils import FindExecutable
from ycmd.completers.rust.rust_completer import _GetCommandOutput, TOOLCHAIN


def AssertRustCompleterServerIsRunning( app, is_running ):
  request_data = BuildRequest( filetype = 'rust' )
  assert_that( app.post_json( '/debug_info', request_data ).json,
               has_entry(
                 'completer',
                 has_entry( 'servers', contains(
                   has_entry( 'is_running', is_running )
                 ) )
               ) )


def CannotFindRustup( command ):
  if command.endswith( 'rustup' ):
   return None
  return FindExecutable( command )


@patch( 'ycmd.utils.FindExecutable', side_effect = CannotFindRustup )
@IsolatedYcmd
def ServerManagement_StartServer_RustupUnavailable_test( app, *args ):
  filepath = PathToTestFile( 'common', 'src', 'main.rs' )
  contents = utils.ReadFile( filepath )

  StartCompleterServer( app, 'rust', filepath )

  for message in PollForMessages( app, { 'filepath': filepath,
                                         'contents': contents,
                                         'filetype': 'rust' }, timeout = 5 ):
    try:
      assert_that( message, has_entry(
        'message', "Could not find rustup. Install it by following "
                   "the instructions on https://www.rustup.rs/ "
                   "then run the 'RestartServer' subcommand." ) )
      break
    except AssertionError:
      pass

  AssertRustCompleterServerIsRunning( app, False )


class ToolchainNotListed( object ):
  first_call = True

  def __call__( self, command ):
    if 'list' in command and self.first_call:
      self.first_call = False
      return ( 'first-dummy-toolchain\n'
               'second-dummy-toolchain' )
    return _GetCommandOutput( command )


@patch( 'ycmd.completers.rust.rust_completer._GetCommandOutput',
        side_effect = ToolchainNotListed() )
@IsolatedYcmd
def ServerManagement_StartServer_InstallToolchain_Success_test( app, *args ):
  filepath = PathToTestFile( 'common', 'src', 'main.rs' )
  contents = utils.ReadFile( filepath )

  StartCompleterServer( app, 'rust', filepath )
  WaitUntilCompleterServerReady( app, 'rust' )

  request_data = BuildRequest( filetype = 'rust' )
  debug_info = app.post_json( '/debug_info', request_data ).json
  completer = debug_info[ 'completer' ]
  toolchain = completer[ 'items' ][ 2 ][ 'value' ]

  for message in PollForMessages( app, { 'filepath': filepath,
                                         'contents': contents,
                                         'filetype': 'rust' }, timeout = 5 ):
    try:
      assert_that( message, has_entry(
        'message', "info: syncing channel updates for '{toolchain}'".format(
          toolchain = toolchain ) ) )
      break
    except AssertionError:
      pass

  AssertRustCompleterServerIsRunning( app, True )


@patch( 'ycmd.completers.rust.rust_completer._GetCommandOutput',
        side_effect = ToolchainNotListed() )
@patch( 'ycmd.completers.rust.rust_completer.RustCompleter.'
        '_RunCommandAndNotify',
        side_effect = lambda command: command[ 1 ] != 'toolchain' )
@IsolatedYcmd
def ServerManagement_StartServer_InstallToolchain_Failure_test( app, *args ):
  filepath = PathToTestFile( 'common', 'src', 'main.rs' )
  contents = utils.ReadFile( filepath )

  StartCompleterServer( app, 'rust', filepath )

  for message in PollForMessages( app, { 'filepath': filepath,
                                         'contents': contents,
                                         'filetype': 'rust' }, timeout = 5 ):
    try:
      assert_that( message, has_entry(
        'message', 'Failed to install toolchain {toolchain}.'.format(
          toolchain = TOOLCHAIN ) ) )
      break
    except AssertionError:
      pass

  AssertRustCompleterServerIsRunning( app, False )


def UnexpectedOutputWhenListingToolchain( command ):
  if 'list' in command:
    return '  unexpected\n'
  return _GetCommandOutput( command )


@patch( 'ycmd.completers.rust.rust_completer._GetCommandOutput',
        side_effect = UnexpectedOutputWhenListingToolchain )
@IsolatedYcmd
def ServerManagement_StartServer_GetToolchain_Failure_test( app, *args ):
  filepath = PathToTestFile( 'common', 'src', 'main.rs' )
  contents = utils.ReadFile( filepath )

  StartCompleterServer( app, 'rust', filepath )

  for message in PollForMessages( app, { 'filepath': filepath,
                                         'contents': contents,
                                         'filetype': 'rust' }, timeout = 5 ):
    try:
      assert_that( message, has_entry(
        'message', 'Failed to get toolchain {toolchain}.'.format(
          toolchain = TOOLCHAIN ) ) )
      break
    except AssertionError:
      pass

  AssertRustCompleterServerIsRunning( app, False )


class CannotFindRlsFirstTime( object ):
  first_call = True

  def __call__( self, executable ):
    print( executable )
    if executable.endswith( 'rls' ) and self.first_call:
      self.first_call = False
      return None
    return FindExecutable( executable )


@patch( 'ycmd.utils.FindExecutable', side_effect = CannotFindRlsFirstTime() )
@IsolatedYcmd
def ServerManagement_StartServer_InstallRls_Success_test( app, *args ):
  filepath = PathToTestFile( 'common', 'src', 'main.rs' )
  contents = utils.ReadFile( filepath )

  StartCompleterServer( app, 'rust', filepath )
  WaitUntilCompleterServerReady( app, 'rust' )

  request_data = BuildRequest( filetype = 'rust' )
  debug_info = app.post_json( '/debug_info', request_data ).json
  completer = debug_info[ 'completer' ]
  toolchain = completer[ 'items' ][ 2 ][ 'value' ]

  for message in PollForMessages( app, { 'filepath': filepath,
                                         'contents': contents,
                                         'filetype': 'rust' }, timeout = 5 ):
    try:
      assert_that( message, has_entry(
        'message',
        "Rust Language Server for toolchain "
        "{toolchain} installed.".format( toolchain = toolchain ) ) )
      break
    except AssertionError:
      pass

  AssertRustCompleterServerIsRunning( app, True )


def CannotFindRls( executable ):
  if executable.endswith( 'rls' ):
    return None
  return FindExecutable( executable )


@patch( 'ycmd.utils.FindExecutable', side_effect = CannotFindRls )
@patch( 'ycmd.completers.rust.rust_completer.RustCompleter.'
        '_RunCommandAndNotify',
        side_effect = lambda command: command[ 1 ] != 'self' )
@IsolatedYcmd
def ServerManagement_StartServer_InstallRls_RustupUpdateFailure_test( app,
                                                                      *args ):
  filepath = PathToTestFile( 'common', 'src', 'main.rs' )
  contents = utils.ReadFile( filepath )

  StartCompleterServer( app, 'rust', filepath )

  for message in PollForMessages( app, { 'filepath': filepath,
                                         'contents': contents,
                                         'filetype': 'rust' }, timeout = 5 ):
    try:
      assert_that( message, has_entry( 'message', 'Failed to update rustup.' ) )
      break
    except AssertionError:
      pass

  AssertRustCompleterServerIsRunning( app, False )


@patch( 'ycmd.utils.FindExecutable', side_effect = CannotFindRls )
@patch( 'ycmd.completers.rust.rust_completer.RustCompleter.'
        '_RunCommandAndNotify',
        side_effect = lambda command: command[ 1 ] != 'update' )
@IsolatedYcmd
def ServerManagement_StartServer_InstallRls_ToolchainUpdateFailure_test(
  app, *args ):

  filepath = PathToTestFile( 'common', 'src', 'main.rs' )
  contents = utils.ReadFile( filepath )

  StartCompleterServer( app, 'rust', filepath )

  for message in PollForMessages( app, { 'filepath': filepath,
                                         'contents': contents,
                                         'filetype': 'rust' }, timeout = 5 ):
    try:
      assert_that( message, has_entry(
        'message', starts_with( 'Failed to update toolchain' ) ) )
      break
    except AssertionError:
      pass

  AssertRustCompleterServerIsRunning( app, False )


@patch( 'ycmd.utils.FindExecutable', side_effect = CannotFindRls )
@patch( 'ycmd.completers.rust.rust_completer.RustCompleter.'
        '_RunCommandAndNotify',
        side_effect = lambda command: command[ 1 ] != 'component' )
@IsolatedYcmd
def ServerManagement_StartServer_InstallRls_ComponentUpdateFailure_test(
  app, *args ):

  filepath = PathToTestFile( 'common', 'src', 'main.rs' )
  contents = utils.ReadFile( filepath )

  StartCompleterServer( app, 'rust', filepath )

  for message in PollForMessages( app, { 'filepath': filepath,
                                         'contents': contents,
                                         'filetype': 'rust' }, timeout = 5 ):
    try:
      assert_that( message, has_entry(
        'message', starts_with( 'Failed to update component' ) ) )
      break
    except AssertionError:
      pass

  AssertRustCompleterServerIsRunning( app, False )


def CannotParseVersion( command ):
  if '--version' in command:
    return 'version format not supported'
  return _GetCommandOutput( command )


# @patch( 'ycmd.utils.FindExecutable', side_effect = CannotFindRlsFirstTime() )
@patch( 'ycmd.completers.rust.rust_completer._GetCommandOutput',
        side_effect = CannotParseVersion )
@IsolatedYcmd
def ServerManagement_StartServer_CannotParseVersions_test( app, *args ):
  filepath = PathToTestFile( 'common', 'src', 'main.rs' )
  contents = utils.ReadFile( filepath )

  StartCompleterServer( app, 'rust', filepath )

  expected_messages = [
    'Cannot parse rustup version.',
    'Cannot parse Rust Language Server version.'
  ]

  for message in PollForMessages( app, { 'filepath': filepath,
                                         'contents': contents,
                                         'filetype': 'rust' }, timeout = 5 ):
    try:
      assert_that( message, has_entry( 'message', expected_messages[ 0 ] ) )
      expected_messages.pop( 0 )
      if not expected_messages:
        break
    except AssertionError:
      pass

  WaitUntilCompleterServerReady( app, 'rust' )

  AssertRustCompleterServerIsRunning( app, True )


@IsolatedYcmd
def ServerManagement_StartServer_AlreadyStarting_test( app ):
  filepath = PathToTestFile( 'common', 'src', 'main.rs' )

  StartCompleterServer( app, 'rust', filepath )

  response = app.post_json(
    '/run_completer_command',
    BuildRequest(
      filepath = filepath,
      filetype = 'rust',
      command_arguments = [ 'RestartServer' ],
    ),
    expect_errors = True
  )
  assert_that( response.status_code, requests.codes.internal_server_error )
  assert_that( response.json, ErrorMatcher( RuntimeError,
                                            'Already starting server.' ) )

  WaitUntilCompleterServerReady( app, 'rust' )

  AssertRustCompleterServerIsRunning( app, True )


@IsolatedYcmd
def ServerManagement_StartServer_AlreadyStarted_test( app ):
  filepath = PathToTestFile( 'common', 'src', 'main.rs' )
  StartRustCompleterServerInDirectory( app, filepath )

  AssertRustCompleterServerIsRunning( app, True )

  response = app.post_json( '/event_notification',
    BuildRequest( filepath = filepath,
                  event_name = 'FileReadyToParse',
                  filetype = 'rust' ) )
  assert_that( response.status_code, requests.codes.ok )

  AssertRustCompleterServerIsRunning( app, True )


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
@patch( 'ycmd.utils.WaitUntilProcessIsTerminated', side_effect = RuntimeError )
def ServerManagement_StopServer_Unclean_test( app, *args ):
  StartRustCompleterServerInDirectory( app, PathToTestFile( 'common', 'src' ) )

  request_data = BuildRequest( filetype = 'rust' )
  debug_info = app.post_json( '/debug_info', request_data ).json
  pid = debug_info[ 'completer' ][ 'servers' ][ 0 ][ 'pid' ]
  process = psutil.Process( pid )

  try:
    app.post_json(
      '/run_completer_command',
      BuildRequest(
        filetype = 'rust',
        command_arguments = [ 'StopServer' ],
      ),
    )

    AssertRustCompleterServerIsRunning( app, False )
  finally:
    process.wait( timeout = 30 )


@IsolatedYcmd
def ServerManagement_StopServer_AlreadyStopped_test( app ):
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
