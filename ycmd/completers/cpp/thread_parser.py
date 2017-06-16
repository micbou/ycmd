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

import _thread
import logging
import threading

OUTDATED_THREAD_MESSAGE = ( 'Newer thread #{0} is waiting to be parsed. '
                            'Drop thread #{1}.' )


class ThreadParser( object ):
  def __init__( self ):
    self._condition = threading.Condition()
    self._latest_time = 0.0
    self._latest_thread_id = 0
    self._logger = logging.getLogger( __name__ )
    self._being_parsed_lock = threading.Lock()
    self._being_parsed = False


  def Parse( self, current_time ):
    return ThreadParserContext( self, current_time )



class ThreadParserContext( object ):

  def __init__( self, parent, current_time ):
    self._logger = parent._logger
    self._parent = parent
    self._thread_id = _thread.get_ident()
    self._condition = parent._condition
    self._current_time = current_time


  def _ParsingStarted( self ):
    with self._parent._being_parsed_lock:
      self._parent._being_parsed = True


  def _ParsingFinished( self ):
    with self._parent._being_parsed_lock:
      self._parent._being_parsed = False


  def _BeingParsed( self ):
    with self._parent._being_parsed_lock:
      return self._parent._being_parsed


  def _IsOutdated( self ):
    return self._current_time < self._parent._latest_time


  def _SetLatest( self ):
    self._parent._latest_time = self._current_time
    self._parent._latest_thread_id = self._thread_id


  def __enter__( self ):
    self._condition.acquire()
    if self._IsOutdated():
      self._condition.release()
      raise RuntimeError( OUTDATED_THREAD_MESSAGE.format(
          self._parent._latest_thread_id,
          self._thread_id ) )
    self._SetLatest()
    self._condition.notify_all()
    self._condition.release()

    while self._BeingParsed():
      self._condition.acquire()
      self._condition.wait()
      if self._IsOutdated():
        self._condition.release()
        raise RuntimeError( OUTDATED_THREAD_MESSAGE.format(
            self._parent._latest_thread_id,
            self._thread_id ) )
      self._condition.release()

    self._logger.debug( 'Parsing thread #{0}'.format( self._thread_id ) )
    self._ParsingStarted()


  def __exit__( self, *unused_args ):
    self._logger.debug( 'Thread #{0} parsed'.format( self._thread_id ) )
    self._ParsingFinished()

    self._condition.acquire()
    self._condition.notify_all()
    self._condition.release()
