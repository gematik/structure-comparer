import argparse

from .serve import serve

parser = argparse.ArgumentParser(description="Compare profiles and generate mapping")

subparsers = parser.add_subparsers(dest="cmd")

parser_serve = subparsers.add_parser("serve", help="start the server")

args = parser.parse_args()

if args.cmd == "serve":
    serve()
