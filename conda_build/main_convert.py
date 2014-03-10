# (c) Continuum Analytics, Inc. / http://continuum.io
# All Rights Reserved
#
# conda is distributed under the terms of the BSD 3-clause license.
# Consult LICENSE.txt or http://opensource.org/licenses/BSD-3-Clause.

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import json
import pprint
import re
import tarfile
from argparse import RawDescriptionHelpFormatter
from locale import getpreferredencoding
from os.path import abspath, expanduser, split, join

from conda.compat import PY3

from conda_build.convert import (has_cext, tar_update, get_pure_py_file_map,
                                 has_nonpy_entry_points)


epilog = """

For now, it is just a tool to convert pure Python packages to other platforms.

The output file name will be the same as the input filename, so the -o option
is required, and cannot be the same directory as any of the input files.

It is recommended to keep packages organized in subdirectories according to
platform, e.g.,

osx-64/
  package-1.0-py33.tar.bz2
win-32/
  package-1.0-py33.tar.bz2

Examples:

Convert a package built with conda build to Windows 64-bit, and place the
resulting package in the current directory (supposing a default Anaconda
install on Mac OS X):

$ conda convert ~/anaconda/conda-bld/osx-64/package-1.0-py33.tar.bz2 -o . -p win-64
"""


def main():
    p = argparse.ArgumentParser(
        description='various tools to convert conda packages'
    )

    # TODO: Factor this into a subcommand, since it's python package specific
    p.add_argument(
        'package_files',
        metavar='package-files',
        action="store",
        nargs='+',
        help="package files to convert"
    )
    p.add_argument(
        '-p', "--platform",
        dest='platforms',
        action="append",
        choices=['osx-64', 'linux-32', 'linux-64', 'win-32', 'win-64'],
        required=True,
        help="Platform to convert the packages to"
    )
    p.add_argument(
        '--show-imports',
        action='store_true',
        default=False,
        help="Show Python imports for compiled parts of the package",
    )
    p.add_argument(
        '-f', "--force",
        action="store_true",
        help="Force convert, even when a package has compiled C extensions",
    )
    p.add_argument(
        '-o', '--output-dir',
        required=True,
        help="""Directory to write the output files (this cannot be the same
                directory as the input file, as they will share the same
                name)"""
    )
    p.add_argument(
        '-v', '--verbose',
        default=False,
        action='store_true',
        help="Print verbose output"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="only display what would have been done",
    )

    p.set_defaults(func=execute)

    args = p.parse_args()
    args.func(args, p)


path_mapping = [# (unix, windows)
                ('lib/python{pyver}', 'Lib'),
                ('bin', 'Scripts')]

pyver_re = re.compile(r'python\s+(\d.\d)')


def execute(args, parser):
    files = args.package_files

    for file in files:
        # Don't use byte literals for paths in Python 2
        if not PY3:
            file = file.decode(getpreferredencoding())

        if not file.endswith('.tar.bz2'):
            raise RuntimeError("%s does not appear to be a conda package"
                               % file)

        file = abspath(expanduser(file))
        t = tarfile.open(file)
        cext = False
        if args.show_imports:
            cext = has_cext(t, show=True)

        if not args.force and (cext or has_cext(t)):
            print("WARNING: Package %s has C extensions, skipping. Use -f to "
                  "force conversion." % file)
            continue

        output_dir = args.output_dir
        if not PY3:
            output_dir = output_dir.decode(getpreferredencoding())
        file_dir, fn = split(file)
        if abspath(expanduser(output_dir)) == abspath(expanduser(file_dir)):
            raise RuntimeError(
                "Cannot use the same output directory as the input files.")

        info = json.loads(t.extractfile('info/index.json')
                          .read().decode('utf-8'))
        source_type = 'unix' if info['platform'] in {'osx', 'linux'} else 'win'

        nonpy_unix = False
        nonpy_win = False

        for platform in args.platforms:
            if not PY3:
                platform = platform.decode('utf-8')
            dest_plat = platform.split('-')[0]
            dest_type = 'unix' if dest_plat in {'osx', 'linux'} else 'win'

            if source_type == 'unix' and dest_type == 'win':
                nonpy_unix = nonpy_unix or has_nonpy_entry_points(t,
                                                                  unix_to_win=True,
                                                                  show=args.verbose)
            if source_type == 'win' and dest_type == 'unix':
                nonpy_win = nonpy_win or has_nonpy_entry_points(t,
                                                                unix_to_win=False,
                                                                show=args.verbose)

            if nonpy_unix and not args.force:
                print(("WARNING: Package %s has non-Python entry points, "
                       "skipping %s to %s conversion. Use -f to force.") %
                      (file, info['platform'], platform))
                continue

            if nonpy_win and not args.force:
                print(("WARNING: Package %s has entry points, which are not "
                       "supported yet. Skipping %s to %s conversion. Use -f to force.") %
                      (file, info['platform'], platform))
                continue

            file_map = get_pure_py_file_map(t, platform)

            if args.dry_run:
                print("Would convert %s from %s to %s" %
                      (file, info['platform'], dest_plat))
                if args.verbose:
                    pprint.pprint(file_map)
                continue
            else:
                print("Converting %s from %s to %s" %
                      (file, info['platform'], dest_plat))

            tar_update(t, join(output_dir, fn), file_map, verbose=args.verbose)


if __name__ == '__main__':
    main()
