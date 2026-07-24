"""
Mirror.ng - Financial Mirror for Nigerian Banks
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="mirror-ng",
    version="1.2.0",
    author="Mirror.ng Team",
    author_email="team@mirror.ng",
    description="Financial mirror for Nigerian bank alerts with ML insights",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/mirror-ng/mirror-ng",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Financial and Insurance Industry",
        "Topic :: Office/Business :: Financial :: Accounting",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.4.3",
            "pytest-asyncio>=0.21.1",
            "black>=23.12.1",
            "isort>=5.13.2",
            "flake8>=7.0.0",
            "mypy>=1.8.0",
        ],
        "production": [
            "gunicorn>=21.2.0",
            "uvloop>=0.19.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "mirror-ng=backend.app.main:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)