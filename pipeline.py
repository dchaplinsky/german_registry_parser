import re
import io
import sys
import os.path
import json
import gzip
import random
import argparse
import glob
from csv import DictWriter
from collections import defaultdict, Counter

import prettytable
from tqdm import tqdm
from natsort import natsorted

from registry_parser import parse_document

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
        stats = defaultdict(Counter)
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
                    if parsing_result:
                        stats[p_doc["notice_id"]].update({k: len(v) for k, v in parsing_result.items()})
                        if "persons" not in parsing_result:
                            stats[p_doc["notice_id"]].update(["got_no_persons"])
                    else:
                        stats[p_doc["notice_id"]]["got_nothing"] = 1

                    json.dump(
                        {"orig": p_doc, "parsed": parsing_result},
                        fp,
                        indent=4,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str
                    )

        global_stats = Counter()
        global_stats_headers = set()
        for v in stats.values():
            global_stats_headers |= set(v.keys())
        
        fieldnames=["notice_id"] + list(sorted(global_stats_headers))

        with open(os.path.join(outdir, "__detailed_stats.csv"), "w") as fp:
            w = DictWriter(fp, fieldnames=fieldnames)
            w.writeheader()

            for k in natsorted(stats.keys()):
                global_stats.update(stats[k])
                row = {"notice_id": k}
                row.update(stats[k])
                w.writerow(row)

        with open(os.path.join(outdir, "__detailed_stats.csv"), "r") as fp:
            prettified = prettytable.from_csv(fp)

        with open(os.path.join(outdir, "__detailed_stats.txt"), "w") as fp:
            fp.write(prettified.get_string())

        with open(os.path.join(outdir, "__global_stats.json"), "w") as fp:
            fp.write(json.dumps(global_stats, indent=4, sort_keys=True))
