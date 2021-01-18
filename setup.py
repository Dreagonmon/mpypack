#!/usr/bin/env python
from setuptools import setup
from mpypack import version

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="mpypack",
    version=version.FULL,
    description="A simple tool to pack up MicroPython code ",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Dreagonmon",
    author_email="531486058@qq.com",
    url="https://github.com/dreagonmon/mpypack",
    install_requires=["pyserial", "mpy_cross", "click"],
    packages=['mpypack'],
    keywords=["micropython", "file transfer", "development"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
    ],
    entry_points={"console_scripts": ["mpypack=mpypack.cli:main"]},
    python_requires='>=3.6',
)

# python mpypack\cli.py