from setuptools import setup, find_packages

setup(
    name="tina-python",
    version="0.7.0rc0",
    packages=find_packages(),
    package_data={"tina": ["py.typed"]},
    install_requires=["httpx", "python-dotenv"],
    extras_require={
        "tui": ["tina-tui>=0.1.0"],
        "multi-agent": ["tina-multi-agent>=0.1.0"],
        "mcp": ["mcp>=2.0"],
    },
    description="tina is in your computer!",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://gitee.com/wang-churi/tina",
    author="王出日",
    author_email="wangchuri@163.com",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
)
