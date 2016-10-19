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
from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

from mock import MagicMock, patch
from hamcrest import assert_that, empty, equal_to, has_entries

from ycmd.completers.python.settings import PythonSettings
from ycmd.tests.python import PathToTestFile


def PythonSettings_GetProjectRootForFile_NoFilename_test():
  python_settings = PythonSettings()
  assert_that(
    python_settings.GetProjectRootForFile( None ),
    equal_to( None )
  )


def PythonSettings_GetProjectRootForFile_NoProject_test():
  python_settings = PythonSettings()
  filename = PathToTestFile( 'no_project', 'script.py' )
  assert_that(
    python_settings.GetProjectRootForFile( filename ),
    equal_to( None )
  )


def PythonSettings_GetProjectRootForFile_ExtraConfProject_test():
  python_settings = PythonSettings()
  filename = PathToTestFile( 'extra_conf_project', 'package', 'module',
                             'file.py' )
  assert_that(
    python_settings.GetProjectRootForFile( filename ),
    equal_to( PathToTestFile( 'extra_conf_project' ) )
  )


def PythonSettings_GetProjectRootForFile_SetupProject_test():
  python_settings = PythonSettings()
  filename = PathToTestFile( 'setup_project', 'package', 'module', 'file.py' )
  assert_that(
    python_settings.GetProjectRootForFile( filename ),
    equal_to( PathToTestFile( 'setup_project' ) )
  )


def PythonSettings_GetProjectRootForFile_InitProject_test():
  python_settings = PythonSettings()
  filename = PathToTestFile( 'init_project', 'package', 'module', 'file.py' )
  assert_that(
    python_settings.GetProjectRootForFile( filename ),
    equal_to( PathToTestFile( 'init_project' ) )
  )


def PythonSettings_GetProjectRootForFile_Package_test():
  python_settings = PythonSettings()
  filename = PathToTestFile( 'package', 'module', 'file.py' )
  assert_that(
    python_settings.GetProjectRootForFile( filename ),
    equal_to( PathToTestFile( 'package' ) )
  )


def PythonSettings_SettingsForFile_NoFilename_test():
  python_settings = PythonSettings()
  assert_that(
    python_settings.SettingsForFile( None ),
    empty()
  )


def PythonSettings_SettingsForFile_NoProject_test():
  python_settings = PythonSettings()
  filename = PathToTestFile( 'no_project', 'script.py' )
  assert_that(
    python_settings.SettingsForFile( filename ),
    empty()
  )


def PythonSettings_SettingsForFile_ExtraConfProject_NoPythonSettings_test():
  python_settings = PythonSettings()
  filename = PathToTestFile( 'extra_conf_project', 'package', 'module',
                             'file.py' )

  module = MagicMock()
  module.PythonSettings = MagicMock( side_effect = AttributeError(
      "module 'random_name' has no attribute 'PythonSettings'" ) )

  with patch( 'ycmd.extra_conf_store.ModuleForSourceFile',
              return_value = module ):
    assert_that(
      python_settings.SettingsForFile( filename ),
      empty()
    )


def PythonSettings_SettingsForFile_ExtraConfProject_NoSettings_test():
  python_settings = PythonSettings()
  filename = PathToTestFile( 'extra_conf_project', 'package', 'module',
                             'file.py' )

  module = MagicMock()
  module.PythonSettings = MagicMock( return_value = {} )

  with patch( 'ycmd.extra_conf_store.ModuleForSourceFile',
              return_value = module ):
    assert_that(
      python_settings.SettingsForFile( filename ),
      empty()
    )


def PythonSettings_SettingsForFile_ExtraConfProject_CustomSettings_test():
  python_settings = PythonSettings()
  filename = PathToTestFile( 'extra_conf_project', 'package', 'module',
                             'file.py' )

  module = MagicMock()
  module.PythonSettings = MagicMock( return_value = {
    'interpreter_path': '/path/to/python'
  } )

  with patch( 'ycmd.extra_conf_store.ModuleForSourceFile',
              return_value = module ):
    assert_that(
      python_settings.SettingsForFile( filename ),
      has_entries( {
        'interpreter_path': '/path/to/python'
      } )
    )


def PythonSettings_SettingsForFile_SetupProject_test():
  python_settings = PythonSettings()
  filename = PathToTestFile( 'setup_project', 'package', 'module', 'file.py' )
  assert_that(
    python_settings.SettingsForFile( filename ),
    empty()
  )


def PythonSettings_SettingsForFile_InitProject_test():
  python_settings = PythonSettings()
  filename = PathToTestFile( 'init_project', 'package', 'module', 'file.py' )
  assert_that(
    python_settings.SettingsForFile( filename ),
    empty()
  )


def PythonSettings_SettingsForFile_Package_test():
  python_settings = PythonSettings()
  filename = PathToTestFile( 'package', 'module', 'file.py' )
  assert_that(
    python_settings.SettingsForFile( filename ),
    empty()
  )
