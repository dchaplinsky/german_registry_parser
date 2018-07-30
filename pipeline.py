# coding=utf-8
import argparse
import glob
import gzip
import json
import os.path
import random
import re
from collections import defaultdict, Counter
from itertools import chain
from csv import DictWriter

import prettytable
from natsort import natsorted
from tqdm import tqdm

from registry_parser import parse_document, dob_regex

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
        "--percent_of_officers",
        type=float,
        default=60,
        help="Number of records in sample that should contain information on officers",
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
        "--add_federal_state",
        action="store_true",
        default=False,
        help="Add federal state to the filenames when parsing",
    )
    parser_parse.add_argument(
        "outdir", type=str, help="path to a dir to store results in. Will be wiped!!!"
    )
    args = parser.parse_args()

    if args.operation == "sample":
        infile = gzip.open(args.infile, "rt")
        outfile = gzip.open(args.outfile, "wt")

        num_of_usual_records = round(
            args.num_of_records
            * (100 - args.percent_of_relocated - args.percent_of_officers)
            / 100
        )
        num_of_relocated_records = round(
            args.num_of_records * args.percent_of_relocated / 100
        )
        num_of_officers_records = round(
            args.num_of_records * args.percent_of_officers / 100
        )

        num_lines = 0
        relocated_records = []
        officers_records = []
        usual_records = []

        with tqdm() as pbar:
            for l in infile:
                pbar.update(1)

                for rel_sign, rel_sign_regex in relocation_signs:
                    # cheap-n-dirty, no json parsing
                    l_lower = l.lower()

                    if rel_sign in l_lower and rel_sign_regex.search(l_lower):
                        # Special case for overused word nun:
                        factor = 1.0

                        # Penalizing it by a factor of 5
                        if rel_sign == "nun":
                            factor = 0.2

                        if random.random() <= factor:
                            signs_usage[rel_sign] += 1
                            relocated_records.append(l)

                            break
                else:
                    if dob_regex.search(l):
                        officers_records.append(l)
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

        print(num_of_usual_records, num_lines)
        print(num_of_relocated_records, len(relocated_records))
        print(num_of_officers_records, len(officers_records))

        for rec in chain(
            random.sample(usual_records, num_of_usual_records),
            random.sample(relocated_records, num_of_relocated_records),
            random.sample(officers_records, num_of_officers_records),
        ):
            outfile.write(rec)

    elif args.operation == "parse":
        stats = defaultdict(Counter)
        outdir = os.path.abspath(args.outdir)
        infile = gzip.open(args.infile, "rt")

        for f in glob.glob(os.path.join(outdir, "*.json")):
            os.remove(f)

        with tqdm() as pbar:
            for l in infile:
                pbar.update(1)
                p_doc = json.loads(l)
                parsing_result, _ = parse_document(p_doc)
                notice_id = p_doc["notice_id"]
                federal_state = p_doc["federal_state"]

                if args.add_federal_state:
                    fname = os.path.join(outdir, "{}_{}.json".format(notice_id, federal_state))
                else:
                    fname = os.path.join(outdir, "{}.json".format(notice_id))

                with open(fname, "w") as fp:
                    if parsing_result:
                        stats[notice_id].update(
                            {k: len(v) for k, v in parsing_result.items()}
                        )
                        possible_persons = dob_regex.findall(p_doc["full_text"])

                        if len(possible_persons) > len(
                            parsing_result.get("officers", [])
                        ):
                            stats[notice_id]["might_have_unparsed_persons"] = 1

                        if "officers" not in parsing_result:
                            stats[notice_id]["got_no_persons"] = 1
                    else:
                        stats[notice_id]["got_no_persons"] = 1
                        stats[notice_id]["got_nothing"] = 1

                    json.dump(
                        {"orig": p_doc, "parsed": parsing_result},
                        fp,
                        indent=4,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    )

        global_stats = Counter()
        global_stats_headers = set()

        for v in stats.values():
            global_stats_headers |= set(v.keys())

        fieldnames = ["notice_id"] + sorted(global_stats_headers)

        with open(
            os.path.join(outdir, "__detailed_stats.csv"), "w"
        ) as f_detailed, open(
            os.path.join(outdir, "__global_stats.json"), "w"
        ) as f_global:
            w = DictWriter(f_detailed, fieldnames=fieldnames)
            w.writeheader()

            for k in natsorted(stats.keys()):
                global_stats.update(stats[k])
                row = {"notice_id": k}
                row.update(stats[k])
                w.writerow(row)

            json.dump(global_stats, f_global, indent=4, sort_keys=True)

        with open(os.path.join(outdir, "__detailed_stats.csv"), "r") as f_in, open(
            os.path.join(outdir, "__detailed_stats.txt"), "w"
        ) as f_out:
            f_out.write(prettytable.from_csv(f_in).get_string())
