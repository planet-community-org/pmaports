#!/usr/bin/env python3
# Copyright 2022 Oliver Smith
# SPDX-License-Identifier: GPL-3.0-or-later
# Various checks on source= in the APKBUILDs

import glob
import logging
import os
import pytest
import sys

# Same dir
import common

# pmbootstrap
import add_pmbootstrap_to_import_path
import pmb.parse
import pmb.parse._apkbuild
import pmb.parse.apkindex
import pmb.helpers.repo


def test_aports_unreferenced_files(args):
    """
    Raise an error if an unreferenced file is found
    """
    for apkbuild_path in glob.iglob(args.aports + "/**/APKBUILD", recursive=True):
        # pmbootstrap parser has some issues with complicated APKBUILDs, skip those.
        if apkbuild_path.startswith(args.aports + "/cross/"):
            continue

        apkbuild = pmb.parse.apkbuild(apkbuild_path)
        sources_chk = common.parse_apkbuild_checksums(args, apkbuild_path)

        # Collect files from subpackages
        subpackage_installs = []
        subpackage_triggers = []
        if apkbuild["subpackages"]:
            for subpackage in apkbuild["subpackages"].values():
                if not subpackage:
                    continue
                subpackage_installs += subpackage.get("install", [])
                subpackage_triggers += subpackage.get("triggers", [])

        # Collect trigger files
        trigger_sources = []
        for trigger in apkbuild["triggers"] + subpackage_triggers:
            trigger_sources.append(trigger.split("=")[0])

        dirname = os.path.dirname(apkbuild_path)
        for file in glob.iglob(dirname + "/**", recursive=True):
            rel_file_path = os.path.relpath(file, dirname)
            # Skip APKBUILDs and directories
            if rel_file_path == "APKBUILD" or os.path.isdir(file):
                continue

            if os.path.basename(rel_file_path) not in sources_chk \
                    and rel_file_path not in apkbuild["install"] \
                    and rel_file_path not in subpackage_installs \
                    and rel_file_path not in trigger_sources:
                raise RuntimeError(f"{apkbuild_path}: found unreferenced file: {rel_file_path}")


def test_distfiles_conflict(args):
    """
    Make sure that each filename mentioned in any source= of any APKBUILD
    always has the same checksum. This is important because apk caches
    downloaded source files in a flat distfiles directory. So if two APKBUILDs
    both download a file with the same filename but different checksum, and the
    user builds both after each other, abuild will fail on the second build
    with a checksum error.
    """
    source_all = {}
    for apkbuild_path in glob.iglob(f"{args.aports}/**/APKBUILD", recursive=True):
        source = common.parse_apkbuild_checksums(args, apkbuild_path)
        dir_path = os.path.dirname(apkbuild_path)
        apkbuild_rel = os.path.relpath(apkbuild_path, args.aports)
        for filename, checksum in source.items():
            # Files bundled with the APKBUILD don't get copied to the distfiles
            # cache, so not relevant for this check. Use glob.glob here and not
            # iglob, because we don't want an iterator.
            if glob.glob(f"{dir_path}/**/{filename}", recursive=True):
                continue

            # First time seeing this file
            if filename not in source_all:
                source_all[filename] = {"checksum": checksum,
                                        "apkbuild_rel": apkbuild_rel}
                continue

            # Saw this file already with same checksum
            if checksum == source_all[filename]["checksum"]:
                continue

            # Saw this file already with different checksum
            logging.error("")
            logging.error(f"ERROR: the source file '{filename}' has different"
                          " checksums in the following files:")
            logging.error(f"- {source_all[filename]['apkbuild_rel']}:")
            logging.error(f"  {source_all[filename]['checksum']}")
            logging.error(f"- {apkbuild_rel}:")
            logging.error(f"  {checksum}")
            logging.error("")
            logging.error("Fix this by setting a different target filename in"
                          " the package you modified:")
            logging.error("https://wiki.alpinelinux.org/wiki/APKBUILD_Reference#source")
            logging.error("")
            raise RuntimeError(f"Conflict with source file '{filename}'")
