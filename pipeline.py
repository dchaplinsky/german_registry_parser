import re
import io
import sys
import os.path
import json
import gzip
import random
import argparse
import glob
from collections import defaultdict

from tqdm import tqdm
from parser import parse_document

relocation_signs = [
    ("sitzverlegung", re.compile(r"\bsitzverlegung\b")),
    ("verlecht", re.compile(r"\bverlecht\b")),
    ("nun", re.compile(r"\bnun\b")),
    ("bisher", re.compile(r"\bbisher\b")),
    ("jetzt", re.compile(r"\bjetzt\b")),
    ("nach", re.compile(r"\bnach.{1,8}amtsgericht\b")),
]

signs_usage = defaultdict(int)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Major operations on scrapped file")
    subparsers = parser.add_subparsers(
        help="All available operations", dest="operation"
    )
    parser_sample = subparsers.add_parser(
        "sample",
        help="Process input file and output random sample file of a given size (jsonlines, gzip)",
    )

    parser_sample.add_argument(
        "infile", help="Input file with company records, jsonlines, gzipped", type=str
    )

    parser_sample.add_argument(
        "--num_of_records", type=int, default=1000, help="Number of records to sample"
    )
    parser_sample.add_argument(
        "--percent_of_relocated",
        type=float,
        default=20,
        help="Number of records in sample that should contain links to pred/succ records",
    )
    parser_sample.add_argument(
        "outfile", type=str, help="random sample of an input file"
    )

    parser_parse = subparsers.add_parser(
        "parse",
        help="Process input file and and store parsed results into outdir, json",
    )
    parser_parse.add_argument(
        "infile", help="Input file with company records, jsonlines, gzipped", type=str
    )

    parser_parse.add_argument(
        "outdir", type=str, help="path to a dir to store results in. Will be wiped!!!"
    )
    args = parser.parse_args()

    if args.operation == "sample":
        infile = gzip.open(args.infile, "rt")
        outfile = gzip.open(args.outfile, "wt")

        num_of_usual_records = round(
            args.num_of_records * (100 - args.percent_of_relocated) / 100
        )
        num_of_relocated_records = round(
            args.num_of_records * args.percent_of_relocated / 100
        )

        num_lines = 0
        relocated_records = []
        usual_records = []

        with tqdm() as pbar:
            for l in infile:
                pbar.update(1)
                for rel_sign, rel_sign_regex in relocation_signs:
                    # cheap-n-dirty, no json parsing
                    l = l.lower()
                    if rel_sign in l:
                        if rel_sign_regex.search(l):
                            signs_usage[rel_sign] += 1
                            relocated_records.append(l)
                            break
                else:
                    num_lines += 1

        print(signs_usage)

        infile.seek(0)
        prob_of_usual_rec = 2 * num_of_usual_records / num_lines

        with tqdm() as pbar:
            for l in infile:
                pbar.update(1)
                if random.random() < prob_of_usual_rec:
                    usual_records.append(l)

        print(num_of_usual_records, len(usual_records))
        print(num_of_relocated_records, len(relocated_records))
        for rec in random.sample(usual_records, num_of_usual_records):
            outfile.write(rec)

        for rec in random.sample(relocated_records, num_of_relocated_records):
            outfile.write(rec)

    elif args.operation == "parse":
        outdir = os.path.abspath(args.outdir)
        infile = gzip.open(args.infile, "rt")
        for f in glob.glob(outdir + "*.json"):
            os.remove(f)

        with tqdm() as pbar:
            for l in infile:
                pbar.update(1)
                p_doc = json.loads(l)
                parsing_result, _ = parse_document(p_doc)
                with open(
                    os.path.join(outdir, p_doc["notice_id"] + ".json"), "w"
                ) as fp:
                    json.dump(
                        {"orig": p_doc, "parsed": [x.to_dict() for x in parsing_result]},
                        fp,
                        indent=4,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str
                    )
