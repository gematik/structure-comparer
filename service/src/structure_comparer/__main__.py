import argparse
from pathlib import Path

from .serve import serve
from .output import output

parser = argparse.ArgumentParser(description="Compare profiles and generate mapping")

subparsers = parser.add_subparsers(dest="cmd", required=True)

parser_serve = subparsers.add_parser("serve", help="start the server")

parser_output = subparsers.add_parser("output", help="generate output files")
parser_output.add_argument(
    "--project-dir",
    type=Path,
    required=True,
    help="The project directory containing the profiles and config",
)
parser_output.add_argument(
    "--format",
    choices=["json", "html"],
    default="html",
    help="The output format (default: html)",
)
parser_output.add_argument(
    "--mapping_id",
    type=str,
    default=None,
    help="The ID of the mapping to generate output for (default: all mappings)",
)

args = parser.parse_args()
if args.cmd == "serve":
    serve()
elif args.cmd == "output":
    output(args.project_dir, args.format, args.mapping_id)
else:
    parser.print_help()
