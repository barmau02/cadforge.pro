"""Setup for cli-anything-freecad — CLI harness for FreeCAD."""

from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-freecad-pf",
    version="1.0.0+pf1",
    description="CadForge sanitized CLI harness for FreeCAD (headless batch)",
    long_description=open("cli_anything/freecad/README.md").read(),
    long_description_content_type="text/markdown",
    author="CLI-Anything Contributors (CadForge fork)",
    license="Apache-2.0",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    py_modules=["pf_freecad_cli"],
    python_requires=">=3.10",
    install_requires=[
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "pf-freecad-cli=pf_freecad_cli:main",
            "cli-anything-freecad=cli_anything.freecad.freecad_cli:main",
        ],
    },
    package_data={
        "cli_anything.freecad": ["skills/*.md"],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Visualization",
    ],
)
