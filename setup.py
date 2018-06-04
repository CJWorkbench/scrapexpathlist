from setuptools import setup

setup(
    name='scrapexpathlist',
    version='0.0.1',
    description='Fetch HTML and supply a vector of strings matching xpath',
    author='Adam Hooper',
    author_email='adam@adamhooper.com',
    url='https://github.com/CJWorkbench/scrape-xpath-list',
    packages=[ '' ],
    py_modules=[ 'scrapexpathlist' ],
    install_requires=[ 'pandas==0.23.0', 'lxml==4.2.1', 'html5lib==1.0.1' ]
)
