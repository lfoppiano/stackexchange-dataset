import argparse
import os
import traceback
from itertools import repeat
from multiprocessing import Pool, cpu_count

import dotenv
from lm_dataformat import Archive, TextArchive, TEXT_FORMAT, SUPPORTED_FORMATS, \
    JSONL_FORMAT

from downloader import Stack_Exchange_Downloader
from pairer import QA_Pairer

dotenv.load_dotenv(override=True)


def download_and_process_single(name, out_format, min_score, max_responses, output_dir="out", keep_sources=False,
                                stream=False):
    try:
        name = name.strip().lower()
        os.makedirs("dumps", exist_ok=True)
        s = Stack_Exchange_Downloader(name)
        if name not in s.sites:
            similar_entries = list(filter(lambda key: key.startswith(name) or key.endswith(name), s.sites.keys()))
            print("StackExchange source not found. Perhaps you meant", similar_entries)
            return

        path_to_xml = "dumps/{}/Posts.xml".format(name)
        if name != "stackoverflow":
            path_to_7z = "dumps/{}.7z".format(s.sites[name]["url"])
        else:
            path_to_7z = "dumps/stackoverflow.com-Posts.7z"

        out_folder = f"{output_dir}/{name}"
        os.makedirs(out_folder, exist_ok=True)
        if not os.path.isfile(path_to_7z):
            # download 7z if it's not downloaded already
            s.download()

        valid = s.validate()
        if valid is False:
            s.download()
            # s.remove_dump()

        if out_format == JSONL_FORMAT:
            archiver = Archive(out_folder)
        elif out_format == TEXT_FORMAT:
            archiver = TextArchive(out_folder)
        else:
            archiver = None

        if not os.path.isfile(path_to_xml) and not stream:
            # extract 7z if it's not extracted already
            s.extract()

        qa = QA_Pairer(path_to_7z if stream else path_to_xml, compressed=stream, name=name, out_format=out_format,
                       archiver=archiver, min_score=min_score,
                       max_responses=max_responses)
        qa.process()
        archiver.commit(name)

        if not keep_sources:
            try:
                os.remove(path_to_7z)
            except FileNotFoundError:
                print('ERROR: FileNotFoundError: File {} not found'.format(s.sites[name]["url"]))

        directory_uncompressed = "dumps/{}".format(name)
        if os.path.exists(directory_uncompressed):
            filelist = [f for f in os.listdir(directory_uncompressed)
                        if f.endswith(".xml")]
            for f in filelist:
                os.remove(os.path.join(directory_uncompressed, f))
            os.removedirs(directory_uncompressed)
    except:
        traceback.print_exc()


def main(args):
    if args.list:
        s = Stack_Exchange_Downloader("all")
        print("List of all the sources of StackExchange: ")
        print("- " + "\n- ".join(sorted(s.sites.keys())))
        return

    names = args.names.split(',')
    if names[0].strip().lower() == "all":
        s = Stack_Exchange_Downloader("all")
        names = []
        for k in s.sites:
            names.append(k)
        # bring stackoverflow to the front, so it is always processed first, since it's the largest
        if "stackoverflow" in names:
            names.insert(0, names.pop(names.index("stackoverflow")))
        # if args.no_zip:
        #     print("Downloading everything required the output to be compressed. Re-run *without* the option --no-zip.")
        #     sys.exit(-1)
    print('Downloading and processing stackexchange dumps for {}'.format(names))
    # Download & Process
    # init pool with as many CPUs as available
    if args.max_num_threads < 1:
        cpu_no = cpu_count() - 1
    else:
        cpu_no = args.max_num_threads

    p = Pool(cpu_no)
    p.starmap(download_and_process_single,
              zip(names, repeat(args.out_format), repeat(args.min_score), repeat(args.max_responses),
                  repeat(args.out_directory), repeat(args.keep_sources), repeat(args.stream)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='CLI for stackexchange_dataset - A tool for downloading & processing StackExchange dumps '
                    'in XML form to a raw question-answer pair text dataset for Language Models')

    parser.add_argument('--list',
                        help='list of all the sources from StackExchange',
                        required=False,
                        action="store_true")
    parser.add_argument("--output-dir",
                        help="Output directory",
                        required=False,
                        default="out")
    parser.add_argument('--names',
                        help='names of stackexchange to download, extract & parse, separated by commas. '
                             'If "all", will download, extract & parse *every* stackoverflow site',
                        required=True,
                        type=str)
    parser.add_argument('--out-format',
                        help='format of the output file',
                        default=TEXT_FORMAT,
                        choices=SUPPORTED_FORMATS,
                        type=str)
    parser.add_argument('--min_score',
                        help='minimum score of a response to be included in the dataset. Default 3.',
                        type=int,
                        default=3)
    parser.add_argument('--max_responses',
                        help='maximum number of responses (sorted by score) to include for each question. Default 3.',
                        type=int,
                        default=3)
    parser.add_argument('--keep-sources',
                        help='Do not clean up the downloaded source 7z files.',
                        action="store_true",
                        default=False)
    parser.add_argument('--max-num-threads',
                        help="Set the maximum thread number. If not specified will use the number of CPU - 1.",
                        required=False,
                        default=-1,
                        type=int)
    parser.add_argument('--stream',
                        help="Stream the file Posts.xml directly from the 7z without decompressing it. "
                             "Experimental feature. Might not work for the stackoverflow site",
                        required=False,
                        action="store_true",
                        default=False)
    args = parser.parse_args()

    main(args)
