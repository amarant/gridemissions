from setuptools import setup, find_packages

setup(
    name="gridemissions",
    package_dir={"": "src"},
    packages=find_packages("src"),
    version="0.1.0",
    python_requires=">=3.8",
    install_requires=[
        "requests",
        "pandas>=1.1.2"
    ],
    entry_points={
        "console_scripts": [
            "download_emissions=gridemissions.scripts.download:main",
        ],
    },
)
