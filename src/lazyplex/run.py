#!/usr/bin/env python
import argparse
import logging
import os
import sys
from importlib import import_module

from lazyplex import Application

logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        prog='Lazyplex runner',
        description='Start your own lazyplex application',
    )
    parser.add_argument('path')
    return parser.parse_args()


def load_applications(name: str):
    loaded = import_module(name)

    return [attr for attr in vars(loaded).values()
            if isinstance(attr, Application)]


def main():
    sys.path.insert(0, os.getcwd())

    args = parse_args()
    apps = load_applications(args.path)

    try:
        apps[0].run_until_complete()
    except Exception as e:
        logger.exception(e)


if __name__ == '__main__':
    main()
