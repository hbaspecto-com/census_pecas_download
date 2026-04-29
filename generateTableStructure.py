#!/usr/bin/env python

"""generateTableStructure

Tool to create a SQL command which, when run in a database,
will create a table to store CSV data.  To be used with
importcsv.py, which will populate the table with the data.
The tool attempts to figure out the type of each column,
trying first integer, if that doesn't work using double
precision, finally defaulting to character varying.

A table to populate is given by the -t/--table option or
by the basename of the input file (if not standard input).

Fields are either given by the -f/--fields option (comma
separated) or determined from the first row of data.
"""

""" HBA Specto: please see https://bitbucket.org/hbaspecto/hba_scripts_and_handy_hints/src/56d9b2311e3f3d52bb6741a679f735e79e9fd9d5/SQL/readme.md?fileviewer=file-view-default """

__version__ = "0.1"
__author__ = "John Abraham based on csv2sql by James Mills"
__date__ = "23rd Octber 2012"

import os
import csv
import sys
import optparse

USAGE = "%prog [options] <file>"
VERSION = "%prog v" + __version__


def parse_options():
    parser = optparse.OptionParser(usage=USAGE, version=VERSION)

    parser.add_option("-t", "--table",
                      action="store", type="string",
                      default=None, dest="table",
                      help="Specify table name (defaults to filename)")

    parser.add_option("-f", "--fields",
                      action="store", type="string",
                      default=None, dest="fields",
                      help="Specify a list of fields (comma-separated)")

    opts, args = parser.parse_args()

    if len(args) < 1:
        parser.print_help()
        raise SystemExit("No args")

    return opts, args


def generate_rows(f):
    sniffer = csv.Sniffer()
    dialect = sniffer.sniff(f.readline())
    f.seek(0)

    reader = csv.reader(f, dialect)
    for line in reader:
        yield line


def main():
    opts, args = parse_options()

    filename = args[0]

    if filename == "-":
        if opts.table is None:
            raise SystemExit("ERROR: No table specified and stdin used.")
        fd = sys.stdin
        table = opts.table
    else:
        fd = open(filename, "r")
        if opts.table is None:
            table = os.path.splitext(filename)[0]
        else:
            table = opts.table

    rows = generate_rows(fd)

    print("CREATE TABLE %s (" % (table))

    if opts.fields:
        fields = opts.fields.split(',')
    else:
        fields = next(rows)

    # Place to store the column types
    types = []
    for field in fields:
        types.append("integer")

    for i, row in enumerate(rows):
        col = 0
        for fval in row:
            if fval != "":
                try:
                    d = int(fval)
                except ValueError:
                    if types[col] == "integer":
                        print("-- can't convert " + fval + " to integer, trying double for column " + str(col))
                        types[col] = "double precision"
                    try:
                        d = float(fval)
                    except ValueError:
                        if types[col] != "character varying":
                            print(
                                "-- can't convert " + fval + " to float, defaulting to varchar for column " + str(col))
                            types[col] = "character varying"
            col = col + 1

    fieldnum = 0
    for field in fields:
        if (fieldnum == len(fields) - 1):
            print("\"%s\" %s" % (field, types[fieldnum]))
        else:
            print("\"%s\" %s," % (field, types[fieldnum]))
        fieldnum = fieldnum + 1
    print(");")


if __name__ == "__main__":
    main()

