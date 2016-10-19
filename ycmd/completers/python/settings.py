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

import logging
import os

from ycmd import extra_conf_store
from ycmd.responses import YCM_EXTRA_CONF_FILENAME
from ycmd.utils import PathsToAllParentFolders


# List of files that we are looking for to find the project root, from highest
# to lowest priority.
CANDIDATES_FOR_PROJECT_ROOT = [ YCM_EXTRA_CONF_FILENAME,
                                'setup.py',
                                '__main__.py' ]


class PythonSettings():

  def __init__( self ):
    self._project_root_for_file = {}
    self._settings_for_project_root = {}
    self._logger = logging.getLogger( __name__ )


  def SettingsForFile( self, filename, client_data = None ):
    project_root = self.GetProjectRootForFile( filename )

    try:
      return self._settings_for_project_root[ project_root ]
    except KeyError:
      pass

    return self._GetSettingsForProjectRoot( project_root,
                                            client_data = client_data )


  def _GetSettingsForProjectRoot( self, project_root, client_data ):
    if not project_root:
      return {}

    module = extra_conf_store.ModuleForSourceFile( project_root )
    if not module:
      # We don't warn the user if no .ycm_extra_conf.py file is found.
      return {}

    try:
      return module.PythonSettings( client_data = client_data )
    except AttributeError:
      self._logger.warning( 'No PythonSettings function defined '
                            'in extra conf file.' )
      return {}


  def GetProjectRootForFile( self, filename ):
    try:
      return self._project_root_for_file[ filename ]
    except KeyError:
      pass

    if not filename:
      self._project_root_for_file[ filename ] = None
      return None

    parent_folders = list( PathsToAllParentFolders( filename ) )

    for candidate in CANDIDATES_FOR_PROJECT_ROOT:
      for folder in parent_folders:
        if os.path.isfile( os.path.join( folder, candidate ) ):
          self._project_root_for_file[ filename ] = folder
          return folder

    # Find the top-most directory that contains a __init__.py file. The project
    # root is likely to be its parent folder.
    top_most_init_folder = None
    for folder in parent_folders:
      if os.path.isfile( os.path.join( folder, '__init__.py' ) ):
        top_most_init_folder = os.path.dirname( folder )

    self._project_root_for_file[ filename ] = top_most_init_folder
    return top_most_init_folder
