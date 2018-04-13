#!/usr/bin/env python

import argparse
import cProfile
import json
import pstats
import os
import subprocess
import sys
import tempfile
from distutils.spawn import find_executable

DIR_OF_THIS_SCRIPT = os.path.dirname( os.path.abspath( __file__ ) )
DIR_OF_THIRD_PARTY = os.path.join( DIR_OF_THIS_SCRIPT, 'third_party' )

from ycmd.completers.completer_utils import FilterAndSortCandidatesWrap


def Run( candidates ):
  FilterAndSortCandidatesWrap( candidates, "insertion_text", "G", 0 )


def ParseArguments():
  parser = argparse.ArgumentParser()
  parser.add_argument( '--runs', type = int, default = 10,
                       help = 'Number of runs.' )
  parser.add_argument( '--visualize', action = 'store_true',
                       help = 'Visualize profiling data.' )
  return parser.parse_args()


def Main():
  args = ParseArguments()

  profile = cProfile.Profile()

  with open( os.path.join( DIR_OF_THIS_SCRIPT, 'windows_header_candidates' ),
             'r' ) as f:
    candidates = json.loads( f.read() )

  # Warmup
  Run( candidates )

  for _ in range( args.runs ):
    profile.enable()
    import time
    tic = time.perf_counter()
    Run( candidates )
    print( time.perf_counter() - tic )
    profile.disable()

  stats = pstats.Stats( profile ).sort_stats( 'cumulative' )
  average_time = int( stats.total_tt * 1000 / args.runs )

  print( 'Average time on {0} runs: {1}ms\n'.format( args.runs, average_time ) )

  if args.visualize:
    import pyprof2calltree
    pyprof2calltree.visualize( stats )


if __name__ == "__main__":
  Main()
